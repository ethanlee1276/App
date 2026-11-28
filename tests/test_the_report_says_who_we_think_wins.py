"""Every game report says who we think wins, and why, for both sides.

Ethan, 2026-11-16: "I also wanna add in the game report section who we think
will win based off the data and match up and our game report and offense
and defense and all that". engine/gamereport.sec_verdict, right under our
picks in every league's report (`finish`). The call and its chance come from
the sharpest number on the board: the books' moneyline with their cut taken
out, else the spread on the league's own win curve, else our simulation. It
is not our team ratings alone. Their disagreements with the NFL close were
measured to carry nothing, and baseball's model-alone moneylines lost 12.4%,
so following them against the price would be noise said with confidence.
The report's own data gives the why: each offense against the other
defense, the records, the last few games, home and road, who is out, the
starting pitchers, the goalies. It is said for both sides, and an upset is
flagged when more of it points at the underdog.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gamereport as R  # noqa: E402

REPORT_JS = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
REPORT_CSS = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")


class _Harness:
    """A sibling test module, imported when a test first needs it (never at
    module scope: test_doctor)."""
    def __init__(self, name):
        self._name = name

    def __getattr__(self, attr):
        import importlib
        return getattr(importlib.import_module(self._name), attr)


NFL = _Harness("test_the_game_report_reads_like_the_research")
LEAGUES = _Harness("test_every_league_gets_a_game_report")
NAMES = {"DET": "Lions", "GB": "Packers"}


def _verdict(rep):
    return next((s for s in rep["sections"] if s["key"] == "verdict"), None)


def _text(sec):
    out = []
    for b in sec["blocks"]:
        if b["type"] in ("p", "note", "h"):
            out.append(b["text"])
        elif b["type"] == "list":
            out += b["items"]
    return out


def _ctx(**g):
    base = {"home": "DET", "away": "GB", "date": "2099-11-16", "kickoff": "13:00"}
    return R.Ctx(dict(base, **g), {}, sport="nfl", names=NAMES)


def test_the_nfl_report_calls_it_and_says_both_sides():
    rep = NFL._report()
    keys = [s["key"] for s in rep["sections"]]
    assert keys.index("verdict") < keys.index("short"), keys
    sec = _verdict(rep)
    assert sec["title"] == "Who we think wins"
    win = sec["blocks"][0]
    assert win["type"] == "winner" and (win["team"], win["other"], win["word"]) == ("DET", "GB", "A lean"), win
    assert abs(win["chance"] - 0.6) < 0.01 and win["source"] == "market", win
    said = _text(sec)
    for want in ("The Lions to win, a 60% chance by the books' moneyline with their cut taken out",
                 "Our simulation of the game, drive by drive, 4,000 times: the Lions 58%",
                 "Prediction markets: Kalshi 61% and Polymarket 60%",
                 "The lines expect about Lions 27.8, Packers 24.8",
                 "Why the Lions", "The Packers' pass protection (22nd) against the Lions' pass rush (5th)",
                 "The Packers are without tackle Zach Tom",
                 "The case for the Packers", "The Packers' passing game (4th) against the Lions' pass defense (22nd)"):
        assert any(want in s for s in said), (want, said)
    # Every reason in the two lists says the teams by name (step AEJ): no code beside a name.
    import re
    assert not [s for s in said[:-1] if re.search(r"\b(GB|DET)\b", s)], said
    assert "they have told us nothing the line didn't already" in said[-1], said[-1]
    assert said[-1].endswith("for each side."), "the note ends as a sentence"
    assert "Who we think wins" not in R.to_text(rep).split("WHO WE THINK WINS")[0], "said once, as its section"
    assert "A lean: Lions — 60% to win" in R.to_text(rep)


def test_an_underdog_the_report_favors_is_the_case_for_an_upset():
    edges = [{"unit": u, "off": "GB", "def": "DET", "off_rank": 3, "def_rank": 28, "gap": 25}
             for u in ("passing", "rushing", "explosive")]
    sec = R.sec_verdict(_ctx(home_ml=-160, away_ml=140, scan={"edges": edges}))
    assert sec["blocks"][0]["team"] == "DET", "the call follows the price"
    said = _text(sec)
    assert any("More of this report points to the Packers than to the Lions (3 reasons to 0): the case for an "
               "upset, against the price" in s for s in said), said
    assert any(s == "The case for the Packers" for s in said)


def test_without_a_moneyline_the_spread_then_our_simulation_then_nothing():
    spread = R.sec_verdict(_ctx(spread=-3.0))
    assert spread["blocks"][0]["source"] == "spread" and spread["blocks"][0]["team"] == "DET"
    assert any("the spread, on the league's own win curve" in s for s in _text(spread))
    sim = R.sec_verdict(_ctx(sim={"p_home_win": 0.41, "trials": 4000}))
    assert sim["blocks"][0]["source"] == "sim" and sim["blocks"][0]["team"] == "GB"
    # With no price posted, nothing says the call follows one (step AIJ).
    said = _text(sim)
    assert not any("the price" in x for x in said), said
    assert "Nothing in the matchup, the records or the injury report tilts this one past our simulation's " \
        "number." in said and said[-1] == "No price was posted for this game, so the chance to win is our " \
        "simulation's, not the books'.", said
    assert abs(sim["blocks"][0]["chance"] - 0.59) < 1e-9 and sim["blocks"][0]["word"] == "A lean"
    assert R.sec_verdict(_ctx()) is None, "no number on the board, no call"
    coin = R.sec_verdict(_ctx(home_ml=-105, away_ml=-115))
    assert coin["blocks"][0]["word"] == "A coin flip", coin["blocks"][0]


def test_records_form_and_who_is_out_count_for_a_side():
    result = {"playoff_picture": {"teams": {"DET": {"wins": 8, "losses": 2}, "GB": {"wins": 4, "losses": 6}}},
              "team_recent": {"DET": [{"scored": 30, "allowed": 17}] * 4 + [{"scored": 20, "allowed": 24}],
                              "GB": [{"scored": 14, "allowed": 24}] * 3 + [{"scored": 27, "allowed": 21}] * 2}}
    g = {"home": "DET", "away": "GB", "home_ml": -200, "away_ml": 170,
         "scan": {"injuries": [{"player": "Jordan Love", "team": "GB", "position": "QB", "status": "Out"}]}}
    sec = R.sec_verdict(R.Ctx(g, result, sport="nfl", names=NAMES))
    said = _text(sec)
    for want in ("The Lions are 8-2, the Packers 4-6",
                 "The Lions have won 4 of their last 5 (outscoring teams by 9.6 points a game); the Packers 2 of 5",
                 "The Packers are without quarterback Jordan Love"):
        assert any(want in s for s in said), (want, said)


def test_the_other_leagues_say_their_own_facts():
    rep, _ = LEAGUES._attach(LEAGUES._mlb_board(), "mlb")
    mlb = _text(_verdict(rep))
    assert any("The starters: Zack Wheeler (PHI, expected ERA 3.05) against Javier Assad (CHC, 4.60)" in s
               for s in mlb), mlb
    assert "bets on our baseball ratings alone against the price lost 12.4%" in mlb[-1]
    rep, _ = LEAGUES._attach(LEAGUES._nhl_board(), "nhl")
    nhl = _text(_verdict(rep))
    assert any("In net: Anthony Stolarz (TOR) has stopped 4.2 more goals than expected lately; Jeremy Swayman "
               "(BOS) has let in 3.4 more goals than expected lately" in s for s in nhl), nhl
    board, meta = LEAGUES._nba_board()
    rep, _ = LEAGUES._attach(board, "nba", meta=meta)
    nba = _verdict(rep)
    assert nba["blocks"][0]["team"] == "BOS" and nba["blocks"][0]["word"] == "A clear favorite"
    assert _text(nba)[-1] == "The chance to win comes from the betting price, not from a number of ours.", \
        "no reasons, so the note does not point at any"


def test_the_page_draws_the_call_and_copies_it():
    assert 'if (b.type === "winner") {' in REPORT_JS and 'class="gr-winner-bar" role="img"' in REPORT_JS
    assert 'else if (b.type === "winner") {' in REPORT_JS
    assert 'out.push(`${b.word || "Our call"}: ${b.name || b.team} — ' in REPORT_JS
    assert ".gr-winner-bar > i {" in REPORT_CSS and ".gr-winner-p { color: var(--good);" in REPORT_CSS
    assert 'elif t == "winner":' in (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
