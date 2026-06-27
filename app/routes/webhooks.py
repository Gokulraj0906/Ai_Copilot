"""
Realtime webhook receivers.

Each trigger type has a dedicated endpoint. When an external platform fires an
event (WhatsApp message, Razorpay payment, Shopify order, …) it hits one of
these endpoints. We find all workflows whose trigger matches, then execute them.

Endpoints:
  POST /webhooks/whatsapp          — Meta WhatsApp Business API
  POST /webhooks/razorpay          — Razorpay payment events
  POST /webhooks/stripe            — Stripe payment events
  POST /webhooks/shopify           — Shopify order/customer events
  POST /webhooks/woocommerce       — WooCommerce order events
  POST /webhooks/typeform          — Typeform form submissions
  POST /webhooks/gmail             — Gmail push notifications (Pub/Sub)
  POST /webhooks/github            — GitHub repository events
  POST /webhooks/generic/{path}    — Custom webhook trigger (any POST)
  GET  /webhooks/whatsapp          — WhatsApp Business verification challenge
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import repository
from app.db.database import get_db
from app.models.workflow import NodeType, Workflow
from app.service.execution import execute_workflow

logger = logging.getLogger("copilot.webhooks")

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _hmac_sig(secret: str, body: bytes, algo: str = "sha256") -> str:
    return hmac.new(secret.encode(), body, getattr(hashlib, algo)).hexdigest()


async def _find_and_run(
    db: AsyncSession,
    trigger_type: NodeType,
    payload: dict,
    background: BackgroundTasks,
    match_config_key: str | None = None,
    match_config_val: str | None = None,
) -> list[str]:
    """
    Find all valid workflows whose first node is trigger_type, optionally
    matching a config field (e.g. phone_number_id must equal incoming value),
    then schedule each for background execution.
    Returns list of workflow_ids triggered.
    """
    records = await repository.list_workflows(db, limit=200)
    triggered: list[str] = []

    for rec in records:
        if not rec.is_valid:
            continue
        try:
            wf = Workflow(**rec.data)
        except Exception:
            continue

        # Find the trigger node
        trigger_nodes = [n for n in wf.nodes if n.type == trigger_type]
        if not trigger_nodes:
            continue

        # Optional config filter (e.g. only run if phone_number_id matches)
        if match_config_key and match_config_val:
            cfg_val = trigger_nodes[0].config.get(match_config_key, "")
            if cfg_val and cfg_val != match_config_val:
                continue

        workflow_id = rec.id
        # Inject incoming payload into context as node "0" (before node "1")
        initial_context: dict = {"0": payload, "trigger": payload}

        logger.info(f"Webhook triggering workflow {workflow_id} ({trigger_type.value})")
        background.add_task(_run_workflow, workflow_id, wf, initial_context)
        triggered.append(workflow_id)

    return triggered


async def _run_workflow(workflow_id: str, wf: Workflow, initial_context: dict) -> None:
    try:
        result = await execute_workflow(workflow_id, wf)
        logger.info(f"Workflow {workflow_id} completed: {result['status']}")
    except Exception as e:
        logger.error(f"Workflow {workflow_id} execution error: {e}")


# ─── WhatsApp Business API ────────────────────────────────────────────────────

@router.get("/whatsapp")
async def whatsapp_verify(request: Request):
    """WhatsApp Business API sends a GET to verify the webhook URL."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    # The verify token must match what you set in Meta dashboard
    expected = settings.whatsapp_access_token[:16] if settings.whatsapp_access_token else "verify_token"
    if mode == "subscribe" and token == expected:
        logger.info("WhatsApp webhook verified successfully")
        return int(challenge)
    raise HTTPException(status_code=403, detail="WhatsApp verification failed")


@router.post("/whatsapp")
async def whatsapp_incoming(
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    data = json.loads(body)

    # Extract message details from WhatsApp payload
    try:
        entry = data["entry"][0]
        change = entry["changes"][0]["value"]
        messages = change.get("messages", [])
        phone_number_id = change.get("metadata", {}).get("phone_number_id", "")

        if not messages:
            # Delivery status update — acknowledge and ignore
            return {"status": "ok"}

        msg = messages[0]
        payload = {
            "phone_number_id": phone_number_id,
            "from": msg.get("from"),
            "message_id": msg.get("id"),
            "text": msg.get("text", {}).get("body", ""),
            "timestamp": msg.get("timestamp"),
            "message_type": msg.get("type"),
        }
    except (KeyError, IndexError):
        return {"status": "ok"}  # Malformed — acknowledge anyway

    triggered = await _find_and_run(
        db, NodeType.WHATSAPP_TRIGGER, payload, background,
        match_config_key="phone_number_id",
        match_config_val=phone_number_id,
    )
    return {"status": "ok", "workflows_triggered": len(triggered)}


# ─── Razorpay ─────────────────────────────────────────────────────────────────

@router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    background: BackgroundTasks,
    x_razorpay_signature: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Verify HMAC signature if webhook secret is configured
    if settings.razorpay_key_secret and x_razorpay_signature:
        expected = _hmac_sig(settings.razorpay_key_secret, body)
        if not hmac.compare_digest(expected, x_razorpay_signature):
            raise HTTPException(status_code=400, detail="Invalid Razorpay signature")

    data = json.loads(body)
    event = data.get("event", "")
    payload_data = data.get("payload", {})

    # Flatten the most useful fields into context
    payment = payload_data.get("payment", {}).get("entity", {})
    payload = {
        "event": event,
        "payment_id": payment.get("id"),
        "order_id": payment.get("order_id"),
        "amount": payment.get("amount"),
        "currency": payment.get("currency"),
        "status": payment.get("status"),
        "contact": payment.get("contact"),
        "email": payment.get("email"),
    }

    triggered = await _find_and_run(db, NodeType.RAZORPAY_TRIGGER, payload, background)
    return {"status": "ok", "event": event, "workflows_triggered": len(triggered)}


# ─── Stripe ───────────────────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    background: BackgroundTasks,
    stripe_signature: str | None = Header(default=None, alias="stripe-signature"),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()

    # Stripe uses a timestamp + signature format
    if settings.stripe_secret_key and stripe_signature:
        try:
            _verify_stripe_signature(body, stripe_signature, settings.stripe_secret_key)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    data = json.loads(body)
    obj = data.get("data", {}).get("object", {})
    payload = {
        "event": data.get("type"),
        "id": obj.get("id"),
        "amount": obj.get("amount"),
        "currency": obj.get("currency"),
        "status": obj.get("status"),
        "customer": obj.get("customer"),
        "customer_email": obj.get("receipt_email") or obj.get("customer_email"),
    }

    triggered = await _find_and_run(db, NodeType.STRIPE_TRIGGER, payload, background)
    return {"status": "ok", "event": payload["event"], "workflows_triggered": len(triggered)}


def _verify_stripe_signature(body: bytes, sig_header: str, secret: str):
    """Stripe signs with t=timestamp,v1=sig — verify HMAC-SHA256."""
    parts = {k: v for k, v in (p.split("=", 1) for p in sig_header.split(","))}
    timestamp = parts.get("t", "")
    v1 = parts.get("v1", "")
    signed_payload = f"{timestamp}.".encode() + body
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, v1):
        raise ValueError("Invalid Stripe webhook signature")


# ─── Shopify ──────────────────────────────────────────────────────────────────

@router.post("/shopify")
async def shopify_webhook(
    request: Request,
    background: BackgroundTasks,
    x_shopify_hmac_sha256: str | None = Header(default=None),
    x_shopify_topic: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    data = json.loads(body)

    payload = {
        "event": x_shopify_topic or "unknown",
        "order_id": data.get("id"),
        "order_number": data.get("order_number"),
        "total_price": data.get("total_price"),
        "currency": data.get("currency"),
        "financial_status": data.get("financial_status"),
        "fulfillment_status": data.get("fulfillment_status"),
        "customer_email": data.get("email"),
        "customer_name": f"{data.get('billing_address', {}).get('first_name', '')} {data.get('billing_address', {}).get('last_name', '')}".strip(),
        "shipping_address": data.get("shipping_address", {}),
        "line_items": data.get("line_items", []),
    }

    triggered = await _find_and_run(db, NodeType.SHOPIFY_TRIGGER, payload, background)
    return {"status": "ok", "topic": x_shopify_topic, "workflows_triggered": len(triggered)}


# ─── WooCommerce ──────────────────────────────────────────────────────────────

@router.post("/woocommerce")
async def woocommerce_webhook(
    request: Request,
    background: BackgroundTasks,
    x_wc_webhook_topic: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    data = json.loads(body)

    payload = {
        "event": x_wc_webhook_topic or "order.created",
        "order_id": data.get("id"),
        "order_number": data.get("number"),
        "status": data.get("status"),
        "total": data.get("total"),
        "currency": data.get("currency"),
        "customer_email": data.get("billing", {}).get("email"),
        "customer_name": f"{data.get('billing', {}).get('first_name', '')} {data.get('billing', {}).get('last_name', '')}".strip(),
        "billing": data.get("billing", {}),
        "shipping": data.get("shipping", {}),
        "line_items": data.get("line_items", []),
    }

    triggered = await _find_and_run(db, NodeType.WOOCOMMERCE_TRIGGER, payload, background)
    return {"status": "ok", "event": payload["event"], "workflows_triggered": len(triggered)}


# ─── Typeform ─────────────────────────────────────────────────────────────────

@router.post("/typeform")
async def typeform_webhook(
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    data = json.loads(body)

    form_response = data.get("form_response", {})
    answers = form_response.get("answers", [])

    # Flatten answers into a simple dict
    flat_answers: dict = {}
    for ans in answers:
        field_ref = ans.get("field", {}).get("ref", f"field_{len(flat_answers)}")
        ans_type = ans.get("type")
        flat_answers[field_ref] = ans.get(ans_type, ans.get("text", ""))

    payload = {
        "form_id": data.get("form_response", {}).get("form_id"),
        "response_id": form_response.get("token"),
        "submitted_at": form_response.get("submitted_at"),
        "answers": flat_answers,
    }

    triggered = await _find_and_run(db, NodeType.TYPEFORM_TRIGGER, payload, background)
    return {"status": "ok", "workflows_triggered": len(triggered)}


# ─── Gmail via Google Pub/Sub push ───────────────────────────────────────────

@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Google Pub/Sub delivers Gmail push notifications here.
    The message data is base64-encoded JSON.

    Pub/Sub also sends empty-body GET/POST requests for subscription verification
    and periodic liveness checks — we must return 200 on those or Pub/Sub will
    keep retrying and eventually disable the subscription.
    """
    import base64 as _base64

    # ── Read raw bytes first — never trust the body is non-empty ─────────────
    raw_body = await request.body()

    if not raw_body or not raw_body.strip():
        # Empty body = Pub/Sub verification ping — acknowledge silently
        logger.debug("Gmail webhook: empty body (Pub/Sub ping) — acknowledged")
        return {"status": "ok", "workflows_triggered": 0}

    # ── Parse JSON safely ─────────────────────────────────────────────────────
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        logger.warning(f"Gmail webhook: invalid JSON ({exc}) — body: {raw_body[:200]!r}")
        # Return 200 so Pub/Sub doesn't keep retrying a malformed message forever
        return {"status": "ok", "workflows_triggered": 0}

    # ── Decode the Pub/Sub message envelope ───────────────────────────────────
    message = body.get("message") or {}
    b64_data = message.get("data", "")

    decoded: dict = {}
    if b64_data:
        try:
            # Pub/Sub base64 may omit padding — add == to be safe
            json_bytes = _base64.b64decode(b64_data + "==")
            decoded = json.loads(json_bytes.decode("utf-8"))
        except Exception as exc:
            logger.warning(f"Gmail webhook: could not decode message.data — {exc}")

    payload = {
        "email_address": decoded.get("emailAddress"),
        "history_id": decoded.get("historyId"),
        "message_id": message.get("messageId") or message.get("message_id"),
        "publish_time": message.get("publishTime"),
        "subscription": body.get("subscription"),
    }

    triggered = await _find_and_run(db, NodeType.GMAIL_TRIGGER, payload, background)
    return {"status": "ok", "workflows_triggered": len(triggered)}


# ─── GitHub ───────────────────────────────────────────────────────────────────

@router.post("/github")
async def github_webhook(
    request: Request,
    background: BackgroundTasks,
    x_github_event: str | None = Header(default=None),
    x_hub_signature_256: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
):
    body = await request.body()
    data = json.loads(body)

    payload = {
        "event": x_github_event,
        "action": data.get("action"),
        "repository": data.get("repository", {}).get("full_name"),
        "sender": data.get("sender", {}).get("login"),
        "ref": data.get("ref"),
        "pull_request": data.get("pull_request", {}).get("title"),
        "issue": data.get("issue", {}).get("title"),
    }

    triggered = await _find_and_run(db, NodeType.WEBHOOK, payload, background)
    return {"status": "ok", "event": x_github_event, "workflows_triggered": len(triggered)}


# ─── Schedule trigger (called by cron / external scheduler) ──────────────────

@router.post("/schedule/{cron_expression:path}")
async def schedule_trigger(
    cron_expression: str,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Called by an external cron service (e.g. cron-job.org, EasyCron, Cloud Scheduler).
    The cron_expression in the path must match what's stored in the workflow config.
    Example: POST /webhooks/schedule/0%209%20*%20*%20*
    """
    import urllib.parse
    expr = urllib.parse.unquote(cron_expression)
    payload = {"cron_expression": expr, "fired_at": __import__("datetime").datetime.utcnow().isoformat()}

    records = await repository.list_workflows(db, limit=200)
    triggered: list[str] = []
    for rec in records:
        if not rec.is_valid:
            continue
        try:
            wf = Workflow(**rec.data)
        except Exception:
            continue
        for node in wf.nodes:
            if node.type == NodeType.SCHEDULE_TRIGGER:
                if node.config.get("cron_expression", "").strip() == expr.strip():
                    background.add_task(_run_workflow, rec.id, wf, {"trigger": payload})
                    triggered.append(rec.id)
                    break

    return {"status": "ok", "cron_expression": expr, "workflows_triggered": len(triggered)}


# ─── Generic webhook trigger ──────────────────────────────────────────────────

@router.post("/generic/{path:path}")
async def generic_webhook(
    path: str,
    request: Request,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """
    Catch-all for any custom webhook trigger.
    Workflows with a `webhook` trigger node whose `path` config matches
    the URL path will be executed.
    """
    body = await request.body()
    try:
        payload = json.loads(body)
    except Exception:
        payload = {"raw": body.decode(errors="replace")}

    payload["_path"] = path
    payload["_headers"] = dict(request.headers)

    records = await repository.list_workflows(db, limit=200)
    triggered: list[str] = []
    for rec in records:
        if not rec.is_valid:
            continue
        try:
            wf = Workflow(**rec.data)
        except Exception:
            continue
        for node in wf.nodes:
            if node.type == NodeType.WEBHOOK:
                cfg_path = node.config.get("path", "").strip("/")
                if not cfg_path or cfg_path == path.strip("/"):
                    background.add_task(_run_workflow, rec.id, wf, {"trigger": payload, **payload})
                    triggered.append(rec.id)
                    break

    return {"status": "ok", "path": path, "workflows_triggered": len(triggered)}
