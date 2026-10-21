import httpx

from sources import bestbuy

KEY = '[bestbuy]\napi_key = "k"\n'


async def test_blank_key_disabled():
    out = await bestbuy.search("widget")
    assert out["data"] == [] and out["sources_skipped"] == [{"name": "bestbuy", "reason": "disabled_in_settings"}]


async def test_happy_path_and_url_shape(mock_http, toml_settings):
    toml_settings(KEY)
    seen = {}
    def handler(request):
        seen["url"] = request.url
        return httpx.Response(200, json={"products": [
            {"sku": 6501, "name": "Widget", "salePrice": 9.5, "regularPrice": 12.0,
             "url": "https://bb/6501", "onlineAvailability": True}]})
    mock_http(handler)
    out = await bestbuy.search("blue widget", num=5)
    assert seen["url"].path == "/v1/products((search=blue&search=widget))"
    assert seen["url"].params["apiKey"] == "k" and seen["url"].params["pageSize"] == "5"
    assert out["sources_checked"] == ["bestbuy"]
    assert out["data"] == [{"title": "Widget", "price": 9.5, "merchant": "bestbuy", "url": "https://bb/6501",
                            "product_id": "6501", "regular_price": 12.0, "in_stock": True}]


async def test_403_blocked(mock_http, toml_settings):
    toml_settings(KEY)
    mock_http(lambda r: httpx.Response(403))
    out = await bestbuy.search("widget")
    assert out["sources_skipped"][0]["reason"] == "blocked"


async def test_timeout(mock_http, toml_settings):
    toml_settings(KEY)
    def handler(request):
        raise httpx.ReadTimeout("slow")
    mock_http(handler)
    out = await bestbuy.search("widget")
    assert out["sources_skipped"][0]["reason"] == "timeout"


async def test_empty_is_no_results(mock_http, toml_settings):
    toml_settings(KEY)
    mock_http(lambda r: httpx.Response(200, json={"products": []}))
    out = await bestbuy.search("widget")
    assert out["data"] == [] and out["sources_skipped"][0]["reason"] == "no_results"
