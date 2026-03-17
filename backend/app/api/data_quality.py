"""API routes for data quality validation — no business logic here."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.api_key import require_api_key
from app.models.quality_models import DataQualityRequest, DataQualityResult
from app.services.data_quality_engine import DataQualityEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/validate", tags=["data-quality"])

_quality_engine = DataQualityEngine()


@router.post(
    "/data-quality",
    response_model=DataQualityResult,
    status_code=status.HTTP_200_OK,
    summary="Evaluate clinical data quality across four dimensions",
)
async def validate_data_quality(
    request: DataQualityRequest,
    _: str = Depends(require_api_key),
) -> DataQualityResult:
    """
    Score a patient record on completeness, accuracy, timeliness,
    and clinical plausibility.  Returns per-dimension breakdown and
    a list of detected issues with severity levels.
    """
    try:
        return _quality_engine.evaluate(request)
    except Exception as exc:
        logger.exception("Data quality engine failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Data quality engine encountered an unexpected error.",
        ) from exc
