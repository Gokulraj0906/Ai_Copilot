from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.database import get_db
from app.db import repository
from app.cache import check_rate_limit, get_cached_explanation, cache_explanation, invalidate_explanation
from app.deps import get_api_key
from app.llm.client import LLMError
import app.copilot as copilot

router = APIRouter(prefix="/copilot", tags=["copilot"])


async def rate_limit_dependency(api_key: str = Depends(get_api_key)) -> str:
    allowed = await check_rate_limit(api_key, limit=30, window_seconds=60)
    if not allowed:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again shortly.")
    return api_key


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


@router.post("/create")
async def create(
    req: CreateRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    try:
        workflow, result, attempts = await copilot.create_workflow(req.instruction)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please try again.")

    wf_id = await repository.save_workflow(db, workflow, is_valid=result.valid)
    return {
        "workflow": workflow.model_dump(by_alias=True),
        "valid": result.valid,
        "issues": [i.model_dump() for i in result.issues],
        "repair_attempts": attempts,
        "workflow_id": wf_id,
    }


@router.post("/modify")
async def modify(
    req: ModifyRequest,
    api_key: str = Depends(rate_limit_dependency),
    db: AsyncSession = Depends(get_db),
):
    existing = await repository.get_workflow(db, req.workflow_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Workflow not found")

    history = await repository.get_session_history(db, req.session_id) if req.session_id else None

    try:
        workflow, result, attempts = await copilot.modify_workflow(existing, req.instruction, history)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please try again.")

    await repository.update_workflow(db, req.workflow_id, workflow, is_valid=result.valid)
    await invalidate_explanation(req.workflow_id)
    if req.session_id:
        await repository.append_session_message(db, req.session_id, "user", req.instruction)

    return {
        "workflow": workflow.model_dump(by_alias=True),
        "valid": result.valid,
        "issues": [i.model_dump() for i in result.issues],
        "repair_attempts": attempts,
        "workflow_id": req.workflow_id,
    }


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
        workflow, result, attempts = await copilot.fix_workflow(existing)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please try again.")

    await repository.update_workflow(db, req.workflow_id, workflow, is_valid=result.valid)
    await invalidate_explanation(req.workflow_id)

    return {
        "workflow": workflow.model_dump(by_alias=True),
        "valid": result.valid,
        "issues": [i.model_dump() for i in result.issues],
        "repair_attempts": attempts,
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
        explanation = await copilot.explain_workflow(existing)
    except LLMError:
        raise HTTPException(status_code=503, detail="AI service is temporarily unavailable. Please try again.")

    await cache_explanation(req.workflow_id, explanation)
    return {"workflow_id": req.workflow_id, "explanation": explanation, "cached": False}