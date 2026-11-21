"""The tournament race reads this week's poll (USEREYES1, 18 November 2026).

The college race page put "#7" beside both Texas and UCLA, "#4" beside
Virginia and UConn and "#16" beside Alabama and Texas Tech, with nobody at
#3, #6 or #9. Each school's rank was read off its latest game, and the poll
comes out on Monday: a school that last played on Sunday still carried the
week before's rank, so two weeks' polls sat side by side. What these hold:

  * the build reads ESPN's own poll (the AP Top 25, the coaches' poll when
    the AP's is missing), keyed by the scoreboard's codes, a tie in the
    voting kept as the poll prints it;
  * without it the scoreboard stands in, each school's rank read off its
    NEXT game (the current poll) and off its latest only when it has none
    left; a next game that shows a school unranked drops it, and the
    tournament's seeds are never read as a poll;
  * the page's rows carry the poll's ranks and say whose they are.

    python3 tests/test_the_race_reads_this_weeks_poll.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import ncaarace as NR                             # noqa: E402
from engine.sources import cbbespn                            # noqa: E402


def _poll(kind, name, rows):
    return {"type": kind, "name": name, "date": "2026-11-16T08:00Z",
            "ranks": [{"current": n, "team": team} for n, team in rows]}


def test_the_ap_poll_is_read_and_a_tie_is_kept():
    ap = _poll("ap", "AP Top 25", [(1, {"abbreviation": "FLA", "conferenceId": "23"}),
                                   (2, {"abbreviation": "MSU", "conferenceId": "7"}),
                                   (7, {"abbreviation": "TEX", "conferenceId": "23"}),
                                   (7, {"abbreviation": "UCLA", "conferenceId": "7"}),
                                   (26, {"abbreviation": "XAV", "conferenceId": "4"})])
    coaches = _poll("usa", "Coaches Poll", [(1, {"abbreviation": "DUKE", "conferenceId": "2"})])
    got = cbbespn.parse_rankings({"rankings": [coaches, ap]})
    assert got == {"name": "AP Top 25", "date": "2026-11-16",
                   "ranks": {"FLA": 1, "MSU": 2, "TEX": 7, "UCLA": 7}}, got
    assert cbbespn.parse_rankings({"rankings": [coaches]})["ranks"] == {"DUKE": 1}
    assert cbbespn.parse_rankings({"rankings": [_poll("", "Some Other Poll", [(1, {"abbreviation": "X"})])]}) == {}
    assert cbbespn.parse_rankings({}) == {} and cbbespn.parse_rankings(None) == {}
    # A school the poll names without its conference keeps ESPN's code.
    bare = cbbespn.parse_rankings({"rankings": [_poll("ap", "AP Top 25", [(3, {"abbreviation": "ZZQ", "id": "999999"})])]})
    assert bare["ranks"] == {"ZZQ": 3}
    assert cbbespn.RANKINGS.endswith("/basketball/mens-college-basketball/rankings")


def _g(date, home, away, hseed=None, aseed=None, st=2):
    return {"date": date, "home": home, "away": away, "hseed": hseed, "aseed": aseed, "st": st}


def test_without_the_poll_each_school_is_ranked_off_its_next_game():
    today = "2026-11-18"
    games = [
        _g("2026-11-15", "TEX", "A", 7, None),       # Sunday: last week's #7
        _g("2026-11-20", "TEX", "B", 9, None),       # Friday: this week's #9
        _g("2026-11-17", "UCLA", "C", 7, None),      # Tuesday: this week's #7
        _g("2026-11-14", "UVA", "D", 3, None),       # no game left: its latest
        _g("2026-11-13", "BAY", "E", 22, None),      # ranked last week,
        _g("2026-11-19", "F", "BAY", None, None),    # unranked on its next game
        _g("2026-11-12", "HB", "G", 99, None),       # hoopR's unranked 99
        _g("2026-11-21", "SEED", "H", 1, 16, st=3),  # a tournament seed is no poll
    ]
    assert NR.poll_ranks(games, today) == {"TEX": 9, "UCLA": 7, "UVA": 3}
    # ESPN's poll, when the build read it, is the answer outright.
    assert NR.poll_ranks(games, today, {"TEX": 6, "UCLA": 7, "BAD": 40}) == {"TEX": 6, "UCLA": 7}


def test_the_page_carries_the_polls_ranks_and_says_whose():
    import test_the_ncaa_tournament_race as T
    games = T.season()
    poll = {"name": "AP Top 25", "date": "2027-01-18", "ranks": {"T000": 3, "T001": 1}}
    out = NR.build(games, T.ratings(games), T.TODAY, sims=40, seed=5, poll=poll)
    rows = {r["team"]: r for r in out["teams"]}
    assert rows["T000"]["rank"] == 3 and rows["T001"]["rank"] == 1
    assert all(r["rank"] is None for t, r in rows.items() if t not in poll["ranks"])
    assert out["poll"] == {"name": "AP Top 25", "date": "2027-01-18"}
    bare = NR.build(games, T.ratings(games), T.TODAY, sims=40, seed=5)
    assert bare["poll"] == {"name": "the scoreboard's", "date": ""}


def test_the_build_reads_the_poll_and_fingerprints_it():
    src = (ROOT / "engine" / "ncaarace.py").read_text(encoding="utf-8")
    pub = src[src.index("def publish("):]
    assert "poll = cbbespn.parse_rankings(cbbespn.fetch_rankings())" in pub and "if fetch is None:" in pub
    assert "racecache.key(\"ncaa_race\", SIMS, day.isoformat(), games, ratings, poll," in pub
    assert "out = build(games, ratings, day.isoformat(), names=names, poll=poll)" in pub
    # The page names the poll its "#" comes from (and says nothing for the scoreboard's).
    js = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
    assert "the # beside a school is its place in the ${escapeHtml(pn)}" in js
    assert "pn && pn !== \"the scoreboard's\"" in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
