# -- Undocumented endpoint: the RedSky field paths below were written from memory and need one live confirmation.
"""
Target RedSky product search (undocumented, scraped public key).

Endpoint: GET https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2.
The key is public and rotates; a 401/403 triggers one re-scrape of target.com
for the current key, persisted in STATE_DIR/target_key.txt, then one retry.
Still refused means 'blocked' and no further attempts.
"""
import re

import httpx

import settings
from . import http
from .envelope import envelope, skipped

SEARCH_URL = "https://redsky.target.com/redsky_aggregations/v1/web/plp_search_v2"
HOME_URL = "https://www.target.com/"
DEFAULT_KEY = "9f36aeafbe60771e321a7cc95a78140772ab3e96"
VISITOR_ID = "0189A3B4C5D6E7F80123456789ABCDEF"
KEY_PATTERNS = (r'"apiKey"\s*:\s*"([0-9a-f]{40})"', r"key=([0-9a-f]{40})")


def _key_path():
    return settings.STATE_DIR / "target_key.txt"


def _key() -> str:
    return _key_path().read_text().strip() if _key_path().exists() else DEFAULT_KEY


async def _scrape_key() -> str | None:
    async with http.client() as c:
        r = await c.get(HOME_URL)
    for pattern in KEY_PATTERNS:
        m = re.search(pattern, r.text)
        if m:
            settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
            _key_path().write_text(m.group(1))
            return m.group(1)
    return None


async def _get(key: str, query: str, num: int) -> httpx.Response:
    params = {"key": key, "channel": "WEB", "keyword": query, "count": num,
              "page": f"/s/{query}", "pricing_store_id": "3991",
              "visitor_id": VISITOR_ID, "platform": "desktop"}
    async with http.client() as c:
        return await c.get(SEARCH_URL, params=params)


async def search(query: str, num: int = 10) -> dict:
    if not settings.current().target.enabled:
        return skipped("target", "disabled_in_settings", data=[])
    try:
        r = await _get(_key(), query, num)
        if r.status_code in (401, 403):
            fresh = await _scrape_key()
            if fresh is None:
                return skipped("target", "blocked", data=[])
            r = await _get(fresh, query, num)
    except httpx.TimeoutException:
        return skipped("target", "timeout", data=[])
    if r.status_code != 200:
        return skipped("target", "blocked", data=[])
    products = r.json().get("data", {}).get("search", {}).get("products", [])
    items = []
    for p in products:
        price = p.get("price", {})
        items.append({
            "title": p.get("item", {}).get("product_description", {}).get("title"),
            "price": http.money(price.get("current_retail", price.get("current_retail_min"))),
            "merchant": "target",
            "url": p.get("item", {}).get("enrichment", {}).get("buy_url"),
            "product_id": p.get("tcin"),
        })
    if not items:
        return skipped("target", "no_results", data=[])
    return envelope(items, checked=["target"])
