"""
Prompt builders — all anti-hallucination rules live here.

Key design decisions:
  • catalog_text is injected by the RAG layer (only relevant nodes, not all 50+).
  • STRICT_RULES are included in every system prompt.
  • json_mode=True is always used so the model cannot emit free text.
  • Temperature = 0.1 (set in client.py) for maximum determinism.
"""

import json
from app.models.workflow import Workflow
from app.models.validation import ValidationResult

# ─── Shared rules injected into every system prompt ──────────────────────────
STRICT_RULES = """
STRICT RULES — you MUST follow every rule below. Breaking any rule is a critical failure.

1. ONLY use node types listed in the "Available node types" section above.
   Never invent a node type. If a service is not listed, do NOT include it.
2. Every node MUST include all required config fields (marked with *).
   For optional fields you can omit them or leave them as empty strings.
3. Trigger nodes MUST have no incoming edges.
4. Every non-trigger node MUST be reachable from a trigger via edges.
5. IDs must be sequential strings starting from "1" ("1", "2", "3", …).
6. Output ONLY a single raw JSON object — no markdown, no prose, no code fences.
7. Never hallucinate integrations, URLs, API keys, or config values that were
   not described by the user. Use descriptive placeholders like
   "{{customer_phone}}", "{{order_id}}", "{{amount_paise}}" for unknown values.
8. If the user's instruction mentions a service that is NOT in the catalog,
   omit it silently — do not substitute a fake node type for it.
"""

SCHEMA_DESCRIPTION = """\
Output STRICT JSON matching this schema:
{
  "name": "short descriptive workflow name",
  "nodes": [
    {"id": "1", "type": "<node_type>", "config": {"field": "value"}}
  ],
  "edges": [
    {"from": "1", "to": "2"}
  ]
}"""


def build_create_prompt(instruction: str, catalog_text: str) -> list[dict]:
    system = f"""You are a workflow automation expert for a no-code platform.
Your job is to generate a valid workflow JSON from a user's plain-English description.

Available node types (use ONLY these — nothing else):
{catalog_text}

{SCHEMA_DESCRIPTION}

{STRICT_RULES}"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction},
    ]


def build_modify_prompt(
    workflow: Workflow,
    instruction: str,
    catalog_text: str,
    history: list[dict] | None = None,
) -> list[dict]:
    system = f"""You are a workflow automation expert. Modify the existing workflow below.

Available node types (use ONLY these):
{catalog_text}

Current workflow (JSON):
{workflow.model_dump_json(by_alias=True)}

{SCHEMA_DESCRIPTION}

{STRICT_RULES}

Additional modification rules:
- Preserve existing nodes and edges unless the user explicitly asks to remove them.
- Continue node ID numbering from the highest existing ID + 1.
- Output the FULL updated workflow (not just the changed parts)."""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": instruction})
    return messages


def build_fix_prompt(
    workflow: Workflow,
    validation_result: ValidationResult,
    catalog_text: str,
) -> list[dict]:
    system = f"""You are a workflow automation expert. Repair the workflow below based on validation errors.

Available node types (use ONLY these):
{catalog_text}

Current workflow (JSON):
{workflow.model_dump_json(by_alias=True)}

Validation errors to fix:
{json.dumps([i.model_dump() for i in validation_result.issues], indent=2)}

{SCHEMA_DESCRIPTION}

{STRICT_RULES}

Repair rules:
- Fix every BLOCKING error.
- For missing required config fields, infer a descriptive placeholder from context,
  e.g. "{{customer_phone}}" or "#orders-team".
- Do NOT remove nodes unless the error is UNKNOWN_NODE_TYPE.
- Output the FULL corrected workflow."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Fix all validation errors in the workflow."},
    ]


def build_explain_prompt(workflow: Workflow, catalog_text: str) -> list[dict]:
    system = f"""You are a workflow automation expert. Explain the workflow below in plain English.

Node types reference:
{catalog_text}

Workflow:
{workflow.model_dump_json(by_alias=True)}

Instructions:
- Describe what the trigger is and what each action does, in order.
- Mention key config values (e.g. which WhatsApp number, which Slack channel).
- Be concise and business-friendly (non-technical reader).
- Output STRICT JSON: {{"explanation": "your explanation text here"}}
- Output ONLY the JSON object. No markdown, no extra text."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Explain this workflow."},
    ]
