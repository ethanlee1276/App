"""When our number is far above the books': a data error, or a real find?

Ethan, 2026-09-27, on picks the Most Likely board refused for being more
than ten points more confident than the market — Kenyon Sadiq 67% against
51% with Mason Taylor out, Omarion Hampton 71% against 57%: "maybe we
figure out if thats data error or if thats genuinely something our model
found and that could happen based on the circumstances."

The ten-point bar (betting.MAX_CREDIBLE_EDGE) has always treated every
big disagreement as our error, and it has been right to often enough —
Quinshon Judkins projected at 31 rushing yards into a 59.5 line (a
stale role), DJ Moore's catches off his Chicago seasons. It has also been
the thing that threw away the site's best step-up reads: Sadiq's ×1.75,
measured over four seasons, landed him exactly where the other AI had
him, and the bar hid it.

So each such row is now asked two questions, in this order.

  IS THERE A SIGN THE INPUTS ARE WRONG?  (→ "suspect", stays off)
    * his history is from another team (an offseason move, carry.reset);
    * his role has moved AGAINST our side — his share of the snaps this
      season sits 20+ points from last season's and our number still
      rests on last season (an over on a shrunken role, an under on a
      grown one);
    * the books have moved the line away from our side on today's tape;
    * the price we are comparing against is hours old.

  IS THERE A REASON IT COULD HAPPEN?  (→ "found", shown)
    * a measured step explains the gap: the chain moved our number from
      his own form by at least half the distance to the market — a
      teammate ruled out ahead of him, a quarterback change, the
      matchup, the game script — and the step is named;
    * his own games back it: at this number, on our side, in eight or
      more of his recent games, at a rate at least five points above the
      market's and no more than five under what we publish.

  NEITHER?  → "unexplained", stays off: nothing on his record or in the
  circumstances accounts for a number this far from the books.

A gap past `BIG_GAP` (25 points, the size the known data errors came in)
is shown only when his own games back it — a step alone does not carry
a number that far.

A "found" row goes on the Most Likely board labelled Bolder than the
books, with the reason, graded on paper under its own bucket ("bold") so
the record — not this argument — says whether these picks win. Nothing
here moves a probability.

Standard library only.
"""
from __future__ import annotations

from .betting import MAX_CREDIBLE_EDGE

#: Past this the known data errors live; a find needs his own games too.
BIG_GAP = 0.25
#: The fewest recent games his own record is read over.
MIN_OWN_GAMES = 8
#: How many recent games the record reads (most recent first).
OWN_GAMES = 12
#: His own hit rate must beat the market's number by this much…
OWN_OVER_MARKET = 0.05
#: …and sit no further than this under what we publish.
OWN_UNDER_SHOWN = 0.05
#: A snap share this far from last season's is a changed role.
ROLE_SHIFT = 0.20
#: A price older than this is not today's market.
STALE_PRICE_S = 6 * 3600

FOUND, SUSPECT, UNEXPLAINED = "found", "suspect", "unexplained"
LABEL = {FOUND: "Bolder than the books", SUSPECT: "Likely a data problem",
         UNEXPLAINED: "Nothing explains the gap"}


def _f(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def _p_side(side: str, line, mean, sd):
    from .statmath import prob_over
    if line is None or mean is None or not sd or sd <= 0:
        return None
    p = prob_over(float(line), float(mean), float(sd))
    return 1.0 - p if side == "under" else p


def _side(x) -> str:
    s = str(x or "").lower()
    return "over" if s in ("over", "yes") else "under" if s in ("under", "no") else s


def _word(market: str) -> str:
    return {"receptions": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards",
            "pass_yds": "passing yards", "pass_td": "passing TDs", "pass_att": "pass attempts",
            "pass_cmp": "completions", "rush_att": "carries"}.get(market, market.replace("_", " "))


def _snap_shift(row: dict):
    """(this season's snap share, last season's) off his logs, or None —
    the logs are most recent first and a season break shows as the week
    number jumping back up."""
    logs = [l for l in row.get("logs") or [] if isinstance(l, dict)]
    now, then, broke, last_wk = [], [], False, None
    for l in logs:
        wk = l.get("week")
        if last_wk is not None and wk is not None and wk > last_wk:
            broke = True
        last_wk = wk if wk is not None else last_wk
        s = _f(l.get("snaps"))
        if s is None:
            continue
        (then if broke else now).append(s)
    if len(now) < 2 or len(then) < 3:
        return None
    return sum(now) / len(now), sum(then[:8]) / len(then[:8])


def flags(row: dict, side: str) -> list:
    """Signs the inputs behind this number are wrong. Each a sentence."""
    out = []
    carried = row.get("carried") or {}
    reset = carried.get("reset") if isinstance(carried, dict) else None
    if isinstance(reset, dict) and reset.get("kind") == "team change":
        out.append(f"His history is from another team ({reset.get('detail') or 'an offseason move'}) — "
                   f"the number is built on a role he no longer has.")
    shift = _snap_shift(row)
    if shift:
        now, then = shift
        heavy = isinstance(carried, dict) and (carried.get("weight") or 0) >= 0.5
        if heavy and now <= then - ROLE_SHIFT and side == "over":
            out.append(f"His role has shrunk — {now:.0%} of the snaps this season against {then:.0%} last — "
                       f"and our over still rests on last season.")
        elif heavy and now >= then + ROLE_SHIFT and side == "under":
            out.append(f"His role has grown — {now:.0%} of the snaps this season against {then:.0%} last — "
                       f"and our under still rests on last season.")
    mv = row.get("line_move") or {}
    if isinstance(mv, dict) and mv.get("verdict") == "against" and (mv.get("steam") or abs(_f(mv.get("delta")) or 0) >= 1):
        out.append(f"The books have moved the line away from our side today ({mv.get('open')} → {mv.get('current')}) "
                   f"— they may know something our feeds do not yet.")
    age = _f(row.get("price_age_s"))
    if age is not None and age > STALE_PRICE_S:
        out.append(f"The price we are measuring against is {age / 3600:.0f} hours old.")
    return out


def step_reason(row: dict, side: str, line, shown: float, fair: float):
    """(sentence, how far the chain moved our number) when a measured step
    explains at least half the gap, else (None, move)."""
    chain = row.get("chain") or {}
    base = _f((chain.get("base") or {}).get("value"))
    mean = _f(row.get("projection"))
    sd = _f(row.get("proj_std"))
    p_base = _p_side(side, line, base, sd)
    p_final = _p_side(side, line, mean, sd)
    if p_base is None or p_final is None:
        return None, 0.0
    moved = p_final - p_base
    gap = shown - fair
    if gap <= 0 or moved < gap / 2.0:
        return None, moved
    steps = [s for s in chain.get("steps") or [] if isinstance(s, dict)
             and _f(s.get("mult")) not in (None, 1.0)
             and ((_f(s.get("mult")) > 1.0) == (side == "over"))]
    if not steps:
        return None, moved
    top = max(steps, key=lambda s: abs(_f(s.get("mult")) - 1.0))
    why = str(top.get("why") or top.get("label") or top.get("key") or "").strip()
    return (f"{why} — from his own form ({p_base:.0%} on this number) to {p_final:.0%}.", moved)


def own_games(row: dict, side: str, line, shown: float, fair: float):
    """(sentence, rate, n) when his own recent games back the number,
    else (None, rate, n)."""
    vals = [v for v in (_f(x) for x in (row.get("recent_values") or [])[:OWN_GAMES]) if v is not None]
    n = len(vals)
    if line is None or n < MIN_OWN_GAMES:
        return None, None, n
    hits = sum(1 for v in vals if (v > float(line)) == (side == "over") and v != float(line))
    rate = hits / n
    if rate >= fair + OWN_OVER_MARKET and rate >= shown - OWN_UNDER_SHOWN:
        word = "over" if side == "over" else "under"
        return (f"His own games back it: {word} {float(line):g} {_word(row.get('market') or '')} "
                f"in {hits} of his last {n} ({rate:.0%}) — the books say {fair:.0%}.", rate, n)
    return None, rate, n


def check(row: dict, side, line, shown, fair, raw=None) -> dict | None:
    """The verdict on one row whose number sits more than
    MAX_CREDIBLE_EDGE from the market's, or None when it does not.

    ``row`` is the prop's published row (projection, chain, logs…);
    ``shown`` is the chance the board would print on ``side`` at
    ``line``; ``fair`` the market's de-vigged chance on that side;
    ``raw`` the engine's pre-shrink claim on that side, when there is
    one."""
    shown, fair, raw = _f(shown), _f(fair), _f(raw)
    if shown is None or fair is None:
        return None
    side = _side(side)
    gap = max(abs(shown - fair), abs(raw - fair) if raw is not None else 0.0)
    if gap <= MAX_CREDIBLE_EDGE:
        return None
    out = {"gap": round(gap, 4), "shown": round(shown, 4), "fair": round(fair, 4),
           "raw": None if raw is None else round(raw, 4)}
    bad = flags(row, side)
    if bad:
        return dict(out, verdict=SUSPECT, label=LABEL[SUSPECT], why=bad)
    # A number BELOW the market's is not a bold call on this side; the
    # board would never show it, and nothing here argues for it.
    if shown < fair:
        return dict(out, verdict=UNEXPLAINED, label=LABEL[UNEXPLAINED],
                    why=["Our number sits under the market's on this side."])
    step, _moved = step_reason(row, side, line, raw if raw is not None and raw > shown else shown, fair)
    games, rate, n = own_games(row, side, line, shown, fair)
    why = [w for w in (step, games) if w]
    if gap > BIG_GAP and not games:
        extra = (f" His own games clear it {rate:.0%} of the time over {n}." if rate is not None
                 else f" Only {n} games of his to read.")
        return dict(out, verdict=UNEXPLAINED, label=LABEL[UNEXPLAINED],
                    why=[f"{gap:.0%} from the books is the size data errors come in, and a step alone "
                         f"does not carry a number that far.{extra}"] + ([step] if step else []))
    if why:
        return dict(out, verdict=FOUND, label=LABEL[FOUND], why=why)
    tail = (f" His own games clear it {rate:.0%} of the time over {n} — near the books' {fair:.0%}."
            if rate is not None else f" Only {n} games of his to read.")
    return dict(out, verdict=UNEXPLAINED, label=LABEL[UNEXPLAINED],
                why=["Nothing in the circumstances moved our number this far — no teammate out, "
                     "no quarterback change, no matchup step that accounts for it." + tail])
