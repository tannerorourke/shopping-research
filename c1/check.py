"""
c1_check(url): optional cross-check against the Capital One Shopping extension.
Opens one product page read-only in a persistent Chromium profile, waits for
the extension's price-comparison response, and returns the offers in the shared
envelope. Disabled by default; a disabled or unsupported call returns a
deterministic skip rather than raising. The server registers it as a tool.
"""
import asyncio
import time
from urllib.parse import urlparse

from c1 import settings as c1_settings
from c1.context import C1Browser
from c1.parsers import parse_c1_offers, parse_c1_panel
from sources.envelope import envelope, skipped

_browser: C1Browser | None = None


def _skip(reason: str) -> dict:
    return skipped("c1_shopping", reason)


async def c1_check(url: str) -> dict:
    global _browser
    s = c1_settings.load()
    if not s.enabled:
        return _skip("disabled_in_settings")
    host = urlparse(url).netloc.removeprefix("www.")
    if not any(host == r or host.endswith("." + r) for r in s.retailers):
        return _skip("retailer_unsupported")
    _browser = _browser or C1Browser(s)
    if _browser._calls >= s.max_calls_per_session:
        return _skip("quota_exhausted")
    ctx = await _browser.context()
    page = await ctx.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded")
        offers, status = await _wait_for_c1(page, s)
    except TimeoutError:
        return _skip("timeout")
    finally:
        await page.close()
    _browser._calls += 1
    if status == 401:
        return _skip("auth_error")  # -- session expired; user re-logs in the profile
    if not offers:
        return envelope({"offers": []}, checked=["c1_shopping"])
    best = min(offers, key=lambda o: o["price"])
    return envelope({"c1_best": best, "offers": offers}, checked=["c1_shopping"])


async def _wait_for_c1(page, s):
    deadline = time.time() + s.timeout_ms / 1000
    while time.time() < deadline:
        for h in await _browser.hits():
            if s.api_url_filter and s.api_url_filter in h["url"]:
                return parse_c1_offers(h["data"]), h["status"]
        await asyncio.sleep(0.5)
    panel = await page.query_selector("[data-c1-panel], [id^='c1'], [class*='capitalone']")
    if panel:
        return parse_c1_panel(await panel.inner_text()), 200
    raise TimeoutError


async def shutdown() -> None:
    global _browser
    if _browser is not None:
        await _browser.close()
        _browser = None


def calls_used() -> int:
    return _browser._calls if _browser else 0
