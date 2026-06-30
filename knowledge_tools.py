import re
from blog_tools import search_articles
from policy_tools import get_policy_info


def normalize_text(value):
    return str(value or "").lower().strip()


def relevance_score(query, item):
    q = normalize_text(query)
    haystack = normalize_text(" ".join(str(item.get(k) or "") for k in ["title", "summary", "description", "url"]))
    score = 0
    for term in [t for t in re.split(r"\W+", q) if len(t) > 2]:
        if term in haystack:
            score += 4
    for phrase in ["river table", "deep pour", "tabletop epoxy", "resin floor", "mica powder", "pigment", "mold", "sanding", "polishing"]:
        if phrase in q and phrase in haystack:
            score += 20
    return score


def topic_aliases(query):
    q = normalize_text(query)
    aliases = [query]
    if "river" in q:
        aliases += ["river table epoxy", "deep pour river table"]
    if "tabletop" in q or "counter" in q:
        aliases += ["tabletop epoxy", "epoxy countertop"]
    if "floor" in q:
        aliases += ["epoxy flooring", "garage floor epoxy"]
    if "pigment" in q or "mica" in q:
        aliases += ["resin pigments", "mica powder resin"]
    if "mold" in q or "coaster" in q:
        aliases += ["resin molds", "resin coaster molds"]
    if "sand" in q or "polish" in q:
        aliases += ["sanding polishing resin", "finish epoxy resin"]
    return list(dict.fromkeys(aliases))


def search_blog_knowledge(query, limit=3):
    all_articles = []
    for alias in topic_aliases(query):
        try:
            for article in search_articles(alias, limit=limit) or []:
                article["source_type"] = "blog"
                article["score"] = relevance_score(query, article)
                all_articles.append(article)
        except Exception as e:
            print("search_blog_knowledge failed:", alias, e)
    deduped = {}
    for article in all_articles:
        key = article.get("url") or article.get("handle") or article.get("title")
        if key and (key not in deduped or article.get("score", 0) > deduped[key].get("score", 0)):
            deduped[key] = article
    return sorted(deduped.values(), key=lambda x: x.get("score", 0), reverse=True)[:limit]


def search_policy_knowledge(query):
    q = normalize_text(query)
    topic = None
    if any(x in q for x in ["ship", "shipping", "delivery", "arrive"]): topic = "shipping"
    elif any(x in q for x in ["return", "refund", "exchange"]): topic = "returns"
    elif any(x in q for x in ["order", "tracking", "where is"]): topic = "orders"
    elif any(x in q for x in ["contact", "email", "support"]): topic = "contact"
    elif any(x in q for x in ["custom table", "commission"]): topic = "custom"
    elif any(x in q for x in ["floor", "contractor"]): topic = "flooring"
    if not topic:
        return []
    policy = get_policy_info(topic=topic)
    return [{"source_type": "policy", "title": link.get("label") or topic.title(), "url": link.get("url"), "summary": policy.get("answer_preview") or "", "score": 25} for link in policy.get("required_links", []) if link.get("url")]


def query_knowledge(query, limit=3):
    combined = search_blog_knowledge(query, limit=limit) + search_policy_knowledge(query)
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    direct = [x for x in combined if x.get("score", 0) >= 10]
    return {"query": query, "count": len(direct[:limit]), "results": direct[:limit], "all_results_count": len(combined), "instruction": "Use Resin Society knowledge only when directly relevant. Do not force weak links."}
