"""The matchup card under a baseball pick, in the shape every league's takes.

Ethan, 2026-10-14: "make sure all sports have the same most likely screens
with same type of info and info is being used how it should be." The NFL,
college and NBA picks each carried a card saying what tonight's opponent
gives up — per game, against the league, and where that ranks — and what
the model did with it (engine/defensevs, engine/hoopsdvp). A baseball pick
had none, though the box stores every plate appearance of the season
(engine/mlb/charts, the hit tracker's table).

WHAT IT SAYS. For a hitter's hits, total bases or home runs: what tonight's
opposing staff allows a game in that stat. For a pitcher's strikeouts: how
often tonight's opposing lineup strikes out a game. Each beside the league's
per-game rate and its rank among the clubs with MIN_GAMES or more (1st gives
up, or strikes out, the most), this season — last season's while this one
has fewer than MIN_GAMES. The staff's line is the WHOLE staff's: tonight's
starter is the projection's own business (engine/mlb/matchup).

WHAT THE MODEL DID, said under it from the row's own chain (engine/chain):
the Matchup step's move and why — the starter's hand and what he allows to
this side, the bullpen, the lineup's strikeout rate — or that the learned
model sets that weight. The staff line on the card is context: nothing here
moves a number.

Standard library only.
"""

from __future__ import annotations

from .charts import HIT_BASES, STRIKEOUTS

#: market → (whose numbers, the words on the card)
MARKETS = {"hits": ("staff", "hits allowed"), "total_bases": ("staff", "total bases allowed"),
           "home_runs": ("staff", "home runs allowed"), "strikeouts": ("lineup", "strikeouts")}
#: A club needs this many games before it is ranked, and a season this
#: many before it is read instead of the last.
MIN_GAMES = 5


def table(conn, season: int) -> dict:
    """``{club: {"games": n, "staff": {market: per game}, "lineup":
    {"strikeouts": per game}}}`` off one season's stored plate appearances.
    A plate appearance's ``team`` is the side batting and ``opponent`` the
    side in the field."""
    staff: dict = {}
    bat: dict = {}
    for gpk, team, opp, et in conn.execute(
            "SELECT game_pk, team, opponent, event_type FROM mlb_pa WHERE season=?", (int(season),)):
        if opp:
            s = staff.setdefault(opp, {"g": set(), "hits": 0, "total_bases": 0, "home_runs": 0})
            s["g"].add(gpk)
            b = HIT_BASES.get(et or "", 0)
            s["hits"] += 1 if b else 0
            s["total_bases"] += b
            s["home_runs"] += 1 if et == "home_run" else 0
        if team:
            t = bat.setdefault(team, {"g": set(), "strikeouts": 0})
            t["g"].add(gpk)
            t["strikeouts"] += 1 if et in STRIKEOUTS else 0
    out: dict = {}
    for club in set(staff) | set(bat):
        s, t = staff.get(club), bat.get(club)
        g = max(len(s["g"]) if s else 0, len(t["g"]) if t else 0)
        out[club] = {"games": g,
                     "staff": ({m: s[m] / len(s["g"]) for m in ("hits", "total_bases", "home_runs")}
                               if s and s["g"] else {}),
                     "lineup": ({"strikeouts": t["strikeouts"] / len(t["g"])} if t and t["g"] else {})}
    return out


def _matchup_step(row: dict) -> tuple:
    steps = ((row or {}).get("chain") or {}).get("steps") or []
    for s in steps:
        if s.get("key") == "learned":
            return None, "learned"
    for s in steps:
        if s.get("key") == "matchup" and s.get("mult") is not None:
            return float(s["mult"]), str(s.get("why") or "")
    return None, ""


def note(row: dict) -> str:
    """What the model did with tonight's matchup, off the row's chain."""
    mult, why = _matchup_step(row)
    if why == "learned":
        return ("Shown for you. The learned model sets this number's matchup weight; "
                "the staff's line here is context.")
    if mult is None:
        return "Shown for you. The model has no matchup step for this market."
    pct = round((mult - 1) * 100)
    moved = (f"moved this projection {'+' if pct > 0 else ''}{pct}%" if pct
             else "left this projection where it was")
    return f"Model: tonight's matchup {moved}" + (f" — {why}" if why else "") + ". The staff's line is context."


def card(row: dict, tables: dict, season: int) -> dict | None:
    """The card for one pick row, or None where the market or the club has
    no number. ``tables`` is ``{season: table(...)}`` for this season and
    the last."""
    market = str((row or {}).get("market") or "")
    opp = str((row or {}).get("opponent") or "")
    if market not in MARKETS or not opp:
        return None
    side, words = MARKETS[market]
    last = False
    tbl = tables.get(season) or {}
    if (tbl.get(opp) or {}).get("games", 0) < MIN_GAMES:
        tbl, last = tables.get(season - 1) or {}, True
    pool = {c: v[side][market] for c, v in tbl.items()
            if v.get("games", 0) >= MIN_GAMES and market in (v.get(side) or {})}
    if opp not in pool:
        return None
    order = sorted(pool, key=lambda c: -pool[c])
    league = sum(pool.values()) / len(pool)
    per = pool[opp]
    rnd = 2 if market == "home_runs" else 1
    games = tbl[opp]["games"]
    who = "lineup" if side == "lineup" else "staff"
    out = {"opponent": opp, "stat": words, "per_game": round(per, rnd), "league": round(league, rnd),
           "rank": order.index(opp) + 1, "of": len(order), "games": games,
           "text": (f"{opp}'s {who}: {per:.{rnd}f} {words} a game, the {_ord(order.index(opp) + 1)}-most of "
                    f"{len(order)} (league {league:.{rnd}f}), {'last season' if last else f'over {games} games'}"),
           "note": note(row)}
    if last:
        out["last_season"] = True
    return out


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def attach(conn, rows, season: int) -> int:
    """Hang ``matchup_card`` on every pick row whose market and opponent
    have a number. Returns how many carry one; never raises on a strange
    row."""
    tables = {season: table(conn, season), season - 1: table(conn, season - 1)}
    n = 0
    for r in rows or []:
        if not isinstance(r, dict) or r.get("matchup_card"):
            continue
        c = card(r, tables, season)
        if c:
            r["matchup_card"] = c
            n += 1
    return n
