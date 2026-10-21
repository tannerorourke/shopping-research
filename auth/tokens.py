"""
eBay application OAuth (client-credentials grant) with a persisted token.

Endpoint: POST https://api.ebay.com/identity/v1/oauth2/v2/token with HTTP Basic
(client_id:client_secret). Called by sources.ebay before each Browse request;
the token lives ~2h, so it is cached in memory and in STATE_DIR/ebay_token.json
and refreshed once it is within five minutes of expiry.
"""
import json
import time

import httpx

import settings
from sources import http

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/v2/token"
SCOPE = "https://api.ebay.com/oauth/api_scope"
REFRESH_MARGIN = 300

_cache: dict | None = None


def _path():
    return settings.STATE_DIR / "ebay_token.json"


def _fresh(tok: dict | None) -> bool:
    return bool(tok) and tok["expires_at"] - time.time() > REFRESH_MARGIN


async def get_ebay_token(force: bool = False) -> str | None:
    global _cache
    cfg = settings.current().ebay
    if not (cfg.client_id and cfg.client_secret):
        return None
    if not force:
        if _cache is None and _path().exists():
            _cache = json.loads(_path().read_text())
        if _fresh(_cache):
            return _cache["access_token"]
    try:
        async with http.client() as c:
            r = await c.post(TOKEN_URL, auth=(cfg.client_id, cfg.client_secret),
                             data={"grant_type": "client_credentials", "scope": SCOPE})
    except httpx.TimeoutException:
        return None
    if r.status_code != 200:
        return None
    body = r.json()
    _cache = {"access_token": body["access_token"], "expires_at": time.time() + body["expires_in"]}
    settings.STATE_DIR.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(_cache))
    return _cache["access_token"]
