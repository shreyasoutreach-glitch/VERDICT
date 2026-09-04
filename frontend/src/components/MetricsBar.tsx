interface Props {
  total: number
  cleared: number
  blocked: number
  humanContext: number
}

function Stat({ value, label, color }: { value: number; label: string; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={`text-2xl font-semibold tabular-nums ${color || 'text-ink'}`}>{value}</span>
      <span className="text-xs text-muted uppercase tracking-wide">{label}</span>
    </div>
  )
}

export default function MetricsBar({ total, cleared, blocked, humanContext }: Props) {
  return (
    <div className="flex items-center gap-8 py-5 px-6 rounded-lg border border-line bg-panel">
      <Stat value={total} label="Evidence packets" />
      <div className="w-px h-9 bg-line" />
      <Stat value={cleared} label="Cleared" color="text-cleared" />
      <div className="w-px h-9 bg-line" />
      <Stat value={blocked} label="Blocked" color="text-blocked" />
      <div className="w-px h-9 bg-line" />
      <Stat value={humanContext} label="Human context" color="text-context" />
    </div>
  )
}
