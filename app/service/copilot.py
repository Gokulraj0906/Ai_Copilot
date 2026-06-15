from app.models.workflow import Workflow
from app.models.validation import ValidationResult
from app.service.validation import validate_workflow
from app.llm.client import call_llm, LLMError
from app.llm.prompts import (
    build_create_prompt, build_modify_prompt, build_fix_prompt, build_explain_prompt,
)
from app.core.catalog import CATALOG_PROMPT_TEXT
import logging

logger = logging.getLogger("copilot.core")

MAX_REPAIR_ATTEMPTS = 2


async def create_workflow(instruction: str) -> tuple[Workflow, ValidationResult, int]:
    messages = build_create_prompt(instruction, CATALOG_PROMPT_TEXT)
    raw = await call_llm(messages)  # may raise LLMError — caller handles
    workflow = Workflow(**raw)
    return await _validate_and_repair(workflow)


async def modify_workflow(existing: Workflow, instruction: str, history: list[dict] | None = None) -> tuple[Workflow, ValidationResult, int]:
    messages = build_modify_prompt(existing, instruction, CATALOG_PROMPT_TEXT, history)
    raw = await call_llm(messages)
    workflow = Workflow(**raw)
    return await _validate_and_repair(workflow)


async def fix_workflow(existing: Workflow) -> tuple[Workflow, ValidationResult, int]:
    return await _validate_and_repair(existing)


async def explain_workflow(workflow: Workflow) -> str:
    messages = build_explain_prompt(workflow, CATALOG_PROMPT_TEXT)
    raw = await call_llm(messages)
    return raw["explanation"]


async def _validate_and_repair(workflow: Workflow) -> tuple[Workflow, ValidationResult, int]:
    """Bounded loop: at most MAX_REPAIR_ATTEMPTS extra LLM calls.

    This bound matters under load — without it, a workflow the LLM
    can't fix could loop many times, each holding an async task +
    making LLM calls, multiplying load from a single user request.
    """
    result = validate_workflow(workflow)
    attempts = 0

    while not result.valid and attempts < MAX_REPAIR_ATTEMPTS:
        try:
            messages = build_fix_prompt(workflow, result, CATALOG_PROMPT_TEXT)
            raw = await call_llm(messages)
            workflow = Workflow(**raw)
            result = validate_workflow(workflow)
        except LLMError:
            # Repair attempt failed — return best-effort workflow with
            # remaining issues rather than raising. The user still gets
            # a usable response.
            break
        attempts += 1

    return workflow, result, attempts