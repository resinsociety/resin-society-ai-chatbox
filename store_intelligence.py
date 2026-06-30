import time, json, re, threading
from shopify_tools import shopify_graphql

SITE_URL = "https://resinsociety.net"
CATALOG_CACHE = {"loaded_at": 0, "products": []}
CACHE_TTL_SECONDS = 900
QUERY_RESULT_CACHE = {}
QUERY_RESULT_CACHE_TTL_SECONDS = 300
PRELOAD_QUERIES = ["epoxy resin", "deep pour epoxy", "tabletop epoxy", "river table resin", "resin pigments", "mica powder", "resin molds", "sanding polishing", "floor epoxy", "woodworking tools"]
QUERY_STOPWORDS = {"about", "also", "and", "any", "are", "available", "best", "can", "could", "for", "from", "good", "have", "in", "is", "need", "now", "product", "products", "that", "the", "this", "what", "with", "you", "your", "resin", "society"}
NEED_CATEGORY_RULES = {
    "deep pour epoxy": ["deep pour", "casting", "thick pour", "river table", "slab"],
    "tabletop epoxy": ["tabletop", "table top", "bar top", "countertop", "coating"],
    "river table": ["river table", "live edge", "slab", "deep pour"],
    "floor epoxy": ["floor", "flooring", "garage", "metallic", "contractor"],
    "pigments": ["pigment", "mica", "powder", "color", "dye", "metallic"],
    "molds": ["mold", "mould", "coaster", "tray", "jewelry", "silicone"],
    "sanding polishing": ["sand", "sanding", "polish", "polishing", "buff", "finish"],
    "woodworking tools": ["wood", "slab", "router", "saw", "clamp", "tool"],
    "resin supplies": ["resin", "epoxy", "cup", "mix", "glove", "torch", "supplies", "kit"],
}


def normalize_text(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value or "").lower().strip()


def tokenize_query_terms(value):
    return [term for term in re.split(r"\W+", normalize_text(value)) if len(term) > 2 and term not in QUERY_STOPWORDS]


def safe_float(value, default=0.0):
    try:
        return float(value) if value not in [None, ""] else default
    except Exception:
        return default


def detect_catalog_intent(user_query):
    q = normalize_text(user_query)
    need = None
    for key, terms in NEED_CATEGORY_RULES.items():
        if key in q or any(term in q for term in terms):
            need = key
            break
    intent_type = "general"
    max_price = None
    if any(x in q for x in ["cheapest", "lowest price", "least expensive", "affordable"]):
        intent_type = "cheapest"
    m = re.search(r"under\s*\$?\s*(\d+)", q)
    if m:
        intent_type = "under_price"; max_price = float(m.group(1))
    if any(x in q for x in ["pair with", "go with", "also need", "complement"]):
        intent_type = "complementary"
    return {"type": intent_type, "need": need, "max_price": max_price, "terms": tokenize_query_terms(user_query)}


def product_text(product):
    parts = [product.get("title"), product.get("vendor"), product.get("product_type"), " ".join(product.get("tags") or []), product.get("description"), product.get("seo_title"), product.get("seo_description")]
    for mf in product.get("metafields") or []:
        parts += [mf.get("namespace"), mf.get("key"), mf.get("value")]
    return normalize_text(" ".join(str(x or "") for x in parts))


def format_product_for_agent(product):
    return {
        "id": product.get("id"), "title": product.get("title"), "handle": product.get("handle"), "vendor": product.get("vendor"), "product_type": product.get("product_type"), "tags": product.get("tags", []), "status": product.get("status"), "url": product.get("url") or (f"{SITE_URL}/products/{product.get('handle')}" if product.get("handle") else ""), "description": product.get("description"), "short_description": product.get("description"), "price": safe_float(product.get("price")), "currency": product.get("currency") or "USD", "image": product.get("image"), "variants": product.get("variants", []), "metafields": product.get("metafields", []),
    }


def fetch_catalog_from_shopify(limit=250):
    query = """
    query Products($first: Int!) {
      products(first: $first, query: "status:active") {
        edges { node { id title handle vendor productType tags status onlineStoreUrl descriptionPlainSummary: description(truncateAt: 800) seo { title description } priceRangeV2 { minVariantPrice { amount currencyCode } } featuredImage { url } variants(first: 50) { edges { node { title availableForSale price inventoryQuantity } } } metafields(first: 50) { edges { node { namespace key type value } } } } }
      }
    }
    """
    data = shopify_graphql(query, {"first": limit})
    products = []
    for edge in data.get("products", {}).get("edges", []):
        p = edge.get("node") or {}
        products.append({
            "id": p.get("id"), "title": p.get("title"), "handle": p.get("handle"), "vendor": p.get("vendor"), "product_type": p.get("productType"), "tags": p.get("tags", []), "status": p.get("status"), "url": p.get("onlineStoreUrl") or f"{SITE_URL}/products/{p.get('handle')}", "description": p.get("descriptionPlainSummary"), "seo_title": (p.get("seo") or {}).get("title"), "seo_description": (p.get("seo") or {}).get("description"), "price": ((p.get("priceRangeV2") or {}).get("minVariantPrice") or {}).get("amount"), "currency": ((p.get("priceRangeV2") or {}).get("minVariantPrice") or {}).get("currencyCode"), "image": (p.get("featuredImage") or {}).get("url"), "variants": [{"title": v["node"].get("title"), "available": v["node"].get("availableForSale"), "price": v["node"].get("price"), "inventory": v["node"].get("inventoryQuantity")} for v in (p.get("variants") or {}).get("edges", [])], "metafields": [{"namespace": m["node"].get("namespace"), "key": m["node"].get("key"), "type": m["node"].get("type"), "value": m["node"].get("value")} for m in (p.get("metafields") or {}).get("edges", [])],
        })
    return products


def get_catalog_snapshot(force_refresh=False):
    age = time.time() - CATALOG_CACHE["loaded_at"] if CATALOG_CACHE["loaded_at"] else 999999
    if not force_refresh and CATALOG_CACHE["products"] and age < CACHE_TTL_SECONDS:
        return CATALOG_CACHE["products"]
    products = fetch_catalog_from_shopify()
    CATALOG_CACHE["products"] = products
    CATALOG_CACHE["loaded_at"] = time.time()
    return products


def get_catalog_cache_status():
    age = time.time() - CATALOG_CACHE["loaded_at"] if CATALOG_CACHE["loaded_at"] else None
    return {"loaded": bool(CATALOG_CACHE["products"]), "product_count": len(CATALOG_CACHE["products"]), "loaded_at": CATALOG_CACHE["loaded_at"], "age_seconds": round(age, 2) if age is not None else None, "ttl_seconds": CACHE_TTL_SECONDS, "query_cache_entries": len(QUERY_RESULT_CACHE)}


def _query_cache_key(user_query, page_context, limit):
    return json.dumps({"query": normalize_text(user_query), "context": page_context or {}, "limit": int(limit or 6)}, sort_keys=True)


def _get_cached_query_result(cache_key):
    entry = QUERY_RESULT_CACHE.get(cache_key)
    if not entry or time.time() - entry["stored_at"] > QUERY_RESULT_CACHE_TTL_SECONDS:
        QUERY_RESULT_CACHE.pop(cache_key, None)
        return None
    result = dict(entry["result"]); result["cache_hit"] = True; return result


def _store_cached_query_result(cache_key, result):
    cached = dict(result or {}); cached["cache_hit"] = False
    QUERY_RESULT_CACHE[cache_key] = {"stored_at": time.time(), "result": cached}


def score_product(product, intent):
    text = product_text(product)
    score = 0
    for term in intent.get("terms") or []:
        if term in normalize_text(product.get("title")):
            score += 10
        if term in text:
            score += 3
    need = intent.get("need")
    if need:
        terms = NEED_CATEGORY_RULES.get(need, [])
        if need in text or any(t in text for t in terms):
            score += 25
        else:
            score -= 8
    if intent.get("max_price") is not None and safe_float(product.get("price")) <= intent["max_price"]:
        score += 12
    return score


def query_catalog(user_query, page_context=None, limit=6):
    page_context = page_context or {}
    cache_key = _query_cache_key(user_query, page_context, limit)
    cached = _get_cached_query_result(cache_key)
    if cached is not None:
        return cached
    products = get_catalog_snapshot()
    intent = detect_catalog_intent(user_query)
    ranked = []
    for p in products:
        s = score_product(p, intent)
        if s > 0:
            ranked.append((s, p))
    ranked.sort(key=lambda x: (x[0], -safe_float(x[1].get("price")) if intent.get("type") == "cheapest" else x[0]), reverse=True)
    if intent.get("type") == "cheapest":
        ranked.sort(key=lambda x: safe_float(x[1].get("price"), 999999))
    results = [p for _, p in ranked[: int(limit or 6)]]
    result = {"query": user_query, "intent": intent, "count": len(results), "total_catalog_products": len(products), "products": [format_product_for_agent(p) for p in results], "cache_hit": False, "instruction": "Use this Resin Society catalog data as source of truth. Do not invent product facts."}
    _store_cached_query_result(cache_key, result)
    return result


def get_complementary_products(product_handle=None, user_query="", page_context=None, limit=6):
    base_terms = user_query or "resin supplies pigments sanding polishing"
    return query_catalog(base_terms, page_context=page_context or {}, limit=limit)


def preload_store_cache(force_refresh=False):
    def _preload():
        try:
            products = get_catalog_snapshot(force_refresh=force_refresh)
            for q in PRELOAD_QUERIES:
                try:
                    query_catalog(q, {}, 6)
                except Exception as e:
                    print("Catalog query preload failed:", q, e)
            print("Resin store cache preloaded:", len(products), "products")
        except Exception as e:
            print("Resin store cache preload failed:", e)
    threading.Thread(target=_preload, daemon=True).start()
    return {"started": True, "status": get_catalog_cache_status()}
