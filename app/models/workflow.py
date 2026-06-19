from pydantic import BaseModel, Field
from typing import Any
from enum import Enum


class NodeType(str, Enum):
    # ── Triggers ──────────────────────────────────────────────────────────────
    GMAIL_TRIGGER              = "gmail_trigger"
    WEBHOOK                    = "webhook"
    WHATSAPP_TRIGGER           = "whatsapp_trigger"
    SCHEDULE_TRIGGER           = "schedule_trigger"
    GOOGLE_SHEETS_TRIGGER      = "google_sheets_trigger"
    TYPEFORM_TRIGGER           = "typeform_trigger"
    RAZORPAY_TRIGGER           = "razorpay_trigger"
    STRIPE_TRIGGER             = "stripe_trigger"
    WOOCOMMERCE_TRIGGER        = "woocommerce_trigger"
    SHOPIFY_TRIGGER            = "shopify_trigger"

    # ── Messaging ─────────────────────────────────────────────────────────────
    SLACK_MESSAGE              = "slack_message"
    DISCORD_MESSAGE            = "discord_message"
    TEAMS_MESSAGE              = "teams_message"
    WHATSAPP_MESSAGE           = "whatsapp_message"
    SMS_SEND                   = "sms_send"
    TELEGRAM_MESSAGE           = "telegram_message"
    EMAIL_SEND                 = "email_send"
    PUSH_NOTIFICATION          = "push_notification"

    # ── Productivity / Docs ───────────────────────────────────────────────────
    NOTION_CREATE_PAGE         = "notion_create_page"
    GOOGLE_SHEETS_APPEND       = "google_sheets_append"
    GOOGLE_DOCS_CREATE         = "google_docs_create"
    AIRTABLE_CREATE_RECORD     = "airtable_create_record"
    JIRA_CREATE_ISSUE          = "jira_create_issue"
    TRELLO_CREATE_CARD         = "trello_create_card"
    LINEAR_CREATE_ISSUE        = "linear_create_issue"
    GITHUB_CREATE_ISSUE        = "github_create_issue"

    # ── CRM / Support ─────────────────────────────────────────────────────────
    HUBSPOT_CREATE_CONTACT     = "hubspot_create_contact"
    SALESFORCE_CREATE_LEAD     = "salesforce_create_lead"
    ZOHO_CRM_CREATE_LEAD       = "zoho_crm_create_lead"
    FRESHDESK_CREATE_TICKET    = "freshdesk_create_ticket"
    ZENDESK_CREATE_TICKET      = "zendesk_create_ticket"

    # ── Payments & Logistics ──────────────────────────────────────────────────
    RAZORPAY_CREATE_PAYMENT_LINK = "razorpay_create_payment_link"
    DELHIVERY_CREATE_SHIPMENT  = "delhivery_create_shipment"
    SHIPROCKET_CREATE_ORDER    = "shiprocket_create_order"
    DUNZO_CREATE_TASK          = "dunzo_create_task"

    # ── Data / Transform / Logic ──────────────────────────────────────────────
    DELAY                      = "delay"
    CONDITION                  = "condition"
    SET_VARIABLE               = "set_variable"
    HTTP_REQUEST               = "http_request"
    JSON_TRANSFORM             = "json_transform"
    PDF_GENERATE               = "pdf_generate"

    # ── Cloud / Storage ───────────────────────────────────────────────────────
    GOOGLE_DRIVE_UPLOAD        = "google_drive_upload"
    S3_UPLOAD                  = "s3_upload"
    DATABASE_INSERT            = "database_insert"

    # ── AI / ML ───────────────────────────────────────────────────────────────
    OPENAI_COMPLETION          = "openai_completion"
    SENTIMENT_ANALYSIS         = "sentiment_analysis"

    # ── Calendar / Meetings ───────────────────────────────────────────────────
    GOOGLE_CALENDAR_CREATE_EVENT = "google_calendar_create_event"
    ZOOM_CREATE_MEETING        = "zoom_create_meeting"
    CALENDLY_CREATE_INVITE     = "calendly_create_invite"

    # ── Social / Marketing ────────────────────────────────────────────────────
    TWITTER_POST               = "twitter_post"
    INSTAGRAM_POST             = "instagram_post"
    MAILCHIMP_ADD_SUBSCRIBER   = "mailchimp_add_subscriber"


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


class NodeExecutionResult(BaseModel):
    node_id: str
    node_type: str
    status: str   # "success" | "skipped" | "error"
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class WorkflowExecutionResult(BaseModel):
    workflow_id: str
    status: str   # "completed" | "failed"
    steps: list[NodeExecutionResult]
