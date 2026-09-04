import { type SourceRecord } from '../lib/api'

function formatDateValue(v: unknown): string {
  if (typeof v !== 'string') return String(v ?? '—')
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return String(v)
  try {
    const d = new Date(m[0])
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
  } catch { return String(v) }
}

function formatFieldLabel(field: string): string {
  return field.replace(/_/g, ' ').toUpperCase()
}

function computeDelta(records: SourceRecord[]): string | null {
  // Try date delta
  const dates = records.map((r) => {
    const s = String(r.value)
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
    return m ? new Date(m[0]) : null
  }).filter(Boolean) as Date[]

  if (dates.length >= 2) {
    const diffMs = Math.abs(dates[1].getTime() - dates[0].getTime())
    const days = Math.round(diffMs / (1000 * 60 * 60 * 24))
    if (days > 0) return `+${days} DAY${days !== 1 ? 'S' : ''}`
  }

  // Try numeric delta
  const nums = records.map((r) => typeof r.value === 'number' ? r.value : parseFloat(String(r.value)))
    .filter((n) => !isNaN(n))
  if (nums.length >= 2) {
    const diff = Math.abs(nums[1] - nums[0])
    if (diff > 0.01) return `\u20b9${diff.toLocaleString('en-IN', { minimumFractionDigits: 2 })}`
  }

  return null
}

interface Props {
  sourceRecords: SourceRecord[]
  reason: string
}

export default function ContradictionReveal({ sourceRecords, reason }: Props) {
  if (sourceRecords.length < 2) return null

  // Group records by source to find the two conflicting sides
  const left = sourceRecords[0]
  const right = sourceRecords[1]
  const delta = computeDelta(sourceRecords)

  return (
    <div className="animate-fade-in">
      {/* Contradiction header */}
      <div className="flex items-center justify-center gap-3 mb-6">
        <div className="h-px flex-1 bg-blocked/30" />
        <span className="text-blocked font-mono text-xs font-semibold tracking-widest uppercase flex items-center gap-2">
          <span className="text-lg">×</span> CONTRADICTION FOUND
        </span>
        <div className="h-px flex-1 bg-blocked/30" />
      </div>

      {/* Evidence comparison */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-stretch">
        {/* Left source */}
        <div className="border border-line bg-panel rounded p-4 flex flex-col gap-2">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">
            {left.source.toUpperCase()}
          </span>
          <span className="text-[10px] font-mono text-dim tracking-wide">
            {left.record_id}
          </span>
          <div className="mt-1">
            <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">
              {formatFieldLabel(left.field)}
            </span>
            <span className="text-xl font-mono font-semibold text-ink tracking-tight">
              {formatDateValue(left.value)}
            </span>
          </div>
        </div>

        {/* Connector */}
        <div className="flex flex-col items-center justify-center gap-2 px-2">
          <svg width="2" height="20" className="text-blocked/50">
            <line x1="1" y1="0" x2="1" y2="20" stroke="currentColor" strokeWidth="1" strokeDasharray="3 2" className="draw-connector" />
          </svg>
          <div className="w-8 h-8 rounded-full border-2 border-blocked/60 bg-blocked/10 flex items-center justify-center">
            <span className="text-blocked font-bold text-sm">×</span>
          </div>
          {delta && (
            <div className="text-center mt-1">
              <span className="text-[10px] font-mono uppercase tracking-widest text-dim block">DELTA</span>
              <span className="text-sm font-mono font-semibold text-blocked">{delta}</span>
            </div>
          )}
          <svg width="2" height="20" className="text-blocked/50">
            <line x1="1" y1="0" x2="1" y2="20" stroke="currentColor" strokeWidth="1" strokeDasharray="3 2" className="draw-connector" />
          </svg>
        </div>

        {/* Right source */}
        <div className="border border-line bg-panel rounded p-4 flex flex-col gap-2">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim">
            {right.source.toUpperCase()}
          </span>
          <span className="text-[10px] font-mono text-dim tracking-wide">
            {right.record_id}
          </span>
          <div className="mt-1">
            <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">
              {formatFieldLabel(right.field)}
            </span>
            <span className="text-xl font-mono font-semibold text-ink tracking-tight">
              {formatDateValue(right.value)}
            </span>
          </div>
        </div>
      </div>

      {/* Reason */}
      <div className="mt-6 text-center">
        <p className="text-[15px] text-muted leading-relaxed max-w-xl mx-auto font-serif italic">{reason}</p>
      </div>
    </div>
  )
}
