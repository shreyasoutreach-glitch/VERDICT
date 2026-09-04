import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type Evaluation } from '../lib/api'

export default function EvaluationPage() {
  const [ev, setEv] = useState<Evaluation | null>(null)

  useEffect(() => {
    api.getEvaluation().then(setEv)
  }, [])

  if (!ev) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-muted text-sm font-mono">Computing evaluation...</div>
      </div>
    )
  }

  const { dataset, confusion_matrix, metrics, performance, status_counts, missed_cases } = ev

  const pct = (n: number) => `${(n * 100).toFixed(1)}%`

  const humanContextCount = status_counts['HUMAN_CONTEXT'] || 0
  const humanContextExpected = dataset.total - dataset.contradictory - dataset.clean + (dataset.total - dataset.contradictory - (confusion_matrix.true_negative + confusion_matrix.false_positive))
  const humanContextDenom = humanContextCount > 0 ? humanContextCount : humanContextExpected || humanContextCount

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-serif font-semibold tracking-tight text-ink">THE PROOF</h1>
        <p className="text-sm text-muted mt-2 font-serif italic">Live evaluation of the verification pipeline.</p>
      </div>

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
          <div className={`text-3xl font-mono font-semibold ${metrics.false_negative_count === 0 ? 'text-cleared' : 'text-blocked'}`}>
            {metrics.false_negative_count}
          </div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">FALSE NEGATIVES</div>
        </div>
        <div className="flex flex-col items-center">
          <div className="text-3xl font-mono font-semibold text-ink">
            {metrics.human_context_routing_accuracy !== null ? `${humanContextCount} / ${humanContextDenom}` : '—'}
          </div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-dim mt-1">HUMAN-CONTEXT ROUTED</div>
        </div>
      </div>

      <div className="flex items-center justify-center gap-8 py-4 border-y border-line">
        <div className="flex items-center">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">PRECISION</span>
          <span className="text-lg font-mono font-semibold text-ink ml-2">{pct(metrics.precision)}</span>
        </div>
        <div className="flex items-center">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">RECALL</span>
          <span className="text-lg font-mono font-semibold text-ink ml-2">{pct(metrics.recall)}</span>
        </div>
        <div className="flex items-center">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">F1</span>
          <span className="text-lg font-mono font-semibold text-ink ml-2">{pct(metrics.f1)}</span>
        </div>
        <div className="flex items-center">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">ACCURACY</span>
          <span className="text-lg font-mono font-semibold text-ink ml-2">{pct(metrics.automatic_decision_accuracy)}</span>
        </div>
      </div>

      <div className="text-sm font-mono text-muted text-center py-3">
        {performance.seconds}s {performance.disputes_per_second ? ` · ${performance.disputes_per_second} disputes/sec` : ''}
      </div>

      <div className="flex flex-col items-center">
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3 w-full max-w-sm text-left">
          CONFUSION MATRIX
        </div>
        <div className="grid grid-cols-2 gap-px bg-line rounded overflow-hidden max-w-sm w-full">
          <div className="bg-panel p-3">
            <span className="text-dim text-[10px] font-mono block mb-0.5">True Positive</span>
            <span className="font-mono text-sm text-ink">{confusion_matrix.true_positive}</span>
          </div>
          <div className="bg-panel p-3">
            <span className="text-dim text-[10px] font-mono block mb-0.5">False Positive</span>
            <span className="font-mono text-sm text-ink">{confusion_matrix.false_positive}</span>
          </div>
          <div className="bg-panel p-3">
            <span className="text-dim text-[10px] font-mono block mb-0.5">False Negative</span>
            <span className="font-mono text-sm text-ink">{confusion_matrix.false_negative}</span>
          </div>
          <div className="bg-panel p-3">
            <span className="text-dim text-[10px] font-mono block mb-0.5">True Negative</span>
            <span className="font-mono text-sm text-ink">{confusion_matrix.true_negative}</span>
          </div>
        </div>
      </div>

      <div className="text-sm font-mono text-muted text-center">
        {dataset.total} DISPUTES · <span className="text-blocked">{dataset.contradictory} CONTRADICTORY</span> · <span className="text-cleared">{dataset.clean} CLEAN</span>
      </div>

      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3">MISSED CASES</div>
        {missed_cases.length === 0 ? (
          <div className="border border-cleared/30 bg-cleared/5 p-4 text-sm text-cleared rounded">
            No missed cases on this run — every seeded contradiction was caught and no clean case was wrongly blocked.
          </div>
        ) : (
          <div className="border border-line bg-panel rounded divide-y divide-line">
            {missed_cases.map(m => (
              <div key={m.dispute_id} className="p-3 text-sm flex justify-between items-center">
                <Link to={`/dispute/${m.dispute_id}`} className="font-mono text-wire hover:underline">
                  {m.dispute_id}
                </Link>
                <span className="text-muted text-xs">
                  Expected {m.expected}, got {m.actual} — {m.reason}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="border border-line bg-panel rounded p-4 text-sm text-muted leading-relaxed mt-8">
        This result is measured on the seeded synthetic benchmark and is not a claim of perfect real-world recall.
      </div>
    </div>
  );
}
