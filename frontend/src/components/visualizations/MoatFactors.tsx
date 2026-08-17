/**
 * MoatFactors - Visualizes the 6 multiplicative economic moat factors
 * Aligned with Whitepaper L0.5: M_moat = D * Q * R * X * F * N
 */
'use client';
import { useAPI } from '../../lib/hooks';
import * as Icons from 'lucide-react';

const FACTORS = [
  { key: 'D_data', short: 'D', name: 'Data Moat', desc: 'Akashic behavioral depth', icon: Icons.Database, color: '#3b82f6' },
  { key: 'Q_quality', short: 'Q', name: 'Quality Moat', desc: 'K-plane calibration accuracy', icon: Icons.Target, color: '#8b5cf6' },
  { key: 'R_reflexivity', short: 'R', name: 'Reflexivity', desc: 'M_adj agreement across signals', icon: Icons.RefreshCw, color: '#ec4899' },
  { key: 'X_crosschain', short: 'X', name: 'Cross-Chain', desc: 'Multi-VM consistency', icon: Icons.GitBranch, color: '#f97316' },
  { key: 'F_falsifiability', short: 'F', name: 'Falsifiability', desc: 'Registered predictions verified', icon: Icons.FlaskConical, color: '#10b981' },
  { key: 'N_network', short: 'N', name: 'Network', desc: 'Validator count & independence', icon: Icons.Network, color: '#06b6d4' },
];

export function MoatFactors() {
  const { data: moat } = useAPI('/api/v1/moat', 10000);
  
  const components = moat?.components || moat?.moat_components || {};
  const M_moat = moat?.M_moat || moat?.moat_factor || 0;
  
  // Get factor values with fallbacks
  const getVal = (key: string) => {
    const direct = components[key];
    if (typeof direct === 'number') return direct;
    // Try alternate key formats
    for (const [k, v] of Object.entries(components)) {
      if (k.toLowerCase().includes(key.split('_')[0].toLowerCase()) && typeof v === 'number') {
        return v;
      }
    }
    return 0.5; // Bootstrap fallback
  };
  
  // Compute multiplicative product
  const product = FACTORS.reduce((acc, f) => acc * Math.max(0.01, getVal(f.key)), 1);
  
  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold">Economic Moat Factors</h3>
          <p className="text-xs text-muted-foreground">M_moat = D · Q · R · X · F · N — multiplicative defensibility</p>
        </div>
        <Icons.Shield className="w-5 h-5 text-muted-foreground" />
      </div>
      
      {/* Factors grid */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        {FACTORS.map(f => {
          const val = getVal(f.key);
          const pct = Math.min(100, val * 100);
          const Icon = f.icon;
          return (
            <div key={f.key} className="p-4 rounded-xl border border-border bg-muted/20">
              <div className="flex items-center gap-3 mb-3">
                <div 
                  className="w-10 h-10 rounded-lg flex items-center justify-center"
                  style={{ backgroundColor: `${f.color}20` }}
                >
                  <Icon className="w-5 h-5" style={{ color: f.color }} />
                </div>
                <div>
                  <div className="font-mono text-xs text-muted-foreground">{f.short}</div>
                  <div className="font-semibold text-sm">{f.name}</div>
                </div>
              </div>
              <div className="text-xs text-muted-foreground mb-2">{f.desc}</div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-lg font-bold" style={{ color: f.color }}>
                  {val.toFixed(3)}
                </span>
              </div>
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-500"
                  style={{ width: `${pct}%`, backgroundColor: f.color }}
                />
              </div>
            </div>
          );
        })}
      </div>
      
      {/* Multiplicative result */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="p-4 rounded-xl bg-gradient-to-br from-purple-500/10 to-blue-500/10 border border-purple-500/30">
          <div className="text-xs text-muted-foreground mb-1">Moat Product (D·Q·R·X·F·N)</div>
          <div className="font-mono text-2xl font-bold text-purple-400">{product.toFixed(6)}</div>
        </div>
        <div className="p-4 rounded-xl bg-gradient-to-br from-amber-500/10 to-green-500/10 border border-amber-500/30">
          <div className="text-xs text-muted-foreground mb-1">M_moat = ln(product)</div>
          <div className="font-mono text-2xl font-bold text-amber-400">{M_moat.toFixed(6)}</div>
        </div>
      </div>
    </div>
  );
}
