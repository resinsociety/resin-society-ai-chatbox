import os, json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from pathlib import Path

load_dotenv()
DATABASE_URL = os.getenv("RESIN_DATABASE_URL") or os.getenv("DATABASE_URL")
TABLE_PREFIX = os.getenv("RESIN_DB_TABLE_PREFIX", "resin")
CONVERSATION_TABLE = f"{TABLE_PREFIX}_conversation_logs"
LEAD_TABLE = f"{TABLE_PREFIX}_leads"
EVENT_TABLE = f"{TABLE_PREFIX}_learning_events"
LOCAL_LOG_DIR = Path(os.getenv("RESIN_LOCAL_LOG_DIR", "data"))


def now_iso():
    return datetime.now(timezone.utc).isoformat()




def append_local_log(kind, payload):
    LOCAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_LOG_DIR / f"{kind}.jsonl"
    record = {"created_at": now_iso(), **(payload or {})}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=True, default=str) + "\n")
    return {"logged": True, "local_file": str(path), "local_fallback": True}


def read_local_logs(kind, limit=25):
    path = LOCAL_LOG_DIR / f"{kind}.jsonl"
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows[-int(limit or 25):]

def get_connection():
    if not DATABASE_URL:
        raise Exception("RESIN_DATABASE_URL or DATABASE_URL missing")
    return psycopg2.connect(DATABASE_URL)


def init_learning_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {CONVERSATION_TABLE} (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT,
            created_at TEXT,
            user_message TEXT,
            assistant_reply TEXT,
            intent_json JSONB,
            page_context_json JSONB,
            tools_called_json JSONB,
            products_json JSONB,
            knowledge_json JSONB,
            support_case_json JSONB,
            auto_resolve_json JSONB,
            customer_email TEXT,
            order_number TEXT,
            issue_type TEXT,
            lead_type TEXT,
            unresolved_question TEXT,
            needs_review BOOLEAN DEFAULT FALSE,
            review_reason TEXT,
            rating TEXT,
            notes TEXT
        )
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {LEAD_TABLE} (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT,
            created_at TEXT,
            lead_type TEXT,
            name TEXT,
            email TEXT,
            project_type TEXT,
            project_size TEXT,
            timeline TEXT,
            budget_range TEXT,
            product_interest TEXT,
            custom_table_inquiry BOOLEAN DEFAULT FALSE,
            flooring_inquiry BOOLEAN DEFAULT FALSE,
            source_message TEXT,
            lead_json JSONB
        )
    """)
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {EVENT_TABLE} (
            id SERIAL PRIMARY KEY,
            conversation_id TEXT,
            created_at TEXT,
            event_type TEXT,
            event_json JSONB
        )
    """)
    conn.commit(); conn.close()


def detect_needs_review(user_message="", assistant_reply="", intent_data=None, tools_called=None):
    intent_data = intent_data or {}
    msg = (user_message or "").lower(); reply = (assistant_reply or "").lower()
    if any(x in msg for x in ["angry", "mad", "lawsuit", "chargeback", "refund", "damaged", "broken", "wrong item", "missing", "human", "person"]):
        return True, "High-risk customer issue"
    if any(intent_data.get(k) for k in ["requested_human", "damage_issue", "return_question", "bulk_or_commercial", "custom_table_lead", "flooring_contractor_lead", "unsure_risk"]):
        return True, "Escalation rule matched"
    if "don't want to guess" in reply or "team" in reply and "confirm" in reply:
        return True, "Unresolved or uncertain answer"
    return False, ""


def log_conversation_turn(conversation_id, user_message, assistant_reply, intent_data=None, page_context=None, tools_called=None, products=None, knowledge_results=None, support_case=None, auto_resolve=None):
    intent_data = intent_data or {}; page_context = page_context or {}; tools_called = tools_called or []; products = products or []; knowledge_results = knowledge_results or []
    needs_review, review_reason = detect_needs_review(user_message, assistant_reply, intent_data, tools_called)
    if not DATABASE_URL:
        payload = {"conversation_id": str(conversation_id), "user_message": user_message, "assistant_reply": assistant_reply, "intent_data": intent_data, "page_context": page_context, "tools_called": tools_called, "products": products, "knowledge_results": knowledge_results, "support_case": support_case, "auto_resolve": auto_resolve, "customer_email": intent_data.get("email", ""), "order_number": intent_data.get("order_number", ""), "issue_type": intent_data.get("question_type", ""), "needs_review": needs_review, "review_reason": review_reason}
        return append_local_log("conversation_logs", payload)
    init_learning_db()
    conn = get_connection(); cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {CONVERSATION_TABLE} (conversation_id, created_at, user_message, assistant_reply, intent_json, page_context_json, tools_called_json, products_json, knowledge_json, support_case_json, auto_resolve_json, customer_email, order_number, issue_type, lead_type, unresolved_question, needs_review, review_reason)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (str(conversation_id), now_iso(), user_message, assistant_reply, psycopg2.extras.Json(intent_data), psycopg2.extras.Json(page_context), psycopg2.extras.Json(tools_called), psycopg2.extras.Json(products), psycopg2.extras.Json(knowledge_results), psycopg2.extras.Json(support_case), psycopg2.extras.Json(auto_resolve), intent_data.get("email", ""), intent_data.get("order_number", ""), intent_data.get("question_type", ""), "custom_table" if intent_data.get("custom_table_lead") else "flooring_contractor" if intent_data.get("flooring_contractor_lead") else "bulk_commercial" if intent_data.get("bulk_or_commercial") else "", user_message if needs_review else "", needs_review, review_reason))
    log_id = cur.fetchone()[0]
    conn.commit(); conn.close()
    return {"logged": True, "log_id": log_id, "needs_review": needs_review, "review_reason": review_reason}


def log_lead(conversation_id, lead, source_message=""):
    lead = lead or {}
    if not DATABASE_URL:
        payload = {"conversation_id": str(conversation_id), "lead": lead, "source_message": source_message}
        return append_local_log("leads", payload)
    init_learning_db()
    conn = get_connection(); cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {LEAD_TABLE} (conversation_id, created_at, lead_type, name, email, project_type, project_size, timeline, budget_range, product_interest, custom_table_inquiry, flooring_inquiry, source_message, lead_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id
    """, (str(conversation_id), now_iso(), lead.get("lead_type", ""), lead.get("name", ""), lead.get("email", ""), lead.get("project_type", ""), lead.get("project_size", ""), lead.get("timeline", ""), lead.get("budget_range", ""), lead.get("product_interest", ""), bool(lead.get("custom_table_inquiry")), bool(lead.get("flooring_inquiry")), source_message, psycopg2.extras.Json(lead)))
    lead_id = cur.fetchone()[0]
    conn.commit(); conn.close()
    return {"logged": True, "lead_id": lead_id}


def get_recent_logs(limit=25):
    if not DATABASE_URL:
        return read_local_logs("conversation_logs", limit)
    init_learning_db(); conn = get_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(f"SELECT * FROM {CONVERSATION_TABLE} ORDER BY id DESC LIMIT %s", (limit,))
    rows = cur.fetchall(); conn.close(); return rows


def build_summary_report(days=1):
    if not DATABASE_URL:
        conversations = read_local_logs("conversation_logs", 10000)
        leads = read_local_logs("leads", 10000)
        needs_review = [r for r in conversations if r.get("needs_review")]
        return {"days": days, "local_fallback": True, "totals": {"conversations": len(conversations), "needs_review": len(needs_review)}, "leads": leads[-25:], "unresolved_questions": [{"user_message": r.get("user_message"), "review_reason": r.get("review_reason")} for r in needs_review[-25:]], "gap_note": "Using local JSONL logs until RESIN_DATABASE_URL is configured."}
    init_learning_db(); conn = get_connection(); cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    since = (datetime.now(timezone.utc) - timedelta(days=int(days or 1))).isoformat()
    cur.execute(f"SELECT COUNT(*) AS conversations, COUNT(*) FILTER (WHERE needs_review) AS needs_review FROM {CONVERSATION_TABLE} WHERE created_at >= %s", (since,))
    totals = dict(cur.fetchone())
    cur.execute(f"SELECT lead_type, COUNT(*) AS count FROM {LEAD_TABLE} WHERE created_at >= %s GROUP BY lead_type ORDER BY count DESC", (since,))
    leads = [dict(r) for r in cur.fetchall()]
    cur.execute(f"SELECT user_message, review_reason FROM {CONVERSATION_TABLE} WHERE created_at >= %s AND needs_review ORDER BY id DESC LIMIT 25", (since,))
    unresolved = [dict(r) for r in cur.fetchall()]
    cur.execute(f"SELECT products_json FROM {CONVERSATION_TABLE} WHERE created_at >= %s", (since,))
    asked = {}
    for row in cur.fetchall():
        for p in row.get("products_json") or []:
            title = p.get("title") if isinstance(p, dict) else None
            if title:
                asked[title] = asked.get(title, 0) + 1
    conn.close()
    return {"days": days, "since": since, "totals": totals, "leads": leads, "unresolved_questions": unresolved, "recommended_products": sorted(asked.items(), key=lambda x: x[1], reverse=True)[:20], "gap_note": "Review unresolved questions for products people ask for but Resin Society does not yet carry."}
