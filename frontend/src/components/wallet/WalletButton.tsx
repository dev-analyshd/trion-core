'use client';

/**
 * TRION Wallet Button - institutional-grade wallet connector.
 *
 * Features:
 *   - Beautiful gradient design with chain-colored accents
 *   - Wrong-chain detection (red banner + switch CTA)
 *   - Click-outside + Escape to close
 *   - Copy-address button
 *   - Block explorer link
 *   - Chain switcher with active highlight
 *   - Balance display with compact formatting
 *   - Full aria attributes (aria-expanded, aria-haspopup, aria-label)
 *   - Responsive: truncates address/balance on small screens
 *   - variant="nav" honored for both connected and disconnected states
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import {
  useAccount, useConnect, useDisconnect, useBalance, useChainId, useSwitchChain,
} from 'wagmi';
import * as Icons from 'lucide-react';
import { supportedChains } from '../../config/wagmi';

export function WalletButton({ variant = 'default' }: { variant?: 'default' | 'nav' }) {
  const { address, isConnected, chainId, chain } = useAccount();
  const { connectors, connect, status, error: connectError } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();
  const { data: balance } = useBalance({ address });
  const [open, setOpen] = useState(false);
  const [showChains, setShowChains] = useState(false);
  const [copied, setCopied] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const currentChain = supportedChains.find(c => c.id === chainId);
  const isWrongChain = isConnected && !currentChain;
  const shortAddr = address ? `${address.slice(0, 6)}...${address.slice(-4)}` : '';

  // Click-outside handler
  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node) &&
          buttonRef.current && !buttonRef.current.contains(e.target as Node)) {
        setOpen(false);
        setShowChains(false);
      }
    };
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        setShowChains(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleEsc);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleEsc);
    };
  }, [open]);

  const copyAddress = useCallback(() => {
    if (!address) return;
    navigator.clipboard?.writeText(address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [address]);

  const explorerUrl = currentChain?.blockExplorers?.default?.url && address
    ? `${currentChain.blockExplorers.default.url}/address/${address}`
    : null;

  const formatBalance = (val: any) => {
    if (!val) return 'N/A';
    const num = parseFloat(val.formatted || '0');
    if (num === 0) return '0';
    if (num < 0.0001) return '<0.0001';
    return num.toFixed(4);
  };

  // Size classes based on variant
  const sizeClass = variant === 'nav'
    ? 'px-3 py-1.5 text-xs gap-1.5'
    : 'px-4 py-2 text-sm gap-2';

  // ── Disconnected state ────────────────────────────────────────────────────
  if (!isConnected) {
    return (
      <div className="relative flex-shrink-0">
        <button
          ref={buttonRef}
          onClick={() => setOpen(v => !v)}
          disabled={status === 'pending'}
          className={`relative flex items-center ${sizeClass} rounded-xl font-medium transition-all overflow-hidden group ${
            status === 'pending'
              ? 'bg-muted text-muted-foreground cursor-wait'
              : 'bg-gradient-to-r from-blue-600 to-purple-600 text-white hover:shadow-lg hover:shadow-blue-500/25 hover:scale-[1.02] active:scale-[0.98]'
          }`}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label="Connect wallet"
        >
          {status === 'pending' ? (
            <>
              <Icons.Loader2 className="w-4 h-4 animate-spin" />
              <span className="hidden sm:inline">Connecting...</span>
            </>
          ) : (
            <>
              <Icons.Wallet className="w-4 h-4 flex-shrink-0" />
              <span className="hidden sm:inline">Connect Wallet</span>
              <span className="sm:hidden">Connect</span>
            </>
          )}
        </button>

        {open && (
          <div
            ref={dropdownRef}
            className="absolute right-0 mt-2 w-72 bg-card border border-border rounded-2xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150"
            role="menu"
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-border bg-gradient-to-r from-blue-500/10 to-purple-500/10">
              <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Connect Wallet</div>
              <div className="text-sm font-semibold mt-0.5">Choose your wallet</div>
            </div>

            {/* Connector list */}
            <div className="p-2 space-y-1">
              {connectors.length === 0 && (
                <div className="px-3 py-4 text-center text-sm text-muted-foreground">
                  No wallet extensions detected.
                  <br />
                  Install MetaMask or Coinbase Wallet.
                </div>
              )}
              {connectors.map((connector) => (
                <button
                  key={connector.uid}
                  onClick={() => { connect({ connector }); setOpen(false); }}
                  className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-accent transition-colors text-left group"
                  role="menuitem"
                >
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center text-blue-600 dark:text-blue-400 font-bold text-sm flex-shrink-0">
                    {connector.name.charAt(0)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium truncate">{connector.name}</div>
                    <div className="text-xs text-muted-foreground truncate">{connector.type || 'wallet'}</div>
                  </div>
                  <Icons.ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                </button>
              ))}
            </div>

            {/* Footer */}
            <div className="px-4 py-3 border-t border-border bg-muted/30">
              <div className="flex items-start gap-2 text-xs text-muted-foreground">
                <Icons.Shield className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>TRION never holds your funds. Your keys stay in your wallet.</span>
              </div>
            </div>

            {connectError && (
              <div className="px-4 py-2 border-t border-red-500/30 bg-red-500/5 text-xs text-red-500">
                {connectError.message}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // ── Wrong chain state ─────────────────────────────────────────────────────
  if (isWrongChain) {
    return (
      <div className="relative flex-shrink-0">
        <button
          ref={buttonRef}
          onClick={() => switchChain({ chainId: supportedChains[0].id })}
          className={`flex items-center ${sizeClass} rounded-xl font-medium bg-red-500/10 text-red-600 border border-red-500/30 hover:bg-red-500/20 transition-colors`}
          aria-label="Switch to supported network"
        >
          <Icons.AlertTriangle className="w-4 h-4 flex-shrink-0" />
          <span className="hidden sm:inline">Wrong Network</span>
          <span className="sm:hidden">Switch</span>
        </button>
      </div>
    );
  }

  // ── Connected state ───────────────────────────────────────────────────────
  return (
    <div className="relative flex-shrink-0">
      <button
        ref={buttonRef}
        onClick={() => setOpen(v => !v)}
        className={`flex items-center ${sizeClass} rounded-xl font-medium border border-border bg-card hover:border-blue-500/40 hover:bg-accent transition-all max-w-[200px]`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Wallet menu - connected as ${shortAddr}`}
      >
        {/* Status dot */}
        <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse flex-shrink-0" />

        {/* Address */}
        <span className="font-mono text-xs truncate">{shortAddr}</span>

        {/* Balance */}
        {balance && (
          <span className="text-xs text-muted-foreground hidden md:inline truncate max-w-[80px]">
            {formatBalance(balance)} {balance.symbol}
          </span>
        )}

        <Icons.ChevronDown className={`w-3.5 h-3.5 text-muted-foreground transition-transform flex-shrink-0 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div
          ref={dropdownRef}
          className="absolute right-0 mt-2 w-80 bg-card border border-border rounded-2xl shadow-2xl z-50 overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150"
          role="menu"
        >
          {/* Connected wallet header */}
          <div className="p-4 border-b border-border bg-gradient-to-r from-green-500/10 to-blue-500/10">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-mono uppercase tracking-wider text-muted-foreground">Connected</div>
              <button
                onClick={copyAddress}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                aria-label="Copy address"
              >
                {copied ? <Icons.Check className="w-3.5 h-3.5 text-green-500" /> : <Icons.Copy className="w-3.5 h-3.5" />}
                {copied ? 'Copied!' : 'Copy'}
              </button>
            </div>
            <div className="font-mono text-sm text-blue-600 dark:text-blue-400 break-all leading-relaxed">
              {address}
            </div>
            {/* Balance + Explorer row */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-border/50">
              <div>
                <div className="text-xs text-muted-foreground">Balance</div>
                <div className="font-mono text-sm font-semibold">
                  {balance ? `${formatBalance(balance)} ${balance.symbol}` : 'N/A'}
                </div>
              </div>
              {explorerUrl && (
                <a
                  href={explorerUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  aria-label="View on block explorer"
                >
                  <Icons.ExternalLink className="w-3.5 h-3.5" />
                  Explorer
                </a>
              )}
            </div>
          </div>

          {/* Chain selector */}
          <div className="p-2">
            <button
              onClick={() => setShowChains(v => !v)}
              className="w-full flex items-center justify-between p-3 rounded-xl hover:bg-accent transition-colors text-left"
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500/20 to-purple-500/20 flex items-center justify-center flex-shrink-0">
                  <Icons.Network className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">Current Chain</div>
                  <div className="text-sm font-medium truncate">{currentChain?.name || 'Unknown'}</div>
                </div>
              </div>
              <Icons.ChevronDown className={`w-4 h-4 text-muted-foreground transition-transform flex-shrink-0 ${showChains ? 'rotate-180' : ''}`} />
            </button>

            {showChains && (
              <div className="mt-1 ml-2 space-y-0.5 max-h-52 overflow-y-auto">
                {supportedChains.map((c) => {
                  const active = c.id === chainId;
                  return (
                    <button
                      key={c.id}
                      onClick={() => { switchChain({ chainId: c.id }); setShowChains(false); }}
                      disabled={active}
                      className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                        active
                          ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium'
                          : 'hover:bg-accent text-foreground'
                      }`}
                    >
                      <span className="truncate">{c.name}</span>
                      {active && <Icons.Check className="w-4 h-4 flex-shrink-0" />}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="p-2 border-t border-border space-y-1">
            <button
              onClick={() => { disconnect(); setOpen(false); }}
              className="w-full flex items-center gap-3 p-3 rounded-xl hover:bg-red-500/10 hover:text-red-500 transition-colors text-left text-sm"
              role="menuitem"
            >
              <Icons.LogOut className="w-4 h-4 flex-shrink-0" />
              Disconnect
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
