"""What changed on a team, and what it does to the season split.

Ethan, 2026-09-27, on the Jets in the matchup scan: "any team that has a
new QB starting this season or new defense coach or offense coach or new
coach, I feel like the 2026 offense and defense should favor more for
those teams." Set by hand that day (75/25, then 65/35 for new staff,
60/40 when the head coach calls the plays), then: "Idk if anything should
be at 75/25. Write the check and do the check then change anything that's
hurting."

The check (scanblendfit.py, 2022-2025) found that only a new starting QB
makes a season's own games predict more; a new head coach changed
nothing, and nothing earned 75%. So engine/teamchange still names every
change — new QB and head coach from the nflverse schedule, coordinators
and the head coach's play-calling from the hand-kept staff file — but
only an offence under a new starting QB takes this season faster
(gamescan.unit_share, QB_PRIOR_GAMES); every other side takes it at the
measured league rate.
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


def test_the_head_coachs_play_calling_is_named_not_weighted():
    """The file says who calls the plays over a new coordinator, and the
    card says so. It moves nothing: measured, new staff did not."""
    staff = {"NYJ": {"dc": "Brian Duker", "oc": "Frank Reich", "hc_calls": ["def", "off"]},
             "KC": {"oc": "Eric Bieniemy", "hc_calls": ["off"]}}
    ch = T.detect(_schedule(), 2026, before_week=4, staff=staff)
    assert ch["NYJ"]["hc_calls"] == ["def"], "the offence's change is its QB, not only a coordinator"
    assert ch["NYJ"]["def"] == ["new defensive coordinator (Brian Duker); the head coach calls the plays"]
    assert ch["KC"]["hc_calls"] == ["off"] and "qb" not in ch["KC"]


def test_only_a_new_starting_qb_moves_the_split():
    ch = T.detect(_schedule(), 2026, before_week=4,
                  staff={"NYJ": {"dc": "Brian Duker", "oc": "Frank Reich"}})
    assert ch["NYJ"]["qb"] == ["off"] and "qb" not in ch["TEN"], "a new head coach is not a new QB"
    assert not hasattr(G, "CHANGED_SHARE") and not hasattr(G, "HC_CALLS_SHARE"), "the hand tiers are gone"
    last = _units(2025, 17, {"NYJ": 0.15, "DET": -0.05})
    now = _units(2026, 3, {"NYJ": -0.10, "DET": 0.05})
    r = G.ratings_from_rows(now, last, {"NYJ": ch["NYJ"], "DET": ch.get("TEN")})
    assert r["NYJ"]["blend_off"] == round(3 / (3 + G.QB_PRIOR_GAMES), 2)
    assert r["NYJ"]["blend_def"] == r["NYJ"]["blend"] == round(3 / (3 + G.UNIT_PRIOR_GAMES), 2)
    assert r["DET"]["blend_off"] == r["DET"]["blend_def"] == r["DET"]["blend"], "new staff, same split"
    assert set(r["NYJ"]["changed"]) == {"off", "def"}, "every change is still named for the card"
    rz = open(os.path.join(ROOT, "engine", "redzone.py"), encoding="utf-8").read()
    assert 'qb = side in (((changes or {}).get(team) or {}).get("qb") or [])' in rz


def _units(season, weeks, epa_allowed):
    out = []
    for w in range(1, weeks + 1):
        for team, opp in (("NYJ", "DET"), ("DET", "NYJ")):
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "def", "opp": opp, "plays": 60, "epa": epa_allowed[team] * 60})
            out.append({"sport": "nfl", "season": season, "period": str(w), "team": team,
                        "side": "off", "opp": opp, "plays": 60, "epa": 0.0})
    return out


def test_what_the_check_found_is_what_the_split_does():
    """scanblendfit.py on 2022-2025: this season's best share grows with
    its games (0.26 after 2-3, 0.41 after 4-5, 0.59 after 6-8) and faster
    for a new QB's offence (0.45 after 2-3). games / (games + k) with
    k = 6 and 3.5 fits both."""
    assert (G.UNIT_PRIOR_GAMES, G.QB_PRIOR_GAMES) == (6.0, 3.5)
    assert abs(G.unit_share(2.5) - 0.29) < 0.01 and abs(G.unit_share(7) - 0.54) < 0.01
    assert abs(G.unit_share(2.5, new_qb=True) - 0.42) < 0.01
    assert G.unit_share(0) == 0.0 and G.unit_share(5, has_prior=False) == 1.0
    fit = open(os.path.join(ROOT, "scanblendfit.py"), encoding="utf-8").read()
    assert "def best_share(" in fit and "def boot(" in fit and "def hand_share(" in fit
    # The check's own arithmetic, on points built to a known answer: a
    # target that is exactly 30% this season, 70% last, fits at 0.30; a
    # ramp built at k=4 fits at k=4.
    import random
    import scanblendfit as F
    rnd = random.Random(3)
    pts = []
    for i in range(200):
        a, b = rnd.uniform(-1, 1), rnd.uniform(-1, 1)
        pts.append(("same", 3, f"c{i % 40}", a, b, 0.3 * a + 0.7 * b, 1.0))
    assert abs(F.best_share(pts) - 0.30) < 1e-9 and F.boot(pts, reps=20) < 1e-6
    ramp = []
    for i in range(300):
        n, a, b = rnd.randint(2, 8), rnd.uniform(-1, 1), rnd.uniform(-1, 1)
        w = n / (n + 4.0)
        ramp.append(("same", n, f"c{i}", a, b, w * a + (1 - w) * b, 1.0))
    assert F.best_ramp(ramp)[0] == 4.0


def test_the_build_reads_the_changes_and_the_red_zone_uses_them_too():
    body = SRC[SRC.index("def attach_nfl("):]
    body = body[:body.index("\ndef ")]
    assert "changes = nfl_changes(season, before_week=week)" in body
    assert "unit_ratings(conn, season, before_week=week, changes=changes)" in body
    assert "_rz_rates(conn, season, before_week=week, changes=changes)" in body
    rz = open(os.path.join(ROOT, "engine", "redzone.py"), encoding="utf-8").read()
    assert "unit_share(g, True, new_qb=new_qb)" in rz


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
