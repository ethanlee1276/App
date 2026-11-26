"""A key player in a good spot is named, on his own list (step AHZ, 26 November 2026).

Ethan, 26 November, with three screenshots of Bears at Lions: "in the Who's guarding who, we show a lot of lions
players as they are in a good spot but then u go to the breakout candidates and who could have a big day and they
are no where too be seen or mentioned like they are gonna have a bad game ... Not mentioning key players at all makes
it seem like they are a bad bet basically so we need too work on that and how we show the data."

Amon-Ra St. Brown and Jameson Williams were FAVORABLE SPOT under Who's guarding who: a good read the Bears' defence
did not carry (the points the lines expect in the board's highest total). The Players to watch list took the good
matchups and the good spots as one list, where each team's best took a seat and the stronger cases filled the rest,
so the Bears' three matchups filled it; the big-day line took three seats, two Bears and Jahmyr Gibbs. What holds:

  * a good spot has its own list, "In a good spot", under the breakout candidates (engine/breakouts SPOTS_HEAD);
  * every key player on the report's matchup cards with a good read is on one list or the other, each team's best
    two seated first before the rest fill in by strength;
  * the big-day line seats each team's best two when both teams have one (a team alone keeps the line's three);
  * a key player whose read leans neither way is named under "No edge either way", never left out;
  * a spot card under Who's guarding who says what made it one before the defence's own number;
  * a good spot is graded on its own line of the record and journaled as its own place ("Good spot").

Offline. Run directly: `python3 tests/test_a_good_spot_is_named.py`
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import breakouts as B                                    # noqa: E402
from engine import gamereport as R                                   # noqa: E402

PASS = "DET gives up the 4th-most passing yards (253 a game)"
LINES = "The lines expect DET to score about 28 (+1.5 at home, total 56.5)"
DEF = "CHI gives up 234 passing yards a game — the 15th-fewest of 32"


def _reads():
    """The screenshots' game, in the test's own numbers (not a real game's)."""
    spot = {"read": "good", "label": "Good spot", "spot": True, "spot_why": [LINES], "pro": [LINES]}
    return [
        {"player": "Caleb Williams", "team": "CHI", "pos": "QB", "read": "breakout", "label": "Breakout candidate",
         "pro": [PASS], "usage": {"snap_pct": 1.0, "attempts_pg": 32.1}},
        {"player": "Rome Odunze", "team": "CHI", "pos": "WR", "read": "breakout", "label": "Breakout candidate",
         "pro": [PASS], "usage": {"tgt_share": 0.20, "targets_pg": 6.4}},
        {"player": "Colston Loveland", "team": "CHI", "pos": "TE", "read": "good", "label": "Good matchup",
         "pro": [PASS], "usage": {"tgt_share": 0.18, "targets_pg": 5.6}},
        {"player": "D'Andre Swift", "team": "CHI", "pos": "RB", "read": "neutral", "label": "Neutral",
         "usage": {"carry_share": 0.55, "carries_pg": 14.0}},
        dict(spot, player="Amon-Ra St. Brown", team="DET", pos="WR", defense_line=DEF,
             usage={"tgt_share": 0.31, "targets_pg": 9.9}),
        dict(spot, player="Jameson Williams", team="DET", pos="WR", defense_line=DEF,
             usage={"tgt_share": 0.18, "targets_pg": 5.8}),
        dict(spot, player="Jahmyr Gibbs", team="DET", pos="RB", usage={"carry_share": 0.6, "carries_pg": 16.0}),
        {"player": "Jared Goff", "team": "DET", "pos": "QB", "read": "neutral", "label": "Neutral",
         "usage": {"snap_pct": 1.0, "attempts_pg": 33.0}},
    ]


def _ctx(reads=None):
    g = {"away": "CHI", "home": "DET", "date": "2026-11-26", "kickoff": "12:30", "spread": 1.5, "total": 56.5}
    return R.Ctx(g, {"games": [g], "scan_reads": {"CHI@DET": {"players": reads or _reads()}}},
                 names={"CHI": "Bears", "DET": "Lions"}, sport="nfl")


def _lists(sec):
    out, head = {}, None
    for b in sec["blocks"]:
        if b.get("type") == "h":
            head = b["text"]
        elif b.get("type") == "verdicts":
            out[head] = [it["player"] for it in b["items"]]
    return out


def test_the_good_spots_have_their_own_list_and_every_key_one_is_named():
    sec = R.sec_watch(_ctx())
    got = _lists(sec)
    assert got["Breakout candidates"] == ["Caleb Williams", "Rome Odunze", "Colston Loveland"], got
    assert sorted(got["In a good spot"]) == ["Amon-Ra St. Brown", "Jahmyr Gibbs", "Jameson Williams"], got
    spots = next(b for b in sec["blocks"] if b.get("type") == "verdicts" and b["items"][0].get("group"))
    assert all(it["group"] == "spots" and it["verdict"] == "up" for it in spots["items"])
    assert all(it["why"][0] == LINES + "." for it in spots["items"]), "each says what made it a spot"


def test_a_key_player_with_no_edge_is_named_not_left_out():
    text = R.to_text({"game": "CHI@DET", "away": "CHI", "home": "DET", "sections": [R.sec_watch(_ctx())],
                      "when": "x", "title": "t"})
    assert "— No edge either way —" in text
    assert ("The Bears' D'Andre Swift (running back); the Lions' Jared Goff (quarterback): the matchup leans neither "
            "way for these players, so they are neither breakout candidates nor fades. Each one's case is under Who's "
            "guarding who; a pick on any of them comes from our projection, not the matchup.") in text, text
    # One player alone is said as one.
    one = [r for r in _reads() if r["player"] != "Jared Goff"]
    text = R.to_text({"game": "CHI@DET", "away": "CHI", "home": "DET", "sections": [R.sec_watch(_ctx(one))],
                      "when": "x", "title": "t"})
    assert ("The Bears' D'Andre Swift (running back): the matchup leans neither way, so the read is neither a "
            "breakout nor a fade. The case is under Who's guarding who; a pick on this player comes from our "
            "projection, not the matchup.") in text, text


def test_every_league_calls_a_breakout_a_breakout_candidate():
    """Basketball's and hockey's scans said "Breakout spot", the word a good spot now has for a read the defence did
    not carry; every league says football's word, as the game page's Matchup scan always has."""
    from engine.nba import scan as NBA
    from engine.nhl import scan as NHL
    from engine.mlb import scan as MLB
    assert NBA.LABELS["breakout"] == NHL.LABELS["breakout"] == MLB.LABELS["breakout"] == "Breakout candidate"
    assert 'breakout: "Breakout candidate"' in (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def test_the_big_day_line_seats_each_teams_best_two():
    lines = R.shine_lines(_ctx(), _ctx().reads)
    assert lines[0] == (
        "Who could have a big day: the Bears' Caleb Williams (quarterback, a breakout candidate) and Rome Odunze "
        "(wide receiver, a breakout candidate) — the Lions give up the fourth-most passing yards (253 a game). The "
        "Lions' Jahmyr Gibbs (running back) and Amon-Ra St. Brown (wide receiver) — the lines expect the Lions to "
        "score about 28 (+1.5 at home, total 56.5)"), lines[0]
    # A team alone with good reads keeps the line's three.
    alone = [r for r in _reads() if r["team"] == "CHI"]
    assert "Colston Loveland" in R.shine_lines(_ctx(alone), alone)[0]


def test_a_spot_card_says_what_made_it_one_before_the_defences_number():
    m = R.sec_matchups(_ctx())
    det = [it for b in m["blocks"] if b.get("type") == "verdicts" for it in b["items"] if it["team"] == "DET"]
    amon = next(it for it in det if it["player"] == "Amon-Ra St. Brown")
    assert amon["label"] == "FAVORABLE SPOT", amon["label"]
    assert amon["why"][:2] == [
        "Favorable because of the game, not the defense: the lines expect DET to score about 28 (+1.5 at home, "
        "total 56.5).",
        "The defense itself: " + DEF + " — the number our projection reads for this matchup."], amon["why"]
    assert sum("lines expect DET" in w for w in amon["why"]) == 1, "said once on the card"


def test_the_seating_rules():
    rows = [{"team": "CHI", "p": i} for i in (1, 2, 3, 4)] + [{"team": "DET", "p": i} for i in (5, 6, 7)]
    assert [r["p"] for r in B.team_balanced(rows, 4, per_team=2)] == [1, 2, 5, 6]
    assert [r["p"] for r in B.team_balanced(rows, 5, per_team=2)] == [1, 2, 3, 5, 6]
    assert [r["p"] for r in B.team_balanced(rows, 3)] == [1, 2, 5], "one seat each by default, as before"
    keys = B.seated(rows, 2, key_fn=lambda r: r["p"] in (3, 7))
    assert [r["p"] for r in keys] == [3, 7], "every key player, however many, before the rest"


def test_the_record_and_the_journal_keep_a_good_spot_apart():
    from engine import reportbets, reportgrade, reportrecord
    assert reportgrade._group("watch", {"verdict": "up", "group": "spots"}) == "spots"
    assert reportgrade._group("watch", {"verdict": "up"}) == "candidates"
    assert ("spots", "Good spots") in reportgrade.GROUPS and reportgrade.RIGHT_WORDS["spots"] == "beat their average"
    assert reportbets.source_of("watch", {"verdict": "up", "group": "spots"}) == "spot"
    assert reportbets.SOURCE_WORDS["spot"] == "Good spot"
    line = reportrecord.track_lines({"games": 12, "since": "2026-11-12",
                                     "groups": {"candidates": (30, 50), "spots": (11, 20), "fades": (9, 14)}},
                                    "nfl")["watch"]
    assert line.startswith("Our record so far: breakout candidates beat their average 30 of 50 times (60%), players "
                           "in a good spot 11 of 20 (55%) and fades fell short of it 9 of 14 times (64%), on 12 "
                           "finished NFL games since Nov 12. For comparison, a key player in an ordinary game"), line
    js = (ROOT / "web" / "js" / "reportpicks.js").read_text(encoding="utf-8")
    assert '["spots", "Good spots"]' in js
    assert '["Good spot", "Good spots"]' in (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")


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
