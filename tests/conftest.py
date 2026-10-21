"""
Test harness. Every test runs against an empty temp state dir and a settings file
that does not exist, so a developer's real settings.toml and budget never leak in.
'mock_http' swaps the shared client for one backed by httpx.MockTransport.
"""
import os
import tempfile

_STATE = tempfile.mkdtemp(prefix="bp-test-")
os.environ["BEST_PRICE_STATE"] = _STATE
os.environ["BEST_PRICE_SETTINGS"] = os.path.join(_STATE, "none.toml")
for _var in ("SERPAPI_KEY", "EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET", "BESTBUY_API_KEY", "C1_CHECK_ENABLED"):
    os.environ.pop(_var, None)

import httpx
import pytest

import settings as settings_mod
from sources import http


@pytest.fixture
def mock_http(monkeypatch):
    """mock_http(handler) routes every sources.http.client() request to handler(request) -> Response."""
    def install(handler):
        def client(timeout: float = 20):
            return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
        monkeypatch.setattr(http, "client", client)
    return install


@pytest.fixture
def toml_settings(monkeypatch, tmp_path):
    """toml_settings(text) writes a settings.toml, reloads settings, and resets the SerpApi budget."""
    def install(text: str):
        p = tmp_path / "settings.toml"
        p.write_text(text)
        monkeypatch.setenv("BEST_PRICE_SETTINGS", str(p))
        settings_mod.reload()
        from sources.budget import serpapi_budget
        serpapi_budget.path.unlink(missing_ok=True)
        serpapi_budget.reload()
        return settings_mod.current()
    return install
