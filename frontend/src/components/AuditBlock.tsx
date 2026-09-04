import type { Verdict } from '../lib/api'

const METHOD_LABEL: Record<string, string> = {
  deterministic_temporal_window:      'DETERMINISTIC · TEMPORAL WINDOW',
  deterministic_temporal_chronology:  'DETERMINISTIC · CHRONOLOGY',
  deterministic_exact_amount:         'DETERMINISTIC · AMOUNT CHECK',
  deterministic_exact_match:          'DETERMINISTIC · EXACT MATCH',
  deterministic_cross_system_status:  'DETERMINISTIC · STATUS CROSS-CHECK',
  deterministic_ledger_presence:      'DETERMINISTIC · LEDGER PRESENCE',
  deterministic_duplicate_consequence:'DETERMINISTIC · DUPLICATE CHECK',
  deterministic_entity_resolution:    'DETERMINISTIC · ENTITY RESOLUTION',
  citation_not_found:                 'CITATION · RECORD NOT FOUND',
  llm_adjudicated:                    'LLM · TOOL-GROUNDED',
  llm_adjudicated_rejected:           'LLM · REJECTED (UNSAFE)',
  llm_adjudication_error:             'LLM · FAILED SAFE',
  demo_adjudicated:                   'DEMO · RULE-BASED',
}

export default function AuditBlock({ verdict }: { verdict: Verdict }) {
  return (
    <div className="border border-line bg-panel/50 rounded overflow-hidden">
      <div className="px-4 py-2.5 border-b border-line bg-raised/50">
        <span className="text-[10px] font-mono uppercase tracking-widest text-dim">
          VERIFICATION RECORD
        </span>
      </div>
      <div className="px-4 py-3 font-mono text-xs space-y-2.5">
        <div className="flex justify-between items-baseline">
          <span className="text-dim tracking-wide">VERDICT</span>
          <span className={`font-semibold uppercase ${
            verdict.verdict === 'contradicted' ? 'text-blocked' :
            verdict.verdict === 'supported' ? 'text-cleared' : 'text-context'
          }`}>
            {verdict.verdict.replace('_', ' ')}
          </span>
        </div>

        <div className="flex justify-between items-baseline gap-4">
          <span className="text-dim tracking-wide shrink-0">METHOD</span>
          <span className="text-muted text-right text-[11px]">
            {METHOD_LABEL[verdict.verification_method] || verdict.verification_method}
          </span>
        </div>

        {verdict.source_records.length > 0 && (
          <div className="pt-2 mt-1 border-t border-line space-y-1.5">
            <span className="text-dim tracking-wide text-[10px]">EVIDENCE RECORDS</span>
            {verdict.source_records.map((r, i) => (
              <div key={i} className="flex justify-between items-baseline text-[11px] gap-3">
                <span className="text-ink uppercase">{r.source} / {r.record_id}</span>
                <span className="text-muted text-right">
                  {r.field !== '*' ? `${r.field} = ${r.value}` : ''}
                </span>
              </div>
            ))}
          </div>
        )}

        <div className="pt-2 mt-1 border-t border-line">
          <span className="text-dim tracking-wide text-[10px] block mb-1">REASON</span>
          <span className="text-muted font-sans text-xs leading-relaxed">{verdict.reason}</span>
        </div>
      </div>
    </div>
  )
}
