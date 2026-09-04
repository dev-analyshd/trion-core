/**
 * Minimal dependency-free Socket.IO v5 / Engine.IO v4 client.
 *
 * WHY this exists: the backend exposes a real WebSocket push layer —
 * `serve.py` wraps the Flask app with flask-socketio (api/socket_push.py,
 * namespace `/feed`) and emits `signal` (new feed entries) and `health`
 * (stats packet) events. The public dashboard should consume it without
 * adding the ~90KB `socket.io-client` npm dependency, so this module
 * speaks the wire protocol directly with the standard browser WebSocket
 * API (WebSocket transport only — engine.io v4).
 *
 * Wire protocol (Engine.IO v4 / Socket.IO v5):
 *   connect URL:  {ws|wss}://{host}/socket.io/?EIO=4&transport=websocket
 *   server → "0{...}"            engine.io OPEN (sid, pingInterval, pingTimeout)
 *   client → "40/feed,"          socket.io CONNECT on namespace /feed
 *   server → "40/feed,{...}"     namespace connect ack
 *   server → "42/feed,[\"signal\",{...}]"   socket.io EVENT
 *   server → "2"                 engine.io PING (server-initiated in v4)
 *   client → "3"                 engine.io PONG (must answer or server drops us)
 *   server → "4"                 engine.io CLOSE
 *
 * Reconnect handling: exponential backoff 1s→2s→4s→…→30s (capped), reset on
 * a successful (re)connect, plus a keepalive watchdog that force-closes the
 * socket when no engine.io ping arrives within pingInterval+pingTimeout.
 *
 * Not implemented (not needed by the dashboard): polling fallback transport,
 * binary frames, ACKs, emitting events back to the server.
 */

export type SocketIOStatus = 'connecting' | 'connected' | 'disconnected';

export interface SocketIOOptions {
  /** Base URL of the socket.io server, e.g. wss://host or ws://127.0.0.1:5000. */
  url?: string;
  /** Namespace to join (default "/feed" — what api/socket_push.py serves). */
  namespace?: string;
  /** Force-close if no engine.io ping within this window (default 30s). */
  pingTimeoutMs?: number;
  /** Max reconnect backoff (default 30s; sequence 1s,2s,4s,8s,16s,30s,…). */
  maxReconnectDelayMs?: number;
  /** Enable auto-reconnect (default true). */
  autoReconnect?: boolean;
}

type EventHandler = (payload: any) => void;
type StatusHandler = (status: SocketIOStatus) => void;

/** Same-origin default: wss on https pages, ws otherwise (works behind the
 *  nginx /socket.io/ proxy location; direct dev uses NEXT_PUBLIC_WS_URL). */
function defaultBaseURL(): string {
  const explicit = process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) return explicit.replace(/\/$/, '');
  if (typeof window !== 'undefined' && window.location && window.location.host) {
    return (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host;
  }
  return '';
}

export class SocketIOClient {
  private opts: Required<Omit<SocketIOOptions, 'url'>> & { url: string };
  private ws: WebSocket | null = null;
  private handlers = new Map<string, EventHandler[]>();
  private statusHandlers: StatusHandler[] = [];
  private status: SocketIOStatus = 'disconnected';
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private watchdogTimer: ReturnType<typeof setTimeout> | null = null;
  private lastPingAt = 0;
  private closedByUser = false;

  constructor(opts: SocketIOOptions = {}) {
    this.opts = {
      url: opts.url !== undefined ? opts.url.replace(/\/$/, '') : defaultBaseURL(),
      namespace: opts.namespace ?? '/feed',
      pingTimeoutMs: opts.pingTimeoutMs ?? 30_000,
      maxReconnectDelayMs: opts.maxReconnectDelayMs ?? 30_000,
      autoReconnect: opts.autoReconnect ?? true,
    };
  }

  /** Subscribe to a socket.io event (e.g. 'signal', 'health') or to
   *  status changes by passing 'status' as the event name. */
  on(event: string, handler: EventHandler | StatusHandler): this {
    if (event === 'status') {
      this.statusHandlers.push(handler as StatusHandler);
    } else {
      const list = this.handlers.get(event) || [];
      list.push(handler as EventHandler);
      this.handlers.set(event, list);
    }
    return this;
  }

  getStatus(): SocketIOStatus {
    return this.status;
  }

  connect(): this {
    if (typeof WebSocket === 'undefined') return this; // SSR guard
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return this;
    this.closedByUser = false;
    this.setStatus('connecting');
    const url = `${this.opts.url}/socket.io/?EIO=4&transport=websocket`;
    try {
      this.ws = new WebSocket(url);
    } catch {
      this.scheduleReconnect();
      return this;
    }
    this.ws.onopen = () => {
      // engine.io OPEN packet arrives as the first message; namespace
      // CONNECT is sent from handleEngineOpen().
    };
    this.ws.onmessage = (ev: MessageEvent) => this.handleFrame(typeof ev.data === 'string' ? ev.data : '');
    this.ws.onerror = () => {
      // close handler performs the reconnect bookkeeping
    };
    this.ws.onclose = () => {
      this.stopWatchdog();
      this.setStatus('disconnected');
      if (!this.closedByUser && this.opts.autoReconnect) this.scheduleReconnect();
    };
    return this;
  }

  /** Close for good (component unmount). No auto-reconnect afterwards. */
  close(): void {
    this.closedByUser = true;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.reconnectTimer = null;
    this.stopWatchdog();
    if (this.ws) {
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.onmessage = null;
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close();
      }
      this.ws = null;
    }
    this.setStatus('disconnected');
  }

  // ── internals ──────────────────────────────────────────────────────────

  private setStatus(s: SocketIOStatus): void {
    this.status = s;
    for (const h of this.statusHandlers) {
      try { h(s); } catch { /* handler errors must not kill the client */ }
    }
  }

  private emit(event: string, payload: any): void {
    for (const h of this.handlers.get(event) || []) {
      try { h(payload); } catch { /* ignore */ }
    }
  }

  private handleFrame(data: string): void {
    if (!data) return;
    const type = data.charAt(0);

    if (type === '0') {
      // engine.io OPEN — join the namespace. parse ping intervals for watchdog
      let pingInterval = 25_000;
      let pingTimeout = 20_000;
      try {
        const meta = JSON.parse(data.slice(1));
        if (typeof meta.pingInterval === 'number') pingInterval = meta.pingInterval;
        if (typeof meta.pingTimeout === 'number') pingTimeout = meta.pingTimeout;
      } catch { /* defaults hold */ }
      this.send(this.nsConnectPacket());
      this.startWatchdog(pingInterval + pingTimeout);
      this.reconnectAttempt = 0; // healthy (re)connect resets backoff
      this.setStatus('connected');
      return;
    }

    if (type === '2') {
      // engine.io PING from server — must answer with PONG ("3")
      this.lastPingAt = Date.now();
      this.send('3');
      return;
    }

    if (type === '3') {
      this.lastPingAt = Date.now();
      return;
    }

    if (type === '4') {
      const sub = data.charAt(1);
      if (sub === '0') {
        // socket.io CONNECT ack (optionally namespaced): "40/feed,{...}"
        this.setStatus('connected');
        return;
      }
      if (sub === '4') {
        // socket.io CONNECT_ERROR on our namespace — treat as disconnect and retry
        if (this.ws) this.ws.close();
        return;
      }
      if (sub === '2') {
        // socket.io EVENT: "42/feed,[\"event\",payload]"
        const { ns, json } = splitNamespace(data.slice(2));
        if (ns && ns !== this.opts.namespace) return;
        try {
          const arr = JSON.parse(json);
          if (Array.isArray(arr) && typeof arr[0] === 'string') {
            this.emit(arr[0], arr.length > 1 ? arr[1] : null);
          }
        } catch { /* malformed event — ignore */ }
        return;
      }
      // "4" alone (engine.io CLOSE) or "41" disconnect fall through
      return;
    }
    // '1' UPGRADE / '6' NOOP / anything else — ignore
  }

  private nsConnectPacket(): string {
    const ns = this.opts.namespace;
    return ns && ns !== '/' ? `40${ns},` : '40';
  }

  private send(frame: string): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try { this.ws.send(frame); } catch { /* ignore send races */ }
    }
  }

  private startWatchdog(windowMs: number): void {
    this.stopWatchdog();
    this.lastPingAt = Date.now();
    const interval = Math.max(5_000, Math.min(windowMs, this.opts.pingTimeoutMs));
    this.watchdogTimer = setInterval(() => {
      if (Date.now() - this.lastPingAt > interval) {
        // Server stopped pinging (stalled TCP, killed backend…) — force a
        // reconnect instead of waiting for the OS to notice.
        if (this.ws) this.ws.close();
      }
    }, Math.max(2_000, interval / 2));
  }

  private stopWatchdog(): void {
    if (this.watchdogTimer) clearInterval(this.watchdogTimer);
    this.watchdogTimer = null;
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const backoff = Math.min(
      this.opts.maxReconnectDelayMs,
      1_000 * Math.pow(2, this.reconnectAttempt),
    );
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, backoff);
  }
}

/** Split "42" remainder into { ns, json } — "42/feed,[…]" vs "42[…]". */
function splitNamespace(s: string): { ns: string | null; json: string } {
  if (s.startsWith('/')) {
    const comma = s.indexOf(',');
    if (comma > 0) return { ns: s.slice(0, comma), json: s.slice(comma + 1) };
    return { ns: s, json: '' };
  }
  return { ns: null, json: s };
}
