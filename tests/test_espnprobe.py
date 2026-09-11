"""Look at the payload before parsing it.

Ethan, 2026-09-04, asked for live play-by-play in every sport. MLB
shipped, because `engine/mlb/sources/pbp.py` had fetched that endpoint
for a year and the repo carries a real fixture of it. The other four
would come from ESPN's `summary?event=`, which this repo already fetches
(`nflpreseason.fetch_boxscore`, `espnhoops.fetch_summary`) and has never
looked inside past the box score. Nothing here records the shape of its
plays, and neither the agent sandbox's proxy nor WebFetch can reach
site.api.espn.com to find out.

Writing a parser against a REMEMBERED shape is how `g["home_id"]` and
`g["away_id"]` — two fields that do not exist — reached a college
headshot cut, on this same day. So this probe goes first.

THE OTHER HALF OF ITS JOB is not printing ESPN's prose. A play's `text`
is their written account of the game; the probe reports `str(29)` and
never the sentence, the same position `pbp.recent_plays` takes by
composing from `event` and `batter` rather than copying `description`.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import espnprobe as P                                        # noqa: E402


PLAY = {"period": {"number": 2}, "clock": {"displayValue": "7:12"},
        "text": "Some written account of what happened on the play",
        "scoringPlay": False, "statYardage": 7, "awayScore": 10,
        "homeScore": 14, "id": "4017729361"}


def _payload():
    return {"drives": {"previous": [{"id": "1", "plays": [PLAY]}]},
            "header": {"id": "401"}, "boxscore": {"teams": []}}


def test_a_plays_text_is_never_printed():
    """THE RIGHTS POSTURE, asserted rather than intended. A length is
    enough to tell a parser-writer the field is prose."""
    out = "\n".join(P.describe(_payload(), max_depth=6))
    assert "Some written account" not in out, out
    assert f"text: str({len(PLAY['text'])})" in out, out


def test_numbers_and_booleans_print_their_value():
    """A parser-writer needs to know `period.number` is 2 and not "2nd" —
    that is the whole reason to look."""
    out = "\n".join(P.describe(_payload(), max_depth=6))
    assert "statYardage: int=7" in out, out
    assert "scoringPlay: bool=False" in out, out
    assert "number: int=2" in out, out


def test_none_is_reported_as_none_not_as_a_missing_key():
    assert P._scalar(None) == "None"
    out = "\n".join(P.describe({"a": None}))
    assert "a: None" in out, out


def test_list_lengths_are_reported():
    out = "\n".join(P.describe({"plays": [PLAY, PLAY, PLAY]}, max_depth=1))
    assert "plays: list(3)" in out, out


def test_depth_is_bounded_and_says_what_it_stopped_on():
    """A summary payload is large. Truncating silently would hide the
    very block this exists to find, so the cut names the keys."""
    deep = {"a": {"b": {"c": {"d": {"e": 1}}}}}
    out = "\n".join(P.describe(deep, max_depth=2))
    assert "...1 keys: c" in out, out
    assert "e: int=1" not in out, out


def test_an_empty_container_is_not_an_error():
    for pay in ({}, {"drives": {}}, {"plays": []}, []):
        P.describe(pay)


def test_every_league_the_scoreboards_cover_has_a_summary_url():
    """A probe that cannot ask about college is no use — college is the
    league whose live board was worst off."""
    from engine.sources.livescores import ESPN_SCOREBOARD
    assert set(P.SUMMARY) == set(ESPN_SCOREBOARD), (
        sorted(P.SUMMARY), sorted(ESPN_SCOREBOARD))
    for lg, url in P.SUMMARY.items():
        assert url.endswith("/summary"), (lg, url)
        assert url.startswith("https://site.api.espn.com/"), (lg, url)
        # Same league path as the scoreboard, one segment different.
        assert url[:-len("summary")] == \
            ESPN_SCOREBOARD[lg][:-len("scoreboard")], lg


def test_the_blocks_it_reports_on_include_the_ones_being_hunted():
    for key in ("drives", "plays", "scoringPlays"):
        assert key in P.WANTED, key


def test_it_prefers_a_game_in_progress():
    """`drives.current` and a live situation only exist while the clock
    is running. Probing a final answers a question nobody asked."""
    board = {"events": [
        {"id": "1", "status": {"type": {"state": "post"}}},
        {"id": "2", "status": {"type": {"state": "in"}}},
        {"id": "3", "status": {"type": {"state": "pre"}}}]}
    was = P._get
    P._get = lambda url: board
    try:
        assert P.pick_event("nfl") == ("2", "in")
    finally:
        P._get = was


def test_with_nothing_live_it_still_answers_and_says_the_state():
    board = {"events": [{"id": "9", "status": {"type": {"state": "pre"}}}]}
    was = P._get
    P._get = lambda url: board
    try:
        assert P.pick_event("cfb") == ("9", "pre")
    finally:
        P._get = was


def test_a_finished_game_can_be_asked_for_and_the_date_reaches_the_url():
    """The WNBA probe ran pre-game three times running; a final keeps its
    play-by-play, so `--prefer post --date YYYYMMDD` answers the shape
    question without anyone waiting for a tip-off."""
    seen = {}
    board = {"events": [
        {"id": "1", "status": {"type": {"state": "pre"}}},
        {"id": "2", "status": {"type": {"state": "post"}}}]}

    def fake(url):
        seen["url"] = url
        return board
    was = P._get
    P._get = fake
    try:
        assert P.pick_event("wnba", "post", "20260904") == ("2", "post")
        assert seen["url"].endswith("/basketball/wnba/scoreboard?dates=20260904")
        assert P.pick_event("wnba") == ("1", "pre"), "the default still prefers live, then first"
        assert P.pick_event("wnba", "any") == ("1", "pre")
    finally:
        P._get = was


def test_an_empty_scoreboard_is_a_named_exit_not_an_index_error():
    was = P._get
    P._get = lambda url: {"events": []}
    try:
        try:
            P.pick_event("nba")
        except SystemExit as exc:
            assert "lists no events" in str(exc), exc
        else:
            raise AssertionError("an empty scoreboard did not exit cleanly")
    finally:
        P._get = was


def test_the_probe_sends_no_custom_user_agent():
    """403 on all four leagues from the droplet, 2026-09-04. fetch.py
    measured the same thing a month earlier: a custom string trips ESPN,
    urllib's own default does not. The probe must do what every working
    ESPN call here does — send nothing."""
    import ast
    import inspect
    import textwrap
    # EXECUTABLE STATEMENTS ONLY. The first draft read the raw source and
    # went red on the docstring that explains why the header is absent —
    # the fourth self-matching needle this session. A structural claim
    # about what a function DOES is not answerable by what is written
    # about it; `ast.unparse` drops comments and the docstring is dropped
    # by hand, so the words below can only appear by being code.
    tree = ast.parse(textwrap.dedent(inspect.getsource(P._get)))
    body = tree.body[0].body
    if (body and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)):
        body = body[1:]
    code = "\n".join(ast.unparse(st) for st in body)
    assert "headers" not in code, code
    assert "Request(url)" in code, code


def test_no_test_in_this_file_can_reach_the_network():
    """Every test above stubs `_get`. The guard is built from pieces so
    it cannot match its own literal."""
    body = Path(__file__).read_text()
    needle = "P." + "_get = lambda"
    assert body.count(needle) == 3, body.count(needle)
    assert body.count("P." + "_get = fake") == 1
    # BUILT FROM PIECES, BOTH OF THEM. The first draft asserted the
    # opener's name was absent by writing that name out — so the guard
    # matched itself and failed. The SECOND draft split the literal and
    # then quoted the original in this very comment, which matched too.
    # A guard that searches its own file cannot name what it forbids,
    # anywhere in the file, comments included.
    assert ("url" + "open") not in body


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
