import os

# The desktop environment can inject a dead local proxy. The chat service must call
# Chatwoot, Shopify, and OpenAI directly so customer replies do not get stuck.
for proxy_key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
    os.environ.pop(proxy_key, None)
os.environ.setdefault("NO_PROXY", "*")
os.environ.setdefault("no_proxy", "*")
import re
import requests
from dotenv import load_dotenv

load_dotenv()

SHOPIFY_STORE_DOMAIN = os.getenv("RESIN_SHOPIFY_STORE_DOMAIN") or os.getenv("SHOPIFY_STORE_DOMAIN")
SHOPIFY_ADMIN_ACCESS_TOKEN = os.getenv("RESIN_SHOPIFY_ADMIN_ACCESS_TOKEN") or os.getenv("SHOPIFY_ADMIN_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01")
SITE_URL = "https://resinsociety.net"


def shopify_graphql(query: str, variables: dict | None = None):
    url = f"https://{SHOPIFY_STORE_DOMAIN}/admin/api/{SHOPIFY_API_VERSION}/graphql.json"

    headers = {
        "X-Shopify-Access-Token": SHOPIFY_ADMIN_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }

    response = requests.post(
        url,
        headers=headers,
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )

    if response.status_code != 200:
        print("Shopify error:", response.status_code, response.text)
        response.raise_for_status()

    data = response.json()

    if "errors" in data:
        print("Shopify GraphQL errors:", data["errors"])
        raise Exception(data["errors"])

    return data["data"]


def normalize_email(email):
    return (email or "").lower().strip()


def clean_order_number(order_number):
    if not order_number:
        return ""

    text = str(order_number).strip()
    text = text.replace("Order", "").replace("order", "")
    text = text.replace("Number", "").replace("number", "")
    text = text.replace(":", "").strip()

    match = re.search(r"#?\s*(\d+)", text)
    if match:
        return match.group(1)

    return text.replace("#", "").strip()


def order_name_matches(order_name, order_number):
    clean = clean_order_number(order_number)
    if not clean or not order_name:
        return False

    name = str(order_name).strip()

    return name == f"#{clean}" or name == clean or clean in name


def format_order_node(o):
    if not o:
        return None

    tracking = []
    for fulfillment in o.get("fulfillments", []) or []:
        for t in fulfillment.get("trackingInfo", []) or []:
            tracking.append({
                "number": t.get("number"),
                "url": t.get("url"),
                "company": t.get("company"),
            })

    items = []
    for item in ((o.get("lineItems") or {}).get("edges") or []):
        node = item.get("node") or {}
        items.append({
            "name": node.get("name"),
            "quantity": node.get("quantity"),
        })

    customer = o.get("customer") or {}

    return {
        "id": o.get("id"),
        "order_name": o.get("name"),
        "customer_email": customer.get("email"),
        "financial_status": o.get("displayFinancialStatus"),
        "fulfillment_status": o.get("displayFulfillmentStatus"),
        "created_at": o.get("createdAt"),
        "processed_at": o.get("processedAt"),
        "cancelled_at": o.get("cancelledAt"),
        "closed_at": o.get("closedAt"),
        "total": ((o.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount"),
        "currency": ((o.get("totalPriceSet") or {}).get("shopMoney") or {}).get("currencyCode"),
        "tracking": tracking,
        "items": items,
    }


ORDER_FIELDS = """
id
name
displayFinancialStatus
displayFulfillmentStatus
createdAt
processedAt
cancelledAt
closedAt
customer {
  email
}
totalPriceSet {
  shopMoney {
    amount
    currencyCode
  }
}
fulfillments {
  trackingInfo {
    number
    url
    company
  }
}
lineItems(first: 20) {
  edges {
    node {
      name
      quantity
    }
  }
}
"""


def search_products(search_term: str, limit: int = 10):
    query = """
    query SearchProducts($query: String!, $first: Int!) {
      products(first: $first, query: $query) {
        edges {
          node {
            id
            title
            handle
            vendor
            productType
            tags
            status
            onlineStoreUrl
            descriptionPlainSummary: description(truncateAt: 800)
            seo {
              title
              description
            }
            priceRangeV2 {
              minVariantPrice {
                amount
                currencyCode
              }
            }
            featuredImage {
              url
            }
            variants(first: 50) {
              edges {
                node {
                  title
                  availableForSale
                  price
                  inventoryQuantity
                }
              }
            }
            metafields(first: 50) {
              edges {
                node {
                  namespace
                  key
                  type
                  value
                }
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "query": search_term,
        "first": limit,
    }

    data = shopify_graphql(query, variables)
    products = []

    for edge in data["products"]["edges"]:
        p = edge["node"]

        metafields = []
        for mf_edge in p.get("metafields", {}).get("edges", []):
            mf = mf_edge["node"]
            metafields.append(
                {
                    "namespace": mf.get("namespace"),
                    "key": mf.get("key"),
                    "type": mf.get("type"),
                    "value": mf.get("value"),
                }
            )

        products.append(
            {
                "id": p.get("id"),
                "title": p.get("title"),
                "handle": p.get("handle"),
                "vendor": p.get("vendor"),
                "product_type": p.get("productType"),
                "tags": p.get("tags", []),
                "status": p.get("status"),
                "url": p.get("onlineStoreUrl") or f"{SITE_URL}/products/{p['handle']}",
                "description": p.get("descriptionPlainSummary"),
                "seo_title": (p.get("seo") or {}).get("title"),
                "seo_description": (p.get("seo") or {}).get("description"),
                "price": p["priceRangeV2"]["minVariantPrice"]["amount"],
                "currency": p["priceRangeV2"]["minVariantPrice"]["currencyCode"],
                "image": p["featuredImage"]["url"] if p.get("featuredImage") else None,
                "variants": [
                    {
                        "title": v["node"]["title"],
                        "available": v["node"]["availableForSale"],
                        "price": v["node"]["price"],
                        "inventory": v["node"]["inventoryQuantity"],
                    }
                    for v in p["variants"]["edges"]
                ],
                "metafields": metafields,
            }
        )

    return products


def lookup_customer_by_email(email):
    email = normalize_email(email)

    if not email:
        return None

    query = """
    query FindCustomer($query: String!) {
      customers(first: 1, query: $query) {
        edges {
          node {
            id
            firstName
            lastName
            email
            phone
            numberOfOrders
          }
        }
      }
    }
    """

    variables = {
        "query": f"email:{email}"
    }

    data = shopify_graphql(query, variables)
    edges = data["customers"]["edges"]

    if not edges:
        return None

    c = edges[0]["node"]

    return {
        "id": c["id"],
        "first_name": c.get("firstName"),
        "last_name": c.get("lastName"),
        "email": c.get("email"),
        "phone": c.get("phone"),
        "number_of_orders": c.get("numberOfOrders"),
    }


def lookup_customer_orders(email, limit=10):
    email = normalize_email(email)

    if not email:
        return []

    query = f"""
    query CustomerOrders($query: String!, $first: Int!) {{
      orders(first: $first, query: $query, reverse: true) {{
        edges {{
          node {{
            {ORDER_FIELDS}
          }}
        }}
      }}
    }}
    """

    query_attempts = [
        f"email:{email}",
        f'email:"{email}"',
        email,
    ]

    last_error = None

    for q in query_attempts:
        try:
            variables = {
                "query": q,
                "first": limit,
            }

            data = shopify_graphql(query, variables)

            orders = []
            for edge in data["orders"]["edges"]:
                order = format_order_node(edge["node"])
                if order:
                    orders.append(order)

            if orders:
                return orders

        except Exception as e:
            last_error = e
            print(f"lookup_customer_orders attempt failed for query '{q}':", e)

    if last_error:
        print("lookup_customer_orders final failure:", last_error)

    return []


def _find_order_by_query(query_string):
    query = f"""
    query FindOrder($query: String!) {{
      orders(first: 5, query: $query, reverse: true) {{
        edges {{
          node {{
            {ORDER_FIELDS}
          }}
        }}
      }}
    }}
    """

    variables = {
        "query": query_string
    }

    data = shopify_graphql(query, variables)
    edges = data["orders"]["edges"]

    return [format_order_node(edge["node"]) for edge in edges if edge.get("node")]


def lookup_order(order_number, email=None):
    """
    Hardened order lookup.

    Tries multiple Shopify search formats:
    - name:#1001
    - name:1001
    - #1001
    - 1001
    - email lookup fallback, then order-number match
    """

    clean = clean_order_number(order_number)
    email = normalize_email(email)

    if not clean:
        return None

    query_attempts = [
        f"name:#{clean}",
        f"name:{clean}",
        f'"#{clean}"',
        f'"{clean}"',
        f"#{clean}",
        clean,
    ]

    if email:
        query_attempts = [
            f"name:#{clean} email:{email}",
            f"name:{clean} email:{email}",
            f'email:"{email}" name:"#{clean}"',
            f"email:{email} name:#{clean}",
        ] + query_attempts

    seen_queries = []
    for q in query_attempts:
        if q in seen_queries:
            continue
        seen_queries.append(q)

        try:
            orders = _find_order_by_query(q)

            for order in orders:
                if not order:
                    continue

                if not order_name_matches(order.get("order_name"), clean):
                    continue

                if email:
                    order_email = normalize_email(order.get("customer_email"))
                    if order_email and order_email != email:
                        continue

                order["lookup_query_used"] = q
                return order

            # fallback: if exact match failed, allow first result only for highly specific name queries
            if orders and q.startswith("name:"):
                order = orders[0]
                if email:
                    order_email = normalize_email(order.get("customer_email"))
                    if order_email and order_email != email:
                        continue
                order["lookup_query_used"] = q
                return order

        except Exception as e:
            print(f"lookup_order attempt failed for query '{q}':", e)

    # Strong fallback: search by email and match order number locally
    if email:
        try:
            customer_orders = lookup_customer_orders(email, limit=25)

            for order in customer_orders:
                if order_name_matches(order.get("order_name"), clean):
                    order["lookup_query_used"] = f"lookup_customer_orders:{email}"
                    return order

        except Exception as e:
            print("lookup_order customer order fallback failed:", e)

    return None


def get_order_tracking(order_number, email=None):
    order = lookup_order(order_number, email=email)

    if not order:
        return None

    return {
        "order_name": order.get("order_name"),
        "fulfillment_status": order.get("fulfillment_status"),
        "financial_status": order.get("financial_status"),
        "created_at": order.get("created_at"),
        "processed_at": order.get("processed_at"),
        "tracking": order.get("tracking", []),
        "items": order.get("items", []),
    }

