"""API routes for medication reconciliation — no business logic here."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.api_key import require_api_key
from app.config import get_settings
from app.models.reconcile_models import ReconciliationRequest, ReconciliationResult
from app.services.cache_service import build_cache_key, get_cache
from app.services.llm_service import LLMService
from app.services.reconciliation_engine import ReconciliationEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reconcile", tags=["reconciliation"])

# Module-level service singletons (shared across requests)
_llm_service = LLMService()
_engine = ReconciliationEngine(llm_service=_llm_service)


@router.post(
    "/medication",
    response_model=ReconciliationResult,
    status_code=status.HTTP_200_OK,
    summary="Reconcile conflicting medication records",
)
async def reconcile_medication(
    request: ReconciliationRequest,
    _: str = Depends(require_api_key),
) -> ReconciliationResult:
    """
    Accept conflicting medication records and return the reconciled truth.

    Processing pipeline:
    1. Check cache (SHA-256 key)
    2. Run deterministic scoring engine
    3. Call LLM for clinical reasoning
    4. Cache and return result
    """
    settings = get_settings()
    cache = get_cache()

    cache_key = build_cache_key(
        request.patient_context.model_dump(mode="json"),
        [s.model_dump(mode="json") for s in request.sources],
    )

    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("Cache hit for patient %s", request.patient_context.patient_id)
        cached.cached = True
        return cached

    try:
        result = await _engine.reconcile(request)
    except Exception as exc:
        logger.exception("Reconciliation engine failure: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Reconciliation engine encountered an unexpected error.",
        ) from exc

    cache.set(cache_key, result, ttl_seconds=settings.cache_ttl_seconds)
    return result
