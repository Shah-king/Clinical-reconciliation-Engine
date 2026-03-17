import React from "react";

function barColor(score) {
  if (score >= 80) return "#16a34a";
  if (score >= 50) return "#d97706";
  return "#dc2626";
}

const LABELS = {
  completeness: "Completeness",
  accuracy: "Accuracy",
  timeliness: "Timeliness",
  clinical_plausibility: "Plausibility",
};

export default function QualityChart({ breakdown }) {
  return (
    <div style={{ marginTop: 8 }}>
      {Object.entries(LABELS).map(([key, label]) => {
        const val = Math.round(breakdown[key] ?? 0);
        return (
          <div className="chart-bar-row" key={key}>
            <span className="chart-bar-label">{label}</span>
            <div className="chart-bar-track">
              <div
                className="chart-bar-fill"
                style={{ width: `${val}%`, background: barColor(val) }}
              />
            </div>
            <span className="chart-bar-val">{val}</span>
          </div>
        );
      })}
    </div>
  );
}
