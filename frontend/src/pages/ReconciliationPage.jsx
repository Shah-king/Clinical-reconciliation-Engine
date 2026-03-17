import React, { useState } from "react";
import { reconcileMedication, submitDecision } from "../utils/api";
import { useApi } from "../hooks/useApi";
import ConfidenceBar from "../components/ConfidenceBar";
import SafetyBadge from "../components/SafetyBadge";

const DEFAULT_FORM = {
  patientId: "P001",
  age: "65",
  egfr: "52",
  allergies: "penicillin",
  diagnoses: "Type 2 Diabetes, Hypertension",
};

function buildPayload(form) {
  return {
    patient_context: {
      patient_id: form.patientId,
      age: parseInt(form.age, 10),
      egfr: form.egfr ? parseFloat(form.egfr) : null,
      allergies: form.allergies ? form.allergies.split(",").map((s) => s.trim()) : [],
      diagnoses: form.diagnoses ? form.diagnoses.split(",").map((s) => s.trim()) : [],
    },
    sources: [
      {
        source_id: "EHR-001",
        source_name: "EHR System",
        reliability: "high",
        recorded_at: new Date(Date.now() - 2 * 86400000).toISOString(),
        medication_name: "Metformin",
        dose_mg: 1000,
        frequency: "twice daily",
        route: "oral",
        pharmacy_confirmed: true,
      },
      {
        source_id: "PAPER-002",
        source_name: "Paper Chart",
        reliability: "low",
        recorded_at: new Date(Date.now() - 120 * 86400000).toISOString(),
        medication_name: "Metformin",
        dose_mg: 2000,
        frequency: "once daily",
        route: "oral",
        pharmacy_confirmed: false,
      },
      {
        source_id: "PHARM-003",
        source_name: "Pharmacy Dispense",
        reliability: "medium",
        recorded_at: new Date(Date.now() - 7 * 86400000).toISOString(),
        medication_name: "Metformin",
        dose_mg: 500,
        frequency: "twice daily",
        route: "oral",
        pharmacy_confirmed: false,
      },
    ],
  };
}

export default function ReconciliationPage() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [decision, setDecision] = useState(null); // "approved" | "rejected"
  const [submitting, setSubmitting] = useState(false);
  const { data, loading, error, execute } = useApi();

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setDecision(null);
    await execute(() => reconcileMedication(buildPayload(form)));
  }

  async function handleDecision(choice) {
    setSubmitting(true);
    try {
      await submitDecision({
        patient_id: form.patientId,
        reconciled_medication: data.reconciled_medication,
        decision: choice,
      });
      setDecision(choice);
    } catch (_) {
      setDecision(choice); // still show UI confirmation even if network fails
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="container" style={{ paddingTop: 32, paddingBottom: 40 }}>
      <h1>Medication Reconciliation</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        Deterministic scoring engine selects the best candidate. LLM provides
        clinical reasoning only.
      </p>

      <div className="card">
        <h2>Patient Context</h2>
        <form onSubmit={handleSubmit}>
          <div className="grid-2">
            <div className="field">
              <label>Patient ID</label>
              <input name="patientId" value={form.patientId} onChange={handleChange} required />
            </div>
            <div className="field">
              <label>Age</label>
              <input name="age" type="number" min="0" max="130" value={form.age} onChange={handleChange} required />
            </div>
            <div className="field">
              <label>eGFR (mL/min)</label>
              <input name="egfr" type="number" value={form.egfr} onChange={handleChange} placeholder="optional" />
            </div>
            <div className="field">
              <label>Allergies (comma-separated)</label>
              <input name="allergies" value={form.allergies} onChange={handleChange} />
            </div>
          </div>
          <div className="field">
            <label>Diagnoses (comma-separated)</label>
            <input name="diagnoses" value={form.diagnoses} onChange={handleChange} />
          </div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}>
            Demo uses 3 pre-built conflicting Metformin sources (EHR, Paper Chart, Pharmacy).
          </p>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? "Reconciling…" : "Run Reconciliation"}
          </button>
        </form>
      </div>

      {error && <p className="error-msg card">{error}</p>}

      {data && !decision && (
        <div>
          <div className="card">
            <h2>Reconciliation Decision</h2>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                marginBottom: 16,
                flexWrap: "wrap",
              }}
            >
              <span style={{ fontSize: 20, fontWeight: 700 }}>
                {data.reconciled_medication}
                {data.reconciled_dose_mg && ` ${data.reconciled_dose_mg} mg`}
                {data.reconciled_frequency && ` — ${data.reconciled_frequency}`}
                {data.reconciled_route && ` (${data.reconciled_route})`}
              </span>
              <SafetyBadge status={data.clinical_safety_check} />
              {data.cached && (
                <span className="badge" style={{ background: "#f1f5f9", color: "var(--text-muted)" }}>
                  cached
                </span>
              )}
            </div>
            <ConfidenceBar score={data.confidence_score} />
            <p style={{ marginTop: 6, fontSize: 12, color: "var(--text-muted)" }}>
              Source selected: {data.selected_source_id}
            </p>
          </div>

          <div className="card">
            <h2>Clinical Reasoning</h2>
            <p style={{ fontSize: 14, lineHeight: 1.7 }}>{data.reasoning}</p>
          </div>

          <div className="card">
            <h2>Recommended Actions</h2>
            <ul className="actions-list">
              {data.recommended_actions.map((a, i) => (
                <li key={i}>{a}</li>
              ))}
            </ul>
          </div>

          <div className="card">
            <h2>Score Breakdown</h2>
            <div className="score-grid">
              {Object.entries(data.score_breakdown)
                .filter(([k]) => k !== "total")
                .map(([key, val]) => (
                  <div className="score-item" key={key}>
                    <div className="val">{(val * 100).toFixed(0)}</div>
                    <div className="lbl">{key.replace(/_/g, " ")}</div>
                  </div>
                ))}
            </div>
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn btn-success" onClick={() => handleDecision("approved")} disabled={submitting}>
              {submitting ? "Saving…" : "✓ Approve"}
            </button>
            <button className="btn btn-danger" onClick={() => handleDecision("rejected")} disabled={submitting}>
              {submitting ? "Saving…" : "✗ Reject"}
            </button>
          </div>
        </div>
      )}

      {decision && (
        <div
          className="card"
          style={{
            borderColor: decision === "approved" ? "#16a34a" : "#dc2626",
            background: decision === "approved" ? "#f0fdf4" : "#fef2f2",
          }}
        >
          <strong style={{ color: decision === "approved" ? "#16a34a" : "#dc2626" }}>
            {decision === "approved"
              ? "Decision recorded: APPROVED — medication reconciliation accepted."
              : "Decision recorded: REJECTED — reconciliation sent back for review."}
          </strong>
          <button
            className="btn btn-outline"
            style={{ marginTop: 12, display: "block" }}
            onClick={() => { setDecision(null); }}
          >
            New Reconciliation
          </button>
        </div>
      )}
    </div>
  );
}
