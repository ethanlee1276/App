"""The free streak game: the slate leaks nothing, the referee is fair.

Ethan's roadmap, item 4: "A daily pick'em/streak survivor using your own
props: pick 3, keep your streak alive, leaderboard. No money = no MGCB
gating... this also builds your user base before the paywall flips on."

Two properties carry the whole feature, and both are pinned here rather
than trusted:

  * THE FREE FILE IS CLEAN. streak.json sits in FREE_FILES — anyone can
    curl it — so a question may carry only facts: player, market, line,
    lock time, graded result. The moment a side, an edge, a projection
    or a price appears in a published question, the paid product is on
    the public path wearing a game's clothes. The key-census test below
    is the tripwire.
  * THE REFEREE CANNOT BE PLAYED. Locks are enforced against the
    slate's own UTC instants, the 3-pick cap against the database, and
    grading reuses the ledger's evidence guards — the same ones that
    stopped the journal grading tonight's bets against last night's box
    scores. A streak someone lost to a premature grade is not a game,
    it is a support ticket.

Run directly: `python3 tests/test_streak.py`
"""

import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import accounts as A                                # noqa: E402
from engine import db as DB                                     # noqa: E402
from engine import gate                                         # noqa: E402
from engine import streak as S                                  # noqa: E402

NOW = dt.datetime(2026, 8, 24, 18, 0, tzinfo=dt.timezone.utc)
TODAY = "2026-08-24"
GOOD = "correct-horse-battery"


def _board():
    return {
        "games": [
            {"home": "New York Yankees", "away": "Boston Red Sox",
             "kickoff": "2026-08-24T23:05:00Z"},
            {"home": "Los Angeles Dodgers", "away": "San Diego Padres",
             "kickoff": "2026-08-25T02:10:00Z"},
        ],
        "recommendations": [
            {"player": "Juan Soto", "team": "New York Yankees",
             "opponent": "Boston Red Sox", "market": "total_bases",
             "market_label": "Total Bases", "line": 1.5, "odds": -110,
             "side": "OVER", "edge": 0.07, "ev_per_unit": 0.05,
             "recommended": True, "has_market": True},
            {"player": "Aaron Judge", "team": "New York Yankees",
             "opponent": "Boston Red Sox", "market": "hits",
             "market_label": "Hits", "line": 1.5, "odds": 105,
             "has_market": True},
            {"player": "Rafael Devers", "team": "Boston Red Sox",
             "opponent": "New York Yankees", "market": "total_bases",
             "market_label": "Total Bases", "line": 1.5, "odds": -102,
             "has_market": True},
            {"player": "Mookie Betts", "team": "Los Angeles Dodgers",
             "opponent": "San Diego Padres", "market": "hits",
             "market_label": "Hits", "line": 1.5, "odds": -108,
             "has_market": True},
            {"player": "Manny Machado", "team": "San Diego Padres",
             "opponent": "Los Angeles Dodgers", "market": "total_bases",
             "market_label": "Total Bases", "line": 1.5, "odds": -115,
             "has_market": True},
            {"player": "Shohei Ohtani", "team": "Los Angeles Dodgers",
             "opponent": "San Diego Padres", "market": "home_runs",
             "market_label": "Home Runs", "line": 0.5, "odds": 320,
             "has_market": True},
            {"player": "No Price", "team": "New York Yankees",
             "opponent": "Boston Red Sox", "market": "hits",
             "market_label": "Hits", "line": 0.5, "odds": -110,
             "has_market": False},
        ],
    }


def _slate():
    return S.build_slate([S.question_pool(_board(), "mlb", TODAY, NOW)])


def _accounts_db():
    d = tempfile.mkdtemp()
    conn = A.connect(os.path.join(d, "acc.db"))
    _, out = A.create_user(conn, "player@example.com", GOOD, confirmed=True)
    S.ensure_tables(conn)
    return conn, out["id"]


def _hist_db():
    return DB.connect(os.path.join(tempfile.mkdtemp(), "hist.db"))


# --- the no-leak contract ----------------------------------------------------

def test_published_questions_carry_facts_only():
    """THE tripwire. The slate is a FREE file; the model's opinion of a
    market — side, price, projection, edge, stake — must never appear in
    a question, however the builder evolves. The board rows feeding it
    carry all of those fields; not one may survive selection."""
    slate = _slate()
    assert slate, "fixture produced no slate — the checks below ran on nothing"
    allowed = {"qid", "sport", "player", "team", "opp", "game",
               "market", "label", "line", "lock"}
    for q in slate:
        extra = set(q) - allowed
        assert not extra, f"question leaked fields: {sorted(extra)}"
        for banned in ("side", "odds", "book", "edge", "ev", "proj",
                       "recommended", "stake"):
            assert banned not in q


def test_streak_json_is_a_registered_free_board():
    """Free by DECISION, in the gate's own registries — an unknown board
    is treated as paid, which would 401 the free game's slate the day
    the paywall flag goes on."""
    assert "streak.json" in gate.FREE_FILES
    assert "streak.json" in gate.KNOWN_BOARDS
    assert gate.is_free("streak.json")
    doc = {"questions": [{"player": "x"}]}
    assert gate.redact(doc, "streak.json") == doc


def test_selection_is_by_price_balance_not_edge():
    """The +320 longshot and the unpriced row never qualify, however big
    the model's edge on them: balance is the only ranking. A slate built
    from edges would be the picks list with the sides erased — still
    readable by anyone who knows the model likes overs."""
    pool = S.question_pool(_board(), "mlb", TODAY, NOW)
    players = {q["player"] for q in pool}
    assert "Shohei Ohtani" not in players     # |implied − .5| over the cap
    assert "No Price" not in players          # has_market: False
    slate = _slate()
    # Most balanced first: +100 would rank above everything here; -102 is
    # the closest present.
    assert slate[0]["player"] == "Rafael Devers"


def test_slate_respects_per_game_and_per_player_caps():
    slate = _slate()
    per_game = {}
    for q in slate:
        per_game[q["game"]] = per_game.get(q["game"], 0) + 1
    assert all(n <= S.MAX_PER_GAME for n in per_game.values())
    assert len({(q["sport"], q["player"]) for q in slate}) == len(slate)


def test_started_games_yield_no_questions():
    now = dt.datetime(2026, 8, 25, 1, 0, tzinfo=dt.timezone.utc)
    pool = S.question_pool(_board(), "mlb", TODAY, now)
    # Yankees game (23:05Z) has started; only the Dodgers game remains.
    assert all("Dodgers" in q["game"] for q in pool)


def test_slate_too_small_to_play_is_refused():
    board = _board()
    board["recommendations"] = board["recommendations"][:2]
    pool = S.question_pool(board, "mlb", TODAY, NOW)
    assert S.build_slate([pool]) == []


def test_qids_are_stable_across_rebuilds():
    a = {q["player"]: q["qid"] for q in _slate()}
    b = {q["player"]: q["qid"] for q in _slate()}
    assert a == b


# --- grading ----------------------------------------------------------------

def test_grading_over_under_and_push():
    hist = _hist_db()
    old = "2026-08-20"
    hist.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, "
        "player, team, market, value) VALUES "
        "('mlb', 2026, ?, 'g1', 'Juan Soto', 'New York Yankees', "
        "'total_bases', 3)", (old,))
    hist.commit()
    q = {"qid": "x", "sport": "mlb", "player": "Juan Soto",
         "market": "total_bases", "line": 1.5, "date": old}
    assert S.grade_question(hist, q, TODAY) == ("over", 3.0)
    assert S.grade_question(hist, dict(q, line=4.5), TODAY)[0] == "under"
    # A push is nobody's win — the fold counts it for neither side.
    assert S.grade_question(hist, dict(q, line=3.0), TODAY)[0] == "void"


def test_todays_question_waits_for_positive_proof_of_a_final():
    """The ledger's premature-grade lesson, inherited whole: a stat row
    on today's date with no final score in the games table is a partial
    line, and grading a streak against it would settle people's nights
    off the fourth inning.

    Dated with the REAL today, not the file's frozen TODAY: the guard's
    strict window is "today or yesterday" off the wall clock
    (ledger._too_early_to_grade reads datetime.date.today()), so a
    frozen date ages out of it at midnight — this test first failed two
    days after it was written, at 00:00 UTC, with no code change."""
    real_today = dt.date.today().isoformat()
    hist = _hist_db()
    hist.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, "
        "player, team, market, value) VALUES "
        "('mlb', 2026, ?, 'g1', 'Juan Soto', 'New York Yankees', "
        "'total_bases', 1)", (real_today,))
    hist.commit()
    q = {"qid": "x", "sport": "mlb", "player": "Juan Soto",
         "market": "total_bases", "line": 1.5, "date": real_today}
    assert S.grade_question(hist, q, real_today) == (None, None)
    # The team's final posts → the same question grades.
    hist.execute(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score) VALUES ('mlb', 2026, ?, 'g1', "
        "'New York Yankees', 'Boston Red Sox', 5, 2)", (real_today,))
    hist.commit()
    assert S.grade_question(hist, q, real_today)[0] == "under"


def test_question_with_no_stat_line_voids_only_after_the_window():
    hist = _hist_db()
    q = {"qid": "x", "sport": "mlb", "player": "Vanished Man",
         "market": "hits", "line": 0.5}
    waiting = dict(q, date="2026-08-23")
    assert S.grade_question(hist, waiting, TODAY) == (None, None)
    stale = dict(q, date="2026-08-19")
    assert S.grade_question(hist, stale, TODAY) == ("void", None)


def test_doubleheader_day_voids_rather_than_guessing():
    hist = _hist_db()
    for gid in ("g1", "g1-G2"):
        hist.execute(
            "INSERT INTO player_game_logs (sport, season, period, game_id, "
            "player, team, market, value) VALUES "
            "('mlb', 2026, '2026-08-20', ?, 'Juan Soto', "
            "'New York Yankees', 'hits', 2)", (gid,))
    hist.commit()
    q = {"qid": "x", "sport": "mlb", "player": "Juan Soto",
         "market": "hits", "line": 1.5, "date": "2026-08-20"}
    assert S.grade_question(hist, q, TODAY)[0] == "void"


def test_grade_day_stamps_final_only_when_every_question_has_a_result():
    hist = _hist_db()
    hist.execute(
        "INSERT INTO player_game_logs (sport, season, period, game_id, "
        "player, team, market, value) VALUES "
        "('mlb', 2026, '2026-08-20', 'g1', 'Juan Soto', "
        "'New York Yankees', 'hits', 2)")
    hist.commit()
    day = {"questions": [
        {"qid": "a", "sport": "mlb", "player": "Juan Soto",
         "market": "hits", "line": 1.5,
         "lock": "2026-08-20T23:05:00Z"},
        {"qid": "b", "sport": "mlb", "player": "Still Waiting",
         "market": "hits", "line": 0.5,
         "lock": "2026-08-20T23:05:00Z"},
    ]}
    changed = S.grade_day(hist, day, "2026-08-20", "2026-08-22", now=NOW)
    assert changed
    assert day["questions"][0]["result"] == "over"
    assert not day.get("final"), "half-graded night must not read as final"


# --- the referee ------------------------------------------------------------

def test_picks_lock_at_the_games_own_start():
    conn, uid = _accounts_db()
    slate = _slate()
    doc = {"date": TODAY, "questions": slate, "days": {}}
    early = next(q for q in slate if "Yankees" in q["game"])
    late_game = next(q for q in slate if "Dodgers" in q["game"])
    after_first = dt.datetime(2026, 8, 24, 23, 30, tzinfo=dt.timezone.utc)
    code, out = S.record_pick(conn, uid, doc, early["qid"], "over",
                              now=after_first)
    assert code == 409 and "locked" in out["error"]
    # …while the later game's question still takes a pick.
    code, _ = S.record_pick(conn, uid, doc, late_game["qid"], "under",
                            now=after_first)
    assert code == 200


def test_three_picks_and_no_more_but_changes_and_clears_are_free():
    conn, uid = _accounts_db()
    slate = _slate()
    doc = {"date": TODAY, "questions": slate, "days": {}}
    for q in slate[:3]:
        assert S.record_pick(conn, uid, doc, q["qid"], "over", now=NOW)[0] == 200
    code, out = S.record_pick(conn, uid, doc, slate[3]["qid"], "over", now=NOW)
    assert code == 409 and "3" in out["error"]
    # Changing a made pick is not a new pick.
    assert S.record_pick(conn, uid, doc, slate[0]["qid"], "under",
                         now=NOW)[0] == 200
    assert S.day_picks(conn, uid, TODAY)[slate[0]["qid"]] == "under"
    # Clearing frees the slot.
    assert S.record_pick(conn, uid, doc, slate[0]["qid"], "clear",
                         now=NOW)[0] == 200
    assert S.record_pick(conn, uid, doc, slate[3]["qid"], "over",
                         now=NOW)[0] == 200


def test_unknown_question_and_bad_side_are_refused():
    conn, uid = _accounts_db()
    doc = {"date": TODAY, "questions": _slate(), "days": {}}
    assert S.record_pick(conn, uid, doc, "nope", "over", now=NOW)[0] == 404
    qid = doc["questions"][0]["qid"]
    assert S.record_pick(conn, uid, doc, qid, "banana", now=NOW)[0] == 400


# --- the rules of surviving a day -------------------------------------------

def _day(results):
    return {"final": True,
            "questions": [{"qid": k, "result": v} for k, v in results.items()]}


def test_judge_day_wins_must_outnumber_losses():
    picks = {"a": "over", "b": "over", "c": "over"}
    assert S.judge_day(picks, _day({"a": "over", "b": "over", "c": "under"})) \
        == "survived"                                   # 2-1 lives
    assert S.judge_day(picks, _day({"a": "over", "b": "under", "c": "void"})) \
        == "lost"                                       # 1-1 with a push dies
    assert S.judge_day(picks, _day({"a": "over", "b": "void", "c": "void"})) \
        == "survived"                                   # 1-0 with two pushes
    assert S.judge_day(picks, _day({"a": "void", "b": "void", "c": "void"})) \
        == "skip"                                       # nobody played


def test_judge_day_fewer_than_three_picks_is_a_skip_not_a_loss():
    picks = {"a": "over", "b": "over"}
    assert S.judge_day(picks, _day({"a": "under", "b": "under"})) == "skip"


def test_fold_builds_resets_and_never_double_counts():
    conn, uid = _accounts_db()
    days = {}
    # qids are date-scoped in real slates (the hash includes the date), so
    # the fixture's are too — reusing "a" across days trips the PK.
    for date, results in (("2026-08-20", {"20a": "over", "20b": "over", "20c": "under"}),
                          ("2026-08-21", {"21a": "over", "21b": "over", "21c": "void"}),
                          ("2026-08-22", {"22a": "under", "22b": "under", "22c": "over"})):
        days[date] = _day(results)
        for qid in results:
            conn.execute(
                "INSERT INTO streak_picks (user_id, date, qid, side, "
                "created_at) VALUES (?,?,?,?,0)", (uid, date, qid, "over"))
    conn.commit()
    doc = {"date": TODAY, "questions": [], "days": days}
    st = S.fold_user(conn, uid, doc)
    # 20th survived, 21st survived, 22nd lost: streak 0, best 2.
    assert (st["current"], st["best"], st["last_result"]) == (0, 2, "lost")
    again = S.fold_user(conn, uid, doc)
    assert (again["current"], again["best"]) == (0, 2), "fold double-counted"


def test_fold_stops_at_a_night_still_grading():
    conn, uid = _accounts_db()
    days = {"2026-08-20": _day({"a": "over", "b": "over", "c": "over"}),
            "2026-08-21": {"final": False, "questions": [
                {"qid": "d", "result": "over"}, {"qid": "e"}, {"qid": "f"}]}}
    for date, qids in (("2026-08-20", "abc"), ("2026-08-21", "def")):
        for qid in qids:
            conn.execute(
                "INSERT INTO streak_picks (user_id, date, qid, side, "
                "created_at) VALUES (?,?,?,?,0)", (uid, date, qid, "over"))
    conn.commit()
    st = S.fold_user(conn, uid, {"date": TODAY, "questions": [], "days": days})
    assert st["current"] == 1
    assert st["folded_through"] == "2026-08-20", \
        "a half-graded night folded — its verdict could still change"


# --- names and the leaderboard ----------------------------------------------

def test_display_names_reject_emails_and_junk():
    assert S.name_problem("Ethan L") is None
    assert S.name_problem("") is None                  # clearing is allowed
    assert S.name_problem("a@b.com") is not None       # no leaked addresses
    assert S.name_problem("x") is not None
    assert S.name_problem("a" * 30) is not None


def test_leaderboard_lists_named_players_only():
    conn, uid = _accounts_db()
    _, other = A.create_user(conn, "quiet@example.com", GOOD, confirmed=True)
    for u, name, cur, best in ((uid, "Ethan L", 3, 5), (other["id"], "", 9, 9)):
        conn.execute(
            "INSERT INTO streak_state (user_id, name, current, best, "
            "folded_through) VALUES (?,?,?,?, '')", (u, name, cur, best))
    conn.commit()
    board = S.leaders(conn)
    assert [r["name"] for r in board] == ["Ethan L"], \
        "an unnamed account appeared on the public board"


def test_tonight_is_a_count_never_a_roster():
    """Day one: the board is rightly empty (nothing has graded), but
    "Nobody on the board yet" right after making picks read as the game
    being broken — Ethan's launch-day report. playing_today is the life
    sign: full slates in for the date, counted. A COUNT only — playing
    is not the same consent as being ranked in public by name."""
    conn, uid = _accounts_db()
    _, other = A.create_user(conn, "second@example.com", GOOD, confirmed=True)
    for i, q in enumerate(("q1", "q2", "q3")):
        conn.execute("INSERT INTO streak_picks (user_id, date, qid, side, "
                     "created_at) VALUES (?,?,?,?,0)", (uid, TODAY, q, "over"))
    # two picks is not a played night, so the neighbour does not count
    for q in ("q1", "q2"):
        conn.execute("INSERT INTO streak_picks (user_id, date, qid, side, "
                     "created_at) VALUES (?,?,?,?,0)",
                     (other["id"], TODAY, q, "over"))
    conn.commit()
    assert S.playing_today(conn, TODAY) == 1
    assert S.playing_today(conn, "") == 0
    import inspect
    src = inspect.getsource(S.playing_today)
    assert "name" not in src.replace("Names stay out", ""), \
        "the count is reading names — it must never become a roster"


def test_the_page_says_the_picks_landed():
    """The note under the card must switch to a confirmation once all
    picks are in — an empty string there is the silence that was
    reported as 'I made my picks and nothing happened'."""
    app = _read("web", "js", "app.js")
    i = app.index("async function renderStreak()")
    body = app[i:i + 6000]
    assert "You’re in for tonight" in body
    assert "nPicked >= need" in body
    assert "in_tonight" in app, "the tonight count never reaches the page"
    assert "player${_stkTonight === 1" in app


# --- the account promises hold here too -------------------------------------

def test_delete_user_takes_streak_data_with_it():
    conn, uid = _accounts_db()
    conn.execute("INSERT INTO streak_picks (user_id, date, qid, side, "
                 "created_at) VALUES (?,?,?,?,0)", (uid, TODAY, "q", "over"))
    conn.execute("INSERT INTO streak_state (user_id, name) VALUES (?, 'X')",
                 (uid,))
    conn.commit()
    A.delete_user(conn, uid)
    for table in ("streak_picks", "streak_state"):
        n = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?",
                         (uid,)).fetchone()[0]
        assert n == 0, f"{table} outlived the account it belonged to"


def test_export_includes_streak_data():
    conn, uid = _accounts_db()
    S.set_name(conn, uid, "Ethan L")
    conn.execute("INSERT INTO streak_picks (user_id, date, qid, side, "
                 "created_at) VALUES (?,?,?,?,0)", (uid, TODAY, "q", "over"))
    conn.commit()
    out = A.export_user(conn, uid)
    assert out["streak"]["name"] == "Ethan L"
    assert out["streak_picks"][0]["qid"] == "q"


# --- the wiring is real, not remembered -------------------------------------

def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_server_routes_and_launch_sweep_exist():
    server = _read("server.py")
    for needle in ('"/api/streak/"', "_streak_get", "_streak_post",
                   "streak_slate"):
        assert needle in server, f"server.py lost {needle}"
    launch = _read("launch.py")
    assert "_streak.run(" in launch, "the sweep no longer builds the slate"
    assert '"nfl"' not in launch.split("_streak.run(")[1].split(")")[0], \
        "NFL joined the slate sports — its logs are week-filed; see " \
        "engine/streak.py before letting this through"


def test_page_is_dispatched_and_outside_the_wall():
    app = _read("web", "js", "app.js")
    assert 'if (name === "streak") renderStreak();' in app, \
        "navigating to #streak would show a blank page — the futures lesson"
    wall = app[app.index("const WALL_OPEN"):]
    wall = wall[:wall.index("]")]
    assert '"streak"' in wall, \
        "the acquisition game went behind the wall it exists to feed"
    html = _read("web", "index.html")
    assert 'id="view-streak"' in html
    assert 'data-view="streak"' in html


def test_run_publishes_through_the_gate(tmp_base=None):
    """run() must write BOTH copies via gate.publish — a builder that
    wrote the public path directly would bypass every sealing rule the
    gate exists to enforce (free today is a decision, not a shape)."""
    src = _read("engine", "streak.py")
    assert "gate.publish(doc, OUT_PUBLIC" in src
    assert "open(OUT_PUBLIC" not in src


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
