#!/usr/bin/env python3
"""Every football player market the Odds API hangs, against what this board does with it.

    python3 marketcensus.py            # both leagues, to stdout
    python3 marketcensus.py --write    # rewrites docs/MARKET_CENSUS.md

Ethan, 2026-10-05: "scan for what bets we supply and what bets and markets
we are missing for nfl. This is for most likely bets and edge bets … Make
sure the model we use for most likely bets is actually being used for
every market and bets we select. For CFB and nfl."

TWO TABLES PER LEAGUE, read off the code's own tables rather than typed
from memory, so the day a table changes the census changes with it:

  * THE CENSUS — one row per market the API documents for American
    football: what we call it, whether the request buys it, whether a
    position builds a prop for it, how it is priced, the edge board's
    tier and bar, the Most Likely gate, whether the box score settles
    it, and which harness measured it;
  * THE WIRING — one row per market we build: the base its number starts
    from, the distribution, and which of the chain's measured factors
    have an entry for it (defence transfer, weather, team tendency, the
    usage bridge, the lineup steps, injuries, the fitters' stores). A
    dash is "this factor leaves the number alone for this market", and
    the reason is usually that it was measured and found flat — the
    notes say which.

READS NO BOX STATE. The rank store, the calibration store and the
adopted widths live on the box; this reads the lists that say which
markets those stores are allowed to hold, so the generated document is
the same on every machine and `tests/test_the_market_census_agrees_with_
the_tables.py` can hold the file to it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DOC = ROOT / "docs" / "MARKET_CENSUS.md"

#: The Odds API's documented player markets for American football
#: (americanfootball_nfl / americanfootball_ncaaf), read 2026-10-05. The
#: alternates (`_alternate`) are documented for most over/under markets;
#: the four we buy are listed where the config names them.
API_MARKETS = [
    ("player_pass_yds", "Passing yards"),
    ("player_pass_tds", "Passing touchdowns"),
    ("player_pass_attempts", "Pass attempts"),
    ("player_pass_completions", "Completions"),
    ("player_pass_interceptions", "Interceptions thrown"),
    ("player_pass_longest_completion", "Longest completion"),
    ("player_rush_yds", "Rushing yards"),
    ("player_rush_attempts", "Carries"),
    ("player_rush_longest", "Longest rush"),
    ("player_rush_tds", "Rushing touchdowns"),
    ("player_receptions", "Receptions"),
    ("player_reception_yds", "Receiving yards"),
    ("player_reception_longest", "Longest reception"),
    ("player_reception_tds", "Receiving touchdowns"),
    ("player_rush_reception_yds", "Rushing + receiving yards"),
    ("player_rush_reception_tds", "Rushing + receiving touchdowns"),
    ("player_pass_rush_reception_yds", "Pass + rush + receiving yards"),
    ("player_pass_rush_reception_tds", "Pass + rush + receiving touchdowns"),
    ("player_anytime_td", "Anytime touchdown"),
    ("player_1st_td", "First touchdown"),
    ("player_last_td", "Last touchdown"),
    ("player_tds_over", "Touchdowns over"),
    ("player_kicking_points", "Kicking points"),
    ("player_field_goals", "Field goals"),
    ("player_pats", "Extra points"),
    ("player_sacks", "Sacks"),
    ("player_solo_tackles", "Solo tackles"),
    ("player_tackles_assists", "Tackles + assists"),
    ("player_assists", "Assists"),
    ("player_defensive_interceptions", "Defensive interceptions"),
]

#: Markets the harnesses measure under their own names, by API key.
HARNESS_NAMES = {
    "player_rush_reception_yds": "rush_rec_yds",
    "player_pass_rush_reception_yds": "pass_rush_yds",
    "player_kicking_points": "kick_pts",
    "player_field_goals": "fg_made",
    "player_tackles_assists": "tackles_ast",
}


def _tables():
    from engine.sources import oddsapi as O
    from engine.sources import nflverse as N
    from engine.cfb import props as P
    from engine.sources import cfbstats as CS
    from engine import ingest as I
    from engine import quality as Q
    from engine import likely as L
    from engine import defensevs as D
    from engine import weather as W
    from engine import teamcontext as TC
    from engine import nflusage as U
    from engine import qbchange as QC
    from engine import teammates as TM
    from engine import injuries as INJ
    from engine import rankfit as RF
    from engine.models import MARKET_LABELS, ANYTIME_TD
    import calibrate, formfit, playerfit, marketfit, cfbmarketfit, cfb_build
    return locals()


def _bought(t, sport: str) -> dict:
    """{api key: engine market} for everything this league's request asks for."""
    O = t["O"]
    cfg = O.SPORT_CONFIG[sport]
    out = dict(cfg.get("markets") or {})
    out.update(cfg.get("scorers") or {})
    out.update(cfg.get("alternates") or {})
    if sport == "cfb":
        for k in t["cfb_build"].PLAYER_MARKETS:
            if k not in out:
                out[k] = O.SCORER_ODDS_TO_MARKET.get(k) or O.ALT_ODDS_TO_MARKET.get(k) or O.CFB_ODDS_TO_MARKET.get(k)
    return out


def _built(t, sport: str) -> dict:
    """{engine market: positions} for everything this league's slate builds."""
    if sport == "nfl":
        got: dict = {}
        for pos, markets in t["N"].POSITION_MARKETS.items():
            for m, _r in markets:
                got.setdefault(m, []).append(pos)
        got[t["ANYTIME_TD"]] = ["RB", "WR", "TE"]            # the scorer layer of build_slate
        return got
    P = t["P"]
    # College builds a market for whoever logs it; the position is the
    # roster's role, with `_POSITION` as the fallback for a player with no
    # label. Catch and receiving markets reach every pass-catcher.
    got = {m: (["RB", "WR", "TE"] if m in ("rec_yds", "receptions") else [P._POSITION[m]]) for m in P.MARKETS}
    # A quarterback who logs rushing yards gets the prop too, with his
    # roster label (engine/cfb/props builds a market for whoever logs it;
    # Ethan, 2026-10-10, asking after "those rushing props").
    got["rush_yds"] = ["QB", "RB"]
    got[t["ANYTIME_TD"]] = ["RB", "WR", "TE"]                # engine/cfb/tds
    return got


def _settles(t, sport: str, market: str) -> bool:
    """Does the box score the ingest stores carry this market by name?
    The NFL writes the built markets' columns (nflverse.MARKET_COLUMNS)
    and the usage stats (ingest.NFL_USAGE_MARKETS); college writes every
    market its play feed counts (cfbstats.MARKETS)."""
    if sport == "nfl":
        # The summed markets (nflverse.STAT_SUMS, 2026-10-10) are written
        # by the same ingest under their own names.
        return (market in t["N"].MARKET_COLUMNS or market in t["N"].STAT_SUMS
                or market in t["I"].NFL_USAGE_MARKETS or market == t["ANYTIME_TD"])
    return market in t["CS"].MARKETS or market == t["ANYTIME_TD"]


def _distribution(t, market: str) -> str:
    if market == t["ANYTIME_TD"]:
        return "scorer model (engine/touchdowns, Poisson)"
    if market in t["L"].COUNT_MARKETS:
        return "Poisson (engine/passtd.at_least)"
    if market in ("receptions", "kick_pts", "tackles_ast"):
        return "discrete normal"
    return "normal"


def _most_likely(t, sport: str, market: str) -> str:
    L = t["L"]
    if sport == "nfl":
        auc = L.RANK_AUC.get(market)
        return f"yes — {auc:.3f} (constant, measured)" if auc is not None else "no — no measured figure"
    if market == t["ANYTIME_TD"]:
        return f"yes — {L.CFB_TD_AUC:.3f} (constant, measured)"
    if market in t["RF"].MARKETS.get("cfb", ()):
        return "the box's walk decides (engine/rankfit store, floor 0.60)"
    return "no — not walked"


def _measured(t, sport: str, key: str, market: str | None) -> str:
    name = market or HARNESS_NAMES.get(key)
    if not name:
        return "—"
    if sport == "nfl":
        cands = {m for m, _p, _k in t["marketfit"].CANDIDATES}
        if name in cands:
            return "marketfit.py"
        return "walk-forward constant" if name in t["L"].RANK_AUC else "—"
    cands = {m for m, _p, _k in t["cfbmarketfit"].CANDIDATES}
    return "cfbmarketfit.py" if name in cands else ("rankfit walk" if name in t["RF"].MARKETS.get("cfb", ()) else "—")


def census(t, sport: str) -> list[dict]:
    bought, built = _bought(t, sport), _built(t, sport)
    rows = []
    for key, what in API_MARKETS:
        market = bought.get(key)
        row = {"key": key, "what": what, "market": market or "—",
               "label": t["MARKET_LABELS"].get(market, "—") if market else "—",
               "bought": "yes" + (" (guarded)" if key in t["O"].UNPROVEN_MARKETS else "") if market else "no",
               "built": ", ".join(built[market]) if market and market in built else "—",
               "priced": _distribution(t, market) if market and market in built else "—",
               "edge": "—", "most_likely": "—", "settles": "—",
               "measured": _measured(t, sport, key, market)}
        if market and market in built:
            if market == t["ANYTIME_TD"]:
                row["edge"] = "Long Shots board (its own measured tier)"
            else:
                tier = t["Q"].market_tier(market)
                row["edge"] = f"Tier {tier}, {t['Q'].tier_min_edge(market):.1%} bar"
            row["most_likely"] = _most_likely(t, sport, market)
            row["settles"] = "yes" if _settles(t, sport, market) else "NO"
        rows.append(row)
    # Alternate ladders, as the config names them.
    for key, market in sorted(t["O"].ALT_ODDS_TO_MARKET.items()):
        rows.append({"key": key, "what": f"{t['MARKET_LABELS'].get(market, market)} ladder", "market": market,
                     "label": t["MARKET_LABELS"].get(market, market), "bought": "yes",
                     "built": "rungs on the main prop", "priced": "the main prop's distribution at each rung",
                     "edge": "Most Likely rungs only", "most_likely": "with the main market", "settles": "yes",
                     "measured": "with the main market"})
    return rows


def _defence(t, sport: str, market: str, positions: list[str]) -> str:
    D = t["D"]
    parts = []
    for pos in positions:
        b = D.transfer(pos, market, sport)
        stat = D.stat_for(pos, market) or D.model_stat(pos, market, sport)
        if b:
            parts.append(f"{pos} ×{b:g} on {D.model_stat(pos, market, sport)}")
        elif stat:
            parts.append(f"{pos} shown ({stat}), not in the number")
        else:
            parts.append(f"{pos} no rating")
    return "; ".join(parts)


def _weather(t, market: str) -> str:
    W = t["W"]
    if market == t["ANYTIME_TD"]:
        return "measured (TD_WIND_FORECAST and the rest)"
    if market in W.MARKETS:
        keys = [k for k in W.WIND_FORECAST if k[0] == market]
        return "measured wind/rain/cold" + (f" ({', '.join(g for _m, g in keys)})" if keys else "")
    return "—"


def _context(t, market: str) -> str:
    TC = t["TC"]
    if market in TC.PASS_MARKETS:
        return "pace + PROE (pass)"
    if market in TC.RUSH_MARKETS:
        return "pace + PROE (rush)"
    return "pace only"


def _lineup(t, market: str, sport: str = "nfl") -> str:
    if sport == "cfb":
        # College's own fit (engine/cfb/lineup) on college games, the NFL's
        # rule; which cases apply is the box's store. Touchdowns too: the
        # college scorer board applies them itself (cfb/tds.lineup_step).
        from engine.cfb import lineup as _clu
        if any(market == m for rows in _clu.MARKETS.values() for m, _f in rows):
            return "QB change, teammate out (college's own fit; the box's store decides)"
        return "—"
    got = []
    if any(k[0] == market for k in t["QC"].EFFECT):
        got.append("QB change")
    if any(k[0] == market for k in list(t["TM"].EFFECT) + list(t["TM"].EFFECT_SNAPS)):
        got.append("teammate out")
    return ", ".join(got) or "—"


def _injuries(t, market: str) -> str:
    rules = [r.key for r in t["INJ"].KNOCK_ONS if market in r.markets]
    return ", ".join(rules) or "—"


def _fitters(t, sport: str, market: str) -> str:
    got = []
    for name, mod in (("calibration", t["calibrate"]), ("form weights", t["formfit"]), ("player memory", t["playerfit"])):
        if market in mod.SPORT_MARKETS.get(sport, ()):
            got.append(name)
    return ", ".join(got) or "—"


def wiring(t, sport: str) -> list[dict]:
    built = _built(t, sport)
    rows = []
    for market, positions in built.items():
        if market == t["ANYTIME_TD"]:
            base = "touchdown model (engine/touchdowns: rate × red-zone chances, script)"
        elif market == "pass_int":
            base = "rate model (engine/passint: picks per attempt × projected attempts)"
        else:
            base = "form blend" + (" + usage bridge" if sport == "nfl" and market in t["U"].OPP_BY_MARKET else "")
        rows.append({"market": market, "positions": ", ".join(positions), "base": base,
                     "distribution": _distribution(t, market),
                     "defence": _defence(t, sport, market, positions),
                     "weather": _weather(t, market),
                     # Only the NFL build prices the context layer (engine/teamcontext
                     # needs the play-by-play profiles); college never passes it.
                     "context": _context(t, market) if sport == "nfl" else "— (college does not price it)",
                     "usage": "yes" if sport == "nfl" and market in t["U"].OPP_BY_MARKET else "—",
                     "lineup": _lineup(t, market, sport), "injuries": _injuries(t, market),
                     "fitters": _fitters(t, sport, market),
                     "most_likely": _most_likely(t, sport, market)})
    return rows


def findings(t) -> list[str]:
    out = []
    for sport in ("nfl", "cfb"):
        bought, built = _bought(t, sport), _built(t, sport)
        for key, market in bought.items():
            if market and market not in built and key not in t["O"].ALT_ODDS_TO_MARKET:
                out.append(f"{sport}: `{key}` is bought and no position builds `{market}`")
        for market in built:
            if market not in bought.values():
                out.append(f"{sport}: `{market}` is built and never bought — proxy lines only")
            if not _settles(t, sport, market):
                out.append(f"{sport}: `{market}` is built and the box score cannot settle it")
            if market != t["ANYTIME_TD"] and market not in t["MARKET_LABELS"]:
                out.append(f"{sport}: `{market}` has no label")
    # Market sets spelled in words no market answers to.
    names = set(t["MARKET_LABELS"]) | {t["ANYTIME_TD"]}
    for word in sorted((t["TC"].PASS_MARKETS | t["TC"].RUSH_MARKETS) - names):
        out.append(f"engine/teamcontext names `{word}`, which is no market of this board "
                   f"(the pass-rate tilt never reaches it)")
    return out


def _table(rows: list[dict], cols: list[tuple[str, str]]) -> list[str]:
    head = "| " + " | ".join(h for _k, h in cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(str(r.get(k, "")) for k, _h in cols) + " |" for r in rows]
    return [head, sep, *body]


CENSUS_COLS = [("key", "API key"), ("what", "What it is"), ("market", "Our market"), ("bought", "Bought"),
               ("built", "Built for"), ("priced", "Priced as"), ("edge", "Edge board"),
               ("most_likely", "Most Likely"), ("settles", "Settles"), ("measured", "Measured by")]
WIRING_COLS = [("market", "Market"), ("positions", "Positions"), ("base", "Base"), ("distribution", "Distribution"),
               ("defence", "Defence (matchup step)"), ("weather", "Weather"), ("context", "Team tendency"),
               ("usage", "Usage bridge"), ("lineup", "Lineup"), ("injuries", "Injury knock-ons"),
               ("fitters", "Self-tuning stores"), ("most_likely", "Most Likely")]


def render() -> str:
    t = _tables()
    out = ["# Market census — generated, do not hand-edit", "",
           "Generated by `python3 marketcensus.py --write` from the code's own tables.",
           "`tests/test_the_market_census_agrees_with_the_tables.py` holds this file to them.", "",
           "Ethan, 2026-10-05: \"scan for what bets we supply and what bets and markets we are",
           "missing for nfl. This is for most likely bets and edge bets … Make sure the model we",
           "use for most likely bets is actually being used for every market and bets we select.\"", "",
           "**How to read it.** *Bought* is on the Odds API request (\"guarded\": dropped and",
           "retried if the API refuses the key). *Built for* is the positions a prop is built for.",
           "*Edge board* is `engine/quality`'s tier and post-haircut bar. *Most Likely* is the",
           "measured ranking gate (`likely.MIN_RANK_AUC` 0.60): the NFL's figures are constants",
           "from the box's harness, college's come from the box's own walk. *Settles* is whether",
           "the box score carries the stat. The wiring table lists which of the one projection",
           "chain's factors have an entry for each market — every market runs the same chain",
           "(`engine/projection.build_projection` → `engine/betting.evaluate_prop` →",
           "`engine/likely.from_prop`); a dash means that factor leaves the number alone, almost",
           "always because it was measured and found flat (the module's own notes say which).", ""]
    for sport, name in (("nfl", "NFL"), ("cfb", "College football")):
        out += [f"## {name}", "", "### The census", ""]
        out += _table(census(t, sport), CENSUS_COLS)
        out += ["", "### The wiring", ""]
        out += _table(wiring(t, sport), WIRING_COLS)
        out += [""]
    out += ["## Findings", ""]
    got = findings(t)
    out += [f"- {f}" for f in got] or ["- none"]
    out += ["", "## What is not bought, and why", "",
            "- **Longest completion / rush / reception, first and last touchdown, touchdowns over:** "
            "no model, no measurement; a book's vig on a longest-play market is the widest on the menu.",
            "- **Sacks, solo tackles, assists and defensive interceptions:** no harness arm yet. "
            "(Rushing + receiving yards, pass + rush + receiving yards, kicking points, field goals "
            "and tackles + assists were measured by `marketfit.py` and bought on 2026-10-10, NFL only.)",
            "- **Rushing / receiving / pass-rush-receiving touchdowns:** the anytime-touchdown model "
            "already prices the scorer; the split markets are the same event at worse prices.", ""]
    return "\n".join(out) + "\n"


def main(argv) -> int:
    text = render()
    if "--write" in argv:
        DOC.write_text(text, encoding="utf-8")
        print(f"wrote {DOC}")
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
