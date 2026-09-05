import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'

export default function ReconcilePage() {
  const [batch, setBatch] = useState<any>(null)
  const [records, setRecords] = useState<any[]>([])
  const [exceptions, setExceptions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  
  const load = useCallback(async () => {
    try {
      const b = await api.getLatestBatch()
      if (b) {
        setBatch(b)
        const recs: any = await api.getReconciliationRecords(b.batch_id)
        setRecords(recs.records || recs)
        const excs = await api.getReconciliationExceptions(b.batch_id)
        setExceptions(excs)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [])
  
  useEffect(() => {
    load()
  }, [load])
  
  const handleRun = async () => {
    setRunning(true)
    try {
      await api.runReconciliation()
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setRunning(false)
    }
  }

  if (loading) {
    return <div className="text-muted text-sm font-mono text-center mt-20">LOADING BATCH...</div>
  }

  return (
    <div className="space-y-12">
      {/* HERO */}
      <div>
        <h1 className="text-4xl font-serif font-semibold tracking-tight text-ink uppercase">RECONCILE THE BOOKS</h1>
        <p className="text-sm text-dim mt-2 font-mono uppercase tracking-widest">
          Cross-system financial reconciliation, with nowhere for exceptions to hide.
        </p>
      </div>

      <div className="border border-line bg-panel p-6 rounded flex items-center justify-between">
        {batch ? (
          <div className="flex gap-12">
            <div>
              <div className="text-[10px] font-mono text-dim uppercase">BATCH</div>
              <div className="text-lg font-mono text-ink">{batch.batch_id}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-dim uppercase">RECORDS</div>
              <div className="text-lg font-mono text-ink">{batch.total_records}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-dim uppercase">RESOLVED</div>
              <div className="text-lg font-mono text-cleared">{batch.resolved_count}</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-dim uppercase">RESOLUTION RATE</div>
              <div className="text-lg font-mono text-ink">{batch.resolution_rate.toFixed(1)}%</div>
            </div>
            <div>
              <div className="text-[10px] font-mono text-dim uppercase">EXCEPTIONS</div>
              <div className="text-lg font-mono text-blocked">{batch.unresolved_count}</div>
            </div>
          </div>
        ) : (
          <div className="text-sm font-mono text-muted">NO BATCHES RUN</div>
        )}
        
        <button
          onClick={handleRun}
          disabled={running}
          className="px-6 py-3 rounded bg-wire/15 border border-wire/30 text-wire font-mono text-sm uppercase tracking-wide hover:bg-wire/25 transition-colors disabled:opacity-50"
        >
          {running ? "PROCESSING..." : "RUN RECONCILIATION"}
        </button>
      </div>

      {/* EXCEPTION QUEUE */}
      {exceptions.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-blocked border-b border-line pb-2">WHAT THE ENGINE COULD NOT RESOLVE</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {exceptions.map(exc => (
              <div key={exc.exception_id} className="border border-line bg-panel rounded p-4">
                <div className="flex justify-between items-start mb-4">
                  <div className="font-mono text-blocked text-xs font-semibold uppercase">{exc.exception_type.replace(/_/g, ' ')}</div>
                  <div className="text-[10px] font-mono text-dim">{exc.source_record_id}</div>
                </div>
                <div className="text-sm font-serif text-ink mb-4">{exc.explanation}</div>
                
                {exc.exception_type === 'AMOUNT_MISMATCH' && (
                  <div className="bg-raised p-3 rounded border border-line2 font-mono text-xs text-muted">
                    <div className="text-[10px] uppercase text-dim mb-1">Human Action Required</div>
                    Investigate amount discrepancy. Review source payment vs ledger entry.
                  </div>
                )}
                {exc.exception_type === 'AMBIGUOUS' && (
                  <div className="bg-raised p-3 rounded border border-line2 font-mono text-xs text-muted">
                    <div className="text-[10px] uppercase text-dim mb-1">Human Action Required</div>
                    Multiple ledger entries match amount but missing Order ID. Please select correct reference.
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* RECONCILIATION TABLE */}
      {records.length > 0 && (
        <div className="space-y-4">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-dim border-b border-line pb-2">ALL RECORDS</h2>
          <div className="border border-line rounded overflow-hidden">
            <table className="w-full text-left text-sm font-mono border-collapse">
              <thead>
                <tr className="bg-panel border-b border-line text-[10px] text-dim uppercase">
                  <th className="px-4 py-3 font-medium">Source Record</th>
                  <th className="px-4 py-3 font-medium">Target Record</th>
                  <th className="px-4 py-3 font-medium text-right">Amount Diff</th>
                  <th className="px-4 py-3 font-medium">Match Type</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {records.map((r, i) => {
                  const isException = r.match_status !== 'MATCHED' && r.match_status !== 'MATCHED_AFTER_NORMALIZATION';
                  return (
                    <tr key={r.reconciliation_id} className={`border-b border-line last:border-none ${i % 2 === 0 ? 'bg-base' : 'bg-panel/30'} hover:bg-raised transition-colors`}>
                      <td className="px-4 py-3 text-ink">{r.source_system} <span className="text-dim text-xs ml-1">{r.source_record_id}</span></td>
                      <td className="px-4 py-3 text-ink">
                        {r.target_record_id ? (
                          <>{r.target_system} <span className="text-dim text-xs ml-1">{r.target_record_id}</span></>
                        ) : (
                          <span className="text-dim">—</span>
                        )}
                      </td>
                      <td className={`px-4 py-3 text-right ${r.amount_difference ? 'text-blocked' : 'text-muted'}`}>
                        {r.amount_difference ? `₹${Math.abs(r.amount_difference).toFixed(2)}` : '—'}
                      </td>
                      <td className="px-4 py-3 text-muted text-xs">{r.match_type.replace(/_/g, ' ')}</td>
                      <td className="px-4 py-3">
                        <span className={`text-[10px] px-2 py-0.5 rounded border uppercase ${
                          isException ? 'border-blocked/30 text-blocked bg-blocked/5' : 'border-cleared/30 text-cleared bg-cleared/5'
                        }`}>
                          {r.match_status.replace(/_/g, ' ')}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
