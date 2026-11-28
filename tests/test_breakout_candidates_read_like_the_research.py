"""Breakout candidates and fades, the way the research reports wrote them (2026-11-15).

Ethan: "I want our game reports for each game to be scanning for all that type
of data and matchup shit and all of that and finding breakout, because
obviously those reports were able to find the good matchups and make very
good picks ... for every sport." His research reports gave a game a
"Breakout candidates" list (32 of them) and "Fades": each player's case in
numbers, the pick, and the main way it loses. Every league's report now
writes those two lists from the matchup scan's reads (engine/breakouts):

  * one heading each, "Breakout candidates" and "Fades", in every league
    (football's "Could shine" and "Could struggle", basketball's "Breakout
    watch", gone);
  * the strongest case first: a breakout spot (a role moving toward him)
    ahead of a good matchup, then more reasons for than against, then his
    work;
  * every measured reason up to four, the scan's notes, the main way it
    loses (his strongest reason against; for a fade, what could still go
    right), and his pick on the read's side where the board has one.

    python3 tests/test_breakout_candidates_read_like_the_research.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import breakouts as B                                    # noqa: E402
from engine import gamereport as R                                   # noqa: E402
from engine import leaguereport as L                                 # noqa: E402


class _Harness:
    """The game report test's own board, imported when a test first needs it
    (never at module scope: test_doctor)."""
    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module("test_the_game_report_reads_like_the_research"), attr)


GR = _Harness()


def _watch(rep):
    sec = next(s for s in rep["sections"] if s["key"] == "watch")
    heads = [b["text"] for b in sec["blocks"] if b["type"] == "h"]
    cards = {}
    for b in sec["blocks"]:
        if b["type"] == "verdicts":
            for it in b["items"]:
                cards[it["player"]] = it
    return heads, cards


def test_the_football_report_lists_breakout_candidates_and_fades_with_the_case_in_numbers():
    board = copy.deepcopy(GR._board())
    for r in board["scan_reads"]["GB@DET"]["players"]:
        if r["player"] == "Jahmyr Gibbs":
            r["con"] = ["GB holds backs to 3.9 yards a carry (8th-fewest)"]
            r["pick"] = {"market": "rush_yds", "market_label": "rushing yards", "side": "Over", "line": 69.5,
                         "odds": -115, "model_prob": 0.62}
    rep = R.build(board["games"][0], board, allowed=GR.ALLOWED, names=GR.NAMES)
    heads, cards = _watch(rep)
    assert heads[:2] == ["Breakout candidates", "Fades"], heads
    gibbs = cards["Jahmyr Gibbs"]
    assert gibbs["verdict"] == "up" and gibbs["role"].startswith("69% of the carries"), gibbs
    assert gibbs["why"][0] == "Takes 69% of the carries (18 a game).", gibbs["why"]
    assert len([w for w in gibbs["why"] if not w.startswith("The main way")]) <= B.REASONS_N + B.NOTES_N
    assert gibbs["why"][-1] == "The main way it loses: GB holds backs to 3.9 yards a carry (8th-fewest).", gibbs["why"]
    assert gibbs["pick"].startswith("Most Likely pick: Over 69.5 rushing yards (−115, 62%)"), gibbs["pick"]
    golden = cards["Matthew Golden"]
    assert golden["verdict"] == "down" and golden["why"][-1].startswith("What could still go right: "), golden
    text = R.to_text(rep)
    assert "Could shine" not in text and "Could struggle" not in text


def _nba_read(player, team, opp, read, pro=(), con=(), notes=(), mpg=30.0, pick=None):
    r = {"player": player, "team": team, "opp": opp, "pos": "", "read": read,
         "label": {"breakout": "Breakout spot", "good": "Good matchup", "tough": "Tough matchup",
                   "avoid": "Avoid"}[read], "pro": list(pro), "con": list(con), "notes": list(notes),
         "headshot": "", "usage": {"mpg": mpg}}
    if pick:
        r["pick"] = pick
    return r


def test_basketball_ranks_the_case_carries_the_pick_and_says_how_it_loses():
    reads = [
        _nba_read("Good Many", "BOS", "MIA", "good", pro=["a", "b", "c", "d"], mpg=36),
        _nba_read("Jay Star", "BOS", "MIA", "breakout",
                  pro=["Minutes up 20% over his last five (31.0 a game, 25.8 before)",
                       "MIA allows the most points a game (119.4)"],
                  con=["A 12.5-point spread — a starter's fourth quarter is the first thing a blowout takes"],
                  notes=["24.2 points a game over his last five"],
                  pick={"market": "pts", "market_label": "points", "side": "Over", "line": 22.5, "odds": -120,
                        "model_prob": 0.6}),
        _nba_read("Good Few", "BOS", "MIA", "good", pro=["a"], mpg=38),
        _nba_read("Heat Man", "MIA", "BOS", "tough", con=["BOS allows the fewest threes a game (10.1)"],
                  pro=["MIA is expected to score 112 by the lines"]),
    ]
    g = {"home": "BOS", "away": "MIA", "date": "2026-11-16", "kickoff": "2026-11-17T00:30:00Z",
         "spread": -12.5, "total": 226.5}
    board = {"date": "2026-11-16", "games": [g], "scan_reads": {"MIA@BOS": {"players": reads}}}
    L.attach(board, "nba", meta={})
    rep = board["game_reports"][0]
    heads, cards = _watch(rep)
    assert heads == ["Breakout candidates", "Fades"], heads
    sec = next(s for s in rep["sections"] if s["key"] == "watch")
    order = [it["player"] for b in sec["blocks"] if b["type"] == "verdicts" for it in b["items"]]
    assert order == ["Jay Star", "Good Many", "Good Few", "Heat Man"], ("a breakout first, then the case", order)
    star = cards["Jay Star"]
    assert star["why"] == ["Minutes up 20% over his last five (31.0 a game, 25.8 before).",
                           "MIA allows the most points a game (119.4).",
                           "24.2 points a game over his last five.",
                           "The main way it loses: A 12.5-point spread — a starter's fourth quarter is the first "
                           "thing a blowout takes."], star["why"]
    assert star["pick"].startswith("Most Likely pick: Over 22.5 points (−120, 60%)"), star["pick"]
    assert cards["Heat Man"]["why"][-1] == "What could still go right: MIA is expected to score 112 by the lines."
    text = R.to_text(rep)
    assert "Breakout watch" not in text and "Could shine" not in text


def test_hockey_and_baseball_write_the_same_two_lists():
    from importlib import import_module
    E = import_module("test_every_league_gets_a_game_report")
    board = E._nhl_board()
    L.attach(board, "nhl")
    heads, cards = _watch(board["game_reports"][0])
    assert heads[:2] == ["Breakout candidates", "Fades"], heads
    # The report's plain words say the rank in letters ("sixth-most").
    assert cards["Auston Matthews"]["why"][0] == "BOS gives up the sixth-most shots a game.", cards["Auston Matthews"]
    board = E._mlb_board()
    L.attach(board, "mlb")
    heads, _cards = _watch(board["game_reports"][0])
    assert heads and heads[0] == "Breakout candidates", heads


def test_one_builder_writes_every_leagues_lists():
    src = {f: (ROOT / "engine" / f).read_text(encoding="utf-8") for f in ("gamereport.py", "leaguereport.py")}
    assert "from .breakouts import blocks" in src["gamereport.py"] and "from .breakouts import blocks" in src["leaguereport.py"]
    for old in ('_h("Breakout watch")', '_h("Could shine")', '_h("Could struggle")'):
        assert old not in src["gamereport.py"] and old not in src["leaguereport.py"], old
    # A read with no case says nothing; no read, no section text.
    assert B.blocks([]) == []
    assert B.blocks([{"player": "X", "read": "neutral"}])[-1]["text"].startswith("No one in this game reads")


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
