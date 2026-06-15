from app.models.workflow import Workflow, Node, Edge
from app.validation import validate_workflow


def test_valid_workflow():
    wf = Workflow(
        name="test",
        nodes=[
            Node(id="1", type="gmail_trigger", config={"sender_filter": "stripe.com"}),
            Node(id="2", type="slack_message", config={"channel_id": "#finance"}),
        ],
        edges=[Edge(**{"from": "1", "to": "2"})],
    )
    result = validate_workflow(wf)
    assert result.valid
    assert result.issues == []


def test_missing_required_config():
    wf = Workflow(
        name="test",
        nodes=[
            Node(id="1", type="gmail_trigger", config={"sender_filter": "stripe.com"}),
            Node(id="2", type="slack_message", config={}),
        ],
        edges=[Edge(**{"from": "1", "to": "2"})],
    )
    result = validate_workflow(wf)
    assert not result.valid
    assert any(i.code == "MISSING_CONFIG_FIELD" for i in result.issues)


def test_unknown_edge_reference():
    wf = Workflow(
        name="test",
        nodes=[Node(id="1", type="webhook", config={})],
        edges=[Edge(**{"from": "1", "to": "2"})],
    )
    result = validate_workflow(wf)
    assert not result.valid
    assert any(i.code == "EDGE_UNKNOWN_TARGET" for i in result.issues)


def test_trigger_with_incoming_edge():
    wf = Workflow(
        name="test",
        nodes=[
            Node(id="1", type="slack_message", config={"channel_id": "#a"}),
            Node(id="2", type="webhook", config={}),
        ],
        edges=[Edge(**{"from": "1", "to": "2"})],
    )
    result = validate_workflow(wf)
    assert any(i.code == "TRIGGER_HAS_INCOMING_EDGE" for i in result.issues)


def test_cycle_detection():
    wf = Workflow(
        name="test",
        nodes=[
            Node(id="1", type="webhook", config={}),
            Node(id="2", type="slack_message", config={"channel_id": "#a"}),
            Node(id="3", type="slack_message", config={"channel_id": "#b"}),
        ],
        edges=[
            Edge(**{"from": "1", "to": "2"}),
            Edge(**{"from": "2", "to": "3"}),
            Edge(**{"from": "3", "to": "2"}),
        ],
    )
    result = validate_workflow(wf)
    assert any(i.code == "CYCLE_DETECTED" for i in result.issues)