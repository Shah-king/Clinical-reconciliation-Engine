# Architecture Decisions

> Clinical Data Reconciliation Engine — design rationale and trade-offs.

---

## 1. LLM Is Explanatory Only — Never the Decision-Maker

**Decision:** The deterministic scoring engine selects the winning medication record.
The LLM receives the already-made decision and returns a clinical reasoning
explanation + safety assessment. It cannot override or change the selection.

**Why:** Clinical decision support systems must be auditable and reproducible.
An LLM making the selection would produce different answers across runs (even at
low temperature), could hallucinate clinical facts, and cannot be traced back to
an accountable rule. A deterministic engine produces a result that a clinician can
inspect, challenge, and hold accountable.

**Enforced architecturally:** `ReconciliationEngine._select_winner()` runs before
`LLMService.get_reasoning()` is called. The LLM prompt explicitly states:
*"The reconciliation decision has ALREADY been made… You must NOT override or
second-guess that decision."*

**Trade-off:** The LLM explanation may occasionally conflict with the numeric
winner (e.g., explain why source B was chosen when source A actually scored higher).
This is acceptable for a prototype and is mitigated by passing the full score
breakdown in the prompt.

---

## 2. Weighted Scoring Model (4 Factors)

**Decision:** Score each source record on four factors with fixed weights:

| Factor | Weight | Rationale |
|---|---|---|
| Recency | 35% | More recent records are more likely to reflect the current regimen |
| Source reliability | 30% | EHR and inpatient records have stronger provenance than self-reports |
| Clinical appropriateness | 25% | Dose must be plausible given patient age, weight, and eGFR |
| Pharmacy confirmation | 10% | Last dispensed record correlates with actual intake |

**Why:** The weights encode domain knowledge that mirrors how a pharmacist
performs manual reconciliation. The model is fully interpretable — every point in
the confidence score traces back to these four factors. Clinicians can audit and
disagree with any factor individually.

**Trade-off:** Weights are fixed and were not derived from outcome data. A
real deployment would learn weights from historical reconciliation decisions.
The clinical appropriateness check is also limited to eGFR/metformin
contraindication — a production system would consult a formulary or drug database.

---

## 3. Confidence Score from Winner Separation

**Decision:** Confidence = `winner_score − runner_up_score`, clamped to [0, 1],
adjusted upward when sources agree on the medication name.

**Why:** A winning score of 0.85 is meaningless on its own — it could be high
because the record is genuinely authoritative, or because all sources scored
poorly. The *gap* between the top two candidates is a better signal: a 0.3
separation (0.85 vs 0.55) is high confidence; a 0.05 separation (0.82 vs 0.77)
warrants human review.

**Trade-off:** Does not account for the absolute score level. Could be improved
by multiplying separation by the winner's absolute score.

---

## 4. Graceful LLM Fallback

**Decision:** Every LLM call is wrapped in a retry loop (3 attempts, exponential
backoff). On any failure — rate limit, timeout, malformed JSON, network error —
the system returns the deterministic result with:
- `reasoning`: "AI reasoning unavailable — deterministic scoring result retained."
- `clinical_safety_check`: UNKNOWN
- `confidence_score`: reduced by 5 percentage points

**Why:** The LLM adds value but is not load-bearing. A clinician receiving a
result with `UNKNOWN` safety check knows to verify manually. A crash or hung
request is far worse than a degraded response.

**Trade-off:** `UNKNOWN` safety check may cause unnecessary alarm. A future
improvement would add a deterministic safety checker as the fallback (e.g., a
static rule for the eGFR/metformin contraindication already present in the
validators).

---

## 5. In-Memory Cache with SHA-256 Keying

**Decision:** Reconciliation results are cached in a Python dict (process-local)
with a 24-hour TTL. The cache key is the SHA-256 hash of the full JSON-serialised
request body.

**Why:**
- LLM calls have latency (~1–3 seconds) and cost quota. Caching identical
  requests avoids both.
- SHA-256 keying is collision-resistant — a single character difference in the
  request (different patient ID, different source date) produces a completely
  different cache key.
- No infrastructure dependency — useful for a prototype where spinning up Redis
  adds deployment friction.

**Trade-off:** Cache is lost on server restart. In a multi-worker deployment
(multiple uvicorn processes), each worker maintains its own cache — no sharing.
Production would use Redis with a shared TTL.

---

## 6. API Key Authentication (Not OAuth2/JWT)

**Decision:** All endpoints require an `x-api-key` header, compared with
`secrets.compare_digest` (timing-safe) against the `API_KEY` environment variable.

**Why:** For an internal prototype where a single consumer (the React frontend)
calls the API, OAuth2 adds substantial complexity with no security benefit. API key
auth is auditable (keys can be rotated) and the timing-safe comparison prevents
timing attacks.

**Trade-off:** A single shared key means there is no per-user identity or
permissions. The `POST /api/reconcile/decision` endpoint records `patient_id` from
the request body rather than from a verified user identity. Production would
require JWT with role claims (prescriber / pharmacist / admin).

---

## 7. Pydantic v2 for All I/O Validation

**Decision:** Every API request and response is modelled as a Pydantic v2
`BaseModel` with explicit types, validators, and field constraints.

**Why:** Clinical data must be validated at the system boundary — garbage input
produces garbage output. Pydantic v2 provides:
- Automatic type coercion and range checking (e.g., `age: int` rejects strings)
- Custom `model_validator` for derived fields (eGFR backfilled from `recent_labs`)
- Serialisation guarantees for cache key generation

**Trade-off:** Strict validation rejects requests that a lenient API would accept.
Some upstream systems send inconsistent field types (e.g., `"dose_mg": "500mg"`
instead of `500`). A production adapter layer would normalise before Pydantic sees
the data.

---

## 8. Frontend: No Framework Beyond React + Vite

**Decision:** Plain React 18 with Vite. No UI component library (no MUI, no
Tailwind). CSS custom properties for the design system. A hand-rolled `useApi`
hook instead of React Query.

**Why:** The dashboard has exactly two pages and four components. Adding a UI
library or data-fetching framework would impose more boilerplate than it removes
at this scale. The result is ~13 source files with zero unnecessary dependencies.

**Trade-off:** The `useApi` hook has no cache invalidation, no optimistic updates,
and no request deduplication. For a production dashboard with multiple concurrent
users, React Query or SWR would be the first addition.

---

## 9. Prompt Engineering Approach

The LLM prompt is structured in two parts:

**System prompt (fixed, per-service):**
- Establishes the LLM's role as a clinical pharmacist AI
- Explicitly forbids overriding the deterministic decision
- Specifies the required JSON output schema
- Sets `temperature=0.1` for near-deterministic explanations

**User prompt (per-request):**
- Injects patient context: age, eGFR, weight, allergies, diagnoses
- Lists all conflicting sources with their scores and reliability
- States the selected winner and its full score breakdown
- Ends with: *"Provide your clinical reasoning explanation and safety assessment as JSON only."*

The separation prevents the model from confusing its constraints (system) with the
clinical data (user). Passing the score breakdown in the user prompt grounds the
explanation in the actual computation rather than the model's prior beliefs.

**JSON enforcement:** `response_mime_type: application/json` is set in the
`GenerateContentConfig`. This is backed up by the system prompt schema and
a `_parse_response` method that strips markdown fences and falls back on
field-level defaults for any missing keys.
