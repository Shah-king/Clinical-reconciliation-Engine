# Clinical Data Reconciliation Engine

> **AI-assisted clinical decision support prototype — NOT a medical device.**

A full-stack system that reconciles conflicting medication records across healthcare
data sources using deterministic scoring and LLM explanatory reasoning.

---

## How to Run Locally

### Prerequisites

- Python 3.11+
- Node.js 18+
- A free Google Gemini API key from [aistudio.google.com/apikey](https://aistudio.google.com/apikey)

### 1 — Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Open .env and set:
#   GEMINI_API_KEY=<your key from aistudio.google.com/apikey>
#   API_KEY=<any hex string, e.g. run: python -c "import secrets; print(secrets.token_hex(32))">

# Start server
uvicorn app.main:app --reload --port 8000
```

> To enable interactive API docs at http://localhost:8000/docs, set `DEBUG=true` in `.env`.

### 2 — Frontend

```bash
cd frontend
cp .env.example .env
# Open .env and set VITE_API_KEY to the same value as API_KEY in backend/.env

npm install
npm run dev
```

Dashboard → http://localhost:5173

### 3 — Tests

```bash
cd backend
pytest tests/ -v
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/reconcile/medication` | Reconcile conflicting medication records — returns winner, confidence score, AI reasoning |
| `POST` | `/api/validate/data-quality` | Score a patient record across 4 quality dimensions (0–100) |
| `POST` | `/api/reconcile/decision` | Record a clinician approve/reject decision on a reconciliation result |
| `GET`  | `/health` | Liveness probe |

All endpoints require an `x-api-key` header matching the `API_KEY` in `.env`.

### Example: Reconcile Medication

```bash
curl -X POST http://localhost:8000/api/reconcile/medication \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{
    "patient_context": {
      "patient_id": "P001",
      "age": 67,
      "egfr": 45,
      "diagnoses": ["Type 2 Diabetes", "Hypertension"],
      "allergies": []
    },
    "sources": [
      {
        "source_id": "EHR-001",
        "source_name": "Hospital EHR",
        "reliability": "high",
        "recorded_at": "2024-10-15T00:00:00Z",
        "medication_name": "Metformin",
        "dose_mg": 1000,
        "frequency": "twice daily",
        "route": "oral",
        "pharmacy_confirmed": false
      },
      {
        "source_id": "PC-002",
        "source_name": "Primary Care",
        "reliability": "high",
        "recorded_at": "2025-01-20T00:00:00Z",
        "medication_name": "Metformin",
        "dose_mg": 500,
        "frequency": "twice daily",
        "route": "oral",
        "pharmacy_confirmed": false
      },
      {
        "source_id": "PH-003",
        "source_name": "Pharmacy",
        "reliability": "medium",
        "recorded_at": "2025-01-25T00:00:00Z",
        "medication_name": "Metformin",
        "dose_mg": 1000,
        "frequency": "daily",
        "route": "oral",
        "pharmacy_confirmed": true
      }
    ]
  }'
```

---

## LLM API Choice: Google Gemini

**Model used:** `gemini-2.5-flash`

**Why Gemini over OpenAI:**

- **Free tier** — Gemini API via AI Studio is free (15 RPM, 1500 RPD) with no credit card required. OpenAI requires a paid account from the first request.
- **Sufficient capability** — For explanatory reasoning on structured clinical context, a mid-tier model is more than adequate. The LLM never makes decisions; it explains them.
- **JSON output mode** — Gemini supports `response_mime_type: application/json` which reduces prompt engineering overhead for structured outputs.
- **Google ecosystem** — The `google-genai` SDK is actively maintained and designed for this use case.

**Note:** The LLM is used only for the `reasoning` field and `clinical_safety_check` assessment. The medication selection is 100% deterministic. If Gemini is unavailable, the system falls back gracefully and returns the deterministic result with `clinical_safety_check: UNKNOWN`.

---

## Key Design Decisions and Trade-offs

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full architecture decisions document.

**Summary of critical decisions:**

| Decision | Rationale |
|---|---|
| LLM explains, never decides | Auditability and safety — deterministic results are reproducible and do not hallucinate |
| Deterministic weighted scoring | 4-factor model (recency 35%, reliability 30%, clinical 25%, pharmacy 10%) is interpretable and clinician-auditable |
| In-memory cache (SHA-256 keyed) | Zero infrastructure for a prototype; same-request deduplication works without Redis |
| API key auth over OAuth2 | Right-sized for an internal prototype; easily swappable |
| Pydantic v2 for all I/O | Strict validation at system boundary prevents garbage-in/garbage-out |
| Graceful LLM fallback | System never crashes on LLM failure — deterministic result is always returned |

---

## What I'd Improve With More Time

- **Persistent audit log** — Replace in-memory decision store with an append-only database table (SQLite → PostgreSQL) so approved/rejected decisions survive restarts
- **Drug-drug interaction detection** — Query RxNorm / OpenFDA APIs to flag dangerous co-prescriptions
- **FHIR R4 ingestion** — Accept `MedicationStatement` and `MedicationRequest` resources directly, not just the internal flat format
- **Patient allergy cross-check** — Validate the reconciled medication against the patient's documented allergies
- **React Query / SWR** — Replace the hand-rolled `useApi` hook with proper cache invalidation and optimistic updates
- **OpenTelemetry tracing** — Track LLM call latency, cache hit rate, and scoring distribution per request
- **Role-based access** — Prescriber, pharmacist, and admin roles with different permitted actions
- **Multi-process cache** — Redis or Memcached to share the response cache across uvicorn workers

---

## Estimated Time Spent

| Phase | Time |
| Backend API + scoring engine | ~3 hours |
| LLM integration + prompt engineering | ~3 hours |
| Frontend dashboard | ~2 hours |
| Production hardening (rate limiting, security headers, auth) | ~1 hours |
| PyHealth data adapter | ~0.5 hours |
| Testing | ~0.5 hours |
| **Total** | **~11 hours** |

---

## Project Structure

```
clinical-reconciliation/
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI route handlers
│   │   ├── auth/          # API key authentication
│   │   ├── middleware/    # Rate limiting
│   │   ├── models/        # Pydantic v2 request/response models
│   │   ├── services/      # Business logic (engine, LLM, cache)
│   │   └── utils/         # Scoring helpers, validators, PyHealth adapter
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/    # ConfidenceBar, QualityChart, SafetyBadge
│   │   ├── hooks/         # useApi
│   │   ├── pages/         # ReconciliationPage, DataQualityPage
│   │   └── utils/         # api.js fetch client
│   ├── .env.example
│   └── package.json
├── ARCHITECTURE.md
└── README.md
```
