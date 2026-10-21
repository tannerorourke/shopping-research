"""
shopping-research: a local FastMCP server (stdio) giving Claude Code product search,
cross-retailer prices, Amazon price history, community deals, and an optional
Capital One Shopping cross-check.

Run:   uv run server.py              (stdio; register in .mcp.json or 'claude mcp add')
Config: settings.toml beside this file (copy settings.toml.example), env vars override.

Every tool returns {data, sources_checked, sources_skipped}. The fan-out tools
union the envelopes of each source so the caller sees exactly which retailers
answered and which were skipped, and why. The server never retries a source
that reported itself blocked.
"""
import asyncio
import sys

import httpx
from fastmcp import FastMCP

import settings as settings_mod
from auth import tokens
from c1 import check as c1_check_mod
from c1 import settings as c1_settings
from sources import bestbuy, camel, ebay, extract, serpapi, slickdeals, target
from sources.budget import serpapi_budget
from sources.envelope import merge, skipped

mcp = FastMCP(
    "shopping-research",
    instructions=("Shopping research over free sources. Every result carries sources_checked and "
                  "sources_skipped; 'best price' means lowest among sources checked. Call get_status "
                  "before spending SerpApi quota."),
)

RETAILERS = {"ebay": ebay.search, "bestbuy": bestbuy.search, "target": target.search}


def _price_key(item: dict):
    return item.get("price") if item.get("price") is not None else 1e9


async def _guard(name: str, coro):
    """A source that raises never takes the fan-out down; it is reported as a skip."""
    try:
        return await coro
    except httpx.TimeoutException:
        return skipped(name, "timeout", data=[])
    except Exception as e:  # -- unexpected failure in one source: report, keep the others
        print(f"[shopping-research] {name} failed: {e!r}", file=sys.stderr)
        return skipped(name, "blocked", data=[])


async def _fan_out(query: str, num: int) -> list[dict]:
    return list(await asyncio.gather(*(_guard(n, f(query, num)) for n, f in RETAILERS.items())))


@mcp.tool
async def search_products(query: str, num: int = 10) -> dict:
    """Find candidate products across Google Shopping (SerpApi), eBay, Best Buy, and Target.
    data: [{title, price, merchant, url, product_id}] sorted by price ascending."""
    envelopes = [await _guard("serpapi", serpapi.search_products(query, num))] + await _fan_out(query, num)
    return merge(envelopes, sort_key=_price_key)


@mcp.tool
async def compare_prices(product_id: str | None = None, query: str | None = None) -> dict:
    """Per-merchant offers for one product. Pass the SerpApi product_id from search_products,
    or a query (the retailer APIs are searched by it too). data: [{merchant, price, url}] ascending."""
    envelopes = [await _guard("serpapi:google_product", serpapi.compare_prices(product_id, query))]
    if query:
        for env in await _fan_out(query, 5):
            env["data"] = [{"merchant": i["merchant"], "price": i["price"], "url": i["url"], "title": i["title"]}
                           for i in env["data"]]
            envelopes.append(env)
    return merge(envelopes, sort_key=_price_key)


@mcp.tool
async def extract_product(url: str) -> dict:
    """Title, price, currency, availability from any product page: Shopify JSON, schema.org JSON-LD,
    OpenGraph, then a headless-browser fallback."""
    return await _guard("page", extract.extract_product(url))


@mcp.tool
async def get_price_history(asin: str | None = None) -> dict:
    """Amazon price history from CamelCamelCamel. Accepts an ASIN or an amazon.com product URL.
    data: {lowest, highest, average, current, verdict} or None with skip reason not_amazon."""
    return await _guard("camelcamelcamel", camel.get_price_history(camel.asin_from_url(asin) if asin else None))


@mcp.tool
async def get_deals(query: str | None = None, category: str | None = None) -> dict:
    """Community-vetted deals from Slickdeals RSS (US). data: [{title, price, store, url, votes}]."""
    return await _guard("slickdeals", slickdeals.get_deals(query, category))


@mcp.tool
async def c1_check(url: str) -> dict:
    """Optional Capital One Shopping cross-check on one finalist URL. Off unless [c1] enabled = true;
    returns sources_skipped disabled_in_settings otherwise. data: {c1_best, offers}."""
    return await _guard("c1_shopping", c1_check_mod.c1_check(url))


async def _status() -> dict:
    s = settings_mod.current()
    ebay_ok = bool(s.ebay.client_id and s.ebay.client_secret) and await tokens.get_ebay_token() is not None
    return {
        "serpapi_configured": bool(s.serpapi.api_key),
        "serpapi_remaining": serpapi_budget.remaining,
        "serpapi_spent": serpapi_budget.spent,
        "ebay_token_ok": ebay_ok,
        "bestbuy_configured": bool(s.bestbuy.api_key),
        "target_enabled": s.target.enabled,
        "c1_enabled": s.c1.enabled,
        "c1_calls_used": c1_check_mod.calls_used(),
        "c1_extension_version": c1_settings.manifest_version(s.c1),
        "settings_path": str(settings_mod.settings_path()),
    }


@mcp.tool
async def get_status() -> dict:
    """Coverage before spending quota: which sources are configured, SerpApi searches left this month,
    whether the C1 cross-check is enabled."""
    return await _status()


@mcp.tool
async def reload_settings() -> dict:
    """Re-read settings.toml without restarting. A running C1 browser is closed if enabled flips to false."""
    was_enabled = settings_mod.current().c1.enabled
    settings_mod.reload()
    serpapi_budget.reload()
    if was_enabled and not settings_mod.current().c1.enabled:
        await c1_check_mod.shutdown()
    return await _status()


if __name__ == "__main__":
    mcp.run()
