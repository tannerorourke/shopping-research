"""
Slickdeals: community-voted deals from the public RSS feed.

Surfaces deals that price comparison misses. Called by the deals tool with an
optional query or category; the front-page feed is used when neither is given.
"""
import re
from urllib.parse import quote_plus

import feedparser
import httpx

from . import http
from .envelope import envelope, skipped

FRONTPAGE = "https://slickdeals.net/newsearch.php?mode=frontpage&searcharea=deals&searchin=first&rss=1"
SEARCH = "https://slickdeals.net/newsearch.php?rss=1&q={q}"
STORE = re.compile(r"\s(?:at|@|from)\s+(.+?)\s*$", re.IGNORECASE)
# -- the feed opens each description with '<Store> has <item> for $x'; the title rarely names the store
STORE_LEAD = re.compile(r"^\s*(.+?)\s+has\s", re.IGNORECASE)
VOTES = re.compile(r"(?:thumb score:?\s*([+-]?\d+)|(\d+)\s*(?:thumbs? up|votes?)|(?:thumbs? up|votes?)\D{0,3}(\d+)|\+(\d+))", re.IGNORECASE)
DOLLARS = re.compile(r"\$\s*[\d,]+(?:\.\d+)?")


def _entry(e) -> dict:
    title = e.get("title", "")
    price = DOLLARS.search(title)
    summary = e.get("summary", "")
    store = STORE_LEAD.search(summary) or STORE.search(title)
    # -- the vote count sits in content:encoded as 'Thumb Score: +N'; the summary is the fallback
    body = " ".join(c.get("value", "") for c in e.get("content", [])) + " " + summary
    votes = VOTES.search(body)
    return {
        "title": title,
        "price": http.money(price.group(0)) if price else None,
        "store": store.group(1) if store else None,
        "url": e.get("link"),
        "votes": int(next(g for g in votes.groups() if g)) if votes else None,
        "published": e.get("published"),
    }


async def get_deals(query: str | None = None, category: str | None = None, num: int = 15) -> dict:
    query = query or category
    url = SEARCH.format(q=quote_plus(query)) if query else FRONTPAGE
    try:
        async with http.client() as c:
            r = await c.get(url)
    except httpx.TimeoutException:
        return skipped("slickdeals", "timeout", data=[])
    if r.status_code in http.BLOCKED_STATUSES:
        return skipped("slickdeals", "blocked", data=[])
    deals = [_entry(e) for e in feedparser.parse(r.text).entries[:num]]
    if not deals:
        return skipped("slickdeals", "no_results", data=[])
    return envelope(deals, checked=["slickdeals"])
