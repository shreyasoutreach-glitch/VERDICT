import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { api, type DisputeDetail as DisputeDetailT, type Witnesses, type AuditEntry } from '../lib/api'
import StatusBadge from '../components/StatusBadge'
import WitnessCard from '../components/WitnessCard'
import AuditBlock from '../components/AuditBlock'
import HumanWitnessPanel from '../components/HumanWitnessPanel'
import ContradictionReveal from '../components/ContradictionReveal'
import ReasoningChain from '../components/ReasoningChain'

const SOFT_QUESTIONS: Record<string, string> = {
  delivery_refusal_intent: 'Why was the delivery not completed?',
  service_quality: 'What actually happened with this customer?',
  fulfillment_quality: 'What actually happened with this order?',
  customer_request_fulfilled: "What did the customer's request actually involve?",
}

export default function DisputeDetail() {
  const { id } = useParams<{ id: string }>()
  const [dispute, setDispute] = useState<DisputeDetailT | null>(null)
  const [witnesses, setWitnesses] = useState<Witnesses | null>(null)
  const [audit, setAudit] = useState<AuditEntry[]>([])

  const load = useCallback(async () => {
    if (!id) return
    const [d, w, a] = await Promise.all([api.getDispute(id), api.getWitnesses(id), api.getAudit(id)])
    setDispute(d)
    setWitnesses(w)
    setAudit(a)
  }, [id])

  useEffect(() => { load() }, [load])

  if (!dispute || !witnesses) {
    return <div className="text-muted text-sm py-20 text-center font-mono">Loading case file…</div>
  }

  const claim = dispute.claims[0]
  const verdict = dispute.verdicts.find((v) => v.claim_id === claim?.claim_id)
  const examinedBySource: Record<string, string[]> = { razorpay: [], shopify: [], shiprocket: [], tally: [] }
  verdict?.source_records.forEach((r) => {
    if (examinedBySource[r.source]) examinedBySource[r.source].push(r.field)
  })

  const isContradicted = verdict?.verdict === 'contradicted'
  const isSupported = verdict?.verdict === 'supported'
  const isInsufficient = verdict?.verdict === 'insufficient_evidence'

  return (
    <div className="flex flex-col gap-8 animate-fade-in">
      {/* Back link */}
      <Link to="/" className="flex items-center gap-1.5 text-xs text-dim hover:text-muted w-fit transition-colors font-mono uppercase tracking-wide">
        <ArrowLeft size={12} /> DOCKET
      </Link>

      {/* ── CASE HEADER ── */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        <div>
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim block mb-1">CASE</span>
          <h1 className="text-3xl font-semibold tracking-tight font-mono text-ink">{dispute.dispute_id}</h1>
        </div>
        <StatusBadge status={dispute.status} size="lg" />
      </div>

      {/* ── CLAIM UNDER EXAMINATION ── */}
      {claim && (
        <div className="border border-line bg-panel rounded p-6">
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim block mb-4">
            CLAIM UNDER EXAMINATION
          </span>
          <p className="text-2xl leading-relaxed text-ink font-serif italic">
            <span className="text-dim mr-1">"</span>
            {dispute.narrative}
            <span className="text-dim ml-1">"</span>
          </p>
          <div className="mt-4 pt-4 border-t border-line flex flex-wrap items-center gap-4 text-[10px] font-mono uppercase tracking-wide text-dim">
            <span>AI-GENERATED CLAIM</span>
            <span className="text-line2">·</span>
            <span>CITED: <span className="text-muted">{claim.cited_source.toUpperCase()} / {claim.cited_record}</span></span>
            <span className="text-line2">·</span>
            <span>CONFIDENCE: <span className="text-muted">{(claim.confidence * 100).toFixed(0)}%</span></span>
          </div>
        </div>
      )}

      {/* ── CROSS-EXAMINATION ── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <span className="text-[10px] font-mono uppercase tracking-widest text-dim block mb-1">CROSS-EXAMINATION</span>
            <span className="text-xs font-mono text-muted">
              {Object.values(witnesses).flat().filter(Boolean).length} INDEPENDENT WITNESSES
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 stagger">
          <WitnessCard name="SHOPIFY" record={witnesses.shopify} examinedFields={examinedBySource.shopify}
                        primary={['order_status', 'promised_delivery_date', 'return_date']} />
          <WitnessCard name="SHIPROCKET" record={witnesses.shiprocket} examinedFields={examinedBySource.shiprocket}
                        primary={['status', 'delivered_date', 'dispatch_date']} />
          <WitnessCard name="RAZORPAY" record={witnesses.razorpay} examinedFields={examinedBySource.razorpay}
                        primary={['amount', 'status', 'method']} />
          <WitnessCard name="TALLY" record={witnesses.tally[0] || null} examinedFields={examinedBySource.tally}
                        primary={['entry_type', 'amount', 'entry_date']} />
        </div>
      </div>

      {/* ── CONTRADICTION REVEAL ── */}
      {verdict && isContradicted && verdict.source_records.length >= 2 && (
        <ContradictionReveal
          sourceRecords={verdict.source_records}
          reason={verdict.reason}
        />
      )}

      {/* ── VERDICT ── */}
      {verdict && (
        <div className={`rounded p-8 text-center border ${
          isContradicted
            ? 'border-blocked/30 bg-blocked/5'
            : isSupported
            ? 'border-cleared/30 bg-cleared/5'
            : 'border-context/30 bg-context/5'
        }`}>
          <p className="text-sm text-muted font-mono uppercase tracking-wide mb-3">
            {isContradicted
              ? 'CLAIM CANNOT BE SUPPORTED'
              : isSupported
              ? 'ALL WITNESSES AGREE'
              : 'INSUFFICIENT EVIDENCE FOR DETERMINATION'}
          </p>
          <h2 className={`text-4xl font-bold tracking-tight font-mono ${
            isContradicted ? 'text-blocked' : isSupported ? 'text-cleared' : 'text-context'
          }`}>
            {isContradicted ? 'BLOCKED' : isSupported ? 'CLEARED' : 'HUMAN CONTEXT'}
          </h2>
        </div>
      )}

      {/* ── REASONING CHAIN ── */}
      {claim && verdict && (
        <ReasoningChain claim={claim} verdict={verdict} narrative={dispute.narrative} />
      )}

      {/* ── VERIFICATION RECORD ── */}
      {verdict && <AuditBlock verdict={verdict} />}

      {/* ── HUMAN WITNESS ── */}
      {dispute.status === 'HUMAN_CONTEXT' && claim && (
        <HumanWitnessPanel
          disputeId={dispute.dispute_id}
          claimId={claim.claim_id}
          claimType={claim.claim_type}
          question={SOFT_QUESTIONS[claim.claim_type] || 'What actually happened here?'}
          existing={dispute.human_attestations}
          onSubmitted={load}
        />
      )}

      {/* ── AUDIT TRAIL ── */}
      {audit.length > 0 && (
        <div>
          <span className="text-[10px] font-mono uppercase tracking-widest text-dim block mb-3">
            INVESTIGATION LOG
          </span>
          <div className="border border-line bg-panel rounded divide-y divide-line">
            {audit.map((a) => {
              const ts = a.created_at.slice(11, 19) || a.created_at.slice(0, 19)
              return (
                <div key={a.audit_id} className="px-4 py-2.5 flex items-start gap-4 text-xs font-mono">
                  <span className="text-dim shrink-0 tabular-nums">{ts}</span>
                  <div className="flex flex-col gap-0.5 min-w-0">
                    <span className="text-ink">
                      {a.action}{a.verdict ? ` → ${a.verdict.toUpperCase()}` : ''}
                    </span>
                    <span className="text-dim truncate">{a.reason}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
