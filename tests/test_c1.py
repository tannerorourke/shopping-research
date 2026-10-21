"""
Tests for the c1 cross-check. No browser is ever launched: check._browser is
replaced by fakes that mimic C1Browser's context() and hits() surface.
"""
import pytest

import settings
from c1 import check
from c1.parsers import parse_c1_offers, parse_c1_panel

AMAZON = "https://www.amazon.com/dp/B000TEST"
WALMART = "https://www.walmart.com/ip/123"
ENABLED = '[c1]\nenabled = true\nretailers = ["amazon.com"]\napi_url_filter = "/compare"\ntimeout_ms = 600\n'


class FakePage:
    def __init__(self, panel=None):
        self.panel, self.closed = panel, False

    async def goto(self, url, wait_until=None):
        pass

    async def query_selector(self, sel):
        return self.panel

    async def close(self):
        self.closed = True


class FakeCtx:
    def __init__(self, page):
        self.page = page

    async def new_page(self):
        return self.page


class FakeBrowser:
    def __init__(self, hits=(), calls=0, panel=None):
        self._hits, self._calls, self.page = list(hits), calls, FakePage(panel)
        self.context_called = False

    async def context(self):
        self.context_called = True
        return FakeCtx(self.page)

    async def hits(self):
        out, self._hits = self._hits, []
        return out


@pytest.fixture(autouse=True)
def reset_browser():
    check._browser = None
    yield
    check._browser = None


@pytest.fixture(autouse=True)
def _reload_after(monkeypatch):
    yield
    monkeypatch.undo()
    settings.reload()


async def test_disabled_by_default():
    assert await check.c1_check(AMAZON) == {
        "data": None, "sources_checked": [],
        "sources_skipped": [{"name": "c1_shopping", "reason": "disabled_in_settings"}],
    }


async def test_retailer_unsupported(toml_settings):
    toml_settings(ENABLED)
    r = await check.c1_check(WALMART)
    assert r["sources_skipped"][0]["reason"] == "retailer_unsupported"


async def test_env_overrides_file(toml_settings, monkeypatch):
    toml_settings(ENABLED)
    monkeypatch.setenv("C1_CHECK_ENABLED", "false")
    settings.reload()
    r = await check.c1_check(AMAZON)
    assert r["sources_skipped"][0]["reason"] == "disabled_in_settings"


async def test_quota_exhausted(toml_settings):
    toml_settings(ENABLED)
    fake = check._browser = FakeBrowser(calls=2)
    r = await check.c1_check(AMAZON)
    assert r["sources_skipped"][0]["reason"] == "quota_exhausted"
    assert not fake.context_called


async def test_best_offer(toml_settings):
    toml_settings(ENABLED)
    payload = [{"merchant": "Walmart", "price": "19.99"}, {"merchant": "Target", "price": 17.5}]
    fake = check._browser = FakeBrowser(hits=[{"url": "https://x/compare?id=1", "status": 200, "data": payload}])
    r = await check.c1_check(AMAZON)
    assert r["sources_checked"] == ["c1_shopping"]
    assert r["data"]["c1_best"]["merchant"] == "Target"
    assert len(r["data"]["offers"]) == 2
    assert fake.page.closed and fake._calls == 1


async def test_auth_error(toml_settings):
    toml_settings(ENABLED)
    check._browser = FakeBrowser(hits=[{"url": "https://x/compare", "status": 401, "data": None}])
    r = await check.c1_check(AMAZON)
    assert r["sources_skipped"][0]["reason"] == "auth_error"


async def test_timeout(toml_settings):
    toml_settings(ENABLED)
    fake = check._browser = FakeBrowser()
    r = await check.c1_check(AMAZON)
    assert r["sources_skipped"][0]["reason"] == "timeout"
    assert fake.page.closed


async def test_calls_used_and_shutdown():
    assert check.calls_used() == 0
    closed = []

    class B:
        _calls = 3

        async def close(self):
            closed.append(True)

    check._browser = B()
    assert check.calls_used() == 3
    await check.shutdown()
    assert closed and check._browser is None


def test_parse_list_payload():
    out = parse_c1_offers([
        {"retailer": "Walmart", "finalPrice": "$1,019.50", "link": "u", "hasCoupon": True},
        {"store": "Nope"},
    ])
    assert out == [{"merchant": "Walmart", "price": 1019.5, "url": "u", "coupon_applied": True}]


@pytest.mark.parametrize("key", ["offers", "results", "comparisons", "prices"])
def test_parse_dict_payload(key):
    out = parse_c1_offers({key: [{"name": "Target", "total": 5, "url": "t", "couponApplied": False}]})
    assert out == [{"merchant": "Target", "price": 5.0, "url": "t", "coupon_applied": False}]


def test_parse_garbage():
    assert parse_c1_offers(None) == []
    assert parse_c1_offers({"other": 1}) == []


def test_parse_panel():
    out = parse_c1_panel("Compare prices\nWalmart $19.99\nTarget $1,017.00 with coupon\n")
    assert out == [
        {"merchant": "Walmart", "price": 19.99, "url": None, "coupon_applied": False},
        {"merchant": "Target", "price": 1017.0, "url": None, "coupon_applied": True},
    ]
