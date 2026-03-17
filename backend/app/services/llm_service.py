"""LLM integration — reasoning explanation only, never truth selection."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.config import get_settings
from app.models.reconcile_models import (
    ClinicalSafetyStatus,
    MedicationRecord,
    PatientContext,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMReasoning:
    """Structured output extracted from LLM response."""

    reasoning: str
    clinical_safety_check: ClinicalSafetyStatus
    recommended_actions: list[str]
    llm_available: bool = True


_FALLBACK = LLMReasoning(
    reasoning="AI reasoning unavailable — deterministic scoring result retained.",
    clinical_safety_check=ClinicalSafetyStatus.UNKNOWN,
    recommended_actions=["Verify manually with pharmacist or prescriber."],
    llm_available=False,
)

_SYSTEM_PROMPT = """\
You are a clinical pharmacist AI assistant supporting a medication reconciliation tool.
Your role is EXPLANATORY ONLY — the reconciliation decision has ALREADY been made by \
a deterministic scoring engine. You must NOT override or second-guess that decision.

Respond ONLY with valid JSON matching this schema:
{
  "reasoning": "<clinical explanation, 2-4 sentences>",
  "clinical_safety_check": "SAFE" | "CAUTION" | "UNSAFE" | "UNKNOWN",
  "recommended_actions": ["<action 1>", "<action 2>", ...]
}

Rules:
- clinical_safety_check must be one of: SAFE, CAUTION, UNSAFE, UNKNOWN
- recommended_actions must be a non-empty list of strings
- Do not include any text outside the JSON object
"""


def _build_user_prompt(
    patient: PatientContext,
    sources: list[MedicationRecord],
    selected: MedicationRecord,
    score_breakdown: dict[str, float],
) -> str:
    """Construct the user-turn prompt with full clinical context."""
    sources_text = "\n".join(
        f"  - [{s.source_name}] {s.medication_name} "
        f"{s.dose_mg or '?'}mg {s.frequency or '?'} "
        f"({s.recorded_at.date()}, reliability={s.reliability.value})"
        for s in sources
    )
    return f"""\
PATIENT CONTEXT:
  Age: {patient.age} years
  eGFR: {patient.egfr or 'unknown'} mL/min
  Weight: {patient.weight_kg or 'unknown'} kg
  Allergies: {', '.join(patient.allergies) if patient.allergies else 'none documented'}
  Diagnoses: {', '.join(patient.diagnoses) if patient.diagnoses else 'none documented'}

CONFLICTING SOURCES:
{sources_text}

DETERMINISTIC ENGINE SELECTED:
  Medication: {selected.medication_name}
  Dose: {selected.dose_mg or 'not specified'} mg
  Frequency: {selected.frequency or 'not specified'}
  Route: {selected.route or 'not specified'}
  Source: {selected.source_name}
  Score breakdown: {json.dumps(score_breakdown)}

Provide your clinical reasoning explanation and safety assessment as JSON only."""


class LLMService:
    """Wraps Gemini calls with retry, JSON parsing, and graceful fallback."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.gemini_model
        self._temperature = settings.llm_temperature
        self._max_tokens = settings.llm_max_tokens
        self._retries = settings.llm_retry_attempts
        self._retry_delay = settings.llm_retry_delay
        self._client: genai.Client | None = None
        if settings.gemini_api_key:
            self._client = genai.Client(api_key=settings.gemini_api_key)

    async def get_reasoning(
        self,
        patient: PatientContext,
        sources: list[MedicationRecord],
        selected: MedicationRecord,
        score_breakdown: dict[str, float],
    ) -> LLMReasoning:
        """
        Call LLM for clinical explanation of the deterministic decision.

        Falls back gracefully on any error — system never crashes.
        """
        if self._client is None:
            logger.warning("Gemini client not initialised — no GEMINI_API_KEY configured.")
            return _FALLBACK

        user_prompt = _build_user_prompt(patient, sources, selected, score_breakdown)

        for attempt in range(1, self._retries + 1):
            try:
                return self._call_gemini(user_prompt)
            except genai_errors.APIError as exc:
                logger.error("LLM API error on attempt %d: %s", attempt, exc)
                if attempt < self._retries:
                    await asyncio.sleep(self._retry_delay * attempt)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unexpected LLM failure on attempt %d: %s", attempt, exc)
                break

        return _FALLBACK

    def _call_gemini(self, user_prompt: str) -> LLMReasoning:
        """Make one Gemini generate_content call and parse the JSON response."""
        response = self._client.models.generate_content(  # type: ignore[union-attr]
            model=self._model_name,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=self._temperature,
                max_output_tokens=self._max_tokens,
            ),
        )
        raw = response.text or "{}"
        return self._parse_response(raw)

    @staticmethod
    def _parse_response(raw: str) -> LLMReasoning:
        """Parse LLM JSON output into LLMReasoning, with field-level fallbacks."""
        # Strip markdown code fences if present (e.g. ```json ... ```)
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.find("\n") + 1:]  # drop opening fence line
            if "```" in cleaned:
                cleaned = cleaned[: cleaned.rfind("```")]
            cleaned = cleaned.strip()
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON: %s", raw[:200])
            return _FALLBACK

        try:
            safety_raw = data.get("clinical_safety_check", "UNKNOWN").upper()
            safety = ClinicalSafetyStatus(safety_raw)
        except ValueError:
            safety = ClinicalSafetyStatus.UNKNOWN

        actions = data.get("recommended_actions", [])
        if not isinstance(actions, list) or not actions:
            actions = ["Review with clinical pharmacist."]

        return LLMReasoning(
            reasoning=data.get("reasoning", "No reasoning provided."),
            clinical_safety_check=safety,
            recommended_actions=[str(a) for a in actions],
            llm_available=True,
        )
