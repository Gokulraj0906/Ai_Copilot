from pydantic import BaseModel, Field
from typing import Any
from enum import Enum


class NodeType(str, Enum):
    GMAIL_TRIGGER = "gmail_trigger"
    SLACK_MESSAGE = "slack_message"
    NOTION_CREATE_PAGE = "notion_create_page"
    WEBHOOK = "webhook"
    DISCORD_MESSAGE = "discord_message"
    TEAMS_MESSAGE = "teams_message"
    DELAY = "delay"
    CONDITION = "condition"


class Node(BaseModel):
    id: str
    type: NodeType
    config: dict[str, Any] = Field(default_factory=dict)
    label: str | None = None


class Edge(BaseModel):
    from_: str = Field(alias="from")
    to: str

    model_config = {"populate_by_name": True}


class Workflow(BaseModel):
    name: str = "Untitled Workflow"
    nodes: list[Node]
    edges: list[Edge]

    model_config = {"populate_by_name": True}