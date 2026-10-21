import httpx
import pytest

import settings
from sources import target

NEW_KEY = "a" * 40
PRODUCTS = {"data": {"search": {"products": [
    {"tcin": "123", "item": {"product_description": {"title": "Widget"},
                             "enrichment": {"buy_url": "https://target/p/123"}},
     "price": {"current_retail": 7.99}},
    {"tcin": "456", "item": {"product_description": {"title": "Range"}, "enrichment": {"buy_url": "u"}},
     "price": {"current_retail_min": 3.5}}]}}}


@pytest.fixture(autouse=True)
def state_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STATE_DIR", tmp_path / "state")


async def test_disabled_in_settings(toml_settings):
    toml_settings("[target]\nenabled = false\n")
    out = await target.search("widget")
    assert out["data"] == [] and out["sources_skipped"] == [{"name": "target", "reason": "disabled_in_settings"}]


async def test_happy_path(mock_http, toml_settings):
    toml_settings("")
    seen = {}
    def handler(request):
        seen["params"] = request.url.params
        return httpx.Response(200, json=PRODUCTS)
    mock_http(handler)
    out = await target.search("widget", num=2)
    assert seen["params"]["key"] == target.DEFAULT_KEY and seen["params"]["keyword"] == "widget"
    assert out["sources_checked"] == ["target"]
    assert out["data"][0] == {"title": "Widget", "price": 7.99, "merchant": "target",
                              "url": "https://target/p/123", "product_id": "123"}
    assert out["data"][1]["price"] == 3.5


async def test_403_rescrapes_key_once_then_blocked(mock_http, toml_settings):
    toml_settings("")
    scrapes = []
    def handler(request):
        if request.url.host == "www.target.com":
            scrapes.append(1)
            return httpx.Response(200, text=f'<script>"apiKey":"{NEW_KEY}"</script>')
        return httpx.Response(403)
    mock_http(handler)
    out = await target.search("widget")
    assert out["sources_skipped"][0]["reason"] == "blocked" and len(scrapes) == 1
    assert (settings.STATE_DIR / "target_key.txt").read_text() == NEW_KEY


async def test_403_then_new_key_succeeds(mock_http, toml_settings):
    toml_settings("")
    def handler(request):
        if request.url.host == "www.target.com":
            return httpx.Response(200, text=f"x?key={NEW_KEY}&y")
        if request.url.params["key"] == NEW_KEY:
            return httpx.Response(200, json=PRODUCTS)
        return httpx.Response(403)
    mock_http(handler)
    out = await target.search("widget")
    assert out["sources_checked"] == ["target"]


async def test_empty_is_no_results(mock_http, toml_settings):
    toml_settings("")
    mock_http(lambda r: httpx.Response(200, json={"data": {"search": {"products": []}}}))
    out = await target.search("widget")
    assert out["data"] == [] and out["sources_skipped"][0]["reason"] == "no_results"
