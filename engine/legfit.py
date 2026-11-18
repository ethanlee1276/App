"""A learned correction for the game parlays' legs, league by league (LEGFIT1, 2026-11-16).

Ethan, asked whether each league should learn how far its parlay legs' stated
chances run past what they hit: "yes".

THE GAP (FOOTCAL1, 2026-11-16). Counted once a bet (parlayledger.legs_once),
the NFL's three-leg tickets' legs hit 13 points under the chance we gave them
and college football's 6. The credibility rule (gameparlays.credible_row)
took out the legs whose number nothing stood behind; this learns what is
left, from the record, and corrects it.

THE CORRECTION. Each leg's chance is pulled toward the book's own fair chance
for it (the leg's `fair`: twoleg._fair_of), by a share `w` each league and
kind learns:

    p' = p - w * (p - fair)

w = 0 is our number as it is, w = 1 the book's. Where the leg keeps no fair
chance (every leg journaled before 16 November), the chance its own price
implies stands in (`implied`), in the fit and in the correction alike; a leg
with neither is left as it is. The share is the one that would have scored
the league's graded legs best (the log loss of each bet once, against our
uncorrected number: the journal keeps it as `p_raw` beside the posted
`p_final`, so a correction is never learned on top of itself), and it is used
only when it also scores better on the newest legs it was not fitted on
(TEST_SHARE). It waits for MIN_N graded legs with a fair chance; until then,
and whenever the held-out legs do not get better, w is 0 and the leg is ours.

THE SECOND CORRECTION: A SHIFT (FOOTCAL2, 2026-11-17; Ethan: "recalibrate
football too"). Pulling toward the book cannot move a leg the book agreed
with. The NFL's three-leg legs claimed 68% and hit 55% (each bet once, 128),
and the books' own prices on them averaged 68% too: w can be anything and
the chance barely moves. So each league and kind also learns a shift in
log-odds, `s`, applied after the pull:

    p'' = sigmoid(logit(p') + s)

fitted the same way (the newest TEST_SHARE held out, kept only when it
scores them better, 0 otherwise), from SHIFT_GRID. It learns only from legs
built the current way: those whose journal names their pool (likely, edge,
priced, scorer; from 16 November, 19:25 UTC). Before that, any priced prop
became a leg at a number the Edge path itself refuses (gameparlays.
credible_row), and that source is gone: a shift learned on it would hold the
honest legs that replaced it to its errors, and with the floor at 60% leave
the NFL with no parlays at all. MIN_N current legs, then the record speaks.

The three-leg tickets' legs ("three", source game_three) and the scorer
pairs' ("scorers", game_td) learn apart: a 70% receptions leg and a 30%
touchdown are different claims. Fitted after each settle pass that graded a
ticket (engine/maintenance), beside the one-club bar; read by
gameparlays.legs_for and scorer_legs before a leg is held to its floor, so a
leg whose corrected chance falls under it is no leg.

EACH MARKET LEARNS TOO (GPWIN1, 2026-11-18; Ethan, of the parlays: "track
them and learn and make them better"). A league's correction is one number for
all its markets, and its markets do not miss alike: the NFL's three-leg
tickets' receptions legs hit 42% where we said 71% (each leg as often as it
rode a ticket), its passing yards 63% where we said 71%, and hockey's shots on
goal 79% where we said 66%. So after the league's pull and shift, each market
with MARKET_MIN_N graded legs built the current way learns a shift of its own
(`_market_fits`), the same way the league's was learned: from SHIFT_GRID, on
all but its newest legs, kept only when it scores the newest better. A market
that runs hot is pulled down until fewer of its legs clear the floor, and its
legs that still do keep its record growing, so the correction follows it.

THE TWO-LEG TICKETS' LEGS ARE THE SAME KIND (GPWIN1). A game's two-leg tickets
(source ``game_two``) are made of the same picks as its three-leg ones, so
their legs learn with them, as "three"; each bet once across both.

Standard library only; `fit` raises nothing a caller must catch beyond a bad
connection, and `w_for` / `apply` never raise.
"""
from __future__ import annotations

import math

FILE = "leg_fit.json"
#: The journal's ticket sources (engine/gameparlays.SOURCES), by kind.
KINDS = {"three": "game_three", "scorers": "game_td"}
#: Every source and the kind its legs learn as: a game's two-leg tickets are
#: made of the same picks as its three-leg ones (GPWIN1).
SOURCE_KIND = {"game_three": "three", "game_two": "three", "game_td": "scorers"}
#: Graded legs built the current way a market needs before it learns a shift
#: of its own (`_market_fits`).
MARKET_MIN_N = 40
#: Graded legs, each bet once and with the book's fair chance, a league and
#: kind needs before it learns anything.
MIN_N = 60
#: The newest share of them held out to check the fit on.
TEST_SHARE = 0.3
#: The shares tried, 0 to 1 by 0.05.
GRID = tuple(round(i / 20, 2) for i in range(21))
#: A chance is kept inside these before the log loss is taken.
EPS = 1e-4
#: The shifts tried, in log-odds: -1.5 (a 70% leg to 34%) to +0.5 (70% to
#: 79%), by 0.05. Down as far as the record could need, up a little.
SHIFT_GRID = tuple(round(-1.5 + i / 20, 2) for i in range(41))


def implied(odds) -> float | None:
    """The chance an American price implies (the book's margin left in), or None."""
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return None
    if o <= -100:
        return -o / (-o + 100.0)
    if o >= 100:
        return 100.0 / (o + 100.0)
    return None


def anchor(fair, odds) -> float | None:
    """The book's chance for a leg: its fair chance, else its price's."""
    try:
        f = float(fair) if fair is not None else None
    except (TypeError, ValueError):
        f = None
    if f is not None and 0 < f < 1:
        return f
    return implied(odds)


def shifted(p: float, s: float) -> float:
    """``p`` moved ``s`` in log-odds (0 leaves it as it is)."""
    if not s:
        return p
    q = min(max(p, EPS), 1 - EPS)
    return 1.0 / (1.0 + math.exp(-(math.log(q / (1 - q)) + s)))


def _ll(rows, w: float, s: float = 0.0) -> float:
    """Mean log loss of (p, fair, won) rows with the share w and the shift s applied."""
    tot = 0.0
    for p, fair, won in rows:
        q = min(max(shifted(p - w * (p - fair), s), EPS), 1 - EPS)
        tot -= math.log(q if won else 1 - q)
    return tot / len(rows) if rows else 0.0


def _best(rows) -> float:
    return min(GRID, key=lambda w: (round(_ll(rows, w), 9), w))


def _best_shift(rows, w: float) -> float:
    """The shift that scores ``rows`` best after the share ``w`` (the smallest in size on a tie)."""
    return min(SHIFT_GRID, key=lambda s: (round(_ll(rows, w, s), 9), abs(s)))


def graded_legs(conn) -> dict:
    """{(league, kind): [(date, id, p, fair, won, pool, market)]}: every graded leg of
    the game parlays with the book's chance (`anchor`) and the pool it came
    from ("" before the journal named pools), each bet once (its game's day,
    the game, the player, the market, the side and the line: the first copy
    journaled, as parlayledger.legs_once counts them), oldest first."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    if "fair" not in cols:
        return {}
    raw = "COALESCE(l.p_raw, l.p_final)" if "p_raw" in cols else "l.p_final"
    pool = "l.pool" if "pool" in cols else "''"
    marks = ",".join("?" * len(SOURCE_KIND))
    rows = conn.execute(
        f"SELECT t.sport, t.source, t.date, t.grade, l.id, l.player, l.market, l.side, l.line, {raw} AS p, "
        f"l.fair, l.odds, l.status, {pool} FROM parlay_legs l JOIN parlays t ON t.id = l.parlay_id "
        f"WHERE t.source IN ({marks}) ORDER BY t.date, l.id", tuple(SOURCE_KIND)).fetchall()
    kind_of = SOURCE_KIND
    seen: set = set()
    out: dict = {}
    for sport, source, date, game, lid, player, market, side, line, p, fair, odds, status, from_pool in rows:
        # Each bet once across the kind's tickets, two legs or three.
        key = (sport, kind_of[source], str(date or ""), str(game or ""), str(player or "").strip().lower(),
               str(market or ""), str(side or "").upper(), line)
        if key in seen:
            continue
        seen.add(key)
        fair = anchor(fair, odds)
        if status not in ("won", "lost") or p is None or fair is None:
            continue
        p = float(p)
        if not 0 < p < 1:
            continue
        out.setdefault((str(sport), kind_of[source]), []).append(
            (str(date or ""), lid, p, fair, status == "won", str(from_pool or ""), str(market or "")))
    return out


def fit(conn, write: bool = True) -> dict:
    """Each league and kind's share (see the module's words): {"fitted_at",
    "fits": {"nfl:three": {"w", "fitted", "n", "why", ...}}}. Written to the
    models directory (FILE) for `w_for`."""
    import datetime as _dt
    out: dict = {"fitted_at": _dt.datetime.now().isoformat(timespec="seconds"), "min_n": MIN_N, "fits": {}}
    for (sport, kind), legs in sorted(graded_legs(conn).items()):
        n = len(legs)
        rows = [(p, f, won) for _d, _i, p, f, won, _pool, _m in legs]
        current = [(p, f, won) for _d, _i, p, f, won, pool, _m in legs if pool]
        said = {"n": n, "claimed": round(sum(r[0] for r in rows) / n, 4), "fair": round(sum(r[1] for r in rows) / n, 4),
                "hit": round(sum(1 for r in rows if r[2]) / n, 4)}
        if n < MIN_N:
            fit_ = {**said, "w": 0.0, "fitted": False,
                    "why": f"waiting on the record: {n} graded leg(s), {MIN_N} needed"}
        else:
            cut = int(round(n * (1 - TEST_SHARE)))
            train, test = rows[:cut], rows[cut:]
            w_train = _best(train)
            before, after = _ll(test, 0.0), _ll(test, w_train)
            if w_train <= 0 or after >= before:
                fit_ = {**said, "w": 0.0, "fitted": False, "test_n": len(test),
                        "why": "the newest legs scored no better pulled toward the books' chances; ours stand"}
            else:
                w = _best(rows)
                fit_ = {**said, "w": w, "fitted": True, "test_n": len(test),
                        "test_loss": [round(before, 4), round(after, 4)],
                        "why": (f"our legs claimed {said['claimed']:.0%} and hit {said['hit']:.0%} over {n}; the books "
                                f"said {said['fair']:.0%}: each leg's chance is pulled {w:.0%} of the way to the book's")}
        both = {**fit_, **_shift_fit(current, fit_["w"] if fit_.get("fitted") else 0.0)}
        markets = _market_fits([leg for leg in legs if leg[5]], both["w"] if both.get("fitted") else 0.0,
                               float(both.get("shift") or 0.0))
        if markets:
            both["markets"] = markets
        out["fits"][f"{sport}:{kind}"] = both
    if write:
        import json as _json
        import os as _os
        from . import modelstate
        p = modelstate.path(FILE)
        _os.makedirs(_os.path.dirname(p) or ".", exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(out, f, indent=1, sort_keys=True)
        _os.replace(tmp, p)
    return out


def _shift_fit(rows, w: float) -> dict:
    """The shift for one league and kind, from its legs built the current way
    (``rows``: (p, fair, won), oldest first), after the share ``w``: the fields
    the fit carries for it ("shift", "shift_n", "shift_why"; "shift_test" when
    one was tried)."""
    n = len(rows)
    if n < MIN_N:
        return {"shift": 0.0, "shift_n": n,
                "shift_why": f"waiting on legs built the current way: {n} graded, {MIN_N} needed"}
    claimed = sum(shifted(p - w * (p - f), 0.0) for p, f, _won in rows) / n
    hit = sum(1 for r in rows if r[2]) / n
    cut = int(round(n * (1 - TEST_SHARE)))
    train, test = rows[:cut], rows[cut:]
    s_train = _best_shift(train, w)
    before, after = _ll(test, w), _ll(test, w, s_train)
    if not s_train or after >= before:
        return {"shift": 0.0, "shift_n": n, "shift_test": [round(before, 4), round(after, 4)],
                "shift_why": f"legs built the current way claimed {claimed:.0%} and hit {hit:.0%} over {n}; "
                             "a shift scored the newest of them no better, so none"}
    s = _best_shift(rows, w)
    return {"shift": s, "shift_n": n, "shift_test": [round(before, 4), round(after, 4)],
            "shift_why": (f"legs built the current way claimed {claimed:.0%} and hit {hit:.0%} over {n}: each "
                          f"leg's chance is moved {s:+.2f} in log-odds (a 70% leg to {shifted(0.70, s):.0%})")}


def _market_fits(legs, w: float, s: float) -> dict:
    """Each market's own shift, on top of its league's share ``w`` and shift
    ``s``: {market: {"shift", "n", "claimed", "hit", "why"}} for each market
    with MARKET_MIN_N graded legs built the current way (``legs``: graded_legs'
    rows, oldest first). A shift is kept only when it scores the market's
    newest legs (TEST_SHARE) better than none; a market that scores no better
    is listed at 0, so the page can say it was read."""
    by: dict = {}
    for _d, _i, p, f, won, _pool, market in legs:
        by.setdefault(market or "", []).append((p, f, won))
    out: dict = {}
    for market, rows in sorted(by.items()):
        n = len(rows)
        if not market or n < MARKET_MIN_N:
            continue
        base = [(shifted(p - w * (p - f), s), shifted(p - w * (p - f), s), won) for p, f, won in rows]
        claimed = sum(r[0] for r in base) / n
        hit = sum(1 for r in base if r[2]) / n
        cut = int(round(n * (1 - TEST_SHARE)))
        train, test = base[:cut], base[cut:]
        m_train = _best_shift(train, 0.0)
        before, after = _ll(test, 0.0), _ll(test, 0.0, m_train)
        if not m_train or after >= before:
            out[market] = {"shift": 0.0, "n": n, "claimed": round(claimed, 4), "hit": round(hit, 4),
                           "why": f"claimed {claimed:.0%}, hit {hit:.0%} over {n}: the league's correction holds"}
            continue
        m = _best_shift(base, 0.0)
        out[market] = {"shift": m, "n": n, "claimed": round(claimed, 4), "hit": round(hit, 4),
                       "test": [round(before, 4), round(after, 4)],
                       "why": (f"claimed {claimed:.0%}, hit {hit:.0%} over {n}: each leg moved {m:+.2f} more "
                               f"in log-odds (a 70% leg to {shifted(0.70, m):.0%})")}
    return out


_HELD: dict = {}
#: Why the fit on file could not be read, in this process; None when it was.
ERROR: str | None = None


def fits() -> dict:
    """The fits on file ({} before the first, or when the file cannot be read,
    which is said once a process and kept in ERROR)."""
    global ERROR
    try:
        import json as _json
        import os as _os
        from . import modelstate
        p = modelstate.path(FILE)
        try:
            key = (p, _os.stat(p).st_mtime_ns)
        except FileNotFoundError:
            ERROR = None
            return {}
        if _HELD.get("key") != key:
            with open(p, encoding="utf-8") as f:
                _HELD.update(key=key, data=_json.load(f))
        ERROR = None
        return dict((_HELD.get("data") or {}).get("fits") or {})
    except Exception as exc:                                 # noqa: BLE001
        why = f"{type(exc).__name__}: {exc}"
        if ERROR != why:
            print(f"  ⚠️ the parlay legs' learned correction could not be read ({why}); legs are taken as they are")
        ERROR = why
        return {}


def w_for(sport: str, kind: str) -> float:
    """The share in force for a league and kind: the fit's when it was fitted,
    else 0. Never raises."""
    try:
        f = fits().get(f"{sport}:{kind}") or {}
        return min(max(float(f.get("w") or 0.0), 0.0), 1.0) if f.get("fitted") else 0.0
    except (TypeError, ValueError):
        return 0.0


def shift_for(sport: str, kind: str) -> float:
    """The shift in force for a league and kind (0 until the record has
    spoken, and whenever the fit kept none). Never raises."""
    try:
        s = float((fits().get(f"{sport}:{kind}") or {}).get("shift") or 0.0)
        return min(max(s, SHIFT_GRID[0]), SHIFT_GRID[-1])
    except (TypeError, ValueError):
        return 0.0


def market_shift_for(sport: str, kind: str, market) -> float:
    """A market's own shift in force on top of its league's (`_market_fits`),
    0 when it has none. Never raises."""
    try:
        m = (((fits().get(f"{sport}:{kind}") or {}).get("markets") or {}).get(str(market or "")) or {})
        return min(max(float(m.get("shift") or 0.0), SHIFT_GRID[0]), SHIFT_GRID[-1])
    except (TypeError, ValueError):
        return 0.0


def apply(leg: dict, sport: str, kind: str, w: float | None = None, shift: float | None = None) -> dict:
    """The leg with its chance corrected (``p``): pulled toward the book's by
    the share, then moved by the shift and its market's own shift. Ours is
    kept as ``p_raw``, the share as ``fit_w`` and the shifts together as
    ``fit_shift``; the leg itself when nothing applies. Never raises."""
    try:
        w = w_for(sport, kind) if w is None else w
        s = shift_for(sport, kind) if shift is None else shift
        s = s + market_shift_for(sport, kind, leg.get("market"))
        if leg.get("p") is None or leg.get("p_raw") is not None:
            return leg
        p = q = float(leg["p"])
        fair = anchor(leg.get("fair"), leg.get("odds"))
        if w and fair is not None:
            q = q - w * (q - fair)
        else:
            w = 0.0
        q = shifted(q, s)
        if not w and not s:
            return leg
        out = {**leg, "p_raw": round(p, 4), "p": round(q, 4), "fit_w": w}
        if s:
            out["fit_shift"] = s
        return out
    except (TypeError, ValueError):
        return leg


def census(sport: str) -> dict:
    """The fit in force for a league, both kinds, for the board's census."""
    got = fits()
    return {kind: {k: v for k, v in (got.get(f"{sport}:{kind}") or {}).items()
                   if k in ("w", "fitted", "n", "why", "shift", "shift_n", "shift_why", "markets")}
            for kind in KINDS if got.get(f"{sport}:{kind}")}
