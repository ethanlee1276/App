"""A quarterback's carries are on the NFL board, measured first.

Ethan, 2026-10-14, "do 1-11", to the call "Quarterback carries on the board
itself? The read prices them from his own games, but the board doesn't
build a carries line for quarterbacks ... Adding them would need the market
measured first (marketfit), as the other five were": yes.

Measured in marketfit.py's own harness and bar (ranking AUC less one
standard error at 0.60 or more, held out): 0.645 ± 0.027 on 2025 (n 503) and
0.632 ± 0.023 on 2024 (n 515). So his carries joined his list
(sources/nflverse.POSITION_MARKETS), built from his real games this season
only, three or more — the population the harness scored — with no carry-in
and no last-season anchor, both measured on backs.

    python3 tests/test_quarterback_carries_are_on_the_board.py
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import carry as C                                        # noqa: E402
from engine.models import Game, Weather, RUSH_ATT                    # noqa: E402
from engine.sources import nflverse as nv                            # noqa: E402


def _row(player, wk, att, carries, team="NYG", pos="QB", season=2026):
    return {"season": str(season), "week": str(wk), "season_type": "REG", "player_display_name": player,
            "position": pos, "recent_team": team, "opponent_team": "DAL" if team == "NYG" else "NYG",
            "attempts": str(att), "completions": str(int(att * 0.62)), "passing_yards": str(att * 7),
            "passing_tds": "1", "interceptions": "0", "carries": str(carries), "rushing_yards": str(carries * 5),
            "targets": "0", "receptions": "0", "receiving_yards": "0"}


def _slate(current):
    games = [Game(home="NYG", away="DAL", weather=Weather(dome=True), injuries=[], date="2026-10-11",
                  kickoff="13:00", spread=-3.0, total=44.5)]
    names = {r["player_display_name"]: r["recent_team"] for r in current}
    saved = {n: getattr(nv, n) for n in ("build_games", "load_weekly_stats", "roster_index", "roster_teams",
                                         "load_schedules")}
    nv.build_games = lambda s, w: games
    nv.load_weekly_stats = lambda s: current if s == 2026 else []
    nv.roster_index = lambda s: {}
    nv.roster_teams = lambda s: names
    nv.load_schedules = lambda: []
    try:
        return nv.build_slate(2026, 6)
    finally:
        for n, fn in saved.items():
            setattr(nv, n, fn)


def test_his_carries_are_one_of_his_markets_and_the_harness_names_them():
    assert RUSH_ATT in [m for m, _r in nv.POSITION_MARKETS["QB"]]
    assert [m for m, _r in nv.POSITION_MARKETS["QB"]][-1] == RUSH_ATT, "on the end: his own market stays first"
    assert not nv.is_secondary("QB", RUSH_ATT), "no floor: the harness scored every starter, and no line, no prop"
    import marketfit
    assert ("rush_att", "QB", "ou") in marketfit.CANDIDATES
    from engine import slipread
    assert "rush_att" in slipread.POSITION_MARKETS_NFL["QB"]
    for pos, markets in nv.POSITION_MARKETS.items():
        if pos in slipread.POSITION_MARKETS_NFL:
            assert tuple(m for m, _r in markets) == slipread.POSITION_MARKETS_NFL[pos], pos


def test_a_spec_with_no_position_still_reads_carries_as_a_backs():
    """The table opens with the quarterback; carries are a back's second
    market and his eighth, so the fallback must not change hands."""
    assert nv.position_of(RUSH_ATT) == "RB"
    want = {"pass_yds": "QB", "pass_td": "QB", "pass_att": "QB", "pass_cmp": "QB", "pass_int": "QB",
            "pass_rush_yds": "QB", "rush_yds": "RB", "rush_rec_yds": "RB", "rec_yds": "WR", "receptions": "TE",
            "kick_pts": "K", "fg_made": "K", "tackles_ast": "DEF", "rush_att": "RB"}
    assert {m: nv.position_of(m) for m in want} == want


def test_a_starter_with_three_real_games_gets_a_carries_prop_off_those_games():
    current = [_row("Run Arm", w, 30, 5 + w) for w in range(1, 6)]
    current += [_row("Cold Arm", w, 32, 1, team="DAL") for w in range(1, 6)]
    slate = _slate(current)
    carries = {p.player: p for p in slate.props if p.market == RUSH_ATT}
    assert "Run Arm" in carries and "Cold Arm" in carries, sorted(carries)
    p = carries["Run Arm"]
    assert p.position == "QB" and [g.value for g in p.logs] == [10.0, 9.0, 8.0, 7.0, 6.0]
    assert p.lines and p.lines[0].book == "proxy"
    assert getattr(p, "form_prior_kind", "") != "season", "no last-season anchor on his carries"


def test_a_relief_appearance_never_counts_and_two_real_games_are_not_enough():
    current = [_row("New Starter", w, 31, 6) for w in (4, 5)]
    current += [_row("New Starter", 2, 4, 3)]                     # kneel-downs in relief
    current += [_row("Vet Arm", w, 33, 4, team="DAL") for w in range(1, 6)]
    slate = _slate(current)
    carries = {p.player for p in slate.props if p.market == RUSH_ATT}
    assert "New Starter" not in carries and "Vet Arm" in carries, carries
    starter, relief = _row("X", 1, 31, 6), _row("X", 1, 4, 3)
    assert nv.quarterbacked(starter, RUSH_ATT) and not nv.quarterbacked(relief, RUSH_ATT)
    assert nv.quarterbacked(_row("Back", 1, 0, 14, pos="RB"), RUSH_ATT), "a back's carries are his, whatever he throws"


def test_the_last_season_anchor_stays_where_it_was_measured():
    assert C.SEASON_PRIOR_POSITIONS["rush_att"] == ("RB",)
    assert C.prior_measured("rush_att", "RB") and not C.prior_measured("rush_att", "QB")
    assert C.prior_measured("rush_yds", "QB") and C.prior_measured("receptions", "TE")
    prior = [_row("Run Arm", w, 30, 8, season=2025) for w in range(1, 15)]
    back = [_row("Bell Cow", w, 0, 18, pos="RB", season=2025) for w in range(1, 15)]
    assert nv.season_anchor(prior, RUSH_ATT, position="QB") is None
    got = nv.season_anchor(back, RUSH_ATT, position="RB")
    assert got and got["anchor"] == 18.0 and got["k"] == C.SEASON_PRIOR_GAMES["rush_att"]
    assert nv.season_anchor(back, RUSH_ATT) == got, "no position given: as before"


def test_the_nightly_stores_his_carries_so_they_settle():
    from engine.ingest import nfl_player_log_rows
    rows = nfl_player_log_rows([_row("Run Arm", 3, 30, 9)], 2026)
    got = {r["market"]: r["value"] for r in rows}
    assert got.get(RUSH_ATT) == 9.0, got


def test_the_runbook_says_so():
    doc = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert "A quarterback's carries are on the NFL board" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
