import React from "react";

function getColor(value) {
  if (value >= 0.8) return "#16a34a";
  if (value >= 0.5) return "#d97706";
  return "#dc2626";
}

export default function ConfidenceBar({ score }) {
  const pct = Math.round(score * 100);
  const color = getColor(score);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 13, color: "var(--text-muted)" }}>Confidence</span>
        <span style={{ fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div className="progress-bar-track">
        <div
          className="progress-bar-fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
    </div>
  );
}
