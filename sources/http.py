"""
Shared HTTP helpers: one browser-like client and a single polite GET.

Scraped sources (CamelCamelCamel, Target, product pages) get exactly one request
per call and no retry loop; a 403 or 503 is reported as 'blocked', never hammered.
"""
import httpx

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
BLOCKED_STATUSES = (401, 403, 429, 503)


def client(timeout: float = 20) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})


async def polite_get(url: str, **kwargs) -> httpx.Response:
    async with client() as c:
        return await c.get(url, **kwargs)


def money(value) -> float | None:
    """'$1,099.00' or 1099 -> 1099.0; anything unparseable -> None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else None
    except ValueError:
        return None


def reason_for(status: int) -> str:
    """Skip reason for a failed response: 401 is a credential problem, everything else is a block."""
    return "auth_error" if status == 401 else "blocked"
