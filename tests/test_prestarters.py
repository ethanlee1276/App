"""Which teams will play their starters.

Ethan, 2026-08-14: "i wanna show props for the pre season … make sure to
implement scanning to see which teams will be playing starters and which
ones wont along with any other information like that that would be
useful."

He is right that this is THE question. A preseason game is not a contest
between two teams, it is a contest between two coaching decisions, and
the decision is how long the first string is on the field.

THE MEASUREMENT IS THE STARTING QUARTERBACK'S ATTEMPTS. He is out there
exactly as long as the staff wants the starters out there, and he is the
one player guaranteed to leave a mark in a box score when he is. Zero is
a rest, a handful is a series, twenty is a dress rehearsal.

WHAT THIS CANNOT SEE, stated rather than papered over: ESPN's preseason
box score carries passing, rushing and receiving, so a player only
appears if he touched the ball. A starting guard who played the whole
first half leaves no trace. "Starters seen" is therefore a count of
skill players and is named that way.

AND NO THRESHOLD IS INVENTED. The cuts are read out of the league's own
data, so they move when the league's habits move. A hard-coded "ten
attempts is a dress rehearsal" would be a claim about football written by
someone who did not check.

BUT THE FIRST CUT OF THOSE BANDS WAS STILL WRONG, in a way worth keeping
written down, because "taken from the data" is not the same as "taken
from the data correctly". They were terciles of the raw attempt column —
and a rest is EXACTLY zero, with about seven outings in ten being rests,
so both terciles landed on 0. The middle band became unreachable and any
attempt at all became a dress rehearsal: Josh Allen at 0.8 expected
attempts came out "extended" on a live page.

Zero is now its own category, because it is a fact rather than a
percentile, and the cuts come from the two things that actually vary —
the spread of REST RATES across the league, and the median workload among
outings he did play.
"""

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.nfl import prestarters as ps                     # noqa: E402


def _db():
    """A journal with both tables, shaped like the real ones."""
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE player_game_logs (sport TEXT, season INT,
        week TEXT, player TEXT, team TEXT, position TEXT, market TEXT,
        value REAL)""")
    c.execute("""CREATE TABLE preseason_player_logs (sport TEXT, season INT,
        week INT, game_id TEXT, player TEXT, team TEXT, opponent TEXT,
        position TEXT, home INT, market TEXT, value REAL)""")
    return c


def _reg(c, team, season, player, pos, snap, games=8, att=0):
    for g in range(games):
        c.execute("INSERT INTO player_game_logs VALUES ('nfl',?,?,?,?,?,?,?)",
                  (season, str(g), player, team, pos, "snap_pct", snap))
    if att:
        c.execute("INSERT INTO player_game_logs VALUES ('nfl',?,?,?,?,?,?,?)",
                  (season, "1", player, team, pos, "pass_att", att))


def _pre(c, team, season, week, player, market, value):
    c.execute("INSERT INTO preseason_player_logs VALUES "
              "('nfl',?,?,'g',?,?,'OPP','QB',1,?,?)",
              (season, week, player, team, market, value))


def _seeded():
    c = _db()
    _reg(c, "DET", 2025, "Jared Goff", "QB", 0.99, att=500)
    _reg(c, "DET", 2025, "Amon-Ra St. Brown", "WR", 0.85)
    _reg(c, "DET", 2025, "Jahmyr Gibbs", "RB", 0.67)
    _reg(c, "DET", 2025, "Deep Reserve", "WR", 0.10)
    _reg(c, "DET", 2025, "Penei Sewell", "OL", 0.99)   # never in a box score
    return c


# --- who counts as a starter ------------------------------------------------
def test_starters_come_from_real_snap_share():
    s = ps.starters(_seeded(), "DET", 2025)
    assert "Jared Goff" in s and "Amon-Ra St. Brown" in s
    assert "Deep Reserve" not in s


def test_snap_share_is_read_as_a_fraction_not_a_percent():
    """`snap_pct` stores 0.99, not 99. A threshold of 55 instead of 0.55
    selects nobody, and every team then reads as resting everyone — a
    silent, total failure that still renders."""
    assert 0 < ps.STARTER_SNAP < 1


def test_a_lineman_is_excluded_because_he_cannot_be_seen():
    """Sewell plays every snap and appears in no box score. Counting him
    among the starters we look for guarantees the share never reaches 1
    and makes every team look like it rested somebody."""
    assert "Penei Sewell" not in ps.starters(_seeded(), "DET", 2025)


def test_one_big_game_is_not_a_role():
    c = _seeded()
    _reg(c, "DET", 2025, "Injury Fill In", "WR", 1.0, games=1)
    assert "Injury Fill In" not in ps.starters(c, "DET", 2025)


def test_the_starting_qb_is_the_one_who_threw_the_ball():
    """Snap share ties two men when a team changed starters mid-season;
    attempts do not."""
    c = _seeded()
    _reg(c, "DET", 2025, "Backup QB", "QB", 0.60, att=40)
    assert ps.starting_qb(c, "DET", 2025) == "Jared Goff"


def test_a_team_with_no_passing_data_has_no_named_qb():
    assert ps.starting_qb(_db(), "DET", 2025) is None


# --- what a team actually did -----------------------------------------------
def test_usage_reads_the_attempts_and_the_faces():
    c = _seeded()
    _pre(c, "DET", 2026, 2, "Jared Goff", "pass_att", 12)
    _pre(c, "DET", 2026, 2, "Amon-Ra St. Brown", "receptions", 3)
    u = ps.usage(c, "DET", 2026, 2)
    assert u["qb"] == "Jared Goff" and u["qb_att"] == 12
    assert u["seen"] == 2 and u["roster"] == 3
    assert abs(u["share"] - 2 / 3) < 1e-9


def test_a_game_that_was_not_ingested_is_none_not_zero():
    """Zero attempts means he was rested. No data means we do not know.
    Collapsing the two would report every un-ingested game as a rest."""
    assert ps.usage(_seeded(), "DET", 2026, 2) is None


def test_a_missing_table_is_survivable():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE player_game_logs (sport TEXT, season INT, "
              "week TEXT, player TEXT, team TEXT, position TEXT, "
              "market TEXT, value REAL)")
    assert ps.usage(c, "DET", 2026, 2) is None


def test_a_departed_starter_is_not_recorded_as_a_rest():
    """THE THIRD ONE THAT SHIPPED, and the quietest. `usage` named a
    preseason's starter from the season BEFORE it, which is right for the
    fixture being previewed and wrong for every historical outing behind
    it: a team that changed quarterbacks had last year's man named, he was
    no longer on the roster, he threw no passes because he was somewhere
    else — and that zero read as a coach resting his starter.

    Cleveland's 2026 habit was four Augusts whose "starter" was a
    different departed player each time.

    For a season already played, the man who led THAT season's attempts is
    that preseason's starter and it is knowable. Hindsight is correct
    here: a tendency is a record of what happened."""
    c = _db()
    # 2025 regular: Old Guy started. 2026 regular: New Guy did.
    _reg(c, "CLE", 2025, "Old Guy", "QB", 0.95, att=500)
    _reg(c, "CLE", 2026, "New Guy", "QB", 0.95, att=480)
    # In the 2026 preseason New Guy threw 14 and Old Guy is gone.
    _pre(c, "CLE", 2026, 2, "New Guy", "pass_att", 14)
    u = ps.usage(c, "CLE", 2026, 2)
    assert u["qb"] == "New Guy", "named last season's departed starter"
    assert u["qb_att"] == 14, "a departed man's absence read as a rest"


def test_a_season_not_yet_played_still_falls_back_to_last_year():
    """The forward-looking half. In August 2026 the 2026 regular season
    has no snaps, and last year's starter is genuinely all that is
    knowable — so the fallback has to survive."""
    c = _db()
    _reg(c, "DET", 2025, "Jared Goff", "QB", 0.99, att=500)
    _pre(c, "DET", 2026, 2, "Jared Goff", "pass_att", 9)
    assert ps.role_season_for(c, "DET", 2026) == 2025
    assert ps.usage(c, "DET", 2026, 2)["qb"] == "Jared Goff"


# --- the bands, taken from the league rather than chosen --------------------
def test_bands_need_a_real_sample_before_they_cut_anything():
    """A verdict from four games is a guess wearing a percentile."""
    c = _seeded()
    _pre(c, "DET", 2026, 2, "Jared Goff", "pass_att", 12)
    assert ps.bands(c) == {}


def test_a_column_that_never_moves_makes_no_bands():
    """THE ONE THAT SHIPPED. `pass_att` was missing from the preseason box
    parser's market list, so every stored attempt count was 0.0. Two
    hundred zeros sailed past the sample-size check, cut into lo = hi = 0,
    and `verdict` took its bottom branch — every team in the league read
    "rested", with a 200-outing sample cited for it.

    Three bands need three distinct values. Fewer means the column is
    empty rather than the league unanimous, and the honest output is no
    bands at all, which renders as "unknown" per side."""
    c = _db()
    for i in range(40):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        _pre(c, team, 2026, 2, f"QB{i}", "pass_att", 0)
    assert ps.bands(c) == {}
    assert ps.verdict(1.0, ps.bands(c)) == "unknown"


def test_a_zero_inflated_column_does_not_collapse_the_middle_band():
    """THE SECOND ONE THAT SHIPPED, and the reason the cuts are no longer
    terciles of the raw column. A rest is EXACTLY zero, and about seven
    outings in ten are rests — so on the real table (392 outings, 270 of
    them zero) both terciles landed on 0. "limited" became unreachable and
    any attempt at all became a dress rehearsal: Josh Allen at 0.8
    expected attempts came out "extended".

    Zero is now its own category and the cuts are taken from the spread of
    REST RATES, which is the thing that actually varies."""
    c = _db()
    for i in range(30):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        # Rest rate walks 0/4 .. 4/4 across the league; when he plays it
        # is a real workload, never a token attempt.
        rests = i % 5
        for wk in range(4):
            _pre(c, team, 2026, wk, f"QB{i}", "pass_att",
                 0 if wk < rests else 8 + (i % 7))
    b = ps.bands(c)
    assert b, "a league with a real spread of habits must produce cuts"
    assert b["rest_lo"] < b["rest_hi"], "the middle band is unreachable"
    assert b["play_cut"] > 0, "the played cut came out of the zeros"
    # And all three verdicts are now reachable.
    assert {ps.verdict(0.0, b), ps.verdict(0.5, b),
            ps.verdict(1.0, b)} == {"plays", "mixed", "rests"}


def test_bands_come_from_the_league_rather_than_from_a_choice():
    """Both cuts are read out of what the league did — the spread of rest
    rates, and the median workload among outings actually played — so they
    move when the league's habits move. A hard-coded "ten attempts is a
    dress rehearsal" would be a claim about football written by someone
    who did not check."""
    c = _db()
    for i in range(30):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        for wk in range(4):
            _pre(c, team, 2026, wk, f"QB{i}", "pass_att",
                 0 if wk < i % 5 else 6 + (i % 11))
    b = ps.bands(c)
    assert b["n"] == 120 and b["n_team_seasons"] == 30
    assert 0 <= b["rest_lo"] < b["rest_hi"] <= 1
    assert 0 < b["play_cut"] <= 17
    assert 0 < b["league_rest_rate"] < 1


def test_the_played_cut_ignores_the_rests():
    """A median taken over the zeros is a median of "did not play", which
    is not a workload and cannot separate a series from a rehearsal."""
    c = _db()
    for i in range(30):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        # Rest rates spread across the league so the cuts exist at all;
        # every outing he DOES play is exactly 20 attempts.
        for wk in range(4):
            _pre(c, team, 2026, wk, f"QB{i}", "pass_att",
                 0 if wk < i % 4 else 20)
    b = ps.bands(c)
    assert b["play_cut"] == 20, "the cut was dragged down by the rests"
    assert 0 < b["league_rest_rate"] < 1


def test_a_league_with_one_shared_habit_makes_no_cuts():
    """Every team resting exactly as often as every other leaves the two
    rest cuts equal, which is the degenerate case that made "limited"
    unreachable in the first place. No cuts is the honest output."""
    c = _db()
    for i in range(30):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        for wk in range(4):
            _pre(c, team, 2026, wk, f"QB{i}", "pass_att", 0 if wk < 3 else 20)
    assert ps.bands(c) == {}


def test_the_verdict_is_unknown_without_bands():
    """The honest answer before the ingest has run, and the one the board
    shows rather than a confident guess."""
    assert ps.verdict(0.5, {}) == "unknown"
    assert ps.verdict(None, {"rest_lo": .2, "rest_hi": .7}) == "unknown"


def test_the_three_verdicts_land_where_they_should():
    """Read from the REST RATE, which is the question — "will they play
    their starters" — rather than from a mean attempt count, which on a
    bimodal habit describes none of the outings it averages."""
    cuts = {"rest_lo": 0.2, "rest_hi": 0.7, "n": 99}
    assert ps.verdict(0.0, cuts) == "plays"
    assert ps.verdict(0.5, cuts) == "mixed"
    assert ps.verdict(1.0, cuts) == "rests"


# --- tendency, which is all a future game can have --------------------------
def test_tendency_averages_past_outings_by_week():
    c = _seeded()
    for season, att in ((2024, 4), (2025, 18)):
        _reg(c, "DET", season - 1, "Jared Goff", "QB", 0.99, att=500)
        _pre(c, "DET", season, 2, "Jared Goff", "pass_att", att)
    t = ps.tendency(c, "DET", [2024, 2025])
    assert t["n"] == 2 and t["mean_att"] == 11.0
    assert t["by_week"][2] == 11.0


def test_a_team_with_no_history_reports_none_rather_than_zero():
    t = ps.tendency(_seeded(), "DET", [2024, 2025])
    assert t["n"] == 0 and t["mean_att"] is None


# --- the scan the board reads -----------------------------------------------
def test_the_scan_answers_per_side():
    c = _seeded()
    _reg(c, "MIA", 2025, "Tua Tagovailoa", "QB", 0.95, att=450)
    for season in (2024, 2025):
        _reg(c, "DET", season - 1, "Jared Goff", "QB", 0.99, att=500)
        _reg(c, "MIA", season - 1, "Tua Tagovailoa", "QB", 0.95, att=450)
        _pre(c, "DET", season, 2, "Jared Goff", "pass_att", 2)
        _pre(c, "MIA", season, 2, "Tua Tagovailoa", "pass_att", 22)
    out = ps.scan(c, [{"home": "DET", "away": "MIA", "week": 2,
                       "date": "2026-08-14"}], 2026, seasons=[2024, 2025])
    home = out["games"][0]["sides"]["home"]
    away = out["games"][0]["sides"]["away"]
    assert home["team"] == "DET" and home["expect_att"] == 2.0
    assert away["team"] == "MIA" and away["expect_att"] == 22.0
    assert home["games_seen"] == 2


def test_the_scan_says_unknown_rather_than_guessing():
    """No ingested preseason at all — every side reads unknown, which is
    what the board must print until `ingest.py nflpre` has run."""
    out = ps.scan(_seeded(), [{"home": "DET", "away": "MIA", "week": 2,
                               "date": "2026-08-14"}], 2026)
    assert out["games"][0]["sides"]["home"]["verdict"] == "unknown"
    assert out["bands"] == {}


def test_the_scan_still_names_the_quarterbacks():
    """Even with no preseason history, who the starter IS comes from the
    regular season and is worth showing."""
    out = ps.scan(_seeded(), [{"home": "DET", "away": "MIA", "week": 2,
                               "date": "2026-08-14"}], 2026)
    assert out["games"][0]["sides"]["home"]["qb"] == "Jared Goff"


# --- the wiring -------------------------------------------------------------
def test_the_probe_exists():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--prescan" in argv' in src and "show_prescan" in src


def test_the_probe_says_what_to_run_when_nothing_is_ingested():
    """"unknown" everywhere with no explanation is the same dead end the
    preseason board itself hit."""
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def show_prescan(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "ingest.py nflpre" in body


def test_the_payload_carries_the_scan():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    assert 'payload["starter_scan"]' in src


def test_the_card_calls_a_habit_a_habit():
    """A fixture that has not been played has no team sheet. Printing a
    tendency as though it were one is exactly how this feature would
    start lying."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function starterScanHTML(")
    body = app[i:app.index("\n}", i)]
    assert "habit, not a team sheet" in body


def test_an_unknown_side_renders_nothing():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function starterScanHTML(")
    body = app[i:app.index("\n}", i)]
    assert 's.verdict === "unknown"' in body


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
