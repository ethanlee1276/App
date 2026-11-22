"""A quarterback back with a club he played for is read against his own games there (step ACJ, 22 November 2026).

Ethan: "Kirk Cousins was just traded back to the Vikings, and he had a long, good career at the Vikings where he
put up a lot of points and a lot of passing yards, and he had good chemistry with a lot of players. So we need to
implement a feature or data that uses that data as well when they realize a QB or another player is back with the
team they used to be on." What these hold:

  * the career splits off the play-by-play (engine/qblean) keep each starter's clean starts club by club: his
    attempts, completions, yards and touchdowns, and the receivers he threw to three times or more;
  * a starter back with a club he started for, after starting elsewhere, has that stint added up (four starts or
    more); one who never left, or never started there, has none;
  * the change's card and the report's line about it say it: his starts there, his line a game, and of the men
    on the club now, who drew the most of his targets then. It moves no number (chemfit.py's test R decides);
  * the box reads the doc of the old shape again that night, not on Wednesday's refit.

    python3 tests/test_a_starter_back_with_a_former_club_reads_his_games_there.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import qbchange as Q, qblean as L                    # noqa: E402


def _play(gid, team, qb, rec, comp="1", yds="8", td="0"):
    return {"season_type": "REG", "pass_attempt": "1", "sack": "0", "two_point_attempt": "0", "qb_spike": "0",
            "passer_player_id": qb, "posteam": team, "game_id": gid, "receiver_player_id": rec,
            "complete_pass": comp, "yards_gained": yds, "pass_touchdown": td}


def test_each_starters_games_are_kept_club_by_club():
    pos = {"wr1": "WR", "te1": "TE", "wr2": "WR"}
    names = {"kc": "Kirk Cousins", "wr1": "Justin Jefferson", "te1": "T.J. Hockenson", "wr2": "Adam Thielen"}
    rows = ([_play("g1", "MIN", "kc", "wr1", yds="15")] * 5 + [_play("g1", "MIN", "kc", "te1", td="1")] * 3
            + [_play("g1", "MIN", "kc", "wr2", comp="0", yds="0")] * 2
            + [_play("g2", "ATL", "kc", "wr2")] * 4)
    got = L.count_season(rows, pos, names)["kc"]
    assert got["starts"] == 2 and set(got["teams"]) == {"MIN", "ATL"}
    assert got["teams"]["MIN"] == {"starts": 1, "att": 10, "cmp": 8, "yds": 99, "td": 3, "targets": 10,
                                   "tgt": {"Justin Jefferson": 5, "T.J. Hockenson": 3}}, got["teams"]["MIN"]
    assert got["teams"]["ATL"]["tgt"] == {"Adam Thielen": 4}


def _line(starts, yds, td, tgt, att=None, cmp_=None):
    att = att if att is not None else 34 * starts
    return {"starts": starts, "att": att, "cmp": cmp_ if cmp_ is not None else round(att * 0.67), "yds": yds,
            "td": td, "targets": 30 * starts, "tgt": tgt}


def _doc():
    row = lambda teams: {"kc": {"name": "Kirk Cousins", "WR": 1, "TE": 1, "RB": 1, "starts": 1, "teams": teams}}  # noqa: E731
    return {"v": 2, "seasons": {
        "2022": row({"MIN": _line(17, 4547, 29, {"Justin Jefferson": 184, "T.J. Hockenson": 86})}),
        "2023": row({"MIN": _line(8, 2331, 18, {"Justin Jefferson": 49, "T.J. Hockenson": 70, "K.J. Osborn": 40})}),
        "2024": row({"ATL": _line(14, 3508, 18, {"Drake London": 120})}),
        "2026": row({"LV": _line(6, 1400, 8, {"Brock Bowers": 50}), "MIN": _line(2, 480, 3, {"Justin Jefferson": 20})}),
    }}


def test_a_starter_back_with_a_former_club_has_that_stint_added_up():
    r = L.reunion(_doc(), "Kirk Cousins", "MIN", 2026)
    assert (r["first"], r["last"], r["starts"], r["yds"], r["td"]) == (2022, 2023, 25, 6878, 47), r
    assert r["tgt"] == {"Justin Jefferson": 233, "T.J. Hockenson": 156, "K.J. Osborn": 40}
    assert L.reunion(_doc(), "Kirk Cousins", "ATL", 2026)["starts"] == 14, "back with any club he left"
    assert L.reunion(_doc(), "Kirk Cousins", "MIN", 2023) is None, "he had not left it yet"
    assert L.reunion(_doc(), "Kirk Cousins", "LV", 2026) is None, "never started there before he left"
    assert L.reunion(_doc(), "Kyler Murray", "MIN", 2026) is None
    short = _doc()
    short["seasons"]["2023"]["kc"]["teams"]["MIN"]["starts"] = 1
    short["seasons"]["2022"]["kc"]["teams"]["MIN"]["starts"] = 2
    assert L.reunion(short, "Kirk Cousins", "MIN", 2026) is None, "three starts are too few to say"
    assert L.reunion({"seasons": {"2025": {"x": {"name": "Kirk Cousins", "WR": 9}}}}, "Kirk Cousins", "MIN") is None, \
        "a doc of the old shape says nothing"


def test_the_card_and_the_report_say_it():
    r = L.reunion(_doc(), "Kirk Cousins", "MIN", 2026)
    w = L.reunion_words(r, "Kirk Cousins", "the Vikings", {"justin jefferson", "t j hockenson"})
    assert w.startswith("Kirk Cousins is back with the Vikings: in his 25 starts for them (2022–2023) he threw for "
                        "275 yards and 1.9 touchdowns a game, completing 67% of his passes"), w
    # Shares of all 750 targets he threw there (30 a start), the receivers under the line too.
    assert w.endswith("Of the receivers there now, Justin Jefferson drew 31%, T.J. Hockenson drew 21% of his targets "
                      "then"), w
    assert "Osborn" not in w, "only the men on the club now"
    stats = [{"recent_team": "MIN", "season": 2026, "week": 11, "player_display_name": "Justin Jefferson",
              "position": "WR", "targets": 9, "season_type": "REG"},
             {"recent_team": "MIN", "season": 2026, "week": 11, "player_display_name": "T.J. Hockenson",
              "position": "TE", "targets": 5, "season_type": "REG"},
             {"recent_team": "SF", "season": 2026, "week": 11, "player_display_name": "K.J. Osborn",
              "position": "WR", "targets": 3, "season_type": "REG"}]
    ch = {"team": "MIN", "starter": "Kyler Murray", "status": "OUT", "replacement": "Kirk Cousins",
          "tier": "similar", "replacement_attempts": 615}
    L.attach({"MIN": ch}, _doc(), stats, 12)
    assert ch["reunion"]["now_on"] == ["justin jefferson", "t j hockenson"] and ch["reunion"]["starts"] == 25
    card = Q.card(ch)
    assert card["reunion"].startswith("Kirk Cousins is back with the Vikings: in his 25 starts"), card["reunion"]
    assert "Osborn" not in card["reunion"]
    assert Q.club_words("MIN") == "the Vikings" and Q.club_words("SF") == "the 49ers" and Q.club_words("ZZZ") == "ZZZ"
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert 'if q.get("reunion"):' in gr and "text += f\". {q['reunion']}\"" in gr
    # Words only: nothing prices it.
    assert "reunion" not in (ROOT / "engine" / "qbchange.py").read_text(encoding="utf-8").split("def effect(")[1]


def test_the_box_reads_the_old_doc_again_that_night():
    mt = (ROOT / "engine" / "maintenance.py").read_text(encoding="utf-8")
    assert 'if _ql.on() and int((_ql.load() or {}).get("v") or 1) < _ql.DOC_VERSION:' in mt
    assert L.DOC_VERSION == 2
    doc = L.build([2025], load_pbp=lambda s: [_play("g1", "MIN", "kc", "wr1")] * 3,
                  load_roster=lambda s: [{"gsis_id": "kc", "full_name": "Kirk Cousins", "position": "QB"},
                                         {"gsis_id": "wr1", "full_name": "Justin Jefferson", "position": "WR"}],
                  have={"seasons": {"2025": {"old": {"name": "X"}}}})
    assert doc["v"] == 2 and "kc" in doc["seasons"]["2025"], "the old shape is read again, not kept"
    again = L.build([2025], load_pbp=lambda s: [], load_roster=lambda s: [], have=doc)
    assert again["seasons"]["2025"] == doc["seasons"]["2025"], "the new shape is kept"


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
