/**
 * Thin API client — uses Fetch API only, no axios.
 * All functions throw on non-2xx responses.
 */

const API_KEY = import.meta.env.VITE_API_KEY || "dev-key-change-in-production";
const BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "x-api-key": API_KEY,
      ...(options.headers ?? {}),
    },
  });

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch (_) {}
    throw new Error(detail);
  }

  return res.json();
}

export function reconcileMedication(payload) {
  return request("/reconcile/medication", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function validateDataQuality(payload) {
  return request("/validate/data-quality", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitDecision(payload) {
  return request("/reconcile/decision", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
