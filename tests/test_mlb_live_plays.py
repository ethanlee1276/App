"""Live play-by-play on the MLB card.

Ethan, 2026-09-04: "if for the games we display live, are we able to get
live play by plays for all sports". MLB is where it starts, because
`engine/mlb/sources/pbp.py` has fetched this exact endpoint since the
pitch-level work went in — on a SEVEN-DAY cache, for modelling, and the
page never saw a play.

TWO THINGS THIS FILE IS REALLY ABOUT, both of which are quiet failures
rather than loud ones:

  * A live read must not poison the modelling cache. `fetch_playbyplay`
    holds a finished game for a week because "a completed game's pitches
    never change"; writing tonight's half-played payload to that name
    would have the velocity and times-through-order parsers model a
    starter off four innings, with nothing in the payload to say so.
  * The card composes its own sentence. The feed carries
    `result.description` — MLB's written account — and nothing here
    reads it. Same position the injuries page's news section settled on.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import live_build as LB                                       # noqa: E402
from engine.mlb.sources import pbp                            # noqa: E402


def _play(event, batter, *, inning=1, half="top", rbi=0, scoring=False,
          away=0, home=0, description="MLB's own words about the play"):
    return {
        "result": {"event": event, "eventType": event.lower().replace(" ", "_"),
                   "rbi": rbi, "awayScore": away, "homeScore": home,
                   "description": description},
        "about": {"inning": inning, "halfInning": half,
                  "isScoringPlay": scoring},
        "matchup": {"batter": {"fullName": batter},
                    "pitcher": {"fullName": "Zack Wheeler"}},
    }


def _payload(n=3):
    plays = [_play("Single", "Aaron Judge"),
             _play("Home Run", "Juan Soto", rbi=2, scoring=True, away=2),
             _play("Strikeout", "Giancarlo Stanton")][:n]
    # The at-bat in progress: same list, no result yet.
    plays.append({"result": {}, "about": {"inning": 1, "halfInning": "top"},
                  "matchup": {"batter": {"fullName": "Somebody Batting"}}})
    return {"allPlays": plays}


# --- the parser -------------------------------------------------------------
def test_the_at_bat_in_progress_is_not_a_play_yet():
    """It rides in the same list with no `result.event`. Emitting it puts
    an empty row at the top of the card every time somebody steps in."""
    got = pbp.recent_plays(_payload())
    assert [p["batter"] for p in got] == [
        "Aaron Judge", "Juan Soto", "Giancarlo Stanton"], got


def test_mlbs_own_prose_never_reaches_the_row():
    """The rights posture, asserted rather than intended."""
    got = pbp.recent_plays(_payload())
    assert "MLB's own words" not in json.dumps(got), got
    assert not any("description" in p for p in got), got


def test_the_fields_the_card_composes_from_are_all_there():
    got = pbp.recent_plays(_payload())[1]
    assert got["batter"] == "Juan Soto"
    assert got["event"] == "Home Run"
    assert got["rbi"] == 2
    assert got["scoring"] is True
    assert got["half"] == "T" and got["inning"] == 1
    assert got["away_score"] == 2 and got["home_score"] == 0


def test_newest_last_and_capped():
    got = pbp.recent_plays(_payload(), limit=2)
    assert len(got) == 2
    assert got[-1]["batter"] == "Giancarlo Stanton", got


def test_a_half_inning_it_cannot_name_is_blank_not_wrong():
    pay = {"allPlays": [_play("Single", "A", half="middle")]}
    assert pbp.recent_plays(pay)[0]["half"] == ""


def test_an_empty_or_broken_payload_is_no_plays_not_a_crash():
    for pay in ({}, None, {"allPlays": None}, {"allPlays": []}):
        assert pbp.recent_plays(pay) == []


# --- the cache separation ---------------------------------------------------
def test_the_live_read_uses_its_own_cache_name():
    """THE ONE THAT WOULD HAVE BEEN INVISIBLE. A partial payload written
    to `mlb_pbp_{pk}.json` is served to the velocity parsers as a
    finished game for the next seven days, and nothing in the payload
    says it is partial."""
    seen = {}

    def fake(url, name, ttl=900, timeout=30):
        seen["url"], seen["name"], seen["ttl"] = url, name, ttl
        return {"allPlays": []}
    was = pbp._get_json
    pbp._get_json = fake
    try:
        pbp.fetch_live_playbyplay(777)
        live = dict(seen)
        pbp.fetch_playbyplay(777)
        final = dict(seen)
    finally:
        pbp._get_json = was
    assert live["name"] != final["name"], live["name"]
    assert live["name"] == "mlb_pbp_live_777.json", live["name"]
    assert final["name"] == "mlb_pbp_777.json", final["name"]
    assert live["url"] == final["url"], "it is the same endpoint"
    assert live["ttl"] < final["ttl"], (live["ttl"], final["ttl"])


def test_the_live_cache_name_is_still_covered_by_the_prune_prefix():
    """`mlb_pbp_` is prunable because ~640 KB a game, ~150 a night, and
    nothing would ever have deleted one. The live name must not escape
    that by being new."""
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    assert "mlb_pbp_live_777.json".startswith(PRUNABLE_CACHE_PREFIXES)


# --- the build --------------------------------------------------------------
def _games(n_live=2, n_other=1):
    out = []
    for i in range(n_live):
        out.append({"game_pk": 100 + i, "home": "NYY", "away": "BOS",
                    "live": {"state": "live", "start_time": ""}})
    for i in range(n_other):
        out.append({"game_pk": 200 + i, "home": "LAD", "away": "SF",
                    "live": {"state": "scheduled", "start_time": ""}})
    return out


def _with_fetch(fn, games, **kw):
    import engine.mlb.sources.pbp as P
    real = P.fetch_live_playbyplay
    P.fetch_live_playbyplay = fn
    try:
        return LB.attach_plays(games, **kw)
    finally:
        P.fetch_live_playbyplay = real


def test_only_games_in_progress_are_fetched():
    """A scheduled game has no plays and a finished one is not what
    anybody is watching. This is what keeps the cost bounded."""
    asked = []

    def fn(pk, ttl=30):
        asked.append(pk)
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert sorted(asked) == [100, 101], asked
    assert games[0]["plays"], games[0]
    assert "plays" not in games[-1], games[-1]
    assert "2 of 2 live game(s)" in note, note


def test_no_games_in_progress_says_so_rather_than_nothing():
    note = LB.attach_plays(_games(n_live=0))
    assert "no games in progress" in note, note


def test_one_dead_feed_costs_that_card_its_plays_and_nothing_else():
    def fn(pk, ttl=30):
        if pk == 100:
            raise RuntimeError("statsapi refused")
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert "plays" not in games[0], games[0]
    assert games[1]["plays"], games[1]
    assert games[0]["live"]["state"] == "live", "the card lost its score"
    assert "1 feed(s) unreachable" in note, note


def test_past_the_cap_the_games_keep_their_scores_and_the_note_says_why():
    """An empty play list because we ran out of budget and one because
    the game has not thrown a pitch are different facts."""
    asked = []

    def fn(pk, ttl=30):
        asked.append(pk)
        return _payload()
    games = _games(n_live=LB.PLAYS_MAX_GAMES + 2, n_other=0)
    note = _with_fetch(fn, games)
    assert "plays" in games[0]
    # THE FIRST LIVE GAME PAST THE CAP, not games[-1]. The first cut of
    # this asserted on the last element of a list whose tail was the
    # SCHEDULED game — which never gets plays whatever the cap does — so
    # deleting the cap entirely left the test green. Caught by mutation,
    # which is the only thing that would have caught it.
    assert "plays" not in games[LB.PLAYS_MAX_GAMES], "the cap did not hold"
    assert len(asked) == LB.PLAYS_MAX_GAMES, len(asked)
    assert f"2 past the {LB.PLAYS_MAX_GAMES}-game cap" in note, note


def test_the_note_rides_on_the_published_file():
    src = (ROOT / "live_build.py").read_text()
    assert 'out["plays_note"] = attach_plays(games)' in src, \
        "the census is computed and thrown away"


# --- the page ---------------------------------------------------------------
def _app():
    return (ROOT / "web" / "js" / "app.js").read_text()


def test_the_card_draws_the_plays():
    src = _app()
    assert "function playsHTML(" in src
    i = src.index("function playsHTML(")
    body = src[i:src.index("\nfunction ", i + 1)]
    for field in ("p.batter", "p.event", "p.rbi", "p.half", "p.inning"):
        assert field in body, field
    assert "p.description" not in body, "the card is reading MLB's prose"
    assert "${playsHTML(g)}" in src, "it is defined and never called"


def test_a_card_with_no_plays_draws_nothing_at_all():
    """Football and basketball cards go through the same renderer, and an
    empty strip with a border on it is a visible bug on every one."""
    src = _app()
    i = src.index("function playsHTML(")
    body = src[i:src.index("\nfunction ", i + 1)]
    assert 'if (!plays.length) return "";' in body, body[:300]


def test_the_style_exists_so_the_strip_is_not_unstyled_text():
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    for cls in (".lb-plays", ".lb-play", ".lb-inn", ".lb-what"):
        assert cls in css, cls


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
