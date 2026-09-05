"""Live football drives, from the shape the droplet actually returned.

espnprobe.py ran on 2026-09-05 during a live college game and printed
the structure of ESPN's summary payload. The fixture here is that
structure, key for key, including the two facts that decide the parser:
`drives.previous` contained the drive in progress as well as
`drives.current` (same id, same plays), and a drive's `team` dict has the
same fields the scoreboard's competitor `team` does. Top-level `plays`
and `scoringPlays` were ABSENT even live, so nothing reads them.

Every row is composed from numbers. A play's `text` and a drive's
`description` are ESPN's written account and are never read — the
fixture puts marker strings in both and asserts they never surface.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402

TEXT = "ESPN's own sentence describing the play"
DESC = "ESPN's drive summary sentence"


def _play(pid, seq, *, period=1, clock="12:34", down=1, dist=10, yl=25,
          yards=4, ptype="Rush", scoring=False, turnover=False,
          penalty=False, away=0, home=0):
    return {
        "id": pid, "sequenceNumber": str(seq),
        "period": {"number": period}, "clock": {"displayValue": clock},
        "start": {"down": down, "distance": dist, "yardLine": yl,
                  "yardsToEndzone": 100 - yl, "team": {"id": "61"}},
        "end": {"down": (down + 1) if down else None,
                "distance": max(dist - yards, 1) if dist else None,
                "yardLine": yl + yards, "yardsToEndzone": 100 - yl - yards,
                "downDistanceText": "2nd & 6 at UGA 29",
                "possessionText": "UGA 29", "shortDownDistanceText": "2nd & 6",
                "team": {"id": "61"}},
        "statYardage": yards, "type": {"abbreviation": "RUSH", "id": "5",
                                       "text": ptype},
        "scoringPlay": scoring, "isTurnover": turnover, "isPenalty": penalty,
        "awayScore": away, "homeScore": home, "priority": False,
        "teamParticipants": [{"id": "1", "order": 1, "team": {"id": "61"},
                              "type": "rusher"}],
        "text": TEXT, "wallclock": "2026-09-05T00:12:00Z",
        "modified": "2026-09-05T00:12",
    }


def _drive(did, plays, team=("UGA", "Georgia Bulldogs", "61"), yards=25,
           elapsed="1:52", offensive=None):
    abbr, name, tid = team
    return {
        "id": did, "description": DESC, "isScore": False,
        "offensivePlays": len(plays) if offensive is None else offensive,
        "plays": plays,
        "start": {"period": {"number": 1, "type": "quarter"},
                  "text": "15:00", "yardLine": 24},
        "team": {"abbreviation": abbr, "displayName": name, "id": tid,
                 "logos": [], "name": name.split()[-1],
                 "shortDisplayName": name.split()[0]},
        "timeElapsed": {"displayValue": elapsed}, "yards": yards,
    }


def _payload(dup_current_in_previous=True):
    """A finished first drive, then the drive in progress — which, as the
    probe showed, ALSO appears at the tail of `previous`."""
    d1 = _drive("40185666401", [
        _play("p1", 1, down=None, dist=None, ptype="Kickoff", yards=0),
        _play("p2", 2, yards=7),
        _play("p3", 3, down=2, dist=3, yards=3, ptype="Pass Reception"),
        _play("p4", 4, down=1, dist=10, yards=-2, ptype="Rush"),
        _play("p5", 5, down=2, dist=12, yards=0, ptype="Punt"),
    ], elapsed="2:31")
    cur = _drive("40185666402", [
        _play("p6", 6, period=1, clock="9:41", down=1, dist=10, yl=30,
              yards=24, ptype="Pass Reception"),
        _play("p7", 7, period=1, clock="9:02", down=1, dist=10, yl=54,
              yards=46, ptype="Pass Reception", scoring=True, away=0,
              home=7),
    ], team=("BAMA", "Alabama Crimson Tide", "333"), yards=70, elapsed="1:10")
    previous = [d1] + ([cur] if dup_current_in_previous else [])
    return {"drives": {"current": cur, "previous": previous},
            "header": {"id": "401856664"}, "boxscore": {"teams": []},
            "winprobability": []}


# --- the parser --------------------------------------------------------------
def test_the_current_drive_appearing_in_previous_is_not_printed_twice():
    """THE FACT THE PROBE SHOWED. `drives.current` and the last entry of
    `drives.previous` were the same drive. Concatenating them without
    this puts the drive in progress on the card twice."""
    rows = E.football_plays(_payload(dup_current_in_previous=True), "cfb",
                            limit=0)
    ids = [r["id"] for r in rows]
    assert ids == ["p1", "p2", "p3", "p4", "p5", "p6", "p7"], ids
    assert len(ids) == len(set(ids))


def test_a_payload_where_previous_excludes_current_still_reads_it():
    """The other reading of the same block: both must work, because the
    probe could only show one live game."""
    rows = E.football_plays(_payload(dup_current_in_previous=False), "cfb",
                            limit=0)
    assert [r["id"] for r in rows][-2:] == ["p6", "p7"], rows


def test_newest_last_and_capped():
    rows = E.football_plays(_payload(), "cfb", limit=3)
    assert [r["id"] for r in rows] == ["p5", "p6", "p7"], rows


def test_espns_prose_never_reaches_a_row():
    rows = E.football_plays(_payload(), "cfb", limit=0)
    flat = json.dumps(rows) + json.dumps(E.current_drive(_payload(), "cfb"))
    assert TEXT not in flat
    assert DESC not in flat
    assert "text" not in json.dumps(rows), "the key itself leaked"


def test_the_fields_the_card_composes_from():
    r = E.football_plays(_payload(), "cfb", limit=1)[0]
    assert r["kind"] == "football"
    assert r["period"] == 1 and r["clock"] == "9:02"
    assert r["down"] == 1 and r["distance"] == 10 and r["yard_line"] == 54
    assert r["yards"] == 46 and r["event"] == "Pass Reception"
    assert r["scoring"] is True and r["turnover"] is False
    assert (r["away_score"], r["home_score"]) == (0, 7)


def test_the_team_is_the_boards_own_key_not_espns_raw_string():
    """`_side_key` resolves a drive's team exactly as the scoreboard row
    resolves a competitor, so a play's team matches the card's home/away.
    College keeps the abbreviation and falls back to `espn:{id}`."""
    rows = E.football_plays(_payload(), "cfb", limit=0)
    assert rows[0]["team"] == "UGA"
    assert rows[-1]["team"] == "BAMA"
    noabbr = _payload()
    noabbr["drives"]["current"]["team"]["abbreviation"] = ""
    noabbr["drives"]["previous"][-1]["team"]["abbreviation"] = ""
    assert E.football_plays(noabbr, "cfb", limit=1)[0]["team"] == "espn:333"


def test_nfl_resolves_through_the_full_name_table():
    """NFL has not been probed live; the parser serves it off the same
    API, and its sides must be nflverse codes when it does."""
    pay = _payload()
    for d in [pay["drives"]["current"]] + pay["drives"]["previous"]:
        d["team"] = {"abbreviation": "WSH", "displayName": "Washington Commanders",
                     "id": "28"}
    assert E.football_plays(pay, "nfl", limit=1)[0]["team"] == "WAS"


def test_a_kickoff_has_no_down():
    r = E.football_plays(_payload(), "cfb", limit=0)[0]
    assert r["event"] == "Kickoff" and r["down"] is None


def test_a_payload_with_no_drives_yields_no_plays_not_a_crash():
    """The pre-game NFL, NBA and WNBA probes: no `drives` at all."""
    for pay in ({}, None, {"drives": None}, {"drives": {}},
                {"drives": {"previous": [], "current": None}},
                {"drives": "not a dict"}):
        assert E.football_plays(pay, "cfb") == []
        assert E.current_drive(pay, "cfb") is None


def test_the_current_drive_is_numbers_not_espns_sentence():
    d = E.current_drive(_payload(), "cfb")
    assert d == {"team": "BAMA", "plays": 2, "yards": 70, "elapsed": "1:10",
                 "start_yard_line": 24, "period": 1}, d


# --- the fetch ---------------------------------------------------------------
def test_the_summary_url_is_the_scoreboards_neighbour():
    from engine.sources.livescores import ESPN_SCOREBOARD
    assert set(E.ESPN_SUMMARY) == set(ESPN_SCOREBOARD)
    for lg, url in E.ESPN_SUMMARY.items():
        assert url.endswith("/summary"), (lg, url)
        assert url[:-len("summary")] == ESPN_SCOREBOARD[lg][:-len("scoreboard")]


def test_the_probe_and_the_parser_agree_on_the_url():
    import espnprobe
    assert espnprobe.SUMMARY == E.ESPN_SUMMARY


def test_the_live_cache_name_is_prunable_and_sends_no_agent():
    from engine.maintenance import PRUNABLE_CACHE_PREFIXES
    seen = {}

    def fake(url, name, ttl=None, timeout=45, user_agent=None):
        seen.update(url=url, name=name, ttl=ttl, ua=user_agent)
        return "{}"
    real = E.fetch_text
    E.fetch_text = fake
    try:
        E.fetch_summary("cfb", "401856664")
    finally:
        E.fetch_text = real
    assert seen["name"] == "espn_cfb_live_401856664.json"
    assert seen["name"].startswith(PRUNABLE_CACHE_PREFIXES), seen["name"]
    assert seen["ua"] is E.DEFAULT_AGENT, "a custom User-Agent gets a 403"
    assert seen["url"].endswith("/football/college-football/summary?event=401856664")
    assert seen["ttl"] == E.LIVE_TTL


def test_basketball_is_not_served_until_it_has_been_seen_live():
    assert set(E.FOOTBALL) == {"nfl", "cfb"}


# --- the build ---------------------------------------------------------------
def _games(n_live=2, n_other=1):
    out = []
    for i in range(n_live):
        out.append({"event_id": f"e{i}", "home": "UGA", "away": "BAMA",
                    "live": {"state": "live", "start_time": ""}})
    for i in range(n_other):
        out.append({"event_id": f"s{i}", "home": "LSU", "away": "OU",
                    "live": {"state": "scheduled", "start_time": ""}})
    return out


def _with_fetch(fn, games, league="cfb"):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, league)
    finally:
        E.fetch_summary = real


def test_only_live_football_games_are_fetched():
    asked = []

    def fn(league, eid, ttl=30):
        asked.append(eid)
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert asked == ["e0", "e1"], asked
    assert games[0]["plays"] and games[0]["drive"]["team"] == "BAMA"
    assert "plays" not in games[-1] and "drive" not in games[-1]
    assert "2 of 2 live game(s)" in note, note


def test_basketball_leagues_are_left_alone_with_a_note():
    asked = []

    def fn(league, eid, ttl=30):
        asked.append(eid)
        return _payload()
    games = _games()
    note = _with_fetch(fn, games, league="nba")
    assert asked == []
    assert "no play-by-play source yet" in note, note
    assert "plays" not in games[0]


def test_one_dead_feed_costs_that_card_its_plays_and_nothing_else():
    def fn(league, eid, ttl=30):
        if eid == "e0":
            raise RuntimeError("ESPN refused")
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert "plays" not in games[0] and games[0]["live"]["state"] == "live"
    assert games[1]["plays"]
    assert "1 feed(s) unreachable" in note, note


def test_past_the_cap_the_games_keep_their_scores_and_the_note_says_why():
    asked = []

    def fn(league, eid, ttl=30):
        asked.append(eid)
        return _payload()
    games = _games(n_live=B.PLAYS_MAX_GAMES + 3, n_other=0)
    note = _with_fetch(fn, games)
    assert len(asked) == B.PLAYS_MAX_GAMES, len(asked)
    assert "plays" in games[0]
    assert "plays" not in games[B.PLAYS_MAX_GAMES], "the cap did not hold"
    assert f"3 past the {B.PLAYS_MAX_GAMES}-game cap" in note, note


def test_no_games_in_progress_says_so():
    assert "no games in progress" in B.attach_plays(_games(n_live=0), "nfl")


def test_the_note_rides_on_the_published_file():
    src = (ROOT / "livescore_build.py").read_text()
    assert 'out["plays_note"] = attach_plays(games, league)' in src


# --- the page ----------------------------------------------------------------
def _fn(name):
    src = (ROOT / "web" / "js" / "app.js").read_text()
    i = src.index(f"function {name}(")
    return src[i:src.index("\nfunction ", i + 1)]


def test_the_card_draws_football_rows_from_the_numbers():
    body = _fn("playsHTML")
    assert 'p.kind === "football"' in body
    for field in ("p.period", "p.clock", "p.down", "p.distance", "p.yards",
                  "p.team", "p.turnover", "p.scoring"):
        assert field in body, field
    assert "p.text" not in body and "p.description" not in body
    assert "g.drive" in body, "the current drive line is never drawn"
    assert "${driveLine}" in body, "the drive line is built and never placed"


def test_mlb_rows_still_render_the_old_way():
    body = _fn("playsHTML")
    assert "p.batter" in body and "p.rbi" in body


def test_the_styles_exist():
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    assert ".lb-play.turnover" in css and ".lb-drive" in css


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
