"""Tests for deterministic validation utilities."""

from __future__ import annotations

import pytest

from app.utils.validators import (
    validate_dose,
    validate_egfr_metformin,
    validate_medication_name,
    validate_route,
)


# ------------------------------------------------------------------
# Medication name validation
# ------------------------------------------------------------------

def test_valid_medication_name():
    result = validate_medication_name("Metformin")
    assert result.valid
    assert not result.errors


def test_empty_medication_name_invalid():
    result = validate_medication_name("   ")
    assert not result.valid


def test_injection_chars_rejected():
    result = validate_medication_name("<script>alert(1)</script>")
    assert not result.valid


# ------------------------------------------------------------------
# Dose validation
# ------------------------------------------------------------------

def test_metformin_dose_in_range_no_warning():
    result = validate_dose("Metformin", 500.0)
    assert not result.warnings


def test_metformin_dose_out_of_range_warned():
    result = validate_dose("Metformin", 15000.0)
    assert result.warnings


def test_none_dose_generates_warning():
    result = validate_dose("Aspirin", None)
    assert result.warnings


# ------------------------------------------------------------------
# Route validation
# ------------------------------------------------------------------

def test_valid_route():
    result = validate_route("oral")
    assert not result.warnings


def test_unknown_route_warned():
    result = validate_route("nebulised")
    assert result.warnings


def test_none_route_warned():
    result = validate_route(None)
    assert result.warnings


# ------------------------------------------------------------------
# eGFR / Metformin clinical rules
# ------------------------------------------------------------------

def test_metformin_safe_egfr():
    result = validate_egfr_metformin("Metformin", egfr=80.0)
    assert result.valid
    assert not result.errors
    assert not result.warnings


def test_metformin_reduced_dose_egfr():
    result = validate_egfr_metformin("Metformin", egfr=40.0)
    assert result.valid
    assert result.warnings  # dose reduction warning expected


def test_metformin_contraindicated_egfr():
    result = validate_egfr_metformin("Metformin", egfr=25.0)
    assert not result.valid
    assert result.errors


def test_non_metformin_ignores_egfr():
    result = validate_egfr_metformin("Atorvastatin", egfr=10.0)
    assert result.valid
    assert not result.errors
    assert not result.warnings
