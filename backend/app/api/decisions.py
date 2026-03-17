"""Clinician decision recording — approve or reject a reconciliation result."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.auth.api_key import require_api_key

router = APIRouter(tags=["decisions"])
logger = logging.getLogger(__name__)

# In-memory audit log (sufficient for a prototype demo)
_decisions: list[dict] = []


class DecisionRequest(BaseModel):
    patient_id: str
    reconciled_medication: str
    decision: Literal["approved", "rejected"]
    notes: str = ""


class DecisionResponse(BaseModel):
    id: str
    patient_id: str
    reconciled_medication: str
    decision: Literal["approved", "rejected"]
    notes: str
    timestamp: str
    status: str


@router.post(
    "/reconcile/decision",
    response_model=DecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a clinician approve/reject decision on a reconciliation result",
)
async def record_decision(
    body: DecisionRequest,
    _: str = Depends(require_api_key),
) -> DecisionResponse:
    record = DecisionResponse(
        id=str(uuid.uuid4()),
        patient_id=body.patient_id,
        reconciled_medication=body.reconciled_medication,
        decision=body.decision,
        notes=body.notes,
        timestamp=datetime.now(timezone.utc).isoformat(),
        status="recorded",
    )
    _decisions.append(record.model_dump())
    logger.info(
        "Decision recorded: %s — %s (%s)", body.decision.upper(), body.reconciled_medication, body.patient_id
    )
    return record
