"""Deterministic data quality scoring engine."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.quality_models import (
    DataQualityRequest,
    DataQualityResult,
    QualityIssue,
    QualityLevel,
    QualityScoreBreakdown,
)

logger = logging.getLogger(__name__)

# Record age thresholds (days)
TIMELINESS_STALE_DAYS = 90
TIMELINESS_VERY_OLD_DAYS = 180


class DataQualityEngine:
    """Evaluates a patient record across four quality dimensions."""

    def evaluate(self, request: DataQualityRequest) -> DataQualityResult:
        """Run all quality checks and return a scored result."""
        issues: list[QualityIssue] = []

        completeness = self._score_completeness(request, issues)
        accuracy = self._score_accuracy(request, issues)
        timeliness = self._score_timeliness(request, issues)
        plausibility = self._score_clinical_plausibility(request, issues)

        overall = round(
            completeness * 0.30
            + accuracy * 0.25
            + timeliness * 0.20
            + plausibility * 0.25,
            2,
        )

        return DataQualityResult(
            patient_id=request.patient_id,
            overall_score=overall,
            quality_level=_level(overall),
            breakdown=QualityScoreBreakdown(
                completeness=completeness,
                accuracy=accuracy,
                timeliness=timeliness,
                clinical_plausibility=plausibility,
            ),
            issues_detected=issues,
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_completeness(
        req: DataQualityRequest, issues: list[QualityIssue]
    ) -> float:
        """Penalise for missing expected fields."""
        optional_fields = [
            ("systolic_bp", req.systolic_bp),
            ("diastolic_bp", req.diastolic_bp),
            ("heart_rate", req.heart_rate),
            ("temperature_c", req.temperature_c),
            ("allergies", req.allergies),
            ("medications", req.medications),
            ("recorded_at", req.recorded_at),
            ("provider_id", req.provider_id),
            ("diagnosis_codes", req.diagnosis_codes),
        ]
        missing = [name for name, val in optional_fields if val is None]
        for name in missing:
            issues.append(
                QualityIssue(
                    dimension="completeness",
                    severity="warning",
                    message=f"Field '{name}' is missing.",
                    field=name,
                )
            )
        score = max(0.0, 100.0 - len(missing) * (100.0 / len(optional_fields)))
        return round(score, 2)

    @staticmethod
    def _score_accuracy(
        req: DataQualityRequest, issues: list[QualityIssue]
    ) -> float:
        """Check formatting and value consistency."""
        deductions = 0.0

        if req.systolic_bp is not None and req.diastolic_bp is not None:
            if req.systolic_bp <= req.diastolic_bp:
                issues.append(
                    QualityIssue(
                        dimension="accuracy",
                        severity="critical",
                        message=(
                            f"Systolic BP ({req.systolic_bp}) must be greater than "
                            f"diastolic BP ({req.diastolic_bp})."
                        ),
                        field="systolic_bp",
                    )
                )
                deductions += 30.0

        if req.temperature_c is not None:
            if not (30.0 <= req.temperature_c <= 45.0):
                issues.append(
                    QualityIssue(
                        dimension="accuracy",
                        severity="warning",
                        message=f"Temperature {req.temperature_c}°C is outside 30–45°C range.",
                        field="temperature_c",
                        value=req.temperature_c,
                    )
                )
                deductions += 20.0

        if req.allergies is not None and len(req.allergies) == 0:
            issues.append(
                QualityIssue(
                    dimension="accuracy",
                    severity="warning",
                    message="Allergy list is empty — confirm 'NKDA' (No Known Drug Allergies) or populate.",
                    field="allergies",
                )
            )
            deductions += 10.0

        return round(max(0.0, 100.0 - deductions), 2)

    @staticmethod
    def _score_timeliness(
        req: DataQualityRequest, issues: list[QualityIssue]
    ) -> float:
        """Penalise stale records."""
        if req.recorded_at is None:
            issues.append(
                QualityIssue(
                    dimension="timeliness",
                    severity="warning",
                    message="recorded_at timestamp is missing — recency unknown.",
                    field="recorded_at",
                )
            )
            return 50.0  # partial credit when date unknown

        now = datetime.now(timezone.utc)
        rec = req.recorded_at
        if rec.tzinfo is None:
            rec = rec.replace(tzinfo=timezone.utc)

        age_days = (now - rec).days

        if age_days > TIMELINESS_VERY_OLD_DAYS:
            issues.append(
                QualityIssue(
                    dimension="timeliness",
                    severity="critical",
                    message=f"Record is {age_days} days old (>{TIMELINESS_VERY_OLD_DAYS}d). Data may be outdated.",
                    field="recorded_at",
                    value=age_days,
                )
            )
            return 20.0
        if age_days > TIMELINESS_STALE_DAYS:
            issues.append(
                QualityIssue(
                    dimension="timeliness",
                    severity="warning",
                    message=f"Record is {age_days} days old (>{TIMELINESS_STALE_DAYS}d). Verify currency.",
                    field="recorded_at",
                    value=age_days,
                )
            )
            return 60.0

        return 100.0

    @staticmethod
    def _score_clinical_plausibility(
        req: DataQualityRequest, issues: list[QualityIssue]
    ) -> float:
        """Check physiologically implausible values."""
        deductions = 0.0

        if req.systolic_bp is not None and req.systolic_bp > 300:
            issues.append(
                QualityIssue(
                    dimension="clinical_plausibility",
                    severity="critical",
                    message=f"Systolic BP {req.systolic_bp} mmHg exceeds physiological maximum (300).",
                    field="systolic_bp",
                    value=req.systolic_bp,
                )
            )
            deductions += 40.0

        if req.heart_rate is not None:
            if req.heart_rate < 20:
                issues.append(
                    QualityIssue(
                        dimension="clinical_plausibility",
                        severity="critical",
                        message=f"Heart rate {req.heart_rate} bpm is below physiological minimum (20).",
                        field="heart_rate",
                        value=req.heart_rate,
                    )
                )
                deductions += 40.0
            elif req.heart_rate > 250:
                issues.append(
                    QualityIssue(
                        dimension="clinical_plausibility",
                        severity="critical",
                        message=f"Heart rate {req.heart_rate} bpm exceeds physiological maximum (250).",
                        field="heart_rate",
                        value=req.heart_rate,
                    )
                )
                deductions += 40.0

        return round(max(0.0, 100.0 - deductions), 2)


def _level(score: float) -> QualityLevel:
    """Map numeric score to QualityLevel enum."""
    if score >= 80:
        return QualityLevel.GOOD
    if score >= 50:
        return QualityLevel.FAIR
    return QualityLevel.POOR
