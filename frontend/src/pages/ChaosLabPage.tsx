import { useState, useEffect, useCallback } from 'react'
import { api, type DisputeSummary, type Status } from '../lib/api';
import StatusBadge from '../components/StatusBadge';

export default function ChaosLabPage() {
  const [disputes, setDisputes] = useState<DisputeSummary[]>([]);
  const [selectedCase, setSelectedCase] = useState<DisputeSummary | null>(null);
  const [contradictionType, setContradictionType] = useState<string | null>(null);
  const [phase, setPhase] = useState<'idle' | 'mutating' | 'verifying' | 'complete'>('idle');
  const [result, setResult] = useState<{ steps: string[], new_status: Status } | null>(null);

  const loadDisputes = useCallback(async () => {
    try {
      const data = await api.listDisputes();
      if (Array.isArray(data)) {
        setDisputes(data.filter(d => d?.status === 'CLEARED'));
      }
    } catch (err) {
      console.error('Failed to load disputes for Chaos Lab:', err);
    }
  }, []);

  useEffect(() => {
    loadDisputes();
    const interval = setInterval(loadDisputes, 2000);
    return () => clearInterval(interval);
  }, [loadDisputes]);

  const handleInject = async () => {
    if (!selectedCase || !contradictionType || phase !== 'idle') return;
    
    setPhase('mutating');
    
    // Simulate mutation phase
    setTimeout(() => {
      setPhase('verifying');
      
      // Call API and handle verification phase
      api.injectContradiction(selectedCase.order_id, contradictionType)
        .then(res => {
          setTimeout(() => {
            setResult({ steps: res.steps, new_status: res.new_status });
            setPhase('complete');
          }, 500);
        })
        .catch(err => {
          console.error(err);
          setPhase('idle');
        });
    }, 500);
  };

  const handleReset = async () => {
    await api.resetDemo();
    setPhase('idle');
    setResult(null);
    setSelectedCase(null);
    setContradictionType(null);
    await loadDisputes();
  };

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-serif font-semibold tracking-tight text-ink">CHAOS LAB</h1>
        <p className="text-sm text-muted mt-2 font-serif italic">Break the financial reality. Watch the institution respond.</p>
      </div>

      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3">SELECT A CLEAN CASE</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {disputes.map(d => {
            const isSelected = selectedCase?.dispute_id === d.dispute_id;
            return (
              <div
                key={d.dispute_id}
                onClick={() => {
                  setSelectedCase(d);
                  if (phase === 'complete') {
                    setPhase('idle');
                    setResult(null);
                  }
                }}
                className={`border rounded p-3 cursor-pointer transition-colors ${
                  isSelected
                    ? 'border-wire/50 bg-wire/5'
                    : 'border-line bg-panel hover:border-line2 hover:bg-raised'
                }`}
              >
                <div className="font-mono text-sm text-ink">{d.dispute_id}</div>
                <div className="font-mono text-[10px] text-dim mb-2">{d.order_id}</div>
                <StatusBadge status={d.status} size="sm" />
              </div>
            );
          })}
        </div>
      </div>

      {selectedCase && (
        <div>
          <div className="flex items-center gap-3">
            <div className="text-2xl font-mono font-semibold text-ink">{selectedCase.dispute_id}</div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase text-dim">CURRENT VERDICT</span>
              <StatusBadge status={selectedCase.status} size="lg" />
            </div>
          </div>
        </div>
      )}

      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3">SELECT CONTRADICTION TYPE</div>
        <div className="flex gap-2">
          {[
            { id: 'delivery_window', label: 'DELIVERY WINDOW' },
            { id: 'amount_mismatch', label: 'AMOUNT MISMATCH' },
            { id: 'payment_status', label: 'PAYMENT STATUS' },
          ].map(type => {
            const isSelected = contradictionType === type.id;
            return (
              <button
                key={type.id}
                onClick={() => setContradictionType(type.id)}
                className={`px-4 py-2.5 rounded border font-mono text-xs uppercase tracking-wide ${
                  isSelected
                    ? 'border-blocked/50 bg-blocked/8 text-blocked'
                    : 'border-line bg-panel text-muted hover:text-ink hover:border-line2'
                }`}
              >
                {type.label}
              </button>
            );
          })}
        </div>
      </div>

      <button
        onClick={handleInject}
        disabled={!selectedCase || !contradictionType || phase !== 'idle'}
        className="w-full py-3 rounded bg-blocked/15 border border-blocked/30 text-blocked font-mono text-sm uppercase tracking-wide hover:bg-blocked/25 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
      >
        BREAK REALITY
      </button>

      {phase !== 'idle' && (
        <div className="border border-line bg-panel rounded p-6">
          {phase === 'mutating' && (
            <div className="text-blocked font-mono text-sm animate-pulse">MUTATING SOURCE RECORD...</div>
          )}
          
          {phase === 'verifying' && (
            <div className="text-wire font-mono text-sm animate-pulse">RE-RUNNING VERIFICATION...</div>
          )}
          
          {phase === 'complete' && result && (
            <div className="space-y-4">
              <div className="space-y-1">
                {result.steps.map((step, idx) => (
                  <div key={idx} className="text-[11px] font-mono text-muted">{step}</div>
                ))}
              </div>
              
              <div className="text-blocked font-semibold">CONTRADICTION FOUND</div>
              
              <div className="text-xl font-mono font-semibold">
                <span className="text-cleared">CLEARED</span>
                <span className="text-muted mx-2">→</span>
                <span className="text-blocked">{result.new_status}</span>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="pt-8 border-t border-line">
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3">BREAK THE BOOKS (RECONCILIATION)</div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {[
            { id: 'amount_mismatch', label: 'MUTATE AMOUNT' },
            { id: 'date_mismatch', label: 'SHIFT DATE' },
            { id: 'delete', label: 'DELETE RECORD' },
            { id: 'duplicate', label: 'DUPLICATE RECORD' }
          ].map(mut => (
            <button
              key={mut.id}
              onClick={async () => {
                await api.injectReconciliationChaos(mut.id);
                alert('Ledger mutated! Run reconciliation to see the effect.');
              }}
              className={`border border-line2 rounded p-3 text-center transition-colors cursor-pointer bg-base hover:border-blocked hover:bg-blocked/5`}
            >
              <div className={`font-mono text-xs uppercase tracking-wide text-ink`}>
                {mut.label}
              </div>
            </button>
          ))}
        </div>
      </div>

      <div className="pt-8">
        <button
          onClick={handleReset}
          className="border border-line bg-panel text-muted font-mono text-xs uppercase tracking-wide px-4 py-2 rounded hover:text-ink hover:border-line2"
        >
          RESET DEMO
        </button>
      </div>
    </div>
  );
}
