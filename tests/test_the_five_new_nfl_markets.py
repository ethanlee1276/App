"""Five NFL markets the books hang, added end to end: pass + rush yards,
rush + rec yards, kicking points, field goals made, tackles + assists.

Ethan, 2026-10-10: "Yes add all of them." Each was measured before it was
added (marketfit.py, walk-forward on the 2021-2025 box scores, held-out
2025): field goals 0.700, a quarterback's passing + rushing yards 0.683,
kicking points 0.673, a back's rushing + receiving yards 0.629, a
defender's tackles + assists 0.621 — every one above likely.MIN_RANK_AUC.

These check, one rule each: a summed market's number is the sum of its
columns (and a kicker's points weight a field goal at three); a kicker and
a defender are board positions, ranked on kicks and on tackles, one kicker
and three defenders a team; the quarterback and the back get their combo
markets, and a back with a handful of touches gets no combo line; a relief
appearance is not a quarterback's game; the ingest stores the five so they
settle, and writes no usage or touchdown rows for kickers and defenders;
the odds keys are on the NFL's request only, behind the guard, and the
credit meter counts them; each is priced on the right distribution, tiered
on the edge board, ranked on Most Likely with its measured figure and
shelved; no kicker or defender gets an anytime-touchdown prop.

Run directly: `python3 tests/test_the_five_new_nfl_markets.py`
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import nflverse as N                            # noqa: E402

FIVE = ("pass_rush_yds", "rush_rec_yds", "kick_pts", "fg_made", "tackles_ast")


def _row(wk, name, pos, group="", team="BUF", **cols):
    r = {"season_type": "REG", "week": str(wk), "recent_team": team, "opponent_team": "MIA",
         "position": pos, "position_group": group or pos, "player_display_name": name}
    r.update({k: str(v) for k, v in cols.items()})
    return r


def _team(weeks=(1, 2, 3, 4)):
    rows = []
    for wk in weeks:
        rows.append(_row(wk, "Quarter Back", "QB", attempts=32, passing_yards=250, rushing_yards=30,
                         receiving_yards=0))
        rows.append(_row(wk, "Lead Back", "RB", carries=16, targets=3, rushing_yards=70, receiving_yards=20))
        rows.append(_row(wk, "Third Back", "RB", carries=2, targets=0, rushing_yards=6, receiving_yards=2))
        rows.append(_row(wk, "Kicker One", "K", "SPEC", fg_att=3, pat_att=3, fg_made=2, pat_made=3))
        for i, (pos, grp, tk) in enumerate((("LB", "LB", 9), ("SAF", "DB", 7), ("CB", "DB", 5),
                                            ("DE", "DL", 2))):
            rows.append(_row(wk, f"Defender {i}", pos, grp, def_tackles_solo=tk, def_tackle_assists=2))
    return rows


def test_a_summed_market_is_the_sum_of_its_columns():
    qb = _row(1, "Q", "QB", passing_yards=250, rushing_yards=30, receiving_yards=4)
    assert N.stat_value(qb, "pass_rush_yds") == 284, "the book's own sum: passing + rushing + receiving"
    assert N.stat_value(_row(1, "R", "RB", rushing_yards=70, receiving_yards=20), "rush_rec_yds") == 90
    k = _row(1, "K", "K", "SPEC", fg_made=2, pat_made=3)
    assert N.stat_value(k, "kick_pts") == 9, "three a field goal, one an extra point"
    assert N.stat_value(k, "fg_made") == 2
    d = _row(1, "D", "LB", def_tackles_solo=6, def_tackle_assists=3)
    assert N.stat_value(d, "tackles_ast") == 9
    assert N.stat_value(_row(1, "D", "LB", def_tackles_solo=6, def_tackles_with_assist=3), "tackles_ast") == 9, \
        "the older schema's spelling"
    assert N.stat_value(_row(1, "Q", "QB", passing_yards=250), "pass_rush_yds") == 250, "a missing part is zero"


def test_kickers_and_defenders_are_board_positions_ranked_on_their_own_work():
    assert N.board_position(_row(1, "K", "K", "SPEC")) == "K"
    for pos, grp in (("LB", "LB"), ("SAF", "DB"), ("CB", "DB"), ("DT", "DL")):
        assert N.board_position(_row(1, "D", pos, grp)) == "DEF"
    assert N.board_position(_row(1, "Q", "QB")) == "QB"
    specs = N.top_players_for_week(_team(), {"BUF"}, 5)
    got = {(s.player, s.market) for s in specs}
    assert ("Kicker One", "kick_pts") in got and ("Kicker One", "fg_made") in got
    tacklers = sorted(p for p, m in got if m == "tackles_ast")
    assert tacklers == ["Defender 0", "Defender 1", "Defender 2"], "the team's top three by tackles"
    assert ("Quarter Back", "pass_rush_yds") in got and ("Lead Back", "rush_rec_yds") in got
    assert sum(1 for s in specs if s.position == "K") == 2, "one kicker, two markets"


def test_a_back_with_a_handful_of_touches_gets_no_combo_line():
    assert N.is_secondary("RB", "rush_rec_yds") and N.SECONDARY_FLOOR["rush_rec_yds"] == 20.0
    assert not N.is_secondary("K", "kick_pts"), "a kicker's points are his own market"


def test_a_relief_appearance_is_not_a_quarterbacks_game():
    rows = _team() + [_row(5, "Quarter Back", "QB", attempts=3, passing_yards=20, rushing_yards=0)]
    logs = N.player_game_logs(rows, "Quarter Back", "pass_rush_yds", 6)
    assert [g.value for g in logs] == [280.0] * 4, "three attempts in mop-up is not a start"


def test_the_ingest_stores_the_five_so_they_settle():
    from engine.ingest import nfl_player_log_rows, nfl_usage_rows, nfl_td_rows
    rows = _team(weeks=(1,))
    got = {(r["player"], r["market"]): r["value"] for r in nfl_player_log_rows(rows, 2026)}
    assert got[("Kicker One", "kick_pts")] == 9 and got[("Kicker One", "fg_made")] == 2
    assert got[("Defender 0", "tackles_ast")] == 11
    assert got[("Quarter Back", "pass_rush_yds")] == 280 and got[("Lead Back", "rush_rec_yds")] == 90
    pos = {r["player"]: r["position"] for r in nfl_player_log_rows(rows, 2026)}
    assert pos["Kicker One"] == "K" and pos["Defender 1"] == "DEF"
    usage = {r["player"] for r in nfl_usage_rows(rows, 2026)}
    tds = {r["player"] for r in nfl_td_rows(rows, 2026)}
    assert "Kicker One" not in usage and "Defender 0" not in usage, "no usage rows for kickers and defenders"
    assert "Kicker One" not in tds and "Defender 0" not in tds


def test_the_keys_are_on_the_nfls_request_behind_the_guard_and_metered():
    from engine.sources import oddsapi as O
    from engine import oddsbudget as B
    keys = {"player_pass_rush_reception_yds": "pass_rush_yds", "player_rush_reception_yds": "rush_rec_yds",
            "player_kicking_points": "kick_pts", "player_field_goals": "fg_made",
            "player_tackles_assists": "tackles_ast"}
    for k, m in keys.items():
        assert O.NFL_ODDS_TO_MARKET[k] == m
        assert k in O.UNPROVEN_MARKETS, "dropped and retried if the API refuses it"
        assert k not in O.CFB_ODDS_TO_MARKET, "college has no kicking or tackle columns to price them"
    cfg = O.SPORT_CONFIG["nfl"]
    assert B.EVENT_CREDITS["nfl"] == len(cfg["markets"]) + len(cfg["scorers"]) + len(cfg["alternates"]) + 3 == 22


def test_an_unnamed_refusal_drops_the_new_keys_before_the_proven_ones():
    """The API refuses a request without naming a key: the five new keys
    go first. Passing touchdowns, the volume markets and interceptions
    have been served since September and stay on the request."""
    from engine.sources import oddsapi as O
    asked = []

    def fake(url, name, ttl=300, cache_only=False):
        import urllib.parse
        markets = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["markets"][0].split(",")
        asked.append(markets)
        if any(m in O.NEW_PROP_ODDS_KEYS for m in markets):
            raise O.OddsAPIError("422 Unprocessable Entity: invalid market")
        return {}, None

    real, O._request = O._request, fake
    before = set(O.REJECTED_MARKETS)
    try:
        O.fetch_event_odds("evt", api_key="k", sport="nfl")
    finally:
        O._request = real
        O.REJECTED_MARKETS.clear()
        O.REJECTED_MARKETS.update(before)
    assert len(asked) == 2, asked
    kept = set(asked[1])
    assert not kept & set(O.NEW_PROP_ODDS_KEYS)
    assert {"player_pass_tds", "player_pass_attempts", "player_pass_interceptions"} <= kept, \
        "a refusal of the new keys must not take the proven ones with it"


def test_each_is_priced_tiered_ranked_and_shelved():
    from engine import likely, quality, parlays, boards
    from engine.models import MARKET_LABELS
    src = open(os.path.join(ROOT, "engine", "betting.py"), encoding="utf-8").read()
    assert "prop.market in (PASS_TD, PASS_INT, FG_MADE)" in src, "field goals: Poisson at the half"
    assert "prop.market in (RECEPTIONS, KICK_PTS, TACKLES_AST)" in src, "whole numbers: discrete"
    measured = {"fg_made": 0.700, "pass_rush_yds": 0.683, "kick_pts": 0.673, "rush_rec_yds": 0.629,
                "tackles_ast": 0.621}
    for m in FIVE:
        assert likely.RANK_AUC[m] == measured[m] and measured[m] >= likely.MIN_RANK_AUC
        assert m in quality.MARKET_TIER and m in quality.VOLATILITY
        assert m in parlays.TIER and m in parlays.FAMILY
        assert m in MARKET_LABELS
        assert any(m in mk for _k, _t, mk, _w in boards.FOOTBALL_SHELVES), m
    assert quality.MARKET_TIER["fg_made"] == 3, "a small count, quarantined with the other counts"
    assert "fg_made" in likely.COUNT_MARKETS


def test_no_kicker_or_defender_gets_an_anytime_touchdown_prop():
    src = open(os.path.join(ROOT, "engine", "sources", "nflverse.py"), encoding="utf-8").read()
    i = src.index("seen_td: set[tuple[str, str]] = set()")
    body = src[i:i + 900]
    assert "if p.position not in OFFENSE_POSITIONS:" in body and "PASS_RUSH_YDS" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
