/**
 * MasterEquation - Live visualization of TRION's Master Equation
 * Aligned with Whitepaper L5.3: T(t) = [C >= Theta] * C(t) * e^(M_moat)
 */
'use client';
import { useAPI } from '../../lib/hooks';
import { pct } from '../../lib/api';
import * as Icons from 'lucide-react';

export function MasterEquation() {
  const { data: health } = useAPI('/api/v1/health', 5000);
  const { data: moat } = useAPI('/api/v1/moat', 10000);
  
  const C = health?.coherence_score ?? health?.dynamic_threshold ?? 0.5;
  const theta = health?.dynamic_threshold ?? 0.661;
  const coherent = C >= theta;
  const M_moat = moat?.M_moat ?? moat?.moat_factor ?? 0;
  const moatExp = Math.exp(M_moat);
  const T = coherent ? C * moatExp : 0;
  
  return (
    <div className="bg-card border border-border rounded-xl p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-lg font-bold">Master Equation</h3>
          <p className="text-xs text-muted-foreground">Truth amplitude with economic moat amplification</p>
        </div>
        <Icons.Calculator className="w-5 h-5 text-muted-foreground" />
      </div>
      
      {/* Equation display */}
      <div className="bg-gradient-to-br from-muted/50 to-transparent border border-border rounded-xl p-6 mb-6">
        <div className="text-center font-mono text-2xl lg:text-3xl font-bold mb-4">
          <span className="text-blue-400">T(t)</span>
          <span className="mx-2">=</span>
          <span className={`mx-1 px-2 py-0.5 rounded ${coherent ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
            [{coherent ? 'C ≥ Θ' : 'C < Θ'}]
          </span>
          <span className="mx-2">·</span>
          <span className="text-amber-400">C(t)</span>
          <span className="mx-2">·</span>
          <span className="text-purple-400">e</span>
          <sup className="text-purple-400 text-sm">M_moat</sup>
        </div>
        
        <div className="grid grid-cols-4 gap-4 text-center text-sm">
          <div>
            <div className="text-xs text-muted-foreground mb-1">Coherence C(t)</div>
            <div className="font-mono text-xl font-bold text-amber-400">{C.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Threshold Θ</div>
            <div className="font-mono text-xl font-bold">{theta.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Moat M_moat</div>
            <div className="font-mono text-xl font-bold text-purple-400">{M_moat.toFixed(4)}</div>
          </div>
          <div>
            <div className="text-xs text-muted-foreground mb-1">Truth T(t)</div>
            <div className={`font-mono text-xl font-bold ${coherent ? 'text-green-400' : 'text-red-400'}`}>
              {T.toFixed(4)}
            </div>
          </div>
        </div>
      </div>
      
      {/* Computation breakdown */}
      <div className="space-y-2 text-sm">
        <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
          <span className="text-muted-foreground">Step 1: Coherence gate</span>
          <span className={`font-mono font-bold ${coherent ? 'text-green-400' : 'text-red-400'}`}>
            {C.toFixed(4)} {coherent ? '≥' : '<'} {theta.toFixed(4)} → {coherent ? '1' : '0'}
          </span>
        </div>
        <div className="flex items-center justify-between p-3 bg-muted/30 rounded-lg">
          <span className="text-muted-foreground">Step 2: Moat amplifier e^({M_moat.toFixed(4)})</span>
          <span className="font-mono font-bold text-purple-400">× {moatExp.toFixed(4)}</span>
        </div>
        <div className="flex items-center justify-between p-3 bg-blue-500/10 border border-blue-500/30 rounded-lg">
          <span className="font-medium">Step 3: Truth amplitude</span>
          <span className={`font-mono text-xl font-bold ${coherent ? 'text-green-400' : 'text-red-400'}`}>
            T(t) = {T.toFixed(6)}
          </span>
        </div>
      </div>
      
      {/* Signal status */}
      <div className={`mt-4 p-4 rounded-xl text-center ${coherent ? 'bg-green-500/10 border border-green-500/30' : 'bg-amber-500/10 border border-amber-500/30'}`}>
        <div className={`text-sm font-bold ${coherent ? 'text-green-400' : 'text-amber-400'}`}>
          {coherent ? '✓ SIGNAL EMITTED' : '○ SILENCE — Insufficient coherence'}
        </div>
        {!coherent && (
          <div className="text-xs text-muted-foreground mt-1">
            Signal selection gate active — no false truths published
          </div>
        )}
      </div>
    </div>
  );
}
