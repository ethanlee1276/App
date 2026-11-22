"""Ethan's answers of 21 November to the open decisions (step AAJ).

"1. Fewer so we don't force anything. 2. No 3. Yes 4. No until commands
5. Yes only shit that actually hold 6. Yes 7. Yes 8. Yes 9. Yes"

1, 2 and 4 keep the site as it was (a game short of three three-leg tickets
posts fewer; hockey's goal scorers stay on its stat tickets; no college
basketball prop is priced off a ladder alone). 5 is
tests/test_football_matchup_counts_the_models_own_step.py and 7
tests/test_the_nfl_board_is_tightened.py. Here: 3, a parlay one book prices
whole is chosen first; 6, v3.1's "no pass-catcher legs behind a new
quarterback too green to rate" reaches college; 8, the record may raise an
NBA or NHL chance toward its price.
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP          # noqa: E402
from engine import likelycal as LC            # noqa: E402
from engine.cfb import qbchange as CQ         # noqa: E402

SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")


# --- 3. a parlay one book prices whole, first ---------------------------------------------------
def _leg(player, line, side="OVER", market="receptions", book="", odds=None):
    return {"player": player, "market": market, "side": side, "line": line, "book": book, "odds": odds}


def _index(rows):
    from engine.sliplive import _key
    out = {}
    for player, market, quotes in rows:
        out[(_key(player), market)] = {"quotes": quotes}
    return out


def test_a_ticket_one_book_has_whole_ranks_ahead_of_one_no_book_has():
    index = _index([
        ("A One", "receptions", [(4.5, "DraftKings", -150, 120), (4.5, "FanDuel", -145, 115)]),
        ("B Two", "receptions", [(3.5, "DraftKings", -160, 125)]),
        ("C Three", "receptions", [(5.5, "FanDuel", -140, 110)]),
    ])
    rank = GP.book_ranker(index)
    whole = {"legs": [_leg("A One", 4.5), _leg("B Two", 3.5)]}          # DraftKings has both
    split = {"legs": [_leg("B Two", 3.5), _leg("C Three", 5.5)]}        # no one book has both
    unknown = {"legs": [_leg("A One", 4.5), _leg("Nobody", 2.5)]}       # a leg with nothing on file
    assert (rank(whole), rank(unknown), rank(split)) == (0, 1, 2)
    # Off its switch, or with no quotes on the board, every ticket ranks the same (as before).
    os.environ["QB_ONE_BOOK_FIRST"] = "off"
    try:
        assert GP.book_ranker(index) is None
    finally:
        os.environ.pop("QB_ONE_BOOK_FIRST", None)
    assert GP.book_ranker({}) is None


def test_the_builder_asks_it_ahead_of_our_chance_and_after_the_reports_own_picks():
    assert 'first = lambda t: (br(t), -float(t["joint"]), -(t.get("ev_at_naive") or -9))' in SRC
    assert "chosen = choose(strong3, spec[\"n\"], rank=first, keep=keep, shared=shared, prior=prior_uses)" in SRC
    # A fill keeps the report's own picks first (`outside`), then one book, then the chance.
    assert 'rank = lambda t: (outside(t), br(t), -float(t["joint"]), -(t.get("ev_at_naive") or -9))' in SRC
    # Both paths hand it in: the board build and the report's own picks.
    assert "books = book_ranker(index, carried)" in SRC
    assert "books = book_ranker(quote_index(board), carried_picks(board))" in SRC


def test_a_posted_ticket_still_stays_ahead_of_a_new_one_book_ticket():
    # `choose` puts the tickets posted last build first, whatever the rank (ZQ: a posted
    # ticket stays until a leg breaks); the one-book rank orders only the places left.
    body = SRC[SRC.index("def _choose("):SRC.index("def backups(")]
    assert "ranked = [first[i] for i in sorted(first)] + [t for t in ranked if id(t) not in held]" in body


# --- 6. a new college quarterback too green to rate ----------------------------------------------
def _conn(rows):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, team TEXT, player TEXT, period TEXT,"
              " market TEXT, value REAL)")
    c.executemany("INSERT INTO player_game_logs VALUES ('cfb', ?, ?, ?, ?, ?, ?)", rows)
    return c


def test_a_college_replacement_under_fifty_passes_is_unrated_and_one_over_is_not():
    rows = []
    for wk in range(1, 9):                                   # the starter: 8 games, 30 passes each
        rows += [(2026, "UGA", "Starter Guy", f"2026-W{wk:02d}", "pass_yds", 250),
                 (2026, "UGA", "Starter Guy", f"2026-W{wk:02d}", "pass_att", 30)]
    rows += [(2026, "UGA", "Green Guy", "2026-W03", "pass_yds", 40), (2026, "UGA", "Green Guy", "2026-W03", "pass_att", 6)]
    for wk in range(1, 9):
        rows += [(2026, "LSU", "Lsu Starter", f"2026-W{wk:02d}", "pass_yds", 240),
                 (2026, "LSU", "Lsu Starter", f"2026-W{wk:02d}", "pass_att", 28)]
    rows += [(2025, "LSU", "Veteran Backup", "2025-W05", "pass_yds", 900), (2025, "LSU", "Veteran Backup", "2025-W05", "pass_att", 120),
             (2026, "LSU", "Veteran Backup", "2026-W04", "pass_yds", 60), (2026, "LSU", "Veteran Backup", "2026-W04", "pass_att", 10)]
    conn = _conn(rows)
    qb = CQ.passers(conn, 2026, ["UGA", "LSU"])
    assert qb["UGA"]["attempts"]["Green Guy"] == 6
    assert qb["LSU"]["attempts"]["Veteran Backup"] == 130, "his passes last season count too"
    out = [SimpleNamespace(team="UGA", player="Starter Guy", status="OUT"),
           SimpleNamespace(team="LSU", player="Lsu Starter", status="OUT")]
    ch = CQ.changes(qb, out, {})
    assert ch["UGA"]["replacement"] == "Green Guy" and ch["UGA"]["replacement_attempts"] == 6
    green = CQ.card(ch["UGA"])
    assert green.get("unrated") is True, "the NFL's rule (v3.1 §8) reaches college"
    assert "has 6 pass attempts in our data — too few to rate" in green["detail"]
    vet = CQ.card(ch["LSU"])
    assert ch["LSU"]["replacement_attempts"] == 130 and "unrated" not in vet
    assert vet["detail"].endswith("has 130 pass attempts in our data"), vet["detail"]
    # A count the logs never took says nothing (no mark either way).
    ch["UGA"]["replacement_attempts"] = None
    assert "unrated" not in CQ.card(ch["UGA"])


def test_the_board_reads_the_mark_for_college_as_for_the_nfl():
    from engine import likelyboard as B
    assert "cfb" in B.METHOD_SPORTS
    r = {"kind": "prop", "player": "Catcher", "market": "receptions", "side": "OVER", "position": "WR",
         "qb_card": {"unrated": True}}
    assert B.METHOD_NEW_QB in B.method_fails(r, "cfb")


# --- 8. the record may raise an NBA or NHL chance -----------------------------------------------
def test_the_shrink_raises_toward_the_price_only_where_allowed():
    assert LC.shrink(0.57, 0.66, 0.5, up=True) > 0.57
    assert abs(LC.shrink(0.57, 0.66, 0.5, up=True) - 0.615) < 1e-9
    assert LC.shrink(0.57, 0.66, 0.5) == 0.57, "elsewhere only ever lowered"
    assert abs(LC.shrink(0.72, 0.60, 0.5, up=True) - 0.66) < 1e-9, "above the price it still only lowers"
    assert LC.raises("nba") and LC.raises("nhl") and not LC.raises("nfl") and not LC.raises("cfb")
    os.environ["QB_RECORD_RAISES"] = "off"
    try:
        assert not LC.raises("nba")
    finally:
        os.environ.pop("QB_RECORD_RAISES", None)


def test_a_fit_learns_to_raise_where_picks_beat_what_we_said():
    rows = []
    for i in range(200):                                      # we said 57%, the price 66%, they hit 66%
        rows.append({"group": "list|over", "market": "pts", "p": 0.57, "q": 0.66, "won": i % 100 < 66,
                     "game": f"g{i // 2}"})
    up = LC.fit_groups(rows, up=True)["list|over"]
    assert up["k"] <= 0.2, up
    flat = LC.fit_groups(rows)["list|over"]
    assert LC.shrink(0.57, 0.66, flat["k"]) == 0.57, "lowering only: nothing to learn here"


def test_apply_raises_an_nba_pick_and_says_so_and_leaves_the_nfl_alone():
    store = {s: {"groups": {"list|over": {"k": 0.5, "n": 80, "hit": 0.67, "claimed": 0.57}}} for s in ("nba", "nfl")}
    row = lambda: {"player": "X", "market": "pts", "side": "OVER", "odds": -200, "model_prob": 0.57,  # noqa: E731
                   "sources": ["likely"]}
    nba, nfl = [row()], [row()]
    assert LC.apply(nba, "nba", store) == 1
    assert nba[0]["model_prob"] > 0.57 and nba[0]["board_raw_prob"] == 0.57
    assert "have hit 67% of 80 where we said 57%" in nba[0]["cal_note"]
    assert LC.apply(nfl, "nfl", store) == 0 and nfl[0]["model_prob"] == 0.57


# --- 9. Saturday's college slate bought from Friday ----------------------------------------------
def _et(y, m, d, hh):
    import datetime as dt
    from zoneinfo import ZoneInfo
    return dt.datetime(y, m, d, hh, tzinfo=ZoneInfo("America/New_York")).timestamp()


def test_a_college_friday_buys_saturday_on_top_and_no_other_day_or_league_does():
    from engine import oddsbudget as OB
    friday_noon, thursday_noon = _et(2026, 11, 20, 12), _et(2026, 11, 19, 12)
    friday_3am = _et(2026, 11, 20, 3)                          # still Thursday's slate (the 5 AM roll)
    assert OB.day_before_saturday("cfb", friday_noon)
    assert not OB.day_before_saturday("cfb", thursday_noon) and not OB.day_before_saturday("cfb", friday_3am)
    assert not OB.day_before_saturday("nfl", friday_noon), "the NFL buys ahead on its own rules (FAR_DAYS)"
    os.environ["QB_CFB_FRIDAY"] = "off"
    try:
        assert not OB.day_before_saturday("cfb", friday_noon)
    finally:
        os.environ.pop("QB_CFB_FRIDAY", None)


def test_the_launcher_adds_the_day_before_pulls_on_top_of_fridays_own():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    body = src[src.index("def _odds_affordable("):src.index("def _spent_so_far(")]
    assert "on_top = day_before_saturday(sport)" in body
    assert "if (tonight == 0 and ahead) or far_n or on_top:" in body
    assert ("elif allowance > 0 and on_top:\n                share = share + min(DAY_BEFORE_SHARE_CAP, "
            "DAY_BEFORE_PULLS * pull / allowance)") in body
    # The college pull buys tomorrow's games inside its window, at most its cap a pull.
    cfb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    assert "PLAYER_EVENT_CAP = 12" in cfb and "PLAYER_WINDOW_HOURS = 36" in cfb


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
