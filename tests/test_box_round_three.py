"""Box round three — what the 2026-10-17 paste found, each fixed and held.

Ethan, 2026-10-17: "go through everything and fix anything that needs
fixing and make sure we are applying everything."

What these hold: an NFL loss finds its final by his team and week (the
logs name a game "BUF-005", the games table "MIA@BUF"), and only when his
team played once that week; the held-out seasons are the newest two of
three or more and the newest of two, in every measurement that holds one
out; "proxy" (our own placeholder line) is never a book's close;
Wikipedia's 429 is waited out once, then the run stops, keeps what it
fetched, and the builds skip for the cooldown; the snap share reaches the
touchdown card as the detected role once that share's verdict holds, and
stays the plain average until then; the readings spend at most their
budget and say what they skipped and what each took; the loss autopsy is
rebuilt by the daily chores, not inside a board build; and the NFL build
times the readings and the Most Likely board as stages of their own. No
test touches the network.

Run directly: `python3 tests/test_box_round_three.py`
"""
import io
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import attention as A                                # noqa: E402
from engine import bookmenu as BM                                # noqa: E402
from engine import causes, db, ledger                            # noqa: E402
from engine import ideagate as G                                 # noqa: E402
from engine import ideas as ID                                   # noqa: E402
from engine import nflusage as NU                                # noqa: E402
from engine import rolechange as RC                              # noqa: E402


class _Models:
    """A private models folder for one test, the gate's cache emptied."""

    def __enter__(self):
        self.dir = tempfile.mkdtemp()
        self.old = os.environ.get("QB_MODELS_DIR")
        os.environ["QB_MODELS_DIR"] = self.dir
        G._cache.clear()
        return self

    def put(self, name, data):
        with open(os.path.join(self.dir, name), "w") as fh:
            json.dump(data, fh)
        G._cache.clear()

    def __exit__(self, *exc):
        if self.old is None:
            os.environ.pop("QB_MODELS_DIR", None)
        else:
            os.environ["QB_MODELS_DIR"] = self.old
        shutil.rmtree(self.dir)
        G._cache.clear()


# ---- the NFL final, by team and week ------------------------------------------------------

def _nfl_loss(games):
    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    hconn = db.connect(":memory:")
    lconn.execute("INSERT INTO bets (sport,date,player,market,side,line,odds,grade,stake_units,"
                  "stake_dollars,status,category) VALUES ('nfl','2026-W05','James Cook','rush_yds',"
                  "'OVER',70.5,-110,'A',1.0,10.0,'lost','main')")
    lconn.commit()
    db.upsert_player_logs(hconn, [{"sport": "nfl", "season": 2026, "period": "005", "game_id": "BUF-005",
                                   "player": "James Cook", "team": "BUF", "opponent": "MIA", "position": "RB",
                                   "home": 1, "market": "rush_yds", "value": 41.0}])
    db.upsert_games(hconn, games)
    return lconn, hconn


def _final(season, gid, home, away, hs, aw):
    return {"sport": "nfl", "season": season, "period": "005", "game_id": gid, "home": home,
            "away": away, "home_score": hs, "away_score": aw}


def test_an_nfl_loss_finds_its_final_by_team_and_week():
    lconn, hconn = _nfl_loss([_final(2026, "MIA@BUF", "BUF", "MIA", 41.0, 10.0),
                              _final(2025, "BUF@MIA", "MIA", "BUF", 3.0, 3.0)])
    b = lconn.execute("SELECT * FROM bets").fetchone()
    assert causes._final_margin(hconn, b) == 31.0, "week 5 of 2026, not week 5 of 2025"
    causes.backfill(lconn, hconn)
    assert lconn.execute("SELECT loss_cause FROM bets").fetchone()[0] == "blowout (31-pt final)"


def test_two_games_for_his_team_in_one_week_is_no_evidence():
    lconn, hconn = _nfl_loss([_final(2026, "MIA@BUF", "BUF", "MIA", 41.0, 10.0),
                              _final(2026, "BUF@NE", "NE", "BUF", 40.0, 0.0)])
    b = lconn.execute("SELECT * FROM bets").fetchone()
    assert causes._final_margin(hconn, b) is None


# ---- the held-out seasons -----------------------------------------------------------------

def test_the_held_out_seasons_are_the_newest_once_there_is_an_older_to_fit():
    assert BM.held_seasons([2025, 2026, 2026]) == {2026}, "the props closes begin in 2025"
    assert BM.held_seasons([2023, 2024, 2025, 2026]) == {2025, 2026}
    assert BM.held_seasons([2026]) == set() and BM.held_seasons([]) == set()
    for mod in ("bookmenu", "bookrecipe", "attention", "practice"):
        src = (ROOT / "engine" / f"{mod}.py").read_text()
        assert "held_seasons(" in src, f"{mod} holds out by the shared rule"


def test_proxy_is_never_a_books_close():
    conn = db.connect(":memory:")
    rows = [("nfl", "2026-10-11T15:00:00Z", "e1", "BUF", "MIA", "James Cook", "rush_yds", book, line, -110, -110, None)
            for book, line in (("draftkings", 70.5), ("proxy", 64.0), ("Proxy ", 64.0))]
    conn.executemany("INSERT INTO odds_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    got = BM.closes_compact(conn, "nfl", "rush_yds")
    assert got == {("James Cook", "2026-10-11"): {"draftkings": (70.5, -110, -110)}}, got


# ---- Wikipedia's 429 ----------------------------------------------------------------------

class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _urlopen(answers):
    def fake(req, timeout=20):
        a = answers.pop(0)
        if isinstance(a, int):
            raise urllib.error.HTTPError(req.full_url, a, "Too Many Requests", {"Retry-After": "7"}, None)
        return _Resp(json.dumps(a).encode())
    return fake


def test_a_429_is_waited_out_once_then_the_run_stops():
    old = urllib.request.urlopen
    slept = []
    try:
        urllib.request.urlopen = _urlopen([429, {"ok": 1}])
        assert A._get_json("https://example.org/a", sleep=slept.append) == {"ok": 1}
        assert slept == [7.0], "the Retry-After it asked for"
        urllib.request.urlopen = _urlopen([429, 429])
        try:
            A._get_json("https://example.org/b", sleep=slept.append)
            raise AssertionError("a second 429 must stop the run")
        except A.RateLimited:
            pass
    finally:
        urllib.request.urlopen = old
    assert "QellysBook/" in A.USER_AGENT and "https://" in A.USER_AGENT, "Wikimedia asks for a contact"


def test_after_a_429_the_builds_skip_for_the_cooldown():
    calls = []

    def limited(url):
        calls.append(url)
        raise A.RateLimited(url)

    with _Models() as m:
        conn = db.connect(":memory:")
        assert not A.cooling_down()
        assert A.keep_current(conn, "nfl", ["Josh Allen", "James Cook"], get=limited) == 0
        assert len(calls) == 1, "the first 429 ends the build's fetching"
        assert A.cooling_down() and os.path.exists(os.path.join(m.dir, "attention_cooldown.json"))
        assert A.keep_current(conn, "nfl", ["Josh Allen"], get=limited) == 0
        assert len(calls) == 1, "inside the hour no build asks again"
        import time
        assert not A.cooling_down(now=time.time() + A.COOLDOWN_SECONDS + 1)


def test_a_backfill_stops_on_a_429_and_says_so():
    def limited(url):
        raise A.RateLimited(url)

    with _Models():
        conn = db.connect(":memory:")
        try:
            A.backfill(conn, "nfl", ["Josh Allen"], "2025-09-01", "2026-01-31", get=limited)
            raise AssertionError("the backfill must hand the 429 up")
        except A.RateLimited:
            pass
        assert A.cooling_down()
    src = (ROOT / "engine" / "attention.py").read_text()
    assert "run this again in an hour" in src


# ---- the snap share, as the detected role ---------------------------------------------------

def _snap_conn(shares):
    conn = db.connect(":memory:")
    db.upsert_player_logs(conn, [{"sport": "nfl", "season": 2026, "period": f"{w:03d}", "game_id": f"BUF-{w:03d}",
                                  "player": "James Cook", "team": "BUF", "opponent": "MIA", "position": "RB",
                                  "home": 1, "market": "snap_pct", "value": v}
                                 for w, v in enumerate(shares, start=1)])
    return conn


def test_the_snap_share_follows_the_detected_role_once_proven():
    from engine.fantasy import _short_key
    cook = _short_key("James Cook", "BUF")
    shares = [0.7] * 6 + [0.3] * 2
    with _Models() as m:
        flat = NU.snap_shares(_snap_conn(shares), season=2026)[cook]
        assert flat == round(sum(shares[-NU.SNAP_WEEKS:]) / NU.SNAP_WEEKS, 3), "the plain average until it holds"
        m.put("rolechange.json", {"shares": {"car": {"settings": RC.DEFAULT, "verdict": {"holds": True}}}})
        assert NU.snap_shares(_snap_conn(shares), season=2026)[cook] == flat, "a carries verdict is not a snap one"
        m.put("rolechange.json", {"shares": {"snap": {"settings": RC.DEFAULT, "verdict": {"holds": True}}}})
        fc = G.role_forecast("snap_pct", shares)
        moved = NU.snap_shares(_snap_conn(shares), season=2026)[cook]
        assert fc is not None and moved == round(fc, 3) and moved < flat, (moved, flat)
        assert G.role_ratio("snap_pct", shares) == 1.0, "a snap share is not a volume"
    where = {g[0]: g[2] for g in G.GATES}
    assert "snap share" in where["role"], "the gate report names where the role lands"


# ---- the readings' budget -------------------------------------------------------------------

def test_the_readings_spend_at_most_their_budget_and_say_what_they_skipped():
    now = {"t": 0.0}

    def fns(name):
        def fn(props, games, board, sport):
            now["t"] += 35.0
            return {"n": name}
        return (fn, None, None, None)

    old = ID._section_fns
    ID._section_fns = fns
    try:
        out = ID.build("nfl", budget=60.0, clock=lambda: now["t"])
    finally:
        ID._section_fns = old
    names = list(ID.SECTIONS)
    assert list(out["sections"]) == names[:2], "0→35s, 35→70s, then the budget is spent"
    assert out["timings"] == {names[0]: 35.0, names[1]: 35.0}
    assert all("budget was spent" in out["errors"][n] for n in names[2:])
    assert ID.BUDGET_SECONDS <= 90, "the readings are the part of a build that can wait"


# ---- what runs where ----------------------------------------------------------------------

def test_the_loss_autopsy_is_rebuilt_by_the_chores_not_a_build():
    from engine import autopsy
    assert not hasattr(autopsy, "journal"), "no build rebuilds the autopsy"
    src = (ROOT / "engine" / "maintenance.py").read_text()
    chores = src[src.index("def _run_chores"):]
    assert "_ap.refresh()" in chores


def test_the_nfl_build_times_the_readings_and_the_board():
    src = (ROOT / "nfl_build.py").read_text()
    marks = [src.index(f'_mem("{st}", args.memtrace)') for st in
             ("run_slate", "ideas readings", "most likely board", "pipeline", "journal")]
    assert marks == sorted(marks), "in the order the build runs them"


def test_each_stage_says_its_seconds_as_it_finishes():
    """The loop kills a build at 600 seconds, before any table at the end
    can print: every college build of 2026-10-17 died with nothing in its
    log to say where the time went."""
    from engine import stageclock as SC
    t = {"now": 100.0}
    lines = []
    SC.start(clock=lambda: t["now"])
    t["now"] = 130.0
    assert SC.mark("odds", out=lines.append, clock=lambda: t["now"]) == 30.0
    t["now"] = 650.0
    SC.mark("prop pricing", out=lines.append, clock=lambda: t["now"])
    assert lines == ["  ⏱ odds: 30s (at 30s of 600)", "  ⏱ prop pricing: 520s (at 550s of 600)"]
    cfb = (ROOT / "cfb_build.py").read_text()
    assert cfb.index("_clock.start()") < cfb.index('_clock.mark("history + team ratings")')
    stages = [cfb.index(f'_clock.mark("{st}")') for st in
              ("history + team ratings", "game bets", "player slate + quotes", "ideas readings",
               "long shots + Most Likely board", "stale lines + journal + settle")]
    assert stages == sorted(stages), "in the order the college build runs them"
    nfl = (ROOT / "nfl_build.py").read_text()
    body = nfl[nfl.index("def _mem("):nfl.index("def _mem_report")]
    assert body.index("_clock.mark(stage)") < body.index("if not on:"), "with or without --memtrace"



def test_the_record_check_compares_the_public_record_with_the_public_record():
    """The page's headline counts bets since RECORD_EPOCH; compared with the
    all-time count, the bets before it read as "the export is behind" (241,
    every run of 2026-10-17)."""
    src = (ROOT / "doctor.py").read_text()
    block = src[src.index("def check_record_page("):src.index("def check_record_page(") + 3200]
    assert "since=ledger.RECORD_EPOCH" in block and '"all_time"' in block
    ev = src[src.index("def check_premature_evidence("):src.index("def check_parlay_agreement(")]
    assert "_neighbour_game_evidence" in ev, "the settler's next-day fallback for a late college final"


def test_the_refit_says_each_fitter_as_it_runs():
    """Step AI printed nothing for 25 minutes and was stopped (2026-10-17):
    the lines came back only when all three fitters were done."""
    import subprocess
    from engine import deepfit as D
    said, real = [], D.subprocess.run
    D.subprocess.run = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    try:
        lines = D.refit_sport("nba", say=said.append)
    finally:
        D.subprocess.run = real
    starts = [x for x in said if "running" in x]
    dones = [x for x in said if "done in" in x]
    assert len(starts) == len(dones) == len(D.REFIT_ORDER), said
    assert said.index(starts[0]) < said.index(dones[0]) < said.index(starts[1]), "each as it happens"
    assert len(lines) == len(D.REFIT_ORDER), "the summary lines are unchanged"
    src = (ROOT / "engine" / "deepfit.py").read_text()
    assert "refit_sport(sys.argv[1].lower(), say=" in src, "python3 -m engine.deepfit nba speaks as it goes"


def test_the_seal_check_counts_rows_a_board_exposes_not_empty_shells():
    """An empty scan (five empty lists) read as five paid rows."""
    from engine import gate
    assert gate._rows({"stale": [], "arbs": [], "middles": []}) == 0
    assert gate._rows({"stale": [{"player": "x"}], "arbs": [1, 2]}) == 3
    assert gate._count_paid({"market_scan": {"stale": [], "arbs": []}, "games": [1]}, gate.PAID_KEYS) == 0
    assert gate._count_paid({"most_likely": [{"player": "x"}]}, gate.PAID_KEYS) == 1


def test_the_witness_sweep_writes_where_it_is_told():
    """A test of the sweep wrote the live web/data/witness.json on every
    deploy's run of the suite."""
    import inspect
    from engine import witness as W
    sig = inspect.signature(W.run)
    assert "path" in sig.parameters and "out_dir" in sig.parameters
    src = (ROOT / "tests" / "test_the_record_has_an_outside_witness.py").read_text()
    assert 'path=d / "witness.json")' in src.split("def test_run_does_all_three")[1][:600]


def test_a_build_failure_note_belongs_to_its_own_thread():
    """The meme board's 15-second thread overwrote the shared note between
    college failing and the heartbeat reading why (2026-10-17)."""
    import threading
    import launch
    launch._LAST_BUILD_NOTE[0] = "exit 1: cfb_build.py timed out"
    t = threading.Thread(target=lambda: launch._LAST_BUILD_NOTE.__setitem__(
        0, "memes_build.py timed out after 180 seconds"))
    t.start()
    t.join()
    assert launch._LAST_BUILD_NOTE[0] == "exit 1: cfb_build.py timed out"
    launch._LAST_BUILD_NOTE[0] = ""

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
