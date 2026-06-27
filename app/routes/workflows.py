from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.credential_store import get_user_credentials
from app.db import repository
from app.db.database import get_db
from app.db.tables import UserRecord
from app.models.workflow import Workflow
from app.service.validation import validate_workflow
from app.service.execution import execute_workflow
from app.core.cache import (
    invalidate_explanation,
    acquire_execution_lock,
    release_execution_lock,
    cache_execution_result,
    get_cached_execution_result,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])

@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await repository.get_workflow(db, workflow_id, user_id=current_user.id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.model_dump(by_alias=True)

@router.get("")
async def list_workflows(
    limit: int = 50,
    offset: int = 0,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    records = await repository.list_workflows(db, limit, offset, user_id=current_user.id)
    return [
        {"id": r.id, "name": r.name, "is_valid": r.is_valid, "created_at": r.created_at.isoformat()}
        for r in records
    ]

@router.post("")
async def create_workflow_direct(
    workflow: Workflow,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = validate_workflow(workflow)
    wf_id = await repository.save_workflow(db, workflow, is_valid=result.valid, user_id=current_user.id)
    return {"workflow_id": wf_id, "valid": result.valid, "issues": [i.model_dump() for i in result.issues]}

@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    deleted = await repository.delete_workflow(db, workflow_id, user_id=current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await invalidate_explanation(workflow_id)
    return {"deleted": True}

@router.post("/{workflow_id}/execute")
async def run_workflow_automation(
    workflow_id: str,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute a workflow using the calling user's own API credentials.
    Credentials are decrypted from the DB (cached in Redis for 5 min).
    """
    wf = await repository.get_workflow(db, workflow_id, user_id=current_user.id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    validation_result = validate_workflow(wf)
    if not validation_result.valid:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "workflow_invalid",
                "message": "Cannot execute an invalid workflow. Run /copilot/fix first.",
                "issues": [i.model_dump() for i in validation_result.issues],
            },
        )

    locked = await acquire_execution_lock(workflow_id)
    if not locked:
        raise HTTPException(status_code=409, detail="This workflow is already executing. Try again shortly.")

    # Load this user's credentials (decrypted, Redis-cached)
    creds = await get_user_credentials(current_user.id, db)

    try:
        result = await execute_workflow(workflow_id, wf, creds)
    finally:
        await release_execution_lock(workflow_id)

    await cache_execution_result(workflow_id, result)
    return result

@router.get("/{workflow_id}/execute/latest")
async def get_latest_execution(
    workflow_id: str,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wf = await repository.get_workflow(db, workflow_id, user_id=current_user.id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    cached = await get_cached_execution_result(workflow_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No execution found for this workflow yet")
    return cached