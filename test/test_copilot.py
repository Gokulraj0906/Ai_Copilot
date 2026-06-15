import pytest
import app.copilot as copilot
from app.llm.client import LLMError

VALID_WORKFLOW_JSON = {
    "name": "Stripe to Finance",
    "nodes": [
        {"id": "1", "type": "gmail_trigger", "config": {"sender_filter": "stripe.com"}},
        {"id": "2", "type": "slack_message", "config": {"channel_id": "#finance"}},
    ],
    "edges": [{"from": "1", "to": "2"}],
}

INVALID_WORKFLOW_JSON = {
    "name": "Stripe to Finance",
    "nodes": [
        {"id": "1", "type": "gmail_trigger", "config": {"sender_filter": "stripe.com"}},
        {"id": "2", "type": "slack_message", "config": {}},
    ],
    "edges": [{"from": "1", "to": "2"}],
}


async def test_create_workflow_valid(monkeypatch):
    async def fake_call_llm(messages, **kwargs):
        return VALID_WORKFLOW_JSON

    monkeypatch.setattr(copilot, "call_llm", fake_call_llm)

    workflow, result, attempts = await copilot.create_workflow("email from stripe to finance slack")
    assert result.valid
    assert attempts == 0
    assert workflow.nodes[0].type == "gmail_trigger"


async def test_create_workflow_repairs_invalid(monkeypatch):
    calls = {"count": 0}

    async def fake_call_llm(messages, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return INVALID_WORKFLOW_JSON
        return VALID_WORKFLOW_JSON

    monkeypatch.setattr(copilot, "call_llm", fake_call_llm)

    workflow, result, attempts = await copilot.create_workflow("...")
    assert result.valid
    assert attempts == 1


async def test_create_workflow_llm_failure(monkeypatch):
    async def fake_call_llm(messages, **kwargs):
        raise LLMError("all models failed")

    monkeypatch.setattr(copilot, "call_llm", fake_call_llm)

    with pytest.raises(LLMError):
        await copilot.create_workflow("...")


async def test_explain_workflow(monkeypatch):
    from app.models.workflow import Workflow

    async def fake_call_llm(messages, **kwargs):
        return {"explanation": "This workflow sends a Slack message when an email arrives."}

    monkeypatch.setattr(copilot, "call_llm", fake_call_llm)

    wf = Workflow(**VALID_WORKFLOW_JSON)
    explanation = await copilot.explain_workflow(wf)
    assert "Slack" in explanation