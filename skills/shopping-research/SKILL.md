---
name: shopping-research
description: Find products, compare prices across retailers, check Amazon price history and community deals, and recommend buy or wait, through the shopping-research MCP server. Use when the user asks to look for deals, find options for a product or category, compare products, find the best price, asks "is this a good deal" or "should I buy this now", pastes a product URL, or mentions buying or considering a specific product. Do not use for items that cannot be purchased.
---

# Shopping research

Every tool on the `shopping-research` MCP server returns `{data, sources_checked, sources_skipped}`. The report you write ends on a `Not checked:` line built from the union of every `sources_skipped` entry in the run. "Best price" means the lowest price among the sources checked, and the report says so in those words.

## Tools

| Tool | Call | `data` |
| --- | --- | --- |
| `search_products` | `(query, num=10)` | `[{title, price, merchant, url, product_id}]` ascending by price |
| `compare_prices` | `(product_id \| None, query \| None)` | `[{merchant, price, url}]` ascending |
| `extract_product` | `(url)` | `{title, price, currency, availability, merchant}` |
| `get_price_history` | `(asin \| amazon URL \| None)` | `{lowest, highest, average, current, verdict}` or `None` |
| `get_deals` | `(query \| None, category \| None)` | `[{title, price, store, url, votes}]` |
| `c1_check` | `(url)` | `{c1_best, offers}` or `None`; settings-gated, off by default |
| `get_status` | `()` | configured sources, SerpApi searches remaining, C1 state |
| `reload_settings` | `()` | status after re-reading `settings.toml` |

## Known limitations, read on every invocation

- Price history is Amazon-only. No source exists for Walmart, Target, Best Buy, or direct-to-consumer history. For a non-Amazon product, history is unknown. Never describe it as flat or stable.
- Coupons are not searched. `c1_check`, when enabled, may return coupon-adjusted prices for finalists; that is the only coupon signal. Never say "no coupons exist".
- Search coverage is finite: SerpApi Google Shopping, eBay, Best Buy, Target, Shopify stores, and page extraction. A retailer absent from results is unchecked, never more expensive.
- SerpApi is quota-limited to 250 searches a month. Call `get_status` first when quota matters. Past quota, comparison degrades to the retailer APIs plus `extract_product`.
- `c1_check` is optional and off by default. When `sources_skipped` says `disabled_in_settings`, report it as not checked; suggest enabling it only when the user asks about coupons.
- Deals are US-only (Slickdeals).

## Workflow

Step 0, classify the result shape before any search: (a) specific product(s) already named, skip to deal finding; (b) head-to-head comparison ("X vs Y"); (c) filtered options ("under $400, must have Z"); (d) ranking ("best 3 for ..."); (e) open brainstorm. Ask at most one clarifying question, only when the shape is genuinely ambiguous.

Step 1, find the product(s): `search_products`, plus `extract_product` for any pasted URL. Output a shortlist of concrete SKUs with retailer URLs.

Step 2, compare and suggest, in the shape chosen in Step 0. Recommend an alternative only when there is a clear better option or a tradeoff worth naming, or when the user asks.

Step 3, find deals, after the finalist(s) are chosen unless the user asked for deals up front. Order: `compare_prices`, then `get_price_history` when the finalist has an ASIN or amazon URL, then `get_deals`, then `c1_check` on finalists only when enabled and the retailer is supported. Never run the deal tools across the whole shortlist; quota and rate limits are per call.

Step 4, report coverage: union every `sources_checked` and `sources_skipped` from the run and write the `Not checked:` line.

## Output contract

- Lowest price among sources checked: retailer, price, URL.
- C1 cross-check result only when it beat the above: retailer, price, whether coupon-adjusted.
- Price-history verdict for Amazon, or "history: not available (non-Amazon)".
- Community-deal signal when relevant: Slickdeals title and votes.
- One-sentence buy or wait recommendation.
- `Not checked:`, mandatory. Map skip reasons to plain text, for example `Not checked: price history (non-Amazon), C1 Shopping (disabled), Target (blocked)`. When nothing was skipped, write `Not checked: none`.

## Skip reasons and what to do

| `sources_skipped` reason | Behavior |
| --- | --- |
| SerpApi `quota_exhausted` | Use eBay, Best Buy, Target, and `extract_product` on candidate URLs; note reduced coverage. |
| SerpApi `disabled_in_settings` | No API key configured; same fallback, and tell the user once. |
| eBay `auth_error` | The server already refreshed the token and retried once. Skip eBay and note it. |
| CamelCamelCamel `blocked` | Current price only; `Not checked: price history (CCC unavailable)`. |
| `not_amazon` on history | Write "history: not available (non-Amazon)". State it, never infer. |
| Target `blocked` | Drop Target, continue. |
| `c1_check` `disabled_in_settings` | List under `Not checked:`; do not retry. |
| `c1_check` `retailer_unsupported` | Skip silently; list under `Not checked:`. |
| `c1_check` `auth_error` | Tell the user to sign into Capital One Shopping in the tool's Chrome profile; do not retry this run. |
| `c1_check` `timeout` | Skip; list under `Not checked:`; do not retry this run. |
| `c1_check` `quota_exhausted` | Finalist cap reached; no further calls this session. |
| any `no_results` | The source answered with nothing; it counts as checked, not skipped, in the `Not checked:` line. |
