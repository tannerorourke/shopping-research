"""
Settings for the server: one settings.toml, loaded at start and on reload_settings().

Resolution order per field: a non-empty environment variable, then settings.toml,
then the dataclass default. An empty env value is unset, so an unfilled plugin
option never blanks a key the file holds. The file path is $BEST_PRICE_SETTINGS or settings.toml beside
this module, so the server resolves the same file whatever directory the MCP
client launches it from. Secrets stay in settings.toml (git-ignored) or the env.
"""
import os
import pathlib
import tomllib
from dataclasses import dataclass, field, fields

ROOT = pathlib.Path(__file__).resolve().parent
STATE_DIR = pathlib.Path(os.environ.get("BEST_PRICE_STATE", "~/.best-price")).expanduser()


@dataclass(frozen=True)
class SerpApiSettings:
    api_key: str = ""
    monthly_budget: int = 250
    cache_ttl_hours: int = 24


@dataclass(frozen=True)
class EbaySettings:
    client_id: str = ""
    client_secret: str = ""


@dataclass(frozen=True)
class BestBuySettings:
    api_key: str = ""


@dataclass(frozen=True)
class TargetSettings:
    enabled: bool = True


@dataclass(frozen=True)
class C1Settings:
    enabled: bool = False
    profile_dir: str = "~/.best-price/chrome-profile"
    extension_dir: str = "extensions/c1shopping-unpacked"
    headless: bool = True
    max_calls_per_session: int = 2
    idle_close_seconds: int = 120
    timeout_ms: int = 10000
    retailers: tuple[str, ...] = ("amazon.com",)
    api_url_filter: str = ""


@dataclass(frozen=True)
class Settings:
    serpapi: SerpApiSettings = field(default_factory=SerpApiSettings)
    ebay: EbaySettings = field(default_factory=EbaySettings)
    bestbuy: BestBuySettings = field(default_factory=BestBuySettings)
    target: TargetSettings = field(default_factory=TargetSettings)
    c1: C1Settings = field(default_factory=C1Settings)


# -- (section, field) -> env var; the env wins over the file
ENV_OVERRIDES = {
    ("serpapi", "api_key"): "SERPAPI_KEY",
    ("serpapi", "monthly_budget"): "SERPAPI_MONTHLY_BUDGET",
    ("target", "enabled"): "TARGET_ENABLED",
    ("ebay", "client_id"): "EBAY_CLIENT_ID",
    ("ebay", "client_secret"): "EBAY_CLIENT_SECRET",
    ("bestbuy", "api_key"): "BESTBUY_API_KEY",
    ("c1", "enabled"): "C1_CHECK_ENABLED",
}

_SECTION_TYPES = {f.name: f.type for f in fields(Settings)}


def settings_path() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BEST_PRICE_SETTINGS", ROOT / "settings.toml")).expanduser()


def _coerce(value: str, target_type: type):
    if target_type is bool:
        return value.strip().lower() in ("1", "true", "yes")
    if target_type is int:
        return int(float(value))
    return target_type(value)


def load(path: pathlib.Path | None = None) -> Settings:
    p = path or settings_path()
    raw = tomllib.loads(p.read_text()) if p.exists() else {}
    sections = {}
    for name, cls in _SECTION_TYPES.items():
        cfg = {k: v for k, v in raw.get(name, {}).items() if k in {f.name for f in fields(cls)}}
        if "retailers" in cfg:
            cfg["retailers"] = tuple(cfg["retailers"])
        for (section, key), var in ENV_OVERRIDES.items():
            if section == name and os.environ.get(var, "") != "":
                cfg[key] = _coerce(os.environ[var], next(f.type for f in fields(cls) if f.name == key))
        sections[name] = cls(**cfg)
    return Settings(**sections)


_current: Settings | None = None


def current() -> Settings:
    global _current
    if _current is None:
        _current = load()
    return _current


def reload() -> Settings:
    global _current
    _current = load()
    return _current
