import pytest
from app.models.workflow import Workflow
from app.service.execution import execute_workflow

WORKFLOW = {
    "name": "Send Slack Message on Email Arrival",
    "edges": [{"from": "1", "to": "2"}],
    "nodes": [
        {"id": "1", "type": "gmail_trigger", "label": None, "config": {"sender_filter": "*"}},
        {"id": "2", "type": "slack_message", "label": None, "config": {"channel_id": "#finance", "message_template": "You have a new email!"}},
    ],
}


async def test_execute_workflow_completes():
    wf = Workflow(**WORKFLOW)
    result = await execute_workflow("test-id", wf)

    assert result["status"] == "completed"
    assert len(result["steps"]) == 2
    assert result["steps"][0]["node_type"] == "gmail_trigger"
    assert result["steps"][1]["node_type"] == "slack_message"
    assert result["steps"][1]["output"]["channel_id"] == "#finance"


async def test_execute_workflow_unknown_node_type_errors():
    # Bypass enum validation to simulate a corrupted record from the DB
    wf = Workflow.model_construct(
        name="bad",
        nodes=[],
        edges=[],
    )
    from app.models.workflow import Node
    bad_node = Node.model_construct(id="1", type="totally_unknown", config={})
    wf.nodes = [bad_node]

    result = await execute_workflow("test-id", wf)
    assert result["status"] == "failed"
    assert result["steps"][0]["status"] == "error"