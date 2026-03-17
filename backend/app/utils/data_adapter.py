"""
PyHealth → ReconciliationRequest adapter.

Accepts either a real PyHealth ``Patient`` object (duck-typed) or a plain
``dict`` that follows the same schema.  No hard dependency on the pyhealth
package — we rely on attribute / key access so the module works even when
pyhealth is not installed.

PyHealth canonical hierarchy:
    Patient
    └─ Visit  (visit_id, encounter_time, discharge_time, visit_type, source_system)
       ├─ medications  [MedicationEvent]  (code, name, dose_mg, frequency, route, start_time)
       ├─ lab_tests    [LabEvent]         (code, name, value, unit, time)
       └─ conditions   [ConditionEvent]   (code, name, time)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timezone
from typing import Any

from app.models.reconcile_models import (
    MedicationRecord,
    PatientContext,
    ReconciliationRequest,
    SourceReliability,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reliability table — visit_type / source_system → SourceReliability
# ---------------------------------------------------------------------------
_VISIT_RELIABILITY: dict[str, SourceReliability] = {
    "inpatient": SourceReliability.HIGH,
    "inpatient ehr": SourceReliability.HIGH,
    "outpatient": SourceReliability.HIGH,
    "outpatient ehr": SourceReliability.HIGH,
    "emergency": SourceReliability.HIGH,
    "emergency department": SourceReliability.HIGH,
    "ed": SourceReliability.HIGH,
    "pharmacy": SourceReliability.MEDIUM,
    "pharmacy claim": SourceReliability.MEDIUM,
    "pharmacy_claim": SourceReliability.MEDIUM,
    "claim": SourceReliability.MEDIUM,
    "insurance claim": SourceReliability.MEDIUM,
    "self_report": SourceReliability.LOW,
    "patient_self_report": SourceReliability.LOW,
    "patient self report": SourceReliability.LOW,
    "patient reported": SourceReliability.LOW,
}

# ---------------------------------------------------------------------------
# Lab name normalisation — free-text / LOINC code → canonical key
# ---------------------------------------------------------------------------
_LAB_ALIASES: dict[str, str] = {
    # eGFR
    "egfr": "egfr",
    "estimated gfr": "egfr",
    "glomerular filtration rate": "egfr",
    "ckd-epi creatinine": "egfr",
    "mdrd gfr": "egfr",
    "33914-3": "egfr",
    "98979-8": "egfr",
    # Creatinine
    "creatinine": "creatinine",
    "serum creatinine": "creatinine",
    "creatinine [mass/volume] in serum or plasma": "creatinine",
    "2160-0": "creatinine",
    # Potassium
    "potassium": "potassium",
    "serum potassium": "potassium",
    "2823-3": "potassium",
    # Sodium
    "sodium": "sodium",
    "serum sodium": "sodium",
    "2951-2": "sodium",
    # HbA1c
    "hba1c": "hba1c",
    "hemoglobin a1c": "hba1c",
    "4548-4": "hba1c",
    # BUN
    "bun": "bun",
    "blood urea nitrogen": "bun",
    "3094-0": "bun",
}


# ---------------------------------------------------------------------------
# Low-level field accessors — support both dict and object input uniformly
# ---------------------------------------------------------------------------

def _get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Try attribute access then key access for each key in order."""
    for key in keys:
        try:
            val = getattr(obj, key, _SENTINEL)
            if val is not _SENTINEL:
                return val
        except Exception:
            pass
        if isinstance(obj, dict):
            val = obj.get(key, _SENTINEL)
            if val is not _SENTINEL:
                return val
    return default


_SENTINEL = object()


def _iter(obj: Any, *keys: str) -> list[Any]:
    """Return iterable at the first matching key/attr, or []."""
    val = _get(obj, *keys, default=[])
    return list(val) if val is not None else []


def _to_datetime(val: Any) -> datetime | None:
    """Coerce str / date / datetime to timezone-aware datetime, or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, date):
        return datetime(val.year, val.month, val.day, tzinfo=timezone.utc)
    if isinstance(val, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(val, fmt)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# ---------------------------------------------------------------------------
# Lab extraction helpers
# ---------------------------------------------------------------------------

def _canonical_lab_name(raw: str) -> str | None:
    """Return canonical lab key or None if unrecognised."""
    return _LAB_ALIASES.get(raw.strip().lower())


def extract_recent_labs(visits: list[Any]) -> dict[str, float]:
    """
    Scan all visits and return the most recent value per canonical lab name.

    Iterates visits in encounter_time order so later entries overwrite earlier
    ones; returns canonical keys only (e.g. "egfr", "creatinine").
    """
    # Collect (time, value) per canonical name across all visits
    candidates: dict[str, tuple[datetime, float]] = {}

    for visit in visits:
        lab_events = _iter(visit, "lab_tests", "labs", "lab_results")
        encounter_time = _to_datetime(_get(visit, "encounter_time", "visit_time"))

        for event in lab_events:
            raw_name: str = _get(event, "name", "test_name", "label", default="") or ""
            raw_code: str = str(_get(event, "code", "loinc_code", default="") or "")
            canonical = _canonical_lab_name(raw_name) or _canonical_lab_name(raw_code)
            if not canonical:
                continue

            raw_value = _get(event, "value", "result_value", "result")
            if raw_value is None:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue

            event_time = _to_datetime(_get(event, "time", "result_time", "timestamp"))
            timestamp = event_time or encounter_time or datetime.min.replace(tzinfo=timezone.utc)

            existing = candidates.get(canonical)
            if existing is None or timestamp >= existing[0]:
                candidates[canonical] = (timestamp, value)

    return {name: round(pair[1], 4) for name, pair in candidates.items()}


# ---------------------------------------------------------------------------
# Reliability inference
# ---------------------------------------------------------------------------

def infer_reliability(visit: Any) -> SourceReliability:
    """
    Infer SourceReliability from visit metadata.

    Checks visit_type first, then source_system as a fallback.
    """
    for field in ("visit_type", "encounter_type", "source_system", "system"):
        raw: str = _get(visit, field, default="") or ""
        key = raw.strip().lower()
        if key in _VISIT_RELIABILITY:
            return _VISIT_RELIABILITY[key]
    return SourceReliability.MEDIUM


def _is_pharmacy_visit(visit: Any) -> bool:
    """Return True when the visit type indicates a pharmacy dispense."""
    for field in ("visit_type", "encounter_type", "source_system"):
        raw: str = _get(visit, field, default="") or ""
        if "pharmacy" in raw.lower():
            return True
    return False


# ---------------------------------------------------------------------------
# Patient context builder
# ---------------------------------------------------------------------------

def build_patient_context(patient: Any, recent_labs: dict[str, float]) -> PatientContext:
    """
    Convert a PyHealth Patient object or compatible dict into PatientContext.

    Age is computed from birth_datetime when available.
    """
    patient_id: str = str(_get(patient, "patient_id", "id", default="UNKNOWN"))

    # Age from birth_datetime
    birth = _to_datetime(_get(patient, "birth_datetime", "dob", "date_of_birth"))
    if birth:
        today = datetime.now(timezone.utc)
        age = (today - birth).days // 365
    else:
        age = int(_get(patient, "age", default=0))

    weight_kg = _get(patient, "weight_kg", "weight")
    try:
        weight_kg = float(weight_kg) if weight_kg is not None else None
    except (TypeError, ValueError):
        weight_kg = None

    # Collect conditions from both patient-level and all visits
    conditions: list[str] = []
    for raw in _iter(patient, "conditions", "diagnoses", "icd_codes"):
        conditions.append(str(_get(raw, "name", "code", default=str(raw))))

    allergies: list[str] = [
        str(a) for a in _iter(patient, "allergies", "allergy_list")
    ]

    return PatientContext(
        patient_id=patient_id,
        age=max(0, min(130, age)),
        weight_kg=weight_kg,
        egfr=None,                   # backfill_egfr_from_labs validator handles this
        recent_labs=recent_labs,
        allergies=allergies,
        diagnoses=conditions,
    )


# ---------------------------------------------------------------------------
# Medication records builder
# ---------------------------------------------------------------------------

def build_medication_records(visits: list[Any]) -> list[MedicationRecord]:
    """
    Flatten medication events from all visits into a list of MedicationRecord.

    Each event becomes one record tagged with its originating visit and system.
    """
    records: list[MedicationRecord] = []

    for visit in visits:
        visit_id: str = str(_get(visit, "visit_id", "encounter_id", default="visit"))
        encounter_time = _to_datetime(_get(visit, "encounter_time", "visit_time"))
        if encounter_time is None:
            encounter_time = datetime.now(timezone.utc)

        reliability = infer_reliability(visit)
        pharmacy_confirmed = _is_pharmacy_visit(visit)

        source_system: str = (
            _get(visit, "source_system", "system", default="") or ""
        ).strip() or _get(visit, "visit_type", default="Unknown System") or "Unknown System"

        med_events = _iter(visit, "medications", "medication_orders", "drug_events")

        for idx, event in enumerate(med_events):
            med_name: str = _get(event, "name", "drug_name", "medication_name", default="") or ""
            if not med_name.strip():
                continue

            dose_raw = _get(event, "dose_mg", "dose", "dosage")
            try:
                dose_mg = float(dose_raw) if dose_raw is not None else None
            except (TypeError, ValueError):
                dose_mg = None

            event_time = _to_datetime(_get(event, "start_time", "time", "order_time"))
            recorded_at = event_time or encounter_time

            prescriber_id = _get(event, "prescriber_id", "provider_id", "ordering_provider")

            # Stable, deterministic source_id for dedup / cache keying
            uid = hashlib.md5(
                f"{visit_id}:{med_name}:{dose_mg}:{recorded_at.isoformat()}".encode()
            ).hexdigest()[:12]

            try:
                records.append(
                    MedicationRecord(
                        source_id=f"{visit_id}_{idx}_{uid}",
                        source_name=str(source_system),
                        reliability=reliability,
                        recorded_at=recorded_at,
                        medication_name=med_name,
                        dose_mg=dose_mg,
                        frequency=_get(event, "frequency", "sig", default=None),
                        route=_get(event, "route", "route_of_admin", default=None),
                        pharmacy_confirmed=pharmacy_confirmed,
                        prescriber_id=str(prescriber_id) if prescriber_id else None,
                    )
                )
            except Exception as exc:
                logger.warning("Skipping malformed medication event in visit %s: %s", visit_id, exc)

    return records


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def adapt_to_reconciliation_request(patient: Any) -> ReconciliationRequest:
    """
    Convert a PyHealth Patient (object or dict) to a ReconciliationRequest.

    Raises ValueError if no medication records can be extracted.
    """
    visits = _iter(patient, "visits", "encounters")

    recent_labs = extract_recent_labs(visits)
    patient_context = build_patient_context(patient, recent_labs)
    sources = build_medication_records(visits)

    if not sources:
        raise ValueError(
            f"No medication records found for patient "
            f"{patient_context.patient_id}."
        )

    logger.info(
        "Adapted patient %s: %d sources, labs=%s",
        patient_context.patient_id,
        len(sources),
        list(recent_labs.keys()),
    )
    return ReconciliationRequest(patient_context=patient_context, sources=sources)
