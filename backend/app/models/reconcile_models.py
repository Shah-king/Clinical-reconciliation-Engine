"""Pydantic v2 models for medication reconciliation."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SourceReliability(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ClinicalSafetyStatus(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"
    UNKNOWN = "UNKNOWN"


class PatientContext(BaseModel):
    """Minimal patient context required for reconciliation."""

    patient_id: str = Field(..., min_length=1, max_length=64)
    age: int = Field(..., ge=0, le=130)
    weight_kg: float | None = Field(default=None, ge=1.0, le=500.0)
    egfr: float | None = Field(default=None, ge=0.0, le=150.0)
    allergies: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    # Keyed by canonical lab name (e.g. "egfr", "creatinine", "potassium").
    # Populated by data_adapter from visit lab_tests; values are latest readings.
    recent_labs: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _backfill_egfr_from_labs(self) -> PatientContext:
        """Auto-populate egfr from recent_labs when not set explicitly."""
        if self.egfr is None and "egfr" in self.recent_labs:
            self.egfr = self.recent_labs["egfr"]
        return self


class MedicationRecord(BaseModel):
    """A single medication entry from one data source."""

    source_id: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    reliability: SourceReliability = SourceReliability.MEDIUM
    recorded_at: datetime
    medication_name: str = Field(..., min_length=1, max_length=200)
    dose_mg: float | None = Field(default=None, ge=0.0)
    frequency: str | None = Field(default=None, max_length=100)
    route: str | None = Field(default=None, max_length=50)
    pharmacy_confirmed: bool = False
    prescriber_id: str | None = None

    @field_validator("medication_name", mode="before")
    @classmethod
    def normalize_med_name(cls, v: str) -> str:
        """Strip and title-case medication name on ingestion."""
        return v.strip().title() if isinstance(v, str) else v


class ReconciliationRequest(BaseModel):
    """Input payload for POST /api/reconcile/medication."""

    patient_context: PatientContext
    sources: list[MedicationRecord] = Field(..., min_length=1, max_length=20)

    @model_validator(mode="after")
    def at_least_one_source(self) -> ReconciliationRequest:
        if not self.sources:
            raise ValueError("At least one medication source is required.")
        return self


class ScoredCandidate(BaseModel):
    """Internal: a source scored by the deterministic engine."""

    source: MedicationRecord
    total_score: float = Field(..., ge=0.0, le=1.0)
    score_breakdown: dict[str, float]


class ReconciliationResult(BaseModel):
    """Output payload returned to the caller."""

    patient_id: str
    reconciled_medication: str
    reconciled_dose_mg: float | None
    reconciled_frequency: str | None
    reconciled_route: str | None
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    recommended_actions: list[str]
    clinical_safety_check: ClinicalSafetyStatus
    selected_source_id: str
    score_breakdown: dict[str, float]
    cached: bool = False
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
