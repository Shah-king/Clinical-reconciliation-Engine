import React, { useState } from "react";
import { validateDataQuality } from "../utils/api";
import { useApi } from "../hooks/useApi";
import QualityChart from "../components/QualityChart";

const DEFAULT_FORM = {
  patientId: "P001",
  systolicBp: "125",
  diastolicBp: "82",
  heartRate: "74",
  temperatureC: "36.8",
  allergies: "penicillin",
  medications: "Metformin 500mg",
  providerId: "DR001",
  diagnosisCodes: "E11.9",
  recordedDaysAgo: "10",
};

function buildPayload(form) {
  const daysAgo = parseInt(form.recordedDaysAgo || "0", 10);
  const recorded = new Date(Date.now() - daysAgo * 86400000).toISOString();
  return {
    patient_id: form.patientId,
    systolic_bp: form.systolicBp ? parseInt(form.systolicBp, 10) : null,
    diastolic_bp: form.diastolicBp ? parseInt(form.diastolicBp, 10) : null,
    heart_rate: form.heartRate ? parseInt(form.heartRate, 10) : null,
    temperature_c: form.temperatureC ? parseFloat(form.temperatureC) : null,
    allergies: form.allergies ? form.allergies.split(",").map((s) => s.trim()) : null,
    medications: form.medications ? form.medications.split(",").map((s) => s.trim()) : null,
    recorded_at: recorded,
    provider_id: form.providerId || null,
    diagnosis_codes: form.diagnosisCodes
      ? form.diagnosisCodes.split(",").map((s) => s.trim())
      : null,
  };
}

function levelColor(level) {
  if (level === "good") return "#16a34a";
  if (level === "fair") return "#d97706";
  return "#dc2626";
}

function levelBg(level) {
  if (level === "good") return "#f0fdf4";
  if (level === "fair") return "#fffbeb";
  return "#fef2f2";
}

export default function DataQualityPage() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const { data, loading, error, execute } = useApi();

  function handleChange(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e) {
    e.preventDefault();
    await execute(() => validateDataQuality(buildPayload(form)));
  }

  return (
    <div className="container" style={{ paddingTop: 32, paddingBottom: 40 }}>
      <h1>Data Quality Assessment</h1>
      <p style={{ color: "var(--text-muted)", marginBottom: 24 }}>
        Evaluates completeness, accuracy, timeliness, and clinical plausibility.
      </p>

      <div className="card">
        <h2>Patient Record</h2>
        <form onSubmit={handleSubmit}>
          <div className="grid-2">
            <div className="field">
              <label>Patient ID</label>
              <input name="patientId" value={form.patientId} onChange={handleChange} required />
            </div>
            <div className="field">
              <label>Record Age (days ago)</label>
              <input name="recordedDaysAgo" type="number" min="0" value={form.recordedDaysAgo} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Systolic BP (mmHg)</label>
              <input name="systolicBp" type="number" value={form.systolicBp} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Diastolic BP (mmHg)</label>
              <input name="diastolicBp" type="number" value={form.diastolicBp} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Heart Rate (bpm)</label>
              <input name="heartRate" type="number" value={form.heartRate} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Temperature (°C)</label>
              <input name="temperatureC" type="number" step="0.1" value={form.temperatureC} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Provider ID</label>
              <input name="providerId" value={form.providerId} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Diagnosis Codes (ICD-10)</label>
              <input name="diagnosisCodes" value={form.diagnosisCodes} onChange={handleChange} />
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label>Allergies (comma-separated)</label>
              <input name="allergies" value={form.allergies} onChange={handleChange} />
            </div>
            <div className="field">
              <label>Medications (comma-separated)</label>
              <input name="medications" value={form.medications} onChange={handleChange} />
            </div>
          </div>
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? "Evaluating…" : "Evaluate Quality"}
          </button>
        </form>
      </div>

      {error && <p className="error-msg card">{error}</p>}

      {data && (
        <>
          <div
            className="card"
            style={{
              borderColor: levelColor(data.quality_level),
              background: levelBg(data.quality_level),
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div>
                <div style={{ fontSize: 13, color: "var(--text-muted)" }}>Overall Score</div>
                <div
                  style={{
                    fontSize: 48,
                    fontWeight: 800,
                    color: levelColor(data.quality_level),
                    lineHeight: 1.1,
                  }}
                >
                  {Math.round(data.overall_score)}
                </div>
              </div>
              <div>
                <span
                  className="badge"
                  style={{
                    background: levelBg(data.quality_level),
                    color: levelColor(data.quality_level),
                    border: `1px solid ${levelColor(data.quality_level)}`,
                    fontSize: 14,
                    padding: "4px 14px",
                  }}
                >
                  {data.quality_level.toUpperCase()}
                </span>
                <p style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 6 }}>
                  {data.quality_level === "good" && "Record meets quality standards."}
                  {data.quality_level === "fair" && "Record has moderate quality issues."}
                  {data.quality_level === "poor" && "Record has serious quality problems."}
                </p>
              </div>
            </div>
          </div>

          <div className="card">
            <h2>Dimension Scores (0–100)</h2>
            <QualityChart breakdown={data.breakdown} />
          </div>

          {data.issues_detected.length > 0 && (
            <div className="card">
              <h2>Issues Detected ({data.issues_detected.length})</h2>
              <div>
                {data.issues_detected.map((issue, i) => (
                  <div className="issue-item" key={i}>
                    <div className={`issue-dot dot-${issue.severity}`} />
                    <div>
                      <strong style={{ textTransform: "capitalize" }}>{issue.severity}</strong>
                      {" — "}
                      {issue.message}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.issues_detected.length === 0 && (
            <div className="card" style={{ borderColor: "#16a34a", background: "#f0fdf4" }}>
              <strong style={{ color: "#16a34a" }}>No issues detected — record passes all quality checks.</strong>
            </div>
          )}
        </>
      )}
    </div>
  );
}
