import React, { useState } from "react";
import ReconciliationPage from "./pages/ReconciliationPage";
import DataQualityPage from "./pages/DataQualityPage";

export default function App() {
  const [tab, setTab] = useState("reconcile");

  return (
    <>
      <nav>
        <div className="nav-inner">
          <span className="brand">⚕ ClinReconcile</span>
          <button
            className={`nav-tab ${tab === "reconcile" ? "active" : ""}`}
            onClick={() => setTab("reconcile")}
          >
            Reconciliation
          </button>
          <button
            className={`nav-tab ${tab === "quality" ? "active" : ""}`}
            onClick={() => setTab("quality")}
          >
            Data Quality
          </button>
        </div>
      </nav>

      {tab === "reconcile" ? <ReconciliationPage /> : <DataQualityPage />}

      <footer style={{
        textAlign: "center", padding: "16px 0", fontSize: 12,
        color: "var(--text-muted)", borderTop: "1px solid var(--border)",
        marginTop: 20
      }}>
        Clinical Reconciliation Engine — AI-assisted decision support prototype.
        NOT a medical device. Not for clinical use.
      </footer>
    </>
  );
}
