'use client';
import { useState } from 'react';
import { useAccount, useConnect, useDisconnect, useBalance, useChainId, useSwitchChain } from 'wagmi';
import { supportedChains } from '../../config/wagmi';

export function WalletButton({ variant = 'default' }: { variant?: 'default' | 'nav' }) {
  const { address, isConnected, chainId } = useAccount();
  const { connectors, connect, status } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();
  const { data: balance } = useBalance({ address });
  const [open, setOpen] = useState(false);
  const [showChains, setShowChains] = useState(false);

  const currentChain = supportedChains.find(c => c.id === chainId) || { name: 'Unknown Chain' };
  const shortAddr = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : '';

  if (!isConnected) {
    return (
      <div className="relative">
        <button
          onClick={() => setOpen(v => !v)}
          className={variant === 'nav'
            ? 'px-3 py-1.5 rounded-lg bg-primary text-primary-foreground text-xs font-medium hover:opacity-90'
            : 'px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90'
          }
        >
          {status === 'pending' ? 'Connecting…' : '🔗 Connect Wallet'}
        </button>
        {open && (
          <div className="absolute right-0 mt-2 w-64 bg-card rounded-2xl p-2 z-50 border border-border shadow-lg">
            <div className="px-3 py-2 text-xs text-muted-foreground font-mono uppercase tracking-wider">Select Wallet</div>
            {connectors.map((connector) => (
              <button
                key={connector.uid}
                onClick={() => { connect({ connector }); setOpen(false); }}
                className="w-full flex items-center gap-3 px-3 py-3 rounded-xl hover:bg-muted transition-all text-left"
              >
                <div className="w-8 h-8 rounded-lg bg-muted flex items-center justify-center text-primary text-sm font-bold">
                  {connector.name[0]}
                </div>
                <div>
                  <div className="text-sm font-medium">{connector.name}</div>
                  <div className="text-[10px] text-muted-foreground">{connector.type}</div>
                </div>
              </button>
            ))}
            <div className="mt-2 px-3 py-2 text-[10px] text-muted-foreground border-t border-border">
              TRION never holds your funds. Your keys stay in your wallet.
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-border bg-card hover:border-primary/40 transition-all"
      >
        <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
        <span className="font-mono text-xs">{shortAddr}</span>
        {balance && (
          <span className="text-[10px] text-muted-foreground">
            {(Number(balance.value) / Math.pow(10, balance.decimals)).toFixed(3)} {balance.symbol}
          </span>
        )}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 bg-card rounded-2xl p-3 z-50 border border-border shadow-lg">
          <div className="p-3 rounded-xl bg-muted mb-2">
            <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider mb-1">Connected</div>
            <div className="font-mono text-xs text-primary break-all">{address}</div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[10px] text-muted-foreground">Balance</span>
              <span className="font-mono text-sm">
                {balance ? `${(Number(balance.value) / Math.pow(10, balance.decimals)).toFixed(4)} ${balance.symbol}` : '—'}
              </span>
            </div>
          </div>
          <button
            onClick={() => setShowChains(v => !v)}
            className="w-full flex items-center justify-between p-3 rounded-xl hover:bg-muted transition-all text-left"
          >
            <div>
              <div className="text-[10px] text-muted-foreground font-mono uppercase tracking-wider">Current Chain</div>
              <div className="text-sm font-medium">{currentChain.name}</div>
            </div>
          </button>
          {showChains && (
            <div className="mt-1 space-y-1 max-h-48 overflow-y-auto">
              {supportedChains.map((chain) => (
                <button
                  key={chain.id}
                  onClick={() => { switchChain({ chainId: chain.id }); setShowChains(false); }}
                  disabled={chain.id === chainId}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-all ${
                    chain.id === chainId ? 'bg-primary/10 text-primary' : 'hover:bg-muted'
                  }`}
                >
                  <span>{chain.name}</span>
                  {chain.id === chainId && <span className="text-[10px]">✓</span>}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={() => { disconnect(); setOpen(false); }}
            className="w-full mt-2 flex items-center gap-2 p-3 rounded-xl hover:bg-red-500/10 hover:text-red-500 transition-all text-left text-sm"
          >
            Disconnect
          </button>
        </div>
      )}
    </div>
  );
}
