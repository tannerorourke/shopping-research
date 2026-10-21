"""
Universal product-page extractor: title, price, currency, availability.

Tries, in order, the Shopify JSON endpoint, JSON-LD Product markup, OpenGraph
price tags, then a stealth headless Chromium render for JS-built pages. Each
stage costs more than the last, so the first hit wins. Called by the
product-lookup tool as extract_product(url).
"""
import json
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from . import http, shopify
from .envelope import envelope, skip, skipped


async def fetch_html(url: str) -> dict:
    try:
        r = await http.polite_get(url)
    except httpx.TimeoutException:
        return skipped("page", "timeout")
    if r.status_code in http.BLOCKED_STATUSES:
        return skipped("page", "blocked")
    return envelope(r.text, checked=["page"])


def _nodes(blob):
    if isinstance(blob, list):
        for item in blob:
            yield from _nodes(item)
    elif isinstance(blob, dict):
        yield blob
        yield from _nodes(blob.get("@graph", []))


def _has_type(node: dict, name: str) -> bool:
    t = node.get("@type")
    return t == name or (isinstance(t, list) and name in t)


def _offer(offers):
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    price = offers.get("lowPrice") if _has_type(offers, "AggregateOffer") else offers.get("price")
    return offers, price


def find_jsonld_product(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            blob = json.loads(tag.string or "")
        except json.JSONDecodeError:
            continue
        for node in _nodes(blob):
            if not _has_type(node, "Product") or not node.get("offers"):
                continue
            offers, price = _offer(node["offers"])
            availability = offers.get("availability")
            return {
                "title": node.get("name"),
                "price": http.money(price),
                "currency": offers.get("priceCurrency"),
                "availability": availability.rstrip("/").rsplit("/", 1)[-1] if availability else None,
                "merchant": None,
            }
    return None


def og_price(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return tag["content"]
        return None

    amount = meta("product:price:amount", "og:price:amount")
    if amount is None:
        return None
    return {
        "title": meta("og:title"),
        "price": http.money(amount),
        "currency": meta("product:price:currency", "og:price:currency"),
        "availability": None,
        "merchant": None,
    }


def _parse(html: str, url: str, suffix: str = "") -> dict | None:
    host = urlparse(url).netloc
    for name, finder in (("jsonld", find_jsonld_product), ("opengraph", og_price)):
        found = finder(html)
        if found:
            return envelope({**found, "merchant": host, "url": url}, checked=[name + suffix])
    return None


async def playwright_extract(url: str) -> dict:
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(channel="chromium", headless=True)
            page = await browser.new_page()
            await Stealth().apply_stealth_async(page)
            await page.goto(url, wait_until="domcontentloaded")
            html = await page.content()
            await browser.close()
    except PlaywrightError:
        return skipped("playwright", "blocked")
    return _parse(html, url, ":playwright") or skipped("playwright", "no_results")


async def extract_product(url: str) -> dict:
    skips = []
    if shopify.is_shopify(url):
        found = await shopify.lookup(url)
        if found["data"]:
            return found
        skips += found["sources_skipped"]
    page = await fetch_html(url)
    skips += page["sources_skipped"]
    found = _parse(page["data"], url) if page["data"] else None
    if found is None:
        found = await playwright_extract(url)
        if found["data"] is None:
            return envelope(None, checked=[], skipped=skips + found["sources_skipped"])
    return envelope(found["data"], found["sources_checked"], skips)
