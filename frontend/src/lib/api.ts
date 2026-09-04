const BASE = import.meta.env.PROD ? '' : (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000')

export type Status = 'CLEARED' | 'BLOCKED' | 'HUMAN_CONTEXT' | 'PENDING'

export interface DisputeSummary {
  dispute_id: string
  order_id: string
  customer_id: string
  status: Status
  updated_at: string
  claim_count: number
  claim_summary: string | null
  cited_source: string | null
  contradictions: number
  systems_checked: string[]
}

export interface Claim {
  claim_id: string
  dispute_id: string
  claim_type: string
  asserted_value: string
  cited_source: string
  cited_record: string
  confidence: number
}

export interface SourceRecord { source: string; record_id: string; field: string; value: unknown }

export interface Verdict {
  verdict_id: string
  dispute_id: string
  claim_id: string
  verdict: 'supported' | 'contradicted' | 'insufficient_evidence'
  verification_method: string
  reason: string
  source_records: SourceRecord[]
  created_at: string
}

export interface HumanAttestation {
  attestation_id: string
  dispute_id: string
  claim_id: string
  question: string
  answer: string
  note: string | null
  submitted_by: string
  created_at: string
}

export interface DisputeDetail {
  dispute_id: string
  order_id: string
  customer_id: string
  narrative: string
  status: Status
  created_at: string
  updated_at: string
  claims: Claim[]
  verdicts: Verdict[]
  human_attestations: HumanAttestation[]
}

export interface Witnesses {
  razorpay: Record<string, unknown> | null
  shopify: Record<string, unknown> | null
  shiprocket: Record<string, unknown> | null
  tally: Record<string, unknown>[]
}

export interface AuditEntry {
  audit_id: string
  dispute_id: string
  claim_id: string | null
  action: string
  verdict: string | null
  reason: string
  source_record_ids: string[]
  verification_method: string | null
  created_at: string
}

export interface Metrics { total: number; CLEARED: number; BLOCKED: number; HUMAN_CONTEXT: number; PENDING: number }

export interface Evaluation {
  dataset: { total: number; contradictory: number; clean: number }
  confusion_matrix: { true_positive: number; true_negative: number; false_positive: number; false_negative: number }
  metrics: {
    precision: number; recall: number; f1: number
    automatic_decision_accuracy: number; false_positive_rate: number
    false_positive_count: number; false_negative_count: number
    human_context_routing_accuracy: number | null
    false_automatic_clear_rate: number
  }
  status_counts: Record<string, number>
  missed_cases: { dispute_id: string; expected: string; actual: string; contradiction_class: string | null; reason: string }[]
  performance: { seconds: number; disputes_per_second: number | null }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers || {}) },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${path}: ${body}`)
  }
  return res.json()
}

export const api = {
  health: () => req<{ status: string; disputes_seeded: number; llm_mode: string }>('/api/health'),
  listDisputes: () => req<DisputeSummary[]>('/api/disputes'),
  getDispute: (id: string) => req<DisputeDetail>(`/api/disputes/${id}`),
  getWitnesses: (id: string) => req<Witnesses>(`/api/disputes/${id}/witnesses`),
  getAudit: (id: string) => req<AuditEntry[]>(`/api/disputes/${id}/audit`),
  getMetrics: () => req<Metrics>('/api/metrics'),
  verifyOne: (id: string) => req(`/api/verify/${id}`, { method: 'POST' }),
  verifyAll: () => req('/api/verify-all', { method: 'POST' }),
  injectContradiction: (orderId: string, contradictionType: string) =>
    req<{ order_id: string; dispute_id: string; contradiction_type: string; steps: string[]; new_status: Status }>(
      `/api/chaos/inject-contradiction/${orderId}`,
      { method: 'POST', body: JSON.stringify({ contradiction_type: contradictionType }) },
    ),
  resetDemo: () => req<{ reset: boolean }>('/api/reset-demo', { method: 'POST' }),
  submitAttestation: (body: { dispute_id: string; claim_id: string; question: string; answer: string; note?: string }) =>
    req<{ attestation_id: string; recorded: boolean }>('/api/human-attestation', {
      method: 'POST', body: JSON.stringify(body),
    }),
  getEvaluation: () => req<Evaluation>('/api/evaluation'),
}
