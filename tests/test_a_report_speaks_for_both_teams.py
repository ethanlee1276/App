"""A game report speaks for both teams (step AEH, 24 November 2026).

Ethan, 24 November 2026, with a screenshot of the Bears-Lions short version, whose big-day line named Caleb Williams,
Rome Odunze and Colston Loveland, all Bears, each "the Lions give up the fourth-most passing yards (253 a game)":
"Also in the game reports I feel like we always favor one team and always ignore the others if one team is considered
too do better. A team like the lions is still a highs scoring team so too have data and shit then say nothing about
the lions in the report doesn't make sense too me so check on that and make sure all game reports and bets included
not always just favore the favored team."

Measured that day on every finished game's report picks: the team with more of a game's picks held a median 82% of
an NFL game's picks, and every pick in 14% of NFL games (13% of hockey's, 22% of college football's, 44% of college
basketball's); its picks hit 65.9% (440 of 668) and the other team's 60.9% (151 of 248), +5.0 points ± 3.6. A weak
lean: the order stays best first, and the other team is never left out. What this file pins:

  * each team's best read takes a seat in "Who could have a big day" (and a hard day, and the Players to watch
    lists) before the rest fill in by strength (engine/breakouts.team_balanced), in the list's own order;
  * players of one team who share a reason are named together, the reason said once, and a player's reason about
    his own position goes before a team-wide one (a tight end's "to tight ends" over "the fourth-most passing yards");
  * a football team with no favorable matchup is still said: who its offense runs through, by his share of the work,
    and the points the lines expect it to score, with no matchup claimed and no player the scan reads as tough;
  * a card whose player picks are all one team's seats the other team's best pick in its last player seat when that
    pick is in the same tier and our chance for it is at least as high: the card loses nothing by the chance it
    shows. A doubted pick, a read, a lower tier or a lower chance never takes the seat.

Offline. Run directly: `python3 tests/test_a_report_speaks_for_both_teams.py`
"""
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import breakouts as B                                    # noqa: E402
from engine import gamereport as R                                   # noqa: E402

PASS = "DET gives up the 4th-most passing yards (253 a game)"


def _ctx(sport="nfl", spread=-3.5, total=49.5):
    g = {"away": "CHI", "home": "DET", "date": "2026-11-26", "kickoff": "12:30", "spread": spread, "total": total}
    return R.Ctx(g, {"games": [g]}, names={"CHI": "Bears", "DET": "Lions"}, sport=sport)


def _reads():
    """The screenshot's reads: three Bears for one reason, the Lions' offense with no favorable matchup."""
    return [
        {"player": "Caleb Williams", "team": "CHI", "pos": "QB", "read": "breakout", "pro": [PASS],
         "usage": {"snap_pct": 1.0, "attempts_pg": 34.1}},
        {"player": "Rome Odunze", "team": "CHI", "pos": "WR", "read": "good", "pro": [PASS],
         "usage": {"tgt_share": 0.24, "targets_pg": 8.1}},
        {"player": "Colston Loveland", "team": "CHI", "pos": "TE", "read": "good",
         "pro": [PASS, "DET gives up the 6th-most receiving yards to tight ends (61 a game)"],
         "usage": {"tgt_share": 0.16, "targets_pg": 5.3}},
        {"player": "Amon-Ra St. Brown", "team": "DET", "pos": "WR", "read": "neutral",
         "usage": {"tgt_share": 0.28, "targets_pg": 9.6}},
        {"player": "Jahmyr Gibbs", "team": "DET", "pos": "RB", "read": "neutral",
         "usage": {"carry_share": 0.55, "carries_pg": 17.2, "tgt_share": 0.10}},
        {"player": "Jared Goff", "team": "DET", "pos": "QB", "read": "neutral",
         "usage": {"snap_pct": 1.0, "attempts_pg": 33.0}},
    ]


def test_each_team_takes_a_seat_in_its_own_order():
    rows = [{"p": 1, "team": "CHI"}, {"p": 2, "team": "CHI"}, {"p": 3, "team": "CHI"}, {"p": 4, "team": "DET"}]
    assert [r["p"] for r in B.team_balanced(rows, 3)] == [1, 2, 4], "the Lions' best takes the third seat"
    assert [r["p"] for r in B.team_balanced(rows, 3, ("DET", "CHI"))] == [1, 2, 4], "the order is the rows' own"
    assert [r["p"] for r in B.team_balanced(rows, 1)] == [1], "one seat is the best's"
    assert [r["p"] for r in B.team_balanced(rows[:3], 3)] == [1, 2, 3], "a team with no row leaves its seat to the rest"
    assert [r["p"] for r in B.team_balanced(rows, 9)] == [1, 2, 3, 4]
    assert B.team_balanced([], 3) == [] and B.team_balanced(rows, 0) == [] and B.team_balanced(None, 2) == []


def test_the_bears_lions_short_version_says_the_lions():
    got = R.shine_lines(_ctx(), _reads(), key_only=True)
    assert got == [
        "Who could have a big day: the Bears' Caleb Williams (quarterback, a breakout candidate) and Rome Odunze "
        "(wide receiver) — the Lions give up the fourth-most passing yards (253 a game). Colston Loveland, the Bears' "
        "tight end — the Lions give up the sixth-most receiving yards to tight ends (61 a game)",
        "The Lions have no player with a favorable matchup by our numbers, but their offense still runs through "
        "Jahmyr Gibbs (55% of the carries) and Amon-Ra St. Brown (28% of the targets), and the lines expect them to "
        "score about 26.",
    ], got
    text = " ".join(got)
    assert text.count("fourth-most passing yards") == 1, "one reason, said once"


def test_a_lions_matchup_takes_a_seat_ahead_of_a_third_bear():
    reads = _reads()
    reads[4] = dict(reads[4], read="good", pro=["CHI gives up the 5th-most rushing yards to running backs (112 a game)"])
    got = R.shine_lines(_ctx(), reads)
    assert got == [
        "Who could have a big day: the Bears' Caleb Williams (quarterback, a breakout candidate) and Rome Odunze "
        "(wide receiver) — the Lions give up the fourth-most passing yards (253 a game). Jahmyr Gibbs, the Lions' "
        "running back — the Bears give up the fifth-most rushing yards to running backs (112 a game)",
    ], got
    assert "Loveland" not in got[0] and "no player with a favorable matchup" not in " ".join(got)


def test_a_players_own_position_comes_before_the_team_wide_reason():
    c = _ctx()
    te = _reads()[2]
    assert R._best_reason(c, te, "up") == "the Lions give up the sixth-most receiving yards to tight ends (61 a game)"
    wr = dict(_reads()[1], pro=[PASS, "the lines expect 27 points", "DET gives up the 2nd-most yards to wide receivers"])
    assert R._best_reason(c, wr, "up") == "the Lions give up the second-most yards to wide receivers"
    qb = dict(_reads()[0], pro=["the lines expect 27 points", PASS])
    assert R._best_reason(c, qb, "up") == "the Lions give up the fourth-most passing yards (253 a game)", \
        "a matchup still goes before the game's line, which every player shares"


def test_the_quiet_team_line_claims_no_matchup_and_names_no_tough_read():
    c = _ctx()
    reads = _reads()
    reads[4] = dict(reads[4], read="tough", con=["CHI's run defense ranks 3rd"])
    line = R.quiet_team_line(c, "DET", reads)
    assert line == ("The Lions have no player with a favorable matchup by our numbers, but their offense still runs "
                    "through Amon-Ra St. Brown (28% of the targets), and the lines expect them to score about 26."), line
    assert R.quiet_team_line(c, "DET", [r for r in reads if r["team"] == "CHI"]) == "", "no one to name, no line"
    # A league whose work the report cannot say by share has no such line.
    assert R.quiet_team_line(_ctx("nba"), "DET", _reads()) == ""
    # Without a line on the game, no points are said.
    no_line = _ctx(spread=None, total=None)
    assert R.quiet_team_line(no_line, "DET", _reads()).endswith("Amon-Ra St. Brown (28% of the targets).")
    school = R.Ctx({"away": "MICH", "home": "OSU", "spread": -10.5, "total": 45.5}, {"games": []},
                   names={"MICH": "Michigan", "OSU": "Ohio State"}, sport="cfb")
    wr = {"player": "Jeremiah Smith", "team": "OSU", "pos": "WR", "read": "neutral",
          "usage": {"tgt_share": 0.31, "share_of": "catches", "rec_pg": 6.2}}
    assert R.quiet_team_line(school, "OSU", [wr]) == (
        "Ohio State has no player with a favorable matchup by our numbers, but its offense still runs through "
        "Jeremiah Smith (31% of the catches), and the lines expect it to score about 28.")


def test_the_players_to_watch_lists_seat_both_teams():
    reads = [dict(r, read="good", pro=[PASS]) for r in _reads()[:3]] + \
        [dict(_reads()[4], read="good", pro=["CHI gives up the 5th-most rushing yards to running backs (112 a game)"])]
    old = B.CANDIDATES_N
    try:
        B.CANDIDATES_N = 2
        blocks = B.blocks(reads)
    finally:
        B.CANDIDATES_N = old
    items = next(b for b in blocks if b.get("type") == "verdicts")["items"]
    teams = [it.get("team") for it in items]
    assert "DET" in teams and "CHI" in teams, items


def _pick(player, team, p, tier="strong", **kw):
    return {"player": player, "team": team, "market": "rec_yds", "side": "over", "line": 50.5, "model_prob": p,
            "tier": tier, "game": "CHI@DET", "home": "DET", "away": "CHI", **kw}


def _card(rows):
    c = types.SimpleNamespace(featured=False, sport="cfb", home="DET", away="CHI", teams=("CHI", "DET"), result={})
    was = R._card_pool
    R._card_pool = lambda _c, key="rows": list(rows)
    try:
        return [r["player"] for r in R._card_rows(c)]
    finally:
        R._card_pool = was


def test_a_one_team_card_seats_the_other_teams_pick_when_it_is_as_good():
    bears = [_pick("Caleb Williams", "CHI", 0.70, "top"), _pick("Rome Odunze", "CHI", 0.68),
             _pick("Colston Loveland", "CHI", 0.64), _pick("D'Andre Swift", "CHI", 0.62)]
    assert _card(bears + [_pick("Jahmyr Gibbs", "DET", 0.63)]) == \
        ["Caleb Williams", "Rome Odunze", "Colston Loveland", "Jahmyr Gibbs"], "the Lions' pick, as good, is seated"
    assert _card(bears + [_pick("Jahmyr Gibbs", "DET", 0.61)]) == [r["player"] for r in bears], \
        "a lower chance never takes the seat"
    assert _card(bears + [_pick("Jahmyr Gibbs", "DET", 0.66, "look")]) == [r["player"] for r in bears], \
        "nor a lower tier"
    assert _card(bears + [_pick("Jahmyr Gibbs", "DET", 0.66, bettable=False)]) == [r["player"] for r in bears], \
        "nor a read we cannot price"
    mixed = [bears[0], _pick("Amon-Ra St. Brown", "DET", 0.67), bears[1], bears[2], _pick("Jahmyr Gibbs", "DET", 0.66)]
    assert _card(mixed) == ["Caleb Williams", "Amon-Ra St. Brown", "Rome Odunze", "Colston Loveland"], \
        "a card with both teams already is left as it is"


def test_a_doubted_pick_never_takes_the_seat():
    bears = [_pick("Caleb Williams", "CHI", 0.70), _pick("Rome Odunze", "CHI", 0.68)]
    gibbs = _pick("Jahmyr Gibbs", "DET", 0.69)
    was = R._card_doubted
    R._card_doubted = lambda sport, r: r is gibbs
    try:
        assert _card(bears + [gibbs]) == ["Caleb Williams", "Rome Odunze", "Jahmyr Gibbs"], \
            "a doubted pick goes behind the bets, and seats only where the card has room"
        full = bears + [_pick("Colston Loveland", "CHI", 0.66), _pick("D'Andre Swift", "CHI", 0.65)]
        assert "Jahmyr Gibbs" not in _card(full + [gibbs])
    finally:
        R._card_doubted = was


def test_the_heartbeat_counts_what_both_teams_got():
    """The reports are paid, so the heartbeat is where anyone sees the lines fire (engine/gamereport.lift_both)."""
    import json
    import launch as L
    c = _ctx()
    R.shine_lines(c, _reads(), key_only=True)
    assert c._both_counts == {"big_day_teams": 1, "quiet": 1}, c._both_counts
    both = _ctx()
    reads = _reads()
    reads[4] = dict(reads[4], read="good", pro=["CHI gives up the 5th-most rushing yards to running backs (112 a game)"])
    R.shine_lines(both, reads)
    assert both._both_counts == {"big_day_teams": 2, "quiet": 0}, both._both_counts
    result = {R.KEY: [{"game": "CHI@DET", R.BOTH_NOTE: dict(c._both_counts)},
                      {"game": "GB@LA", R.BOTH_NOTE: {"big_day_teams": 2, "quiet": 0, "seated": 1}},
                      {"game": "KC@DAL"}]}
    assert R.lift_both(result) == {"big_day": 2, "big_day_both": 1, "quiet": 1, "seated": 1}
    assert all(R.BOTH_NOTE not in r for r in result[R.KEY]), "each report's note is lifted off before it is written"
    assert result[R.BOTH_KEY] == {"big_day": 2, "big_day_both": 1, "quiet": 1, "seated": 1}
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(result, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got.get("both_teams") == {"big_day": 2, "big_day_both": 1, "quiet": 1, "seated": 1}, got
    none = {R.KEY: [{"game": "KC@DAL"}], R.BOTH_KEY: {"big_day": 3}}
    R.lift_both(none)
    assert R.BOTH_KEY not in none, "a board with nothing to count drops the key"


def test_a_seated_card_is_noted():
    bears = [_pick("Caleb Williams", "CHI", 0.70), _pick("Rome Odunze", "CHI", 0.68)]
    c = types.SimpleNamespace(featured=False, sport="cfb", home="DET", away="CHI", teams=("CHI", "DET"), result={})
    was = R._card_pool
    R._card_pool = lambda _c, key="rows": bears + [_pick("Jahmyr Gibbs", "DET", 0.69)]
    try:
        R._card_rows(c)
    finally:
        R._card_pool = was
    assert getattr(c, "_both_counts", {}) == {}, "a card with room seats the pick without a swap"
    full = bears + [_pick("Colston Loveland", "CHI", 0.66), _pick("D'Andre Swift", "CHI", 0.65),
                    _pick("Jahmyr Gibbs", "DET", 0.65)]
    R._card_pool = lambda _c, key="rows": list(full)
    try:
        R._card_rows(c)
    finally:
        R._card_pool = was
    assert c._both_counts == {"seated": 1}, c._both_counts


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
