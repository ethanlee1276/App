"""The league search answers in well under a second, and once the typing pauses.

Ethan, 2026-11-16: "Also players are not showing up on the search page for
players." Measured on the live site the same hour: a college football search
took 8 to 16 seconds ("arch manning" 15.6 s), an NBA one up to 5.9 s. Two
costs, both paid on every keystroke:

* the logs were searched with `LIKE '%q%'`, which no index can serve, so
  each letter read every row the league has (millions for college);
* every rostered player (41,888 in college football) went through the
  spelling matcher to pad the list, difflib included.

And the page sent one search per letter typed, so a one-core box worked
through a dozen of those before it reached the name actually typed.

Now each league's names are kept (engine/playersearch.NameIndex, built a
seek a name and warmed at start), a real name never reaches the spelling
matcher, a guess is never shown beside the name typed, and the page asks
the league once the typing stops for a moment.

Run directly: `python3 tests/test_the_search_answers_before_the_next_letter.py`
"""

import contextlib
import io
import json
import os
import random
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, playersearch as ps, statlogs  # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
LAUNCH = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
SERVER = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def _names(n, seed=11):
    rnd = random.Random(seed)
    first = ["Jacoby", "Jacob", "Coby", "Arch", "Archie", "Jeremiah", "Jeremy", "Carson", "Dylan", "José",
             "Amon-Ra", "D'Andre", "Ja'Marr", "Kauê", "Patrick", "Aaron", "Nikola", "A'ja", "Caitlin", "Josh"]
    last = ["Brissett", "Rodriguez", "Bryant", "Manning", "Smith", "Smith-Jones", "Beck", "Raiola", "Ramírez",
            "St. Brown", "O'Neal", "Chase", "Fernandes", "Mahomes", "Judge", "Jokić", "Wilson", "Clark", "Allen",
            "Hines-Allen", "Mc Donald", "Jr.", "Swift", "Lamb"]
    out = {f"{f} {l}" for f, l in ((rnd.choice(first), rnd.choice(last)) for _ in range(n * 3))}
    out |= {f"{rnd.choice(first)} {''.join(rnd.choice('abcdefghijklmnopqrstuvwxyz') for _ in range(rnd.randint(4, 9))).title()}"
            for _ in range(n)}
    return sorted(out)[:n]


QUERIES = ["jacoby brissett", "brissett", "jacob", "arch manning", "arch maning", "jeremia smiht", "smith",
           "st brown", "amonra", "ramirez jose", "kaue", "oneal", "carson bek", "jokic", "mahomez", "jugde",
           "xq", "j", "zzzzzz", "dandre", "hines allen", "allen hines", "mc donald", "mcdonald", "a ja wilson"]


# --- the same answers ------------------------------------------------------

def test_the_kept_list_ranks_exactly_as_the_matcher_does():
    """The name typed in, the tiers out, identical to `rank` name by name:
    the real tiers (0 to 2) where anyone has one, else the closest spellings."""
    names = _names(1500)
    ix = ps.NameIndex((n, 2026) for n in names)
    for q in QUERIES:
        want = {n: r for n in names for r in [ps.rank(n, q)] if r is not None}
        real = {n: r for n, r in want.items() if r < 3}
        got = {ix.names[k]: t for k, t in ix.ranked(ps.norm(q)).items()}
        assert got == (real or want), (q, sorted(set(got) ^ set(real or want))[:6])


def test_the_fast_typo_pass_takes_exactly_the_names_the_old_one_did():
    names = _names(1500, seed=5)
    norms = [ps.norm(n) for n in names]
    for q in QUERIES:
        ql = ps.norm(q)
        want = [k for k, n in enumerate(norms) if n and ps._close_enough(n, n.split(), ql, ql.split())]
        assert ps.fuzzy_hits(norms, ql) == want, q


def test_a_name_that_norms_to_nothing_does_not_shift_the_rest():
    rows = [("Jacoby Brissett", 2026), ("---", 2026), ("Jacob Rodriguez", 2025)]
    ix = ps.NameIndex(rows)
    assert ix.names == ["Jacoby Brissett", "Jacob Rodriguez"]
    assert list(ix.src) == [0, 2] and list(ix.last) == [2026, 2025]
    assert ix.norm_of(1) == "jacob rodriguez" and ix.norms() == ["jacoby brissett", "jacob rodriguez"]


# --- what it costs -----------------------------------------------------------

@contextlib.contextmanager
def _counting_matcher():
    real = ps.difflib.SequenceMatcher
    made = [0]

    class Counting(real):
        def __init__(self, *a, **kw):
            made[0] += 1
            super().__init__(*a, **kw)
    ps.difflib.SequenceMatcher = Counting
    try:
        yield made
    finally:
        ps.difflib.SequenceMatcher = real


def _roster_dir(names, sport="cfb"):
    d = tempfile.mkdtemp()
    teams = {}
    for i, n in enumerate(names):
        teams.setdefault(f"T{i % 130}", {"players": []})["players"].append(
            {"player": n, "position": "WR", "headshot": "", "number": str(i % 99)})
    with open(os.path.join(d, f"rosters_{sport}.json"), "w", encoding="utf-8") as fh:
        json.dump({"teams": teams}, fh)
    statlogs._ROSTER.clear()
    statlogs._ROSTER_INDEX.clear()
    return d


def _db_with(rows):
    path = os.path.join(tempfile.mkdtemp(), "h.db")
    conn = db.connect(path)
    db.upsert_player_logs(conn, [dict({"season": 2026, "team": "ARI", "opponent": "OPP", "position": "QB",
                                       "home": 1, "market": "pass_yds", "value": 200.0}, **r) for r in rows])
    conn.close()
    statlogs._NAME_INDEX.clear()
    return path


def test_a_real_name_never_reaches_the_spelling_matcher():
    """The 41,888-player college roster went through difflib on every
    keystroke to pad the list with near spellings. A name someone holds is
    found without it; only a search that finds nobody pays for spelling."""
    names = _names(6000, seed=3) + ["Arch Manning"]
    d = _roster_dir(names)
    path = _db_with([{"sport": "cfb", "period": "009", "game_id": "g1", "player": "Arch Manning", "team": "TEX"}])
    statlogs.search("cfb", "arch", db_path=path, data_dir=d)          # the lists are built
    with _counting_matcher() as made:
        hits = statlogs.search("cfb", "arch manning", db_path=path, data_dir=d)
    assert hits and hits[0]["player"] == "Arch Manning", hits
    assert made[0] == 0, f"{made[0]} spelling comparisons for a name the league holds"
    with _counting_matcher() as made:
        hits = statlogs.search("cfb", "arch maning", db_path=path, data_dir=d)
    assert hits and hits[0]["player"] == "Arch Manning" and hits[0]["rank"] == 3, hits[:3]
    assert made[0] > 0


def test_a_freshman_typed_exactly_never_reaches_the_spelling_matcher():
    """Nobody in the logs has the name and the roster does: the roster's names
    as typed are read before anyone's closest spellings, so a player with no
    game yet costs no spelling pass over every name the league has logged."""
    names = _names(3000, seed=9) + ["Freshman Exactname"]
    d = _roster_dir(names)
    path = _db_with([{"sport": "cfb", "period": "009", "game_id": f"g{i}", "player": n}
                     for i, n in enumerate(_names(3000, seed=4))])
    statlogs.search("cfb", "warm", db_path=path, data_dir=d)
    with _counting_matcher() as made:
        hits = statlogs.search("cfb", "freshman exactname", db_path=path, data_dir=d)
    assert [h["player"] for h in hits] == ["Freshman Exactname"] and hits[0]["games"] == 0, hits
    assert made[0] == 0, f"{made[0]} spelling comparisons for a name the roster holds"


# --- what it shows -----------------------------------------------------------

def test_a_guess_is_not_shown_beside_the_name_typed():
    """Ethan's search, 2026-11-16: "jacoby brissett" found him, and eleven
    rostered near spellings came with him (Jacob Rodriguez, Coby Bryant...)."""
    d = _roster_dir(["Jacoby Brissett", "Jacob Rodriguez", "Coby Bryant", "Jacob Bayer", "Jacob Cowing"], "nfl")
    path = _db_with([{"sport": "nfl", "period": f"{w:03d}", "game_id": f"g{w}", "player": "Jacoby Brissett"}
                     for w in range(1, 9)])
    hits = statlogs.search("nfl", "jacoby brissett", db_path=path, data_dir=d)
    assert [h["player"] for h in hits] == ["Jacoby Brissett"], hits
    # A misspelling still finds the nearest names, nearest first.
    hits = statlogs.search("nfl", "jacoby brisett", db_path=path, data_dir=d)
    assert hits and hits[0]["player"] == "Jacoby Brissett" and hits[0]["rank"] == 3, hits


def test_a_college_player_is_listed_at_his_school_not_espns_number():
    """Live, 16 Nov: "jeremiah smith" answered him alone, at "espn:194", the
    newest of his rows being a copy keyed by ESPN's number for Ohio State."""
    rows = [{"sport": "cfb", "period": f"2026-11-{d:02d}", "game_id": f"g{d}", "player": "Jeremiah Smith", "team": "OSU",
             "position": "WR", "market": m, "value": 90.0} for d in (7, 14) for m in ("rec_yds", "receptions")]
    rows += [{"sport": "cfb", "period": "2026-11-15", "game_id": "401", "player": "Jeremiah Smith",
              "team": "espn:194", "position": "", "market": "rec_yds", "value": 90.0},
             # The 14th's game held once more with the sides swapped: live, the search read "NU".
             {"sport": "cfb", "period": "2026-11-14", "game_id": "g14x", "player": "Jeremiah Smith", "team": "NU",
              "opponent": "OSU", "position": "WR", "market": "rec_yds", "value": 90.0},
            {"sport": "cfb", "period": "2025-11-29", "game_id": "g0", "player": "Old Walkon", "team": "espn:2000",
             "market": "rec_yds", "value": 5.0}]
    path = _db_with(rows)
    d = _roster_dir([], "cfb")
    hits = statlogs.search("cfb", "jeremiah smith", db_path=path, data_dir=d)
    assert [(h["player"], h["team"], h["position"]) for h in hits] == [("Jeremiah Smith", "OSU", "WR")], hits
    hits = statlogs.search("cfb", "old walkon", db_path=path, data_dir=d)
    assert [h["team"] for h in hits] == ["espn:2000"], "the number, when it is all a season has"


def test_a_traded_player_is_listed_at_his_new_club():
    """The club of his newest game, though the old one holds more of his lines."""
    rows = [{"sport": "nfl", "period": f"{w:03d}", "game_id": f"j{w}", "player": "Traded Man", "team": "JAX",
             "position": "WR", "market": m, "value": 50.0} for w in range(1, 10) for m in ("rec_yds", "receptions")]
    rows += [{"sport": "nfl", "period": "010", "game_id": "b10", "player": "Traded Man", "team": "BUF",
              "position": "WR", "market": "rec_yds", "value": 40.0}]
    hits = statlogs.search("nfl", "traded man", db_path=_db_with(rows), data_dir=_roster_dir([], "nfl"))
    assert [(h["player"], h["team"]) for h in hits] == [("Traded Man", "BUF")], hits


def test_the_play_files_short_names_are_not_a_second_player():
    """The NFL's red-zone and expected-points rows carry the play file's own
    spelling ("J.Brissett"), which the fantasy layer joins to the real name.
    In the search each was a second player with a game count and an empty
    card: "brissett" found Jacoby Brissett and "J.Brissett" (44 games)."""
    rows = [{"sport": "nfl", "period": f"{w:03d}", "game_id": f"g{w}", "player": "Jacoby Brissett"} for w in range(1, 5)]
    rows += [{"sport": "nfl", "period": f"{w:03d}", "game_id": f"ARI-{w:03d}", "player": "J.Brissett",
              "market": "rz_tgt", "value": 1.0} for w in range(1, 5)]
    rows += [{"sport": "nfl", "period": "001", "game_id": "g1", "player": n} for n in ("A.J. Brown", "D.K. Metcalf")]
    path = _db_with(rows)
    d = _roster_dir([], "nfl")
    assert [h["player"] for h in statlogs.search("nfl", "brissett", db_path=path, data_dir=d)] == ["Jacoby Brissett"]
    assert [h["player"] for h in statlogs.search("nfl", "aj brown", db_path=path, data_dir=d)] == ["A.J. Brown"]
    assert [h["player"] for h in statlogs.search("nfl", "metcalf", db_path=path, data_dir=d)] == ["D.K. Metcalf"]
    for short in ("J.Brissett", "P.Mahomes", "A.St. Brown", "J.Smith-Njigba", "Ja.Chase"):
        assert not statlogs._searchable("nfl", short), short
    for real in ("A.J. Brown", "D.K. Metcalf", "C.J. Stroud", "J.J. McCarthy", "Amon-Ra St. Brown"):
        assert statlogs._searchable("nfl", real), real
    assert statlogs._searchable("mlb", "J.Brissett"), "only the NFL's play file spells names this way"


def test_a_rostered_name_typed_beats_the_logs_guesses():
    """Nobody in the logs has the name, a freshman on the roster does: his
    exact name is the answer, and the logs' near spellings are not shown."""
    d = _roster_dir(["Freshman Exactname"], "cfb")
    path = _db_with([{"sport": "cfb", "period": "009", "game_id": "g1", "player": "Freshman Exactnam"}])
    hits = statlogs.search("cfb", "freshman exactname", db_path=path, data_dir=d)
    assert [h["player"] for h in hits] == ["Freshman Exactname"], hits


def test_the_all_league_box_drops_guesses_beside_an_answer():
    hits = [{"player": "A", "rank": 0}, {"player": "B", "rank": 3}, {"player": "C", "rank": 2}]
    assert [h["player"] for h in ps.no_guess_beside_an_answer(hits)] == ["A", "C"]
    only = [{"player": "B", "rank": 3}, {"player": "D", "rank": 3}]
    assert ps.no_guess_beside_an_answer(only) == only
    assert "return no_guess_beside_an_answer(merge(per, q, limit, order, prefer=prefer))" in open(
        os.path.join(ROOT, "engine", "playersearch.py"), encoding="utf-8").read()


# --- kept, and kept fresh ------------------------------------------------

def _row(player, game="g1"):
    return {"sport": "mlb", "season": 2026, "period": "2026-08-20", "game_id": game, "player": player,
            "team": "SEA", "opponent": "OPP", "position": "C", "home": 1, "market": "hits", "value": 1.0}


def _join_rebuilds():
    for t in threading.enumerate():
        if t.name.startswith(("names-", "roster-")):
            t.join(30)


def test_every_league_answers_from_its_list_while_the_new_one_builds():
    """Every league keeps answering from the list it has; the new list is
    built behind it and the next search reads it. Live, the evening of 16
    Nov, minutes after a deploy: a league under 20,000 names was rebuilt in
    line, and "mcdavid", "buzelis" and "judge" each took 17 to 25 seconds the
    first time after their logs moved, under a second straight after.

    The rebuild is held until the first answer is in: left to run, it can
    finish between the two reads one search makes (the gate's 8-at-a-time
    load did, 16 Nov), and the answer is then the fresh one, which is right
    and not what this checks. What this checks is that nobody waits for it."""
    import time
    d = _roster_dir([], "mlb")
    path = _db_with([_row("Aaron Judge")])
    gap, build = statlogs.NAME_INDEX_GAP, statlogs._build_names
    held = threading.Event()

    def held_build(conn, sport, sig):
        if threading.current_thread().name.startswith("names-"):
            held.wait(30)
        return build(conn, sport, sig)
    statlogs.NAME_INDEX_GAP = 0
    try:
        statlogs.search("mlb", "judge", db_path=path, data_dir=d)
        conn = db.connect(path)
        db.upsert_player_logs(conn, [_row("Cal Raleigh", "g2")])
        conn.close()
        statlogs._build_names = held_build
        t0 = time.time()
        first = statlogs.search("mlb", "raleigh", db_path=path, data_dir=d)
        took = time.time() - t0
        held.set()
        _join_rebuilds()
        second = statlogs.search("mlb", "raleigh", db_path=path, data_dir=d)
    finally:
        held.set()
        statlogs.NAME_INDEX_GAP, statlogs._build_names = gap, build
    assert not [h for h in first if h["player"] == "Cal Raleigh"], "the stale list was waited on"
    assert took < 10, took
    assert second and second[0]["player"] == "Cal Raleigh", second


def test_a_failed_rebuild_keeps_the_list_and_says_so_once():
    path = _db_with([_row("Aaron Judge")])
    statlogs.search("mlb", "judge", db_path=path, data_dir=_roster_dir([], "mlb"))
    key = ("mlb", os.path.realpath(path))
    old = statlogs._NAME_INDEX[key]
    old.at = 0.0
    real, said = statlogs._build_names, statlogs._NAMES_FAIL_SAID[0]

    def broken(*a, **kw):
        raise RuntimeError("disk gone")
    statlogs._build_names, statlogs._NAMES_FAIL_SAID[0] = broken, False
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            statlogs._rebuild_names("mlb", os.path.realpath(path))
            statlogs._rebuild_names("mlb", os.path.realpath(path))
    finally:
        statlogs._build_names, statlogs._NAMES_FAIL_SAID[0] = real, said
    assert statlogs._NAME_INDEX[key] is old
    assert old.at > 0, "the next try waits a minute instead of retrying on every search"
    assert out.getvalue().count("name list was not rebuilt") == 1, out.getvalue()
    assert key not in statlogs._NAMES_BUSY


def test_the_roster_is_reread_only_when_its_file_changes():
    d = _roster_dir(["Arch Manning"])
    first = statlogs._roster_players("cfb", d)
    key = ("cfb", d)
    statlogs._ROSTER[key] = (0.0,) + statlogs._ROSTER[key][1:]       # past its quarter hour
    assert statlogs._roster_players("cfb", d) is first, "an unchanged file was read again"
    path = os.path.join(d, "rosters_cfb.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"teams": {"TEX": {"players": [{"player": "Arch Manning"}, {"player": "Ryan Wingo"}]}}}, fh)
    os.utime(path, ns=(1, 1))
    statlogs._ROSTER[key] = (0.0,) + statlogs._ROSTER[key][1:]
    assert statlogs._roster_players("cfb", d) is first, "the search waited for the new file to be read"
    _join_rebuilds()
    again = statlogs._roster_players("cfb", d)
    assert again is not first and [p["player"] for p in again] == ["Arch Manning", "Ryan Wingo"], again
    assert statlogs._ROSTER_INDEX[key][0] is again, "the new roster's names were listed before it was handed out"
    _, ix = statlogs._roster_index("cfb", d)
    assert ix.names == ["Arch Manning", "Ryan Wingo"]
    # A file caught half-written keeps the roster in hand, not an empty one.
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('{"teams": {"TEX": {"players": [{"player": "Arch')
    os.utime(path, ns=(2, 2))
    statlogs._ROSTER[key] = (0.0,) + statlogs._ROSTER[key][1:]
    statlogs._roster_players("cfb", d)
    _join_rebuilds()
    assert statlogs._roster_players("cfb", d) is again


def test_a_search_in_the_first_build_waits_for_it_instead_of_building_twice():
    """After a restart the warm-up builds every league's list; a search that
    comes in meanwhile used to build its league again beside it."""
    path = _db_with([_row("Aaron Judge")])
    d = _roster_dir([], "mlb")
    build, made, started, held = statlogs._build_names, [], threading.Event(), threading.Event()

    def slow_build(conn, sport, sig):
        if sport == "mlb":                # the warm-up is building this league's list
            made.append(threading.current_thread().name)
            started.set()
            held.wait(30)
        return build(conn, sport, sig)
    statlogs._build_names = slow_build
    try:
        warm = statlogs.warm_search(db_path=path, data_dir=d)
        assert started.wait(30)
        out = []
        t = threading.Thread(target=lambda: out.append(statlogs.search("mlb", "judge", db_path=path, data_dir=d)))
        t.start()
        t.join(0.5)
        assert t.is_alive(), "the search did not wait for the build in progress"
        held.set()
        t.join(30)
        warm.join(60)
    finally:
        held.set()
        statlogs._build_names = build
    assert out and out[0] and out[0][0]["player"] == "Aaron Judge", out
    assert made == ["search-warm"], f"the league's list was built {len(made)} times: {made}"


def test_every_league_is_built_before_anyone_types():
    d = _roster_dir(["Arch Manning"], "cfb")
    path = _db_with([_row("Aaron Judge"), {"sport": "cfb", "period": "009", "game_id": "g9",
                                           "player": "Arch Manning", "team": "TEX"}])
    statlogs.warm_search(db_path=path, data_dir=d).join(60)
    real = os.path.realpath(path)
    assert ("mlb", real) in statlogs._NAME_INDEX and ("cfb", real) in statlogs._NAME_INDEX
    assert statlogs._NAME_INDEX[("cfb", real)].names == ["Arch Manning"]
    assert ("cfb", d) in statlogs._ROSTER_INDEX


def test_the_box_builds_the_lists_at_start():
    i = LAUNCH.index("def _startup_chores() -> None:")
    body = LAUNCH[i:i + 2500]
    assert "statlogs.warm_search()" in body and body.index("statlogs.warm_search()") < body.index(
        "with _BUILD_LOCK:"), "the lists are built before the boards, in their own thread"
    j = SERVER.index("        playerpage.warm()\n")
    assert "        statlogs.warm_search()\n" in SERVER[j:j + 200]


# --- the page ------------------------------------------------------------------

def test_the_page_asks_the_league_once_the_typing_pauses():
    i = APP.index("async function leagueSearchAfterPause(q, seq, host) {")
    body = APP[i:i + 600]
    assert "const LEAGUE_PAUSE_MS = 280;" in APP
    assert "if (!_leagueCache.has(`${state.sport}|${q}`)) {" in body
    assert "await new Promise((r) => setTimeout(r, LEAGUE_PAUSE_MS));" in body
    assert "if (seq !== _playersSeq) return null;" in body
    j = APP.index("async function renderPlayers(")
    k = APP.index("\nasync function ", j + 10)
    rp = APP[j:k]
    assert rp.count("await leagueSearchAfterPause(q, seq, host)") == 2, "both league asks wait for the pause"
    assert "await leagueSearch(q)" not in rp


def _browser(run):
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return None
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return None
    import rendercheck
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
            if os.path.exists("/opt/pw-browsers/chromium"):
                kw["executable_path"] = "/opt/pw-browsers/chromium"
            browser = pw.chromium.launch(**kw)
            try:
                return run(browser, port)
            finally:
                browser.close()
    finally:
        srv.shutdown()


def test_in_a_browser_a_name_typed_letter_by_letter_is_one_search():
    """Typed at a person's pace, "arch manning" asks the league once, for the
    whole name, and the page says it is searching while it waits."""
    body = {"board": {"sport": "cfb", "recommendations": [], "player_stats": {}},
            "logs": {"player": "Arch Manning", "stats": {"Passing Yards": [
                {"value": 260, "week": 7, "opponent": "OU", "home": False}]}},
            "page": {"sport": "cfb", "player": "Arch Manning", "team": "TEX", "position": "QB", "seasons": [2026],
                     "season": 2026, "bio": {"team": "TEX", "number": "16", "position": "QB"}, "notes": {},
                     "headline": [], "splits": {"rows": [], "groups": []},
                     "career": {"rows": [], "groups": [], "total": {}}},
            "log": {}, "news": {"sports": {}}}

    def run(browser, port):
        ctx = browser.new_context(viewport={"width": 412, "height": 823}, is_mobile=True, has_touch=True,
                                  device_scale_factor=1, service_workers="block")
        page = ctx.new_page()
        errors, asked = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        local = f"http://127.0.0.1:{port}/"
        page.route(lambda u: not u.startswith(local), lambda r: r.abort())

        def answer(key):
            return lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body[key]))

        def search(route):
            asked.append(route.request.url)
            route.fulfill(status=200, content_type="application/json", body=json.dumps({"players": [
                {"player": "Arch Manning", "sport": "cfb", "team": "TEX", "position": "QB", "games": 10,
                 "rank": 0, "headshot": ""}]}))
        for pattern, key in (("**/api/players/logs*", "logs"), ("**/api/players/page*", "page"),
                             ("**/api/players/gamelog*", "log"), ("**/data/news.json*", "news"),
                             ("**/api/recommendations*", "board"), ("**/data/recommendations*", "board")):
            page.route(pattern, answer(key))
        page.route("**/api/players/search*", search)
        page.add_init_script("try{localStorage.setItem('qb_intro_v1','1');localStorage.setItem('qb.tour','done');}"
                             "catch(e){}")
        page.goto(f"{local}index.html?sport=cfb#players", wait_until="load")
        page.wait_for_function("() => typeof state !== 'undefined' && state.view === 'players'", timeout=30000)
        page.type("#player-search", "arch manning", delay=60)
        waiting = page.evaluate("document.getElementById('players-board').innerText")
        page.wait_for_selector(".plr .plr-hero", timeout=30000)
        out = {"asked": asked, "waiting": waiting, "hero": page.inner_text(".plr-hero"), "errors": errors}
        ctx.close()
        return out
    got = _browser(run)
    if got is None:
        return
    assert len(got["asked"]) == 1 and "q=arch%20manning" in got["asked"][0], got["asked"]
    waiting = got["waiting"].lower()                       # the title is set in capitals
    assert "searching cfb players" in waiting and "arch manning" in waiting, got["waiting"]
    assert "Arch" in got["hero"] and "Manning" in got["hero"], got["hero"]
    assert not got["errors"], got["errors"]


if __name__ == "__main__":
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {name}")
            except Exception as exc:                                  # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    if fails:
        print(f"\n{fails} failed")
        sys.exit(1)
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
