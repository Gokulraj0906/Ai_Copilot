from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.tables import WorkflowRecord, SessionMessageRecord, AuditLogRecord
from app.models.workflow import Workflow


async def save_workflow(db: AsyncSession, workflow: Workflow, is_valid: bool = False) -> str:
    record = WorkflowRecord(name=workflow.name, data=workflow.model_dump(by_alias=True), is_valid=is_valid)
    db.add(record)
    await db.commit()
    return record.id


async def get_workflow(db: AsyncSession, workflow_id: str) -> Workflow | None:
    record = await db.get(WorkflowRecord, workflow_id)
    return Workflow(**record.data) if record else None


async def update_workflow(db: AsyncSession, workflow_id: str, workflow: Workflow, is_valid: bool = False) -> None:
    record = await db.get(WorkflowRecord, workflow_id)
    if record:
        record.data = workflow.model_dump(by_alias=True)
        record.name = workflow.name
        record.is_valid = is_valid
        await db.commit()


async def delete_workflow(db: AsyncSession, workflow_id: str) -> bool:
    record = await db.get(WorkflowRecord, workflow_id)
    if record:
        await db.delete(record)
        await db.commit()
        return True
    return False


async def list_workflows(db: AsyncSession, limit: int = 50, offset: int = 0) -> list[WorkflowRecord]:
    result = await db.execute(select(WorkflowRecord).order_by(WorkflowRecord.created_at.desc()).limit(limit).offset(offset))
    return list(result.scalars().all())


async def get_session_history(db: AsyncSession, session_id: str, limit: int = 10) -> list[dict]:
    result = await db.execute(
        select(SessionMessageRecord)
        .where(SessionMessageRecord.session_id == session_id)
        .order_by(SessionMessageRecord.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return [{"role": r.role, "content": r.content} for r in rows]


async def append_session_message(db: AsyncSession, session_id: str, role: str, content: str) -> None:
    db.add(SessionMessageRecord(session_id=session_id, role=role, content=content))
    await db.commit()


async def log_audit(db: AsyncSession, request_id: str, action: str, input_data: dict, llm_model: str, raw_response: str) -> None:
    db.add(AuditLogRecord(request_id=request_id, action=action, input_data=input_data, llm_model=llm_model, raw_response=raw_response))
    await db.commit()