"""Pure deterministic scoring helpers — no side effects, no I/O."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Final

from app.models.reconcile_models import MedicationRecord, SourceReliability

# Factor weights must sum to 1.0
WEIGHT_RECENCY: Final[float] = 0.35
WEIGHT_RELIABILITY: Final[float] = 0.30
WEIGHT_CLINICAL: Final[float] = 0.25
WEIGHT_PHARMACY: Final[float] = 0.10

RELIABILITY_MAP: dict[SourceReliability, float] = {
    SourceReliability.HIGH: 1.0,
    SourceReliability.MEDIUM: 0.6,
    SourceReliability.LOW: 0.2,
}

# Maximum age considered for recency scoring (days)
MAX_AGE_DAYS: Final[int] = 365


def score_recency(recorded_at: datetime) -> float:
    """Return 0–1 where 1 = very recent, 0 = older than MAX_AGE_DAYS."""
    now = datetime.now(timezone.utc)
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - recorded_at).total_seconds() / 86_400)
    return max(0.0, 1.0 - age_days / MAX_AGE_DAYS)


def score_reliability(reliability: SourceReliability) -> float:
    """Map source reliability enum to 0–1 score."""
    return RELIABILITY_MAP.get(reliability, 0.4)


def score_pharmacy_confirmation(confirmed: bool) -> float:
    """Binary score for pharmacy confirmation."""
    return 1.0 if confirmed else 0.0


def score_clinical_appropriateness(
    record: MedicationRecord,
    egfr: float | None,
    age: int,
) -> float:
    """Deterministic clinical plausibility — penalise red flags."""
    score = 1.0
    name = record.medication_name.lower()

    # eGFR-based Metformin penalty
    if "metformin" in name and egfr is not None:
        if egfr < 30:
            score -= 0.80  # contraindicated
        elif egfr < 45:
            score -= 0.40  # dose reduction required

    # Paediatric dose checks (age < 18)
    if age < 18 and record.dose_mg is not None:
        adult_high_dose = 2000.0  # rough adult upper bound
        if record.dose_mg > adult_high_dose:
            score -= 0.50

    # Penalise implausibly large single doses generically
    if record.dose_mg is not None and record.dose_mg > 10_000:
        score -= 0.60

    return max(0.0, min(1.0, score))


def compute_total_score(
    record: MedicationRecord,
    egfr: float | None,
    age: int,
) -> tuple[float, dict[str, float]]:
    """
    Return (total_score, breakdown_dict) for a single MedicationRecord.

    Scores are weighted per the clinical reconciliation spec.
    """
    recency = score_recency(record.recorded_at)
    reliability = score_reliability(record.reliability)
    clinical = score_clinical_appropriateness(record, egfr, age)
    pharmacy = score_pharmacy_confirmation(record.pharmacy_confirmed)

    total = (
        recency * WEIGHT_RECENCY
        + reliability * WEIGHT_RELIABILITY
        + clinical * WEIGHT_CLINICAL
        + pharmacy * WEIGHT_PHARMACY
    )

    breakdown = {
        "recency": round(recency, 4),
        "reliability": round(reliability, 4),
        "clinical_appropriateness": round(clinical, 4),
        "pharmacy_confirmation": round(pharmacy, 4),
        "total": round(total, 4),
    }
    return round(total, 4), breakdown


def compute_confidence_from_spread(scores: list[float]) -> float:
    """
    Derive confidence score from separation between top two candidates.

    High separation → high confidence in the winner.
    """
    if len(scores) < 2:
        return 0.90  # only one candidate, high confidence by default
    sorted_scores = sorted(scores, reverse=True)
    spread = sorted_scores[0] - sorted_scores[1]
    # Scale spread (0–1) → confidence (0.5–1.0)
    confidence = 0.50 + spread * 0.50
    return round(min(1.0, max(0.0, confidence)), 4)
