"""The posted picks are read against the matchup reads, every league, in one
command (engine/pickaudit, 2026-11-14).

Ethan: "Duke's running back has 17 touchdowns, and yet we're marking him as
a bad matchup ... audit all of that for every sport ... audit all the picks
and all that shit and remove and add anything we need to." The reads were
fixed at the rule (engine/readlogic). What the boards post after that is
read on the box, off the private copy, so the next fix is a rule too:
every could-struggle read on a key player with its reasons, go-to scorers
first, and every go-to scorer with no touchdown pick on any board.

    python3 tests/test_the_posted_picks_are_audited_against_the_reads.py
"""
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import pickaudit as A                    # noqa: E402


def _board():
    duke = {"player": "Duke Back", "team": "DUKE", "opp": "MIA", "pos": "RB", "read": "tough",
            "label": "Tough for yards — still the go-to scorer",
            "pro": ["Duke is expected to score 31"], "con": ["Miami's run defense ranks 5th"],
            "lean": ["rush_yds"], "usage": {"carry_share": 0.62},
            "scoring": {"go_to": True, "prob": 0.58, "implied": 31.0},
            "td": {"model_prob": 0.58, "odds": 105, "book": "FanDuel"}}
    miami = {"player": "Miami Back", "team": "MIA", "opp": "DUKE", "pos": "RB", "read": "neutral",
             "label": "Neutral", "pro": [], "con": [], "lean": [], "usage": {"carry_share": 0.50},
             "scoring": {"go_to": True, "prob": 0.44}, "td": {"model_prob": 0.44, "odds": 140}}
    heavy = {"player": "Heavy Favourite", "team": "MIA", "opp": "DUKE", "pos": "TE", "read": "good",
             "label": "Good matchup", "pro": ["x"], "con": [], "lean": [], "usage": {"tgt_share": 0.2},
             "scoring": {"go_to": True, "prob": 0.40}, "td": {"model_prob": 0.40, "odds": -300}}
    bench = {"player": "Bench Guy", "team": "MIA", "opp": "DUKE", "pos": "WR", "read": "tough",
             "label": "Tough matchup", "pro": [], "con": ["Duke's slot corner"], "lean": ["receptions"],
             "usage": {"tgt_share": 0.05}}
    return {"built_at": "2026-11-14T12:00:00",
            "scan_reads": {"DUKE@MIA": {"players": [duke, miami, heavy, bench]}},
            "most_likely": [{"player": "Miami Back", "team": "MIA", "market": "anytime_td", "side": "YES",
                             "line": 0.5, "model_prob": 0.44, "odds": 140, "book": "FanDuel"}]}


def test_a_key_player_who_could_struggle_is_listed_with_his_reasons():
    a = A.audit(_board())
    assert [x["player"] for x in a["struggle"]] == ["Duke Back"], "a bench receiver is no key player"
    lines = "\n".join(A.report("cfb", _board()))
    assert "Duke Back (DUKE vs MIA, RB): \"Tough for yards — still the go-to scorer\" · 62% of the carries" in lines
    assert "go-to scorer: 58% to score, his team expected to score 31.0" in lines
    assert "against: Miami's run defense ranks 5th" in lines and "for: Duke is expected to score 31" in lines


def test_a_go_to_scorer_with_no_touchdown_pick_is_named_with_why():
    a = A.audit(_board())
    assert [x["player"] for x in a["unposted"]] == ["Duke Back", "Heavy Favourite"], \
        "the Miami back's touchdown is posted on Most Likely"
    lines = "\n".join(A.report("cfb", _board()))
    assert "Duke Back (DUKE, RB): 58% at +105 FanDuel — priced, under every board's bar" in lines
    assert "Heavy Favourite (MIA, TE): 40% at -300 — past the -250 cap" in lines


def test_a_touchdown_leg_in_a_game_parlay_counts_as_posted():
    d = _board()
    d["game_parlays"] = {"games": [{"scorers": [{"legs": [{"player": "Duke Back", "market": "anytime_td"}]}]}]}
    assert "Duke Back" not in [x["player"] for x in A.audit(d)["unposted"]]


def test_every_league_with_reads_is_read_and_a_missing_board_says_so():
    assert set(A.FILES) >= {"nfl", "cfb", "nba", "wnba", "cbb", "nhl"}
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "cfb.json"
        p.write_text(json.dumps(_board()))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert A.main(["--sport", "cfb", "--file", str(p)]) == 0
        assert "CFB board built 2026-11-14T12:00:00" in buf.getvalue()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert A.main(["--sport", "nhl", "--file", str(Path(tmp) / "none.json")]) == 0
        assert "NHL: no board to read" in buf.getvalue()


def test_it_reads_the_private_copy_and_writes_nothing():
    src = (ROOT / "engine" / "pickaudit.py").read_text(encoding="utf-8")
    assert "gate.board_source(path)" in src, "the public copy has the reads and the picks taken out"
    for w in ("open(path, \"w", ".write(", "sqlite3", "connect("):
        assert w not in src, f"read-only: {w}"



def test_a_started_game_is_judged_at_the_boards_build_and_the_rows_are_printed():
    """Ethan's run, 2026-11-14 at 7:32pm ET, counted 43 college picks STARTED:
    every 7:30 kickoff since the 7:19 build. As of the build only a pick
    already under way is a fault; and the rows behind each count print."""
    from engine import pickaudit as PA
    row = {"team": "MIA", "market": "rush_yds", "side": "over", "line": 50.5, "model_prob": 0.6, "odds": -150}
    d = {"generated_at": "2026-11-15T00:19:00+00:00", "most_likely": [
        dict(row, player="Kicks Off Later", kickoff="2026-11-15T00:30:00Z"),
        dict(row, player="Under Way", kickoff="2026-11-15T00:00:00Z")]}
    a = PA.audit(d)
    assert a["contradictions"].get("STARTED") == 1, a["contradictions"]
    lines = PA.report("cfb", d)
    assert any(ln.strip().startswith("STARTED: Under Way") for ln in lines), lines
    assert PA.built_utc({"generated_at": "junk"}) is None

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
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
