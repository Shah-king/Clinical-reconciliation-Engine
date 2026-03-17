"""Pydantic v2 models for data quality assessment."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityLevel(str, Enum):
    GOOD = "good"       # 80–100
    FAIR = "fair"       # 50–79
    POOR = "poor"       # <50


class QualityIssue(BaseModel):
    """A single detected quality problem."""

    dimension: str
    severity: str = Field(..., pattern="^(critical|warning|info)$")
    message: str
    field: str | None = None
    value: Any = None


class QualityScoreBreakdown(BaseModel):
    """Per-dimension scores (0–100)."""

    completeness: float = Field(..., ge=0.0, le=100.0)
    accuracy: float = Field(..., ge=0.0, le=100.0)
    timeliness: float = Field(..., ge=0.0, le=100.0)
    clinical_plausibility: float = Field(..., ge=0.0, le=100.0)


class DataQualityRequest(BaseModel):
    """Payload for POST /api/validate/data-quality."""

    patient_id: str = Field(..., min_length=1, max_length=64)
    systolic_bp: int | None = Field(default=None, ge=0)
    diastolic_bp: int | None = Field(default=None, ge=0)
    heart_rate: int | None = Field(default=None, ge=0)
    temperature_c: float | None = None
    allergies: list[str] | None = None
    medications: list[str] | None = None
    recorded_at: datetime | None = None
    provider_id: str | None = None
    diagnosis_codes: list[str] | None = None
    notes: str | None = None


class DataQualityResult(BaseModel):
    """Output payload for data quality check."""

    patient_id: str
    overall_score: float = Field(..., ge=0.0, le=100.0)
    quality_level: QualityLevel
    breakdown: QualityScoreBreakdown
    issues_detected: list[QualityIssue]
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
