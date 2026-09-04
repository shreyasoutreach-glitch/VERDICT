import type { Status } from '../lib/api'

const CONFIG: Record<Status, { label: string; color: string; bg: string; border: string; dot: string }> = {
  CLEARED:       { label: 'CLEARED',       color: 'text-cleared', bg: 'bg-cleared/8',  border: 'border-cleared/25', dot: 'bg-cleared' },
  BLOCKED:       { label: 'BLOCKED',       color: 'text-blocked', bg: 'bg-blocked/8',  border: 'border-blocked/25', dot: 'bg-blocked' },
  HUMAN_CONTEXT: { label: 'HUMAN CONTEXT', color: 'text-context', bg: 'bg-context/8',  border: 'border-context/25', dot: 'bg-context' },
  PENDING:       { label: 'PENDING',       color: 'text-dim',     bg: 'bg-dim/8',      border: 'border-line2',      dot: 'bg-dim' },
}

export default function StatusBadge({ status, size = 'md' }: { status: Status; size?: 'sm' | 'md' | 'lg' }) {
  const c = CONFIG[status]

  if (size === 'lg') {
    return (
      <div className={`inline-flex items-center gap-2.5 px-4 py-2 rounded border ${c.bg} ${c.border}`}>
        <span className={`w-2.5 h-2.5 rounded-full ${c.dot}`} />
        <span className={`text-sm font-semibold font-mono tracking-wide ${c.color}`}>{c.label}</span>
      </div>
    )
  }

  const pad = size === 'sm'
    ? 'px-2 py-0.5 text-[10px] gap-1.5'
    : 'px-2.5 py-1 text-xs gap-1.5'

  return (
    <span className={`inline-flex items-center ${pad} rounded border font-mono font-medium tracking-wide ${c.color} ${c.bg} ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${c.dot}`} />
      {c.label}
    </span>
  )
}
