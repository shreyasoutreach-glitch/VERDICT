import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { Claim, Verdict } from '../lib/api'

function formatFieldLabel(field: string): string {
  return field.replace(/_/g, ' ').toUpperCase()
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'string') {
    const m = v.match(/^(\d{4})-(\d{2})-(\d{2})/)
    if (m) {
      try {
        const d = new Date(m[0])
        return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
      } catch { return v }
    }
    return v
  }
  if (typeof v === 'number') {
    return v % 1 !== 0 ? `\u20b9${v.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : String(v)
  }
  return String(v)
}

const METHOD_LABEL: Record<string, string> = {
  deterministic_temporal_window:      'DETERMINISTIC · TEMPORAL WINDOW CHECK',
  deterministic_temporal_chronology:  'DETERMINISTIC · CHRONOLOGY CHECK',
  deterministic_exact_amount:         'DETERMINISTIC · AMOUNT COMPARISON',
  deterministic_exact_match:          'DETERMINISTIC · EXACT FIELD MATCH',
  deterministic_cross_system_status:  'DETERMINISTIC · STATUS CROSS-CHECK',
  deterministic_ledger_presence:      'DETERMINISTIC · LEDGER PRESENCE CHECK',
  deterministic_duplicate_consequence:'DETERMINISTIC · DUPLICATE CHECK',
  deterministic_entity_resolution:    'DETERMINISTIC · ENTITY RESOLUTION',
  citation_not_found:                 'CITATION CHECK · RECORD NOT FOUND',
  llm_adjudicated:                    'LLM ADJUDICATION · TOOL-GROUNDED',
  demo_adjudicated:                   'DEMO ADJUDICATOR · RULE-BASED',
}

interface Props {
  claim: Claim
  verdict: Verdict
  narrative: string
}

export default function ReasoningChain({ claim, verdict, narrative }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-line bg-panel rounded overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full px-5 py-3 flex items-center justify-between hover:bg-raised transition-colors"
      >
        <span className="text-xs font-mono uppercase tracking-widest text-dim">SHOW ME WHY</span>
        {open ? <ChevronDown size={14} className="text-dim" /> : <ChevronRight size={14} className="text-dim" />}
      </button>

      {open && (
        <div className="px-5 pb-5 animate-fade-in">
          <div className="flex flex-col items-center">
            {/* Step 1: AI Claim */}
            <ChainNode
              label="AI CLAIM"
              value={`"${narrative}"`}
              sublabel={`CITED: ${claim.cited_source.toUpperCase()} / ${claim.cited_record}`}
              tone="neutral"
            />
            <ChainConnector />

            {/* Step 2+: Source Records */}
            {verdict.source_records.map((r, i) => (
              <div key={i} className="flex flex-col items-center w-full">
                <ChainNode
                  label={formatFieldLabel(r.field)}
                  value={formatValue(r.value)}
                  sublabel={`SOURCE: ${r.source.toUpperCase()} / ${r.record_id}`}
                  tone="neutral"
                />
                <ChainConnector />
              </div>
            ))}

            {/* Verdict step */}
            {verdict.verdict === 'contradicted' && (
              <>
                <ChainNode label="CONTRADICTION" value="EVIDENCE CONFLICTS" tone="blocked" />
                <ChainConnector />
              </>
            )}

            {/* Final verdict */}
            <ChainNode
              label="VERDICT"
              value={verdict.verdict === 'contradicted' ? 'BLOCKED' : verdict.verdict === 'supported' ? 'CLEARED' : 'HUMAN CONTEXT REQUIRED'}
              tone={verdict.verdict === 'contradicted' ? 'blocked' : verdict.verdict === 'supported' ? 'cleared' : 'context'}
            />

            {/* Method */}
            <div className="mt-4 text-center">
              <span className="text-[10px] font-mono uppercase tracking-widest text-dim block mb-1">METHOD</span>
              <span className="text-xs font-mono text-muted">
                {METHOD_LABEL[verdict.verification_method] || verdict.verification_method}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ChainNode({ label, value, sublabel, tone }: {
  label: string
  value: string
  sublabel?: string
  tone: 'neutral' | 'blocked' | 'cleared' | 'context'
}) {
  const border =
    tone === 'blocked' ? 'border-blocked/40 bg-blocked/5' :
    tone === 'cleared' ? 'border-cleared/40 bg-cleared/5' :
    tone === 'context' ? 'border-context/40 bg-context/5' :
    'border-line bg-raised/50'

  const valueColor =
    tone === 'blocked' ? 'text-blocked' :
    tone === 'cleared' ? 'text-cleared' :
    tone === 'context' ? 'text-context' :
    'text-ink'

  return (
    <div className={`w-full max-w-md border rounded px-4 py-3 text-center ${border}`}>
      <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">{label}</span>
      <span className={`text-sm font-mono font-medium ${valueColor} block`}>{value}</span>
      {sublabel && <span className="text-[10px] font-mono text-dim mt-1 block">{sublabel}</span>}
    </div>
  )
}

function ChainConnector() {
  return (
    <div className="flex flex-col items-center py-1">
      <div className="w-px h-5 bg-line2" />
      <span className="text-dim text-[10px]">↓</span>
      <div className="w-px h-5 bg-line2" />
    </div>
  )
}
