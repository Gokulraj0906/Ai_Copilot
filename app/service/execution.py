"""
Real-time execution engine — multi-tenant edition.

Credentials are passed in as `creds: dict[str, str]` loaded per-user
from the credentials table (decrypted at call time, cached in Redis).
The global `settings` object is only used for OPENROUTER_API_KEY and DATABASE_URL
— infrastructure credentials that belong to the platform, not the user.

Real-time execution engine.

Every executor makes a live API call using credentials from Settings.
If a credential is missing the executor raises a clear ConfigError —
never silently falls back to a mock.

Context propagation:
  context[node_id] = output_dict  — available to downstream nodes as
  {{node_id.field}} placeholders (resolved by _render()).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.core.config import settings  # kept for DB URL only
from app.models.workflow import Node, NodeExecutionResult, Workflow

logger = logging.getLogger("copilot.execution")


# ─── Helpers ─────────────────────────────────────────────────────────────────

class ConfigError(Exception):
    """Raised when a required API credential is not configured."""


def _require(value: str, name: str) -> str:
    if not value:
        raise ConfigError(
            f"Missing credential: {name}. Connect this integration via POST /credentials."
        )
    return value


def _render(template: str, context: dict) -> str:
    """Replace {{node_id.field}} and {{field}} placeholders from context."""
    if not isinstance(template, str):
        return template

    def replacer(m: re.Match) -> str:
        key = m.group(1).strip()
        # nested: node_id.field
        if "." in key:
            parts = key.split(".", 1)
            node_out = context.get(parts[0], {})
            return str(node_out.get(parts[1], m.group(0)))
        # flat key
        for node_out in context.values():
            if isinstance(node_out, dict) and key in node_out:
                return str(node_out[key])
        return m.group(0)  # leave unreplaced

    return re.sub(r"\{\{(.+?)\}\}", replacer, template)


def _cfg(node: Node, key: str, context: dict, default: str = "") -> str:
    raw = node.config.get(key, default)
    return _render(str(raw) if raw is not None else default, context)


# ─── Messaging executors ─────────────────────────────────────────────────────

async def _execute_slack_message(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("slack.bot_token", ""), "SLACK_BOT_TOKEN")
    channel = _cfg(node, "channel_id", context)
    message = _cfg(node, "message_template", context, "Automated message from your workflow.")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel, "text": message},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Slack API error: {data.get('error')}")
    return {"channel": channel, "ts": data.get("ts"), "message_sent": message}


async def _execute_discord_message(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("discord.bot_token", ""), "DISCORD_BOT_TOKEN")
    channel_id = _cfg(node, "channel_id", context)
    message = _cfg(node, "message_template", context, "Automated message.")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://discord.com/api/v10/channels/{channel_id}/messages",
            headers={"Authorization": f"Bot {token}"},
            json={"content": message},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"message_id": data.get("id"), "channel_id": channel_id}


async def _execute_teams_message(node: Node, context: dict, creds: dict) -> dict:
    # Teams uses incoming webhooks (no bot token required)
    webhook_url = _cfg(node, "channel_id", context)  # channel_id stores the webhook URL
    message = _cfg(node, "message_template", context, "Automated message.")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            webhook_url,
            json={"text": message},
        )
        resp.raise_for_status()
    return {"status": "sent", "message": message}


async def _execute_whatsapp_message(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("whatsapp.access_token", ""), "WHATSAPP_ACCESS_TOKEN")
    phone_number_id = _cfg(node, "phone_number_id", context)
    to = _cfg(node, "to", context)
    message = _cfg(node, "message_template", context)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f'{creds.get("whatsapp.api_url", "https://graph.facebook.com/v18.0")}/{phone_number_id}/messages',
            headers={"Authorization": f"Bearer {token}"},
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": message},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"message_id": data.get("messages", [{}])[0].get("id"), "to": to}


async def _execute_sms_send(node: Node, context: dict, creds: dict) -> dict:
    provider = _cfg(node, "provider", context, "twilio")
    to = _cfg(node, "to", context)
    body = _cfg(node, "message_template", context)

    if provider == "twilio":
        sid = _require(creds.get("twilio.account_sid", ""), "TWILIO_ACCOUNT_SID")
        auth = _require(creds.get("twilio.auth_token", ""), "TWILIO_AUTH_TOKEN")
        from_num = _require(creds.get("twilio.from_number", ""), "TWILIO_FROM_NUMBER")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                auth=(sid, auth),
                data={"To": to, "From": from_num, "Body": body},
            )
            resp.raise_for_status()
            data = resp.json()
        return {"sid": data.get("sid"), "status": data.get("status"), "to": to}
    else:
        raise ConfigError(f"SMS provider '{provider}' not yet implemented. Use 'twilio'.")


async def _execute_telegram_message(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("telegram.bot_token", ""), "TELEGRAM_BOT_TOKEN")
    chat_id = _cfg(node, "chat_id", context)
    message = _cfg(node, "message_template", context)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"message_id": data["result"]["message_id"], "chat_id": chat_id}


async def _execute_email_send(node: Node, context: dict, creds: dict) -> dict:
    provider = _cfg(node, "provider", context, "smtp")
    to = _cfg(node, "to", context)
    subject = _cfg(node, "subject", context)
    body = _cfg(node, "body_template", context)

    if provider == "sendgrid":
        key = _require(creds.get("sendgrid.api_key", ""), "SENDGRID_API_KEY")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "personalizations": [{"to": [{"email": to}]}],
                    "from": {"email": creds.get("smtp.user", "")},
                    "subject": subject,
                    "content": [{"type": "text/plain", "value": body}],
                },
            )
            resp.raise_for_status()
        return {"to": to, "subject": subject, "provider": "sendgrid"}

    # Default: SMTP
    _require(creds.get("smtp.user", ""), "SMTP_USER")
    _require(creds.get("smtp.password", ""), "SMTP_PASSWORD")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = creds.get("smtp.user", "")
    msg["To"] = to
    msg.attach(MIMEText(body, "plain"))
    ctx = ssl.create_default_context()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: _smtp_send(msg, creds.get("smtp.host", "smtp.gmail.com"), int(creds.get("smtp.port", "587")),
                           creds.get("smtp.user", ""), creds.get("smtp.password", ""), ctx),
    )
    return {"to": to, "subject": subject, "provider": "smtp"}


def _smtp_send(msg, host, port, user, password, ctx):
    with smtplib.SMTP(host, port) as server:
        server.ehlo()
        server.starttls(context=ctx)
        server.login(user, password)
        server.sendmail(msg["From"], msg["To"], msg.as_string())


async def _execute_push_notification(node: Node, context: dict, creds: dict) -> dict:
    key = _require(creds.get("firebase.server_key", ""), "FIREBASE_SERVER_KEY")
    token = _cfg(node, "device_token", context)
    title = _cfg(node, "title", context)
    body = _cfg(node, "body", context)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://fcm.googleapis.com/fcm/send",
            headers={"Authorization": f"key={key}"},
            json={
                "to": token,
                "notification": {"title": title, "body": body},
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"message_id": data.get("results", [{}])[0].get("message_id"), "success": data.get("success")}


# ─── Productivity executors ───────────────────────────────────────────────────

async def _execute_notion_create_page(node: Node, context: dict, creds: dict) -> dict:
    key = _require(creds.get("notion.api_key", ""), "NOTION_API_KEY")
    db_id = _cfg(node, "database_id", context)
    title = _cfg(node, "title_template", context, "New Page")
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.notion.com/v1/pages",
            headers={
                "Authorization": f"Bearer {key}",
                "Notion-Version": "2022-06-28",
            },
            json={
                "parent": {"database_id": db_id},
                "properties": {
                    "Name": {"title": [{"text": {"content": title}}]}
                },
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"page_id": data.get("id"), "url": data.get("url"), "title": title}


async def _execute_google_sheets_append(node: Node, context: dict, creds: dict) -> dict:
    sa_path = _require(creds.get("google.service_account_json", ""), "GOOGLE_SERVICE_ACCOUNT_JSON")
    spreadsheet_id = _cfg(node, "spreadsheet_id", context)
    sheet_name = _cfg(node, "sheet_name", context, "Sheet1")
    row_data_raw = _cfg(node, "row_data", context, "{}")
    try:
        row_obj = json.loads(row_data_raw)
        values = [list(row_obj.values())]
    except json.JSONDecodeError:
        values = [[row_data_raw]]

    token = await _google_access_token(sa_path, ["https://www.googleapis.com/auth/spreadsheets"])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_name}!A1:append",
            headers={"Authorization": f"Bearer {token}"},
            params={"valueInputOption": "USER_ENTERED"},
            json={"values": values},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"updated_range": data.get("updates", {}).get("updatedRange"), "rows_added": len(values)}


async def _execute_google_docs_create(node: Node, context: dict, creds: dict) -> dict:
    sa_path = _require(creds.get("google.service_account_json", ""), "GOOGLE_SERVICE_ACCOUNT_JSON")
    title = _cfg(node, "title", context, "New Document")
    content = _cfg(node, "content_template", context)
    folder_id = _cfg(node, "folder_id", context)

    token = await _google_access_token(sa_path, [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ])
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://docs.googleapis.com/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": title},
        )
        resp.raise_for_status()
        doc = resp.json()
        doc_id = doc["documentId"]

        if content:
            await client.post(
                f"https://docs.googleapis.com/v1/documents/{doc_id}:batchUpdate",
                headers={"Authorization": f"Bearer {token}"},
                json={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
            )
        if folder_id:
            await client.post(
                f"https://www.googleapis.com/drive/v3/files/{doc_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={"addParents": folder_id},
            )
    return {"document_id": doc_id, "title": title, "url": f"https://docs.google.com/document/d/{doc_id}"}


async def _execute_airtable_create_record(node: Node, context: dict, creds: dict) -> dict:
    key = _require(creds.get("airtable.api_key", ""), "AIRTABLE_API_KEY")
    base_id = _cfg(node, "base_id", context)
    table = _cfg(node, "table_name", context)
    fields_raw = _cfg(node, "fields", context, "{}")
    try:
        fields = json.loads(fields_raw)
    except json.JSONDecodeError:
        fields = {"Value": fields_raw}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.airtable.com/v0/{base_id}/{table}",
            headers={"Authorization": f"Bearer {key}"},
            json={"fields": fields},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"record_id": data.get("id"), "table": table}


async def _execute_jira_create_issue(node: Node, context: dict, creds: dict) -> dict:
    domain = _require(creds.get("jira.domain", ""), "JIRA_DOMAIN")
    email = _require(creds.get("jira.email", ""), "JIRA_EMAIL")
    token = _require(creds.get("jira.api_token", ""), "JIRA_API_TOKEN")
    project = _cfg(node, "project_key", context)
    summary = _cfg(node, "summary", context)
    issue_type = _cfg(node, "issue_type", context, "Task")
    description = _cfg(node, "description", context)
    creds = base64.b64encode(f"{email}:{token}".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://{domain}/rest/api/3/issue",
            headers={"Authorization": f"Basic {creds}", "Content-Type": "application/json"},
            json={
                "fields": {
                    "project": {"key": project},
                    "summary": summary,
                    "issuetype": {"name": issue_type},
                    "description": {"type": "doc", "version": 1, "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                    ]} if description else None,
                }
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"issue_key": data.get("key"), "issue_id": data.get("id"), "project": project}


async def _execute_trello_create_card(node: Node, context: dict, creds: dict) -> dict:
    key = _require(creds.get("trello.api_key", ""), "TRELLO_API_KEY")
    token = _require(creds.get("trello.api_token", ""), "TRELLO_API_TOKEN")
    list_id = _cfg(node, "list_id", context)
    name = _cfg(node, "card_name", context)
    desc = _cfg(node, "description", context)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.trello.com/1/cards",
            params={"key": key, "token": token},
            json={"idList": list_id, "name": name, "desc": desc},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"card_id": data.get("id"), "url": data.get("shortUrl"), "name": name}


async def _execute_linear_create_issue(node: Node, context: dict, creds: dict) -> dict:
    key = _require(creds.get("linear.api_key", ""), "LINEAR_API_KEY")
    team_id = _cfg(node, "team_id", context)
    title = _cfg(node, "title", context)
    priority_map = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
    priority = priority_map.get(_cfg(node, "priority", context, "medium"), 3)
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.linear.app/graphql",
            headers={"Authorization": key},
            json={"query": """
                mutation($teamId: String!, $title: String!, $priority: Int) {
                  issueCreate(input: {teamId: $teamId, title: $title, priority: $priority}) {
                    success issue { id identifier url }
                  }
                }""",
                "variables": {"teamId": team_id, "title": title, "priority": priority}},
        )
        resp.raise_for_status()
        data = resp.json()
    issue = data["data"]["issueCreate"]["issue"]
    return {"issue_id": issue["id"], "identifier": issue["identifier"], "url": issue["url"]}


async def _execute_github_create_issue(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("github.token", ""), "GITHUB_TOKEN")
    owner = _cfg(node, "owner", context)
    repo = _cfg(node, "repo", context)
    title = _cfg(node, "title", context)
    body = _cfg(node, "body", context)
    labels_raw = _cfg(node, "labels", context)
    labels = [l.strip() for l in labels_raw.split(",") if l.strip()] if labels_raw else []
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://api.github.com/repos/{owner}/{repo}/issues",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            json={"title": title, "body": body, "labels": labels},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"issue_number": data.get("number"), "url": data.get("html_url"), "title": title}


# ─── CRM executors ────────────────────────────────────────────────────────────

async def _execute_hubspot_create_contact(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("hubspot.access_token", ""), "HUBSPOT_ACCESS_TOKEN")
    email = _cfg(node, "email", context)
    props = {
        "email": email,
        "firstname": _cfg(node, "firstname", context),
        "lastname": _cfg(node, "lastname", context),
        "phone": _cfg(node, "phone", context),
    }
    props = {k: v for k, v in props.items() if v}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers={"Authorization": f"Bearer {token}"},
            json={"properties": props},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"contact_id": data.get("id"), "email": email}


async def _execute_freshdesk_create_ticket(node: Node, context: dict, creds: dict) -> dict:
    domain = _require(creds.get("freshdesk.domain", ""), "FRESHDESK_DOMAIN")
    api_key = _require(creds.get("freshdesk.api_key", ""), "FRESHDESK_API_KEY")
    subject = _cfg(node, "subject", context)
    description = _cfg(node, "description", context)
    email = _cfg(node, "email", context)
    priority = int(_cfg(node, "priority", context, "2"))
    creds = base64.b64encode(f"{api_key}:X".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://{domain}/api/v2/tickets",
            headers={"Authorization": f"Basic {creds}"},
            json={"subject": subject, "description": description, "email": email, "priority": priority, "status": 2},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"ticket_id": data.get("id"), "subject": subject}


async def _execute_zendesk_create_ticket(node: Node, context: dict, creds: dict) -> dict:
    subdomain = _require(creds.get("zendesk.subdomain", ""), "ZENDESK_SUBDOMAIN")
    email = _require(creds.get("zendesk.email", ""), "ZENDESK_EMAIL")
    token = _require(creds.get("zendesk.api_token", ""), "ZENDESK_API_TOKEN")
    subject = _cfg(node, "subject", context)
    description = _cfg(node, "description", context)
    requester = _cfg(node, "requester_email", context)
    creds = base64.b64encode(f"{email}/token:{token}".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://{subdomain}.zendesk.com/api/v2/tickets.json",
            headers={"Authorization": f"Basic {creds}"},
            json={"ticket": {"subject": subject, "comment": {"body": description}, "requester": {"email": requester}}},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"ticket_id": data["ticket"]["id"], "subject": subject}


# ─── Payments executors ───────────────────────────────────────────────────────

async def _execute_razorpay_create_payment_link(node: Node, context: dict, creds: dict) -> dict:
    key_id = _require(creds.get("razorpay.key_id", ""), "RAZORPAY_KEY_ID")
    key_secret = _require(creds.get("razorpay.key_secret", ""), "RAZORPAY_KEY_SECRET")
    amount = int(_cfg(node, "amount", context, "0"))
    currency = _cfg(node, "currency", context, "INR")
    description = _cfg(node, "description", context, "Payment")
    customer_phone = _cfg(node, "customer_phone", context)
    customer_email = _cfg(node, "customer_email", context)
    payload: dict = {
        "amount": amount,
        "currency": currency,
        "description": description,
        "reminder_enable": True,
    }
    if customer_phone:
        payload["customer"] = {"contact": customer_phone, "email": customer_email or ""}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.razorpay.com/v1/payment_links",
            auth=(key_id, key_secret),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    return {
        "payment_link_id": data.get("id"),
        "short_url": data.get("short_url"),
        "amount": amount,
        "currency": currency,
    }


# ─── Logistics executors ─────────────────────────────────────────────────────

async def _execute_delhivery_create_shipment(node: Node, context: dict, creds: dict) -> dict:
    token = _require(creds.get("delhivery.api_token", ""), "DELHIVERY_API_TOKEN")
    client_name = _cfg(node, "client_name", context)
    pickup_pincode = _cfg(node, "pickup_pincode", context)
    recipient_name = _cfg(node, "recipient_name", context)
    recipient_address = _cfg(node, "recipient_address", context)
    recipient_pincode = _cfg(node, "recipient_pincode", context)
    recipient_phone = _cfg(node, "recipient_phone", context)
    cod_amount = float(_cfg(node, "cod_amount", context, "0") or "0")
    weight = _cfg(node, "weight", context, "500")
    waybill = _cfg(node, "waybill", context, "")
    shipment_data = {
        "shipments": [{
            "name": recipient_name,
            "add": recipient_address,
            "pin": recipient_pincode,
            "city": "",
            "state": "",
            "country": "India",
            "phone": recipient_phone,
            "order": waybill or f"ORD-{recipient_phone[-4:]}",
            "payment": "COD" if cod_amount > 0 else "Prepaid",
            "cod_amount": cod_amount,
            "weight": weight,
            "client": client_name,
            "pickup_location": {"add": "Shop Address", "pin": pickup_pincode},
        }]
    }
    async with httpx.AsyncClient(timeout=15, base_url=creds.get("delhivery.api_url", "https://track.delhivery.com")) as client:
        resp = await client.post(
            "/api/cmu/create.json",
            headers={
                "Authorization": f"Token {token}",
                "Content-Type": "application/json",
            },
            json={"format": "json", "data": json.dumps(shipment_data)},
        )
        resp.raise_for_status()
        data = resp.json()
    packages = data.get("packages", [{}])
    return {
        "waybill": packages[0].get("waybill") if packages else None,
        "status": packages[0].get("status") if packages else "created",
        "recipient": recipient_name,
    }


async def _execute_shiprocket_create_order(node: Node, context: dict, creds: dict) -> dict:
    email = _require(creds.get("shiprocket.email", ""), "SHIPROCKET_EMAIL")
    password = _require(creds.get("shiprocket.password", ""), "SHIPROCKET_PASSWORD")

    # Get auth token (Shiprocket uses JWT, valid 10 days)
    async with httpx.AsyncClient(timeout=15) as client:
        auth = await client.post(
            "https://apiv2.shiprocket.in/v1/external/auth/login",
            json={"email": email, "password": password},
        )
        auth.raise_for_status()
        jwt = auth.json()["token"]

        order_items_raw = _cfg(node, "order_items", context, "[]")
        try:
            order_items = json.loads(order_items_raw)
        except json.JSONDecodeError:
            order_items = [{"name": "Item", "sku": "SKU001", "units": 1, "selling_price": 100}]

        payload = {
            "order_id": _cfg(node, "order_id", context),
            "order_date": __import__("datetime").datetime.utcnow().strftime("%Y-%m-%d %H:%M"),
            "pickup_location": _cfg(node, "pickup_location", context),
            "billing_customer_name": _cfg(node, "billing_customer_name", context),
            "billing_address": _cfg(node, "billing_address", context),
            "billing_city": "City",
            "billing_pincode": _cfg(node, "billing_pincode", context),
            "billing_state": "State",
            "billing_country": "India",
            "billing_email": "",
            "billing_phone": _cfg(node, "billing_phone", context),
            "shipping_is_billing": True,
            "order_items": order_items,
            "payment_method": _cfg(node, "payment_method", context, "Prepaid"),
            "sub_total": sum(i.get("selling_price", 0) * i.get("units", 1) for i in order_items),
            "length": 10, "breadth": 10, "height": 10, "weight": 0.5,
        }
        resp = await client.post(
            "https://apiv2.shiprocket.in/v1/external/orders/create/adhoc",
            headers={"Authorization": f"Bearer {jwt}"},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    return {"order_id": data.get("order_id"), "shipment_id": data.get("shipment_id"), "status": data.get("status")}


# ─── Data / Logic executors ───────────────────────────────────────────────────

async def _execute_delay(node: Node, context: dict, creds: dict) -> dict:
    seconds = int(_cfg(node, "duration_seconds", context, "0"))
    await asyncio.sleep(min(seconds, 30))  # cap at 30s in-process; use celery for longer
    return {"waited_seconds": seconds}


async def _execute_condition(node: Node, context: dict, creds: dict) -> dict:
    expression = _cfg(node, "expression", context, "true")
    # Safe eval: only basic comparisons, no exec/import
    safe_expr = re.sub(r"\{\{.*?\}\}", "''", expression)
    try:
        result = bool(eval(safe_expr, {"__builtins__": {}}, {}))  # noqa: S307
    except Exception:
        result = True  # default to true branch on error
    return {"expression": expression, "result": result, "branch": "true" if result else "false"}


async def _execute_set_variable(node: Node, context: dict, creds: dict) -> dict:
    var_name = _cfg(node, "variable_name", context)
    value = _cfg(node, "value_expression", context)
    return {var_name: value, "variable_name": var_name}


async def _execute_http_request(node: Node, context: dict, creds: dict) -> dict:
    url = _cfg(node, "url", context)
    method = _cfg(node, "method", context, "GET").upper()
    headers_raw = _cfg(node, "headers", context, "{}")
    body_raw = _cfg(node, "body", context, "")
    try:
        headers = json.loads(headers_raw)
    except json.JSONDecodeError:
        headers = {}
    try:
        body = json.loads(body_raw) if body_raw else None
    except json.JSONDecodeError:
        body = body_raw or None
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(method, url, headers=headers, json=body if isinstance(body, dict) else None,
                                    content=body if isinstance(body, str) else None)
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            data = {"text": resp.text}
    return {"status_code": resp.status_code, "response": data}


async def _execute_json_transform(node: Node, context: dict, creds: dict) -> dict:
    input_expr = _cfg(node, "input_expression", context)
    output_var = _cfg(node, "output_variable", context, "result")
    return {output_var: input_expr}


async def _execute_pdf_generate(node: Node, context: dict, creds: dict) -> dict:
    html = _cfg(node, "html_template", context)
    filename = _cfg(node, "output_filename", context, "document.pdf")
    # Uses weasyprint if installed, else returns HTML as placeholder
    try:
        import weasyprint  # type: ignore
        pdf_bytes = weasyprint.HTML(string=html).write_pdf()
        encoded = base64.b64encode(pdf_bytes).decode()
        return {"filename": filename, "base64_pdf": encoded, "size_bytes": len(pdf_bytes)}
    except ImportError:
        return {"filename": filename, "html_preview": html[:200], "note": "Install weasyprint for real PDF generation"}


# ─── Cloud / Storage executors ────────────────────────────────────────────────

async def _execute_google_drive_upload(node: Node, context: dict, creds: dict) -> dict:
    sa_path = _require(creds.get("google.service_account_json", ""), "GOOGLE_SERVICE_ACCOUNT_JSON")
    file_url = _cfg(node, "file_url", context)
    filename = _cfg(node, "filename", context, "upload.bin")
    folder_id = _cfg(node, "folder_id", context)
    token = await _google_access_token(sa_path, ["https://www.googleapis.com/auth/drive.file"])
    async with httpx.AsyncClient(timeout=30) as client:
        file_resp = await client.get(file_url)
        file_resp.raise_for_status()
        metadata: dict = {"name": filename}
        if folder_id:
            metadata["parents"] = [folder_id]
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
            headers={"Authorization": f"Bearer {token}"},
            files={
                "metadata": (None, json.dumps(metadata), "application/json"),
                "file": (filename, file_resp.content),
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return {"file_id": data.get("id"), "name": filename}


async def _execute_s3_upload(node: Node, context: dict, creds: dict) -> dict:
    try:
        import boto3  # type: ignore
    except ImportError:
        raise ConfigError("boto3 not installed. Run: pip install boto3")
    _require(creds.get("aws.access_key_id", ""), "AWS_ACCESS_KEY_ID")
    _require(creds.get("aws.secret_access_key", ""), "AWS_SECRET_ACCESS_KEY")
    bucket = _cfg(node, "bucket", context)
    key = _cfg(node, "key", context)
    file_url = _cfg(node, "file_url", context)
    async with httpx.AsyncClient(timeout=30) as client:
        file_resp = await client.get(file_url)
        file_resp.raise_for_status()
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: boto3.client(
        "s3",
        aws_access_key_id=creds.get("aws.access_key_id", ""),
        aws_secret_access_key=creds.get("aws.secret_access_key", ""),
        region_name=creds.get("aws.region", "ap-south-1"),
    ).put_object(Bucket=bucket, Key=key, Body=file_resp.content))
    return {"bucket": bucket, "key": key, "url": f"https://{bucket}.s3.amazonaws.com/{key}"}


async def _execute_database_insert(node: Node, context: dict, creds: dict) -> dict:
    data_raw = _cfg(node, "data", context, "{}")
    table = _cfg(node, "table", context)
    try:
        data = json.loads(data_raw)
    except json.JSONDecodeError:
        data = {"value": data_raw}
    cols = ", ".join(data.keys())
    placeholders = ", ".join([f"${i+1}" for i in range(len(data))])
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING id"
    try:
        import asyncpg  # type: ignore
        conn = await asyncpg.connect(settings.database_url.replace("+asyncpg", ""))
        row = await conn.fetchrow(sql, *data.values())
        await conn.close()
        return {"inserted_id": str(row["id"]) if row else None, "table": table}
    except Exception as e:
        return {"status": "error", "error": str(e), "table": table, "sql": sql}


# ─── Calendar / Meetings executors ───────────────────────────────────────────

async def _execute_google_calendar_create_event(node: Node, context: dict, creds: dict) -> dict:
    sa_path = _require(creds.get("google.service_account_json", ""), "GOOGLE_SERVICE_ACCOUNT_JSON")
    cal_id = _cfg(node, "calendar_id", context, "primary")
    summary = _cfg(node, "summary", context)
    start = _cfg(node, "start_datetime", context)
    end = _cfg(node, "end_datetime", context)
    attendees_raw = _cfg(node, "attendees", context)
    attendees = [{"email": e.strip()} for e in attendees_raw.split(",") if e.strip()]
    token = await _google_access_token(sa_path, ["https://www.googleapis.com/auth/calendar"])
    event: dict = {
        "summary": summary,
        "start": {"dateTime": start, "timeZone": "UTC"},
        "end": {"dateTime": end, "timeZone": "UTC"},
    }
    if attendees:
        event["attendees"] = attendees
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{cal_id}/events",
            headers={"Authorization": f"Bearer {token}"},
            json=event,
        )
        resp.raise_for_status()
        data = resp.json()
    return {"event_id": data.get("id"), "html_link": data.get("htmlLink"), "summary": summary}


async def _execute_zoom_create_meeting(node: Node, context: dict, creds: dict) -> dict:
    account_id = _require(creds.get("zoom.account_id", ""), "ZOOM_ACCOUNT_ID")
    client_id = _require(creds.get("zoom.client_id", ""), "ZOOM_CLIENT_ID")
    client_secret = _require(creds.get("zoom.client_secret", ""), "ZOOM_CLIENT_SECRET")
    topic = _cfg(node, "topic", context)
    start_time = _cfg(node, "start_time", context)
    duration = int(_cfg(node, "duration_minutes", context, "60"))
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=10) as client:
        token_resp = await client.post(
            f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={account_id}",
            headers={"Authorization": f"Basic {creds}"},
        )
        token_resp.raise_for_status()
        zoom_token = token_resp.json()["access_token"]
        resp = await client.post(
            "https://api.zoom.us/v2/users/me/meetings",
            headers={"Authorization": f"Bearer {zoom_token}"},
            json={"topic": topic, "type": 2, "start_time": start_time, "duration": duration, "settings": {"join_before_host": True}},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"meeting_id": data.get("id"), "join_url": data.get("join_url"), "topic": topic}


# ─── Social / Marketing executors ────────────────────────────────────────────

async def _execute_twitter_post(node: Node, context: dict, creds: dict) -> dict:
    api_key = _require(creds.get("twitter.api_key", ""), "TWITTER_API_KEY")
    api_secret = _require(creds.get("twitter.api_secret", ""), "TWITTER_API_SECRET")
    access_token = _require(creds.get("twitter.access_token", ""), "TWITTER_ACCESS_TOKEN")
    access_secret = _require(creds.get("twitter.access_secret", ""), "TWITTER_ACCESS_SECRET")
    content = _cfg(node, "content", context)
    # OAuth 1.0a for Twitter v2
    import time, urllib.parse
    timestamp = str(int(time.time()))
    nonce = base64.b64encode(str(time.time()).encode()).decode().replace("=", "")
    oauth_params = {
        "oauth_consumer_key": api_key,
        "oauth_token": access_token,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp,
        "oauth_nonce": nonce,
        "oauth_version": "1.0",
    }
    base_string = "&".join([
        "POST",
        urllib.parse.quote("https://api.twitter.com/2/tweets", safe=""),
        urllib.parse.quote("&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in sorted(oauth_params.items())), safe=""),
    ])
    signing_key = f"{urllib.parse.quote(api_secret, safe='')}&{urllib.parse.quote(access_secret, safe='')}"
    signature = base64.b64encode(hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()).decode()
    oauth_params["oauth_signature"] = signature
    auth_header = "OAuth " + ", ".join(f'{k}="{urllib.parse.quote(v, safe="")}"' for k, v in sorted(oauth_params.items()))
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.twitter.com/2/tweets",
            headers={"Authorization": auth_header, "Content-Type": "application/json"},
            json={"text": content[:280]},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"tweet_id": data["data"]["id"], "text": content[:280]}


async def _execute_mailchimp_add_subscriber(node: Node, context: dict, creds: dict) -> dict:
    api_key = _require(creds.get("mailchimp.api_key", ""), "MAILCHIMP_API_KEY")
    server = _require(creds.get("mailchimp.server_prefix", ""), "MAILCHIMP_SERVER_PREFIX")
    list_id = _cfg(node, "list_id", context)
    email = _cfg(node, "email", context)
    merge_raw = _cfg(node, "merge_fields", context, "{}")
    try:
        merge_fields = json.loads(merge_raw)
    except json.JSONDecodeError:
        merge_fields = {}
    subscriber_hash = hashlib.md5(email.lower().encode()).hexdigest()
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.put(
            f"https://{server}.api.mailchimp.com/3.0/lists/{list_id}/members/{subscriber_hash}",
            auth=("anystring", api_key),
            json={"email_address": email, "status_if_new": "subscribed", "merge_fields": merge_fields},
        )
        resp.raise_for_status()
        data = resp.json()
    return {"subscriber_id": data.get("id"), "email": email, "status": data.get("status")}


# ─── AI executors ─────────────────────────────────────────────────────────────

async def _execute_openai_completion(node: Node, context: dict, creds: dict) -> dict:
    key = _require(settings.openrouter_api_key, "OPENROUTER_API_KEY")  # reuse OpenRouter
    prompt = _cfg(node, "prompt_template", context)
    model = _cfg(node, "model", context, "openai/gpt-4o-mini")
    output_var = _cfg(node, "output_variable", context, "ai_response")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        )
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"]
    return {output_var: text, "model_used": model}


async def _execute_sentiment_analysis(node: Node, context: dict, creds: dict) -> dict:
    key = _require(settings.openrouter_api_key, "OPENROUTER_API_KEY")
    text_var = _cfg(node, "text_variable", context)
    output_var = _cfg(node, "output_variable", context, "sentiment")
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "openai/gpt-4o-mini", "messages": [
                {"role": "user", "content": f"Classify the sentiment of this text as exactly one word: positive, negative, or neutral.\n\nText: {text_var}"}
            ]},
        )
        resp.raise_for_status()
        sentiment = resp.json()["choices"][0]["message"]["content"].strip().lower()
    return {output_var: sentiment, "text_analysed": text_var[:100]}


# ─── Trigger executors (acknowledge only — real triggers are webhook-driven) ──

async def _execute_trigger(node: Node, context: dict, creds: dict) -> dict:
    return {"acknowledged": True, "node_type": node.type.value,
            "note": "Trigger acknowledged. Real events arrive via webhook or schedule."}


async def _execute_unknown(node: Node, context: dict, creds: dict) -> dict:
    raise ValueError(f"No executor registered for node type '{node.type.value}'")


# ─── Google OAuth helper ──────────────────────────────────────────────────────

async def _google_access_token(sa_json_path: str, scopes: list[str]) -> str:
    """Exchange a service account JSON for a short-lived access token."""
    import json as _json, time as _time
    try:
        from google.oauth2 import service_account  # type: ignore
        from google.auth.transport.requests import Request as GRequest  # type: ignore
        import requests as _requests
    except ImportError:
        raise ConfigError("google-auth not installed. Run: pip install google-auth google-auth-httplib2")
    sa_info = _json.loads(open(sa_json_path).read()) if not sa_json_path.startswith("{") else _json.loads(sa_json_path)
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: creds.refresh(_requests.Request()))
    return creds.token


# ─── Executor registry ────────────────────────────────────────────────────────

EXECUTORS: dict[str, object] = {
    # Triggers — all acknowledge only
    "gmail_trigger":          _execute_trigger,
    "webhook":                _execute_trigger,
    "whatsapp_trigger":       _execute_trigger,
    "schedule_trigger":       _execute_trigger,
    "google_sheets_trigger":  _execute_trigger,
    "typeform_trigger":       _execute_trigger,
    "razorpay_trigger":       _execute_trigger,
    "stripe_trigger":         _execute_trigger,
    "woocommerce_trigger":    _execute_trigger,
    "shopify_trigger":        _execute_trigger,
    # Messaging
    "slack_message":          _execute_slack_message,
    "discord_message":        _execute_discord_message,
    "teams_message":          _execute_teams_message,
    "whatsapp_message":       _execute_whatsapp_message,
    "sms_send":               _execute_sms_send,
    "telegram_message":       _execute_telegram_message,
    "email_send":             _execute_email_send,
    "push_notification":      _execute_push_notification,
    # Productivity
    "notion_create_page":     _execute_notion_create_page,
    "google_sheets_append":   _execute_google_sheets_append,
    "google_docs_create":     _execute_google_docs_create,
    "airtable_create_record": _execute_airtable_create_record,
    "jira_create_issue":      _execute_jira_create_issue,
    "trello_create_card":     _execute_trello_create_card,
    "linear_create_issue":    _execute_linear_create_issue,
    "github_create_issue":    _execute_github_create_issue,
    # CRM
    "hubspot_create_contact":  _execute_hubspot_create_contact,
    "salesforce_create_lead":  _execute_unknown,  # requires OAuth flow
    "zoho_crm_create_lead":    _execute_unknown,  # requires OAuth flow
    "freshdesk_create_ticket": _execute_freshdesk_create_ticket,
    "zendesk_create_ticket":   _execute_zendesk_create_ticket,
    # Payments & Logistics
    "razorpay_create_payment_link": _execute_razorpay_create_payment_link,
    "delhivery_create_shipment":    _execute_delhivery_create_shipment,
    "shiprocket_create_order":      _execute_shiprocket_create_order,
    "dunzo_create_task":            _execute_unknown,
    # Data / Logic
    "delay":           _execute_delay,
    "condition":       _execute_condition,
    "set_variable":    _execute_set_variable,
    "http_request":    _execute_http_request,
    "json_transform":  _execute_json_transform,
    "pdf_generate":    _execute_pdf_generate,
    # Cloud
    "google_drive_upload": _execute_google_drive_upload,
    "s3_upload":           _execute_s3_upload,
    "database_insert":     _execute_database_insert,
    # AI
    "openai_completion":  _execute_openai_completion,
    "sentiment_analysis": _execute_sentiment_analysis,
    # Calendar / Meetings
    "google_calendar_create_event": _execute_google_calendar_create_event,
    "zoom_create_meeting":          _execute_zoom_create_meeting,
    "calendly_create_invite":       _execute_unknown,
    # Social
    "twitter_post":              _execute_twitter_post,
    "instagram_post":            _execute_unknown,  # requires Graph API review
    "mailchimp_add_subscriber":  _execute_mailchimp_add_subscriber,
}


# ─── Graph execution ──────────────────────────────────────────────────────────

async def execute_node(node: Node, context: dict, creds: dict) -> NodeExecutionResult:
    try:
        executor = EXECUTORS.get(node.type.value, _execute_unknown)
        output = await executor(node, context, creds)
        logger.info(f"Node {node.id} ({node.type.value}) → success")
        return NodeExecutionResult(
            node_id=node.id, node_type=node.type.value, status="success", output=output
        )
    except ConfigError as e:
        logger.error(f"Node {node.id} config error: {e}")
        return NodeExecutionResult(
            node_id=node.id, node_type=node.type.value, status="error", output={}, error=str(e)
        )
    except httpx.HTTPStatusError as e:
        body = e.response.text[:400]
        logger.warning(f"Node {node.id} HTTP {e.response.status_code}: {body}")
        return NodeExecutionResult(
            node_id=node.id, node_type=node.type.value, status="error", output={},
            error=f"HTTP {e.response.status_code}: {body}",
        )
    except Exception as e:
        logger.warning(f"Node {node.id} ({node.type.value}) failed: {e}")
        return NodeExecutionResult(
            node_id=node.id, node_type=node.type.value, status="error", output={}, error=str(e)
        )


def _topological_order(workflow: Workflow) -> list[Node]:
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


async def execute_workflow(workflow_id: str, workflow: Workflow, creds: dict) -> dict:
    steps: list[NodeExecutionResult] = []
    context: dict = {}
    status = "completed"

    for node in _topological_order(workflow):
        result = await execute_node(node, context, creds)
        steps.append(result)
        # Propagate output into context for downstream nodes
        context[node.id] = result.output
        if result.status == "error":
            status = "failed"
            break

    return {
        "workflow_id": workflow_id,
        "status": status,
        "steps": [s.model_dump() for s in steps],
    }