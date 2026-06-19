"""
Intent classification layer.

Classifies user instructions into:
  - "create_workflow"       → proceed to workflow generation
  - "out_of_scope"          → irrelevant request (tax, legal, etc.) — return guidance
  - "partially_supported"   → valid automation idea but some services not in catalog

No LLM call here — pure rule-based, fast, zero hallucination risk.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from app.core.catalog import search_nodes

# ─── Out-of-scope patterns ────────────────────────────────────────────────────
_OOS_PATTERNS = [
    r"\btax\s*filing\b", r"\bgst\s*return\b", r"\bitr\b", r"\bincome\s*tax\b",
    r"\bca\b", r"\bchartered\s*accountant\b", r"\baudit\b", r"\blegal\s*advice\b",
    r"\bpayroll\b", r"\bsalary\s*slip\b", r"\bpf\b", r"\bepf\b", r"\besi\b",
    r"\bform\s*16\b", r"\bmedical\s*prescription\b", r"\bdoctor\s*appointment\b",
    r"\bloan\s*application\b", r"\bmortgage\b",
    r"\bwrite\s*(an?\s+)?(essay|poem|story)\b",
    r"\btell\s+me\s+a\s+joke\b", r"\bwhat\s+is\s+the\s+capital\b",
]
_OOS_RE = re.compile("|".join(_OOS_PATTERNS), re.I)

# ─── Guidance for out-of-scope topics ────────────────────────────────────────
_TOPIC_GUIDANCE: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\btax\b|\bgst\b|\bitr\b|\bincome\s*tax\b|\btax\s*filing\b", re.I),
        (
            "Tax filing is outside my scope — I only automate business workflows. "
            "For tax filing in India you can use:\n"
            "• **ClearTax** (cleartax.in) — ITR & GST returns\n"
            "• **Tax2Win** — ITR e-filing with CA assistance\n"
            "• **Quicko** — GST + ITR\n"
            "• **incometax.gov.in** — government self-filing portal\n\n"
            "💡 If you want to *automate* something tax-related (e.g. email invoice PDFs "
            "to your accountant every month), describe that and I can build a workflow for it."
        ),
    ),
    (
        re.compile(r"\bpayroll\b|\bsalary\s*slip\b|\bpf\b|\bepf\b|\bform\s*16\b", re.I),
        (
            "Payroll processing is outside my scope. Recommended tools:\n"
            "• **Razorpay Payroll** — automated salary, PF, ESI\n"
            "• **Zoho Payroll** — India-compliant payroll\n"
            "• **Keka HR** — payroll + HRMS\n\n"
            "💡 I *can* automate payroll-adjacent tasks like sending salary slip emails "
            "after payroll runs, or notifying employees on Slack/WhatsApp."
        ),
    ),
    (
        re.compile(r"\blegal\b|\bcontract\s*law\b|\bchartered\s*accountant\b|\baudit\b", re.I),
        (
            "Legal or accounting advice is outside my scope. Please consult a CA or lawyer.\n\n"
            "💡 I can automate tasks *around* legal work — e.g. sending contract PDFs for "
            "e-signature, setting reminders, or logging agreements in Notion."
        ),
    ),
    (
        re.compile(r"\bloan\b|\bmortgage\b", re.I),
        (
            "Loan applications are outside my scope. Check with your bank or NBFC directly.\n\n"
            "💡 I can automate loan-related notifications or reminders if needed."
        ),
    ),
]

# ─── Services we know users mention but we don't support ─────────────────────
_UNSUPPORTED_SERVICES: dict[str, str] = {
    "paytm": (
        "Paytm does not offer a public automation API at this time.\n"
        "✅ **Alternative**: Use **razorpay_create_payment_link** — Razorpay supports "
        "UPI, cards, net banking and works identically for collecting payments."
    ),
    "phonepe": (
        "PhonePe does not have a workflow automation API.\n"
        "✅ **Alternative**: Use **razorpay_create_payment_link** to generate a UPI-compatible payment link."
    ),
    "gpay": (
        "Google Pay does not offer an automation API.\n"
        "✅ **Alternative**: **razorpay_create_payment_link** generates links payable via GPay/UPI."
    ),
    "upi": (
        "Direct UPI integration is not available via API.\n"
        "✅ **Alternative**: Razorpay payment links support UPI — use **razorpay_create_payment_link**."
    ),
    "amazon": (
        "Amazon Seller API requires seller registration and is not in our catalog.\n"
        "✅ **Alternative**: Use a **webhook** trigger to receive order events if Amazon exposes one, "
        "or manually trigger via **schedule_trigger**."
    ),
    "flipkart": (
        "Flipkart Seller API is invite-only and not in our catalog.\n"
        "✅ **Alternative**: Use a **webhook** node if Flipkart sends order callbacks."
    ),
    "swiggy": (
        "Swiggy does not offer a public API for automation.\n"
        "✅ **Alternative**: Use a **whatsapp_trigger** to receive orders and build a manual workflow."
    ),
    "zomato": (
        "Zomato API is restricted and not in our catalog.\n"
        "✅ **Alternative**: Use a **whatsapp_trigger** or **webhook** to receive order events."
    ),
    "quickbooks": (
        "QuickBooks is not in our catalog yet.\n"
        "✅ **Alternative**: Use **http_request** with the QuickBooks REST API directly."
    ),
    "tally": (
        "Tally ERP has no cloud API.\n"
        "✅ **Alternative**: Export Tally data as CSV and process it with **google_sheets_append**."
    ),
}


@dataclass
class FeasibilityResult:
    is_feasible: bool
    supported_node_types: list[str] = field(default_factory=list)
    unsupported_services: list[str] = field(default_factory=list)
    alternatives_guidance: str = ""


@dataclass
class IntentResult:
    intent: str           # "create_workflow" | "out_of_scope" | "partially_supported"
    guidance: str = ""    # human-readable message when not "create_workflow"
    feasibility: FeasibilityResult | None = None


# ─── Public API ───────────────────────────────────────────────────────────────

def classify_intent(instruction: str) -> IntentResult:
    """
    Fast rule-based intent classification — no LLM call.
    Returns an IntentResult that the service layer acts on.
    """
    # 1. Hard out-of-scope check
    if _OOS_RE.search(instruction):
        return IntentResult(
            intent="out_of_scope",
            guidance=_get_oos_guidance(instruction),
        )

    # 2. Feasibility check (are there unsupported services?)
    feas = _check_feasibility(instruction)

    if not feas.is_feasible:
        return IntentResult(
            intent="out_of_scope",
            guidance=(
                "I don't currently support this integration. Here are your options:\n\n"
                + feas.alternatives_guidance
            ),
            feasibility=feas,
        )

    if feas.unsupported_services:
        return IntentResult(
            intent="partially_supported",
            guidance=feas.alternatives_guidance,
            feasibility=feas,
        )

    return IntentResult(intent="create_workflow", feasibility=feas)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_oos_guidance(text: str) -> str:
    for pattern, guidance in _TOPIC_GUIDANCE:
        if pattern.search(text):
            return guidance
    return (
        "That request is outside my scope. I specialise in automating business "
        "workflows by connecting apps like WhatsApp, Razorpay, Delhivery, Gmail, "
        "Slack, Notion, and more.\n\n"
        "Try describing a business process you want to automate end-to-end."
    )


def _check_feasibility(text: str) -> FeasibilityResult:
    text_lower = text.lower()
    unsupported: list[str] = []
    guidance_parts: list[str] = []

    for service, message in _UNSUPPORTED_SERVICES.items():
        if re.search(rf"\b{re.escape(service)}\b", text_lower):
            unsupported.append(service)
            guidance_parts.append(f"**{service.title()}**: {message}")

    # Find which catalog nodes are relevant
    relevant = search_nodes(text, top_k=6)
    supported_types = [n.type for n in relevant]

    if unsupported and not supported_types:
        return FeasibilityResult(
            is_feasible=False,
            unsupported_services=unsupported,
            alternatives_guidance="\n\n".join(guidance_parts),
        )

    if unsupported:
        header = (
            "I can automate the supported parts of your workflow. "
            "Here's what I found about the unsupported pieces:\n\n"
        )
        return FeasibilityResult(
            is_feasible=True,
            supported_node_types=supported_types,
            unsupported_services=unsupported,
            alternatives_guidance=header + "\n\n".join(guidance_parts),
        )

    return FeasibilityResult(is_feasible=True, supported_node_types=supported_types)
