"""Every Claude model the site calls, in one table.

Audit 2026-09-30, C-5 (roadmap #35). Twenty-six model-name literals were
spread over askbot.py and hypotheses.py, each list deciding one thing —
which models take an effort setting, which get the server-side refusal
fallback, which get the newer web-search tool, what a token costs — and
the runtime defaults were bare names that age. A model added to one list
and not the others was half-supported without anything saying so, and a
model in none of them priced at nothing, which switched Ask's daily
dollar cap off (C-4).

One row per model now. A dated snapshot id the API serves back
("claude-sonnet-5-20260115") resolves to its family row by prefix, so the
usage log can price what was SERVED rather than what was asked for. A
model in no row is priced at the dearest listed rate — an estimate that
errs toward stopping, never toward a free ride past the cap.
"""

from __future__ import annotations

#: $ per million tokens (input, output) and what each model supports.
#: effort      — takes `output_config.effort` (Ask runs it at "low")
#: web_dynamic — takes the web-search version that filters in code
#: fallback    — gets the server-side refusal fallback to FALLBACK_TO
MODELS = {
    "claude-fable-5-1": {"price": (10.0, 50.0), "effort": True, "web_dynamic": True, "fallback": True},
    # No published rate on file: priced at UNLISTED_PRICE, the dearest.
    "claude-fable-5":   {"effort": True, "web_dynamic": True},
    "claude-opus-5-5":  {"price": (4.0, 20.0), "effort": True, "web_dynamic": True},
    "claude-opus-5":    {"price": (5.0, 25.0), "effort": True, "web_dynamic": True, "fallback": True},
    "claude-sonnet-5":  {"price": (2.0, 10.0), "effort": True, "web_dynamic": True},
    "claude-opus-4-8":  {"price": (5.0, 25.0), "effort": True, "web_dynamic": True},
    "claude-opus-4-7":  {"price": (5.0, 25.0), "effort": True, "web_dynamic": True},
    "claude-opus-4-6":  {"price": (5.0, 25.0), "web_dynamic": True},
    "claude-sonnet-4-6": {"price": (3.0, 15.0), "web_dynamic": True},
    "claude-haiku-4-5": {"price": (1.0, 5.0)},
}

#: Names a setting can use instead of an id, so a default is one line.
ALIASES = {
    "ask": "claude-sonnet-5",        # Ask: fast, cheap, good enough
    "lab": "claude-opus-5",          # hypothesis lab and nightly prose
    "latest": "claude-opus-5-5",
}

#: Where a refused request is retried, server-side.
FALLBACK_TO = "claude-opus-4-8"
FALLBACK_BETA = "server-side-fallback-2026-06-01"

#: An unknown model is priced at the dearest listed rate (see module doc).
UNLISTED_PRICE = max((m["price"] for m in MODELS.values() if "price" in m),
                     key=lambda p: p[0] + p[1])


def resolve(name: str | None) -> str:
    """An alias to its id; an id (or an unknown name) unchanged."""
    n = str(name or "").strip()
    return ALIASES.get(n, n)


def row(model: str | None) -> dict | None:
    """The table row for an id or a dated snapshot of one; None if unknown.
    The longest matching family wins, so "claude-opus-5-5-…" is never read
    as "claude-opus-5"."""
    m = resolve(model)
    if m in MODELS:
        return MODELS[m]
    best = ""
    for fam in MODELS:
        if m.startswith(fam + "-") and len(fam) > len(best):
            best = fam
    return MODELS.get(best)


def price(model: str | None) -> tuple:
    """(input, output) $ per million tokens."""
    return (row(model) or {}).get("price") or UNLISTED_PRICE


def priced(model: str | None) -> bool:
    """Is there a published rate on file, rather than the conservative one?"""
    return bool((row(model) or {}).get("price"))


def takes_effort(model: str | None) -> bool:
    return bool((row(model) or {}).get("effort"))


def web_dynamic(model: str | None) -> bool:
    return bool((row(model) or {}).get("web_dynamic"))


def gets_fallback(model: str | None) -> bool:
    return bool((row(model) or {}).get("fallback"))
