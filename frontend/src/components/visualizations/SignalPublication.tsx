/**
 * SignalPublication - Shows on-chain signal publication status
 * Aligned with whitepaper: publishBehavioralSignal -> TRIONOracleV3 -> Arbitrum Sepolia
 */
'use client';
import { useAPI } from '../../lib/hooks';
import { fmt, dtfmt } from '../../lib/api';
import * as Icons from 'lucide-react';

const ORACLE_ADDRESS = '0xb819c63c02Ed5aB49017C0f3f2568A14624658b3';
const CHAIN_NAME = 'Arbitrum Sepolia';
const CHAIN_ID = '421614';

export function SignalPublication() {
  const { data: health } = useAPI('/api/v1/health', 5000);
  
  const signalsOnChain = health?.total_signals_onchain ?? 0;
  const lastSignal = health?.last_signal_timestamp;
  const chainAvailable = health?.chain_available ?? health?.relay_available ?? false;
  
  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold">On-Chain Publication</h3>
          <p className="text-xs text-muted-foreground">TRIONOracleV3 · Arbitrum Sepolia (421614)</p>
        </div>
        <Icons.Link className="w-5 h-5 text-muted-foreground" />
      </div>
      
      {/* Contract info */}
      <div className="p-4 rounded-xl bg-muted/30 border border-border mb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs text-muted-foreground">Oracle Contract</span>
          <span className="text-xs px-2 py-0.5 rounded bg-blue-500/20 text-blue-400 font-mono">Chain ID {CHAIN_ID}</span>
        </div>
        <div className="font-mono text-sm break-all">{ORACLE_ADDRESS}</div>
        <div className="text-xs text-muted-foreground mt-1">{CHAIN_NAME}</div>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="p-4 rounded-xl bg-green-500/10 border border-green-500/30 text-center">
          <div className="text-xs text-muted-foreground mb-1">Signals On-Chain</div>
          <div className="font-mono text-3xl font-bold text-green-400">{fmt(signalsOnChain, 0)}</div>
        </div>
        <div className="p-4 rounded-xl bg-muted/30 border border-border text-center">
          <div className="text-xs text-muted-foreground mb-1">Last Published</div>
          <div className="font-mono text-sm font-bold">
            {lastSignal ? dtfmt(lastSignal) : '—'}
          </div>
        </div>
      </div>
      
      {/* Relay status */}
      <div className={`p-4 rounded-xl flex items-center gap-3 ${chainAvailable ? 'bg-green-500/10 border border-green-500/30' : 'bg-amber-500/10 border border-amber-500/30'}`}>
        <div className={`w-3 h-3 rounded-full ${chainAvailable ? 'bg-green-500' : 'bg-amber-500'}`} />
        <div className="flex-1">
          <div className="font-semibold text-sm">
            {chainAvailable ? 'Relay Online' : 'Relay in Bootstrap Mode'}
          </div>
          <div className="text-xs text-muted-foreground">
            {chainAvailable 
              ? 'Publishing signals to on-chain oracle' 
              : 'Configure PRIVATE_KEY + ARB_SEPOLIA_RPC in Railway env vars to enable'}
          </div>
        </div>
        <Icons.ExternalLink className="w-4 h-4 text-muted-foreground" />
      </div>
      
      {/* Signal format */}
      <div className="mt-4 p-4 rounded-xl bg-muted/20 border border-border">
        <div className="text-xs font-semibold text-muted-foreground mb-2">256-bit Thermodynamic Packing</div>
        <div className="font-mono text-xs space-y-1 text-muted-foreground">
          <div>bits [0-7]: status</div>
          <div>bits [8-39]: coherence × 1e6</div>
          <div>bits [40-71]: threshold × 1e6</div>
          <div>bits [72-135]: blockNumber</div>
          <div>bits [136-199]: timestamp</div>
          <div>bits [200+]: plane_code</div>
        </div>
      </div>
    </div>
  );
}
