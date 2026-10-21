"""
Parsers that turn Capital One Shopping data into offers:
[{merchant, price, url, coupon_applied}].

Both parsers are placeholders until the endpoint payload and the panel text
are discovered once with `headless = false`; they cover common shapes only.
"""
import re

_LIST_KEYS = ("offers", "results", "comparisons", "prices")
_MERCHANT_KEYS = ("merchant", "retailer", "store", "name")
_PRICE_KEYS = ("price", "total", "finalPrice")
_URL_KEYS = ("url", "link")
_COUPON_KEYS = ("couponApplied", "coupon", "hasCoupon")
_AMOUNT = re.compile(r"\$\s*([\d,]+(?:\.\d+)?)")


def _first(d: dict, keys: tuple[str, ...]):
    return next((d[k] for k in keys if d.get(k) is not None), None)


def _to_price(v) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"[\d,]+(?:\.\d+)?", v)
        return float(m.group().replace(",", "")) if m else None
    return None


def parse_c1_offers(data) -> list[dict]:
    if isinstance(data, dict):
        data = next((data[k] for k in _LIST_KEYS if isinstance(data.get(k), list)), [])
    if not isinstance(data, list):
        return []
    offers = []
    for o in data:
        if not isinstance(o, dict):
            continue
        price = _to_price(_first(o, _PRICE_KEYS))
        if price is None:
            continue
        offers.append({
            "merchant": _first(o, _MERCHANT_KEYS),
            "price": price,
            "url": _first(o, _URL_KEYS),
            "coupon_applied": bool(_first(o, _COUPON_KEYS)),
        })
    return offers


def parse_c1_panel(text: str) -> list[dict]:
    offers = []
    for line in text.splitlines():
        m = _AMOUNT.search(line)
        if not m:
            continue
        merchant = line[:m.start()].strip(" :-\t")
        if not merchant:
            continue
        offers.append({
            "merchant": merchant,
            "price": float(m.group(1).replace(",", "")),
            "url": None,
            "coupon_applied": "coupon" in line.lower(),
        })
    return offers
