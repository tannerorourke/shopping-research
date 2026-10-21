"""Server-level behavior: fan-out union, failure isolation, status and reload."""
import httpx

import server
import settings as settings_mod
from sources import bestbuy, ebay, serpapi, target
from sources.envelope import envelope, skipped


async def test_search_unions_sources_and_isolates_failures(monkeypatch):
    async def ok(query, num):
        return envelope([{"title": "a", "price": 30.0, "merchant": "ebay", "url": "u", "product_id": "1"}], ["ebay"])
    async def cheap(query, num):
        return envelope([{"title": "a", "price": 20.0, "merchant": "bestbuy", "url": "u", "product_id": "2"}], ["bestbuy"])
    async def boom(query, num):
        raise httpx.ReadTimeout("slow")
    monkeypatch.setattr(serpapi, "search_products", lambda q, n: _skip("serpapi"))
    monkeypatch.setitem(server.RETAILERS, "ebay", ok)
    monkeypatch.setitem(server.RETAILERS, "bestbuy", cheap)
    monkeypatch.setitem(server.RETAILERS, "target", boom)
    out = await server.search_products("thing")
    assert [i["merchant"] for i in out["data"]] == ["bestbuy", "ebay"]
    assert out["sources_checked"] == ["ebay", "bestbuy"]
    assert {s["name"]: s["reason"] for s in out["sources_skipped"]} == {"serpapi": "disabled_in_settings", "target": "timeout"}


async def _skip(name):
    return skipped(name, "disabled_in_settings", data=[])


async def test_tools_registered():
    names = sorted(t.name for t in await server.mcp.list_tools())
    assert names == ["c1_check", "compare_prices", "extract_product", "get_deals",
                     "get_price_history", "get_status", "reload_settings", "search_products"]


async def test_c1_disabled_by_default_and_status(toml_settings):
    toml_settings("")
    out = await server.c1_check("https://www.amazon.com/dp/B000000000")
    assert out["sources_skipped"] == [{"name": "c1_shopping", "reason": "disabled_in_settings"}]
    status = await server.get_status()
    assert status["serpapi_remaining"] == 250 and status["c1_enabled"] is False and status["ebay_token_ok"] is False


async def test_reload_settings_picks_up_file_change(toml_settings, tmp_path):
    toml_settings('[serpapi]\napi_key = "k"\nmonthly_budget = 7\n')
    (tmp_path / "settings.toml").write_text('[serpapi]\napi_key = "k"\nmonthly_budget = 9\n[c1]\nenabled = true\n')
    status = await server.reload_settings()
    assert status["serpapi_remaining"] == 9 and status["c1_enabled"] is True
