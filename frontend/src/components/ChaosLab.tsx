import { useState } from 'react'
import { FlaskConical, Zap, Loader2 } from 'lucide-react'
import { api, type DisputeSummary } from '../lib/api'

const TYPES = [
  { value: 'delivery_window', label: 'Delivery window (late vs. promised)' },
  { value: 'amount_mismatch', label: 'Amount mismatch (gateway vs. ledger)' },
  { value: 'payment_status', label: 'Payment status (stale vs. ledger refund)' },
]

interface Props {
  disputes: DisputeSummary[]
  onInjected: () => void
}

export default function ChaosLab({ disputes, onInjected }: Props) {
  const [open, setOpen] = useState(false)
  const [orderId, setOrderId] = useState('')
  const [type, setType] = useState(TYPES[0].value)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<Awaited<ReturnType<typeof api.injectContradiction>> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [resetting, setResetting] = useState(false)

  const cleared = disputes.filter((d) => d.status === 'CLEARED')

  async function runInjection() {
    if (!orderId) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const res = await api.injectContradiction(orderId, type)
      setResult(res)
      onInjected()
    } catch (e: any) {
      setError(e.message || 'Injection failed')
    } finally {
      setBusy(false)
    }
  }

  async function doReset() {
    setResetting(true)
    try {
      await api.resetDemo()
      setResult(null)
      setError(null)
      onInjected()
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="rounded-lg border border-line2 bg-panel overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-5 py-3.5 text-left hover:bg-raised transition-colors"
      >
        <span className="flex items-center gap-2.5 text-sm font-medium">
          <FlaskConical size={15} className="text-wire" />
          Chaos Lab
          <span className="text-dim font-mono text-xs font-normal">
            inject a real inconsistency into merchant state
          </span>
        </span>
        <span className="text-dim text-xs font-mono">{open ? 'hide' : 'open'}</span>
      </button>

      {open && (
        <div className="border-t border-line px-5 py-4 flex flex-col gap-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="flex flex-col gap-1.5 text-xs text-muted">
              Order (currently clean)
              <select
                value={orderId}
                onChange={(e) => setOrderId(e.target.value)}
                className="bg-raised border border-line2 rounded px-2.5 py-2 text-ink text-sm font-mono focus:outline-none focus:border-wire"
              >
                <option value="">select an order…</option>
                {cleared.map((d) => (
                  <option key={d.order_id} value={d.order_id}>
                    {d.order_id} ({d.dispute_id})
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1.5 text-xs text-muted">
              Contradiction type
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="bg-raised border border-line2 rounded px-2.5 py-2 text-ink text-sm focus:outline-none focus:border-wire"
              >
                {TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end gap-2">
              <button
                onClick={runInjection}
                disabled={!orderId || busy}
                className="flex-1 flex items-center justify-center gap-2 bg-blocked/15 border border-blocked/40 text-blocked hover:bg-blocked/25 disabled:opacity-40 disabled:cursor-not-allowed rounded px-3 py-2 text-sm font-medium transition-colors"
              >
                {busy ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
                Inject contradiction
              </button>
              <button
                onClick={doReset}
                disabled={resetting}
                className="px-3 py-2 text-sm text-muted hover:text-ink border border-line2 rounded transition-colors"
              >
                {resetting ? '…' : 'Reset demo'}
              </button>
            </div>
          </div>

          {error && <div className="text-sm text-blocked font-mono">{error}</div>}

          {result && (
            <div className="rounded border border-line2 bg-raised p-4 text-sm flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs text-muted">
                {result.steps.map((s, i) => (
                  <span key={i} className="flex items-center gap-1.5">
                    <span className="px-1.5 py-0.5 rounded bg-wire/10 text-wire border border-wire/25">{s}</span>
                    {i < result.steps.length - 1 && <span className="text-dim">→</span>}
                  </span>
                ))}
              </div>
              <div className="pt-1">
                Order <span className="font-mono text-ink">{result.order_id}</span> → dispute{' '}
                <span className="font-mono text-ink">{result.dispute_id}</span> is now{' '}
                <span className="font-semibold">{result.new_status}</span>. This is a real row in the
                database, re-verified from scratch — not a scripted transition.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
