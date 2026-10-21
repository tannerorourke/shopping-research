"""
eBay Browse API: keyword search over live listings.

Endpoint: GET https://api.ebay.com/buy/browse/v1/item_summary/search with a
Bearer application token from auth.tokens. A 401 means the cached token went
stale early, so the token is force-refreshed and the request retried once.
"""
import httpx

import settings
from auth.tokens import get_ebay_token
from . import http
from .envelope import envelope, skipped
from .http import money

SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


async def _get(token: str, query: str, num: int) -> httpx.Response:
    async with http.client() as c:
        return await c.get(SEARCH_URL, params={"q": query, "limit": num},
                           headers={"Authorization": f"Bearer {token}",
                                    "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})


async def search(query: str, num: int = 10) -> dict:
    cfg = settings.current().ebay
    if not (cfg.client_id and cfg.client_secret):
        return skipped("ebay", "disabled_in_settings", data=[])
    token = await get_ebay_token()
    if token is None:
        return skipped("ebay", "auth_error", data=[])
    try:
        r = await _get(token, query, num)
        if r.status_code == 401:
            token = await get_ebay_token(force=True)
            if token is None:
                return skipped("ebay", "auth_error", data=[])
            r = await _get(token, query, num)
    except httpx.TimeoutException:
        return skipped("ebay", "timeout", data=[])
    if r.status_code != 200:
        return skipped("ebay", http.reason_for(r.status_code), data=[])
    items = [{
        "title": i.get("title"),
        "price": money(i.get("price", {}).get("value")),
        "merchant": "ebay",
        "url": i.get("itemWebUrl"),
        "product_id": i.get("itemId"),
        "condition": i.get("condition"),
    } for i in r.json().get("itemSummaries", [])]
    if not items:
        return skipped("ebay", "no_results", data=[])
    return envelope(items, checked=["ebay"])
