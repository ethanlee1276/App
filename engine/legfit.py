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

The three-leg tickets' legs ("three", source game_three) and the scorer
pairs' ("scorers", game_td) learn apart: a 70% receptions leg and a 30%
touchdown are different claims. Fitted after each settle pass that graded a
ticket (engine/maintenance), beside the one-club bar; read by
gameparlays.legs_for and scorer_legs before a leg is held to its floor, so a
leg whose corrected chance falls under it is no leg.

Standard library only; `fit` raises nothing a caller must catch beyond a bad
connection, and `w_for` / `apply` never raise.
"""
from __future__ import annotations

import math

FILE = "leg_fit.json"
#: The journal's ticket sources (engine/gameparlays.SOURCES), by kind.
KINDS = {"three": "game_three", "scorers": "game_td"}
#: Graded legs, each bet once and with the book's fair chance, a league and
#: kind needs before it learns anything.
MIN_N = 60
#: The newest share of them held out to check the fit on.
TEST_SHARE = 0.3
#: The shares tried, 0 to 1 by 0.05.
GRID = tuple(round(i / 20, 2) for i in range(21))
#: A chance is kept inside these before the log loss is taken.
EPS = 1e-4


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


def _ll(rows, w: float) -> float:
    """Mean log loss of (p, fair, won) rows with the share w applied."""
    tot = 0.0
    for p, fair, won in rows:
        q = min(max(p - w * (p - fair), EPS), 1 - EPS)
        tot -= math.log(q if won else 1 - q)
    return tot / len(rows) if rows else 0.0


def _best(rows) -> float:
    return min(GRID, key=lambda w: (round(_ll(rows, w), 9), w))


def graded_legs(conn) -> dict:
    """{(league, kind): [(date, id, p, fair, won)]}: every graded leg of the
    game parlays with the book's chance (`anchor`), each bet once (its game's day,
    the game, the player, the market, the side and the line: the first copy
    journaled, as parlayledger.legs_once counts them), oldest first."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parlay_legs)")}
    if "fair" not in cols:
        return {}
    raw = "COALESCE(l.p_raw, l.p_final)" if "p_raw" in cols else "l.p_final"
    marks = ",".join("?" * len(KINDS))
    rows = conn.execute(
        f"SELECT t.sport, t.source, t.date, t.grade, l.id, l.player, l.market, l.side, l.line, {raw} AS p, "
        f"l.fair, l.odds, l.status FROM parlay_legs l JOIN parlays t ON t.id = l.parlay_id "
        f"WHERE t.source IN ({marks}) ORDER BY t.date, l.id", tuple(KINDS.values())).fetchall()
    kind_of = {v: k for k, v in KINDS.items()}
    seen: set = set()
    out: dict = {}
    for sport, source, date, game, lid, player, market, side, line, p, fair, odds, status in rows:
        key = (sport, source, str(date or ""), str(game or ""), str(player or "").strip().lower(), str(market or ""),
               str(side or "").upper(), line)
        if key in seen:
            continue
        seen.add(key)
        fair = anchor(fair, odds)
        if status not in ("won", "lost") or p is None or fair is None:
            continue
        p = float(p)
        if not 0 < p < 1:
            continue
        out.setdefault((str(sport), kind_of[source]), []).append((str(date or ""), lid, p, fair, status == "won"))
    return out


def fit(conn, write: bool = True) -> dict:
    """Each league and kind's share (see the module's words): {"fitted_at",
    "fits": {"nfl:three": {"w", "fitted", "n", "why", ...}}}. Written to the
    models directory (FILE) for `w_for`."""
    import datetime as _dt
    out: dict = {"fitted_at": _dt.datetime.now().isoformat(timespec="seconds"), "min_n": MIN_N, "fits": {}}
    for (sport, kind), legs in sorted(graded_legs(conn).items()):
        n = len(legs)
        rows = [(p, f, won) for _d, _i, p, f, won in legs]
        said = {"n": n, "claimed": round(sum(r[0] for r in rows) / n, 4), "fair": round(sum(r[1] for r in rows) / n, 4),
                "hit": round(sum(1 for r in rows if r[2]) / n, 4)}
        if n < MIN_N:
            out["fits"][f"{sport}:{kind}"] = {**said, "w": 0.0, "fitted": False,
                                               "why": f"waiting on the record: {n} graded leg(s), {MIN_N} needed"}
            continue
        cut = int(round(n * (1 - TEST_SHARE)))
        train, test = rows[:cut], rows[cut:]
        w_train = _best(train)
        before, after = _ll(test, 0.0), _ll(test, w_train)
        if w_train <= 0 or after >= before:
            out["fits"][f"{sport}:{kind}"] = {**said, "w": 0.0, "fitted": False, "test_n": len(test),
                                               "why": "the newest legs scored no better pulled toward the books' "
                                                      "chances; ours stand"}
            continue
        w = _best(rows)
        out["fits"][f"{sport}:{kind}"] = {
            **said, "w": w, "fitted": True, "test_n": len(test), "test_loss": [round(before, 4), round(after, 4)],
            "why": (f"our legs claimed {said['claimed']:.0%} and hit {said['hit']:.0%} over {n}; the books said "
                    f"{said['fair']:.0%}: each leg's chance is pulled {w:.0%} of the way to the book's")}
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


def apply(leg: dict, sport: str, kind: str, w: float | None = None) -> dict:
    """The leg with its chance corrected (``p``), ours kept as ``p_raw`` and
    the share as ``fit_w``; the leg itself when nothing applies. Never raises."""
    try:
        w = w_for(sport, kind) if w is None else w
        fair = anchor(leg.get("fair"), leg.get("odds"))
        if not w or fair is None or leg.get("p") is None or leg.get("p_raw") is not None:
            return leg
        p = float(leg["p"])
        return {**leg, "p_raw": round(p, 4), "p": round(p - w * (p - fair), 4), "fit_w": w}
    except (TypeError, ValueError):
        return leg


def census(sport: str) -> dict:
    """The fit in force for a league, both kinds, for the board's census."""
    got = fits()
    return {kind: {k: v for k, v in (got.get(f"{sport}:{kind}") or {}).items()
                   if k in ("w", "fitted", "n", "why")} for kind in KINDS if got.get(f"{sport}:{kind}")}
