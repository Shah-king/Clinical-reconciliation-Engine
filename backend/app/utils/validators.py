"""Input validation helpers — all deterministic, no AI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

VALID_ROUTE_PATTERNS = {"oral", "iv", "im", "subcutaneous", "topical", "inhaled", "rectal", "transdermal"}

# Dose sanity ranges (mg) keyed by normalized partial name
DOSE_SANITY: dict[str, tuple[float, float]] = {
    "metformin": (250.0, 3000.0),
    "lisinopril": (2.5, 80.0),
    "atorvastatin": (10.0, 80.0),
    "warfarin": (0.5, 20.0),
    "aspirin": (25.0, 4000.0),
    "amoxicillin": (125.0, 3000.0),
    "ibuprofen": (100.0, 3200.0),
    "insulin": (1.0, 200.0),
}


@dataclass
class ValidationResult:
    valid: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def validate_medication_name(name: str) -> ValidationResult:
    """Ensure medication name looks like a real name (no injection chars)."""
    result = ValidationResult()
    if not name or not name.strip():
        result.valid = False
        result.errors.append("Medication name is empty.")
        return result
    if re.search(r"[<>{};]", name):
        result.valid = False
        result.errors.append(f"Medication name contains invalid characters: {name!r}")
    if len(name) > 200:
        result.valid = False
        result.errors.append("Medication name exceeds 200 characters.")
    return result


def validate_dose(medication_name: str, dose_mg: float | None) -> ValidationResult:
    """Check dose is within known physiological range for given medication."""
    result = ValidationResult()
    if dose_mg is None:
        result.warnings.append("Dose not provided — completeness reduced.")
        return result

    normalized = medication_name.lower()
    for key, (low, high) in DOSE_SANITY.items():
        if key in normalized:
            if dose_mg < low or dose_mg > high:
                result.warnings.append(
                    f"Dose {dose_mg} mg is outside expected range "
                    f"[{low}–{high}] mg for {key}."
                )
    return result


def validate_route(route: str | None) -> ValidationResult:
    """Ensure route of administration is a known value."""
    result = ValidationResult()
    if route is None:
        result.warnings.append("Route of administration not specified.")
        return result
    if route.lower() not in VALID_ROUTE_PATTERNS:
        result.warnings.append(
            f"Unrecognised route '{route}'. Expected one of: "
            + ", ".join(sorted(VALID_ROUTE_PATTERNS))
        )
    return result


def validate_egfr_metformin(medication_name: str, egfr: float | None) -> ValidationResult:
    """Flag metformin at low eGFR — clinical safety rule."""
    result = ValidationResult()
    if "metformin" not in medication_name.lower():
        return result
    if egfr is None:
        result.warnings.append("eGFR unknown — cannot assess metformin safety.")
        return result
    if egfr < 30:
        result.valid = False
        result.errors.append(
            f"Metformin is CONTRAINDICATED with eGFR={egfr:.1f} mL/min (<30)."
        )
    elif egfr < 45:
        result.warnings.append(
            f"Metformin requires dose reduction with eGFR={egfr:.1f} mL/min (<45)."
        )
    return result


def merge_validation_results(*results: ValidationResult) -> ValidationResult:
    """Combine multiple ValidationResults into one."""
    merged = ValidationResult()
    for r in results:
        if not r.valid:
            merged.valid = False
        merged.warnings.extend(r.warnings)
        merged.errors.extend(r.errors)
    return merged
