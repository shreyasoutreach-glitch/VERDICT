# VERIDICT

**AI can write the claim. VERIDICT checks whether reality agrees.**

A pre-submission verification layer for AI-generated financial claims. It takes
an evidence packet written by an upstream AI agent (a dispute responder, a
recovery agent, anything that asserts something about money and cites a
source), cross-examines every atomic claim in it against every connected
merchant system — not just the one it cited — and decides: **CLEARED**,
**BLOCKED**, or **HUMAN_CONTEXT**.

---

## The problem

An AI-generated financial claim can be fluent, plausible, grounded in a real
source, correctly cited — and still be globally false. Not because the model
hallucinated. Because the source it cited is only one fragment of the
merchant's reality.

The flagship case in this repo (`VER-001`, order `ORDER-4821`):

> "The order was delivered within the promised delivery window, per Shiprocket
> record SHIP-4821."

Shiprocket genuinely supports this: the item **was** delivered, and the record
cited is real. But Shopify's own order record shows the delivery was promised
for August 10, and Shiprocket's own timestamp shows it actually arrived
August 14. The claim is grounded and false at the same time. VERIDICT's job is
to notice that, cite the exact two records that disagree, and block the claim
before it reaches a card network — while also knowing when it *can't*
establish something, and asking a human instead of guessing.

## Why existing systems don't cover this

- **Chargeflow, Justt** (and Razorpay's own Dispute Responder Agent, shipped
  in Agent Studio, March 2026) *generate* evidence. None of them publish a
  distinct step that checks a generated claim against systems it didn't cite.
- **General LLM-output grounding / hallucination-detection tooling** checks a
  claim against the one document it was given. It isn't built for card-network
  evidence semantics, and it has no notion of a merchant's *other* systems
  possibly disagreeing with the one that was cited.
- Neither category distinguishes a **system fact** (directly observable, e.g.
  `shiprocket.delivered_date`), an **AI interpretation** (a conclusion drawn
  from those facts, e.g. "delivered on time"), and **human context**
  (something real that happened but that no system recorded, e.g. *why* a
  delivery attempt failed). VERIDICT treats these as three different kinds of
  truth and never lets one quietly become another — a human explaining a
  contradiction does not get to overturn it; see `POST /api/human-attestation`,
  which returns `409` if you try.

## What this is not

Not a chargeback responder, not a generic fraud detector, not an "AI
governance dashboard," not a document-verification tool, not a chatbot. It
sits **one layer underneath** an evidence-generating agent, as a gate the
claim has to pass before it becomes a submission.

---

## Architecture

```
AI CLAIM (structured: claim_type, asserted_value, cited_source, cited_record)
   │
   ▼
CLAIM EXTRACTOR            (app/verifier/claim_extractor.py)
   │
   ▼
SOURCE RESOLVER            (app/verifier/source_resolver.py)
   │   fetches ALL four systems for the order, not just the cited one;
   │   flags a citation that doesn't exist in any system at all
   ▼
        Is this claim type structured (date/amount/status/id)?
          /                                          \
        YES                                           NO
         │                                             │
         ▼                                             ▼
DETERMINISTIC VERIFICATION                    LLM / DEMO ADJUDICATOR
(app/verifier/deterministic.py                (app/verifier/llm_adjudicator.py
 + temporal.py — dates, amounts,                / demo_adjudicator.py)
 statuses, counts, entity resolution.           Only for genuinely soft claims
 Zero model calls. Zero network calls.)         (service quality, refusal intent).
         │                                      Structured JSON out; any
         │                                      citation outside the supplied
         │                                      record set is rejected, not
         │                                      trusted.
         └──────────────────┬──────────────────┘
                             ▼
                      VERDICT ENGINE
              supported → CLEARED
              contradicted → BLOCKED
              insufficient_evidence → HUMAN_CONTEXT
                             │
                             ▼
                      AUDIT TRAIL  (every verdict + every human
                                    attestation + every chaos injection)
```

**Design principle, enforced by the code, not just stated:** AI does not
decide what is true. AI helps reason about evidence where code alone can't
(soft, subjective claims). The verdict engine decides, from evidence and
explicit rules, everywhere else. See `deterministic.DETERMINISTIC_CLAIM_TYPES`
— 7 of the 8 claim types in this system never touch a model.

## Four systems that don't talk to each other

SQLite tables, deliberately never joined in SQL by the verifier — each is
resolved independently the way a real cross-system client would have to:

- `razorpay_payments` — the payment gateway's record
- `shopify_orders` — the commerce record (promised delivery, returns)
- `shiprocket_shipments` — the fulfillment record (actual delivery, scan events)
- `tally_ledger` — the accounting ledger (sales, refunds)

Plus VERIDICT's own state: `disputes`, `claims`, `verdicts`, `audit_log`,
`human_attestations`.

## The 8 contradiction classes seeded

| Class | What disagrees |
|---|---|
| `delivery_window` | Shiprocket's actual delivery date vs. Shopify's promised date (the flagship) |
| `amount_mismatch` | Razorpay's captured amount vs. Tally's sale entry |
| `payment_status` | Razorpay's stale status vs. a refund entry already in Tally |
| `return_chronology` | A return recorded before the courier's own delivery timestamp |
| `refund_amount` | A partial ledger refund vs. the full original payment |
| `missing_ledger_entry` | Razorpay says refunded; Tally has no matching entry at all |
| `duplicate_refund` | Two ledger refund entries for one order |
| `customer_order_mismatch` | The cited record belongs to a real, different customer |

Plus two flavors of legitimate uncertainty, kept structurally distinct from
contradictions: a **dangling citation** (the agent cited a record ID that
doesn't exist anywhere) and a **structurally unknowable claim**
(`delivery_refusal_intent` — no table anywhere records customer intent,
regardless of how complete the data is).

---

## Evaluation methodology

60 synthetic disputes, fixed random seed (`SEED = 1729` in `app/seed.py`): 12
deliberately contradictory across the 8 classes above, 48 clean (including 6
that legitimately require human context). Ground truth
(`ground_truth_contradiction`, `ground_truth_needs_context`) is written at
seed time and **never read by the verification pipeline** — only by
`app/evaluation.py`, which the pipeline doesn't import. Precision, recall, F1,
accuracy, false-positive rate, human-context routing accuracy, and false
automatic-clear rate are computed fresh from the current database state on
every call to `GET /api/evaluation` — nothing is cached or hardcoded, and the
frontend's Evaluation screen shows misses if there are any.

**On this dataset, the current build achieves 12/12 recall and 0 false
positives.** That's an honest result of fixing a real bug during
development (see the `customer_identity` citation-check fix in
`app/verifier/pipeline.py` — the generic dangling-citation check was
initially, incorrectly, also firing on cross-order citations before it was
scoped correctly), not of tuning the dataset to guarantee it. It should be
read as "the deterministic core is reliable on a 60-case synthetic set with 8
contradiction classes," not as a claim about real-world recall on messier,
more adversarial, or more heavily LLM-adjudicated data — a dataset with more
soft claims and fewer of the sharply-structured contradiction classes here
would show a lower number, and that's expected, not a regression.

**Note on chaos injection and evaluation:** injecting a contradiction changes
the live database but does not retroactively update that dispute's seeded
ground-truth label. Until you call `reset-demo`, the evaluation screen will
honestly report the injected case as a "false positive" relative to the
*original* seed — which is correct: the evaluation harness has no way to know
you deliberately broke a case, and it isn't supposed to guess.

---

## How to run

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# First request auto-seeds and auto-verifies 60 disputes. Nothing else to run.

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

No Docker, no Postgres, no Redis, no paid service required.

### Enabling OpenAI

```bash
cp .env.example backend/.env
# edit backend/.env: set OPENAI_API_KEY=sk-...
export OPENAI_API_KEY=sk-...   # or export LLM_MODE=openai explicitly
uvicorn app.main:app --reload --port 8000
```

With no key set, `LLM_MODE` resolves to `demo` automatically — the app is
fully functional either way. Only 3 of the 60 seeded claim types
(`service_quality`, `fulfillment_quality`, `customer_request_fulfilled`, and
`delivery_refusal_intent`) ever reach the adjudicator; everything else is
resolved deterministically regardless of which mode is active. The `LLM:
live` / `LLM: demo mode` badge in the header reflects the real value of
`GET /api/health`, not a guess.

### Tests

```bash
cd backend
.venv/bin/pytest -q
# 23 passed
```

Covers: clean delivery clears, the flagship contradiction, amount mismatch,
payment-status mismatch, missing/dangling evidence, human-context routing
accuracy, human-attestation persistence (and its `409` guard against
overriding a CONTRADICTED verdict), live chaos injection flipping a real row,
reset-demo restoring deterministic state, duplicate-injection idempotency,
evaluation-metric computation, and LLM-adjudicator citation validation — plus
an HTTP-level integration suite (`tests/test_api.py`) against the real FastAPI
app, including the exact inject → verify → CLEARED-becomes-BLOCKED flow.

### Example API calls

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/disputes/VER-001
curl http://localhost:8000/api/disputes/VER-001/witnesses
curl -X POST http://localhost:8000/api/chaos/inject-contradiction/ORDER-1012 \
  -H "Content-Type: application/json" -d '{"contradiction_type":"delivery_window"}'
curl http://localhost:8000/api/evaluation
curl -X POST http://localhost:8000/api/reset-demo
```

---

## Demo flow

1. Open `http://localhost:5173` — the Docket. Real counts from the backend,
   polling every 2 seconds.
2. Click `VER-001` — the flagship. AI testimony, four witness cards
   (Shiprocket examined and highlighted, Shopify examined and highlighted),
   the contradiction, the exact two fields and values, the audit block.
3. Back on the Docket, open **Chaos Lab**, pick any currently-`CLEARED` order,
   inject a `delivery_window` contradiction. Watch the row flip — that's a
   real `UPDATE` to `shiprocket_shipments.delivered_date`, a real regenerated
   claim, a real re-run of the pipeline.
4. Open a `HUMAN_CONTEXT` case. Submit an answer. Then try (via `curl`, the
   UI won't offer it) to attach human context to `VER-001` instead — `409`,
   on purpose.
5. Open **Evaluation**. Real precision/recall/F1, real confusion matrix, and
   — if you injected chaos and haven't reset — an honest false positive
   sitting right there.
6. **Reset demo** to return to the deterministic baseline for the next run.

---

## Known limitations / what's synthetic

- All four "merchant systems" are SQLite tables in one process, not real
  Shopify/Shiprocket/Tally/Razorpay integrations. The verifier is written as
  if they were separate services (independent resolution, no SQL joins across
  them) specifically so that swapping a table for a real API client would not
  require touching `deterministic.py` or `pipeline.py`.
- 60 disputes, fixed seed — not a claim about performance at production
  volume or against adversarially-phrased evidence.
- The OpenAI code path (`app/verifier/llm_adjudicator.py`) is written to the
  real API (structured JSON output, citation validation, safe-fallback on any
  failure) but could not be exercised against the live OpenAI API from the
  sandbox this was built in — `api.openai.com` wasn't reachable from that
  environment. The demo-mode path was exercised extensively and is what the
  60-case evaluation above reflects. If you run this with a real
  `OPENAI_API_KEY`, treat the first few soft-claim results as worth a manual
  spot-check.
- Human attestations are stored and auditable but nothing currently *acts* on
  them beyond recording — no downstream workflow re-triggers because a human
  answered.
- This is a prototype demonstrating an architectural primitive, not
  production-ready infrastructure. No auth, no multi-tenancy, no rate
  limiting, no production-scale claims are made anywhere in this repo.

## Repository structure

```
veridict/
├── backend/
│   ├── app/
│   │   ├── main.py              FastAPI app, all endpoints
│   │   ├── db.py                schema, connection handling
│   │   ├── seed.py              deterministic 60-dispute generator
│   │   ├── evidence_generator.py the naive upstream "Dispute Responder"
│   │   ├── evaluation.py        precision/recall/F1 against held-out ground truth
│   │   ├── chaos.py             live injection endpoints' logic
│   │   ├── schemas.py           Pydantic request models
│   │   └── verifier/
│   │       ├── claim_extractor.py
│   │       ├── source_resolver.py
│   │       ├── temporal.py
│   │       ├── deterministic.py  the engineering core
│   │       ├── llm_adjudicator.py
│   │       ├── demo_adjudicator.py
│   │       └── pipeline.py       orchestrates all of the above
│   ├── tests/
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/      Docket, DisputeDetail, EvaluationPage
│       ├── components/ StatusBadge, WitnessCard, AuditBlock, ChaosLab, HumanWitnessPanel
│       └── lib/api.ts  typed client
├── .env.example
└── README.md (this file)
```
