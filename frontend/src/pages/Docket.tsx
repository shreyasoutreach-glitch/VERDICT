import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, type DisputeSummary } from '../lib/api'
import StatusBadge from '../components/StatusBadge'

export default function Docket() {
  const [disputes, setDisputes] = useState<DisputeSummary[] | null>(null)
  const [filter, setFilter] = useState<'ALL' | 'CLEARED' | 'BLOCKED' | 'HUMAN_CONTEXT'>('ALL')
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set())
  const navigate = useNavigate()

  const load = useCallback(async () => {
    try {
      const next = await api.listDisputes()
      setDisputes((prev) => {
        if (prev) {
          const changed = new Set<string>()
          for (const d of next) {
            const before = prev.find((p) => p.dispute_id === d.dispute_id)
            if (before && before.status !== d.status) changed.add(d.dispute_id)
          }
          if (changed.size) {
            setFlashIds(changed)
            setTimeout(() => setFlashIds(new Set()), 1100)
          }
        }
        return next
      })
    } catch (e) {
      console.error(e)
    }
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 2000)
    return () => clearInterval(t)
  }, [load])

  if (!disputes) {
    return <div className="text-muted text-sm py-12 text-center font-mono">Loading docket...</div>
  }

  const counts = {
    total: disputes.length,
    cleared: disputes.filter((d) => d.status === 'CLEARED').length,
    blocked: disputes.filter((d) => d.status === 'BLOCKED').length,
    humanContext: disputes.filter((d) => d.status === 'HUMAN_CONTEXT').length,
  }

  const shown = filter === 'ALL' ? disputes : disputes.filter((d) => d.status === filter)

  const getBorderClass = (status: string) => {
    switch (status) {
      case 'CLEARED': return 'border-l-cleared'
      case 'BLOCKED': return 'border-l-blocked'
      case 'HUMAN_CONTEXT': return 'border-l-context'
      default: return 'border-l-dim'
    }
  }

  const formatClaim = (claim: string | null) => {
    if (!claim) return '—'
    const formatted = claim.replace(/_/g, ' ')
    return formatted.charAt(0).toUpperCase() + formatted.slice(1)
  }

  return (
    <div className="flex flex-col gap-10">
      <div>
        <div className="text-[15px] font-serif italic text-dim mb-4">
          Veridict · Cross-System Truth Verification
        </div>
        <div className="text-5xl sm:text-6xl font-semibold tracking-tight text-ink font-mono">
          {counts.total}
        </div>
        <div className="text-xs font-mono uppercase tracking-widest text-dim mt-2">
          DISPUTES UNDER EXAMINATION
        </div>

        <div className="flex items-center flex-wrap gap-2 mt-6 text-sm font-mono">
          <div className="flex items-center gap-1.5 text-cleared">
            <div className="w-1.5 h-1.5 rounded-full bg-cleared" />
            {counts.cleared} CLEARED
          </div>
          <span className="text-dim">·</span>
          <div className="flex items-center gap-1.5 text-blocked">
            <div className="w-1.5 h-1.5 rounded-full bg-blocked" />
            {counts.blocked} BLOCKED
          </div>
          <span className="text-dim">·</span>
          <div className="flex items-center gap-1.5 text-context">
            <div className="w-1.5 h-1.5 rounded-full bg-context" />
            {counts.humanContext} HUMAN CONTEXT
          </div>
        </div>
      </div>

      <div className="flex items-center gap-6 border-b border-line">
        {(['ALL', 'CLEARED', 'BLOCKED', 'HUMAN_CONTEXT'] as const).map((f) => {
          const isActive = filter === f
          const count = f === 'ALL' ? counts.total : counts[f === 'CLEARED' ? 'cleared' : f === 'BLOCKED' ? 'blocked' : 'humanContext']
          const label = f.replace('_', ' ')
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`pb-3 text-xs font-mono uppercase tracking-wide transition-colors ${
                isActive
                  ? 'text-ink border-b-2 border-ink'
                  : 'text-muted hover:text-ink border-b-2 border-transparent'
              }`}
            >
              {label} ({count})
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 stagger">
        {shown.map((d) => (
          <div
            key={d.dispute_id}
            onClick={() => navigate(`/dispute/${d.dispute_id}`)}
            className={`border border-line bg-panel rounded p-4 hover:bg-raised hover:border-line2 transition-colors cursor-pointer border-l-2 flex flex-col justify-between min-h-[120px] ${
              getBorderClass(d.status)
            } ${flashIds.has(d.dispute_id) ? 'flash-update' : ''}`}
          >
            <div>
              <div className="flex items-start justify-between gap-4">
                <div className="font-mono text-sm text-ink font-medium truncate">
                  {d.dispute_id}
                </div>
                <StatusBadge status={d.status} size="sm" />
              </div>
              <div className="text-muted text-[15px] mt-3 line-clamp-2 font-serif italic leading-relaxed">
                {formatClaim(d.claim_summary)}
              </div>
            </div>
            
            <div className="flex items-center gap-3 mt-4 text-[10px] font-mono text-dim uppercase tracking-wide flex-wrap">
              {d.cited_source && (
                <span className="capitalize">{d.cited_source}</span>
              )}
              {d.cited_source && <span>·</span>}
              <span>{d.systems_checked.length} WITNESSES</span>
              <span>·</span>
              <span>
                {d.contradictions} CONFLICT{d.contradictions !== 1 ? 'S' : ''}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
