code = """import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Evaluation } from '../lib/api'

export default function EvaluationPage() {
  const [ev, setEv] = useState<any | null>(null)

  const load = () => api.getEvaluation().then(setEv).catch(console.error)
  
  useEffect(() => {
    load()
    const int = setInterval(load, 2000)
    return () => clearInterval(int)
  }, [])

  if (!ev) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted text-sm font-mono">Computing evaluation...</div>
      </div>
    )
  }

  const { dataset, confusion_matrix, metrics, performance, status_counts, missed_cases, reconciliation } = ev

  const pct = (n: number) => typeof n === 'number' ? `${(n * 100).toFixed(1)}%` : '—'

  const humanContextCount = status_counts['HUMAN_CONTEXT'] || 0
  const humanContextExpected = dataset.total - dataset.contradictory - dataset.clean + (dataset.total - dataset.contradictory - (confusion_matrix.true_negative + confusion_matrix.false_positive))
  const humanContextDenom = humanContextCount > 0 ? humanContextCount : humanContextExpected || humanContextCount

  return (
    <div className="space-y-12">
      <div>
        <h1 className="text-4xl font-serif font-semibold tracking-tight text-ink uppercase">PROOF</h1>
        <p className="text-sm text-dim mt-2 font-mono uppercase tracking-widest">Continuous Evaluation against Hidden Ground Truth.</p>
      </div>

      {reconciliation && (
        <div className="space-y-4">
          <h2 className="text-[11px] font-mono uppercase tracking-widest text-dim border-b border-line pb-2 mb-4">RECONCILIATION PROOF</h2>
          
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">BATCH PROCESSED</div>
              <div className="text-3xl font-mono text-ink">{reconciliation.total_records}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">AUTOMATICALLY RESOLVED</div>
              <div className="text-3xl font-mono text-cleared">{reconciliation.resolved_count}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">AUTOMATIC RESOLUTION RATE</div>
              <div className="text-3xl font-mono text-ink">{reconciliation.resolution_rate.toFixed(1)}%</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">EXCEPTIONS</div>
              <div className="text-3xl font-mono text-blocked">{reconciliation.unresolved_count}</div>
            </div>
          </div>
          
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
             <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">EXACT MATCH RATE</div>
              <div className="text-xl font-mono text-ink">{reconciliation.exact_match_rate.toFixed(1)}%</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">PRECISION</div>
              <div className="text-xl font-mono text-ink">{pct(reconciliation.precision)}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">RECALL</div>
              <div className="text-xl font-mono text-ink">{pct(reconciliation.recall)}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">F1 SCORE</div>
              <div className="text-xl font-mono text-ink">{pct(reconciliation.f1)}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">FALSE NEGATIVES</div>
              <div className="text-xl font-mono text-ink">{reconciliation.false_negatives}</div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">THROUGHPUT</div>
              <div className="text-xl font-mono text-ink">{reconciliation.throughput} <span className="text-[10px]">rec/s</span></div>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4 pt-8 border-t border-line">
        <h2 className="text-[11px] font-mono uppercase tracking-widest text-dim border-b border-line pb-2 mb-4">TRUTH VERIFICATION PROOF</h2>
        <div className="py-8 text-center flex flex-col items-center">
          <div className="text-6xl font-mono font-bold tracking-tight text-ink">
            {confusion_matrix.true_positive} / {dataset.contradictory}
          </div>
          <div className="text-xs font-mono uppercase tracking-widest text-dim mt-2">
            CONTRADICTIONS DETECTED
          </div>
        </div>

        <div className="flex items-start justify-center gap-12 py-6">
          <div className="flex flex-col items-center">
            <div className={`text-3xl font-mono font-semibold ${metrics.false_positive_count === 0 ? 'text-cleared' : 'text-blocked'}`}>
              {metrics.false_positive_count}
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">FALSE POSITIVES</div>
          </div>

          <div className="flex flex-col items-center">
            <div className="text-3xl font-mono font-semibold text-ink">
              {pct(metrics.precision)}
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">PRECISION</div>
          </div>

          <div className="flex flex-col items-center">
            <div className="text-3xl font-mono font-semibold text-ink">
              {pct(metrics.recall)}
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">RECALL</div>
          </div>

          <div className="flex flex-col items-center">
            <div className="text-3xl font-mono font-semibold text-ink">
              {pct(metrics.f1)}
            </div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">F1 SCORE</div>
          </div>
        </div>

        <div className="pt-8 border-t border-line">
          <div className="text-xs font-mono uppercase tracking-widest text-dim mb-4">HUMAN CONTEXT ROUTING</div>
          <div className="grid grid-cols-2 gap-4">
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">CORRECTLY DEFERRED TO HUMAN</div>
              <div className="text-2xl font-mono text-ink">
                {humanContextCount} / {humanContextDenom}
              </div>
            </div>
            <div className="border border-line bg-panel p-4 rounded">
              <div className="text-[10px] font-mono text-dim uppercase mb-1">ROUTING ACCURACY</div>
              <div className="text-2xl font-mono text-ink">
                {metrics.human_context_routing_accuracy !== null ? pct(metrics.human_context_routing_accuracy) : '—'}
              </div>
            </div>
          </div>
        </div>

        {missed_cases.length > 0 && (
          <div className="pt-8">
            <div className="text-xs font-mono uppercase tracking-widest text-blocked mb-4">MISSED CASES ({missed_cases.length})</div>
            <div className="space-y-3">
              {missed_cases.map((c: any, i: number) => (
                <div key={i} className="border border-blocked/30 bg-blocked/5 p-4 rounded text-sm font-mono">
                  <div className="flex justify-between items-start mb-2">
                    <Link to={`/dispute/${c.dispute_id}`} className="font-semibold text-ink hover:underline">
                      {c.dispute_id}
                    </Link>
                    <span className="text-[10px] px-2 py-0.5 rounded border border-blocked/30 text-blocked uppercase">
                      {c.contradiction_class || 'FALSE POSITIVE'}
                    </span>
                  </div>
                  <div className="text-muted text-xs">Expected: {c.expected} | Actual: {c.actual}</div>
                  <div className="text-ink mt-2">{c.reason}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
"""

with open('frontend/src/pages/EvaluationPage.tsx', 'w') as f:
    f.write(code)
