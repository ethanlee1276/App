"""A side of the ball that is not last season's leans on this season.

Ethan, 2026-09-27, on the Jets in the matchup scan: "any team that has a
new QB starting this season or new defense coach or offense coach or new
coach, I feel like the 2026 offense and defense should favor more for
those teams. Like maybe 75/25 or 70/30."

A new head coach moves both sides, a new starting QB or offensive
coordinator the offence, a new defensive coordinator the defence — read
from the nflverse schedule (coaches and starting QBs) and the hand-kept
coordinator file (engine/teamchange). A changed side blends 75/25 from
two games on by what changed — 75/25 for a new starting QB, 65/35 for
new staff with the same players, 60/40 for a coordinator whose plays the
head coach calls (Ethan, the same day: "75/25 seems like a lot especially
if the players r not different") — and an unchanged side keeps 55/45.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402
from engine import teamchange as T                               # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
SRC = open(os.path.join(ROOT, "engine", "gamescan.py"), encoding="utf-8").read()


def _g(season, week, away, home, ac, hc, aqb, hqb, played=True, aid="", hid=""):
    return {"season": str(season), "week": str(week), "gameday": f"{season}-09-{week:02d}",
            "away_team": away, "home_team": home, "away_coach": ac, "home_coach": hc,
            "away_qb_name": aqb, "home_qb_name": hqb, "away_qb_id": aid, "home_qb_id": hid,
            "home_score": "20" if played else "", "away_score": "17" if played else ""}


def _schedule():
    rows = []
    # 2025: NYJ coached by Glenn, Fields at QB; TEN by Callahan, Ward; ATL
    # Morris, Penix (id P1); KC Reid, Mahomes.
    for w in range(1, 18):
        rows.append(_g(2025, w, "NYJ", "TEN", "Aaron Glenn", "Brian Callahan",
                       "Justin Fields", "Cam Ward"))
        rows.append(_g(2025, w, "ATL", "KC", "Raheem Morris", "Andy Reid",
                       "Michael Penix", "Patrick Mahomes", aid="P1"))
    # 2026, three weeks played: NYJ same coach, Geno Smith at QB; TEN a new
    # coach; ATL's QB spelled differently, same id; KC's starter hurt in
    # week 3, so the backup has one start to his two.
    kc = ["Patrick Mahomes", "Patrick Mahomes", "Carson Wentz"]
    for w in range(1, 4):
        rows.append(_g(2026, w, "NYJ", "TEN", "Aaron Glenn", "Robert Saleh",
                       "Geno Smith", "Cam Ward"))
        rows.append(_g(2026, w, "ATL", "KC", "Raheem Morris", "Andy Reid",
                       "Michael Penix Jr.", kc[w - 1], aid="P1"))
    rows.append(_g(2026, 4, "NYJ", "TEN", "Aaron Glenn", "Robert Saleh",
                   "Geno Smith", "Cam Ward", played=False))
    return rows


def test_changes_are_read_from_the_schedule_and_moved_to_the_right_side():
    ch = T.detect(_schedule(), 2026, before_week=4, staff={})
    assert ch["TEN"]["off"] == ["new head coach (Robert Saleh)"]
    assert ch["TEN"]["def"] == ["new head coach (Robert Saleh)"], "a head coach moves both sides"
    assert ch["NYJ"]["off"] == ["new starting QB (Geno Smith)"] and ch["NYJ"]["def"] == []
    assert "ATL" not in ch, "one man under two spellings is not a new QB (the schedule's id)"
    assert "KC" not in ch, "a backup's start while the starter is hurt is not a new QB"


def test_a_tie_in_starts_keeps_last_seasons_quarterback():
    rows = [r for r in _schedule() if not (r["season"] == "2026" and r["week"] == "1")]
    # KC 2026: Mahomes week 2, Wentz week 3 — one each.
    assert "KC" not in T.detect(rows, 2026, before_week=4, staff={})


def test_before_a_game_is_played_the_first_game_names_the_staff():
    rows = [r for r in _schedule() if r["season"] == "2025"]
    rows.append(_g(2026, 1, "NYJ", "TEN", "Aaron Glenn", "Robert Saleh", "Geno Smith",
                   "Cam Ward", played=False))
    ch = T.detect(rows, 2026, before_week=1, staff={})
    assert ch["TEN"]["def"] and ch["NYJ"]["off"] == ["new starting QB (Geno Smith)"]


def test_coordinators_come_from_the_staff_file_only():
    ch = T.detect(_schedule(), 2026, before_week=4, staff={"NYJ": {"dc": "Some Name"}})
    assert ch["NYJ"]["def"] == ["new defensive coordinator (Some Name)"]
    assert ch["NYJ"]["off"] == ["new starting QB (Geno Smith)"]
    blob = json.load(open(os.path.join(ROOT, "data", "nfl_staff_changes.json")))
    assert "2026" in blob and "_note" in blob
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump({"2026": {"nyj": {"dc": " A Name ", "oc": ""}, "LAR": {"oc": "B"}}}, fh)
    try:
        assert T.load_staff(2026, fh.name) == {"NYJ": {"dc": "A Name"}, "LA": {"oc": "B"}}
        assert T.load_staff(2025, fh.name) == {}
    finally:
        os.unlink(fh.name)
    assert T.load_staff(2026, "/nonexistent.json") == {}
    assert T.detect(None, 2026) == {} and T.detect([{"season": "x"}], 2026) == {}



def test_the_file_backs_up_a_head_coach_the_schedule_missed():
    """nflverse kept Jonathan Gannon on Arizona's 2026 rows after he was
    fired; the file's head coach counts, once, and never twice when the
    schedule already caught it."""
    rows = _schedule()
    ch = T.detect(rows, 2026, before_week=4, staff={"NYJ": {"hc": "Someone New"},
                                                    "TEN": {"hc": "Robert Saleh"}})
    assert ch["NYJ"]["def"] == ["new head coach (Someone New)"]
    assert ch["TEN"]["off"] == ["new head coach (Robert Saleh)"], "not listed twice"


def test_the_2026_staff_file_is_filled_and_sane():
    staff = T.load_staff(2026)
    assert sum(1 for v in staff.values() if v.get("oc")) == 21
    assert sum(1 for v in staff.values() if v.get("dc")) == 14
    assert sum(1 for v in staff.values() if v.get("hc")) == 10
    assert staff["NYJ"] == {"oc": "Frank Reich", "dc": "Brian Duker", "hc_calls": ["def"]}
    assert {t for t, v in staff.items() if v.get("hc_calls")} == {"NYJ", "KC", "CHI", "LA"}
    assert staff["ARI"]["hc"] == "Mike LaFleur" and "dc" not in staff["ARI"]
    assert "NE" not in staff, "Kuhr ran the 2025 defence already"
    nfl = {"ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN", "DET", "GB",
           "HOU", "IND", "JAX", "KC", "LA", "LAC", "LV", "MIA", "MIN", "NE", "NO", "NYG",
           "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"}
    assert set(staff) <= nfl, set(staff) - nfl
    blob = json.load(open(os.path.join(ROOT, "data", "nfl_staff_changes.json")))
    assert "_sources" in blob, "every name says where it came from"


def test_a_new_coordinator_under_a_play_calling_head_coach_is_60_40():
    """Ethan, 2026-09-27: "teams with new cordinators but head coach
    calling plays maybe we do 60/40". Only when the coordinator is the
    side's only change: a new QB on the same side still counts in full."""
    staff = {"NYJ": {"dc": "Brian Duker", "oc": "Frank Reich", "hc_calls": ["def", "off"]},
             "KC": {"oc": "Eric Bieniemy", "hc_calls": ["off"]}}
    ch = T.detect(_schedule(), 2026, before_week=4, staff=staff)
    assert ch["NYJ"]["hc_calls"] == ["def"], "the new QB keeps the offence in full"
    assert ch["NYJ"]["def"] == ["new defensive coordinator (Brian Duker); the head coach calls the plays"]
    assert ch["KC"]["hc_calls"] == ["off"]
    assert G.HC_CALLS_SHARE == 0.60
    assert G.season_share(3, changed=True, top=G.HC_CALLS_SHARE) == 0.60
    assert G.season_share(1, changed=True, top=G.HC_CALLS_SHARE) == 0.5
    last = _units(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _units(2026, 3, {"NYJ": -0.10, "DET": 0.05})
    r = G.ratings_from_rows(now, last, {"NYJ": {"off": [], "def": ["x"], "hc_calls": ["def"],
                                                "top": {"def": G.HC_CALLS_SHARE}}})
    assert r["NYJ"]["blend_def"] == 0.60
    assert abs(r["NYJ"]["def"]["overall"]["value"] - (0.60 * -0.10 + 0.40 * 0.15)) < 1e-6
    assert set(r["NYJ"]["changed"]) == {"def"}, "the markers are not sides"


def test_the_share_goes_by_what_changed_and_the_largest_wins():
    """New players count more than new staff; two changes on one side
    take the larger share, never a sum."""
    staff = {"NYJ": {"dc": "Brian Duker", "oc": "Frank Reich", "hc_calls": ["def"]},
             "KC": {"oc": "Eric Bieniemy", "hc_calls": ["off"]}}
    ch = T.detect(_schedule(), 2026, before_week=4, staff=staff)
    assert ch["NYJ"]["top"] == {"off": G.QB_CHANGE_SHARE, "def": G.HC_CALLS_SHARE}, \
        "new QB and new OC: the QB's 75, not more"
    assert ch["TEN"]["top"] == {"off": G.CHANGED_SHARE, "def": G.CHANGED_SHARE}
    assert ch["KC"]["top"] == {"off": G.HC_CALLS_SHARE}
    assert (G.QB_CHANGE_SHARE, G.CHANGED_SHARE, G.HC_CALLS_SHARE) == (0.75, 0.65, 0.60)
    last = _units(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _units(2026, 3, {"NYJ": -0.10, "DET": 0.05})
    r = G.ratings_from_rows(now, last, {"NYJ": {"off": ["qb"], "def": ["dc"],
                                                "top": {"off": 0.75, "def": 0.60}}})
    assert (r["NYJ"]["blend_off"], r["NYJ"]["blend_def"]) == (0.75, 0.60)
    rz = open(os.path.join(ROOT, "engine", "redzone.py"), encoding="utf-8").read()
    assert 'top = (ch.get("top") or {}).get(side)' in rz

def _units(season, weeks, epa_allowed):
    out = []
    for w in range(1, weeks + 1):
        for team, opp in (("NYJ", "DET"), ("DET", "NYJ")):
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "def", "opp": opp, "plays": 60, "epa": epa_allowed[team] * 60})
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "off", "opp": opp, "plays": 60, "epa": 0.0})
    return out


def test_the_jets_defence_the_way_ethan_described_it():
    """2025: the Jets' defence poor, Detroit's good. 2026: a modest turn
    the other way. At 55/45 Detroit still ranks first; with the Jets'
    defence under new staff it leans 65/35 and the Jets rank first."""
    last = _units(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _units(2026, 3, {"NYJ": -0.10, "DET": 0.05})
    same = G.ratings_from_rows(now, last)
    assert same["DET"]["def"]["overall"]["rank"] == 1
    moved = G.ratings_from_rows(now, last, {"NYJ": {"off": [], "def": ["new defensive coordinator"]}})
    assert moved["NYJ"]["def"]["overall"]["rank"] == 1
    assert abs(moved["NYJ"]["def"]["overall"]["value"] - (0.65 * -0.10 + 0.35 * 0.15)) < 1e-6
    assert moved["NYJ"]["blend_def"] == G.CHANGED_SHARE == 0.65
    assert moved["NYJ"]["blend_off"] == moved["NYJ"]["blend"] == 0.55, "the other side is untouched"
    assert moved["NYJ"]["changed"] == {"def": ["new defensive coordinator"]}
    assert "changed" not in moved["DET"]


def test_the_ramp_before_two_games():
    assert G.season_share(1, changed=True) == 0.5 and G.season_share(1) == 0.2
    assert G.season_share(2, changed=True) == G.season_share(12, changed=True) == 0.65
    assert G.season_share(3, changed=True, top=G.QB_CHANGE_SHARE) == 0.75
    assert G.season_share(0, changed=True) == 0.0
    assert G.season_share(3, has_prior=False, changed=True) == 1.0


def test_the_build_reads_the_changes_and_the_red_zone_uses_them_too():
    body = SRC[SRC.index("def attach_nfl("):]
    body = body[:body.index("\ndef ")]
    assert "changes = nfl_changes(season, before_week=week)" in body
    assert "unit_ratings(conn, season, before_week=week, changes=changes)" in body
    assert "_rz_rates(conn, season, before_week=week, changes=changes)" in body
    rz = open(os.path.join(ROOT, "engine", "redzone.py"), encoding="utf-8").read()
    assert "season_share(g, True, changed=changed, top=top)" in rz


def test_the_card_names_the_side_and_the_reason():
    fn = APP[APP.index("function scanTapeHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert "${tapeChanges(scan, away, home)}" in fn
    ch = APP[APP.index("function tapeChanges("):]
    ch = ch[:ch.index("\n}\n")]
    assert "u.changed" in ch and "blend_${side}" in ch and "escapeHtml(l)" in ch


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
