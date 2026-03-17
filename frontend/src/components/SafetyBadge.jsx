import React from "react";

const CLASS_MAP = {
  SAFE: "badge badge-safe",
  CAUTION: "badge badge-caution",
  UNSAFE: "badge badge-unsafe",
  UNKNOWN: "badge badge-unknown",
};

export default function SafetyBadge({ status }) {
  return (
    <span className={CLASS_MAP[status] ?? CLASS_MAP.UNKNOWN}>
      {status ?? "UNKNOWN"}
    </span>
  );
}
