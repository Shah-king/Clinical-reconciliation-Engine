"""Tests for the data quality scoring engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.quality_models import DataQualityRequest, QualityLevel
from app.services.data_quality_engine import DataQualityEngine

engine = DataQualityEngine()


def _req(**kwargs) -> DataQualityRequest:
    """Helper to build a DataQualityRequest with defaults."""
    defaults = dict(
        patient_id="P001",
        systolic_bp=120,
        diastolic_bp=80,
        heart_rate=72,
        temperature_c=37.0,
        allergies=["penicillin"],
        medications=["Metformin 500mg"],
        recorded_at=datetime.now(timezone.utc) - timedelta(days=5),
        provider_id="DR001",
        diagnosis_codes=["E11.9"],
    )
    defaults.update(kwargs)
    return DataQualityRequest(**defaults)


# ------------------------------------------------------------------
# Test 1: Implausible systolic BP > 300 flagged
# ------------------------------------------------------------------

def test_implausible_systolic_bp_flagged():
    """Systolic BP > 300 must be flagged as a critical clinical issue."""
    result = engine.evaluate(_req(systolic_bp=350))
    fields = [i.field for i in result.issues_detected]
    assert "systolic_bp" in fields
    severities = [i.severity for i in result.issues_detected if i.field == "systolic_bp"]
    assert "critical" in severities
    assert result.breakdown.clinical_plausibility < 100.0


# ------------------------------------------------------------------
# Test 2: Implausible heart rate < 20 flagged
# ------------------------------------------------------------------

def test_implausible_heart_rate_low_flagged():
    """Heart rate < 20 bpm must generate a critical clinical issue."""
    result = engine.evaluate(_req(heart_rate=10))
    fields = [i.field for i in result.issues_detected]
    assert "heart_rate" in fields


# ------------------------------------------------------------------
# Test 3: Implausible heart rate > 250 flagged
# ------------------------------------------------------------------

def test_implausible_heart_rate_high_flagged():
    """Heart rate > 250 bpm must generate a critical clinical issue."""
    result = engine.evaluate(_req(heart_rate=300))
    fields = [i.field for i in result.issues_detected]
    assert "heart_rate" in fields


# ------------------------------------------------------------------
# Test 4: Empty allergy list triggers warning
# ------------------------------------------------------------------

def test_empty_allergy_list_warned():
    """An empty (not None) allergy list should raise an accuracy warning."""
    result = engine.evaluate(_req(allergies=[]))
    messages = [i.message for i in result.issues_detected]
    assert any("allergy" in m.lower() or "Allergy" in m for m in messages)


# ------------------------------------------------------------------
# Test 5: Very old record (>180 days) triggers timeliness issue
# ------------------------------------------------------------------

def test_very_old_record_timeliness_flagged():
    """Records older than 180 days should receive a low timeliness score."""
    old_date = datetime.now(timezone.utc) - timedelta(days=200)
    result = engine.evaluate(_req(recorded_at=old_date))
    assert result.breakdown.timeliness <= 20.0


# ------------------------------------------------------------------
# Test 6: Perfect record scores ≥80 and is GOOD level
# ------------------------------------------------------------------

def test_complete_valid_record_scores_good():
    """A fully populated, plausible record should reach GOOD quality level."""
    result = engine.evaluate(_req())
    assert result.overall_score >= 80.0
    assert result.quality_level == QualityLevel.GOOD


# ------------------------------------------------------------------
# Test 7: Missing fields reduce completeness
# ------------------------------------------------------------------

def test_missing_fields_reduce_completeness():
    """Omitting multiple optional fields must lower completeness score."""
    result = engine.evaluate(
        DataQualityRequest(
            patient_id="P002",
            systolic_bp=None,
            diastolic_bp=None,
            heart_rate=None,
        )
    )
    assert result.breakdown.completeness < 70.0
