"""The matchup scan, for every college game.

Ethan, 2026-09-24: "use this as what exactly needs to be done when we look
at every single NFL game and college football game". College has no
defender files and no charting, so its scan is CollegeFootballData's
advanced season table (engine/sources/cfbd.parse_advanced) ranked across
the FBS: overall, passing, rushing, success, explosiveness, and the two
questions college adds — havoc, and the line of scrimmage. The cutoffs
scale with the league, so 20th of 134 is not read like 20th of 32.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                               # noqa: E402
from engine.sources import cfbd                                 # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()


def _row(team, plays, ppa, havoc_off, havoc_def, line_off=3.0, stuff_def=0.18):
    side = lambda p, h, line, stuff: {                           # noqa: E731
        "plays": plays, "ppa": p, "successRate": 0.42, "explosiveness": 1.2,
        "lineYards": line, "stuffRate": stuff, "havoc": {"total": h},
        "passingPlays": {"ppa": p}, "rushingPlays": {"ppa": p}}
    return {"team": team, "offense": side(ppa, havoc_off, line_off, 0.2),
            "defense": side(-ppa, havoc_def, 3.0, stuff_def)}


def test_the_cfbd_table_parses_into_the_scan_units():
    got = cfbd.parse_advanced([_row("Georgia", 700, 0.3, 0.12, 0.22), {"offense": {}}])
    assert list(got) == ["Georgia"], "a row with no school is dropped"
    g = got["Georgia"]
    assert g["plays"] == 700 and g["off"]["overall"] == 0.3 and g["def"]["havoc"] == 0.22
    assert set(g["off"]) == set(G.CFB_UNITS)


def test_havoc_and_stuffs_rank_the_right_way_round():
    cur = cfbd.parse_advanced([_row("UGA", 700, 0.3, 0.10, 0.25, stuff_def=0.25),
                               _row("TENN", 700, 0.1, 0.20, 0.12, stuff_def=0.10)])
    r = G.cfb_ratings(cur)
    assert r["UGA"]["off"]["havoc"]["rank"] == 1, "an offence allowing less havoc is better"
    assert r["UGA"]["def"]["havoc"]["rank"] == 1, "a defence making more havoc is better"
    assert r["UGA"]["def"]["stuff"]["rank"] == 1, "a front stuffing more runs is better"
    assert r["UGA"]["def"]["overall"]["rank"] == 1, "the defence allowing less is first"


def test_a_few_games_lean_on_last_season():
    cur = cfbd.parse_advanced([_row("A", 140, 0.4, 0.1, 0.2), _row("B", 140, 0.0, 0.1, 0.2)])
    pri = cfbd.parse_advanced([_row("A", 900, -0.2, 0.1, 0.2), _row("B", 900, 0.0, 0.1, 0.2)])
    r = G.cfb_ratings(cur, pri)
    assert r["A"]["blend"] == round(140 / (140 + G.CFB_PRIOR_PLAYS), 2)
    assert r["A"]["off"]["overall"]["value"] < 0.4 * 0.5, "two games are mostly last season"
    assert G.cfb_ratings(cur)["A"]["blend"] == 1.0, "no prior, nothing to lean on"


def test_the_cutoffs_scale_with_the_league():
    assert G._strong(8) and not G._strong(9), "8th of 32 is the top quarter"
    assert G._weak(21) and not G._weak(20)
    assert G._strong(30, 134) and not G._weak(30, 134), "30th of 134 is good, not weak"
    assert G._weak(90, 134) and not G._weak(80, 134)


def _board():
    teams = [("Georgia", 0.35, 0.10, 0.24)] + [(f"T{i}", 0.2 - i * 0.004, 0.14, 0.18) for i in range(80)]
    teams += [("Tennessee", -0.2, 0.22, 0.10)]
    rows = [_row(t, 700, p, ho, hd) for t, p, ho, hd in teams]
    keys = {"Georgia": "UGA", "Tennessee": "TENN"}
    keys.update({f"T{i}": f"T{i}" for i in range(80)})
    out = {"games": [{"home": "UGA", "away": "TENN"}, {"home": "UGA", "away": "NOPE"}],
           "recommendations": [{"player": "Gunner Stockton", "team": "UGA", "opponent": "TENN",
                                "position": "QB", "market": "pass_yds", "hit_prob": 0.68, "odds": -140}]}
    return out, rows, keys


def test_every_game_with_both_teams_rated_is_scanned():
    out, rows, keys = _board()
    n = G.attach_cfb(out, 2026, keys.get, fetch=lambda year: cfbd.parse_advanced(rows))
    assert n == 1, "a school the table does not know is not guessed at"
    scan = out["games"][0]["scan"]
    assert scan["method"] == {"teams": 82, "opponent_adjusted": False}
    assert "players" not in scan and "microscope" not in scan, "the reads are paid"
    assert "scan" not in out["games"][1]
    reads = out["scan_reads"]["TENN@UGA"]
    assert [p["player"] for p in reads["players"]] == ["Gunner Stockton"]
    assert any("pass defense ranks 82nd" in t for t in reads["players"][0]["pro"])
    units = {e["unit"] for e in scan["edges"]}
    assert "havoc" in units, "Tennessee's offence gives up the most havoc to the best havoc defence"


def test_no_key_scans_nothing_and_says_so():
    out, _rows, keys = _board()

    def down(year):
        raise cfbd.DataUnavailable("no CFBD key")
    assert G.attach_cfb(out, 2026, keys.get, fetch=down) == 0
    assert "scan" not in out["games"][0] and "scan_reads" not in out


def test_the_build_scans_and_never_fails_on_it():
    i = BUILD.index("_scan.attach_cfb(")
    block = BUILD[BUILD.rindex("try:", 0, i):BUILD.index("matchup scan skipped", i)]
    assert "except Exception" in block and "cfbdata.resolve_team(school, lookup)" in block
    assert BUILD.index("_scan.attach_cfb(") < BUILD.index('out["status"] = "slate"')


def test_the_page_ranks_the_league_it_was_given():
    fn = APP[APP.index("function matchupScanHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "Ranked 1–${n}" in fn and "not adjusted for schedule" in fn
    assert "CollegeFootballData" in fn
    for unit in ('["havoc", "Havoc"', '["line", "Line yards"', '["stuff", "Runs stuffed at the line"'):
        assert unit in APP, unit
    cov = APP[APP.index("function scanCoverageHTML("):]
    assert 'return "";' in cov[:cov.index("\n}\n")], "no coverage card for a college defence"


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
