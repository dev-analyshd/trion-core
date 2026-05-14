/**
 * TRION Protocol — TypeScript SDK
 * Full client for all whitepaper-defined signal types.
 *
 * Usage:
 *   import { TRIONClient } from './trion';
 *   const client = new TRIONClient({ baseUrl: 'https://trion-protocol.replit.app' });
 *   const signal = await client.getSignal('uniswap');
 */

export interface TRIONConfig {
  baseUrl:        string;
  apiKey?:        string;
  timeoutMs?:     number;
  retryCount?:    number;
}

export interface PlaneBreakdown {
  phi_adj:  number;
  m_adj:    number;
  sigma:    number;
  k_plane:  number;
  anima:    number;
}

export interface BiologicalTime {
  circadian_phase:  number;
  ultradian_phase:  number;
  lunar_phase:      number;
  seasonal_phase:   number;
}

export interface TRIONSignal {
  signal_id:         string;
  signal_type:       string;
  entity_id:         string;
  signal_value:      number | null;
  ci_95:             [number, number];
  coherence:         number;
  threshold:         number;
  margin:            number;
  mf_score:          number;
  silence:           boolean;
  silence_gap:       number;
  coherence_trend:   string;
  eta_blocks:        number;
  plane_breakdown:   PlaneBreakdown;
  limiting_plane:    string | null;
  bootstrap_phase:   boolean;
  biological_time:   BiologicalTime;
  timestamp:         number;
  ttl_seconds:       number;
}

export interface NLSignal {
  nl_score:        number;
  ld_score:        number;
  lo_score:        number;
  lc_score:        number;
  ls_score:        number;
  alert:           boolean;
  limiting_factor: string;
  recommendation:  'DO_NOT_ROUTE' | 'CAUTION' | 'CLEAR';
  coherence:       number;
  timestamp:       number;
}

export interface BTCPResult {
  btcp_score:    number;
  raw_score:     number;
  mf_discount:   number;
  is_safe:       boolean;
  nl_healthy:    boolean;
  components:    Record<string, number>;
}

export interface SystemStatus {
  status:          string;
  akashic_depth:   number;
  faiss_vectors:   number;
  validator_count: number;
  bootstrap_phase: boolean;
  planes: {
    phi_active:    boolean;
    m_active:      boolean;
    sigma_active:  boolean;
    k_active:      boolean;
    anima_active:  boolean;
  };
}

export interface BootstrapStatus {
  bootstrap_active:      boolean;
  sigma_bootstrap_value: number;
  k_bootstrap_value:     number;
  anima_bootstrap_value: number;
  anima_d_minimum:       number;
  current_depth:         number;
  full_activation_eta:   string;
  honest_disclosure: {
    sigma: string;
    k:     string;
    anima: string;
  };
}

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'APIError';
  }
}

export class TRIONClient {
  private config: Required<TRIONConfig>;

  constructor(config: TRIONConfig) {
    this.config = {
      baseUrl:    config.baseUrl.replace(/\/$/, ''),
      apiKey:     config.apiKey     ?? '',
      timeoutMs:  config.timeoutMs  ?? 10000,
      retryCount: config.retryCount ?? 3,
    };
  }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const url     = `${this.config.baseUrl}${path}`;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept':       'application/json',
    };
    if (this.config.apiKey) {
      headers['X-TRION-API-Key'] = this.config.apiKey;
    }

    let lastError: Error | null = null;
    for (let attempt = 0; attempt < this.config.retryCount; attempt++) {
      try {
        const controller = new AbortController();
        const timer      = setTimeout(() => controller.abort(), this.config.timeoutMs);
        const response   = await fetch(url, {
          ...options,
          headers: { ...headers, ...(options?.headers ?? {}) },
          signal:  controller.signal,
        });
        clearTimeout(timer);

        if (!response.ok) {
          throw new APIError(response.status, `HTTP ${response.status}: ${response.statusText}`);
        }
        return response.json() as Promise<T>;
      } catch (err) {
        lastError = err as Error;
        if (err instanceof APIError && err.status < 500) throw err;
        if (attempt < this.config.retryCount - 1) {
          await new Promise(r => setTimeout(r, 200 * (attempt + 1)));
        }
      }
    }
    throw lastError!;
  }

  // ─── Core Signal ─────────────────────────────────────────────

  async getSignal(entityId: string): Promise<TRIONSignal> {
    return this.request<TRIONSignal>(`/api/v1/signal/${encodeURIComponent(entityId)}`);
  }

  async getSignalHistory(entityId: string, limit = 100): Promise<TRIONSignal[]> {
    return this.request<TRIONSignal[]>(
      `/api/v1/signal/${encodeURIComponent(entityId)}/history?limit=${limit}`
    );
  }

  async batchSignals(entityIds: string[]): Promise<Record<string, TRIONSignal>> {
    return this.request<Record<string, TRIONSignal>>('/api/v1/signal/batch', {
      method: 'POST',
      body:   JSON.stringify({ entity_ids: entityIds }),
    });
  }

  // ─── Planes ───────────────────────────────────────────────────

  async getAllPlanes(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/all`);
  }

  async getPhysicalPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/physical`);
  }

  async getMentalPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/mental`);
  }

  async getSpiritualPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/spiritual`);
  }

  async getConsciousPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/conscious`);
  }

  async getAnimaPlane(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/planes/${encodeURIComponent(entityId)}/anima`);
  }

  // ─── Security ─────────────────────────────────────────────────

  async checkSecurity(txData: string): Promise<Record<string, unknown>> {
    return this.request('/api/v1/security/check', {
      method: 'POST',
      body:   JSON.stringify({ tx_data: txData }),
    });
  }

  async getMFScore(entityId: string): Promise<Record<string, unknown>> {
    return this.request(`/api/v1/security/${encodeURIComponent(entityId)}/mf`);
  }

  async getCRISPRLibrary(): Promise<Record<string, unknown>> {
    return this.request('/api/v1/security/crispr/library');
  }

  // ─── Liquidity ────────────────────────────────────────────────

  async getNLScore(assetAddress: string): Promise<NLSignal> {
    return this.request<NLSignal>(`/api/v1/liquidity/${encodeURIComponent(assetAddress)}`);
  }

  // ─── BTCP ─────────────────────────────────────────────────────

  async getBTCPScore(routeData: Record<string, unknown>): Promise<BTCPResult> {
    return this.request<BTCPResult>('/api/v1/btcp/score', {
      method: 'POST',
      body:   JSON.stringify(routeData),
    });
  }

  // ─── System ───────────────────────────────────────────────────

  async getSystemStatus(): Promise<SystemStatus> {
    return this.request<SystemStatus>('/api/v1/system/status');
  }

  async getBootstrapStatus(): Promise<BootstrapStatus> {
    return this.request<BootstrapStatus>('/api/v1/system/bootstrap');
  }

  async getFalsifiability(): Promise<Record<string, unknown>> {
    return this.request('/api/v1/system/falsifiability');
  }

  async health(): Promise<{ status: string; timestamp: number }> {
    return this.request('/health');
  }

  // ─── Utilities ────────────────────────────────────────────────

  /**
   * Checks if the oracle recommends proceeding with a transaction.
   * Returns false if SILENCE, NL < 0.30, or MF > 0.70.
   */
  async isSafeToExecute(entityId: string): Promise<{
    safe:     boolean;
    reason:   string;
    signal:   TRIONSignal;
  }> {
    const signal = await this.getSignal(entityId);

    if (signal.silence) {
      return {
        safe: false,
        reason: `SILENCE: C(t)=${signal.coherence.toFixed(4)} < Θ(t)=${signal.threshold.toFixed(4)}, limiting plane=${signal.limiting_plane}`,
        signal,
      };
    }

    if (signal.mf_score >= 0.70) {
      return {
        safe:   false,
        reason: `MANIPULATION_ALERT: MF_score=${signal.mf_score.toFixed(4)}`,
        signal,
      };
    }

    return { safe: true, reason: 'PASS', signal };
  }
}

// ─── Convenience factory ─────────────────────────────────────────

export function createClient(baseUrl: string, apiKey?: string): TRIONClient {
  return new TRIONClient({ baseUrl, apiKey });
}

export default TRIONClient;
