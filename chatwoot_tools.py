import os, requests

# The desktop environment can inject a dead local proxy. The chat service must call
# Chatwoot, Shopify, and OpenAI directly so customer replies do not get stuck.
for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_key, None)
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")
from dotenv import load_dotenv

load_dotenv()
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL", "https://app.chatwoot.com")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")
SAFE_TEST_MODE = os.getenv("RESIN_SAFE_TEST_MODE", "true").lower() != "false"
ENABLE_CHATWOOT_SEND = os.getenv("RESIN_ENABLE_CHATWOOT_SEND", "false").lower() == "true"
HUMAN_SUPPORT_AGENT_ID = os.getenv("RESIN_HUMAN_SUPPORT_AGENT_ID")


def chatwoot_headers():
    return {"api_access_token": CHATWOOT_API_TOKEN, "Content-Type": "application/json"}


def chatwoot_url(path):
    return f"{CHATWOOT_BASE_URL.rstrip('/')}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}{path}"


def direct_request(method, url, **kwargs):
    session = requests.Session()
    session.trust_env = False
    try:
        return session.request(method, url, **kwargs)
    finally:
        session.close()


def safe_request(method, url, **kwargs):
    if SAFE_TEST_MODE or not ENABLE_CHATWOOT_SEND:
        return {"dry_run": True, "method": method, "url": url, "payload": kwargs.get("json")}
    response = direct_request(method, url, headers=chatwoot_headers(), timeout=30, **kwargs)
    response.raise_for_status()
    try:
        return response.json()
    except Exception:
        return {"ok": True, "raw": response.text}


def normalize_label(value):
    value = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return "".join(ch for ch in value if ch.isalnum() or ch == "_")


def get_support_labels(issue_type=None, priority="normal", extra_labels=None):
    labels = ["resin_ai", "resin_society"]
    issue = normalize_label(issue_type or "general_support")
    if issue:
        labels.append(issue)
    if issue in ["damaged_or_missing_order", "damaged_order", "order_not_received", "wrong_item"]:
        labels += ["needs_human_review", "order_issue"]
    if issue in ["return_or_refund_request", "return_request", "refund_request", "exchange_request"]:
        labels += ["needs_human_review", "returns"]
    if issue in ["bulk_commercial_quote", "custom_table_lead", "flooring_contractor_lead"]:
        labels += ["needs_human_review", "lead"]
    if issue in ["human_requested", "ai_unsure"]:
        labels.append("needs_human_review")
    if priority in ["high", "urgent"]:
        labels.append(f"priority_{priority}")
    for label in extra_labels or []:
        clean = normalize_label(label)
        if clean:
            labels.append(clean)
    return sorted(set(labels))


def add_private_note(conversation_id, content):
    return safe_request("POST", chatwoot_url(f"/conversations/{conversation_id}/messages"), json={"content": content, "message_type": "outgoing", "private": True})


def apply_labels(conversation_id, labels):
    return safe_request("POST", chatwoot_url(f"/conversations/{conversation_id}/labels"), json={"labels": sorted(set(labels))})


def update_custom_attributes(conversation_id, attributes):
    clean_attrs = {k: v for k, v in (attributes or {}).items() if v not in [None, "", [], {}]}
    if not clean_attrs:
        return {"ok": True, "skipped": True}
    return safe_request("POST", chatwoot_url(f"/conversations/{conversation_id}/custom_attributes"), json={"custom_attributes": clean_attrs})


def assign_conversation(conversation_id, assignee_id=None):
    assignee_id = assignee_id or HUMAN_SUPPORT_AGENT_ID
    if not assignee_id:
        return {"ok": True, "skipped": True, "reason": "RESIN_HUMAN_SUPPORT_AGENT_ID is not set"}
    return safe_request("POST", chatwoot_url(f"/conversations/{conversation_id}/assignments"), json={"assignee_id": int(assignee_id)})


def create_support_case(conversation_id, issue_type="general_support", customer_message="", order_number=None, customer_email=None, priority="normal", labels=None, summary="", extra_attributes=None):
    issue_type = normalize_label(issue_type or "general_support")
    priority = normalize_label(priority or "normal")
    final_labels = get_support_labels(issue_type=issue_type, priority=priority, extra_labels=labels)
    note = "\n".join([
        "Human support needed - Resin Society AI escalation",
        "",
        "This conversation was routed to human support because the AI should not resolve it alone.",
        f"Issue type: {issue_type}",
        f"Priority: {priority}",
        f"Order number: {order_number or ''}",
        f"Customer email: {customer_email or ''}",
        "",
        "Customer message:",
        customer_message or "(No message captured)",
        "",
        "AI summary:",
        summary or "(No summary captured)",
    ])
    custom_attributes = {"resin_ai_case": True, "resin_issue_type": issue_type, "resin_priority": priority, "resin_order_number": order_number, "resin_customer_email": customer_email, "resin_ai_summary": summary}
    if extra_attributes:
        custom_attributes.update(extra_attributes)
    results = {"conversation_id": conversation_id, "issue_type": issue_type, "priority": priority, "labels": final_labels}
    for key, fn in [("labels_result", lambda: apply_labels(conversation_id, final_labels)), ("attributes_result", lambda: update_custom_attributes(conversation_id, custom_attributes)), ("assignment_result", lambda: assign_conversation(conversation_id)), ("private_note_result", lambda: add_private_note(conversation_id, note))]:
        try:
            results[key] = fn()
        except Exception as e:
            results[key.replace("result", "error")] = str(e)
    return results


def resolve_conversation(conversation_id):
    return safe_request("POST", chatwoot_url(f"/conversations/{conversation_id}/toggle_status"), json={"status": "resolved"})


def add_resolution_note(conversation_id, reason="Auto-resolved by Resin Society AI"):
    return add_private_note(conversation_id, f"Resin Society AI Auto-Resolved\n\nReason: {reason}")


def get_conversation_messages(conversation_id):
    response = direct_request("GET", chatwoot_url(f"/conversations/{conversation_id}/messages"), headers=chatwoot_headers(), timeout=30)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        return data.get("payload") or data.get("messages") or []
    return data if isinstance(data, list) else []


def is_incoming_customer_message(message):
    message_type = message.get("message_type")
    return message.get("private") is not True and message_type in ["incoming", 0]


def has_new_customer_reply(conversation_id, source_message_id=None):
    if source_message_id is None:
        return False
    try:
        source_message_id = int(source_message_id)
    except Exception:
        return False
    for message in get_conversation_messages(conversation_id):
        try:
            message_id = int(message.get("id"))
        except Exception:
            continue
        if message_id > source_message_id and is_incoming_customer_message(message):
            return True
    return False


def close_conversation_if_no_new_customer_reply(conversation_id, source_message_id=None, reason="No customer reply after Resin Society AI answer"):
    if SAFE_TEST_MODE or not ENABLE_CHATWOOT_SEND:
        return {"dry_run": True, "conversation_id": conversation_id, "reason": reason}
    if has_new_customer_reply(conversation_id, source_message_id):
        return {"resolved": False, "reason": "Customer replied again before auto-close."}
    note = add_resolution_note(conversation_id, reason)
    result = resolve_conversation(conversation_id)
    return {"resolved": True, "note": note, "result": result, "reason": reason}


def should_auto_resolve(intent_data=None, reply_text=""):
    intent_data = intent_data or {}
    if intent_data.get("requested_human") or intent_data.get("damage_issue") or intent_data.get("return_question"):
        return False
    if intent_data.get("bulk_or_commercial") or intent_data.get("custom_table_lead") or intent_data.get("flooring_contractor_lead"):
        return False
    if "team" in (reply_text or "").lower() and "follow" in (reply_text or "").lower():
        return False
    return intent_data.get("question_type") in ["product_recommendation", "shipping_question", "general_question", "order_question"]


def maybe_auto_resolve_conversation(conversation_id, intent_data=None, reply_text=""):
    if not should_auto_resolve(intent_data, reply_text):
        return {"resolved": False, "reason": "Needs human review or not eligible."}
    note = add_resolution_note(conversation_id)
    result = resolve_conversation(conversation_id)
    return {"resolved": True, "note": note, "result": result}
