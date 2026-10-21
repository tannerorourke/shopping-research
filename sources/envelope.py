"""
Response envelope shared by every tool: {data, sources_checked, sources_skipped}.

A tool never claims coverage it did not have. 'sources_checked' names the
sources whose answer is in 'data'; 'sources_skipped' names the ones that were
not consulted and why, drawn from the closed SKIP_REASONS vocabulary so the
calling skill can map each reason to user-facing text deterministically.
"""

SKIP_REASONS = frozenset({
    "disabled_in_settings", 
    "quota_exhausted", 
    "retailer_unsupported",
    "auth_error", 
    "blocked", 
    "timeout", 
    "not_amazon", 
    "not_shopify", 
    "no_results",
})


def skip(name: str, reason: str) -> dict:
    assert reason in SKIP_REASONS, f"unknown skip reason {reason!r}"
    return {"name": name, "reason": reason}


def envelope(data, checked: list[str], skipped: list[dict] | None = None) -> dict:
    return {
        "data": data, 
        "sources_checked": list(checked), 
        "sources_skipped": list(skipped or [])
    }


def skipped(name: str, reason: str, data=None) -> dict:
    return envelope(data, checked=[], skipped=[skip(name, reason)])


def merge(envelopes: list[dict], sort_key=None) -> dict:
    """Union list-valued envelopes: data concatenated, checked deduped in order, skips appended."""
    data, checked, skips = [], [], []
    for e in envelopes:
        data.extend(e["data"] or [])
        checked.extend(c for c in e["sources_checked"] if c not in checked)
        skips.extend(e["sources_skipped"])
    if sort_key:
        data.sort(key=sort_key)
    return envelope(data, checked, skips)
