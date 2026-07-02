from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os, re, time, requests

# The desktop environment can inject a dead local proxy. The chat service must call
# Chatwoot, Shopify, and OpenAI directly so customer replies do not get stuck.
for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_key, None)
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone

from shopify_tools import search_products, lookup_order, lookup_customer_orders, get_order_tracking
from store_intelligence import query_catalog, preload_store_cache, get_catalog_cache_status
from knowledge_tools import query_knowledge
from blog_tools import search_articles
from memory_tools import add_message, build_memory_text
from openai_agent import run_resin_agent
from policy_tools import get_policy_info
from chatwoot_tools import create_support_case, maybe_auto_resolve_conversation
from learning_tools import log_conversation_turn, log_lead, build_summary_report

load_dotenv()

BRAND = "Resin Society"
SITE_URL = "https://resinsociety.net"
SUPPORT_EMAIL = os.getenv("RESIN_SUPPORT_EMAIL", "hello@resinsociety.net")
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL", "https://app.chatwoot.com")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID")
CHATWOOT_API_TOKEN = os.getenv("CHATWOOT_API_TOKEN")
RESIN_CHATWOOT_INBOX_ID = os.getenv("RESIN_CHATWOOT_INBOX_ID")
SAFE_TEST_MODE = os.getenv("RESIN_SAFE_TEST_MODE", "true").lower() != "false"
ENABLE_CHATWOOT_SEND = os.getenv("RESIN_ENABLE_CHATWOOT_SEND", "false").lower() == "true"
TARGET_RESPONSE_SECONDS = float(os.getenv("RESIN_TARGET_RESPONSE_SECONDS", "5"))
WAITING_MESSAGE = "I'm checking that for you now so I don't give you the wrong answer. This may take 1-3 minutes."
TEAM_FOLLOWUP_MESSAGE = "I want to make sure I give you the right answer. I'm going to have the Resin Society team review this and follow up."
BACKGROUND_EXECUTOR = ThreadPoolExecutor(max_workers=int(os.getenv("RESIN_CHAT_WORKERS", "4")))

app = FastAPI(title="Resin Society AI Chat")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://resinsociety.net", "https://www.resinsociety.net", "http://localhost:3000", "http://localhost:5000", "http://127.0.0.1:3000", "http://127.0.0.1:5000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def preload_fast_answer_data():
    preload_store_cache()
    for topic in ["shipping", "returns", "orders", "contact", "trust", "general", "custom", "flooring"]:
        try:
            get_policy_info(topic=topic)
        except Exception as e:
            print("Policy preload failed:", topic, e)

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def new_timing_metrics():
    return {"started_at": time.perf_counter(), "total_response_time_ms": 0, "retrieval_time_ms": 0, "shopify_api_time_ms": 0, "ai_model_time_ms": 0, "steps": [], "slowest_step": None, "timed_out": False, "stage": "final"}

def record_timing(metrics, step, elapsed_seconds, category="retrieval"):
    if not metrics:
        return
    elapsed_ms = round(elapsed_seconds * 1000, 2)
    metrics["steps"].append({"step": step, "category": category, "ms": elapsed_ms})
    if category == "shopify":
        metrics["shopify_api_time_ms"] += elapsed_ms
    elif category == "ai_model":
        metrics["ai_model_time_ms"] += elapsed_ms
    else:
        metrics["retrieval_time_ms"] += elapsed_ms
    if not metrics.get("slowest_step") or elapsed_ms > metrics["slowest_step"].get("ms", 0):
        metrics["slowest_step"] = {"step": step, "category": category, "ms": elapsed_ms}

def timed_call(metrics, step, category, fn):
    started = time.perf_counter()
    try:
        return fn()
    finally:
        record_timing(metrics, step, time.perf_counter() - started, category)

def finish_timing(metrics):
    if not metrics:
        return {}
    metrics["total_response_time_ms"] = round((time.perf_counter() - metrics["started_at"]) * 1000, 2)
    return metrics

def log_chat_timing(conversation_id, endpoint, metrics):
    metrics = finish_timing(metrics)
    print("========== RESIN CHAT TIMING ==========")
    print("Endpoint:", endpoint)
    print("Conversation:", conversation_id)
    print("Total response time ms:", metrics.get("total_response_time_ms"))
    print("Slowest step:", metrics.get("slowest_step"))
    print("Timed out:", metrics.get("timed_out"))
    print("Catalog cache:", get_catalog_cache_status())
    print("=======================================")
    return metrics

def clean_price(price):
    try:
        return f"${float(price):,.2f}".replace(".00", "")
    except Exception:
        return str(price or "").strip()

def clean_text(value, max_len=700):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:max_len].rstrip()

def extract_email(text):
    m = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", text or "")
    return m.group(0).lower() if m else ""

def extract_order_number(text):
    m = re.search(r"(?:order\s*)?#?\s*(\d{4,})", text or "", re.I)
    return m.group(1) if m else ""


def is_simple_greeting(text):
    msg = re.sub(r"[^a-z\s]", "", (text or "").lower()).strip()
    return msg in ["hi", "hello", "hey", "hiya", "good morning", "good afternoon", "good evening"]


def storefront_greeting():
    return "Hi, I'm Sol. I can help you shop Resin Society home decor and resin art, explore custom tables, choose supplies, plan a resin project, or check shipping, returns, and orders. What can I help you find today?"


def extract_project_size(text):
    for pattern in [r"\b\d+(?:\.\d+)?\s*(?:x|by)\s*\d+(?:\.\d+)?\s*(?:x|by)?\s*\d*(?:\.\d+)?\s*(?:in|inch|inches|ft|feet|foot|sq ft|square feet)?", r"\b\d+(?:\.\d+)?\s*(?:sq ft|square feet|gallons?|oz|ounces?|liters?|quarts?)\b"]:
        m = re.search(pattern, text or "", re.I)
        if m:
            return m.group(0)
    return ""

def detect_customer_intent(message):
    msg = (message or "").lower()
    project_types = {
        "river_table": ["river table", "slab table", "live edge"],
        "tabletop": ["table top", "tabletop", "bar top", "countertop"],
        "deep_pour": ["deep pour", "casting", "thick pour"],
        "flooring": ["floor", "flooring", "garage floor", "metallic floor", "contractor"],
        "art_mold": ["mold", "mould", "coaster", "jewelry", "art", "tray"],
        "custom_table": ["custom table", "build me a table", "commission", "dining table"],
    }
    project_type = next((name for name, needles in project_types.items() if any(n in msg for n in needles)), "")
    product_words = ["pigment", "mica", "powder", "mold", "sanding", "polishing", "wood", "river table", "tabletop", "deep pour", "floor", "recommend", "best", "how much", "calculator", "need", "kit", "supplies", "tools"]
    damage_words = ["damaged", "broken", "leaking", "missing", "wrong item", "not received", "never arrived"]
    quote_words = ["bulk", "commercial", "wholesale", "contractor", "quote", "large order"]
    return {
        "email": extract_email(message),
        "order_number": extract_order_number(message),
        "project_type": project_type,
        "project_size": extract_project_size(message),
        "question_type": "order_question" if any(x in msg for x in ["order", "tracking", "where is", "shipped", "delivered"]) else "return_question" if any(x in msg for x in ["return", "refund", "exchange", "cancel"]) else "shipping_question" if any(x in msg for x in ["shipping", "ship", "delivery", "arrive"]) else "lead" if project_type in ["custom_table", "flooring"] or any(x in msg for x in quote_words) else "product_recommendation" if any(x in msg for x in product_words) else "general_question",
        "requested_human": any(x in msg for x in ["angry", "mad", "frustrated", "lawsuit", "chargeback", "human", "person", "call me"]),
        "damage_issue": any(x in msg for x in damage_words),
        "return_question": any(x in msg for x in ["return", "refund", "exchange", "cancel"]),
        "order_question": any(x in msg for x in ["order", "tracking", "where is", "shipped", "delivered"]),
        "bulk_or_commercial": any(x in msg for x in quote_words),
        "custom_table_lead": project_type == "custom_table",
        "flooring_contractor_lead": project_type == "flooring" and any(x in msg for x in ["contractor", "quote", "commercial", "garage"]),
        "unsure_risk": any(x in msg for x in ["not sure", "confused", "technical data", "sds", "safety data", "food safe"]),
    }

def detect_lead(intent_data, message, page_context):
    msg = (message or "").lower()
    if not (intent_data.get("project_type") or intent_data.get("bulk_or_commercial") or any(x in msg for x in ["quote", "custom", "timeline", "budget", "project"])):
        return None
    lead_type = "custom_table" if intent_data.get("custom_table_lead") else "flooring_contractor" if intent_data.get("flooring_contractor_lead") else "bulk_commercial" if intent_data.get("bulk_or_commercial") else "project"
    return {"lead_type": lead_type, "name": page_context.get("customer_name", ""), "email": intent_data.get("email") or page_context.get("customer_email", ""), "project_type": intent_data.get("project_type", ""), "project_size": intent_data.get("project_size", ""), "timeline": "mentioned" if re.search(r"\b(week|month|asap|soon|spring|summer|fall|winter|timeline)\b", msg) else "", "budget_range": "mentioned" if "budget" in msg or "$" in msg else "", "product_interest": page_context.get("product_title", ""), "custom_table_inquiry": bool(intent_data.get("custom_table_lead")), "flooring_inquiry": bool(intent_data.get("flooring_contractor_lead"))}

def escalation_type(intent_data):
    if intent_data.get("requested_human"):
        return "human_requested"
    if intent_data.get("damage_issue"):
        return "damaged_or_missing_order"
    if intent_data.get("return_question"):
        return "return_or_refund_request"
    if intent_data.get("bulk_or_commercial"):
        return "bulk_commercial_quote"
    if intent_data.get("custom_table_lead"):
        return "custom_table_lead"
    if intent_data.get("flooring_contractor_lead"):
        return "flooring_contractor_lead"
    if intent_data.get("unsure_risk"):
        return "ai_unsure"
    return ""

def build_api_page_context(payload):
    context = payload.get("page_context") if isinstance(payload.get("page_context"), dict) else {}
    return {"url": payload.get("url") or context.get("url") or "", "product_handle": payload.get("product_handle") or context.get("product_handle") or "", "product_title": payload.get("product_title") or context.get("product_title") or "", "collection_handle": payload.get("collection_handle") or context.get("collection_handle") or "", "customer_email": payload.get("customer_email") or context.get("customer_email") or "", "customer_name": payload.get("customer_name") or context.get("customer_name") or ""}

def extract_frontend_context(data):
    attrs = ((data.get("conversation") or {}).get("custom_attributes") or {}) if isinstance(data, dict) else {}
    additional = data.get("additional_attributes") or {}
    return {"url": attrs.get("resin_page_url") or additional.get("referer") or "", "product_handle": attrs.get("resin_product_handle") or "", "product_title": attrs.get("resin_product_title") or "", "collection_handle": attrs.get("resin_collection_handle") or "", "customer_email": attrs.get("resin_customer_email") or "", "customer_name": attrs.get("resin_customer_name") or ""}

def product_line(product):
    return " - ".join(x for x in [product.get("title") or "This product", clean_price(product.get("price")), clean_text(product.get("short_description") or product.get("description"), 130), product.get("url") or ""] if x)

def is_resin_amount_question(message):
    msg = (message or "").lower()
    amount_words = ["how much", "calculator", "calculate", "estimate", "need", "gallons", "ounces", "volume"]
    resin_words = ["resin", "epoxy", "pour", "river table", "flood coat", "tabletop", "mold", "casting", "slab"]
    return any(x in msg for x in amount_words) and any(x in msg for x in resin_words)


def detect_resin_project_type(message):
    msg = (message or "").lower()
    if any(x in msg for x in ["flood coat", "top coat", "seal coat", "tabletop coating", "table top coating", "bar top", "countertop", "coat my", "coating"]):
        return "flood_coat"
    if any(x in msg for x in ["river table", "resin river", "live edge", "river", "channel", "gap", "void"]):
        return "river_table"
    if any(x in msg for x in ["mold", "mould", "casting", "cast", "coaster", "tray", "sphere", "dice", "blank"]):
        return "mold_casting"
    if any(x in msg for x in ["solid slab", "full slab", "all resin", "solid resin", "no wood", "entire slab", "whole slab"]):
        return "solid_slab"
    return "other"


def _unit_to_inches(value, unit, default_unit="in"):
    unit = (unit or default_unit or "in").lower()
    if unit in ["ft", "feet", "foot"]:
        return value * 12
    return value


def parse_resin_dimensions(message):
    text = (message or "").lower()
    pattern = r"(\d+(?:\.\d+)?)\s*(ft|feet|foot|in|inch|inches)?\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*(ft|feet|foot|in|inch|inches)?(?:\s*(?:x|by)\s*(\d+(?:\.\d+)?)\s*(ft|feet|foot|in|inch|inches)?)?"
    match = re.search(pattern, text)
    if not match:
        return None
    a, au, b, bu, c, cu = match.groups()
    nums = [float(a), float(b)] + ([float(c)] if c else [])
    has_units = bool(au or bu or cu)
    table_context = any(x in text for x in ["table", "counter", "bar", "desktop", "slab"])
    resin_space_context = any(x in text for x in ["gap", "void", "channel", "river gap", "river space", "empty space"])
    default_plan_unit = "in" if resin_space_context else "ft" if table_context and not has_units else "in"
    length_in = _unit_to_inches(float(a), au, default_plan_unit)
    width_in = _unit_to_inches(float(b), bu, default_plan_unit)
    depth_in = _unit_to_inches(float(c), cu, "in") if c else None
    return {"length_in": length_in, "width_in": width_in, "depth_in": depth_in, "numbers": nums, "has_units": has_units, "raw": match.group(0).strip(), "assumed_plan_feet": table_context and not (au or bu)}


def gallons_for_rect(length_in, width_in, depth_in):
    return (length_in * width_in * depth_in) / 231


def format_gallons(value):
    if value < 1:
        return f"{value:.2f} gal"
    if value < 10:
        return f"{value:.1f} gal"
    return f"{value:.0f} gal"


def resin_example_lines(length_in=None):
    table_len = length_in or 96
    flood_18 = gallons_for_rect(96, 48, 0.125)
    flood_14 = gallons_for_rect(96, 48, 0.25)
    river_6 = gallons_for_rect(table_len, 6, 2)
    river_12 = gallons_for_rect(table_len, 12, 2)
    return [
        f"1/8 inch flood coat on an 8 ft x 4 ft top: about {format_gallons(flood_18)}.",
        f"1/4 inch flood coat on an 8 ft x 4 ft top: about {format_gallons(flood_14)}.",
        f"6 inch average river x 2 inch deep over 8 ft: about {format_gallons(river_6)}.",
        f"12 inch average river x 2 inch deep over 8 ft: about {format_gallons(river_12)}.",
    ]


def resin_amount_answer(message):
    if not is_resin_amount_question(message):
        return None
    msg = (message or "").lower()
    project_type = detect_resin_project_type(message)
    dims = parse_resin_dimensions(message)

    if dims and dims.get("depth_in"):
        full_volume = gallons_for_rect(dims["length_in"], dims["width_in"], dims["depth_in"])
        only_rect_dims = project_type == "other" and not any(x in msg for x in ["river", "gap", "void", "channel", "flood", "coat", "mold", "casting"])
        if full_volume > 10 and only_rect_dims:
            examples = "\n".join(f"- {line}" for line in resin_example_lines(dims["length_in"]))
            return (
                "Before I calculate that as a solid block, what type of pour are you doing: flood coat/tabletop coating, river table, mold casting, full solid resin slab, or something else?\n\n"
                f"I do not want to assume the whole {dims['raw']} area is resin. A full 8 ft x 4 ft x 2 inch solid resin slab is about 40 gallons, and that is uncommon. Most tables use much less because the wood takes up most of the volume.\n\n"
                "For a realistic estimate, measure the empty space where wood is not: average river/gap width, length, and pour depth. If you are coating the top, use the coating thickness instead.\n\n"
                "Quick examples:\n" + examples
            )

    if project_type == "other":
        examples = "\n".join(f"- {line}" for line in resin_example_lines(dims["length_in"] if dims else None))
        if dims and not dims.get("depth_in"):
            size_note = f" For an {dims['raw']} table, the answer can swing a lot because that footprint is not usually all resin."
        else:
            size_note = ""
        return (
            "Are you building a river table, applying a flood coat/tabletop coating, pouring into a mold, or making a full solid resin slab?"
            + size_note +
            " The amount can vary from a few gallons for a coating to nearly 40 gallons for a full 8 ft x 4 ft x 2 inch solid slab.\n\n"
            "For the most accurate estimate, measure only the resin space: average gap/river width, length, and depth, plus any resin coat over the wood.\n\n"
            "Quick examples:\n" + examples
        )

    if project_type == "flood_coat":
        if not dims:
            return "For a flood coat/tabletop coating, send the top length and width plus the coating thickness, usually 1/8 inch or 1/4 inch. You are coating the surface, not filling the whole tabletop thickness."
        depth = dims.get("depth_in") or (0.25 if "1/4" in msg or ".25" in msg else 0.125)
        gallons = gallons_for_rect(dims["length_in"], dims["width_in"], depth)
        assumed = "I used 1/8 inch as the coating thickness. " if not dims.get("depth_in") else ""
        return f"For a flood coat/tabletop coating, {assumed}{dims['raw']} at {depth:g} inch thick is about {format_gallons(gallons)}. Add a little extra for edge drips, seal coats, and waste. If you meant a river/void instead, measure only the open gap where wood is not."

    if project_type == "river_table":
        if not dims or not dims.get("depth_in"):
            examples = "\n".join(f"- {line}" for line in resin_example_lines(dims["length_in"] if dims else None))
            return "For a river table, do not use the full tabletop width unless the whole center is resin. Measure the average river/gap width, river length, and pour depth.\n\nQuick examples:\n" + examples
        gallons = gallons_for_rect(dims["length_in"], dims["width_in"], dims["depth_in"])
        return f"If {dims['raw']} is the actual open river/gap, the estimate is about {format_gallons(gallons)} before waste. Add roughly 10-15% for uneven live edges, leaks, and mixing loss. If those dimensions are the whole tabletop, send the average empty river width instead."

    if project_type == "mold_casting":
        if not dims or not dims.get("depth_in"):
            return "For a mold casting, send the inside length, inside width, and pour depth of the mold. If the shape is irregular, estimate the average filled area or send the mold capacity if you know it."
        gallons = gallons_for_rect(dims["length_in"], dims["width_in"], dims["depth_in"])
        return f"For a mold casting with inside dimensions of {dims['raw']}, the estimate is about {format_gallons(gallons)}. Use the inside mold space only, then add a small buffer for drips and leftover in the mixing cup."

    if project_type == "solid_slab":
        if not dims or not dims.get("depth_in"):
            return "For a full solid resin slab, send length, width, and slab thickness. Just a heads up: full solid slabs use a lot of resin; an 8 ft x 4 ft x 2 inch slab is about 40 gallons."
        gallons = gallons_for_rect(dims["length_in"], dims["width_in"], dims["depth_in"])
        return f"A full solid resin slab at {dims['raw']} is about {format_gallons(gallons)}. That is only right if the entire shape is resin with no wood or filler taking up space. For most tables, measure the empty river/void area instead."

    return None
def maybe_create_support_case(conversation_id, issue_type, message, intent_data, page_context, priority="normal"):
    if SAFE_TEST_MODE or not ENABLE_CHATWOOT_SEND:
        return {"dry_run": True, "reason": "RESIN_SAFE_TEST_MODE or RESIN_ENABLE_CHATWOOT_SEND disabled", "conversation_id": conversation_id, "issue_type": issue_type, "priority": priority}
    return create_support_case(conversation_id=conversation_id, issue_type=issue_type, customer_message=message, order_number=intent_data.get("order_number"), customer_email=intent_data.get("email") or page_context.get("customer_email"), priority=priority, labels=["resin_society"], summary=message[:800], extra_attributes={"resin_page_url": page_context.get("url"), "resin_project_type": intent_data.get("project_type"), "resin_project_size": intent_data.get("project_size")})

def try_fast_deterministic_answer(message, page_context, conversation_id, learning_tracker, timing_metrics):
    if is_simple_greeting(message):
        record_timing(timing_metrics, "storefront_greeting", 0, "retrieval")
        return storefront_greeting()
    intent = detect_customer_intent(message)
    amount = resin_amount_answer(message)
    if amount:
        record_timing(timing_metrics, "resin_amount", 0, "retrieval")
        return amount
    if intent.get("damage_issue"):
        learning_tracker["support_case"] = maybe_create_support_case(conversation_id, "damaged_or_missing_order", message, intent, page_context, "high")
        return "I'm sorry that happened. Please send your order number, checkout email, and photos if anything arrived damaged. The Resin Society team should review this instead of me guessing at a refund or replacement."
    if intent.get("return_question"):
        policy = timed_call(timing_metrics, "get_policy_info:returns", "retrieval", lambda: get_policy_info(topic="returns"))
        learning_tracker["support_case"] = maybe_create_support_case(conversation_id, "return_or_refund_request", message, intent, page_context)
        return clean_text(policy.get("answer_preview"), 700)
    if intent.get("order_question") and not (intent.get("order_number") or intent.get("email") or page_context.get("customer_email")):
        return "Please send your order number and checkout email, and I can check the Resin Society order without guessing."
    if intent.get("shipping_question") and not intent.get("order_number"):
        policy = timed_call(timing_metrics, "get_policy_info:shipping", "retrieval", lambda: get_policy_info(topic="shipping"))
        return clean_text(policy.get("answer_preview"), 700)
    if intent.get("question_type") in ["product_recommendation", "lead"]:
        try:
            result = timed_call(timing_metrics, "query_catalog:resin_fast_path", "retrieval", lambda: query_catalog(user_query=message, page_context=page_context, limit=6))
            products = result.get("products") or []
            learning_tracker["products"] = products
            if products:
                return "Here are the closest Resin Society options I'd look at first:\n" + "\n".join(product_line(p) for p in products[:3])
        except Exception as e:
            learning_tracker.setdefault("tools_called", []).append("query_catalog:error")
            learning_tracker["catalog_error"] = str(e)
            print("Resin catalog lookup failed:", e)
            if intent.get("question_type") == "lead":
                return "I can help route this as a Resin Society project lead. Send your name, email, project type, project size, timeline, budget range, and any product you are considering."
    return None

def safe_tool_response(tool_name, learning_tracker, fn):
    try:
        learning_tracker.setdefault("tools_called", []).append(tool_name)
        return fn()
    except Exception as e:
        return {"error": str(e), "tool": tool_name}

def make_tool_executor(conversation_id, raw_user_message, page_context, learning_tracker):
    def tool_executor(tool_name, arguments):
        args = arguments or {}
        if tool_name == "query_catalog":
            result = safe_tool_response(tool_name, learning_tracker, lambda: query_catalog(args.get("query") or raw_user_message, page_context, args.get("limit", 6)))
            learning_tracker["products"] = result.get("products", []) if isinstance(result, dict) else []
            return result
        if tool_name == "search_products":
            result = safe_tool_response(tool_name, learning_tracker, lambda: search_products(args.get("search_term") or raw_user_message, args.get("limit", 6)))
            learning_tracker["products"] = result if isinstance(result, list) else []
            return result
        if tool_name == "lookup_order":
            return safe_tool_response(tool_name, learning_tracker, lambda: lookup_order(args.get("order_number"), args.get("email")))
        if tool_name == "lookup_customer_orders":
            return safe_tool_response(tool_name, learning_tracker, lambda: lookup_customer_orders(args.get("email")))
        if tool_name == "get_order_tracking":
            return safe_tool_response(tool_name, learning_tracker, lambda: get_order_tracking(args.get("order_number"), args.get("email")))
        if tool_name == "query_knowledge":
            result = safe_tool_response(tool_name, learning_tracker, lambda: query_knowledge(args.get("query") or raw_user_message, args.get("limit", 3)))
            learning_tracker["knowledge_results"] = result.get("results", []) if isinstance(result, dict) else []
            return result
        if tool_name == "search_articles":
            result = safe_tool_response(tool_name, learning_tracker, lambda: search_articles(args.get("query") or raw_user_message, args.get("limit", 3)))
            learning_tracker["knowledge_results"] = result if isinstance(result, list) else []
            return result
        if tool_name == "get_policy_info":
            return safe_tool_response(tool_name, learning_tracker, lambda: get_policy_info(args.get("topic", "general")))
        if tool_name == "create_support_case":
            intent = detect_customer_intent(raw_user_message)
            result = maybe_create_support_case(conversation_id, args.get("issue_type") or escalation_type(intent) or "general_support", raw_user_message, intent, page_context, args.get("priority", "normal"))
            learning_tracker["support_case"] = result
            return result
        return {"error": f"Unknown tool {tool_name}"}
    return tool_executor

def direct_chatwoot_request(method, url, **kwargs):
    session = requests.Session()
    session.trust_env = False
    try:
        return session.request(method, url, **kwargs)
    finally:
        session.close()


def send_chatwoot_reply(conversation_id, message):
    if SAFE_TEST_MODE or not ENABLE_CHATWOOT_SEND:
        print("DRY RUN Chatwoot reply:", conversation_id, message[:500])
        return {"dry_run": True, "conversation_id": conversation_id, "message": message}
    url = f"{CHATWOOT_BASE_URL.rstrip('/')}/api/v1/accounts/{CHATWOOT_ACCOUNT_ID}/conversations/{conversation_id}/messages"
    response = direct_chatwoot_request("POST", url, headers={"api_access_token": CHATWOOT_API_TOKEN, "Content-Type": "application/json"}, json={"content": message, "message_type": "outgoing", "private": False}, timeout=25)
    response.raise_for_status()
    return response.json()

def build_safe_fallback(raw_user_message):
    intent = detect_customer_intent(raw_user_message)
    return TEAM_FOLLOWUP_MESSAGE if escalation_type(intent) else "I don't want to guess on that. Send the product name, project size, or order number if you have it, and I can narrow this down for Resin Society."

def should_escalate_answer(answer, status, intent_data, learning_tracker):
    if status == "waiting" or escalation_type(intent_data):
        return True
    text = (answer or "").lower()
    uncertainty_phrases = ["i don't want to guess", "team review", "follow up", "not sure", "can't confirm", "cannot confirm"]
    return bool(learning_tracker.get("catalog_error")) or any(phrase in text for phrase in uncertainty_phrases)

def schedule_logging(conversation_id, message, answer, intent_data, page_context, learning_tracker, lead):
    def run():
        try:
            log_conversation_turn(str(conversation_id), message, answer, intent_data, page_context, learning_tracker.get("tools_called", []), learning_tracker.get("products", []), learning_tracker.get("knowledge_results", []), learning_tracker.get("support_case"), {"resolved": False, "reason": "Resin AI chat"})
            if lead:
                log_lead(str(conversation_id), lead, message)
        except Exception as e:
            print("Resin logging failed:", e)
    BACKGROUND_EXECUTOR.submit(run)

def build_answer(message, conversation_id, page_context, memory_text, timing_metrics):
    intent_data = detect_customer_intent(message)
    learning_tracker = {"tools_called": [], "products": [], "knowledge_results": [], "support_case": None}
    lead = detect_lead(intent_data, message, page_context)
    issue = escalation_type(intent_data)
    if issue:
        learning_tracker["support_case"] = maybe_create_support_case(conversation_id, issue, message, intent_data, page_context, "high" if issue != "return_or_refund_request" else "normal")
    answer = try_fast_deterministic_answer(message, page_context, conversation_id, learning_tracker, timing_metrics)
    if not answer:
        tool_executor = make_tool_executor(conversation_id, message, page_context, learning_tracker)
        answer = timed_call(timing_metrics, "run_resin_agent", "ai_model", lambda: run_resin_agent(message, memory_text, page_context, tool_executor))
    if lead and not lead.get("email") and not is_resin_amount_question(message):
        answer += "\n\nFor a project quote, send your name, email, project size, timeline, and rough budget range."
    schedule_logging(conversation_id, message, answer, intent_data, page_context, learning_tracker, lead)
    return answer, intent_data, learning_tracker, lead

@app.get("/")
def home():
    return {"status": "Resin Society AI chat running", "safe_test_mode": SAFE_TEST_MODE, "chatwoot_send_enabled": ENABLE_CHATWOOT_SEND, "site_url": SITE_URL}

@app.post("/ai/ask")
async def ai_ask(request: Request):
    payload = await request.json()
    message = (payload.get("message") or payload.get("query") or "").strip()
    if not message:
        return {"ok": False, "answer": "Ask me about Resin Society products, projects, shipping, returns, or an order."}
    conversation_id = payload.get("conversation_id") or f"resin_embedded_{now_iso()}"
    page_context = build_api_page_context(payload)
    memory_text = build_memory_text(conversation_id) if payload.get("use_memory") else ""
    timing_metrics = new_timing_metrics()
    future = BACKGROUND_EXECUTOR.submit(build_answer, message, conversation_id, page_context, memory_text, timing_metrics)
    try:
        answer, intent_data, learning_tracker, lead = future.result(timeout=TARGET_RESPONSE_SECONDS)
        status = "answered"
    except TimeoutError:
        timing_metrics["timed_out"] = True
        timing_metrics["stage"] = "waiting"
        answer, intent_data, learning_tracker, lead = WAITING_MESSAGE, detect_customer_intent(message), {}, None
        status = "waiting"
    add_message(conversation_id, "user", message)
    add_message(conversation_id, "assistant", answer)
    metrics = log_chat_timing(conversation_id, "/ai/ask", timing_metrics)
    return {"ok": True, "conversation_id": conversation_id, "answer": answer, "status": status, "follow_up_required": should_escalate_answer(answer, status, intent_data, learning_tracker), "safe_test_mode": SAFE_TEST_MODE, "lead": lead, "products": learning_tracker.get("products", [])[:8], "tools_called": learning_tracker.get("tools_called", []), "performance": metrics}

class _PayloadRequest:
    def __init__(self, payload):
        self.payload = payload
    async def json(self):
        return self.payload

@app.post("/ai/search")
async def ai_search(request: Request):
    payload = await request.json()
    payload["message"] = payload.get("query") or payload.get("message") or ""
    return await ai_ask(_PayloadRequest(payload))

@app.post("/chatwoot/webhook")
async def chatwoot_webhook(request: Request):
    data = await request.json()
    if data.get("event") != "message_created" or data.get("message_type") != "incoming" or data.get("private") is True:
        return {"status": "ignored"}
    conversation = data.get("conversation") or {}
    if RESIN_CHATWOOT_INBOX_ID and str(conversation.get("inbox_id") or "") != str(RESIN_CHATWOOT_INBOX_ID):
        return {"status": "ignored_wrong_inbox"}
    conversation_id = conversation.get("id")
    message = (data.get("content") or "").strip()
    if not conversation_id or not message:
        return {"status": "ignored"}
    page_context = extract_frontend_context(data)
    memory_text = build_memory_text(conversation_id)
    timing_metrics = new_timing_metrics()
    future = BACKGROUND_EXECUTOR.submit(build_answer, message, conversation_id, page_context, memory_text, timing_metrics)
    try:
        answer, intent_data, learning_tracker, lead = future.result(timeout=TARGET_RESPONSE_SECONDS)
        send_chatwoot_reply(conversation_id, answer)
        add_message(conversation_id, "user", message)
        add_message(conversation_id, "assistant", answer)
        if not SAFE_TEST_MODE and ENABLE_CHATWOOT_SEND:
            maybe_auto_resolve_conversation(conversation_id, intent_data, answer)
        log_chat_timing(conversation_id, "/chatwoot/webhook", timing_metrics)
        return {"status": "replied", "stage": "final", "safe_test_mode": SAFE_TEST_MODE}
    except TimeoutError:
        timing_metrics["timed_out"] = True
        timing_metrics["stage"] = "waiting"
        send_chatwoot_reply(conversation_id, WAITING_MESSAGE)
        add_message(conversation_id, "assistant", WAITING_MESSAGE)
        log_chat_timing(conversation_id, "/chatwoot/webhook-waiting", timing_metrics)
        return {"status": "waiting", "stage": "checking", "safe_test_mode": SAFE_TEST_MODE}

@app.get("/reports/summary")
def reports_summary(days: int = 1):
    return build_summary_report(days=days)
