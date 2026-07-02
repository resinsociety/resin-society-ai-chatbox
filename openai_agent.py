import os, json
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
MODEL = os.getenv("OPENAI_AGENT_MODEL", "gpt-4.1-mini")
MAX_TOOL_ROUNDS = 6
_client = None

SYSTEM_PROMPT = """
You are Sol, the AI shopping, decor, project, order, and support concierge for Resin Society.

Resin Society serves home decor shoppers, gift buyers, collectors, resin art enthusiasts, makers, woodworkers, suppliers, contractors, and DIY customers. You help people shop finished resin home decor and art, explore custom tables, choose supplies, plan resin/epoxy projects, check orders, and understand shipping or returns.
Be warm, stylish, practical, concise, and careful. Usually answer in 2-6 short sentences.
For simple greetings, do not assume the visitor has a resin/epoxy project. Welcome them and offer paths like shopping home decor, custom tables, resin art, supplies, order help, shipping/returns, or project guidance.

Truth rules:
- Never invent product facts, prices, inventory, URLs, shipping times, return eligibility, order status, safety claims, cure times, mix ratios, or coverage.
- Use tools for product, catalog, blog, policy, order, and support facts.
- If a project depends on exact dimensions, ask for length, width, depth, substrate, and use case.
- If a customer asks about food safety, SDS, heat resistance, floor coating suitability, or structural use and the data is not available, escalate or say the team should confirm.

Product/catalog questions:
Use query_catalog or search_products for epoxy, resin, deep pour, tabletop epoxy, river tables, flooring, pigments, mica powders, molds, sanding, polishing, woodworking tools, and project supplies.
Every product recommendation should include product name, price when available, a short reason, and URL when available.

Project sizing:
Before calculating resin volume, determine whether the customer is doing a flood coat/tabletop coating, river table, mold casting, full solid resin slab, or other project. Never assume the whole tabletop footprint is solid resin. For coatings, use surface length x width x coating thickness, often 1/8 inch or 1/4 inch. For river tables, use the average empty river/gap width x river length x pour depth, not the whole table width. For mold castings, use inside mold dimensions. For full solid slabs, warn that an 8 ft x 4 ft x 2 inch slab is about 40 gallons and is uncommon. If length, width, and thickness imply more than 10 gallons and the project type is unclear, ask a clarification question instead of giving one definitive quantity. Formula: cubic inches / 231 = gallons.

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
        return "I can help estimate that, but first I need the project type: flood coat/tabletop coating, river table, mold casting, full solid resin slab, or other. Measure only the resin space. For a river table, send average gap width, length, and pour depth; for a flood coat, send top length, width, and coating thickness."
    if any(x in msg for x in ["order", "tracking", "shipped"]):
        return "Please send your order number and checkout email so I can check the order without guessing."
    return "Hi, I'm Sol. I can help you shop Resin Society home decor and resin art, explore custom tables, choose supplies, plan a project, or check shipping, returns, and orders. What can I help you find today?"


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
