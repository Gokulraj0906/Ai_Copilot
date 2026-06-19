"""
RAG (Retrieval-Augmented Generation) layer.

Instead of dumping the full 50-node catalog into every LLM prompt
(which wastes tokens and dilutes focus), we:

  1. Parse the user instruction to identify mentioned services/verbs.
  2. Retrieve the most relevant catalog nodes (keyword-weighted search).
  3. Always inject the FULL set of trigger nodes so the LLM can choose
     the right starting point.
  4. Return a compact catalog_text that is injected into the system prompt.

No custom LLM / fine-tuning / LoRA — purely prompt engineering + retrieval.
"""

from __future__ import annotations
import re
from app.core.catalog import (
    CATALOG,
    CatalogEntry,
    search_nodes,
    TRIGGER_TYPES,
)

# ─── Service / integration keywords ──────────────────────────────────────────
# Maps plain-English words a user might write → catalog capability keywords.
# When a match is found we boost retrieval for that keyword.

_KEYWORD_MAP: dict[str, list[str]] = {
    # messaging
    "whatsapp":   ["whatsapp"],
    "wa":         ["whatsapp"],
    "slack":      ["slack"],
    "telegram":   ["telegram"],
    "sms":        ["sms"],
    "email":      ["email"],
    "gmail":      ["gmail"],
    "discord":    ["discord"],
    "teams":      ["teams"],
    # payments
    "razorpay":   ["razorpay", "payment link", "india payment"],
    "payment":    ["razorpay", "payment link", "payment"],
    "pay":        ["razorpay", "payment link", "payment"],
    "invoice":    ["razorpay", "invoice", "pdf"],
    # logistics
    "delhivery":  ["delhivery", "logistics", "shipment"],
    "shiprocket": ["shiprocket", "shipping"],
    "ship":       ["shipment", "delhivery", "shiprocket"],
    "deliver":    ["delivery", "delhivery", "shiprocket"],
    "courier":    ["courier", "delhivery", "shiprocket"],
    "dispatch":   ["order dispatch", "delhivery"],
    # productivity
    "notion":     ["notion"],
    "sheets":     ["google sheets"],
    "spreadsheet":["google sheets"],
    "airtable":   ["airtable"],
    "jira":       ["jira"],
    "trello":     ["trello"],
    "github":     ["github"],
    "linear":     ["linear"],
    # crm
    "hubspot":    ["hubspot"],
    "salesforce": ["salesforce"],
    "zoho":       ["zoho"],
    "freshdesk":  ["freshdesk"],
    "zendesk":    ["zendesk"],
    # schedule / trigger
    "schedule":   ["schedule", "cron"],
    "daily":      ["schedule", "cron"],
    "weekly":     ["schedule", "cron"],
    "form":       ["typeform", "form submission"],
    "shopify":    ["shopify"],
    "woocommerce":["woocommerce"],
    # cloud / data
    "s3":         ["s3", "aws"],
    "drive":      ["google drive"],
    "database":   ["database", "sql"],
    "pdf":        ["pdf", "invoice"],
    "ai":         ["ai", "gpt", "openai"],
    "gpt":        ["ai", "gpt", "openai"],
    # calendar
    "calendar":   ["google calendar", "schedule"],
    "zoom":       ["zoom"],
    "meeting":    ["zoom", "google calendar"],
    # social
    "twitter":    ["twitter"],
    "instagram":  ["instagram"],
    "mailchimp":  ["mailchimp"],
}


def _extract_keywords(instruction: str) -> list[str]:
    """Return a flat list of capability keywords inferred from the instruction."""
    text = instruction.lower()
    found: list[str] = []
    for word, caps in _KEYWORD_MAP.items():
        # whole-word match to avoid "pay" inside "payment" triggering twice
        if re.search(rf"\b{re.escape(word)}\b", text):
            found.extend(caps)
    # de-dup while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for k in found:
        if k not in seen:
            seen.add(k)
            result.append(k)
    return result


def retrieve_relevant_nodes(instruction: str, top_k: int = 16) -> list[CatalogEntry]:
    """
    Retrieve the most relevant catalog nodes for a user instruction.

    Strategy:
      • Always include all trigger nodes (small set, always needed).
      • Search with each extracted keyword and accumulate scored nodes.
      • Fall back to full-text search on the raw instruction.
      • De-duplicate and cap at top_k.
    """
    # Step 1: always include triggers
    trigger_entries = [e for e in CATALOG.values() if e.category == "trigger"]

    # Step 2: keyword-based retrieval
    keywords = _extract_keywords(instruction)
    scored: dict[str, tuple[int, CatalogEntry]] = {}

    for kw in keywords:
        for entry in search_nodes(kw, top_k=10):
            if entry.type in scored:
                scored[entry.type] = (scored[entry.type][0] + 1, entry)
            else:
                scored[entry.type] = (1, entry)

    # Step 3: also search the raw instruction (catches multi-word phrases)
    for entry in search_nodes(instruction, top_k=8):
        if entry.type in scored:
            scored[entry.type] = (scored[entry.type][0] + 2, entry)
        else:
            scored[entry.type] = (2, entry)

    # Step 4: merge triggers + scored actions, deduplicated
    sorted_actions = sorted(scored.values(), key=lambda x: x[0], reverse=True)
    action_entries = [e for _, e in sorted_actions if e.category == "action"]

    # triggers first, then top actions
    seen: set[str] = set()
    result: list[CatalogEntry] = []
    for e in trigger_entries + action_entries:
        if e.type not in seen:
            seen.add(e.type)
            result.append(e)

    return result[:top_k]


def build_rag_catalog_text(instruction: str) -> str:
    """
    Build a compact catalog_text injected into every LLM system prompt.
    Only contains nodes relevant to the instruction — prevents hallucination
    of non-existent node types and keeps prompts focused.
    """
    nodes = retrieve_relevant_nodes(instruction)
    lines = []
    for entry in nodes:
        fields = ", ".join(
            f"{name}{'*' if spec.required else ''}"
            for name, spec in entry.config_schema.items()
        ) or "none"
        lines.append(
            f"- {entry.type} ({entry.category}): {entry.description}. "
            f"Config fields: {fields} (* = required)"
        )
    return "\n".join(lines)
