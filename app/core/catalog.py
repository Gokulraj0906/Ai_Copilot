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
    category: str          # "trigger" | "action"
    config_schema: dict[str, ConfigField]
    capabilities: list[str] = []   # RAG: keywords used for semantic retrieval


# ─────────────────────────────────────────────────────────────────────────────
# CATALOG  –  all node types the platform supports.
# The LLM is only ever shown this list; it cannot invent nodes outside of it.
# ─────────────────────────────────────────────────────────────────────────────
CATALOG: dict[str, CatalogEntry] = {

    # ── TRIGGERS ─────────────────────────────────────────────────────────────
    "gmail_trigger": CatalogEntry(
        type="gmail_trigger",
        description="Triggers when a new email arrives in Gmail",
        category="trigger",
        config_schema={"sender_filter": ConfigField(required=True, description="Email address or domain to filter on")},
        capabilities=["email", "gmail", "inbox", "receive email", "new mail"],
    ),
    "webhook": CatalogEntry(
        type="webhook",
        description="Receive HTTP POST/GET requests from external systems",
        category="trigger",
        config_schema={"path": ConfigField(required=False, description="Custom webhook path suffix")},
        capabilities=["http", "webhook", "api call", "external trigger", "rest"],
    ),
    "whatsapp_trigger": CatalogEntry(
        type="whatsapp_trigger",
        description="Triggers when a WhatsApp message is received via WhatsApp Business API",
        category="trigger",
        config_schema={
            "phone_number_id": ConfigField(required=True, description="WhatsApp Business phone number ID"),
            "keyword_filter": ConfigField(required=False, description="Optional keyword to filter messages"),
        },
        capabilities=["whatsapp", "chat", "message", "order", "customer message", "inbound message"],
    ),
    "schedule_trigger": CatalogEntry(
        type="schedule_trigger",
        description="Triggers on a recurring cron schedule (e.g. every day at 9 am)",
        category="trigger",
        config_schema={"cron_expression": ConfigField(required=True, description="Cron expression e.g. '0 9 * * *'")},
        capabilities=["schedule", "cron", "recurring", "daily", "weekly", "timer", "interval"],
    ),
    "google_sheets_trigger": CatalogEntry(
        type="google_sheets_trigger",
        description="Triggers when a new row is added to a Google Sheet",
        category="trigger",
        config_schema={
            "spreadsheet_id": ConfigField(required=True, description="Google Spreadsheet ID"),
            "sheet_name": ConfigField(required=False, description="Sheet tab name, defaults to first sheet"),
        },
        capabilities=["google sheets", "spreadsheet", "new row", "form response", "data entry"],
    ),
    "typeform_trigger": CatalogEntry(
        type="typeform_trigger",
        description="Triggers when a Typeform form is submitted",
        category="trigger",
        config_schema={"form_id": ConfigField(required=True, description="Typeform form ID")},
        capabilities=["typeform", "form submission", "survey", "lead form"],
    ),
    "razorpay_trigger": CatalogEntry(
        type="razorpay_trigger",
        description="Triggers on Razorpay payment events: payment.captured, payment.failed, refund.created",
        category="trigger",
        config_schema={
            "event_type": ConfigField(required=True, description="payment.captured | payment.failed | refund.created"),
            "webhook_secret": ConfigField(required=False, description="Razorpay webhook secret"),
        },
        capabilities=["razorpay", "payment received", "payment captured", "payment gateway", "india payment", "paid"],
    ),
    "stripe_trigger": CatalogEntry(
        type="stripe_trigger",
        description="Triggers on Stripe payment or subscription events",
        category="trigger",
        config_schema={
            "event_type": ConfigField(required=True, description="e.g. payment_intent.succeeded"),
            "webhook_secret": ConfigField(required=False, description="Stripe webhook signing secret"),
        },
        capabilities=["stripe", "payment", "subscription", "card payment", "checkout"],
    ),
    "woocommerce_trigger": CatalogEntry(
        type="woocommerce_trigger",
        description="Triggers on WooCommerce order events (new order, status change)",
        category="trigger",
        config_schema={
            "store_url": ConfigField(required=True, description="WooCommerce store base URL"),
            "event_type": ConfigField(required=True, description="order.created | order.updated | order.completed"),
        },
        capabilities=["woocommerce", "ecommerce", "order", "shop", "online store", "wordpress"],
    ),
    "shopify_trigger": CatalogEntry(
        type="shopify_trigger",
        description="Triggers on Shopify store events (new order, fulfillment, customer created)",
        category="trigger",
        config_schema={
            "shop_domain": ConfigField(required=True, description="e.g. mystore.myshopify.com"),
            "event_type": ConfigField(required=True, description="orders/create | orders/fulfilled | customers/create"),
        },
        capabilities=["shopify", "ecommerce", "order", "fulfillment", "product", "customer"],
    ),

    # ── MESSAGING ACTIONS ─────────────────────────────────────────────────────
    "slack_message": CatalogEntry(
        type="slack_message",
        description="Send a message to a Slack channel or user",
        category="action",
        config_schema={
            "channel_id": ConfigField(required=True, pattern=r"^#?[\w-]+$", description="Slack channel name or ID"),
            "message_template": ConfigField(required=False, description="Message text, supports {{variables}}"),
        },
        capabilities=["slack", "team chat", "notify team", "send message", "alert"],
    ),
    "discord_message": CatalogEntry(
        type="discord_message",
        description="Send a message to a Discord channel",
        category="action",
        config_schema={"channel_id": ConfigField(required=True, description="Discord channel ID")},
        capabilities=["discord", "community", "bot message"],
    ),
    "teams_message": CatalogEntry(
        type="teams_message",
        description="Send a Microsoft Teams channel message",
        category="action",
        config_schema={"channel_id": ConfigField(required=True, description="Teams channel ID")},
        capabilities=["teams", "microsoft teams", "office", "enterprise chat"],
    ),
    "whatsapp_message": CatalogEntry(
        type="whatsapp_message",
        description="Send a WhatsApp message via WhatsApp Business API",
        category="action",
        config_schema={
            "phone_number_id": ConfigField(required=True, description="WhatsApp Business phone number ID"),
            "to": ConfigField(required=True, description="Recipient phone with country code e.g. 919876543210"),
            "message_template": ConfigField(required=True, description="Message text, supports {{variables}}"),
        },
        capabilities=["whatsapp", "chat", "notify customer", "order update", "send message"],
    ),
    "sms_send": CatalogEntry(
        type="sms_send",
        description="Send an SMS via Twilio or AWS SNS",
        category="action",
        config_schema={
            "to": ConfigField(required=True, description="Recipient phone with country code"),
            "message_template": ConfigField(required=True, description="SMS body, supports {{variables}}"),
            "provider": ConfigField(required=False, description="twilio | aws_sns  (default: twilio)"),
        },
        capabilities=["sms", "text message", "mobile", "notify", "otp"],
    ),
    "telegram_message": CatalogEntry(
        type="telegram_message",
        description="Send a Telegram message via bot",
        category="action",
        config_schema={
            "chat_id": ConfigField(required=True, description="Telegram chat ID or @channel_username"),
            "message_template": ConfigField(required=False, description="Message text, supports {{variables}}"),
        },
        capabilities=["telegram", "bot", "channel", "notification"],
    ),
    "email_send": CatalogEntry(
        type="email_send",
        description="Send an email via SMTP, SendGrid, or SES",
        category="action",
        config_schema={
            "to": ConfigField(required=True, description="Recipient email or {{variable}}"),
            "subject": ConfigField(required=True, description="Email subject line"),
            "body_template": ConfigField(required=False, description="Email body, supports {{variables}}"),
            "provider": ConfigField(required=False, description="smtp | sendgrid | ses  (default: smtp)"),
        },
        capabilities=["email", "send email", "notify", "customer email"],
    ),
    "push_notification": CatalogEntry(
        type="push_notification",
        description="Send a mobile push notification via Firebase (FCM)",
        category="action",
        config_schema={
            "device_token": ConfigField(required=True, description="FCM device token or {{variable}}"),
            "title": ConfigField(required=True, description="Notification title"),
            "body": ConfigField(required=False, description="Notification body text"),
        },
        capabilities=["push", "mobile notification", "firebase", "fcm", "app notification"],
    ),

    # ── PRODUCTIVITY / DOCS ───────────────────────────────────────────────────
    "notion_create_page": CatalogEntry(
        type="notion_create_page",
        description="Create a new page or database entry in Notion",
        category="action",
        config_schema={
            "database_id": ConfigField(required=True, description="Target Notion database ID"),
            "title_template": ConfigField(required=False, description="Page title, supports {{variables}}"),
        },
        capabilities=["notion", "database", "record", "note", "wiki", "document"],
    ),
    "google_sheets_append": CatalogEntry(
        type="google_sheets_append",
        description="Append a new row to a Google Sheet",
        category="action",
        config_schema={
            "spreadsheet_id": ConfigField(required=True, description="Google Spreadsheet ID"),
            "sheet_name": ConfigField(required=False, description="Sheet tab name"),
            "row_data": ConfigField(required=True, description="JSON object of column→value to append"),
        },
        capabilities=["google sheets", "spreadsheet", "log", "record data", "append row"],
    ),
    "google_docs_create": CatalogEntry(
        type="google_docs_create",
        description="Create a new Google Doc with content",
        category="action",
        config_schema={
            "title": ConfigField(required=True, description="Document title"),
            "content_template": ConfigField(required=False, description="Document content, supports {{variables}}"),
            "folder_id": ConfigField(required=False, description="Google Drive folder ID"),
        },
        capabilities=["google docs", "document", "report", "write", "create doc"],
    ),
    "airtable_create_record": CatalogEntry(
        type="airtable_create_record",
        description="Create a new record in an Airtable base",
        category="action",
        config_schema={
            "base_id": ConfigField(required=True, description="Airtable base ID"),
            "table_name": ConfigField(required=True, description="Table name"),
            "fields": ConfigField(required=True, description="JSON object of field→value"),
        },
        capabilities=["airtable", "database", "record", "crm", "table", "spreadsheet"],
    ),
    "jira_create_issue": CatalogEntry(
        type="jira_create_issue",
        description="Create a new Jira issue or bug ticket",
        category="action",
        config_schema={
            "project_key": ConfigField(required=True, description="Jira project key e.g. ENG"),
            "summary": ConfigField(required=True, description="Issue title/summary"),
            "issue_type": ConfigField(required=False, description="Bug | Task | Story  (default: Task)"),
            "description": ConfigField(required=False, description="Issue description"),
        },
        capabilities=["jira", "ticket", "bug", "task", "issue tracking", "sprint"],
    ),
    "trello_create_card": CatalogEntry(
        type="trello_create_card",
        description="Create a new card on a Trello board list",
        category="action",
        config_schema={
            "list_id": ConfigField(required=True, description="Trello list ID"),
            "card_name": ConfigField(required=True, description="Card title"),
            "description": ConfigField(required=False, description="Card description"),
        },
        capabilities=["trello", "kanban", "card", "task", "project management"],
    ),
    "linear_create_issue": CatalogEntry(
        type="linear_create_issue",
        description="Create a Linear issue for engineering teams",
        category="action",
        config_schema={
            "team_id": ConfigField(required=True, description="Linear team ID"),
            "title": ConfigField(required=True, description="Issue title"),
            "priority": ConfigField(required=False, description="urgent | high | medium | low"),
        },
        capabilities=["linear", "issue", "engineering", "bug", "feature"],
    ),
    "github_create_issue": CatalogEntry(
        type="github_create_issue",
        description="Create a GitHub issue in a repository",
        category="action",
        config_schema={
            "owner": ConfigField(required=True, description="GitHub repo owner/org"),
            "repo": ConfigField(required=True, description="Repository name"),
            "title": ConfigField(required=True, description="Issue title"),
            "body": ConfigField(required=False, description="Issue description"),
            "labels": ConfigField(required=False, description="Comma-separated label names"),
        },
        capabilities=["github", "issue", "code", "repository", "dev", "bug report"],
    ),

    # ── CRM / SUPPORT ─────────────────────────────────────────────────────────
    "hubspot_create_contact": CatalogEntry(
        type="hubspot_create_contact",
        description="Create or update a contact in HubSpot CRM",
        category="action",
        config_schema={
            "email": ConfigField(required=True, description="Contact email address"),
            "firstname": ConfigField(required=False, description="First name"),
            "lastname": ConfigField(required=False, description="Last name"),
            "phone": ConfigField(required=False, description="Phone number"),
        },
        capabilities=["hubspot", "crm", "contact", "lead", "sales", "customer"],
    ),
    "salesforce_create_lead": CatalogEntry(
        type="salesforce_create_lead",
        description="Create a lead or opportunity in Salesforce",
        category="action",
        config_schema={
            "first_name": ConfigField(required=False, description="Lead first name"),
            "last_name": ConfigField(required=True, description="Lead last name"),
            "email": ConfigField(required=True, description="Lead email"),
            "company": ConfigField(required=True, description="Company name"),
        },
        capabilities=["salesforce", "crm", "lead", "opportunity", "sales pipeline"],
    ),
    "zoho_crm_create_lead": CatalogEntry(
        type="zoho_crm_create_lead",
        description="Create a lead in Zoho CRM",
        category="action",
        config_schema={
            "last_name": ConfigField(required=True, description="Lead last name"),
            "email": ConfigField(required=False, description="Lead email"),
            "phone": ConfigField(required=False, description="Phone number"),
        },
        capabilities=["zoho", "crm", "lead", "india crm", "sales"],
    ),
    "freshdesk_create_ticket": CatalogEntry(
        type="freshdesk_create_ticket",
        description="Create a support ticket in Freshdesk",
        category="action",
        config_schema={
            "subject": ConfigField(required=True, description="Ticket subject"),
            "description": ConfigField(required=True, description="Ticket description"),
            "email": ConfigField(required=True, description="Customer email"),
            "priority": ConfigField(required=False, description="1=low 2=medium 3=high 4=urgent"),
        },
        capabilities=["freshdesk", "support ticket", "customer support", "helpdesk"],
    ),
    "zendesk_create_ticket": CatalogEntry(
        type="zendesk_create_ticket",
        description="Create a Zendesk support ticket",
        category="action",
        config_schema={
            "subject": ConfigField(required=True, description="Ticket subject"),
            "description": ConfigField(required=True, description="Ticket body"),
            "requester_email": ConfigField(required=True, description="Requester email address"),
        },
        capabilities=["zendesk", "support", "helpdesk", "customer service", "ticket"],
    ),

    # ── PAYMENTS & LOGISTICS ──────────────────────────────────────────────────
    "razorpay_create_payment_link": CatalogEntry(
        type="razorpay_create_payment_link",
        description="Create a Razorpay payment link and return the URL to share with the customer",
        category="action",
        config_schema={
            "amount": ConfigField(required=True, description="Amount in paise (e.g. 50000 = ₹500)"),
            "currency": ConfigField(required=False, description="Currency code, default: INR"),
            "description": ConfigField(required=False, description="Payment description shown to customer"),
            "customer_phone": ConfigField(required=False, description="Customer phone for pre-filling"),
            "customer_email": ConfigField(required=False, description="Customer email for pre-filling"),
        },
        capabilities=["razorpay", "payment link", "collect payment", "india payment", "invoice", "request money"],
    ),
    "delhivery_create_shipment": CatalogEntry(
        type="delhivery_create_shipment",
        description="Create a Delhivery shipment/waybill to dispatch a package",
        category="action",
        config_schema={
            "client_name": ConfigField(required=True, description="Delhivery client name"),
            "waybill": ConfigField(required=False, description="Waybill number (auto-generated if blank)"),
            "pickup_pincode": ConfigField(required=True, description="Pickup PIN code"),
            "recipient_name": ConfigField(required=True, description="Recipient full name"),
            "recipient_address": ConfigField(required=True, description="Recipient address"),
            "recipient_pincode": ConfigField(required=True, description="Recipient PIN code"),
            "recipient_phone": ConfigField(required=True, description="Recipient phone number"),
            "cod_amount": ConfigField(required=False, description="COD amount in INR, 0 for prepaid"),
            "weight": ConfigField(required=False, description="Package weight in grams"),
        },
        capabilities=["delhivery", "logistics", "shipment", "delivery", "courier", "india logistics", "order dispatch"],
    ),
    "shiprocket_create_order": CatalogEntry(
        type="shiprocket_create_order",
        description="Create a Shiprocket order for multi-courier delivery",
        category="action",
        config_schema={
            "order_id": ConfigField(required=True, description="Your internal order ID"),
            "pickup_location": ConfigField(required=True, description="Pickup location name in Shiprocket"),
            "billing_customer_name": ConfigField(required=True, description="Customer name"),
            "billing_address": ConfigField(required=True, description="Billing address"),
            "billing_pincode": ConfigField(required=True, description="Billing PIN code"),
            "billing_phone": ConfigField(required=True, description="Customer phone"),
            "order_items": ConfigField(required=True, description="JSON array [{name,sku,units,selling_price}]"),
            "payment_method": ConfigField(required=False, description="Prepaid | COD"),
        },
        capabilities=["shiprocket", "shipping", "courier", "delivery", "logistics", "order fulfilment"],
    ),
    "dunzo_create_task": CatalogEntry(
        type="dunzo_create_task",
        description="Create a hyperlocal delivery task on Dunzo",
        category="action",
        config_schema={
            "pickup_lat": ConfigField(required=True, description="Pickup latitude"),
            "pickup_lng": ConfigField(required=True, description="Pickup longitude"),
            "delivery_lat": ConfigField(required=True, description="Delivery latitude"),
            "delivery_lng": ConfigField(required=True, description="Delivery longitude"),
            "reference_id": ConfigField(required=False, description="Your order reference ID"),
        },
        capabilities=["dunzo", "hyperlocal", "delivery", "last mile", "local delivery"],
    ),

    # ── DATA / TRANSFORM / LOGIC ──────────────────────────────────────────────
    "delay": CatalogEntry(
        type="delay",
        description="Wait for a specified duration before continuing",
        category="action",
        config_schema={"duration_seconds": ConfigField(required=True, pattern=r"^\d+$", description="Delay in seconds")},
        capabilities=["wait", "pause", "delay", "timer", "sleep"],
    ),
    "condition": CatalogEntry(
        type="condition",
        description="Branch the workflow based on a boolean expression",
        category="action",
        config_schema={"expression": ConfigField(required=True, description="Boolean expression e.g. {{amount}} > 500")},
        capabilities=["if", "condition", "branch", "filter", "check", "logic"],
    ),
    "set_variable": CatalogEntry(
        type="set_variable",
        description="Set or compute a workflow variable for use in later steps",
        category="action",
        config_schema={
            "variable_name": ConfigField(required=True, description="Variable name to set"),
            "value_expression": ConfigField(required=True, description="Value or expression e.g. {{amount}} * 1.18"),
        },
        capabilities=["variable", "set value", "transform", "calculate", "assign"],
    ),
    "http_request": CatalogEntry(
        type="http_request",
        description="Make an arbitrary HTTP GET/POST request to any REST API",
        category="action",
        config_schema={
            "url": ConfigField(required=True, description="Target URL, supports {{variables}}"),
            "method": ConfigField(required=False, description="GET | POST | PUT | PATCH | DELETE"),
            "headers": ConfigField(required=False, description="JSON object of headers"),
            "body": ConfigField(required=False, description="Request body JSON, supports {{variables}}"),
        },
        capabilities=["api", "http", "rest", "custom api", "webhook call", "integration", "external api"],
    ),
    "json_transform": CatalogEntry(
        type="json_transform",
        description="Extract or reshape fields from JSON data",
        category="action",
        config_schema={
            "input_expression": ConfigField(required=True, description="JSONPath e.g. {{payload.order.id}}"),
            "output_variable": ConfigField(required=True, description="Variable to store the result"),
        },
        capabilities=["json", "transform", "parse", "extract", "map data"],
    ),
    "pdf_generate": CatalogEntry(
        type="pdf_generate",
        description="Generate a PDF document from an HTML template (invoices, receipts, reports)",
        category="action",
        config_schema={
            "html_template": ConfigField(required=True, description="HTML content with {{variables}}"),
            "output_filename": ConfigField(required=False, description="e.g. invoice_{{order_id}}.pdf"),
        },
        capabilities=["pdf", "invoice", "receipt", "document", "report", "generate pdf"],
    ),

    # ── CLOUD / STORAGE ───────────────────────────────────────────────────────
    "google_drive_upload": CatalogEntry(
        type="google_drive_upload",
        description="Upload a file to Google Drive",
        category="action",
        config_schema={
            "file_url": ConfigField(required=True, description="Source file URL to upload"),
            "folder_id": ConfigField(required=False, description="Target Google Drive folder ID"),
            "filename": ConfigField(required=False, description="Filename to save as"),
        },
        capabilities=["google drive", "upload", "storage", "file", "backup"],
    ),
    "s3_upload": CatalogEntry(
        type="s3_upload",
        description="Upload a file to AWS S3 or compatible object storage",
        category="action",
        config_schema={
            "bucket": ConfigField(required=True, description="S3 bucket name"),
            "key": ConfigField(required=True, description="Object key (path in bucket)"),
            "file_url": ConfigField(required=True, description="Source file URL to upload"),
        },
        capabilities=["s3", "aws", "storage", "upload", "file", "object storage"],
    ),
    "database_insert": CatalogEntry(
        type="database_insert",
        description="Insert a row into a PostgreSQL or MySQL database",
        category="action",
        config_schema={
            "table": ConfigField(required=True, description="Table name"),
            "data": ConfigField(required=True, description="JSON object of column→value"),
            "db_type": ConfigField(required=False, description="postgres | mysql  (default: postgres)"),
        },
        capabilities=["database", "sql", "insert", "store data", "log", "postgres", "mysql"],
    ),

    # ── AI / ML ───────────────────────────────────────────────────────────────
    "openai_completion": CatalogEntry(
        type="openai_completion",
        description="Call OpenAI GPT to generate text, classify, or summarize content",
        category="action",
        config_schema={
            "prompt_template": ConfigField(required=True, description="Prompt with {{variables}}"),
            "model": ConfigField(required=False, description="gpt-4o | gpt-4o-mini  (default: gpt-4o-mini)"),
            "output_variable": ConfigField(required=True, description="Variable to store AI response"),
        },
        capabilities=["ai", "gpt", "openai", "summarize", "classify", "generate text", "llm"],
    ),
    "sentiment_analysis": CatalogEntry(
        type="sentiment_analysis",
        description="Analyse sentiment of text (positive / negative / neutral)",
        category="action",
        config_schema={
            "text_variable": ConfigField(required=True, description="Variable containing text to analyse"),
            "output_variable": ConfigField(required=True, description="Variable to store sentiment result"),
        },
        capabilities=["sentiment", "emotion", "nlp", "feedback analysis", "review"],
    ),

    # ── CALENDAR / MEETINGS ───────────────────────────────────────────────────
    "google_calendar_create_event": CatalogEntry(
        type="google_calendar_create_event",
        description="Create a Google Calendar event",
        category="action",
        config_schema={
            "calendar_id": ConfigField(required=True, description="Calendar ID or 'primary'"),
            "summary": ConfigField(required=True, description="Event title"),
            "start_datetime": ConfigField(required=True, description="Start date-time ISO 8601"),
            "end_datetime": ConfigField(required=True, description="End date-time ISO 8601"),
            "attendees": ConfigField(required=False, description="Comma-separated attendee emails"),
        },
        capabilities=["google calendar", "meeting", "event", "schedule", "appointment"],
    ),
    "zoom_create_meeting": CatalogEntry(
        type="zoom_create_meeting",
        description="Create a Zoom meeting and return the join link",
        category="action",
        config_schema={
            "topic": ConfigField(required=True, description="Meeting topic"),
            "start_time": ConfigField(required=True, description="Start time ISO 8601"),
            "duration_minutes": ConfigField(required=False, description="Meeting duration in minutes"),
        },
        capabilities=["zoom", "meeting", "video call", "virtual meeting"],
    ),
    "calendly_create_invite": CatalogEntry(
        type="calendly_create_invite",
        description="Create a one-off Calendly scheduling link",
        category="action",
        config_schema={
            "event_type_uuid": ConfigField(required=True, description="Calendly event type UUID"),
            "invitee_email": ConfigField(required=True, description="Invitee email address"),
        },
        capabilities=["calendly", "scheduling", "booking", "appointment"],
    ),

    # ── SOCIAL / MARKETING ────────────────────────────────────────────────────
    "twitter_post": CatalogEntry(
        type="twitter_post",
        description="Post a tweet / X post",
        category="action",
        config_schema={"content": ConfigField(required=True, description="Tweet text (max 280 chars)")},
        capabilities=["twitter", "x", "tweet", "social media", "post"],
    ),
    "instagram_post": CatalogEntry(
        type="instagram_post",
        description="Publish an image post to an Instagram Business account",
        category="action",
        config_schema={
            "image_url": ConfigField(required=True, description="Public URL of the image"),
            "caption": ConfigField(required=False, description="Post caption text"),
        },
        capabilities=["instagram", "social media", "photo", "post", "marketing"],
    ),
    "mailchimp_add_subscriber": CatalogEntry(
        type="mailchimp_add_subscriber",
        description="Add or update a Mailchimp email subscriber",
        category="action",
        config_schema={
            "list_id": ConfigField(required=True, description="Mailchimp audience/list ID"),
            "email": ConfigField(required=True, description="Subscriber email address"),
            "merge_fields": ConfigField(required=False, description="JSON object {FNAME: John}"),
        },
        capabilities=["mailchimp", "email marketing", "newsletter", "subscriber", "mailing list"],
    ),
}

TRIGGER_TYPES = {k for k, v in CATALOG.items() if v.category == "trigger"}


# ─── lookup helpers ───────────────────────────────────────────────────────────

def get_catalog_entry(node_type: str) -> CatalogEntry | None:
    return CATALOG.get(node_type)


def search_nodes(query: str, top_k: int = 8) -> list[CatalogEntry]:
    """
    Keyword-weighted search across type name, description, and capabilities.
    Used by the RAG layer to inject only relevant nodes into the LLM context.
    """
    q = query.lower()
    scored: list[tuple[int, CatalogEntry]] = []
    for entry in CATALOG.values():
        score = 0
        if q in entry.type.lower():
            score += 4
        if q in entry.description.lower():
            score += 2
        for cap in entry.capabilities:
            if q in cap.lower() or cap.lower() in q:
                score += 1
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]


def _build_catalog_prompt_text() -> str:
    lines = []
    for entry in CATALOG.values():
        fields = ", ".join(
            f"{name}{'*' if spec.required else ''}" for name, spec in entry.config_schema.items()
        ) or "none"
        lines.append(
            f"- {entry.type} ({entry.category}): {entry.description}. Config fields: {fields} (* = required)"
        )
    return "\n".join(lines)


CATALOG_PROMPT_TEXT = _build_catalog_prompt_text()
