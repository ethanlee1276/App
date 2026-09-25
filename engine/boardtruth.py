"""Does the published board say what its own data says? Checked every build.

Ethan, 2026-09-25, after two claims got to his phone before anything
caught them — a scan card calling Over 109.5 at +700 (4%) Ladd McConkey's
"likeliest over", and prices a board read an hour late still called
"priced 4m ago": "what's next so we can keep working and making sure all
that shit is good."

`engine/boardlint` is the human's audit — every row, every flag, run by
hand. This is the machine's: a short list of claims the page makes that
can be checked against the payload that makes them, run on every board
after every build (launch._note_board), counted into the heartbeat and
shown on the Status page. Each check is a sentence a reader would take at
its word:

  FLOOR        an unlocked Most Likely row under the 55% the board needs
  CAP          an unlocked Most Likely row heavier than −250
  OLD PRICE    an unlocked row whose price was past the freshness bar at
               the build and is not marked `price_stale`
  NO NOW       a locked pick with no word on today's price at its number
  LOCK NOTE    a locked pick's note naming a chance its tile does not show
  PICK MISSING a scan read that names its Most Likely pick, which is not on
               the board
  LONGSHOT     a no-pick card offering a "likeliest" number at under 20%
               and plus money — the McConkey sentence
  BARE MATE    a teammate-out line with no number in it
  DATA BEHIND  a week table behind the last week played (engine/freshness)

A problem is a question for a human, not a verdict; nothing here edits a
board. Standard library only.
"""
from __future__ import annotations

import re

#: A "likeliest" number under this, at plus money, is a longshot.
LONGSHOT_PROB = 0.20
#: How many problems the heartbeat carries per board (the count is whole).
KEEP = 8

_BARE_MATE = re.compile(r" is out — his (targets|carries) are open$")
_NOW_PCT = re.compile(r"now (\d+)%")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _who(r: dict) -> str:
    side = str(r.get("side") or "").lower()
    line = "" if r.get("line") is None else f" {r.get('line')}"
    return f"{r.get('player') or r.get('pick_label') or '?'} {side}{line} {r.get('market') or ''}".strip()


def _same(a: dict, b: dict) -> bool:
    if (a.get("player"), a.get("market")) != (b.get("player"), b.get("market")):
        return False
    if str(a.get("side") or "").lower() != str(b.get("side") or "").lower():
        return False
    la, lb = _f(a.get("line")), _f(b.get("line"))
    return (la is None and lb is None) or (la is not None and lb is not None and abs(la - lb) < 1e-9)


def check(board: dict) -> dict:
    """{"checked": claims read, "count": problems, "by_check": {name: n},
    "problems": ["CHECK — row: detail", … up to KEEP]}."""
    from .likely import HEAVIEST_PRICE, MIN_PROB
    from .sources.oddsapi import MAX_PROP_PRICE_AGE
    probs: list[tuple[str, str]] = []
    checked = 0
    ml = [r for r in (board or {}).get("most_likely") or [] if isinstance(r, dict)]
    for r in ml:
        checked += 1
        p, odds = _f(r.get("model_prob")), _f(r.get("odds"))
        if r.get("locked"):
            if (r.get("kind") or "prop") == "prop" and "now_listed" not in r:
                probs.append(("NO NOW", f"{_who(r)}: locked, no word on today's price"))
            m = _NOW_PCT.search(str(r.get("lock_note") or ""))
            if m and p is not None and int(m.group(1)) != round(p * 100):
                probs.append(("LOCK NOTE", f"{_who(r)}: note says {m.group(1)}%, tile {round(p * 100)}%"))
            continue
        if r.get("reserve"):
            continue
        if p is not None and p < MIN_PROB - 1e-9:
            probs.append(("FLOOR", f"{_who(r)}: {p:.0%} on the board"))
        if odds is not None and odds < HEAVIEST_PRICE:
            probs.append(("CAP", f"{_who(r)}: {odds:+.0f}"))
    for r in ml + [x for x in (board or {}).get("recommendations") or [] if isinstance(x, dict)]:
        age = _f(r.get("price_age_s"))
        if age is not None and not r.get("locked") and age > MAX_PROP_PRICE_AGE and not r.get("price_stale"):
            probs.append(("OLD PRICE", f"{_who(r)}: {age / 3600:.1f}h old at the build, not marked"))
    for game in ((board or {}).get("scan_reads") or {}).values():
        for x in (game or {}).get("players") or []:
            checked += 1
            pick = x.get("pick")
            if pick and ml and not any(_same(dict(pick, player=x.get("player")), r) for r in ml):
                probs.append(("PICK MISSING", f"{x.get('player')}: card names "
                              f"{pick.get('side')} {pick.get('line')} {pick.get('market')}"))
            best = (x.get("no_pick") or {}).get("best") or {}
            bp, bo = _f(best.get("model_prob")), _f(best.get("odds"))
            if bp is not None and bo is not None and bp < LONGSHOT_PROB and bo > 0:
                probs.append(("LONGSHOT", f"{x.get('player')}: likeliest is {best.get('side')} "
                              f"{best.get('line')} {best.get('market')} {bo:+.0f} at {bp:.0%}"))
            for t in (x.get("pro") or []) + (x.get("notes") or []):
                if _BARE_MATE.search(str(t)):
                    probs.append(("BARE MATE", f"{x.get('player')}: {t}"))
    fresh = (board or {}).get("data_freshness") or {}
    if fresh.get("played") is not None:
        checked += 1
        if fresh.get("behind"):
            unit = "day" if fresh.get("unit") == "day" else "week"
            probs.append(("DATA BEHIND", f"{unit} {fresh['played']} played; behind: "
                          + ", ".join(fresh["behind"])))
    by: dict = {}
    for name, _ in probs:
        by[name] = by.get(name, 0) + 1
    return {"checked": checked, "count": len(probs), "by_check": by,
            "problems": [f"{n} — {w}" for n, w in probs[:KEEP]]}


def line(name: str, rep: dict) -> str:
    """One sentence for the build log."""
    if not rep.get("count"):
        return f"{name} self-check: {rep.get('checked', 0)} claims, all hold."
    by = ", ".join(f"{k} {v}" for k, v in sorted(rep["by_check"].items()))
    return f"{name} self-check: {rep['count']} of {rep.get('checked', 0)} claims fail — {by}"
