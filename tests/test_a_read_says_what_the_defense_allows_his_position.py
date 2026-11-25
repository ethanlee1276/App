"""A football read says what the defence gives up to the player's own position, in every stat (step AHO, 25 Nov 2026).

Ethan, on the Packers at the Rams, a fade of Tucker Kraft that read "LA gives up the second-fewest passing yards
(198 a game)": "you're not going into specifics about how many passing yards they give up to tight ends, and for
receivers you're not going into specifics on how many passing yards they give up to receivers, and same for
touchdown props ... how a real sports bettor would use it".

Re-measured that day (positionfit.py, 2022-2025, 7,321 receiver and tight end games): the overall pass defence split
catchers' games 103% / 93% of their usual yards, the position's own number 103% / 94%, and counting both as one vote
102% / 94%. So what holds:

  * every read says, first among its notes, what the defence gives up a game to his position — yards, catches and
    touchdowns (a passer's: yards, touchdowns, interceptions forced), each with its rank, at any rank;
  * a stat already said as a counted reason is left out of that line, which then says "also";
  * the counted reason for a catcher says the pass defence is overall, and no position number becomes a vote;
  * the report's matchup cards and its fade and breakout cards carry the line;
  * a touchdown line says the number beside the rank, and only a running back's "touchdown matchup backs it";
  * a touchdown leg says his position's touchdowns allowed, at any rank;
  * "the Packers' last game", never "Packers's".

    python3 tests/test_a_read_says_what_the_defense_allows_his_position.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import breakouts as BO, gamereport as GR, gamescan as S   # noqa: E402


def _row(pg, rank, of=32, games=11):
    return {"pg": pg, "rank": rank, "of": of, "games": games, "factor": 1.0}


#: The Rams as the screenshot had them (198 passing yards, the second-fewest), and to each position.
LA = {"qb_pass_yds": _row(198.0, 31), "te_rec_yds": _row(47.0, 18), "te_rec": _row(4.6, 15), "te_td": _row(0.1, 31),
      "wr_rec_yds": _row(111.0, 31), "wr_rec": _row(9.6, 28), "wr_td": _row(0.6, 26),
      "rb_rush_yds": _row(88.0, 25), "rb_rec": _row(3.9, 20), "rb_rec_yds": _row(30.0, 22), "rb_td": _row(0.3, 32),
      "qb_pass_td": _row(1.1, 29), "qb_pass_int": _row(0.9, 10)}


def _read(name, pos, usage, allowed=LA):
    return S.player_read(name, "GB", "LA", pos, usage=usage, ratings={}, room=None, scheme=None, split=None,
                         tackling=None, line_out=None, mates_out=None, n_teams=32, allowed=allowed, points=22.0,
                         line_words="", weather=None)


def kraft():
    return _read("Tucker Kraft", "TE", {"tgt_share": 0.19, "targets_pg": 5.5, "games": 11, "share_of": "targets"})


def test_the_tight_end_read_says_what_la_gives_up_to_tight_ends():
    r = kraft()
    assert r["con"] == ["LA gives up the 2nd-fewest passing yards overall (198 a game)"], r["con"]
    line = ("Against tight ends, LA allows 47 receiving yards (the 15th-fewest), 4.6 catches (the 15th-most) and "
            "0.1 touchdowns (the 2nd-fewest) a game — of 32 defenses, over 11 games")
    assert r["notes"][0] == line and r["vs_position"] == line, r["notes"]
    assert r["position_td"] == "LA gives up the 2nd-fewest touchdowns to tight ends (0.1 a game)"
    # Shown, never counted: no reason for or against reads a tight-end number.
    assert not any("tight ends" in x for x in r["pro"] + r["con"]), r


def test_receivers_backs_and_passers_get_their_own_line():
    reed = _read("Jayden Reed", "WR", {"tgt_share": 0.18, "targets_pg": 5.0, "games": 9, "share_of": "targets"})
    assert reed["notes"][0].startswith("Against wide receivers, LA allows 111 receiving yards (the 2nd-fewest), "
                                       "9.6 catches (the 5th-fewest) and 0.6 touchdowns (the 7th-fewest) a game")
    lloyd = _read("MarShawn Lloyd", "RB", {"carry_share": 0.45, "carries_pg": 12.0, "games": 8, "share_of": "carries"})
    # His rushing yards and touchdowns are counted (defensevs.MODEL_STAT), so the line says what else, "also".
    assert "LA gives up the 8th-fewest rushing yards to running backs (88 a game)" in lloyd["con"], lloyd["con"]
    assert lloyd["notes"][0] == ("Against running backs, LA also allows 3.9 catches for 30 yards (the 13th-fewest; "
                                 "the 11th-fewest in yards) a game — of 32 defenses, over 11 games"), lloyd["notes"]
    love = _read("Jordan Love", "QB", {"attempts_pg": 33.0, "games": 11})
    assert love["notes"][0] == ("Against quarterbacks, LA also allows 1.1 passing touchdowns (the 4th-fewest) and "
                                "forces 0.9 interceptions (the 10th-most) a game — of 32 defenses, over 11 games")
    assert love["notes"][0].count("a game") == 1
    # Every stat his bets are on: a back's carries (and what he gains a carry), a passer's completions and attempts.
    more = dict(LA, rb_rush_att=_row(23.6, 21), qb_pass_cmp=_row(21.0, 21), qb_pass_att=_row(33.2, 24))
    assert S.position_line("rb", more, "LA").startswith(
        "Against running backs, LA allows 88 rushing yards (the 8th-fewest) on 24 carries (3.7 yards a carry; the "
        "12th-fewest in carries), 3.9 catches for 30 yards"), S.position_line("rb", more, "LA")
    assert S.position_line("rb", more, "LA", skip={"rb_rush_yds"}).startswith(
        "Against running backs, LA also allows 24 carries (3.7 yards a carry; the 12th-fewest), 3.9 catches")
    assert S.position_line("qb", more, "LA", skip={"qb_pass_yds"}) == (
        "Against quarterbacks, LA also allows 21 completions (the 12th-fewest), 33 pass attempts (the 9th-fewest) and "
        "1.1 passing touchdowns (the 4th-fewest), and forces 0.9 interceptions (the 10th-most) a game — of 32 "
        "defenses, over 11 games")


def test_the_line_reads_any_rank_and_nothing_without_ratings():
    assert S._place(1, 32) == "the most" and S._place(32, 32) == "the fewest"
    assert S._place(16, 32) == "the 16th-most" and S._place(17, 32) == "the 16th-fewest"
    assert S.position_line("te", {}, "LA") == "" and S.position_line("k", LA, "LA") == ""
    assert "position_td" not in _read("Tucker Kraft", "TE", {"tgt_share": 0.19, "games": 11}, allowed={})


def test_the_report_cards_carry_it():
    r = dict(kraft(), headshot="", lean=["rec_yds"])
    card = BO.card(r, "down")
    assert any(w.startswith("Against tight ends, LA allows 47 receiving yards") for w in card["why"]), card["why"]
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '+ ([_sentence(r["vs_position"])] if r.get("vs_position") else []),' in src
    # The report's own words: "the 2nd-fewest" said "the second-fewest" (gamereport.plain).
    assert GR.plain(r["vs_position"]).endswith("and 0.1 touchdowns (the second-fewest) a game — of 32 defenses, "
                                               "over 11 games")


def test_a_touchdown_line_says_the_number_and_backs_only_a_running_back():
    assert GR._per_game({"pg": 0.14}) == " (0.1 a game)" and GR._per_game({}) == ""
    assert GR.TD_FUNNEL_POS == ("RB", "FB")
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "funnel = rank <= TD_FUNNEL_RANK and pos in TD_FUNNEL_POS" in src


def test_a_touchdown_leg_says_his_positions_touchdowns():
    from engine import gameparlays as GP
    leg = {"player": "Tucker Kraft", "team": "GB", "market": "anytime_td", "side": "yes"}
    why = GP.why_lines(leg, None, kraft())
    assert "LA gives up the 2nd-fewest touchdowns to tight ends (0.1 a game)" in why, why


def test_a_missed_game_reads_the_packers_last_game():
    from engine import availability as A
    r = {"player": "Jayden Reed", "team": "GB", "availability": A.MISSED, "missed": {"kind": "stat", "team": "GB"}}

    class C:
        names, sport = {"GB": "Packers"}, "nfl"

        def name(self, t):
            return self.names.get(t, t)

        def poss(self, t):
            n = self.name(t)
            return f"{n}'" if n.endswith("s") else f"{n}'s"
    out = A.note(r, C())
    assert "in the Packers' last game" in out and "Packers's" not in out, out
    # A college goes by its school, with no "the" (gamereport._the).
    C.names, C.sport = {"GB": "Indiana"}, "cfb"
    assert "in Indiana's last game" in A.note(r, C())
    assert "in GB's last game" in A.note(r, None), "no report, the code's own possessive"


def test_a_hockey_reason_says_the_number_beside_the_rank():
    """The same in hockey (step AHP): "BOS gives up the 2nd-most shots (34.2 a game)", never the rank alone."""
    from engine.nhl import scan as N
    teams = {f"T{i:02d}": {"sog_against": 25.0 + i * 0.3, "ga": 2.5 + i * 0.03, "xga_ev": 2.0 + i * 0.02,
                           "sog_for": 30 - i * 0.2} for i in range(32)}
    teams["BOS"] = {"sog_against": 34.2, "ga": 3.61, "xga_ev": 2.88, "sog_for": 24.0}
    r = N.read_skater("Auston Matthews", {"games": []}, "T00", "BOS", teams, {}, {})
    assert r["pro"] == ["BOS gives up the 2nd-most shots (34.2 a game)",
                        "BOS gives up the most 5-on-5 chances (2.88 expected goals against a game)",
                        "BOS allows the most goals (3.6 a game)"], r["pro"]
    g = N.read_goalie("Goalie X", "T05", "BOS", teams, {"T05": {"starter_sure": True, "starter_share": 0.8}})
    assert g["con"] == ["BOS takes the 2nd-fewest shots (24.0 a game)", "T05 allows the 6th-fewest shots (26.5 a game)"]
    # No number, the rank as before.
    bare = {t: {k: (None if k == "sog_against" else v) for k, v in row.items()} for t, row in teams.items()}
    assert N._pg(bare, "BOS", "sog_against") == ""


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
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
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
