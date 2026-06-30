import re


def extract_product_handle_from_message(message):
    match = re.search(r"https?://(?:www\.)?resinsociety\.net/products/([^\s/?#]+)", message or "")
    return match.group(1) if match else None


def extract_email(message):
    match = re.search(r"[\w.\-+]+@[\w.\-]+\.\w+", message or "")
    return match.group(0).lower() if match else None


def extract_order_number(message):
    match = re.search(r"(?:order\s*)?#?\s*(\d{4,})", message or "", re.I)
    return match.group(1) if match else None


def detect_question_type(message):
    msg = (message or "").lower()
    if any(x in msg for x in ["return", "refund", "exchange", "cancel"]):
        return "return_question"
    if any(x in msg for x in ["order", "tracking", "where is", "shipped", "delivered"]):
        return "order_question"
    if any(x in msg for x in ["shipping", "ship", "delivery", "arrive"]):
        return "shipping_question"
    if any(x in msg for x in ["custom table", "flooring", "contractor", "bulk", "commercial", "quote"]):
        return "lead"
    if any(x in msg for x in ["epoxy", "resin", "pigment", "mica", "mold", "river table", "tabletop", "deep pour", "sanding", "polishing", "how much"]):
        return "product_recommendation"
    return "general_question"


def detect_customer_intent(message):
    msg = (message or "").lower()
    return {
        "question_type": detect_question_type(message),
        "email": extract_email(message),
        "order_number": extract_order_number(message),
        "product_handle": extract_product_handle_from_message(message),
        "requested_human": any(x in msg for x in ["human", "person", "call me", "angry", "frustrated"]),
        "damage_issue": any(x in msg for x in ["damaged", "broken", "missing", "wrong item", "not received", "never arrived"]),
        "return_question": any(x in msg for x in ["return", "refund", "exchange", "cancel"]),
        "order_question": any(x in msg for x in ["order", "tracking", "where is", "shipped", "delivered"]),
    }
