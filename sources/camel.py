"""
CamelCamelCamel: Amazon price history (lowest, highest, average, current).

Gives the "is this a good price" verdict that Google Shopping cannot. Called by
the price-history tool with an ASIN taken from an Amazon URL.
"""
# -- page structure written from memory; needs one live confirmation. CCC sits
# behind Cloudflare, so one request per call and no retry.
import re

import httpx
from bs4 import BeautifulSoup

from . import http
from .envelope import envelope, skipped

ASIN = re.compile(r"^[A-Z0-9]{10}$")
ASIN_IN_URL = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?#]|$)")
LABELS = ("lowest", "highest", "average", "current")
DOLLARS = re.compile(r"\$\s*[\d,]+(?:\.\d+)?")


def asin_from_url(url_or_asin: str) -> str | None:
    if ASIN.match(url_or_asin):
        return url_or_asin
    m = ASIN_IN_URL.search(url_or_asin)
    return m.group(1) if m else None


def parse_ccc(html: str) -> dict | None:
    found = {}
    for row in BeautifulSoup(html, "html.parser").find_all("tr"):
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True).lower()
        for name in LABELS:
            if label.startswith(name) and name not in found:
                m = DOLLARS.search(" ".join(c.get_text(" ", strip=True) for c in cells[1:]))
                found[name] = http.money(m.group(0)) if m else None
    return {name: found.get(name) for name in LABELS} if found else None


def verdict(hist: dict) -> str:
    current, lowest, average = hist["current"], hist["lowest"], hist["average"]
    if current <= lowest * 1.03:
        return "at/near all-time low"
    if current > average * 1.10:
        return "above average; consider waiting"
    if current < average:
        return "below average"
    return "around average"


async def get_price_history(asin: str | None) -> dict:
    if asin is None:
        return skipped("camelcamelcamel", "not_amazon")
    try:
        r = await http.polite_get(f"https://camelcamelcamel.com/product/{asin}")
    except httpx.TimeoutException:
        return skipped("camelcamelcamel", "timeout")
    if r.status_code in http.BLOCKED_STATUSES:
        return skipped("camelcamelcamel", "blocked")
    hist = parse_ccc(r.text)
    if hist is None or None in hist.values():
        return skipped("camelcamelcamel", "no_results")
    return envelope({**hist, "verdict": verdict(hist)}, checked=["camelcamelcamel"])
