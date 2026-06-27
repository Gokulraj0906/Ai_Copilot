# # """
# # Credential management routes — all require JWT auth.

# # POST   /credentials                — save or update one credential
# # GET    /credentials                — list all connected integrations (no plaintext)
# # DELETE /credentials/{service}/{key} — remove a credential

# # The catalogue of service_name / credential_key pairs supported:

# #   slack           → bot_token
# #   whatsapp        → access_token, phone_number_id
# #   telegram        → bot_token
# #   discord         → bot_token
# #   twilio          → account_sid, auth_token, from_number
# #   sendgrid        → api_key
# #   smtp            → host, port, user, password, from
# #   firebase        → server_key
# #   notion          → api_key
# #   google          → service_account_json
# #   airtable        → api_key
# #   jira            → domain, email, api_token
# #   trello          → api_key, api_token
# #   linear          → api_key
# #   github          → token
# #   hubspot         → access_token
# #   freshdesk       → domain, api_key
# #   zendesk         → subdomain, email, api_token
# #   razorpay        → key_id, key_secret
# #   stripe          → secret_key
# #   delhivery       → api_token
# #   shiprocket      → email, password
# #   aws             → access_key_id, secret_access_key, region
# #   zoom            → account_id, client_id, client_secret
# #   twitter         → api_key, api_secret, access_token, access_secret
# #   mailchimp       → api_key, server_prefix
# # """

# # from fastapi import APIRouter, Depends, HTTPException
# # from pydantic import BaseModel
# # from sqlalchemy.ext.asyncio import AsyncSession

# # from app.core.auth import get_current_user
# # from app.core.credential_store import (
# #     delete_credential,
# #     list_credentials,
# #     upsert_credential,
# # )
# # from app.db.database import get_db
# # from app.db.tables import UserRecord

# # router = APIRouter(prefix="/credentials", tags=["credentials"])

# # # All service+key pairs the platform supports
# # VALID_CREDENTIAL_KEYS: dict[str, list[str]] = {
# #     "slack":      ["bot_token"],
# #     "whatsapp":   ["access_token", "phone_number_id"],
# #     "telegram":   ["bot_token"],
# #     "discord":    ["bot_token"],
# #     "twilio":     ["account_sid", "auth_token", "from_number"],
# #     "sendgrid":   ["api_key"],
# #     "smtp":       ["host", "port", "user", "password", "from"],
# #     "firebase":   ["server_key"],
# #     "notion":     ["api_key"],
# #     "google":     ["service_account_json"],
# #     "airtable":   ["api_key"],
# #     "jira":       ["domain", "email", "api_token"],
# #     "trello":     ["api_key", "api_token"],
# #     "linear":     ["api_key"],
# #     "github":     ["token"],
# #     "hubspot":    ["access_token"],
# #     "freshdesk":  ["domain", "api_key"],
# #     "zendesk":    ["subdomain", "email", "api_token"],
# #     "razorpay":   ["key_id", "key_secret"],
# #     "stripe":     ["secret_key"],
# #     "delhivery":  ["api_token"],
# #     "shiprocket": ["email", "password"],
# #     "aws":        ["access_key_id", "secret_access_key", "region"],
# #     "zoom":       ["account_id", "client_id", "client_secret"],
# #     "twitter":    ["api_key", "api_secret", "access_token", "access_secret"],
# #     "mailchimp":  ["api_key", "server_prefix"],
# # }


# # class SaveCredentialRequest(BaseModel):
# #     service_name: str    # e.g. "slack"
# #     credential_key: str  # e.g. "bot_token"
# #     value: str           # plaintext — transmitted over HTTPS, encrypted before storage
# #     label: str = ""      # optional user-friendly name e.g. "My Slack workspace"


# # @router.post("", status_code=201)
# # async def save_credential(
# #     req: SaveCredentialRequest,
# #     current_user: UserRecord = Depends(get_current_user),
# #     db: AsyncSession = Depends(get_db),
# # ):
# #     # Validate service + key against known catalogue
# #     valid_keys = VALID_CREDENTIAL_KEYS.get(req.service_name)
# #     if valid_keys is None:
# #         raise HTTPException(
# #             status_code=400,
# #             detail=f"Unknown service '{req.service_name}'. Supported: {sorted(VALID_CREDENTIAL_KEYS.keys())}",
# #         )
# #     if req.credential_key not in valid_keys:
# #         raise HTTPException(
# #             status_code=400,
# #             detail=f"Unknown key '{req.credential_key}' for service '{req.service_name}'. Valid keys: {valid_keys}",
# #         )
# #     if not req.value.strip():
# #         raise HTTPException(status_code=400, detail="Credential value cannot be empty")

# #     cred_id = await upsert_credential(
# #         user_id=current_user.id,
# #         service_name=req.service_name,
# #         credential_key=req.credential_key,
# #         plaintext_value=req.value,
# #         label=req.label or f"{req.service_name} {req.credential_key}",
# #         db=db,
# #     )
# #     return {
# #         "id": cred_id,
# #         "service_name": req.service_name,
# #         "credential_key": req.credential_key,
# #         "label": req.label,
# #         "saved": True,
# #     }


# # @router.get("")
# # async def get_credentials(
# #     current_user: UserRecord = Depends(get_current_user),
# #     db: AsyncSession = Depends(get_db),
# # ):
# #     """Returns credential metadata — never returns the plaintext values."""
# #     items = await list_credentials(current_user.id, db)
# #     # Group by service for a cleaner response
# #     grouped: dict[str, list[dict]] = {}
# #     for item in items:
# #         svc = item["service_name"]
# #         grouped.setdefault(svc, []).append({
# #             "key": item["credential_key"],
# #             "label": item["label"],
# #             "id": item["id"],
# #             "updated_at": item["updated_at"],
# #         })
# #     return {"connected_services": grouped, "total": len(items)}


# # @router.delete("/{service_name}/{credential_key}")
# # async def remove_credential(
# #     service_name: str,
# #     credential_key: str,
# #     current_user: UserRecord = Depends(get_current_user),
# #     db: AsyncSession = Depends(get_db),
# # ):
# #     deleted = await delete_credential(current_user.id, service_name, credential_key, db)
# #     if not deleted:
# #         raise HTTPException(status_code=404, detail="Credential not found")
# #     return {"deleted": True, "service_name": service_name, "credential_key": credential_key}


# # @router.get("/supported")
# # async def supported_credentials():
# #     """Returns the full list of supported service/key pairs — no auth required."""
# #     return {"services": VALID_CREDENTIAL_KEYS}
# """
# Credential management routes — all require JWT auth.

# POST   /credentials                — save or update one credential
# GET    /credentials                — list all connected integrations (no plaintext)
# DELETE /credentials/{service}/{key} — remove a credential

# The catalogue of service_name / credential_key pairs supported:

#   slack           → bot_token
#   whatsapp        → access_token, phone_number_id
#   telegram        → bot_token
#   discord         → bot_token
#   twilio          → account_sid, auth_token, from_number
#   sendgrid        → api_key
#   smtp            → host, port, user, password, from
#   firebase        → server_key
#   notion          → api_key
#   google          → service_account_json
#   airtable        → api_key
#   jira            → domain, email, api_token
#   trello          → api_key, api_token
#   linear          → api_key
#   github          → token
#   hubspot         → access_token
#   freshdesk       → domain, api_key
#   zendesk         → subdomain, email, api_token
#   razorpay        → key_id, key_secret
#   stripe          → secret_key
#   delhivery       → api_token
#   shiprocket      → email, password
#   aws             → access_key_id, secret_access_key, region
#   zoom            → account_id, client_id, client_secret
#   twitter         → api_key, api_secret, access_token, access_secret
#   mailchimp       → api_key, server_prefix
# """

# from fastapi import APIRouter, Depends, HTTPException
# from pydantic import BaseModel
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.core.auth import get_current_user
# from app.core.credential_store import (
#     delete_credential,
#     list_credentials,
#     upsert_credential,
# )
# from app.db.database import get_db
# from app.db.tables import UserRecord

# router = APIRouter(prefix="/credentials", tags=["credentials"])

# # All service+key pairs the platform supports
# VALID_CREDENTIAL_KEYS: dict[str, list[str]] = {
#     "slack":      ["bot_token"],
#     "whatsapp":   ["access_token", "phone_number_id"],
#     "telegram":   ["bot_token"],
#     "discord":    ["bot_token"],
#     "twilio":     ["account_sid", "auth_token", "from_number"],
#     "sendgrid":   ["api_key"],
#     "smtp":       ["host", "port", "user", "password"],
#     "firebase":   ["server_key"],
#     "notion":     ["api_key"],
#     "google":     ["service_account_json"],
#     "airtable":   ["api_key"],
#     "jira":       ["domain", "email", "api_token"],
#     "trello":     ["api_key", "api_token"],
#     "linear":     ["api_key"],
#     "github":     ["token"],
#     "hubspot":    ["access_token"],
#     "freshdesk":  ["domain", "api_key"],
#     "zendesk":    ["subdomain", "email", "api_token"],
#     "razorpay":   ["key_id", "key_secret"],
#     "stripe":     ["secret_key"],
#     "delhivery":  ["api_token"],
#     "shiprocket": ["email", "password"],
#     "aws":        ["access_key_id", "secret_access_key", "region"],
#     "zoom":       ["account_id", "client_id", "client_secret"],
#     "twitter":    ["api_key", "api_secret", "access_token", "access_secret"],
#     "mailchimp":  ["api_key", "server_prefix"],
# }


# class SaveCredentialRequest(BaseModel):
#     service_name: str    # e.g. "slack"
#     credential_key: str  # e.g. "bot_token"
#     value: str           # plaintext — transmitted over HTTPS, encrypted before storage
#     label: str = ""      # optional user-friendly name e.g. "My Slack workspace"


# @router.post("", status_code=201)
# async def save_credential(
#     req: SaveCredentialRequest,
#     current_user: UserRecord = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     # Validate service + key against known catalogue
#     valid_keys = VALID_CREDENTIAL_KEYS.get(req.service_name)
#     if valid_keys is None:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Unknown service '{req.service_name}'. Supported: {sorted(VALID_CREDENTIAL_KEYS.keys())}",
#         )
#     if req.credential_key not in valid_keys:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Unknown key '{req.credential_key}' for service '{req.service_name}'. Valid keys: {valid_keys}",
#         )
#     if not req.value.strip():
#         raise HTTPException(status_code=400, detail="Credential value cannot be empty")

#     cred_id = await upsert_credential(
#         user_id=current_user.id,
#         service_name=req.service_name,
#         credential_key=req.credential_key,
#         plaintext_value=req.value,
#         label=req.label or f"{req.service_name} {req.credential_key}",
#         db=db,
#     )
#     return {
#         "id": cred_id,
#         "service_name": req.service_name,
#         "credential_key": req.credential_key,
#         "label": req.label,
#         "saved": True,
#     }


# @router.get("")
# async def get_credentials(
#     current_user: UserRecord = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     """Returns credential metadata — never returns the plaintext values."""
#     items = await list_credentials(current_user.id, db)
#     # Group by service for a cleaner response
#     grouped: dict[str, list[dict]] = {}
#     for item in items:
#         svc = item["service_name"]
#         grouped.setdefault(svc, []).append({
#             "key": item["credential_key"],
#             "label": item["label"],
#             "id": item["id"],
#             "updated_at": item["updated_at"],
#         })
#     return {"connected_services": grouped, "total": len(items)}


# @router.delete("/{service_name}/{credential_key}")
# async def remove_credential(
#     service_name: str,
#     credential_key: str,
#     current_user: UserRecord = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     deleted = await delete_credential(current_user.id, service_name, credential_key, db)
#     if not deleted:
#         raise HTTPException(status_code=404, detail="Credential not found")
#     return {"deleted": True, "service_name": service_name, "credential_key": credential_key}


# @router.get("/supported")
# async def supported_credentials():
#     """Returns the full list of supported service/key pairs — no auth required."""
#     return {"services": VALID_CREDENTIAL_KEYS}


# # ─── Test endpoints — fire a real API call right now ─────────────────────────

# class TestEmailRequest(BaseModel):
#     to: str           # recipient email
#     subject: str = "Test from AI Workflow Copilot"
#     body: str    = "This is a test email sent from your workflow automation platform."


# @router.post("/test/email")
# async def test_email(
#     req: TestEmailRequest,
#     current_user: UserRecord = Depends(get_current_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Send a real test email RIGHT NOW using your saved SMTP credentials.
#     No workflow needed — fires the executor directly.
#     """
#     from app.core.credential_store import get_user_credentials
#     from app.models.workflow import Node, NodeType
#     from app.service.execution import execute_node

#     # Load this user's decrypted credentials
#     creds = await get_user_credentials(current_user.id, db)

#     # Check smtp credentials exist before trying
#     if not creds.get("smtp.user"):
#         raise HTTPException(
#             status_code=400,
#             detail={
#                 "error": "smtp_not_configured",
#                 "message": "No Gmail credentials found. Save them first:",
#                 "steps": [
#                     'POST /credentials  {"service_name":"smtp","credential_key":"user","value":"you@gmail.com"}',
#                     'POST /credentials  {"service_name":"smtp","credential_key":"password","value":"xxxx xxxx xxxx xxxx"}',
#                 ],
#             },
#         )

#     if not creds.get("smtp.password"):
#         raise HTTPException(
#             status_code=400,
#             detail={
#                 "error": "smtp_password_missing",
#                 "message": "SMTP user found but password is missing.",
#                 "steps": [
#                     'POST /credentials  {"service_name":"smtp","credential_key":"password","value":"xxxx xxxx xxxx xxxx"}',
#                 ],
#             },
#         )

#     # Build a fake node with the test config
#     node = Node(
#         id="test",
#         type=NodeType.EMAIL_SEND,
#         config={
#             "to":            req.to,
#             "subject":       req.subject,
#             "body_template": req.body,
#             "provider":      "smtp",
#         },
#     )

#     result = await execute_node(node, context={}, creds=creds)

#     if result.status == "success":
#         return {
#             "status":   "sent",
#             "from":     creds.get("smtp.user"),
#             "to":       req.to,
#             "subject":  req.subject,
#             "message":  "Email delivered successfully. Check your inbox.",
#         }
#     else:
#         raise HTTPException(
#             status_code=500,
#             detail={
#                 "error":   "send_failed",
#                 "reason":  result.error,
#                 "from":    creds.get("smtp.user"),
#                 "to":      req.to,
#                 "tip":     (
#                     "Common causes: wrong app password, Gmail 2FA not enabled, "
#                     "or 'Less secure app access' blocked. "
#                     "Make sure you used a Gmail App Password, not your normal Gmail password."
#                 ),
#             },
#         )

"""
Credential management routes — all require JWT auth.

POST   /credentials                     — save or update one credential
GET    /credentials                     — list all connected integrations (no plaintext)
DELETE /credentials/{service}/{key}     — remove a credential
GET    /credentials/supported           — list all valid service/key pairs (no auth)
POST   /credentials/test/email          — send a real test email right now
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.credential_store import (
    delete_credential,
    get_user_credentials,
    list_credentials,
    upsert_credential,
)
from app.db.database import get_db
from app.db.tables import UserRecord

router = APIRouter(prefix="/credentials", tags=["credentials"])

# ─── Supported service → key catalogue ───────────────────────────────────────
VALID_CREDENTIAL_KEYS: dict[str, list[str]] = {
    "slack":      ["bot_token"],
    "whatsapp":   ["access_token", "phone_number_id"],
    "telegram":   ["bot_token"],
    "discord":    ["bot_token"],
    "twilio":     ["account_sid", "auth_token", "from_number"],
    "sendgrid":   ["api_key"],
    "smtp":       ["host", "port", "user", "password"],   # user = Gmail address, also used as From
    "firebase":   ["server_key"],
    "notion":     ["api_key"],
    "google":     ["service_account_json"],
    "airtable":   ["api_key"],
    "jira":       ["domain", "email", "api_token"],
    "trello":     ["api_key", "api_token"],
    "linear":     ["api_key"],
    "github":     ["token"],
    "hubspot":    ["access_token"],
    "freshdesk":  ["domain", "api_key"],
    "zendesk":    ["subdomain", "email", "api_token"],
    "razorpay":   ["key_id", "key_secret"],
    "stripe":     ["secret_key"],
    "delhivery":  ["api_token"],
    "shiprocket": ["email", "password"],
    "aws":        ["access_key_id", "secret_access_key", "region"],
    "zoom":       ["account_id", "client_id", "client_secret"],
    "twitter":    ["api_key", "api_secret", "access_token", "access_secret"],
    "mailchimp":  ["api_key", "server_prefix"],
}


# ─── Request models ───────────────────────────────────────────────────────────

class SaveCredentialRequest(BaseModel):
    service_name:   str        # e.g. "slack"
    credential_key: str        # e.g. "bot_token"
    value:          str        # plaintext — encrypted before storage
    label:          str = ""   # optional friendly name e.g. "My Slack workspace"


class TestEmailRequest(BaseModel):
    to:      str
    subject: str = "Test from AI Workflow Copilot"
    body:    str = "This is a test email sent from your workflow automation platform."


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def save_credential(
    req: SaveCredentialRequest,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save or update one credential. Value is AES-256-GCM encrypted before storage."""
    valid_keys = VALID_CREDENTIAL_KEYS.get(req.service_name)
    if valid_keys is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown service '{req.service_name}'. Supported: {sorted(VALID_CREDENTIAL_KEYS.keys())}",
        )
    if req.credential_key not in valid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown key '{req.credential_key}' for '{req.service_name}'. Valid keys: {valid_keys}",
        )
    if not req.value.strip():
        raise HTTPException(status_code=400, detail="Credential value cannot be empty")

    cred_id = await upsert_credential(
        user_id=current_user.id,
        service_name=req.service_name,
        credential_key=req.credential_key,
        plaintext_value=req.value,
        label=req.label or f"{req.service_name} {req.credential_key}",
        db=db,
    )
    return {
        "id":             cred_id,
        "service_name":   req.service_name,
        "credential_key": req.credential_key,
        "label":          req.label,
        "saved":          True,
    }


@router.get("")
async def get_credentials(
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all connected integrations. Never returns plaintext values."""
    items = await list_credentials(current_user.id, db)
    grouped: dict[str, list[dict]] = {}
    for item in items:
        svc = item["service_name"]
        grouped.setdefault(svc, []).append({
            "key":        item["credential_key"],
            "label":      item["label"],
            "id":         item["id"],
            "updated_at": item["updated_at"],
        })
    return {"connected_services": grouped, "total": len(items)}


@router.delete("/{service_name}/{credential_key}")
async def remove_credential(
    service_name:   str,
    credential_key: str,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a saved credential."""
    deleted = await delete_credential(current_user.id, service_name, credential_key, db)
    if not deleted:
        raise HTTPException(status_code=404, detail="Credential not found")
    return {"deleted": True, "service_name": service_name, "credential_key": credential_key}


@router.get("/supported")
async def supported_credentials():
    """List all valid service/key pairs. No auth required."""
    return {"services": VALID_CREDENTIAL_KEYS}


@router.post("/test/email")
async def test_email(
    req: TestEmailRequest,
    current_user: UserRecord = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Send a real test email RIGHT NOW using your saved SMTP/Gmail credentials.
    No workflow needed — fires the executor directly so you see the result immediately.
    """
    from app.models.workflow import Node, NodeType
    from app.service.execution import execute_node

    creds = await get_user_credentials(current_user.id, db)

    if not creds.get("smtp.user"):
        raise HTTPException(
            status_code=400,
            detail={
                "error":   "smtp_not_configured",
                "message": "No Gmail credentials found. Save them first:",
                "step_1":  'POST /credentials  {"service_name":"smtp","credential_key":"user","value":"you@gmail.com"}',
                "step_2":  'POST /credentials  {"service_name":"smtp","credential_key":"password","value":"xxxx xxxx xxxx xxxx"}',
            },
        )

    if not creds.get("smtp.password"):
        raise HTTPException(
            status_code=400,
            detail={
                "error":   "smtp_password_missing",
                "message": "Gmail address saved but App Password is missing.",
                "fix":     'POST /credentials  {"service_name":"smtp","credential_key":"password","value":"xxxx xxxx xxxx xxxx"}',
            },
        )

    node = Node(
        id="test",
        type=NodeType.EMAIL_SEND,
        config={
            "to":            req.to,
            "subject":       req.subject,
            "body_template": req.body,
            "provider":      "smtp",
        },
    )

    result = await execute_node(node, context={}, creds=creds)

    if result.status == "success":
        return {
            "status":  "sent",
            "from":    creds.get("smtp.user"),
            "to":      req.to,
            "subject": req.subject,
            "message": "Email delivered successfully. Check your inbox.",
        }

    raise HTTPException(
        status_code=500,
        detail={
            "error":  "send_failed",
            "reason": result.error,
            "from":   creds.get("smtp.user"),
            "to":     req.to,
            "tip": (
                "Common causes: wrong App Password, Gmail 2FA not enabled. "
                "Use a Gmail App Password (myaccount.google.com/apppasswords), "
                "not your normal Gmail password."
            ),
        },
    )