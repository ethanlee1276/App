"""A questionable starting quarterback gets both versions of his game's report (step ABS, 22 November 2026).

Ethan, the Sunday morning: "we can start making game reports, at least for NFL and college football at first, for
like if a significant player is out. As in, example, today for the Lions game, it's not confirmed if Baker Mayfield
is playing or not yet. So we should have a game report ready for if Baker Mayfield is in and one if he's not in".
A starter listed out or doubtful was already a quarterback change (engine/qbchange); one listed questionable, or a
game-time decision, moved nothing and the report spoke to one side of the game's biggest question. What these hold:

  * a starter questionable or a game-time decision is unsure; one out or doubtful (priced as out) is not;
  * his team's props are priced both ways through the board's own pricing: as the board has them, and with the
    change qbchange would make if he sat (his backup, the measured receivers' effect); his own props left out;
  * the slate's game is left as it was found;
  * the report opens a section beside our picks that says both: who starts if he sits, what it does, and each
    number that moves, both ways; the NFL's build makes the versions and the page opens the section;
  * the injury board's newest word on him (its blurb, a recent one only) is said, with when it was posted.

    python3 tests/test_a_questionable_starter_gets_both_versions.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as GR, qbchange as QC, qbscenario as Q   # noqa: E402
from engine.data_loader import load_slate              # noqa: E402
from engine.models import Injury                       # noqa: E402
from engine.pipeline import price_props                # noqa: E402

QB = {"teams": {"DET": {"starter": "Jared Goff", "backup": "Hendon Hooker"},
                "GB": {"starter": "Jordan Love", "backup": "Malik Willis"}}, "passing": {}}


def _hurt(status, team="DET", who="Jared Goff"):
    return [Injury(player=who, team=team, position="QB", role="qb", status=status)]


def _price(sub):
    return price_props(sub, sport="nfl")


STARTERS = Q.nfl_starters(QB)


def _changes(inj):
    return QC.changes(QB, inj, None)


def test_questionable_and_game_time_are_unsure_and_out_or_doubtful_are_not():
    assert STARTERS == {"DET": "Jared Goff", "GB": "Jordan Love"}
    assert Q.unsure_starters(STARTERS, _hurt("QUESTIONABLE")) == {"DET": {"starter": "Jared Goff", "status": "QUESTIONABLE"}}
    assert Q.unsure_starters(STARTERS, _hurt("GTD")) == {"DET": {"starter": "Jared Goff", "status": "GTD"}}
    for status in ("OUT", "DOUBTFUL", "IR", ""):
        assert Q.unsure_starters(STARTERS, _hurt(status)) == {}, status
    assert Q.unsure_starters(STARTERS, _hurt("QUESTIONABLE", who="Amon-Ra St. Brown")) == {}, "a receiver is not the starter"
    assert Q.unsure_starters(None, None) == {}
    assert Q.cfb_starters({"OSU": {"usual": "Julian Sayin"}, "MICH": {}}) == {"OSU": "Julian Sayin"}


def test_his_teams_props_are_priced_both_ways_and_the_game_is_left_as_found():
    slate = load_slate(ROOT / "data" / "sample_slate.json")
    game = next(g for g in slate.games if "DET" in (g.home, g.away))
    before = getattr(game, "qb_changes", None)
    out = Q.build(slate, STARTERS, _hurt("QUESTIONABLE"), _changes, _price)
    assert getattr(game, "qb_changes", None) == before
    assert len(out) == 1 and out[0]["team"] == "DET" and out[0]["replacement"] == "Hendon Hooker"
    assert out[0]["tier"] == "downgrade" and out[0]["headline"] == "Jared Goff (QUESTIONABLE) — Hendon Hooker starts"
    rows = {(r["player"], r["market"]): r for r in out[0]["rows"]}
    wr = rows[("Amon-Ra St. Brown", "rec_yds")]
    assert wr["sits"] < wr["plays"], wr
    rb = rows[("Jahmyr Gibbs", "rush_yds")]
    assert rb["sits"] == rb["plays"], "nothing measured moves a back"
    assert out[0]["rows"][0]["player"] == "Amon-Ra St. Brown", "the biggest move first"
    assert all(r["player"] != "Jared Goff" for r in out[0]["rows"])
    # A board's own version: the first pricing, as the board has it.
    board = {(r["player"], r["market"], float(r["line"])): Q._p_over(r) for r in _price(slate) if r.get("team") == "DET"}
    assert abs(board[("Amon-Ra St. Brown", "rec_yds", wr["line"])] - wr["plays"]) < 1e-3


def test_a_team_that_fails_is_left_out_and_nothing_raises():
    slate = load_slate(ROOT / "data" / "sample_slate.json")

    def broken(sub):
        raise RuntimeError("no pricing")
    assert Q.build(slate, STARTERS, _hurt("QUESTIONABLE"), _changes, broken) == []
    assert Q.build(slate, {}, _hurt("QUESTIONABLE"), _changes, _price) == []


def _report(scen):
    g = {"home": "DET", "away": "GB", "date": "2099-10-25", "kickoff": "13:00", "spread": -2.5, "total": 47.5}
    result = {"date": "2099-W08", "games": [g], "likely_board": {"rows": [], "held": []}, "most_likely": [],
              "qb_scenarios": scen}
    return GR.build(g, result, sport="nfl", names={"GB": "Packers", "DET": "Lions"})


def test_the_report_says_both_beside_our_picks():
    scen = [{"team": "DET", "starter": "Jared Goff", "status": "QUESTIONABLE", "replacement": "Hendon Hooker",
             "tier": "downgrade", "headline": "x",
             "rows": [{"player": "Amon-Ra St. Brown", "position": "WR", "market": "rec_yds", "line": 94.5,
                       "plays": 0.4893, "sits": 0.4454},
                      {"player": "Jahmyr Gibbs", "position": "RB", "market": "rush_yds", "line": 75.5,
                       "plays": 0.4758, "sits": 0.4758}]}]
    rep = _report(scen)
    keys = [s["key"] for s in rep["sections"]]
    assert "swing" in keys
    sec = next(s for s in rep["sections"] if s["key"] == "swing")
    text = " ".join(str(b.get("text") or "") + " ".join(map(str, b.get("items") or [])) for b in sec["blocks"])
    assert "Jared Goff, the Lions' starting quarterback, is questionable: the inactives come out" in text, text
    assert "If he sits, Hendon Hooker starts" in text and "10% fewer yards" in text
    assert "49% if he plays, 45% if he sits" in text, text
    assert "Jahmyr Gibbs" not in text, "a number that does not move is not listed"
    assert "swing" not in [s["key"] for s in _report([])["sections"]], "no unsure starter, no section"


def test_the_newest_word_on_him_is_said_with_when_it_was_posted():
    # ESPN's board files a blurb with each designation; Mayfield's, the Sunday morning, said which way it leaned.
    rows = [{"team": "Tampa Bay Buccaneers", "player": "Baker Mayfield", "status": "Questionable",
             "date": "2026-11-22T12:24Z", "comment": "Mayfield (foot/right thumb) is slated to play in Sunday's "
             "game against the Lions, Ian Rapoport of NFL Network reports."},
            {"team": "Tampa Bay Buccaneers", "player": "Baker Mayfield", "status": "Questionable",
             "date": "2026-11-20T20:00Z", "comment": "older"},
            {"team": "Detroit Lions", "player": "Jared Goff", "status": "Questionable",
             "date": "2026-11-12T12:00Z", "comment": "a week old"}]
    now = 1795357200.0                                      # 2026-11-22 14:20 UTC
    scen = [{"team": "TB", "starter": "Baker Mayfield"}, {"team": "DET", "starter": "Jared Goff"},
            {"team": "GB", "starter": "Jordan Love"}]
    Q.attach_news(scen, "nfl", rows=rows, team_key={"Tampa Bay Buccaneers": "TB", "Detroit Lions": "DET"}.get,
                  now=now)
    assert scen[0]["news"] == {"text": rows[0]["comment"], "posted": "2026-11-22T12:24:00Z"}, scen[0]
    assert "news" not in scen[1], "a week-old blurb is about another game"
    assert "news" not in scen[2], "no blurb, nothing said"
    assert Q.attach_news([{"team": "TB", "starter": "X"}], "nfl", rows=[{"bad": 1}], now=now)  # never raises
    sc = {"team": "DET", "starter": "Jared Goff", "status": "QUESTIONABLE", "replacement": "Hendon Hooker",
          "tier": "downgrade", "headline": "x", "rows": [],
          "news": {"text": "Goff (ankle) is expected to play Sunday.", "posted": "2026-11-22T12:24:00Z"}}
    sec = next(s for s in _report([sc])["sections"] if s["key"] == "swing")
    line = next(b for b in sec["blocks"] if "newest word" in str(b.get("text")))
    assert line["text"] == ("The newest word on him, posted at Sun 7:24 AM ET: Goff (ankle) is expected to play "
                            "Sunday."), line
    assert line["post_at"] == "2026-11-22T12:24:00Z", "the page says the time in the reader's zone"
    assert '_qs.attach_news(result["qb_scenarios"], "nfl")' in (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert '_qs.attach_news(out["qb_scenarios"], "cfb", team_key=lambda name: _rt(name, lookup))' in \
        (ROOT / "cfb_build.py").read_text(encoding="utf-8")


def test_the_nfl_build_makes_them_and_the_page_opens_the_section():
    nb = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    i = nb.index("result = run_slate(slate, config, model=model, nfl_usage=nfl_usage,")
    assert nb.index('result["qb_scenarios"] = _qs.build(', i) > i
    assert "lambda inj: _qls.attach(_qbc.changes(_qb_now, inj, depth_qb1, news_qb=_news_now), _qls_doc," in nb
    assert "lambda sub: _price_props(sub, config, model=model, nfl_usage=nfl_usage, team_notes=qb_notes," in nb
    cb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    j = cb.index('out["recommendations"] = _price_props(_prop_slate, sport="cfb")')
    assert cb.index('out["qb_scenarios"] = _qs.build(', j) > j and "lambda inj: _cq2.changes(_pass, inj, _pq)," in cb
    lu = (ROOT / "engine" / "cfb" / "lineup.py").read_text(encoding="utf-8")
    assert '"passers": passers, "priced_qbs": priced_qbs(slate)}' in lu
    js = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'const OPEN_SECTIONS = ["graded", "card", "swing", "short"];' in js
    assert GR.SECTIONS[0] is GR.sec_swing


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
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
