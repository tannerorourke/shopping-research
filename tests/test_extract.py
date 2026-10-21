import json

import httpx

from sources import extract


def _ld(blob) -> str:
    return f'<html><head><script type="application/ld+json">{json.dumps(blob)}</script></head></html>'


def test_jsonld_plain_product():
    html = _ld({"@type": "Product", "name": "Widget", "offers": {
        "@type": "Offer", "price": "19.99", "priceCurrency": "USD", "availability": "https://schema.org/InStock"}})
    assert extract.find_jsonld_product(html) == {
        "title": "Widget", "price": 19.99, "currency": "USD", "availability": "InStock", "merchant": None}


def test_jsonld_top_level_list_with_offer_list():
    html = _ld([{"@type": "BreadcrumbList"}, {"@type": ["Thing", "Product"], "name": "W", "offers": [
        {"price": 5, "priceCurrency": "EUR", "availability": "https://schema.org/OutOfStock"}]}])
    found = extract.find_jsonld_product(html)
    assert found["price"] == 5.0 and found["availability"] == "OutOfStock" and found["currency"] == "EUR"


def test_jsonld_graph_aggregate_offer():
    html = _ld({"@graph": [{"@type": "WebSite"}, {"@type": "Product", "name": "W", "offers": {
        "@type": "AggregateOffer", "lowPrice": "12.50", "highPrice": "20", "priceCurrency": "USD"}}]})
    found = extract.find_jsonld_product(html)
    assert found["price"] == 12.5 and found["availability"] is None


def test_jsonld_skips_product_without_offers_and_bad_json():
    html = ('<script type="application/ld+json">{oops</script>'
            + _ld({"@type": "Product", "name": "NoOffer"}))
    assert extract.find_jsonld_product(html) is None


OG = ('<meta property="og:title" content="Gadget"><meta property="product:price:amount" content="$1,099.00">'
      '<meta property="product:price:currency" content="USD">')


def test_og_price():
    assert extract.og_price(OG)["price"] == 1099.0
    assert extract.og_price(OG)["title"] == "Gadget"
    assert extract.og_price("<html></html>") is None


async def test_extract_uses_jsonld(mock_http):
    html = _ld({"@type": "Product", "name": "W", "offers": {"price": "3", "priceCurrency": "USD"}})
    mock_http(lambda r: httpx.Response(200, text=html))
    out = await extract.extract_product("https://example.com/item")
    assert out["sources_checked"] == ["jsonld"] and out["data"]["merchant"] == "example.com"


async def test_extract_og_fallback(mock_http):
    mock_http(lambda r: httpx.Response(200, text=OG))
    out = await extract.extract_product("https://example.com/item")
    assert out["sources_checked"] == ["opengraph"] and out["data"]["price"] == 1099.0


async def test_extract_carries_shopify_skip(mock_http):
    def handler(request):
        if request.url.path.endswith(".json"):
            return httpx.Response(404)
        return httpx.Response(200, text=OG)
    mock_http(handler)
    out = await extract.extract_product("https://example.com/products/widget")
    assert out["sources_checked"] == ["opengraph"]
    assert out["sources_skipped"] == [{"name": "shopify", "reason": "not_shopify"}]


async def test_extract_falls_through_to_playwright(mock_http, monkeypatch):
    async def stub(url):
        return {"data": {"title": "T", "price": 1.0}, "sources_checked": ["jsonld:playwright"], "sources_skipped": []}
    monkeypatch.setattr(extract, "playwright_extract", stub)
    mock_http(lambda r: httpx.Response(200, text="<html></html>"))
    out = await extract.extract_product("https://example.com/item")
    assert out["sources_checked"] == ["jsonld:playwright"]


async def test_extract_blocked_page_and_playwright_miss(mock_http, monkeypatch):
    async def stub(url):
        return {"data": None, "sources_checked": [], "sources_skipped": [{"name": "playwright", "reason": "no_results"}]}
    monkeypatch.setattr(extract, "playwright_extract", stub)
    mock_http(lambda r: httpx.Response(403))
    out = await extract.extract_product("https://example.com/item")
    assert out["data"] is None
    assert [s["reason"] for s in out["sources_skipped"]] == ["blocked", "no_results"]
