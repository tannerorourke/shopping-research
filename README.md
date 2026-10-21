# shopping-research

A local MCP server that gives Claude Code live product search, cross-retailer prices, Amazon price history, community deals, and an optional Capital One Shopping cross-check, over free sources only. Every tool reports its own coverage: the response envelope is `{data, sources_checked, sources_skipped}`, so the calling skill can never claim a best price over a source it never saw.

## Setup

1. `uv sync` installs the environment (Python 3.12 or newer).
2. `cp settings.toml.example settings.toml` and fill the keys you have. Each key can also come from the environment variable named in the file. A blank key leaves that source registered and reported as `disabled_in_settings`.
3. `uv run playwright install chromium` enables the headless-browser fallback in `extract_product` and the optional `c1_check`.
4. Register the server. Project scope: the shipped `.mcp.json` runs `uv run server.py` from this directory. User scope, so the tools are available from any directory:

```bash
claude mcp add --scope user shopping-research -- uv run --directory /absolute/path/to/shopping-research server.py
```

5. Copy or symlink `.claude/skills/shopping-research/` into `~/.claude/skills/` to make the skill available outside this repository.

Pass condition: `get_status` from a Claude Code session returns `serpapi_remaining` and the configured flags.

## Sources

| Source | Provides | Free tier | Key |
| --- | --- | --- | --- |
| SerpApi `google_shopping` / `google_product` | cross-retailer search and per-merchant offers | 250 searches a month | `SERPAPI_KEY` |
| eBay Browse API | marketplace listings | 5,000 calls a day | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` |
| Best Buy Developer API | products, prices, availability | free key | `BESTBUY_API_KEY` |
| Target RedSky | price, availability | undocumented public key | none |
| Shopify `/products/<handle>.json`, schema.org JSON-LD, OpenGraph, Playwright | any product page | none | none |
| CamelCamelCamel | Amazon price history | polite scrape, one request | none |
| Slickdeals RSS | community deals (US) | hourly feed | none |
| Capital One Shopping extension via Playwright | coupon-adjusted cross-check on finalists | free account, off by default | sign in once in the profile |

The SerpApi monthly counter and cache persist in `~/.best-price/` (override with `BEST_PRICE_STATE`). The server refuses SerpApi calls past `monthly_budget`.

## Tools

`search_products`, `compare_prices`, `extract_product`, `get_price_history`, `get_deals`, `c1_check`, `get_status`, `reload_settings`. Signatures and the skip-reason vocabulary are documented in `.claude/skills/shopping-research/SKILL.md`; the vocabulary itself is `sources/envelope.py`.

## Enabling the C1 cross-check

1. Unpack the Capital One Shopping extension into `extensions/c1shopping-unpacked/` (an unpacked directory, never a `.crx`).
2. Set `[c1] enabled = true` and `headless = false` in `settings.toml`, run `reload_settings`, call `c1_check` on an Amazon product URL, and sign in when the extension asks.
3. In `chrome://extensions`, open the extension's service worker and read the price-comparison endpoint from its Network tab. Write a unique substring of it into `api_url_filter`.
4. Set `headless = true` and `reload_settings`. `c1/parsers.py` is written against the common payload shapes; adjust it once if the endpoint's shape differs.

## Tests

`uv run pytest -q`. The suite uses `httpx.MockTransport` and launches no browser.
