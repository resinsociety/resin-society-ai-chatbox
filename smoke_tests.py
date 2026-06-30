import asyncio
import os

os.environ["RESIN_SAFE_TEST_MODE"] = "true"
os.environ["RESIN_ENABLE_CHATWOOT_SEND"] = "false"
os.environ["OPENAI_API_KEY"] = ""

import app

# Avoid requiring a database during smoke tests.
app.log_conversation_turn = lambda *a, **k: {"logged": True, "smoke": True}
app.log_lead = lambda *a, **k: {"logged": True, "smoke": True}
app.query_catalog = lambda user_query, page_context=None, limit=6: {"products": [{"title": "Sample Deep Pour Epoxy", "price": 129, "description": "Good fit for river table pours", "url": "https://resinsociety.net/products/sample-deep-pour-epoxy"}], "count": 1}

class Request:
    def __init__(self, payload):
        self.payload = payload
    async def json(self):
        return self.payload

async def run():
    cases = [
        {"message": "How much resin do I need for a river table?"},
        {"message": "Where is my order?"},
        {"message": "I need a custom table quote for a 8 x 3 ft dining table, budget around $3000", "customer_email": "maker@example.com"},
        {"message": "My order arrived damaged and leaking"},
    ]
    for payload in cases:
        result = await app.ai_ask(Request(payload))
        print("---")
        print(payload["message"])
        print(result["status"], "safe_test_mode=", result["safe_test_mode"], "follow_up=", result["follow_up_required"])
        print(result["answer"][:500])
        if result.get("lead"):
            print("lead=", result["lead"])

asyncio.run(run())

