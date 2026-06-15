import json
from app.models.workflow import Workflow
from app.models.validation import ValidationResult

SCHEMA_DESCRIPTION = """Output STRICT JSON matching this schema:
{
  "name": "short descriptive name",
  "nodes": [{"id": "1", "type": "gmail_trigger", "config": {"sender_filter": "..."}}],
  "edges": [{"from": "1", "to": "2"}]
}"""


def build_create_prompt(instruction: str, catalog_text: str) -> list[dict]:
    system = f"""You are a workflow automation expert. You generate workflow JSON for an automation platform.

Available node types (use ONLY these):
{catalog_text}

{SCHEMA_DESCRIPTION}

Rules:
- Every node must include all required config fields for its type (marked with *).
- Trigger nodes (gmail_trigger, webhook) must have no incoming edges.
- Generate sequential string IDs starting from "1".
- Output ONLY the JSON object. No markdown, no explanation."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction},
    ]


def build_modify_prompt(workflow: Workflow, instruction: str, catalog_text: str, history: list[dict] | None = None) -> list[dict]:
    system = f"""You are a workflow automation expert. You modify an existing workflow based on a user instruction.

Available node types:
{catalog_text}

Current workflow:
{workflow.model_dump_json(by_alias=True)}

Instructions:
- Apply the user's requested change while preserving existing nodes/edges unless the user asks to remove them.
- Use new sequential IDs for any new nodes (continue numbering from the highest existing ID + 1).
- Output the FULL updated workflow as STRICT JSON matching the same schema.
- Output ONLY the JSON object. No markdown, no explanation."""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": instruction})
    return messages


def build_fix_prompt(workflow: Workflow, validation_result: ValidationResult, catalog_text: str) -> list[dict]:
    system = f"""You are a workflow automation expert. You repair a workflow based on validation errors.

Available node types:
{catalog_text}

Current workflow:
{workflow.model_dump_json(by_alias=True)}

Validation errors:
{json.dumps([i.model_dump() for i in validation_result.issues], indent=2)}

Instructions:
- Fix each BLOCKING error. For missing config fields, infer sensible values from context (e.g. "channel_id": "#finance-team" if the workflow concerns finance).
- Do not remove nodes unless the error is about an invalid/unknown node type.
- Output the FULL corrected workflow as STRICT JSON matching the original schema.
- Output ONLY the JSON object. No markdown, no explanation."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Fix the workflow."},
    ]


def build_explain_prompt(workflow: Workflow, catalog_text: str) -> list[dict]:
    system = f"""You are a workflow automation expert. Explain the given workflow in plain, human-readable English.

Node types reference:
{catalog_text}

Workflow:
{workflow.model_dump_json(by_alias=True)}

Instructions:
- Describe the trigger, then each subsequent action in order, in plain language.
- Mention key configuration values (e.g. which Slack channel, which sender filter).
- Output STRICT JSON: {{"explanation": "your explanation text here"}}
- Output ONLY the JSON object. No markdown, no explanation outside the JSON."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "Explain this workflow."},
    ]