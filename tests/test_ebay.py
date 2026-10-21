import httpx
import pytest

import settings
from auth import tokens
from sources import ebay

CREDS = '[ebay]\nclient_id = "id"\nclient_secret = "secret"\n'


@pytest.fixture(autouse=True)
def fresh_token_state(monkeypatch, tmp_path):
    monkeypatch.setattr(tokens, "_cache", None)
    monkeypatch.setattr(settings, "STATE_DIR", tmp_path / "state")


def _router(counts, search_status=200, body=None):
    def handler(request):
        if request.url.host == "api.ebay.com" and "oauth2" in request.url.path:
            counts["token"] += 1
            return httpx.Response(200, json={"access_token": f"t{counts['token']}", "expires_in": 7200})
        counts["search"] += 1
        if search_status != 200:
            return httpx.Response(search_status)
        return httpx.Response(200, json=body if body is not None else {"itemSummaries": [
            {"title": "Widget", "price": {"value": "19.99", "currency": "USD"},
             "itemWebUrl": "https://ebay/1", "itemId": "v1|1|0", "condition": "New"}]})
    return handler


async def test_blank_credentials_disabled():
    out = await ebay.search("widget")
    assert out["data"] == [] and out["sources_skipped"] == [{"name": "ebay", "reason": "disabled_in_settings"}]


async def test_happy_path_maps_fields(mock_http, toml_settings):
    toml_settings(CREDS)
    counts = {"token": 0, "search": 0}
    mock_http(_router(counts))
    out = await ebay.search("widget")
    assert out["sources_checked"] == ["ebay"]
    assert out["data"] == [{"title": "Widget", "price": 19.99, "merchant": "ebay",
                            "url": "https://ebay/1", "product_id": "v1|1|0", "condition": "New"}]


async def test_401_refreshes_once_then_auth_error(mock_http, toml_settings):
    toml_settings(CREDS)
    counts = {"token": 0, "search": 0}
    mock_http(_router(counts, search_status=401))
    out = await ebay.search("widget")
    assert out["sources_skipped"][0]["reason"] == "auth_error"
    assert counts == {"token": 2, "search": 2}


async def test_blocked(mock_http, toml_settings):
    toml_settings(CREDS)
    mock_http(_router({"token": 0, "search": 0}, search_status=429))
    out = await ebay.search("widget")
    assert out["sources_skipped"][0]["reason"] == "blocked"


async def test_empty_is_no_results(mock_http, toml_settings):
    toml_settings(CREDS)
    mock_http(_router({"token": 0, "search": 0}, body={}))
    out = await ebay.search("widget")
    assert out["data"] == [] and out["sources_skipped"][0]["reason"] == "no_results"


async def test_token_persisted_across_searches(mock_http, toml_settings, monkeypatch):
    toml_settings(CREDS)
    counts = {"token": 0, "search": 0}
    mock_http(_router(counts))
    await ebay.search("widget")
    monkeypatch.setattr(tokens, "_cache", None)
    await ebay.search("widget")
    assert counts["token"] == 1 and counts["search"] == 2
