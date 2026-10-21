"""
SerpApi: Google Shopping search and per-merchant offers (google_product engine).

Primary discovery and comparison source. Every call passes through
'serpapi_budget', so a month past 'monthly_budget' returns 'quota_exhausted'
instead of a request, and a repeated query is served from the cache.
"""
import httpx

from . import http
from .budget import serpapi_budget
from .envelope import envelope, skipped
from .http import money

SEARCH_URL = "https://serpapi.com/search"


async def _call(params: dict) -> tuple[dict | None, str | None]:
    """Returns (json, None) on success, (None, skip_reason) otherwise. Spends budget only on 200."""
    try:
        async with http.client() as c:
            r = await c.get(SEARCH_URL, params={**params, "api_key": serpapi_budget.key})
    except httpx.TimeoutException:
        return None, "timeout"
    if r.status_code == 401:
        return None, "auth_error"
    if r.status_code != 200:
        return None, "blocked"
    serpapi_budget.spend()
    return r.json(), None


async def search_products(query: str, num: int = 10) -> dict:
    cache_key = ("shopping", query, num)
    cached = serpapi_budget.cache_get(cache_key)
    if cached is not None:
        return envelope(cached, checked=["serpapi:cache"])
    if not serpapi_budget.key:
        return skipped("serpapi", "disabled_in_settings", data=[])
    if not serpapi_budget.can_spend():
        return skipped("serpapi", "quota_exhausted", data=[])
    body, reason = await _call({"engine": "google_shopping", "q": query, "num": num})
    if reason:
        return skipped("serpapi", reason, data=[])
    items = [{
        "title": i.get("title"),
        "price": i.get("extracted_price"),
        "merchant": i.get("source"),
        "url": i.get("product_link") or i.get("link"),
        "product_id": i.get("product_id"),
    } for i in body.get("shopping_results", [])]
    serpapi_budget.cache_put(cache_key, items)
    if not items:
        return skipped("serpapi", "no_results", data=[])
    return envelope(items, checked=["serpapi"])


async def compare_prices(product_id: str | None = None, query: str | None = None) -> dict:
    if product_id is None:
        hits = await search_products(query, num=1)
        if not hits["data"] or not hits["data"][0].get("product_id"):
            return envelope([], checked=hits["sources_checked"],
                            skipped=hits["sources_skipped"] or [{"name": "serpapi", "reason": "no_results"}])
        product_id = hits["data"][0]["product_id"]
    cache_key = ("product", product_id)
    cached = serpapi_budget.cache_get(cache_key)
    if cached is not None:
        return envelope(cached, checked=["serpapi:google_product:cache"])
    if not serpapi_budget.key:
        return skipped("serpapi", "disabled_in_settings", data=[])
    if not serpapi_budget.can_spend():
        return skipped("serpapi", "quota_exhausted", data=[])
    body, reason = await _call({"engine": "google_product", "product_id": product_id, "offers": "1"})
    if reason:
        return skipped("serpapi", reason, data=[])
    sellers = body.get("sellers_results", {}).get("online_sellers", [])
    offers = sorted(
        [{"merchant": s.get("name"), "price": money(s.get("base_price")),
          "total_price": money(s.get("total_price")), "url": s.get("link")} for s in sellers],
        key=lambda o: o["price"] if o["price"] is not None else 1e9)
    serpapi_budget.cache_put(cache_key, offers)
    if not offers:
        return skipped("serpapi:google_product", "no_results", data=[])
    return envelope(offers, checked=["serpapi:google_product"])
