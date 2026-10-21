import httpx

from sources import slickdeals

FEED = """<?xml version="1.0"?><rss version="2.0"><channel><title>t</title>
<item><title>Sony WH-1000XM5 Headphones $248 at Amazon</title><link>https://slickdeals.net/f/1</link>
<description>Popular deal, 42 votes</description><pubDate>Mon, 19 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Free shipping on everything</title><link>https://slickdeals.net/f/2</link>
<description>+17 thumbs</description></item>
</channel></rss>"""


async def test_parses_price_store_votes(mock_http):
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=FEED)
    mock_http(handler)
    out = await slickdeals.get_deals(query="headphones")
    assert "q=headphones" in seen[0]
    first, second = out["data"]
    assert (first["price"], first["store"], first["votes"]) == (248.0, "Amazon", 42)
    assert first["url"] == "https://slickdeals.net/f/1"
    assert (second["price"], second["store"], second["votes"]) == (None, None, 17)
    assert out["sources_checked"] == ["slickdeals"]


async def test_frontpage_without_query(mock_http):
    seen = []
    mock_http(lambda r: seen.append(str(r.url)) or httpx.Response(200, text=FEED))
    await slickdeals.get_deals(num=1)
    assert "mode=frontpage" in seen[0]


async def test_category_becomes_query(mock_http):
    seen = []
    mock_http(lambda r: seen.append(str(r.url)) or httpx.Response(200, text=FEED))
    await slickdeals.get_deals(category="laptops")
    assert "q=laptops" in seen[0]


async def test_no_entries_and_blocked(mock_http):
    mock_http(lambda r: httpx.Response(200, text='<rss version="2.0"><channel></channel></rss>'))
    assert (await slickdeals.get_deals())["sources_skipped"][0]["reason"] == "no_results"
    mock_http(lambda r: httpx.Response(403))
    assert (await slickdeals.get_deals())["sources_skipped"][0]["reason"] == "blocked"


async def test_live_feed_shape_store_in_description_votes_in_content(mock_http):
    xml = """<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel><item>
<title>Pelican Marine Case for AirPods Pro - $9.99 + FS</title><link>https://slickdeals.net/f/1</link>
<description>Best Buy has *Pelican Marine Case for $9.99 + Free Shipping*</description>
<content:encoded><![CDATA[<div>Thumb Score: +3 </div><div>Best Buy has <b>Pelican</b></div>]]></content:encoded>
</item></channel></rss>"""
    mock_http(lambda r: httpx.Response(200, text=xml))
    out = await slickdeals.get_deals("airpods")
    d = out["data"][0]
    assert (d["price"], d["store"], d["votes"]) == (9.99, "Best Buy", 3)
