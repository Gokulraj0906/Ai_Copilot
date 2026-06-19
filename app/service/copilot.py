"""
Copilot service — orchestrates RAG retrieval, intent classification,
LLM calls, and self-repair loop.

Flow for create_workflow:
  1. classify_intent()  → out_of_scope?  return guidance immediately (no LLM)
  2. build_rag_catalog_text()  → retrieve relevant nodes only
  3. build_create_prompt()  → inject RAG catalog into system prompt
  4. call_llm()  → model generates workflow JSON
  5. _validate_and_repair()  → up to 2 self-repair attempts
"""

import logging
from app.models.workflow import Workflow
from app.models.validation import ValidationResult
from app.service.validation import validate_workflow
from app.llm.client import call_llm, LLMError
from app.llm.prompts import (
    build_create_prompt,
    build_modify_prompt,
    build_fix_prompt,
    build_explain_prompt,
)
from app.llm.rag import build_rag_catalog_text
from app.llm.intent import classify_intent, IntentResult
from app.core.catalog import CATALOG_PROMPT_TEXT

logger = logging.getLogger("copilot.core")

MAX_REPAIR_ATTEMPTS = 2


# ─── Public result types ──────────────────────────────────────────────────────

class WorkflowResult:
    """Returned by create/modify/fix — includes optional guidance for partial support."""
    def __init__(
        self,
        workflow: Workflow,
        validation: ValidationResult,
        repair_attempts: int,
        intent: IntentResult | None = None,
    ):
        self.workflow = workflow
        self.validation = validation
        self.repair_attempts = repair_attempts
        self.intent = intent

    @property
    def partial_guidance(self) -> str | None:
        """Non-empty when the instruction mentioned unsupported services."""
        if self.intent and self.intent.intent == "partially_supported":
            return self.intent.guidance
        return None


class OutOfScopeResult:
    """Returned when the instruction is irrelevant to workflow automation."""
    def __init__(self, guidance: str, intent: IntentResult):
        self.guidance = guidance
        self.intent = intent


# ─── Core service functions ───────────────────────────────────────────────────

async def create_workflow(
    instruction: str,
) -> WorkflowResult | OutOfScopeResult:
    """
    Create a workflow from a plain-English instruction.

    Returns OutOfScopeResult when the request is irrelevant (e.g. tax filing).
    Returns WorkflowResult (with optional partial_guidance) otherwise.
    """
    # Step 1: Intent classification — no LLM, rule-based, instant
    intent = classify_intent(instruction)

    if intent.intent == "out_of_scope":
        logger.info(f"Out-of-scope instruction: {instruction[:80]!r}")
        return OutOfScopeResult(guidance=intent.guidance, intent=intent)

    # Step 2: RAG — retrieve only relevant catalog nodes
    rag_catalog = build_rag_catalog_text(instruction)
    logger.debug(f"RAG catalog for instruction:\n{rag_catalog}")

    # Step 3: Build prompt with RAG-filtered catalog
    messages = build_create_prompt(instruction, rag_catalog)

    # Step 4: Call LLM (may raise LLMError — caller handles)
    raw = await call_llm(messages)
    workflow = Workflow(**raw)

    # Step 5: Validate + self-repair loop
    workflow, validation, attempts = await _validate_and_repair(workflow, rag_catalog)

    return WorkflowResult(
        workflow=workflow,
        validation=validation,
        repair_attempts=attempts,
        intent=intent,
    )


async def modify_workflow(
    existing: Workflow,
    instruction: str,
    history: list[dict] | None = None,
) -> WorkflowResult | OutOfScopeResult:
    intent = classify_intent(instruction)
    if intent.intent == "out_of_scope":
        return OutOfScopeResult(guidance=intent.guidance, intent=intent)

    rag_catalog = build_rag_catalog_text(instruction)
    messages = build_modify_prompt(existing, instruction, rag_catalog, history)
    raw = await call_llm(messages)
    workflow = Workflow(**raw)
    workflow, validation, attempts = await _validate_and_repair(workflow, rag_catalog)
    return WorkflowResult(workflow=workflow, validation=validation, repair_attempts=attempts, intent=intent)


async def fix_workflow(existing: Workflow) -> WorkflowResult:
    workflow, validation, attempts = await _validate_and_repair(existing, CATALOG_PROMPT_TEXT)
    return WorkflowResult(workflow=workflow, validation=validation, repair_attempts=attempts)


async def explain_workflow(workflow: Workflow) -> str:
    # For explain we use full catalog — no instruction to filter on
    messages = build_explain_prompt(workflow, CATALOG_PROMPT_TEXT)
    raw = await call_llm(messages)
    return raw["explanation"]


# ─── Internal helpers ─────────────────────────────────────────────────────────

async def _validate_and_repair(
    workflow: Workflow,
    catalog_text: str,
) -> tuple[Workflow, ValidationResult, int]:
    """
    Bounded self-repair loop: at most MAX_REPAIR_ATTEMPTS extra LLM calls.

    Uses the same catalog_text (RAG-filtered) that was used to generate the
    workflow — keeps repair grounded in the same context.
    """
    result = validate_workflow(workflow)
    attempts = 0

    while not result.valid and attempts < MAX_REPAIR_ATTEMPTS:
        try:
            messages = build_fix_prompt(workflow, result, catalog_text)
            raw = await call_llm(messages)
            workflow = Workflow(**raw)
            result = validate_workflow(workflow)
        except LLMError:
            # Repair failed — return best-effort with remaining issues
            break
        attempts += 1

    return workflow, result, attempts
