"""
Best Buy Products API: keyword search sorted by sale price.

Endpoint: GET https://api.bestbuy.com/v1/products((search=a&search=b)) with the
API key as a query parameter. The filter lives in the path, so it is built by
hand with one quoted 'search=' clause per query word; everything else goes
through httpx params.
"""
from urllib.parse import quote

import httpx

import settings
from . import http
from .envelope import envelope, skipped
from .http import money

BASE_URL = "https://api.bestbuy.com/v1/products"
FIELDS = "sku,name,salePrice,regularPrice,url,onlineAvailability"


async def search(query: str, num: int = 10) -> dict:
    key = settings.current().bestbuy.api_key
    if not key:
        return skipped("bestbuy", "disabled_in_settings", data=[])
    clauses = "&".join(f"search={quote(w, safe='')}" for w in query.split())
    params = {"apiKey": key, "format": "json", "show": FIELDS,
              "pageSize": num, "sort": "salePrice.asc"}
    try:
        async with http.client() as c:
            r = await c.get(f"{BASE_URL}(({clauses}))", params=params)
    except httpx.TimeoutException:
        return skipped("bestbuy", "timeout", data=[])
    if r.status_code != 200:
        return skipped("bestbuy", http.reason_for(r.status_code), data=[])
    items = [{
        "title": p.get("name"),
        "price": money(p.get("salePrice")),
        "merchant": "bestbuy",
        "url": p.get("url"),
        "product_id": str(p["sku"]) if p.get("sku") is not None else None,
        "regular_price": money(p.get("regularPrice")),
        "in_stock": p.get("onlineAvailability"),
    } for p in r.json().get("products", [])]
    if not items:
        return skipped("bestbuy", "no_results", data=[])
    return envelope(items, checked=["bestbuy"])
