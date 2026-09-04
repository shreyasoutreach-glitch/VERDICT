import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

interface Props {
  name: string
  record: Record<string, unknown> | null
  examinedFields: string[]
  primary?: string[]
}

function formatDate(v: string): string {
  try {
    const d = new Date(v)
    if (isNaN(d.getTime())) return v
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
  } catch { return v }
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'number') return v % 1 !== 0 ? `\u20b9${v.toLocaleString('en-IN', { minimumFractionDigits: 2 })}` : v.toLocaleString('en-IN')
  if (Array.isArray(v)) return `${v.length} event(s)`
  const s = String(v)
  // Try to format dates
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return formatDate(s.slice(0, 10))
  return s
}

function formatFieldLabel(k: string): string {
  return k.replace(/_/g, ' ').toUpperCase()
}

export default function WitnessCard({ name, record, examinedFields, primary = [] }: Props) {
  const [expanded, setExpanded] = useState(false)
  const wasExamined = examinedFields.length > 0
  const hasConflict = examinedFields.length > 0

  if (!record) {
    return (
      <div className="border border-line2 bg-panel rounded p-4 opacity-40">
        <div className="text-[10px] font-mono uppercase tracking-widest text-dim mb-3">{name}</div>
        <div className="text-sm text-dim font-mono">NO RECORD</div>
        <div className="mt-3 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-dim" />
          <span className="text-[10px] font-mono text-dim tracking-wide">UNAVAILABLE</span>
        </div>
      </div>
    )
  }

  // Extract record ID (first field that looks like an ID)
  const idField = Object.entries(record).find(([k]) =>
    k.endsWith('_id') || k === 'order_id' || k === 'payment_id' || k === 'shipment_id' || k === 'entry_id'
  )

  const displayEntries = Object.entries(record).filter(([k]) => k !== 'scan_events' && !k.endsWith('_id') && k !== 'customer_id')
  const shown = primary.length
    ? displayEntries.filter(([k]) => primary.includes(k))
    : displayEntries.slice(0, 3)

  // Determine if any examined field has a conflict (we infer from the context)
  const borderColor = wasExamined ? 'border-l-wire' : 'border-l-transparent'

  return (
    <div className={`border border-line bg-panel rounded p-4 flex flex-col gap-3 transition-colors border-l-2 ${borderColor}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono uppercase tracking-widest text-dim">{name}</span>
        {wasExamined && (
          <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-wire/10 text-wire border border-wire/20 tracking-wide">
            EXAMINED
          </span>
        )}
      </div>

      {/* Record ID */}
      {idField && (
        <div className="font-mono text-sm text-ink font-medium tracking-tight">
          {String(idField[1])}
        </div>
      )}

      {/* Key Facts */}
      <div className="flex flex-col gap-2.5">
        {shown.map(([k, v]) => {
          const isExamined = examinedFields.includes(k)
          return (
            <div key={k} className="flex flex-col gap-0.5">
              <span className="text-[9px] font-mono uppercase tracking-widest text-dim">
                {formatFieldLabel(k)}
              </span>
              <span className={`font-mono text-sm ${isExamined ? 'text-ink font-medium' : 'text-muted'}`}>
                {formatValue(v)}
              </span>
            </div>
          )
        })}
      </div>

      {/* Status */}
      <div className="mt-auto pt-2 border-t border-line flex items-center gap-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${wasExamined ? 'bg-wire' : 'bg-dim'}`} />
        <span className={`text-[10px] font-mono tracking-wide ${wasExamined ? 'text-wire' : 'text-dim'}`}>
          {wasExamined ? 'VERIFIED' : 'CHECKED'}
        </span>
      </div>

      {/* Raw Record Toggle */}
      <button
        onClick={(e) => { e.stopPropagation(); setExpanded((x) => !x) }}
        className="flex items-center gap-1 text-[10px] text-dim hover:text-muted self-start font-mono"
      >
        {expanded ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        {expanded ? 'HIDE RAW' : 'VIEW RAW'}
      </button>
      {expanded && (
        <pre className="text-[10px] font-mono bg-base border border-line rounded p-2.5 overflow-x-auto text-muted max-h-48 overflow-y-auto">
          {JSON.stringify(record, null, 2)}
        </pre>
      )}
    </div>
  )
}
