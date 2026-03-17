"""
Deterministic medication reconciliation engine.

LLM is called AFTER the decision — it explains, never decides.
"""

from __future__ import annotations

import logging

from app.models.reconcile_models import (
    MedicationRecord,
    PatientContext,
    ReconciliationRequest,
    ReconciliationResult,
    ScoredCandidate,
)
from app.services.llm_service import LLMService
from app.utils.scoring import compute_confidence_from_spread, compute_total_score
from app.utils.validators import (
    merge_validation_results,
    validate_dose,
    validate_egfr_metformin,
    validate_medication_name,
    validate_route,
)

logger = logging.getLogger(__name__)


class ReconciliationEngine:
    """
    Orchestrates the full reconciliation pipeline:

    1. Validate all sources
    2. Score deterministically
    3. Select winner
    4. Call LLM for reasoning
    5. Return structured result
    """

    def __init__(self, llm_service: LLMService) -> None:
        self._llm = llm_service

    async def reconcile(self, request: ReconciliationRequest) -> ReconciliationResult:
        """
        Execute the reconciliation pipeline for a single patient request.

        Returns a ReconciliationResult regardless of LLM availability.
        """
        patient = request.patient_context
        sources = request.sources

        scored = self._score_all(sources, patient)
        winner = self._select_winner(scored)

        all_scores = [c.total_score for c in scored]
        confidence = compute_confidence_from_spread(all_scores)

        # Penalty if LLM will be unavailable or validation has errors
        validation = self._validate_winner(winner.source, patient)
        if validation.errors:
            confidence = max(0.0, confidence - 0.20)

        llm_result = await self._llm.get_reasoning(
            patient=patient,
            sources=sources,
            selected=winner.source,
            score_breakdown=winner.score_breakdown,
        )
        if not llm_result.llm_available:
            confidence = max(0.0, confidence - 0.05)

        actions = self._build_actions(winner.source, patient, validation, llm_result.recommended_actions)

        return ReconciliationResult(
            patient_id=patient.patient_id,
            reconciled_medication=winner.source.medication_name,
            reconciled_dose_mg=winner.source.dose_mg,
            reconciled_frequency=winner.source.frequency,
            reconciled_route=winner.source.route,
            confidence_score=round(confidence, 4),
            reasoning=llm_result.reasoning,
            recommended_actions=actions,
            clinical_safety_check=llm_result.clinical_safety_check,
            selected_source_id=winner.source.source_id,
            score_breakdown=winner.score_breakdown,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _score_all(
        self, sources: list[MedicationRecord], patient: PatientContext
    ) -> list[ScoredCandidate]:
        """Score every source and return a list sorted best-first."""
        scored: list[ScoredCandidate] = []
        for src in sources:
            total, breakdown = compute_total_score(
                record=src, egfr=patient.egfr, age=patient.age
            )
            scored.append(ScoredCandidate(source=src, total_score=total, score_breakdown=breakdown))
        return sorted(scored, key=lambda c: c.total_score, reverse=True)

    @staticmethod
    def _select_winner(scored: list[ScoredCandidate]) -> ScoredCandidate:
        """Return the highest-scoring candidate."""
        if not scored:
            raise ValueError("No candidates to select from.")
        return scored[0]

    @staticmethod
    def _validate_winner(
        record: MedicationRecord, patient: PatientContext
    ):  # -> ValidationResult
        """Run all validators against the winning record."""
        return merge_validation_results(
            validate_medication_name(record.medication_name),
            validate_dose(record.medication_name, record.dose_mg),
            validate_route(record.route),
            validate_egfr_metformin(record.medication_name, patient.egfr),
        )

    @staticmethod
    def _build_actions(
        record: MedicationRecord,
        patient: PatientContext,
        validation,
        llm_actions: list[str],
    ) -> list[str]:
        """
        Combine deterministic safety actions with LLM suggestions.

        Deterministic actions always appear first.
        """
        actions: list[str] = []

        for error in validation.errors:
            actions.append(f"[CRITICAL] {error}")
        for warning in validation.warnings:
            actions.append(f"[WARNING] {warning}")

        if not patient.allergies:
            actions.append("[WARNING] No allergy information on file — verify with patient.")

        # Append LLM suggestions that aren't already covered
        for llm_action in llm_actions:
            if llm_action not in actions:
                actions.append(llm_action)

        if not actions:
            actions.append("No additional actions required.")

        return actions
