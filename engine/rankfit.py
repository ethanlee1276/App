"""Ranking AUC per (sport, market) — measured where the logs are, then adopted.

Ethan, 2026-08-31: "We should have a most likely page for every sport…
We should dive deeper into getting the most likely page for MLB set up."

THE RULE THE NFL BOARD WAS BUILT UNDER APPLIES: a market appears on the
likelihood board only after it has been SHOWN to rank (`likely.RANK_AUC`
— "a market with no measurement does not appear"). The NFL's numbers
were measured by hand on 2026-08-30 and shipped as constants. That does
not scale to a second sport, and it cannot run on the dev box at all:
the MLB logs live only on the droplet, so a hand-measured constant would
be a number typed from memory about a database the typist cannot see.

So the measurement is a fitter like the calibrations are: walk the
sport's own ingested logs forward, score each market's probabilities as
a RANKING (AUC — the probability a cleared-line row was ranked above an
uncleared one), and persist to the models dir. `likely.rank_auc` reads
this store first, so a market turns its shelf on BY ITSELF on the box
that measured it — and turns it off again if a refit lands under the
bar. Nothing is ever claimed that this box has not measured.

AUC AND NOT BRIER, deliberately: the likelihood board sorts, and sorting
survives any monotone miscalibration. rush_yds ranks at 0.76 while being
unbettable — the two abilities are separate and this measures only the
one the board uses.

Weekly from the maintenance pass, plus a bootstrap on a box whose store
is empty — the same "fit it now, not on Wednesday" precedent the CFB
touchdown backfill set. Standard library only.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from . import modelstate as _modelstate

STORE = Path(_modelstate.path("rank_auc.json"))

#: Settled walk-forward pairs before a market's AUC is worth storing.
#: An AUC on a few hundred pairs swings whole points between refits, and
#: a shelf that flickers on and off teaches readers to ignore it.
MIN_PAIRS = 2_000

#: The markets each sport's likelihood board would rank, if measurement
#: allows. Matching `calibrate.SPORT_MARKETS` where both exist.
#:
#: COLLEGE FOOTBALL JOINED 2026-09-03, and it is the reason this table is
#: worth reading twice. Ethan, twice on 2026-09-02: "make sure everything
#: I'm telling you to do for NFL is also being implemented for college
#: football because I'm still not seeing any props for college football."
#: College had no yardage market at all — not a broken one, an absent one.
#:
#: The question that had to be answered before adding a line here was
#: whether college needs its OWN projection or can walk the shared one.
#: It can walk the shared one, and the reason is structural rather than
#: hopeful: `logwalk.walk` hands every non-MLB sport to the same generic
#: chain, `projection.build_projection` takes `sport` only to KEY its
#: self-tuning stores (formfit/playerfit), and `betting.evaluate_prop`
#: already reads "cfb" as football for weather and fatigue. Nothing in
#: that path is nflverse-shaped. So college gets the NFL's MODEL and its
#: own MEASUREMENT — which is the entire point, and the opposite of what
#: happened to the touchdown board, where `likely.CFB_TD_AUC` had to be
#: un-borrowed from the NFL's 0.721 after the college board wore a number
#: measured on somebody else's football.
#:
#: NFL is deliberately NOT here: its five markets are hand-measured
#: constants in `likely.RANK_AUC`, and a store entry would silently
#: override them. That is a separate decision from this one.
MARKETS = {
    "mlb": ("hits", "total_bases", "home_runs", "strikeouts"),
    "nba": ("pts", "reb", "ast", "fg3m", "pra"),
    "wnba": ("pts", "reb", "ast", "fg3m", "pra"),
    "cfb": ("pass_yds", "rush_yds", "rec_yds", "receptions"),
}


def auc(pairs) -> float | None:
    """Mann-Whitney AUC of ``[(prob, outcome)]`` — ties share credit."""
    pos = sorted(float(p) for p, o in pairs if o)
    neg = sorted(float(p) for p, o in pairs if not o)
    if not pos or not neg:
        return None
    # Rank-sum over the merged list, O(n log n) — 100k pairs is fine.
    import bisect
    wins = 0.0
    for p in pos:
        lo = bisect.bisect_left(neg, p)
        hi = bisect.bisect_right(neg, p)
        wins += lo + 0.5 * (hi - lo)
    return wins / (len(pos) * len(neg))


def load(path: Path | str = STORE) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def _save(store: dict, path: Path | str = STORE) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, indent=1))
    os.replace(tmp, path)


def rank_auc(sport: str, market: str, store: dict | None = None):
    """The measured AUC for this market on THIS box, or None."""
    got = (store if store is not None else load()).get(f"{sport}:{market}")
    return got.get("auc") if got else None


def _park_context():
    """``game_for_index`` for the MLB walk: each historical game in the
    ballpark it was actually played in, named by the log's own
    team/opponent/home columns — static factors, so nothing the walk
    sees postdates the game it is predicting."""
    from .mlb.models import MLBGame
    from .mlb.parks import park_of_game

    def game_for_index(e, i):
        def at(key):
            lst = e.get(key) or []
            return lst[i] if i < len(lst) else ""
        team, opp = at("teams"), at("opps")
        home = bool(at("homes"))
        park = park_of_game(team, opp, home)
        return MLBGame(home=(team if home else opp),
                       away=(opp if home else team),
                       park=park.key if park else "generic")
    return game_for_index


def context_report(conn, sport: str = "mlb", markets=None,
                   log=print) -> list[str]:
    """Baseline vs park-context ranking AUC, per market — the A/B.

    The standing finding this answers: the walk replays history in a
    NEUTRAL stadium, so the venue layer the handicapping script wired
    into the live model is invisible to the rank store's numbers. This
    runs each market twice — neutral, then with every game in its real
    ballpark — and prints both AUCs side by side. It writes NOTHING:
    adoption (making the context walk the store's standard) is a
    decision for whoever reads the deltas, not a side effect of
    measuring them. MLB only — it is the sport whose logs carry venue
    context and whose engine prices it.
    """
    if sport != "mlb":
        return [f"context report: no venue-aware walk for {sport}"]
    from . import calibrate as _cal
    from . import db as _db
    from .logwalk import walk

    lines: list[str] = []
    gfi = _park_context()
    for market in markets or MARKETS.get(sport, ()):
        key = f"{sport}:{market}"
        try:
            entries = _db.entries_for_market(conn, sport, market)
            if not entries:
                lines.append(f"context {key}: no ingested logs")
                continue
            with _cal.disabled():
                base = walk(sport, entries, market)
                ctx = walk(sport, entries, market, game_for_index=gfi)
            a, b = auc(base.pairs), auc(ctx.pairs)
        except Exception as exc:                          # noqa: BLE001
            lines.append(f"context {key}: walk failed — {exc}")
            continue
        if a is None or b is None or len(base.pairs) < MIN_PAIRS:
            lines.append(f"context {key}: too thin to compare "
                         f"({len(base.pairs):,} pairs)")
            continue
        word = ("park context RANKS BETTER" if b > a + 0.002
                else "park context ranks worse" if b < a - 0.002
                else "no measurable difference")
        lines.append(f"context {key}: neutral {a:.4f} → in-park {b:.4f} "
                     f"({(b - a) * 100:+.2f} pts on {len(ctx.pairs):,} "
                     f"pairs) — {word}")
    for ln in lines:
        log(f"  {ln}")
    return lines


def measure(conn, sport: str, markets=None, log=print,
            path: Path | str = STORE) -> list[str]:
    """Walk each market forward, store what the sample supports.

    A market under MIN_PAIRS is REMOVED from the store rather than left
    at its old value: a number measured on data this box no longer holds
    is a number nobody can re-derive, and the shelf it kept open would
    outlive its evidence.
    """
    from . import calibrate as _cal
    from . import db as _db
    from .logwalk import walk

    lines: list[str] = []
    store = load(path)
    changed = False
    for market in markets or MARKETS.get(sport, ()):
        key = f"{sport}:{market}"
        try:
            entries = _db.entries_for_market(conn, sport, market)
            if not entries:
                lines.append(f"rank fit {key}: no ingested logs")
                continue
            # Raw probabilities: a monotone calibration cannot change an
            # AUC, and fitting on corrected output would re-measure the
            # store's own influence — same reason calibrate.fit_market
            # walks with the correction off.
            with _cal.disabled():
                report = walk(sport, entries, market)
            pairs = report.pairs
        except Exception as exc:                          # noqa: BLE001
            lines.append(f"rank fit {key}: walk failed — {exc}")
            continue
        if len(pairs) < MIN_PAIRS:
            if key in store:
                del store[key]
                changed = True
                lines.append(f"rank fit {key}: only {len(pairs):,} pairs — "
                             f"measurement RETIRED (needs {MIN_PAIRS:,})")
            else:
                lines.append(f"rank fit {key}: {len(pairs):,} pairs — needs "
                             f"{MIN_PAIRS:,} before it can claim to rank")
            continue
        got = auc(pairs)
        if got is None:
            lines.append(f"rank fit {key}: one-sided outcomes — no AUC")
            continue
        store[key] = {"auc": round(got, 4), "n": len(pairs),
                      "fitted_at": _dt.date.today().isoformat()}
        changed = True
        from .likely import MIN_RANK_AUC
        word = ("on the board" if got >= MIN_RANK_AUC
                else f"UNDER the {MIN_RANK_AUC} floor — stays off the board")
        lines.append(f"rank fit {key}: AUC {got:.4f} on {len(pairs):,} "
                     f"pairs — {word}")
    if changed:
        _save(store, path)
    for ln in lines:
        log(f"  {ln}")
    return lines
