import httpx

from sources import camel

TABLE = """<table class="camelegend"><tr><th></th><th>Amazon</th><th>3rd Party</th></tr>
<tr><td>Highest *</td><td>$129.99 <small>Jan 1</small></td><td>$140.00</td></tr>
<tr><td>Lowest *</td><td>$79.00</td><td>$70.00</td></tr>
<tr><td>Current</td><td>$99.00</td><td>$95.00</td></tr>
<tr><td>Average</td><td>$100.00</td><td>$98.00</td></tr></table>"""


def test_asin_forms():
    assert camel.asin_from_url("B08N5WRWNW") == "B08N5WRWNW"
    assert camel.asin_from_url("https://www.amazon.com/Some-Title/dp/B08N5WRWNW/ref=x?th=1") == "B08N5WRWNW"
    assert camel.asin_from_url("https://www.amazon.com/gp/product/B08N5WRWNW") == "B08N5WRWNW"
    assert camel.asin_from_url("https://www.target.com/p/thing") is None


def test_parse_table():
    assert camel.parse_ccc(TABLE) == {"lowest": 79.0, "highest": 129.99, "average": 100.0, "current": 99.0}
    assert camel.parse_ccc("<html></html>") is None


def test_verdict_branches():
    base = {"lowest": 100.0, "average": 150.0}
    assert camel.verdict({**base, "current": 102}) == "at/near all-time low"
    assert camel.verdict({**base, "current": 170}) == "above average; consider waiting"
    assert camel.verdict({**base, "current": 130}) == "below average"
    assert camel.verdict({**base, "current": 155}) == "around average"


async def test_not_amazon():
    assert (await camel.get_price_history(None))["sources_skipped"] == [{"name": "camelcamelcamel", "reason": "not_amazon"}]


async def test_history_with_verdict(mock_http):
    mock_http(lambda r: httpx.Response(200, text=TABLE))
    out = await camel.get_price_history("B08N5WRWNW")
    assert out["sources_checked"] == ["camelcamelcamel"]
    assert out["data"]["verdict"] == "below average" and out["data"]["current"] == 99.0


async def test_blocked_and_empty(mock_http):
    mock_http(lambda r: httpx.Response(403))
    assert (await camel.get_price_history("B08N5WRWNW"))["sources_skipped"][0]["reason"] == "blocked"
    mock_http(lambda r: httpx.Response(200, text="<html></html>"))
    assert (await camel.get_price_history("B08N5WRWNW"))["sources_skipped"][0]["reason"] == "no_results"
