import { useState } from 'react'
import type { HumanAttestation } from '../lib/api'
import { api } from '../lib/api'

interface Props {
  disputeId: string
  claimId: string
  claimType?: string
  question: string
  existing: HumanAttestation[]
  onSubmitted: () => void
}

const OPTION_MAP: Record<string, string[]> = {
  delivery_refusal_intent: [
    'Customer unavailable at delivery',
    'Courier could not locate address',
    'Customer refused delivery',
    'Merchant-side delay',
    'Other',
    'I don\'t know',
  ],
  service_quality: [
    'Service was satisfactory',
    'Issue was resolved by merchant',
    'Complaint is valid',
    'Other',
    'I don\'t know',
  ],
  fulfillment_quality: [
    'Order was delivered complete',
    'Partial fulfillment',
    'Item was damaged',
    'Wrong item delivered',
    'Other',
    'I don\'t know',
  ],
  customer_request_fulfilled: [
    'Request was fulfilled',
    'Request is still pending',
    'Request was cancelled by customer',
    'Other',
    'I don\'t know',
  ],
}

export default function HumanWitnessPanel({ disputeId, claimId, claimType, question, existing, onSubmitted }: Props) {
  const [selected, setSelected] = useState<string | null>(null)
  const [freeText, setFreeText] = useState('')
  const [note, setNote] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitted, setSubmitted] = useState(false)

  // If already has attestations, show them as evidence objects
  if (existing.length > 0 || submitted) {
    const latest = existing[existing.length - 1]
    return (
      <div className="border border-context/25 bg-context/5 rounded p-6 animate-fade-in">
        <div className="flex items-center gap-2 mb-4">
          <span className="w-2 h-2 rounded-full bg-context" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-context">HUMAN WITNESS</span>
        </div>
        {latest ? (
          <div className="space-y-3">
            <div>
              <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">QUESTION</span>
              <span className="text-sm text-muted">{latest.question}</span>
            </div>
            <div>
              <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">TESTIMONY</span>
              <span className="text-sm font-mono text-ink font-medium">{latest.answer}</span>
            </div>
            {latest.note && (
              <div>
                <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">NOTE</span>
                <span className="text-sm text-muted">{latest.note}</span>
              </div>
            )}
            <div>
              <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-1">SUBMITTED BY</span>
              <span className="text-xs font-mono text-dim">{latest.submitted_by} · {latest.created_at.slice(0, 19).replace('T', ' ')}</span>
            </div>
            <div className="pt-3 mt-3 border-t border-context/20">
              <span className="text-[10px] font-mono text-context tracking-wide">
                CONTEXT RECORDED · THIS IS HUMAN TESTIMONY, NOT AN OBJECTIVE SYSTEM RECORD
              </span>
            </div>
          </div>
        ) : (
          <div className="text-sm text-context font-mono">TESTIMONY SUBMITTED</div>
        )}
      </div>
    )
  }

  const options = claimType ? OPTION_MAP[claimType] : undefined
  const answer = selected === 'Other' ? freeText : (selected || freeText)

  const handleSubmit = async () => {
    if (!answer.trim()) return
    setSubmitting(true)
    try {
      await api.submitAttestation({
        dispute_id: disputeId,
        claim_id: claimId,
        question,
        answer: answer.trim(),
        note: note.trim() || undefined,
      })
      setSubmitted(true)
      onSubmitted()
    } catch (err) {
      console.error('Attestation failed:', err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="border border-context/30 bg-context/5 rounded overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="px-6 py-4 border-b border-context/20">
        <div className="flex items-center gap-2 mb-2">
          <span className="w-2.5 h-2.5 rounded-full bg-context animate-pulse-dot" />
          <span className="text-sm font-mono font-semibold text-context tracking-wide">HUMAN WITNESS REQUIRED</span>
        </div>
        <p className="text-[15px] text-muted leading-relaxed font-serif italic">
          The records are not enough. We need context only a person can provide.
        </p>
      </div>

      <div className="px-6 py-5 space-y-5">
        {/* Question */}
        <div>
          <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-2">QUESTION</span>
          <p className="text-lg text-ink font-medium leading-snug">{question}</p>
        </div>

        {/* Options */}
        {options ? (
          <div className="space-y-2">
            <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-2">SELECT RESPONSE</span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {options.map((opt) => (
                <button
                  key={opt}
                  onClick={() => setSelected(opt)}
                  className={`text-left px-4 py-3 rounded border font-mono text-sm transition-colors ${
                    selected === opt
                      ? 'border-context/50 bg-context/10 text-context'
                      : 'border-line bg-panel text-muted hover:text-ink hover:border-line2'
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
            {selected === 'Other' && (
              <input
                type="text"
                value={freeText}
                onChange={(e) => setFreeText(e.target.value)}
                placeholder="Describe what happened..."
                className="w-full mt-2 px-4 py-2.5 rounded border border-line bg-base text-ink font-mono text-sm placeholder:text-dim focus:border-context/50 focus:outline-none"
              />
            )}
          </div>
        ) : (
          <div>
            <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-2">YOUR RESPONSE</span>
            <input
              type="text"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              placeholder="Describe what happened..."
              className="w-full px-4 py-2.5 rounded border border-line bg-base text-ink font-mono text-sm placeholder:text-dim focus:border-context/50 focus:outline-none"
            />
          </div>
        )}

        {/* Note */}
        <div>
          <span className="text-[9px] font-mono uppercase tracking-widest text-dim block mb-2">ADDITIONAL NOTE (OPTIONAL)</span>
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Any additional context..."
            className="w-full px-4 py-2.5 rounded border border-line bg-base text-ink font-mono text-sm placeholder:text-dim focus:border-context/50 focus:outline-none"
          />
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!answer.trim() || submitting}
          className="w-full py-3 rounded border border-context/30 bg-context/10 text-context font-mono text-sm uppercase tracking-wide hover:bg-context/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {submitting ? 'SUBMITTING...' : 'SUBMIT TESTIMONY'}
        </button>

        {/* Semantic note */}
        <p className="text-[10px] font-mono text-dim text-center tracking-wide">
          HUMAN TESTIMONY PROVIDES CONTEXT · IT CANNOT OVERWRITE OBJECTIVE SYSTEM RECORDS
        </p>
      </div>
    </div>
  )
}
