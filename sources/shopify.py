"""
Shopify storefront lookup: price and stock from the public product JSON.

Any Shopify store serves /products/<handle>.json without credentials, which is
cheaper and more stable than scraping the page. Called by extract_product for
URLs shaped like a Shopify product page; a 404 means the store is not Shopify.
"""
import re
from urllib.parse import urlparse

from . import http
from .envelope import envelope, skipped

PRODUCT_PATH = re.compile(r"^(?:/collections/[^/]+)?/products/([^/?#]+?)(?:\.json)?/?$")


def is_shopify(url: str) -> bool:
    return PRODUCT_PATH.match(urlparse(url).path) is not None


async def product_json_url(url: str) -> str:
    parts = urlparse(url)
    handle = PRODUCT_PATH.match(parts.path).group(1)
    return f"https://{parts.netloc}/products/{handle}.json"


async def lookup(url: str) -> dict:
    if not is_shopify(url):
        return skipped("shopify", "not_shopify")
    json_url = await product_json_url(url)
    async with http.client() as c:
        r = await c.get(json_url)
    # -- password-protected stores redirect every path to /password
    if r.url.path == "/password" or r.status_code in http.BLOCKED_STATUSES:
        return skipped("shopify", "blocked")
    if r.status_code != 200:
        return skipped("shopify", "not_shopify")
    product = r.json()["product"]
    variants = product["variants"]
    # -- the public .json omits 'available' on most stores; inventory_quantity is the next signal, else unknown
    in_stock = [v for v in variants if v.get("available") or (v.get("available") is None and (v.get("inventory_quantity") or 0) > 0)]
    known = any("available" in v or "inventory_quantity" in v for v in variants)
    cheapest = min(in_stock or variants, key=lambda v: http.money(v["price"]))
    data = {
        "title": product["title"],
        "price": http.money(cheapest["price"]),
        "currency": "USD",
        "availability": ("InStock" if in_stock else "OutOfStock") if known else None,
        "merchant": urlparse(url).netloc,
        "url": url,
    }
    return envelope(data, checked=["shopify"])
