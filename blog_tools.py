import os, requests

# The desktop environment can inject a dead local proxy. The chat service must call
# Chatwoot, Shopify, and OpenAI directly so customer replies do not get stuck.
for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_key, None)
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")
from dotenv import load_dotenv

load_dotenv()
SHOPIFY_STORE_DOMAIN = os.getenv("SHOPIFY_STORE_DOMAIN") or os.getenv("RESIN_SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_ACCESS_TOKEN = os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN") or os.getenv("RESIN_SHOPIFY_ADMIN_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01")
SITE_URL = "https://resinsociety.net"


def shopify_graphql(query: str, variables: dict | None = None):
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"
    response = requests.post(url, headers={"X-Shopify-Access-Token": SHOPIFY_ADMIN_ACCESS_TOKEN, "Content-Type": "application/json"}, json={"query": query, "variables": variables or {}}, timeout=30)
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        print("Shopify article GraphQL errors:", data["errors"])
        return None
    return data.get("data")


def make_article_url(blog_handle, article_handle):
    return f"{SITE_URL}/blogs/{blog_handle}/{article_handle}" if blog_handle and article_handle else None


def search_articles(search_term: str, limit: int = 5):
    query = """
    query SearchArticles($query: String!, $first: Int!) {
      articles(first: $first, query: $query) {
        edges { node { id title handle summary publishedAt blog { title handle } } }
      }
    }
    """
    try:
        data = shopify_graphql(query, {"query": search_term, "first": limit})
        if not data:
            return []
        articles = []
        for edge in data.get("articles", {}).get("edges", []):
            a = edge["node"]; blog = a.get("blog") or {}
            articles.append({"title": a.get("title"), "summary": a.get("summary") or "", "url": make_article_url(blog.get("handle"), a.get("handle")), "blog": blog.get("title"), "blog_handle": blog.get("handle"), "handle": a.get("handle"), "published_at": a.get("publishedAt")})
        return articles
    except Exception as e:
        print("Article search failed:", e)
        return []


def build_article_search_query(message: str):
    msg = (message or "").lower()
    if "river" in msg:
        return "river table epoxy"
    if "deep pour" in msg:
        return "deep pour epoxy"
    if "tabletop" in msg or "counter" in msg:
        return "tabletop epoxy countertop"
    if "floor" in msg:
        return "epoxy flooring garage floor"
    if "pigment" in msg or "mica" in msg:
        return "resin pigment mica powder"
    if "mold" in msg or "coaster" in msg:
        return "resin molds coasters"
    if "sand" in msg or "polish" in msg:
        return "sanding polishing epoxy resin"
    return message
