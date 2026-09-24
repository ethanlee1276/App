"""The matchup scan: corners, scheme, injuries and a read on every player.

Ethan, 2026-09-24, with a Falcons @ Packers breakdown he wants for every
game: "what players could shine and what players couldn't and where
there's holes in the defense and offense". engine/sources/nflscheme reads
the defender-level files (PFR coverage allowed, participation charting);
engine/gamescan sets them against each game and reads every player with
a prop. The reads and their props are paid (`scan_reads`); the rest of
the scan rides free on the game.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G, gate                          # noqa: E402
from engine.sources import nflscheme as N                        # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
BUILD = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()


def _inj(player, team, pos, status):
    return types.SimpleNamespace(player=player, team=team, position=pos, status=status, role="")


# ── the defender files ──────────────────────────────────────────────────────


def test_passer_rating_is_the_nfl_formula_on_the_season_sums():
    assert N.passer_rating(20, 13, 150, 1, 0) == 104.2, "(1.75 + 1.125 + 1.0 + 2.375) / 6"
    assert N.passer_rating(10, 10, 300, 5, 0) == 158.3, "the cap on every term"
    assert N.passer_rating(0, 0, 0, 0, 0) is None


def test_names_join_across_the_injury_report_and_pfr():
    assert N.name_key("A.J. Terrell") == N.name_key("AJ Terrell")
    assert N.name_key("Billy Bowman Jr.") == N.name_key("Billy Bowman")
    assert N.name_key("Ja'Marr Chase") == N.name_key("JaMarr Chase")


def test_defenders_sum_the_season_and_rate_it():
    rows = [{"game_type": "REG", "team": "ATL", "pfr_player_name": "Mike Hughes", "def_targets": "8",
             "def_completions_allowed": "4", "def_yards_allowed": "50", "def_receiving_td_allowed": "1",
             "def_ints": "0", "def_tackles_combined": "4", "def_missed_tackles": "1", "def_pressures": "0"},
            {"game_type": "REG", "team": "ATL", "pfr_player_name": "Mike Hughes", "def_targets": "4",
             "def_completions_allowed": "4", "def_yards_allowed": "74", "def_receiving_td_allowed": "0",
             "def_ints": "0", "def_tackles_combined": "3", "def_missed_tackles": "0"}]
    d = N.defenders(rows)[("ATL", "mike hughes")]
    assert (d["games"], d["targets"], d["yds_per_tgt"]) == (2, 12.0, 10.3)
    assert d["rating"] == N.passer_rating(12, 8, 124, 1, 0)
    assert N.team_tackling(rows * 3) == {"ATL": round(3 / 24, 3)}


def test_scheme_reads_the_defence_off_the_game_id():
    part = [{"nflverse_game_id": "2025_01_ATL_GB", "possession_team": "ATL",
             "defense_man_zone_type": "ZONE_COVERAGE", "defense_coverage_type": "COVER_2",
             "number_of_pass_rushers": "4", "was_pressure": "FALSE"}] * 60
    part += [{"nflverse_game_id": "2025_01_ATL_GB", "possession_team": "ATL",
              "defense_man_zone_type": "MAN_COVERAGE", "defense_coverage_type": "COVER_1",
              "number_of_pass_rushers": "5", "was_pressure": "TRUE"}] * 40
    s = N.scheme(part)["GB"]
    assert (s["zone"], s["man"], s["mofo"], s["mofc"], s["blitz"], s["pressure"]) == (0.6, 0.4, 0.6, 0.4, 0.4, 0.4)
    assert "ATL" not in N.scheme(part), "the offence is not the defence"


def test_receiver_splits_join_the_play_by_play():
    part = [{"nflverse_game_id": "g1", "play_id": "10", "defense_man_zone_type": "ZONE_COVERAGE",
             "defense_coverage_type": "COVER_3"}]
    pbp = [{"game_id": "g1", "play_id": "10.0", "receiver_player_name": "D.London", "posteam": "ATL",
            "yards_gained": "18", "complete_pass": "1"}]
    got = N.receiver_splits(part, pbp)[("ATL", "D.London")]
    assert got["zone"] == [1, 18.0] and got["mofc"] == [1, 18.0] and got["man"] == [0, 0.0]


# ── the scan ────────────────────────────────────────────────────────────────


CHART = {"ATL": [{"position": "LCB", "players": ["A.J. Terrell", "C.J. Henderson"]},
                 {"position": "RCB", "players": ["Mike Hughes", "Mike Ford"]},
                 {"position": "NB", "players": ["Billy Bowman Jr.", "Sydney Brown"]}]}
DEF = {("ATL", "cj henderson"): {"name": "C.J. Henderson", "targets": 9, "yds_per_tgt": 4.7, "rating": 104.9, "td": 1},
       ("ATL", "mike hughes"): {"name": "Mike Hughes", "targets": 12, "yds_per_tgt": 10.3, "rating": 121.5, "td": 1}}


def test_a_starter_out_is_named_and_the_next_man_up_steps_in():
    room = G.coverage_room("ATL", CHART["ATL"], DEF, None, [_inj("A.J. Terrell", "ATL", "CB", "IR")])
    assert room["missing"] == [{"name": "A.J. Terrell", "spot": "LCB", "status": "IR"}]
    lcb = room["corners"][0]
    assert (lcb["name"], lcb["next_man_up"]) == ("C.J. Henderson", True)
    assert room["weakest"] == "Mike Hughes", "the starter allowing the most, past the bar"


def test_a_receiver_read_counts_its_reasons():
    ratings = {"GB": {"off": {}, "def": {}}, "ATL": {"off": {}, "def": {"passing": {"rank": 24}}}}
    room = G.coverage_room("ATL", CHART["ATL"], DEF, None, [_inj("A.J. Terrell", "ATL", "CB", "IR")])
    x = G.player_read("Christian Watson", "GB", "ATL", "WR",
                      usage={"tgt_share": 0.29, "targets_pg": 9.5, "games": 2}, ratings=ratings,
                      room=room, scheme={"zone": 0.67, "man": 0.33},
                      split={"zone": [41, 467.0], "man": [21, 180.0]}, tackling={}, line_out=[], mates_out=[])
    assert x["read"] == "breakout" and len(x["pro"]) == 5 and not x["con"]
    thin = G.player_read("Kyle Pitts", "ATL", "GB", "TE", usage={"tgt_share": 0.07, "games": 2},
                         ratings={"GB": {"def": {"passing": {"rank": 3}}}}, room={}, scheme={},
                         split={}, tackling={}, line_out=[], mates_out=[])
    assert thin["read"] == "avoid" and len(thin["con"]) == 2


def test_the_reads_are_paid_and_the_facts_ride_the_game():
    assert "scan_reads" in gate.PAID_KEYS
    real = (G.unit_ratings, N.load_pfr_def, G.scheme_tables)
    G.unit_ratings = lambda *a, **k: {}
    N.load_pfr_def = lambda season: []
    G.scheme_tables = lambda season: {"season": 2025, "defense": {}, "receivers": {}}
    import engine.sources.nflverse as NV
    wk, sn = NV.load_weekly_stats, NV.load_snap_counts
    NV.load_weekly_stats = lambda s: []
    NV.load_snap_counts = lambda s: []
    try:
        result = {"games": [{"home": "GB", "away": "ATL"}],
                  "recommendations": [{"player": "Christian Watson", "team": "GB", "opponent": "ATL",
                                       "position": "WR", "market": "rec_yds", "hit_prob": 0.7, "odds": -150}]}
        slate = types.SimpleNamespace(games=[types.SimpleNamespace(home="GB", away="ATL", injuries=[])])
        assert G.attach_nfl(result, slate, 2026, 3, conn=object()) == 1
    finally:
        G.unit_ratings, N.load_pfr_def, G.scheme_tables = real
        NV.load_weekly_stats, NV.load_snap_counts = wk, sn
    scan = result["games"][0]["scan"]
    assert "players" not in scan and "microscope" not in scan
    assert [p["player"] for p in result["scan_reads"]["ATL@GB"]["players"]] == ["Christian Watson"]
    public = gate.redact(result, "recommendations.json")
    assert public["scan_reads"] == {} and public["games"][0]["scan"] == scan


def test_a_prop_clears_only_at_65_and_no_heavier_than_minus_250():
    reads = G.scan_game("GB", "ATL", ratings={"ATL": {"def": {"passing": {"rank": 30}}, "off": {}},
                                              "GB": {"off": {}, "def": {}}},
                        charts={}, defenders_now={}, usage={("GB", "christian watson"): {"tgt_share": 0.3, "targets_pg": 9, "games": 2}},
                        props=[{"player": "Christian Watson", "team": "GB", "position": "WR", "market": m,
                                "hit_prob": p, "odds": o} for m, p, o in
                               [("rec_yds", 0.66, -180), ("receptions", 0.70, -260), ("rec_yds", 0.60, -120)]])
    got = [(m["prob"], m["clears"]) for m in reads["microscope"]]
    assert got == [(0.70, False), (0.66, True), (0.60, False)]


def test_a_questionable_player_reads_as_if():
    txt = G._opens(_inj("Billy Bowman Jr.", "ATL", "CB", "QUESTIONABLE"), "ATL", "GB", {}, CHART, {})
    assert txt.startswith("If he sits — ATL's coverage thins — Sydney Brown steps in")


# ── Ask and the pick page ──────────────────────────────────────────────────


def _scanned_board():
    scan = {"units": {"GB": {"off": {"passing": {"rank": 5, "value": 0.2}}, "def": {}},
                      "ATL": {"off": {}, "def": {"passing": {"rank": 27, "value": 0.1}}}},
            "edges": [{"unit": "passing", "off": "GB", "def": "ATL", "off_rank": 5, "def_rank": 27, "gap": 22}],
            "coverage": {"ATL": {"weakest": "Mike Hughes"}}, "injuries": [
                {"team": "ATL", "player": "A.J. Terrell", "position": "CB", "status": "OUT",
                 "opens": "C.J. Henderson steps in at LCB"}],
            "method": {"teams": 32, "opponent_adjusted": True}}
    reads = {"players": [{"player": "Christian Watson", "team": "GB", "pos": "WR", "read": "breakout",
                          "label": "Breakout spot", "pro": ["a", "b"], "con": []}],
             "microscope": [{"player": "Christian Watson", "market": "rec_yds", "side": "OVER",
                             "line": 55.5, "odds": -150, "prob": 0.66, "clears": True}]}
    return {"games": [{"home": "GB", "away": "ATL", "scan": scan}], "scan_reads": {"ATL@GB": reads}}


def test_ask_reads_the_scan_for_a_named_game_only():
    from engine import askbot as AB
    b = _scanned_board()
    g = b["games"][0]
    assert "matchup_scan" not in AB.game_facts(b, g), "the slate listing stays lean"
    ms = AB.game_facts(b, g, scan=True)["matchup_scan"]
    assert ms["unit_ranks"]["ATL"]["def"] == {"passing": 27}
    assert ms["mismatches"] == ["GB offense passing 5 vs ATL defense passing 27: edge GB"]
    assert ms["soft_spot_in_coverage"] == {"ATL": "Mike Hughes"}
    assert ms["player_reads"][0]["read"] == "breakout"
    assert ms["props_under_the_microscope"][0]["clears"] is True
    assert "moves none of our numbers" in AB.SYSTEM
    src = open(os.path.join(ROOT, "engine", "askbot.py"), encoding="utf-8").read()
    assert 'facts["games"] = [game_facts(boards[s], g, scan=True)' in src


def test_the_pick_page_carries_the_players_read():
    page = APP[APP.index("function renderPropPage("):]
    page = page[:page.index("\n}\n")]
    assert "${pickScanHTML(r)}" in page
    fn = APP[APP.index("function pickScanRead("):]
    fn = fn[:fn.index("\n}\n")]
    assert "(d.scan_reads || {})[`${g.away}@${g.home}`]" in fn


# ── the build and the page ─────────────────────────────────────────────────


def test_the_build_scans_every_game_and_never_fails_on_it():
    i = BUILD.index("_scan.attach_nfl(result, slate, args.season, args.week,")
    block = BUILD[BUILD.rindex("try:", 0, i):BUILD.index("matchup scan skipped", i)]
    assert "except Exception" in block
    assert "scan_depth_rows = rows" in BUILD


def test_the_game_page_draws_the_scan():
    j = APP.index("function renderGamePage(")
    page = APP[j:APP.index("\n}\n", j)]
    assert "${matchupScanHTML(g)}" in page and '["gp-sec-scan", "Matchup scan"]' in page
    fn = APP[APP.index("function matchupScanHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "(d.scan_reads || {})[`${away}@${home}`]" in fn
    assert "d.locked && d.locked.scan_reads" in fn, "a signed-out reader is told what is behind the paywall"
    assert "None of this moves our numbers" in fn and "2022–2025" in fn, "the page says what was measured"
    for sel in (".ms-unit {", ".ms-rank.good {", ".ms-read.breakout {", ".ms-why li.pro::marker {", ".ms-micro {"):
        assert sel in CSS, sel


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
