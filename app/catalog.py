from pydantic import BaseModel
import re


class ConfigField(BaseModel):
    required: bool = False
    pattern: str | None = None
    description: str = ""

    def matches(self, value) -> bool:
        if not self.pattern:
            return True
        return bool(re.match(self.pattern, str(value)))


class CatalogEntry(BaseModel):
    type: str
    description: str
    category: str  # "trigger" | "action"
    config_schema: dict[str, ConfigField]


CATALOG: dict[str, CatalogEntry] = {
    "gmail_trigger": CatalogEntry(
        type="gmail_trigger", description="Triggers when a new email arrives", category="trigger",
        config_schema={"sender_filter": ConfigField(required=True, description="Email address or domain to filter on")},
    ),
    "webhook": CatalogEntry(
        type="webhook", description="Receive HTTP requests", category="trigger", config_schema={},
    ),
    "slack_message": CatalogEntry(
        type="slack_message", description="Send a Slack message", category="action",
        config_schema={
            "channel_id": ConfigField(required=True, pattern=r"^#?[\w-]+$", description="Slack channel name or ID"),
            "message_template": ConfigField(required=False, description="Message text, supports {{variables}}"),
        },
    ),
    "notion_create_page": CatalogEntry(
        type="notion_create_page", description="Create a Notion page", category="action",
        config_schema={
            "database_id": ConfigField(required=True, description="Target Notion database ID"),
            "title_template": ConfigField(required=False, description="Page title, supports {{variables}}"),
        },
    ),
    "discord_message": CatalogEntry(
        type="discord_message", description="Send a Discord message", category="action",
        config_schema={"channel_id": ConfigField(required=True, description="Discord channel ID")},
    ),
    "teams_message": CatalogEntry(
        type="teams_message", description="Send a Microsoft Teams message", category="action",
        config_schema={"channel_id": ConfigField(required=True, description="Teams channel ID")},
    ),
    "delay": CatalogEntry(
        type="delay", description="Wait for a duration before continuing", category="action",
        config_schema={"duration_seconds": ConfigField(required=True, pattern=r"^\d+$", description="Delay in seconds")},
    ),
    "condition": CatalogEntry(
        type="condition", description="Branch based on a condition expression", category="action",
        config_schema={"expression": ConfigField(required=True, description="Boolean expression to evaluate")},
    ),
}

TRIGGER_TYPES = {k for k, v in CATALOG.items() if v.category == "trigger"}


def get_catalog_entry(node_type: str) -> CatalogEntry | None:
    return CATALOG.get(node_type)


def search_nodes(query: str) -> list[CatalogEntry]:
    q = query.lower()
    return [e for e in CATALOG.values() if q in e.type.lower() or q in e.description.lower()]


def _build_catalog_prompt_text() -> str:
    lines = []
    for entry in CATALOG.values():
        fields = ", ".join(
            f"{name}{'*' if spec.required else ''}" for name, spec in entry.config_schema.items()
        ) or "none"
        lines.append(f"- {entry.type} ({entry.category}): {entry.description}. Config fields: {fields} (* = required)")
    return "\n".join(lines)


CATALOG_PROMPT_TEXT = _build_catalog_prompt_text()