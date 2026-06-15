from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db import repository
from app.models.workflow import Workflow
from app.validation import validate_workflow
from app.execution import execute_workflow
from app.cache import (
    invalidate_explanation,
    acquire_execution_lock,
    release_execution_lock,
    cache_execution_result,
    get_cached_execution_result,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    wf = await repository.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.model_dump(by_alias=True)


@router.get("")
async def list_workflows(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
    records = await repository.list_workflows(db, limit, offset)
    return [
        {"id": r.id, "name": r.name, "is_valid": r.is_valid, "created_at": r.created_at.isoformat()}
        for r in records
    ]


@router.post("")
async def create_workflow_direct(workflow: Workflow, db: AsyncSession = Depends(get_db)):
    result = validate_workflow(workflow)
    wf_id = await repository.save_workflow(db, workflow, is_valid=result.valid)
    return {"workflow_id": wf_id, "valid": result.valid, "issues": [i.model_dump() for i in result.issues]}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
    deleted = await repository.delete_workflow(db, workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found")
    await invalidate_explanation(workflow_id)
    return {"deleted": True}


@router.post("/{workflow_id}/execute")
async def run_workflow_automation(workflow_id: str, db: AsyncSession = Depends(get_db)):
    """Executes a saved workflow by iterating through its nodes.

    Redis usage here:
    - acquire_execution_lock prevents two concurrent executions of the
      same workflow (e.g. double-click) from both running.
    - cache_execution_result stores the latest run so it can be
      retrieved without re-querying/re-running.
    """
    wf = await repository.get_workflow(db, workflow_id)
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

    try:
        result = await execute_workflow(workflow_id, wf)
    finally:
        await release_execution_lock(workflow_id)

    await cache_execution_result(workflow_id, result)
    return result


@router.get("/{workflow_id}/execute/latest")
async def get_latest_execution(workflow_id: str, db: AsyncSession = Depends(get_db)):
    wf = await repository.get_workflow(db, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")

    cached = await get_cached_execution_result(workflow_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No execution found for this workflow yet")
    return cached

# import asyncio
# import logging
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.database import get_db
# from app.db import repository
# from app.models.workflow import Workflow
# from app.validation import validate_workflow

# logger = logging.getLogger("copilot")

# router = APIRouter(prefix="/workflows", tags=["workflows"])


# @router.get("/{workflow_id}")
# async def get_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
#     wf = await repository.get_workflow(db, workflow_id)
#     if not wf:
#         raise HTTPException(status_code=404, detail="Workflow not found")
#     return wf.model_dump(by_alias=True)


# @router.get("")
# async def list_workflows(limit: int = 50, offset: int = 0, db: AsyncSession = Depends(get_db)):
#     records = await repository.list_workflows(db, limit, offset)
#     return [
#         {"id": r.id, "name": r.name, "is_valid": r.is_valid, "created_at": r.created_at.isoformat()}
#         for r in records
#     ]


# @router.post("")
# async def create_workflow_direct(workflow: Workflow, db: AsyncSession = Depends(get_db)):
#     result = validate_workflow(workflow)
#     wf_id = await repository.save_workflow(db, workflow, is_valid=result.valid)
#     return {"workflow_id": wf_id, "valid": result.valid, "issues": [i.model_dump() for i in result.issues]}


# @router.delete("/{workflow_id}")
# async def delete_workflow(workflow_id: str, db: AsyncSession = Depends(get_db)):
#     deleted = await repository.delete_workflow(db, workflow_id)
#     if not deleted:
#         raise HTTPException(status_code=404, detail="Workflow not found")
#     return {"deleted": True}


# # --- NEW EXECUTION ENDPOINT ---
# @router.post("/{workflow_id}/execute")
# async def run_workflow_automation(workflow_id: str, db: AsyncSession = Depends(get_db)):
#     """
#     Executes a saved workflow by iterating through its nodes.
#     """
#     wf = await repository.get_workflow(db, workflow_id)
#     if not wf:
#         raise HTTPException(status_code=404, detail="Workflow not found")

#     execution_logs = []
    
#     try:
#         # Assuming wf is your Pydantic Workflow model
#         for node in wf.nodes: 
#             logger.info(f"Executing node {node.id} ({node.type})")
#             config = node.config
            
#             if node.type == "slack_message":
#                 channel = config.get("channel_id", "default_channel")
#                 msg = config.get("message_template", "Hello!")
                
#                 logger.info(f"--> [Slack API] Sending '{msg}' to {channel}")
#                 execution_logs.append(f" Slack: Sent message to {channel}")
                
#             elif node.type == "gmail_trigger":
#                 execution_logs.append(f" Trigger: Acknowledged Gmail event")
                
#             elif node.type == "delay":
#                 delay_sec = int(config.get("seconds", 2))
#                 logger.info(f"--> [System] Sleeping for {delay_sec}s")
#                 await asyncio.sleep(delay_sec) 
#                 execution_logs.append(f" System: Delayed for {delay_sec} seconds")
                
#             elif node.type == "notion_create_page":
#                 page_name = config.get("page_name", "Untitled")
#                 execution_logs.append(f" Notion: Created page '{page_name}'")
                
#             else:
#                 execution_logs.append(f" System: Processed {node.type}")

#         return {
#             "status": "success", 
#             "message": "Workflow executed successfully.",
#             "logs": execution_logs
#         }
        
#     except Exception as e:
#         logger.error(f"Workflow execution failed: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")