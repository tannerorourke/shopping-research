import json

import httpx

from sources import serpapi
from sources.budget import serpapi_budget


def _shopping(request):
    assert request.url.params["engine"] == "google_shopping"
    return httpx.Response(200, json={"shopping_results": [
        {"title": "Widget", "extracted_price": 19.5, "source": "Acme", "product_link": "https://g/p1", "product_id": "p1"}]})


async def test_search_without_key_is_disabled():
    out = await serpapi.search_products("widget")
    assert out["data"] == [] and out["sources_skipped"] == [{"name": "serpapi", "reason": "disabled_in_settings"}]


async def test_search_spends_then_caches(mock_http, toml_settings):
    toml_settings('[serpapi]\napi_key = "k"\nmonthly_budget = 2\n')
    mock_http(_shopping)
    first = await serpapi.search_products("widget")
    assert first["sources_checked"] == ["serpapi"] and first["data"][0]["price"] == 19.5
    assert serpapi_budget.spent == 1
    again = await serpapi.search_products("widget")
    assert again["sources_checked"] == ["serpapi:cache"] and serpapi_budget.spent == 1


async def test_quota_hard_stop(mock_http, toml_settings):
    toml_settings('[serpapi]\napi_key = "k"\nmonthly_budget = 1\n')
    mock_http(_shopping)
    await serpapi.search_products("a")
    out = await serpapi.search_products("b")
    assert out["sources_skipped"][0]["reason"] == "quota_exhausted"


async def test_compare_sorts_offers_ascending(mock_http, toml_settings):
    toml_settings('[serpapi]\napi_key = "k"\n')
    def handler(request):
        assert request.url.params["engine"] == "google_product"
        return httpx.Response(200, json={"sellers_results": {"online_sellers": [
            {"name": "B", "base_price": "$30.00", "link": "b"}, {"name": "A", "base_price": "$1,020.50", "link": "a"},
            {"name": "C", "base_price": "$9.99", "total_price": "$14.99", "link": "c"}]}})
    mock_http(handler)
    out = await serpapi.compare_prices(product_id="p1")
    assert [o["merchant"] for o in out["data"]] == ["C", "B", "A"]
    assert out["data"][2]["price"] == 1020.5 and out["data"][0]["total_price"] == 14.99


async def test_compare_by_query_with_no_hit(mock_http, toml_settings):
    toml_settings('[serpapi]\napi_key = "k"\n')
    mock_http(lambda r: httpx.Response(200, json={"shopping_results": []}))
    out = await serpapi.compare_prices(query="nothing")
    assert out["data"] == [] and out["sources_skipped"][0]["reason"] == "no_results"


async def test_auth_error_is_reported_not_spent(mock_http, toml_settings):
    toml_settings('[serpapi]\napi_key = "bad"\n')
    mock_http(lambda r: httpx.Response(401, json={"error": "Invalid API key"}))
    out = await serpapi.search_products("x")
    assert out["sources_skipped"][0]["reason"] == "auth_error" and serpapi_budget.spent == 0
