import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
MODEL = os.getenv("OPENAI_AGENT_MODEL", "gpt-4.1-mini")
MAX_TOOL_ROUNDS = 6
_client = None

SYSTEM_PROMPT = """
You are Resin Society Concierge, the AI shopping, project, order, and support assistant for Resin Society.

You help makers, artists, woodworkers, suppliers, contractors, and DIY customers choose resin/epoxy products and plan projects.
Be warm, practical, concise, and careful. Usually answer in 2-6 short sentences.

Truth rules:
- Never invent product facts, prices, inventory, URLs, shipping times, return eligibility, order status, safety claims, cure times, mix ratios, or coverage.
- Use tools for product, catalog, blog, policy, order, and support facts.
- If a project depends on exact dimensions, ask for length, width, depth, substrate, and use case.
- If a customer asks about food safety, SDS, heat resistance, floor coating suitability, or structural use and the data is not available, escalate or say the team should confirm.

Product/catalog questions:
Use query_catalog or search_products for epoxy, resin, deep pour, tabletop epoxy, river tables, flooring, pigments, mica powders, molds, sanding, polishing, woodworking tools, and project supplies.
Every product recommendation should include product name, price when available, a short reason, and URL when available.

Project sizing:
For rectangular pours, explain length x width x depth and cubic inches / 231 = gallons. For irregular river channels, ask for average channel width, length, and depth, and suggest a safety margin.

Order support:
Use order tools when order number or checkout email is available. Ask for both when missing. Do not guess order status.

Escalate or create a support case for angry/frustrated customers, refunds/returns, damaged or missing orders, bulk/commercial quotes, custom table leads, flooring contractor leads, and anything uncertain or safety-sensitive.

Lead capture:
When relevant, collect name, email, project type, project size, timeline, budget range, product interest, and whether it is custom table or flooring/contractor work.

Never mention internal tools. Never say "the tool says" or "I searched".
"""

TOOLS = [
    {"type": "function", "function": {"name": "query_catalog", "description": "Search Resin Society catalog with rich product data.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 6}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_products", "description": "Search Shopify products.", "parameters": {"type": "object", "properties": {"search_term": {"type": "string"}, "limit": {"type": "integer", "default": 6}}, "required": ["search_term"]}}},
    {"type": "function", "function": {"name": "lookup_order", "description": "Look up a Shopify order by order number and optional email.", "parameters": {"type": "object", "properties": {"order_number": {"type": "string"}, "email": {"type": "string"}}, "required": ["order_number"]}}},
    {"type": "function", "function": {"name": "lookup_customer_orders", "description": "Look up recent orders by customer email.", "parameters": {"type": "object", "properties": {"email": {"type": "string"}}, "required": ["email"]}}},
    {"type": "function", "function": {"name": "get_order_tracking", "description": "Get order tracking when available.", "parameters": {"type": "object", "properties": {"order_number": {"type": "string"}, "email": {"type": "string"}}, "required": ["order_number"]}}},
    {"type": "function", "function": {"name": "query_knowledge", "description": "Search Resin Society blog/policy knowledge.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 3}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "search_articles", "description": "Search Shopify articles/blog posts.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 3}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_policy_info", "description": "Get Resin Society policy/contact/shipping/return guidance.", "parameters": {"type": "object", "properties": {"topic": {"type": "string", "enum": ["shipping", "returns", "orders", "contact", "trust", "custom", "flooring", "general"]}}, "required": ["topic"]}}},
    {"type": "function", "function": {"name": "create_support_case", "description": "Escalate a conversation for human review.", "parameters": {"type": "object", "properties": {"issue_type": {"type": "string"}, "priority": {"type": "string", "enum": ["normal", "high", "urgent"]}}, "required": ["issue_type"]}}},
]


def _fallback(user_message):
    msg = (user_message or "").lower()
    if any(x in msg for x in ["how much", "calculator", "gallon", "resin do i need"]):
        return "I can help estimate that. Send the length, width, and pour depth. For a rectangle, length x width x depth gives cubic inches, and cubic inches divided by 231 gives gallons."
    if any(x in msg for x in ["order", "tracking", "shipped"]):
        return "Please send your order number and checkout email so I can check the order without guessing."
    return "I can help with Resin Society products, project sizing, shipping, returns, order status, or custom project leads. What are you working on?"


def get_openai_client():
    global _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    if _client is None:
        _client = OpenAI(api_key=api_key)
    return _client


def run_resin_agent(user_message, memory_text="", page_context=None, tool_executor=None):
    client = get_openai_client()
    if not client:
        return _fallback(user_message)

    page_context = page_context or {}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.strip()},
        {"role": "user", "content": json.dumps({"newest_message": user_message, "recent_memory": memory_text[-1500:] if memory_text else "", "page_context": page_context})},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(model=MODEL, temperature=0.2, messages=messages, tools=TOOLS, tool_choice="auto")
        except Exception as e:
            print("OpenAI agent failed:", type(e).__name__, str(e)[:500])
            return _fallback(user_message)
        message = response.choices[0].message
        messages.append(message)
        if not message.tool_calls:
            return message.content or _fallback(user_message)
        for call in message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = tool_executor(call.function.name, args) if tool_executor else {"error": "tool executor unavailable"}
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)[:12000]})

    return "I want the Resin Society team to confirm this rather than risk guessing."
