import { useEffect, useState } from 'react'
import { api, type DisputeSummary } from '../lib/api'

export default function ActivityTicker() {
  const [disputes, setDisputes] = useState<DisputeSummary[]>([])
  const [activeIdx, setActiveIdx] = useState(0)

  useEffect(() => {
    api.listDisputes()
      .then((d) => setDisputes(d.slice(0, 12)))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (disputes.length === 0) return
    const t = setInterval(() => setActiveIdx((i) => (i + 1) % disputes.length), 4000)
    return () => clearInterval(t)
  }, [disputes.length])

  if (disputes.length === 0) return null

  const d = disputes[activeIdx]
  const color =
    d.status === 'CLEARED'       ? 'text-cleared' :
    d.status === 'BLOCKED'       ? 'text-blocked' :
    d.status === 'HUMAN_CONTEXT' ? 'text-context' : 'text-dim'

  return (
    <div className="flex items-center gap-2 text-[10px] font-mono text-dim">
      <span className="w-1 h-1 rounded-full bg-cleared animate-pulse-dot shrink-0" />
      <span className="text-muted">{d.dispute_id}</span>
      <span>·</span>
      <span>{d.systems_checked.length} SYSTEMS</span>
      <span>·</span>
      <span>{d.contradictions} CONFLICTS</span>
      <span className="text-dim">→</span>
      <span className={color}>{d.status.replace('_', ' ')}</span>
    </div>
  )
}
