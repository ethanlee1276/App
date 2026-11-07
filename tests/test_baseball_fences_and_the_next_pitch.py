"""Baseball's two: a homer in how many of the 30 parks, and the next pitch.

Ethan, 2026-10-15, two of the sixteen ideas he asked to have built ("do
every one for every sport"): MLB "homer in X of 30 parks", labelled an
estimate, and next-pitch odds on the live pitch tracker. Neither moves a
number on any board.

What these hold: the fence runs straight from each pole to centre, a ball
clears it by its distance against the fence plus the wall's height, and a
ball on the ground, short or foul is not asked; the hit page keeps only
each ball's count and the season's card says which parks by the shorter
list; the next pitch is the pitcher's own mix in the count the pitch was
thrown in (the feed's count is the one after it), against this batter's
side, falling back by a stated order when a count is thin; the live build
reads the database read-only and a table that will not read costs only
the card; and both pages say what they are.

Run directly: `python3 tests/test_baseball_fences_and_the_next_pitch.py`
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine.mlb import fences as F                               # noqa: E402
from engine.mlb import nextpitch as N                            # noqa: E402
from engine.mlb.parks import PARKS                               # noqa: E402

MLB_JS = (ROOT / "web" / "js" / "chart-mlb.js").read_text(encoding="utf-8")
GC_JS = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")


def test_the_fence_runs_pole_to_centre_and_the_wall_counts():
    fenway = PARKS["fenway"]
    assert F.fence_at(fenway, -45) == fenway.lf_ft and F.fence_at(fenway, 0) == fenway.cf_ft
    assert F.fence_at(fenway, 45) == fenway.rf_ft
    assert F.fence_at(fenway, -22.5) == (fenway.lf_ft + fenway.cf_ft) / 2
    assert F.fence_at(fenway, 46) is None and F.fence_at(fenway, None) is None, "foul is not asked"
    assert F.wall_at(fenway, -30) == fenway.lf_wall_ft, "the Monster down the left-field line"
    assert F.wall_at(fenway, 0) == F.CENTRE_WALL_FT
    need = F.fence_at(fenway, -30) + fenway.lf_wall_ft
    assert F.clears(fenway, need, -30) and not F.clears(fenway, need - 1, -30)


def test_only_balls_in_the_air_far_enough_and_fair_are_asked():
    assert F.parks_out(420, 10, "ground_ball") is None and F.parks_out(420, 10, "popup") is None
    assert F.parks_out(240, 0) is None and F.parks_out(None, 0) is None and F.parks_out(400, None) is None
    assert F.parks_out(400, 50) is None
    assert len(F.parks_out(460, 0)) == len(PARKS), "460 to centre is out of every park"
    assert F.parks_out(300, 0) == [], "300 to centre is out of none"
    some = F.parks_out(380, -30, "line_drive")
    assert 0 < len(some) < len(PARKS) and set(some) <= set(PARKS)


def _pa(et, pk, d, keys=None, date="2026-09-01", opp="KC", ev=""):
    return {"et": et, "pk": pk, "d": d, "pko": keys if keys is not None else list(PARKS)[:pk], "date": date, "opp": opp,
            "ev": ev}


def test_the_season_card_names_the_shorter_list():
    keys = list(PARKS)
    pas = [_pa("home_run", 30, 440, keys), _pa("home_run", 3, 352, keys[:3], date="2026-09-03"),
           _pa("field_out", 12, 395, keys[:12], ev="Flyout"), _pa("double", 1, 360, keys[:1], ev="Double"),
           _pa("field_out", 0, 300, []), {"et": "strikeout"}]
    b = F.season_block(pas)
    assert [r["n"] for r in b["hr"]] == [30, 3], "most parks first"
    assert b["no_doubt"] == 1 and b["doubters"] == 1 and b["parks"] == 30
    assert [r["n"] for r in b["near"]] == [12, 1] and b["near_n"] == 2, "a ball out of no park is not a near miss"
    assert b["hr"][0]["held_by"] == [] and "out_of" not in b["hr"][0], "out of all of them: none held it"
    assert b["hr"][1]["out_of"] == sorted(PARKS[k].team for k in keys[:3])
    assert b["near"][0]["ev"] == "Flyout" and b["near"][0]["date"] == "2026-09-01"
    assert F.season_block([{"et": "single"}]) is None


def test_the_hit_page_keeps_only_each_balls_count():
    import test_mlb_hit_tracker_and_pitch_chart as T
    from engine.mlb import charts as MC
    d = MC.hits_chart(T._conn(), "Aaron Judge")
    pas = [p for g in d["games"] for p in g["pas"]]
    assert all("pko" not in p for p in pas), "which parks rides on the season's card, not on every ball"
    hr = next(p for p in pas if p["et"] == "home_run")
    assert hr["pk"] == 30, "431 feet to left-centre is out of every park"
    assert all("pk" not in p for p in pas if p["et"] != "home_run"), "a ground ball and a 180-foot liner are not asked"
    assert d["fences"]["hr"][0]["n"] == 30 and d["fences"]["no_doubt"] == 1 and d["fences"]["near"] == []


def test_the_count_a_pitch_was_thrown_in_is_the_one_before_it():
    rows = [{"game_pk": 1, "at_bat": 0, "n": 1, "pitch_type": "FF", "bat_side": "L", "balls": 0, "strikes": 1},
            {"game_pk": 1, "at_bat": 0, "n": 2, "pitch_type": "SL", "bat_side": "L", "balls": 0, "strikes": 2},
            {"game_pk": 1, "at_bat": 0, "n": 3, "pitch_type": "SL", "bat_side": "L", "balls": 0, "strikes": 3},
            {"game_pk": 1, "at_bat": 1, "n": 1, "pitch_type": "CH", "bat_side": "R", "balls": None, "strikes": None},
            {"game_pk": 1, "at_bat": 1, "n": 2, "pitch_type": "FF", "bat_side": "R", "balls": 1, "strikes": 0},
            {"game_pk": 1, "at_bat": 2, "n": 1, "pitch_type": "", "bat_side": "R", "balls": 1, "strikes": 0}]
    got = N.counts_before(rows)
    assert got == [("0-0", "FF", "L"), ("0-1", "SL", "L"), ("0-2", "SL", "L"), ("0-0", "CH", "R")], got
    assert N.family("0-2") == "ahead" and N.family("3-1") == "behind" and N.family("2-2") == "even"


def test_a_thin_count_falls_back_in_the_stated_order():
    seen = ([("0-0", "FF", "L")] * 40 + [("0-0", "SL", "L")] * 10          # 50 in 0-0 to lefties
            + [("3-0", "FF", "R")] * 35                                     # 3-0 only to righties
            + [("2-0", "CH", "L")] * 5 + [("3-1", "CH", "L")] * 30)         # thin 2-0, a behind family to lean on
    t = N.table(seen, "L")
    assert t["0-0"]["basis"] == "count" and t["0-0"]["n"] == 50
    assert t["0-0"]["mix"][:2] == [["FF", "Four-seam", 0.8], ["SL", "Slider", 0.2]]
    assert t["3-0"]["basis"] == "count_all" and t["3-0"]["mix"][0][0] == "FF"
    assert t["2-0"]["basis"] == "family" and t["2-0"]["fam"] == "behind" and t["2-0"]["n"] == 35
    assert t["1-1"]["basis"] == "family" and t["1-1"]["n"] == 50, "even counts to lefties: the 0-0s"
    many = [("0-0", k, "L") for k in ("FF", "SI", "FC", "SL", "CU", "CH", "FS") for _ in range(10)]
    mix = N.table(many, "L")["0-0"]["mix"]
    assert len(mix) == N.TOP + 1 and mix[-1][:2] == ["", "Other"] and abs(sum(m[2] for m in mix) - 1) < 0.01
    assert all(v["basis"] in ("count_all", "family_all", "all") for v in N.table(seen, "").values()), \
        "no side known: every batter"


def test_the_live_build_reads_the_table_read_only():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE mlb_pitches (game_pk, at_bat, n, season, pitcher_id, pitch_type, bat_side, balls, strikes)")
    for i in range(40):
        conn.execute("INSERT INTO mlb_pitches VALUES (?,?,?,?,?,?,?,?,?)", (i, 0, 1, 2026, 7, "SI", "R", 1, 0))
        conn.execute("INSERT INTO mlb_pitches VALUES (?,?,?,?,?,?,?,?,?)", (i, 0, 2, 2026, 7, "SL", "R", 1, 1))
    conn.execute("INSERT INTO mlb_pitches VALUES (?,?,?,?,?,?,?,?,?)", (99, 0, 1, 2024, 7, "KN", "R", 0, 0))
    N._CACHE.clear()
    got = N.for_current({"pitcher_id": 7, "bat_side": "R"}, conn=conn)
    assert got["n"] == 80 and got["side"] == "R"
    assert got["counts"]["0-0"]["mix"][0][0] == "SI" and got["counts"]["1-0"]["mix"][0][0] == "SL"
    assert all(m[0] != "KN" for v in got["counts"].values() for m in v["mix"]), "two seasons back is not read"
    assert N.for_current(None) is None and N.for_current({"pitcher_id": None}) is None
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.db"
        assert N.for_current({"pitcher_id": 8, "bat_side": "L"}, db_path=missing) is None
        assert not missing.exists(), "the live build never creates the database"
    src = (ROOT / "engine" / "mlb" / "nextpitch.py").read_text(encoding="utf-8")
    assert 'f"file:{path}?mode=ro", uri=True' in src
    live = (ROOT / "live_build.py").read_text(encoding="utf-8")
    assert 'nxt = for_current(doc["current"])' in live and 'doc["next_pitch"] = nxt' in live


def test_the_at_bat_in_progress_says_his_side():
    from engine.mlb.sources import pbp
    pay = {"allPlays": [{"result": {}, "about": {"atBatIndex": 3, "inning": 2, "halfInning": "top"},
                         "matchup": {"batter": {"id": 1, "fullName": "A"}, "batSide": {"code": "L"},
                                     "pitcher": {"id": 2, "fullName": "B"}}, "playEvents": []}]}
    assert pbp.current_at_bat(pay)["bat_side"] == "L"
    pay["allPlays"][0]["matchup"].pop("batSide")
    assert pbp.current_at_bat(pay)["bat_side"] == ""


def _np():
    return {"pitcher_id": 1, "side": "R", "n": 900, "counts": {
        "2-2": {"n": 64, "basis": "count", "fam": "even", "mix": [["SL", "Slider", 0.55], ["FF", "Four-seam", 0.45]]},
        "0-0": {"n": 40, "basis": "count_all", "fam": "even", "mix": [["FF", "Four-seam", 0.7], ["CH", "Changeup", 0.3]]}}}


def test_the_live_zone_shows_the_next_pitch():
    import json
    import test_the_live_trackers as L
    live = L._mlb_doc()
    live["current"].update(pitcher_id=1)
    live["next_pitch"] = _np()
    up = L._mlb_doc(done=True)
    up["current"] = {"pitcher_id": 1, "pitcher": "Tarik Skubal", "pitches": 0}
    up["next_pitch"] = _np()
    other = L._mlb_doc()
    other["current"].update(pitcher_id=2)
    other["next_pitch"] = _np()
    got = L._node(f"""return [Q.zone({json.dumps(live)}), Q.zone({json.dumps(up)}), Q.zone({json.dumps(other)}),
                             Q.zone({json.dumps(L._mlb_doc())})];""")
    if got is None:
        return
    now, fresh, wrong, none = got
    assert "Next pitch · 2-2" in now and ">Slider<" in now and ">55%<" in now
    assert "in 2-2 counts to right-handed batters" in now and "64 pitches" in now and "not a forecast" in now
    assert "Next pitch · 0-0" in fresh and "in 0-0 counts to every batter" in fresh, "the batter just up starts 0-0"
    assert "Next pitch" not in wrong, "a table for another pitcher is not shown"
    assert "Next pitch" not in none


def test_the_hit_page_draws_the_card_and_says_estimate():
    import json
    import test_mlb_hit_tracker_and_pitch_chart as T
    keys = list(PARKS)
    d = {"fences": F.season_block([_pa("home_run", 30, 440, keys), _pa("home_run", 3, 352, keys[:3]),
                                   _pa("field_out", 12, 395, keys[:12], ev="Flyout")])}
    got = T._node(f"""const SP = T.DRAW.spray, d = {json.dumps(d)};
      return {{ card: SP._t.fencesCard(d), none: SP._t.fencesCard({{}}),
                tip: SP.tip({{ et: "home_run", inn: 1, p: "X", pk: 28 }}), quiet: SP.tip({{ et: "field_out", inn: 1, p: "X", pk: 0 }}) }};""")
    if got is None:
        return
    card = got["card"]
    assert "A homer in how many of the 30 parks?" in card and ">Estimate<" in card and "cc-pill mute" in card
    assert card.index(">3<small>of 30") < card.index(">30<small>of 30"), "the doubters first"
    assert "Not a homer, but gone somewhere" in card and "Flyout" in card and "out only in" in card
    assert "No air, altitude or wind" in card and "Nothing on the board reads it." in card
    assert got["none"] == ""
    assert "out in 28 of 30 parks (estimate)" in got["tip"] and "parks" not in got["quiet"]
    assert "+ seasonStats(d, sport) + fencesCard(d) + splits;" in MLB_JS
    assert "${nextPitch(d, ps, done)}</div>`;" in GC_JS


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
