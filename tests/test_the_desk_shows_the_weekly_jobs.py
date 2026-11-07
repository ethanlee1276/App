"""The owner's desk shows the weekly jobs (engine/ownerdesk.weekly, the
Weekly jobs card in js/owner.js).

The deep refit, the Lab and board learning run beside the boards, each
with an hour, and what each did was read off the public heartbeat or the
box's logs: the Lab's page went five weeks unchanged and the refit had not
reached the NFL since August before anyone saw. What this holds:

  * each job's last run comes as engine.maintenance kept it (started, how
    long, running, cut off, the exit, the last line), the refit and the Lab
    first;
  * the deep refit's round says what it has done, what it still owes, and
    where a run's time ran out in a sport;
  * the Lab says the date each sport's numbers are from, and when a run
    last started each;
  * a box with no refit round or no Lab page leaves that part out, and the
    desk carries the card as its own section;
  * a file is read again only when it changes;
  * a sport's Lab numbers two turns late, or a sport the refit owes last
    fitted two weeks ago or never, go under Needs you and to the owner's
    phones (engine/owneralerts), once a day like the rest;
  * the page names each job in words, marks a running, cut-off or failed
    one, a late Lab sport in amber, and draws a job's last line as text;
    a job's time is the box's own Eastern clock as written, never moved
    through the browser's zone (and never formatted outside tzTime).

Run directly: `python3 tests/test_the_desk_shows_the_weekly_jobs.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ownerdesk as OD                                # noqa: E402

READ = lambda *p: ROOT.joinpath(*p).read_text(encoding="utf-8")   # noqa: E731

JOBS = {"engine.lab": {"started": "2026-11-05T00:46:39", "ended": "2026-11-05T02:25:29", "minutes": 99,
                       "exit": None, "cut_off": True, "running": False, "last": "lab: replaying nfl (1 of 6)…",
                       "pid": 4242},
        "engine.boardlearn": {"started": "2026-11-05T07:18:17", "ended": "2026-11-05T07:43:00", "minutes": 25,
                              "exit": 0, "cut_off": False, "running": False,
                              "last": "board learning: refitted nothing (no new graded picks)"},
        "engine.deepfit": {"started": "2026-11-05T10:49:16", "ended": None, "minutes": None, "exit": None,
                           "cut_off": False, "running": True, "last": ""},
        "engine.zzz": {"started": "2026-11-04T01:00:00", "ended": "2026-11-04T01:01:00", "minutes": 1,
                       "exit": 2, "cut_off": False, "running": False, "last": "<b>boom</b>"}}
DEEP = {"round": "2026-11-04", "left": ["nfl", "touchdowns"],
        "pieces": {"cfb": {"done": "2026-11-04"}, "nba": {"done": "2026-11-05"}, "mlb": {"done": "2026-10-29"},
                   "nfl": {"fitters_done": {"round": "2026-11-04", "done": ["recency dial"]},
                           "cut_off": {"fitter": "player memory", "after_s": 2700, "on": "2026-11-05",
                                       "round": "2026-11-04"}}}}
PAGE = {"generated_at": "2026-10-22T03:00:00",
        "sports": {"mlb": {"replayed_at": "2026-11-05T01:10:00"}, "nfl": {"props": {}}, "nba": {}}}
TRIED = {"mlb": "2026-11-05", "nfl": "2026-11-05", "cfb": "2026-11-04"}
NOW = time.mktime((2026, 11, 5, 12, 0, 0, 0, 0, -1))


def _files(deep=DEEP, page=PAGE, tried=TRIED):
    d = Path(tempfile.mkdtemp())
    paths = {}
    for name, obj in (("deep", deep), ("tried", tried)):
        if obj is not None:
            (d / f"{name}.json").write_text(json.dumps(obj), encoding="utf-8")
        paths[name] = d / f"{name}.json"
    web = d / "web" / "data"
    web.mkdir(parents=True)
    if page is not None:
        (d / "data" / "built").mkdir(parents=True)
        (d / "data" / "built" / "backtest.json").write_text(json.dumps(page), encoding="utf-8")
    paths["lab"] = web / "backtest.json"
    return paths


def _weekly(jobs=JOBS, **kw):
    p = _files(**kw)
    return OD.weekly(now=NOW, jobs=jobs, deep_path=p["deep"], lab_path=p["lab"], attempts_path=p["tried"])


def test_each_job_comes_as_the_box_kept_it_the_refit_and_the_lab_first():
    w = _weekly()
    assert [j["job"] for j in w["jobs"]] == ["deepfit", "lab", "boardlearn", "zzz"], w["jobs"]
    lab = w["jobs"][1]
    assert lab["cut_off"] is True and lab["minutes"] == 99 and lab["last"].startswith("lab: replaying nfl")
    assert "pid" not in lab, "only the fields a reader needs"
    assert w["jobs"][0]["running"] is True


def test_the_refit_says_what_it_did_what_it_owes_and_where_the_time_ran_out():
    deep = _weekly()["deep"]
    assert deep["round"] == "2026-11-04" and deep["left"] == ["nfl", "touchdowns"]
    assert deep["done"] == ["cfb", "nba"], "mlb's fit is from an earlier round"
    assert deep["part_way"] == ["nfl (recency dial done; player memory cut off after 45 min)"], deep["part_way"]
    assert deep["last_done"] == {"nfl": None}, "the sports still owed, each with its last finished fit"


def test_a_sport_the_round_file_never_finished_reads_its_fit_from_the_stores():
    """The desk on 5 November: five sports "none on record", the round file
    being new and the fits before it in the stores. The stores' own dates
    stand in: the older of the dial's newest and the memory's, the
    journal's memory fits left out, the round file's date where later."""
    d = Path(tempfile.mkdtemp())
    form, mem = d / "formfit.json", d / "playerfit.json"
    form.write_text(json.dumps({
        "nfl:receiving_yards": {"sport": "nfl", "fitted": "2026-08-27T03:10:00"},
        "nfl:receptions": {"sport": "nfl", "fitted": "2026-11-05T11:20:00"},   # a cut-off run's first market
        "mlb:hits": {"sport": "mlb", "fitted": "2026-10-01T02:00:00"}}), encoding="utf-8")
    mem.write_text(json.dumps({
        "nfl:receiving_yards": {"sport": "nfl", "fitted": "2026-08-27T03:40:00"},
        "nba:pts": {"sport": "nba", "fitted": "2026-10-20T05:00:00"},
        "wnba:pts": {"sport": "wnba", "basis": "journal-mae", "fitted": "2026-11-04T05:00:00"},
        "mlb:hits": {"sport": "mlb", "fitted": "2026-10-01T02:30:00"}}), encoding="utf-8")
    assert OD.fit_dates([form, mem]) == {"nfl": "2026-08-27", "mlb": "2026-10-01", "nba": "2026-10-20"}, \
        "the older of the two stores' newest; basketball has no dial; the journal's fits are not the refit's"
    deep = dict(DEEP, left=["nfl", "nba", "wnba", "mlb", "touchdowns"])
    deep["pieces"] = {"mlb": {"done": "2026-10-29"}, "nfl": DEEP["pieces"]["nfl"]}
    p = _files(deep=deep)
    # The WNBA and MLB stand in here for any sport owed: on 5 November both
    # are at rest, which tests/test_a_league_at_rest_sits_out_the_heavy_nights.py
    # holds; this one holds the stores' dates, so the season rule is off.
    from engine import deepfit as D
    keep = D.resting_pieces
    D.resting_pieces = lambda pieces, today: []
    try:
        w = OD.weekly(now=NOW, jobs=JOBS, deep_path=p["deep"], lab_path=p["lab"], attempts_path=p["tried"],
                      fit_paths=[form, mem])
    finally:
        D.resting_pieces = keep
    assert w["deep"]["last_done"] == {"nfl": "2026-08-27", "nba": "2026-10-20", "wnba": None,
                                      "mlb": "2026-10-29"}, w["deep"]["last_done"]
    got = _alerts(w)
    assert got and got[0]["title"] == "The deep refit has no finished WNBA fit on record", got
    assert "NFL (70 days)" in got[0]["body"] and "NBA (16 days)" in got[0]["body"], got[0]["body"]
    assert "none on record" not in got[0]["body"].replace("WNBA (none on record)", ""), got[0]["body"]
    assert OD.fit_dates([d / "missing.json"]) == {}


def _alerts(weekly):
    from engine import owneralerts as OA
    return [p for p in OA.problems({"weekly": weekly}, now=NOW) if p["key"] in ("lab", "deepfit")]


def test_a_lab_two_turns_late_or_a_sport_the_refit_left_behind_needs_the_owner():
    lab = {"sports": [{"sport": "nfl", "replayed": "2026-09-29"}, {"sport": "mlb", "replayed": "2026-11-04"},
                      {"sport": "cfb", "replayed": "2026-10-21"}]}
    got = _alerts({"lab": lab})
    assert [p["key"] for p in got] == ["lab"], got
    assert got[0]["title"] == "The Lab's NFL numbers are 37 days old", got[0]
    assert "NFL (37 days), college football (15 days)" in got[0]["body"] and "MLB" not in got[0]["body"]
    assert _alerts({"lab": {"sports": [{"sport": "nfl", "replayed": "2026-10-22"}]}}) == [], "under two turns"
    deep = {"last_done": {"nfl": "2026-08-27", "cfb": "2026-11-04", "nba": None},
            "part_way": ["nfl (recency dial done; player memory cut off after 45 min)"]}
    got = _alerts({"deep": deep})
    assert [p["key"] for p in got] == ["deepfit"], got
    assert got[0]["title"] == "The deep refit has no finished NBA fit on record", got[0]
    assert "NBA (none on record), NFL (70 days)" in got[0]["body"] and "Part-way: nfl (recency dial" in got[0]["body"]
    assert "college" not in got[0]["body"], "fitted yesterday"
    got = _alerts({"deep": {"last_done": {"nfl": "2026-08-27"}}})
    assert got[0]["title"] == "The deep refit has not fitted the NFL in 70 days"
    assert _alerts({"deep": {"last_done": {"nfl": "2026-11-01"}}}) == []
    assert _alerts({}) == [] and _alerts({"error": "x"}) == []


def test_the_lab_says_the_date_each_sports_numbers_are_from():
    lab = _weekly()["lab"]
    got = {x["sport"]: (x["replayed"], x["tried"]) for x in lab["sports"]}
    assert got["mlb"] == ("2026-11-05", "2026-11-05")
    assert got["nfl"] == ("2026-10-22", "2026-11-05"), "a sport with no date of its own has the page's"
    assert got["cfb"] == ("2026-10-22", "2026-11-04")
    assert [x["sport"] for x in lab["sports"]][:2] == ["mlb", "nfl"] and lab["every_days"] == 7


def test_a_box_without_a_round_or_a_lab_page_leaves_that_part_out():
    w = _weekly(jobs={}, deep=None, page=None, tried=None)
    assert w == {"jobs": [], "deep": None, "lab": None}, w
    src = READ("engine", "ownerdesk.py")
    assert 'out["weekly"] = _section(weekly, t)' in src, "health carries it through its per-section guard"
    assert '"weekly": h.get("weekly") if isinstance(h, dict) else None' in src, "the desk reads it from there"


def test_a_file_is_read_again_only_when_it_changes():
    d = Path(tempfile.mkdtemp())
    f = d / "x.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    assert OD._json_cached(f) == {"a": 1}
    real = Path.read_text
    calls = []
    Path.read_text = lambda self, *a, **k: calls.append(self) or real(self, *a, **k)
    try:
        OD._json_cached(f)
    finally:
        Path.read_text = real
    assert not calls, "an unchanged file is not read again"
    f.write_text('{"a": 22}', encoding="utf-8")
    os.utime(f, (time.time() + 5, time.time() + 5))
    assert OD._json_cached(f) == {"a": 22}
    assert OD._json_cached(d / "missing.json") == {}


def _draw(sample, script):
    node = shutil.which("node")
    if not node:
        return None
    stubs = """
      const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
      const escapeAttr = escapeHtml;
      const toneOf = (v) => (v > 0 ? "pos" : v < 0 ? "neg" : "");
      const tzTime = () => "3:00 PM";
      const document = { addEventListener() {}, querySelectorAll() { return []; } };
      const navigator = {};
    """
    prog = stubs + READ("web", "js", "owner.js") + f"\nconst D = {json.dumps(sample)};\n" + script
    fd, path = tempfile.mkstemp(suffix=".js")
    with os.fdopen(fd, "w") as fh:
        fh.write(prog)
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return out.stdout


def test_the_page_names_each_job_and_marks_what_needs_a_look():
    w = _weekly()
    html = _draw({"w": w}, "process.stdout.write(odWeeklyHTML(D.w, '2026-11-05'));")
    if html is None:
        return
    for want in ("Weekly jobs", "The deep refit", "The Lab’s replay", "Board learning",
                 "running since 5 Nov 10:49am ET", "The Lab’s replay · 5 Nov 12:46am ET",
                 "cut off after 99 min", "failed (exit 2)", "finished in 25 min",
                 "The deep refit’s round of 2026-11-04", "2 still owed", "Still owed", "NFL, touchdowns",
                 "Done this round", "College, NBA", "nfl (recency dial done; player memory cut off after 45 min)",
                 "lab: replaying nfl (1 of 6)…"):
        assert want in html, want
    assert "<b>boom</b>" not in html and "&lt;b&gt;boom&lt;/b&gt;" in html, "a last line is text"
    assert '<span class="od-pill">MLB' in html, "replayed today"
    assert '<span class="od-pill warn">NFL' in html, "two weeks old is late"


def test_the_card_is_on_the_desk_and_an_empty_or_failed_one_says_so():
    desk = {"at": time.time(), "day": "2026-11-05", "now": {"members": 1, "visitors": 0, "pages": 1}, "prefs": {},
            "switches": [], "notice": {}, "community": {}, "reports": {"open": [], "open_n": 0, "hidden": [],
                                                                       "hidden_n": 0},
            "weekly": _weekly()}
    out = _draw(desk, "process.stdout.write(odHTML(D) + '\\n=====\\n' + odWeeklyHTML({jobs: [], deep: null, lab: null})"
                " + '\\n=====\\n' + odWeeklyHTML({error: 'OSError: nope'}));")
    if out is None:
        return
    full, empty, failed = out.split("\n=====\n")
    assert "Weekly jobs" in full and "The deep refit’s round" in full
    assert "No weekly job has run on this box yet" in empty
    assert "Could not read this part: OSError: nope" in failed


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
