"""
Copilot API routes.

POST /copilot/create   — Generate workflow from instruction
POST /copilot/modify   — Modify existing workflow
POST /copilot/fix      — Repair validation errors
POST /copilot/explain  — Explain workflow in plain English

Out-of-scope instructions return HTTP 200 with:
  { "out_of_scope": true, "guidance": "..." }

Partial support (some services unsupported) returns HTTP 200 with:
  { "workflow": {...}, "partial_guidance": "...", ... }
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.db import repository
from app.core.cache import (
    check_rate_limit,
    get_cached_explanation,
    cache_explanation,
    invalidate_explanation,
)
from app.core.deps import get_api_key
from app.llm.client import LLMError
from app.service.copilot import (
    OutOfScopeResult,
    WorkflowResult,
    create_workflow,
    modify_workflow,
    fix_workflow,
    explain_workflow,
)

router = APIRouter(prefix="/copilot", tags=["copilot"])


async def rate_limit_dependency(api_key: str = Depends(get_api_key)) -> str:
    allowed = await check_rate_limit(api_key, limit=30, window_seconds=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    return api_key


# ─── Request models ───────────────────────────────────────────────────────────

class CreateRequest(BaseModel):
    instruction: str


class ModifyRequest(BaseModel):
    workflow_id: str
    instruction: str
    session_id: str | None = None


class FixRequest(BaseModel):
    workflow_id: str


class ExplainRequest(BaseModel):
    workflow_id: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/create")
async def create(
    req: CreateRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await create_workflow(req.instruction)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please retry.")

    # Out-of-scope: instruction is irrelevant — return guidance, no workflow created
    if isinstance(result, OutOfScopeResult):
        return {
            "out_of_scope": True,
            "guidance": result.guidance,
        }

    # Partially supported: workflow created, but some services weren't available
    wf_id = await repository.save_workflow(db, result.workflow, is_valid=result.validation.valid)
    response = {
        "workflow": result.workflow.model_dump(by_alias=True),
        "valid": result.validation.valid,
        "issues": [i.model_dump() for i in result.validation.issues],
        "repair_attempts": result.repair_attempts,
        "workflow_id": wf_id,
        "out_of_scope": False,
    }
    if result.partial_guidance:
        response["partial_guidance"] = result.partial_guidance

    return response


@router.post("/modify")
async def modify(
    req: ModifyRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    existing = await repository.get_workflow(db, req.workflow_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")

    history = (
        await repository.get_session_history(db, req.session_id)
        if req.session_id
        else None
    )

    try:
        result = await modify_workflow(existing, req.instruction, history)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please retry.")

    if isinstance(result, OutOfScopeResult):
        return {"out_of_scope": True, "guidance": result.guidance}

    await repository.update_workflow(db, req.workflow_id, result.workflow, is_valid=result.validation.valid)
    await invalidate_explanation(req.workflow_id)

    if req.session_id:
        await repository.append_session_message(db, req.session_id, "user", req.instruction)

    response = {
        "workflow": result.workflow.model_dump(by_alias=True),
        "valid": result.validation.valid,
        "issues": [i.model_dump() for i in result.validation.issues],
        "repair_attempts": result.repair_attempts,
        "workflow_id": req.workflow_id,
        "out_of_scope": False,
    }
    if result.partial_guidance:
        response["partial_guidance"] = result.partial_guidance
    return response


@router.post("/fix")
async def fix(
    req: FixRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    existing = await repository.get_workflow(db, req.workflow_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        result = await fix_workflow(existing)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please retry.")

    await repository.update_workflow(db, req.workflow_id, result.workflow, is_valid=result.validation.valid)
    await invalidate_explanation(req.workflow_id)

    return {
        "workflow": result.workflow.model_dump(by_alias=True),
        "valid": result.validation.valid,
        "issues": [i.model_dump() for i in result.validation.issues],
        "repair_attempts": result.repair_attempts,
        "workflow_id": req.workflow_id,
    }


@router.post("/explain")
async def explain(
    req: ExplainRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    existing = await repository.get_workflow(db, req.workflow_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")

    cached = await get_cached_explanation(req.workflow_id)
    if cached:
        return {"workflow_id": req.workflow_id, "explanation": cached, "cached": True}

    try:
        explanation = await explain_workflow(existing)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please retry.")

    await cache_explanation(req.workflow_id, explanation)
    return {"workflow_id": req.workflow_id, "explanation": explanation, "cached": False}
