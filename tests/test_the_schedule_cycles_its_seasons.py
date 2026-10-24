"""The team page's Schedule tab cycles every season on file.

Ethan, 2026-09-28, on the Bears' schedule: "Since we have 2021-2026 stats,
we should be able too cycle from 2021 - 2026 here." teamdex.season_schedule
now names every season the team has games in; /api/team takes ?season= and
?only=schedule so a chip reads one season without redrawing the page; the
page draws the chips and keeps each season it read. Two fixes from the same
screenshot ride along: "Wk 001" reads "Wk 1", and a far-off week with no
spread posted no longer says "line 0".

Called, not read, for the endpoint (the test_team_endpoint pattern: an
in-memory database, db.connect patched, never the box's).

Run directly: `python3 tests/test_the_schedule_cycles_its_seasons.py`
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server                                                # noqa: E402
from engine import db, teamdex                               # noqa: E402

_GAMES = (
    # (season, period, date, home, away, home_score, away_score, spread, total)
    (2024, "005", "2024-10-06", "CHI", "CAR", 36, 10, -4.0, 42.0),
    (2025, "019", "2026-01-11", "CHI", "GB", 24, 20, -1.5, 44.5),      # a Wild Card game
    (2026, "001", "2026-09-13", "CAR", "CHI", 37, 59, 3.0, 47.5),
    (2026, "003", "2026-09-28", "CHI", "PHI", None, None, 4.5, 41.5),
    (2026, "005", "2026-10-11", "GB", "CHI", None, None, 0.0, 49.5),     # no spread posted yet
    (2026, "008", "2026-11-02", "SEA", "CHI", None, None, 0.0, None),
)


def _conn():
    conn = db.connect(":memory:")
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, date, home, away, home_score, away_score, "
        "spread, total) VALUES ('nfl',?,?,?,?,?,?,?,?,?,?)",
        [(s, p, f"{a}@{h}{s}{p}", d, h, a, hs, as_, sp, to) for (s, p, d, h, a, hs, as_, sp, to) in _GAMES])
    conn.commit()
    return conn


class _Fake:
    def __init__(self):
        self.sent = None

    def _send(self, code, body, kind):
        self.sent = (code, body, kind)


def _call(**params):
    conn = _conn()
    real = db.connect
    db.connect = lambda *a, **k: conn                 # noqa: E731
    fake = _Fake()
    try:
        server.Handler._team(fake, {k: [v] for k, v in params.items()})
    finally:
        db.connect = real
    code, body, _kind = fake.sent
    return code, json.loads(body)


def test_the_schedule_names_every_season_and_opens_on_the_newest():
    sch = teamdex.season_schedule(_conn(), "nfl", "CHI")
    assert sch["seasons"] == [2026, 2025, 2024] and sch["season"] == 2026
    assert [g["period"] for g in sch["games"]] == ["001", "003", "005", "008"]


def test_one_season_on_request_and_an_unknown_one_is_empty_not_another():
    old = teamdex.season_schedule(_conn(), "nfl", "CHI", 2024)
    assert old["season"] == 2024 and len(old["games"]) == 1 and old["games"][0]["result"] == "W"
    assert old["seasons"] == [2026, 2025, 2024], "the chips stay the same whichever is shown"
    none = teamdex.season_schedule(_conn(), "nfl", "CHI", 2019)
    assert none == {"season": 2019, "seasons": [2026, 2025, 2024], "games": []}


def test_a_week_with_no_spread_posted_carries_no_line():
    g = {x["period"]: x for x in teamdex.season_schedule(_conn(), "nfl", "CHI")["games"]}
    assert g["003"]["line"] == 4.5, "a posted line, CHI at home"
    assert g["005"]["line"] is None and g["005"]["total"] == 49.5
    assert g["008"]["line"] is None and g["008"]["total"] is None


def test_the_endpoint_takes_a_season_and_can_answer_the_schedule_alone():
    code, out = _call(sport="nfl", team="CHI", season="2025", only="schedule")
    assert code == 200 and set(out) == {"sport", "team", "schedule"}, "one season's schedule, nothing else"
    assert out["schedule"]["season"] == 2025 and out["schedule"]["games"][0]["period"] == "019"
    code, full = _call(sport="nfl", team="CHI")
    assert code == 200 and full["schedule"]["season"] == 2026 and "profile" in full
    assert full["schedule"]["seasons"] == [2026, 2025, 2024]
    code, bad = _call(sport="nfl", team="CHI", season="20x6", only="schedule")
    assert code == 200 and bad["schedule"]["season"] == 2026, "a malformed season is ignored, not trusted"


def test_the_page_draws_the_chips_and_reads_one_season_at_a_time():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    chips = js[js.index("function teamSeasonChipsHTML"):js.index("function teamScheduleHTML")]
    assert 'data-team-season="${escapeAttr(String(y))}"' in chips and "seasons.length < 2" in chips
    load = js[js.index("async function teamLoadSeason"):js.index("function teamSeasonChipsHTML")]
    assert "&season=${encodeURIComponent(season)}&only=schedule" in load
    assert "if (st.schedCache[season]) return renderTeamPage();" in load, "a season read once is kept"
    assert "if (_teamState !== st || st.sport !== who[0] || st.team !== who[1]) return;" in load
    sched = js[js.index("function teamScheduleHTML"):js.index("function teamDepthHTML")]
    assert "const sch = teamSchedFor(d);" in sched and "${chips}" in sched
    assert 'if (seasonBtn) return teamLoadSeason(Number(seasonBtn.dataset.teamSeason));' in js
    assert "schedCache: same ? (_teamState.schedCache || {}) : {} };" in js, "a new team starts on its current season"


def test_weeks_read_as_numbers_and_playoff_weeks_by_name():
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    when = js[js.index("const NFL_ROUNDS"):js.index("function teamGameDate")]
    assert 'const NFL_ROUNDS = { 19: "Wild Card", 20: "Divisional", 21: "Conference", 22: "Super Bowl" };' in when
    assert "return `Wk ${wk}`;" in when and "Number(g.period)" in when


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
