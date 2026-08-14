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

AND NO THRESHOLD IS INVENTED. Rested / limited / extended are terciles of
the league's own distribution of those attempt counts, so they move when
the league's habits move. A hard-coded "ten attempts is extended" would
be a claim about football written by someone who did not check.
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


# --- the bands, taken from the league rather than chosen --------------------
def test_bands_need_a_real_sample_before_they_cut_anything():
    """A verdict from four games is a guess wearing a percentile."""
    c = _seeded()
    _pre(c, "DET", 2026, 2, "Jared Goff", "pass_att", 12)
    assert ps.bands(c) == {}


def test_bands_are_terciles_of_what_actually_happened():
    c = _db()
    for i in range(40):
        team = f"T{i}"
        _reg(c, team, 2025, f"QB{i}", "QB", 0.9, att=400)
        _pre(c, team, 2026, 2, f"QB{i}", "pass_att", i)
    b = ps.bands(c)
    assert b["n"] == 40
    assert 0 < b["lo"] < b["hi"] < 40


def test_the_verdict_is_unknown_without_bands():
    """The honest answer before the ingest has run, and the one the board
    shows rather than a confident guess."""
    assert ps.verdict(12, {}) == "unknown"
    assert ps.verdict(None, {"lo": 5, "hi": 20}) == "unknown"


def test_the_three_verdicts_land_where_they_should():
    cuts = {"lo": 5, "hi": 20, "n": 99}
    assert ps.verdict(0, cuts) == "rested"
    assert ps.verdict(12, cuts) == "limited"
    assert ps.verdict(25, cuts) == "extended"


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
