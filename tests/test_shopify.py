import httpx

from sources import shopify


def test_handle_detection():
    assert shopify.is_shopify("https://shop.example.com/products/blue-widget")
    assert shopify.is_shopify("https://shop.example.com/collections/sale/products/blue-widget?variant=1")
    assert not shopify.is_shopify("https://shop.example.com/pages/about")


async def test_json_url_drops_collection_and_query():
    url = await shopify.product_json_url("https://shop.example.com/collections/sale/products/blue-widget?v=1")
    assert url == "https://shop.example.com/products/blue-widget.json"


async def test_not_shopify_shaped_url():
    out = await shopify.lookup("https://example.com/item/1")
    assert out["sources_skipped"] == [{"name": "shopify", "reason": "not_shopify"}]


async def test_lookup_picks_cheapest_available(mock_http):
    mock_http(lambda r: httpx.Response(200, json={"product": {"title": "Widget", "variants": [
        {"price": "5.00", "available": False}, {"price": "30.00", "available": True}, {"price": "20.00", "available": True}]}}))
    out = await shopify.lookup("https://shop.example.com/products/widget")
    assert out["sources_checked"] == ["shopify"]
    assert out["data"] == {"title": "Widget", "price": 20.0, "currency": "USD", "availability": "InStock",
                           "merchant": "shop.example.com", "url": "https://shop.example.com/products/widget"}


async def test_lookup_all_sold_out(mock_http):
    mock_http(lambda r: httpx.Response(200, json={"product": {"title": "W", "variants": [
        {"price": "9.00", "available": False}, {"price": "7.00", "available": False}]}}))
    out = await shopify.lookup("https://shop.example.com/products/w")
    assert out["data"]["price"] == 7.0 and out["data"]["availability"] == "OutOfStock"


async def test_password_redirect_is_blocked(mock_http):
    def handler(request):
        if request.url.path == "/password":
            return httpx.Response(200, text="password page")
        return httpx.Response(302, headers={"location": "/password"})
    mock_http(handler)
    out = await shopify.lookup("https://shop.example.com/products/widget")
    assert out["sources_skipped"] == [{"name": "shopify", "reason": "blocked"}]


async def test_status_mapping(mock_http):
    mock_http(lambda r: httpx.Response(429))
    assert (await shopify.lookup("https://s.example.com/products/w"))["sources_skipped"][0]["reason"] == "blocked"
    mock_http(lambda r: httpx.Response(404))
    assert (await shopify.lookup("https://s.example.com/products/w"))["sources_skipped"][0]["reason"] == "not_shopify"


async def test_lookup_without_available_uses_inventory_quantity(mock_http):
    mock_http(lambda r: httpx.Response(200, json={"product": {"title": "W", "variants": [
        {"price": "5.00", "inventory_quantity": 0}, {"price": "8.00", "inventory_quantity": 3}]}}))
    out = await shopify.lookup("https://shop.example/products/w")
    assert out["data"]["price"] == 8.0 and out["data"]["availability"] == "InStock"


async def test_lookup_with_no_stock_signal_reports_unknown(mock_http):
    mock_http(lambda r: httpx.Response(200, json={"product": {"title": "W", "variants": [{"price": "5.00"}]}}))
    out = await shopify.lookup("https://shop.example/products/w")
    assert out["data"]["price"] == 5.0 and out["data"]["availability"] is None
