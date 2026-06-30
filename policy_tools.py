"""Resin Society policy + page truth layer."""

SITE_URL = "https://resinsociety.net"
SUPPORT_EMAIL = "hello@resinsociety.net"
URLS = {
    "home": SITE_URL,
    "contact": f"{SITE_URL}/pages/contact",
    "privacy": f"{SITE_URL}/policies/privacy-policy",
    "terms": f"{SITE_URL}/policies/terms-of-service",
    "refund": f"{SITE_URL}/policies/refund-policy",
    "shipping_policy": f"{SITE_URL}/policies/shipping-policy",
    "blog": f"{SITE_URL}/blogs/news",
}

POLICIES = {
    "returns": {
        "title": "Resin Society Returns & Refunds",
        "primary_url": URLS["refund"],
        "answer_preview": "Returns, refunds, exchanges, damaged orders, and eligibility should be checked against Resin Society's current policy and the specific supplier/product rules. Do not send items back until Resin Society confirms instructions. For refund, return, damaged, missing, or wrong-item issues, collect order number, checkout email, and photos when relevant, then escalate to the team.",
        "required_links": [{"label": "Refund policy", "url": URLS["refund"]}, {"label": "Contact", "url": URLS["contact"]}],
    },
    "shipping": {
        "title": "Resin Society Shipping",
        "primary_url": URLS["shipping_policy"],
        "answer_preview": "Shipping can vary by product, supplier, artist partner, or fulfillment location. For a product-specific answer, check the product record or send the product name. For order status, provide the order number and checkout email.",
        "required_links": [{"label": "Shipping policy", "url": URLS["shipping_policy"]}],
    },
    "orders": {
        "title": "Resin Society Order Help",
        "primary_url": URLS["contact"],
        "answer_preview": "For order help, Resin Society needs the order number and checkout email. The assistant should use Shopify order tools when available and avoid guessing status or delivery dates.",
        "required_links": [{"label": "Contact", "url": URLS["contact"]}],
    },
    "contact": {
        "title": "Contact Resin Society",
        "primary_url": URLS["contact"],
        "answer_preview": f"Customers can contact Resin Society at {SUPPORT_EMAIL} or through the contact page.",
        "required_links": [{"label": "Contact", "url": URLS["contact"]}],
    },
    "custom": {
        "title": "Custom Table Inquiries",
        "primary_url": URLS["contact"],
        "answer_preview": "For custom tables, collect name, email, project size, wood/slab details, timeline, location if relevant, and budget range. Escalate as a custom table lead.",
        "required_links": [{"label": "Contact", "url": URLS["contact"]}],
    },
    "flooring": {
        "title": "Flooring and Contractor Inquiries",
        "primary_url": URLS["contact"],
        "answer_preview": "For flooring or contractor questions, collect name, email, square footage, substrate, project location, timeline, product interest, and whether this is residential or commercial. Escalate for human review.",
        "required_links": [{"label": "Contact", "url": URLS["contact"]}],
    },
    "trust": {
        "title": "About Resin Society",
        "primary_url": URLS["home"],
        "answer_preview": "Resin Society helps makers, woodworkers, artists, and contractors find resin, epoxy, pigments, tools, supplies, partner products, and project guidance.",
        "required_links": [{"label": "Resin Society", "url": URLS["home"]}],
    },
    "general": {
        "title": "Resin Society Help",
        "primary_url": URLS["contact"],
        "answer_preview": "Resin Society can help with epoxy/resin recommendations, river tables, tabletop epoxy, deep pour epoxy, flooring, pigments, molds, sanding/polishing, order status, shipping, returns, and custom project inquiries.",
        "required_links": [{"label": "Contact", "url": URLS["contact"]}],
    },
}

ALIASES = {"return": "returns", "refund": "returns", "exchange": "returns", "ship": "shipping", "delivery": "shipping", "tracking": "orders", "order": "orders", "custom table": "custom", "floor": "flooring", "contractor": "flooring"}


def get_policy_info(topic="general", page_context=None):
    key = (topic or "general").lower().strip()
    key = ALIASES.get(key, key)
    return POLICIES.get(key, POLICIES["general"])
