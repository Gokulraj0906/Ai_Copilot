"""Simulated execution engine.

Real integrations (Gmail, Slack, Notion APIs) are out of scope for
this assignment — each "executor" below returns a deterministic mock
output based on the node's config, so the /execute endpoint is fully
testable without external credentials. Swapping a mock for a real
API call is a one-function change per node type.
"""

import asyncio
import logging
from app.models.workflow import Workflow, Node, NodeExecutionResult

logger = logging.getLogger("copilot.execution")


async def execute_node(node: Node, context: dict) -> NodeExecutionResult:
    try:
        executor = EXECUTORS.get(node.type.value, _execute_unknown)
        output = await executor(node, context)
        return NodeExecutionResult(node_id=node.id, node_type=node.type.value, status="success", output=output)
    except Exception as e:
        logger.warning(f"Node {node.id} ({node.type.value}) failed: {e}")
        return NodeExecutionResult(node_id=node.id, node_type=node.type.value, status="error", output={}, error=str(e))


async def _execute_gmail_trigger(node: Node, context: dict) -> dict:
    return {
        "simulated": True,
        "matched_sender": node.config.get("sender_filter", "*"),
        "email": {"from": "billing@stripe.com", "subject": "Your invoice is ready"},
    }


async def _execute_webhook(node: Node, context: dict) -> dict:
    return {"simulated": True, "received_payload": {"event": "test"}}


async def _execute_slack_message(node: Node, context: dict) -> dict:
    template = node.config.get("message_template", "")
    return {
        "simulated": True,
        "channel_id": node.config.get("channel_id"),
        "message_sent": template or "(no message_template configured)",
    }


async def _execute_notion_create_page(node: Node, context: dict) -> dict:
    return {
        "simulated": True,
        "database_id": node.config.get("database_id"),
        "page_title": node.config.get("title_template", "Untitled"),
    }


async def _execute_discord_message(node: Node, context: dict) -> dict:
    return {"simulated": True, "channel_id": node.config.get("channel_id")}


async def _execute_teams_message(node: Node, context: dict) -> dict:
    return {"simulated": True, "channel_id": node.config.get("channel_id")}


async def _execute_delay(node: Node, context: dict) -> dict:
    seconds = int(node.config.get("duration_seconds", 0))
    capped = min(seconds, 2)  # never actually block a request for the real duration
    await asyncio.sleep(capped)
    return {"simulated": True, "requested_seconds": seconds, "actual_seconds": capped}


async def _execute_condition(node: Node, context: dict) -> dict:
    return {"simulated": True, "expression": node.config.get("expression"), "result": True}


async def _execute_unknown(node: Node, context: dict) -> dict:
    raise ValueError(f"No executor registered for node type '{node.type.value}'")


EXECUTORS = {
    "gmail_trigger": _execute_gmail_trigger,
    "webhook": _execute_webhook,
    "slack_message": _execute_slack_message,
    "notion_create_page": _execute_notion_create_page,
    "discord_message": _execute_discord_message,
    "teams_message": _execute_teams_message,
    "delay": _execute_delay,
    "condition": _execute_condition,
}


def _topological_order(workflow: Workflow) -> list[Node]:
    """Orders nodes so triggers run first and each node runs after
    its predecessors. Falls back to declaration order for any node
    not reachable via edges (e.g. orphans)."""
    node_map = {n.id: n for n in workflow.nodes}
    incoming: dict[str, list[str]] = {n.id: [] for n in workflow.nodes}
    for e in workflow.edges:
        if e.to in incoming:
            incoming[e.to].append(e.from_)

    visited: set[str] = set()
    ordered: list[Node] = []

    def visit(node_id: str):
        if node_id in visited:
            return
        for dep in incoming.get(node_id, []):
            visit(dep)
        visited.add(node_id)
        ordered.append(node_map[node_id])

    for n in workflow.nodes:
        visit(n.id)

    return ordered


async def execute_workflow(workflow_id: str, workflow: Workflow) -> dict:
    steps: list[NodeExecutionResult] = []
    context: dict = {}
    status = "completed"

    for node in _topological_order(workflow):
        result = await execute_node(node, context)
        steps.append(result)
        context[node.id] = result.output
        if result.status == "error":
            status = "failed"
            break

    return {
        "workflow_id": workflow_id,
        "status": status,
        "steps": [s.model_dump() for s in steps],
    }