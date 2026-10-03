"""The NHL's NFL features: the matchup scan, the injury report, the books'
pulled players.

Ethan, 2026-10-03: "dive deeper into looking at what features we have for
NFL and implement them into NHL ... I know we could use the who could do
good and who could struggle." Checks: every game gets a tale of the tape
(each side's starter, goals and shots with league ranks, expected goals);
the key skaters and both starters get a read in the football scan's row
shape; a weak opposing starter is a reason for a skater and a lopsided game
is one against a goalie; the reads reach the one board's matchup check; a
player ruled out on ESPN's NHL report has no prop and no read, a day-to-day
one is held; ESPN's NHL board is in the injury feed's league list.

Run directly: `python3 tests/test_nhl_scan_and_injuries.py`
"""
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import nhl_build as B                                          # noqa: E402
from engine import likelyboard                                 # noqa: E402
from engine.nhl import scan as S                               # noqa: E402
from engine.sources import espninjuries                        # noqa: E402
T = importlib.import_module("test_nhl_board_builds")   # the board fixture, shared


def _built(injuries=None):
    conn = T._history()
    out, slate = B.build("2025-10-30", T.TONIGHT, conn, attach_odds=T._odds, injuries=injuries or {})
    return out, slate


def test_every_game_gets_a_tale_of_the_tape():
    out, _ = _built()
    tape = out["games"][0]["nhl_tape"]
    edm, cgy = tape["sides"]["EDM"], tape["sides"]["CGY"]
    assert edm["starter"] == "Stuart Skinner" and cgy["starter"] == "Dan Vladar"
    assert edm["ranks"]["gf"] in (1, 2) and edm["xg"] is not None and edm["gf"] > 0
    assert "injuries" in edm and tape["teams"] == 2


def test_key_players_and_both_starters_get_a_read_in_the_football_shape():
    out, _ = _built()
    rows = out["scan_reads"]["CGY@EDM"]["players"]
    names = {r["player"] for r in rows}
    assert {"Connor McDavid", "Stuart Skinner", "Dan Vladar"} <= names, names
    need = {"player", "team", "opp", "pos", "read", "label", "pro", "con", "notes", "lean", "headshot", "usage"}
    for r in rows:
        assert need <= set(r) and r["read"] in S.LABELS
    goalie = next(r for r in rows if r["player"] == "Stuart Skinner")
    assert goalie["lean"] == ["saves"] and goalie["pos"] == "G"


def test_a_weak_starter_is_a_reason_and_a_lopsided_game_is_one_against():
    league = {"sv": 0.900}
    teams = {"EDM": {"sog_against": 28, "ga": 2.6, "sog_for": 33}, "CGY": {"sog_against": 33, "ga": 3.4, "sog_for": 26}}
    ctx = {"EDM": {"xg": 3.5, "starter": "S", "starter_sure": True, "sv": 0.915, "starter_share": 1.0},
           "CGY": {"xg": 2.2, "starter": "V", "starter_sure": True, "sv": 0.890, "starter_share": 0.9}}
    p = {"position": "C", "games": [{"toi": 20.0, "sog": 4.0} for _ in range(12)]}
    r = S.read_skater("Connor McDavid", p, "EDM", "CGY", teams, ctx, league)
    assert any("V," in x and "below the league" in x for x in r["pro"]), r["pro"]
    assert any("expected to score 3.5" in x for x in r["pro"])
    g = S.read_goalie("V", "CGY", "EDM", teams, ctx)
    assert any("lopsided" in x for x in g["con"]), g["con"]


def test_the_reads_reach_the_one_boards_matchup_check():
    assert likelyboard.MATCHUP_SOURCE["nhl"] == "scan"
    out, _ = _built()
    assert out["scan_reads"]


def test_a_ruled_out_player_has_no_prop_and_no_read_and_day_to_day_is_held():
    inj = {"Connor McDavid": {"status": "Out", "team": "EDM", "injury": "Lower body"},
           "Stuart Skinner": {"status": "Day-To-Day", "team": "EDM", "injury": "Upper body"}}
    out, _ = _built(inj)
    assert not any(r["player"] == "Connor McDavid" for r in out["recommendations"])
    assert "Connor McDavid" not in {r["player"] for r in out["scan_reads"]["CGY@EDM"]["players"]}
    held = [r for r in out["recommendations"] if r["player"] == "Stuart Skinner"]
    assert held and all(r["injury_status"] == "Day-To-Day" for r in held)
    assert {i["player"] for i in out["games"][0]["nhl_tape"]["sides"]["EDM"]["injuries"]} == set(inj)


def test_espns_nhl_board_is_read_and_cleared_notices_are_not_injuries():
    assert espninjuries.LEAGUES["nhl"].endswith("/hockey/nhl/injuries")
    payload = {"injuries": [{"displayName": "Edmonton Oilers", "injuries": [
        {"athlete": {"displayName": "Connor McDavid"}, "status": "Out", "date": "2026-10-02T15:00Z",
         "details": {"type": "Lower Body"}},
        {"athlete": {"displayName": "Evan Bouchard"}, "status": "Active", "date": "2026-10-02T15:00Z"}]}]}
    got = B.nhl_injuries(fetch=lambda: payload)
    assert got["Connor McDavid"]["status"] == "Out" and got["Connor McDavid"]["team"] == "EDM"
    assert "Evan Bouchard" not in got, "a cleared-to-play notice is not an injury"
    assert B.nhl_injuries(fetch=lambda: (_ for _ in ()).throw(RuntimeError("down"))) == {}


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
