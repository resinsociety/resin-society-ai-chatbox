DEFAULT_ROUTER_RESULT = {"intent": "general_question", "product_category": None, "topic_shift": True, "use_memory": False, "use_page_context": False, "confidence": 0.7}


def ai_route_message(raw_message: str, memory_text: str = "", page_context: dict | None = None):
    msg = (raw_message or "").lower()
    result = DEFAULT_ROUTER_RESULT.copy()
    if any(x in msg for x in ["order", "tracking", "shipped", "delivered"]):
        result["intent"] = "order_question"
    elif any(x in msg for x in ["return", "refund", "exchange", "cancel"]):
        result["intent"] = "return_question"
    elif any(x in msg for x in ["shipping", "delivery", "arrive"]):
        result["intent"] = "shipping_question"
    elif any(x in msg for x in ["custom table", "contractor", "floor", "bulk", "commercial", "quote"]):
        result["intent"] = "lead"
    elif any(x in msg for x in ["epoxy", "resin", "pigment", "mica", "mold", "river table", "tabletop", "deep pour", "sanding", "polishing"]):
        result["intent"] = "product_recommendation"
    if "river table" in msg:
        result["product_category"] = "river table"
    elif "deep pour" in msg:
        result["product_category"] = "deep pour epoxy"
    elif "table" in msg or "counter" in msg:
        result["product_category"] = "tabletop epoxy"
    elif "floor" in msg:
        result["product_category"] = "floor epoxy"
    elif "pigment" in msg or "mica" in msg:
        result["product_category"] = "pigments"
    return result
