"""Live basketball plays, from the shape the droplet actually returned.

espnprobe.py could not catch a WNBA game in progress — four runs landed
between games — so `--prefer post --date` read the Aug 30 final (event
401857186) and printed what a basketball summary keeps: a top-level
`plays` list of 392, each play with `team{id}`, `participants[{athlete
{id}}]`, `type{id, text}`, `period{number}`, `clock{displayValue}`,
`scoringPlay`, `shootingPlay`, `scoreValue`, `pointsAttempted`, the
running score, and two prose fields. No `drives`, no `scoringPlays`.

The fixture here is that structure, key for key. The two lookups the
parser needs — a team id to the card's side, an athlete id to a name —
come from the scoreboard's competitor ids and from the box-score read
`espnhoops.parse_summary` has built the hoops boards from for weeks,
so nothing here is read off a block that has not been looked at.

Every row is composed from numbers and the type label. A play's `text`
and `shortDescription` are ESPN's written account and are never read —
the fixture puts marker strings in both and asserts they never surface.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import livescore_build as B                                  # noqa: E402
from engine.sources import espnplays as E                    # noqa: E402

TEXT = "ESPN's own sentence describing the play"
SHORT = "ESPN's shorter sentence"

LV, IND = "14", "5"                 # ESPN team ids, as the scoreboard has them
WILSON, CLARK = "2529185", "4433403"


def _play(pid, seq, *, period=1, clock="9:41", team=LV, parts=(WILSON,),
          ptype="Jump Shot", scoring=False, shot=True, value=0,
          attempted=2, away=0, home=0):
    return {
        "id": pid, "sequenceNumber": str(seq),
        "period": {"number": period, "displayValue": "1st Quarter"},
        "clock": {"displayValue": clock},
        "team": {"id": team} if team else {},
        "participants": [{"athlete": {"id": a}} for a in parts],
        "type": {"id": "558", "text": ptype},
        "scoringPlay": scoring, "shootingPlay": shot,
        "scoreValue": value, "pointsAttempted": attempted,
        "awayScore": away, "homeScore": home,
        "coordinate": {"x": 25, "y": 10},
        "shortDescription": SHORT, "text": TEXT,
        "wallclock": "2026-08-30T19:12:00Z",
    }


def _box_team(tid, abbr, name, athletes):
    """`boxscore.players[]` as `espnhoops.parse_summary` reads it."""
    return {"team": {"id": tid, "abbreviation": abbr, "displayName": name},
            "statistics": [{"names": ["MIN", "PTS"],
                            "athletes": [{"athlete": {"id": aid,
                                                      "displayName": nm},
                                          "stats": ["30", "22"]}
                                         for aid, nm in athletes]}]}


def _payload(plays=None):
    plays = plays if plays is not None else [
        _play("p1", 1, ptype="Jumpball", parts=(WILSON, CLARK, WILSON),
              shot=False, attempted=0, team=""),
        _play("p2", 2, clock="9:41", scoring=True, value=2, away=0, home=2),
        _play("p3", 3, clock="9:20", team=IND, parts=(CLARK,),
              attempted=3, away=0, home=2),
        _play("p4", 4, clock="9:18", ptype="Defensive Rebound", shot=False,
              attempted=0, away=0, home=2),
        _play("p5", 5, clock="9:02", ptype="Free Throw", scoring=True,
              value=1, attempted=1, away=0, home=3),
        _play("p6", 6, period=5, clock="0:41", team=IND, parts=(CLARK,),
              ptype="Three Point Jump Shot", scoring=True, value=3,
              attempted=3, away=88, home=90),
    ]
    return {"plays": plays,
            "boxscore": {"players": [
                _box_team(LV, "LV", "Las Vegas Aces", [(WILSON, "A'ja Wilson")]),
                _box_team(IND, "IND", "Indiana Fever", [(CLARK, "Caitlin Clark")]),
            ], "teams": []},
            "header": {"id": "401857186"}, "winprobability": []}


SIDES = {LV: "LVA", IND: "IND"}      # what the scoreboard row resolved to


# --- the parser --------------------------------------------------------------
def test_newest_last_and_capped():
    rows = E.hoops_plays(_payload(), "wnba", limit=3, sides=SIDES)
    assert [r["id"] for r in rows] == ["p4", "p5", "p6"], rows
    assert [r["id"] for r in E.hoops_plays(_payload(), "wnba", limit=0)] \
        == ["p1", "p2", "p3", "p4", "p5", "p6"]


def test_espns_prose_never_reaches_a_row():
    rows = E.hoops_plays(_payload(), "wnba", limit=0, sides=SIDES)
    flat = json.dumps(rows)
    assert TEXT not in flat
    assert SHORT not in flat
    assert "text" not in flat, "the key itself leaked"
    assert "shortDescription" not in flat


def test_the_fields_the_card_composes_from():
    r = E.hoops_plays(_payload(), "wnba", limit=1, sides=SIDES)[0]
    assert r["kind"] == "hoops"
    assert r["period"] == 5 and r["clock"] == "0:41"
    assert r["team"] == "IND" and r["player"] == "Caitlin Clark"
    assert r["event"] == "Three Point Jump Shot"
    assert r["scoring"] is True and r["shot"] is True
    assert r["points"] == 3 and r["points_attempted"] == 3
    assert (r["away_score"], r["home_score"]) == (88, 90)


def test_a_miss_is_a_shot_that_scored_nothing():
    rows = E.hoops_plays(_payload(), "wnba", limit=0, sides=SIDES)
    miss = rows[2]
    assert miss["id"] == "p3" and miss["shot"] is True
    assert miss["scoring"] is False and miss["points"] == 0
    assert miss["points_attempted"] == 3
    reb = rows[3]
    assert reb["event"] == "Defensive Rebound" and reb["shot"] is False


def test_the_team_is_the_scoreboards_side_key_looked_up_by_id():
    """A play carries `team{id}` and nothing else. The scoreboard row
    already resolved that id into the card's own key — WNBA goes through
    `WNBA_TEAM_ABBR`, so ESPN's LV is the board's LVA — and the play
    takes the same answer, so it matches the card's home/away."""
    rows = E.hoops_plays(_payload(), "wnba", limit=0, sides=SIDES)
    assert rows[1]["team"] == "LVA"
    assert rows[2]["team"] == "IND"
    assert rows[0]["team"] == "", "a jump ball has no team and says so"


def test_a_side_the_scoreboard_did_not_name_is_kept_as_espn_id():
    """Not dropped: a play with a team is a fact even when the name is
    not to hand, and `espn:{id}` is the same spelling the college board
    uses for a school with no abbreviation."""
    pay = _payload()
    pay["boxscore"] = {"players": []}
    rows = E.hoops_plays(pay, "wnba", limit=0, sides={LV: "LVA"})
    assert rows[1]["team"] == "LVA"
    assert rows[2]["team"] == f"espn:{IND}"


def test_the_box_score_maps_a_side_when_the_scoreboard_cannot():
    """The fallback: `boxscore.players[].team` resolved through the same
    `_side_key` the scoreboard uses. The scoreboard's answer wins when
    both know the id."""
    from engine.sources.livescores import _side_key
    rows = E.hoops_plays(_payload(), "wnba", limit=0)
    want = _side_key({"id": LV, "abbreviation": "LV",
                      "displayName": "Las Vegas Aces"}, "wnba")
    assert want == "LVA"
    assert rows[1]["team"] == want
    rows = E.hoops_plays(_payload(), "wnba", limit=0, sides={LV: "HOME"})
    assert rows[1]["team"] == "HOME", "the scoreboard's key did not win"


def test_the_player_is_the_first_participant_named_by_the_box_score():
    rows = E.hoops_plays(_payload(), "wnba", limit=0, sides=SIDES)
    assert rows[1]["player"] == "A'ja Wilson"
    assert rows[0]["player"] == "A'ja Wilson", "the first of three, on a jump ball"
    pay = _payload([_play("x", 1, parts=("999999",))])
    assert E.hoops_plays(pay, "wnba")[0]["player"] == "", \
        "an id the box score does not carry is blank, not invented"
    pay = _payload([_play("y", 1, parts=())])
    assert E.hoops_plays(pay, "wnba")[0]["player"] == ""


def test_a_play_seen_twice_prints_once():
    p = _play("dup", 1)
    rows = E.hoops_plays(_payload([p, dict(p), _play("z", 2)]), "wnba")
    assert [r["id"] for r in rows] == ["dup", "z"], rows


def test_a_payload_with_no_plays_yields_no_rows_not_a_crash():
    """The four pre-game WNBA probes: no `plays` at all. And a football
    payload, which has `drives` and no `plays`, reads as empty here."""
    for pay in ({}, None, {"plays": None}, {"plays": {}}, {"plays": "x"},
                {"plays": []}, {"drives": {"current": {}, "previous": []}},
                {"plays": [None, "x", 3]}):
        assert E.hoops_plays(pay, "wnba") == [], pay


def test_a_basketball_payload_gives_football_nothing_and_vice_versa():
    assert E.football_plays(_payload(), "wnba") == []
    assert E.current_drive(_payload(), "wnba") is None


def test_the_leagues_each_parser_serves():
    assert set(E.FOOTBALL) == {"nfl", "cfb"}
    assert set(E.HOOPS) == {"nba", "wnba"}
    assert not set(E.FOOTBALL) & set(E.HOOPS)


# --- the scoreboard carries the ids -------------------------------------------
def _board(state="in"):
    return {"events": [{
        "id": "401857186", "date": "2026-08-30T19:00Z",
        "status": {"type": {"state": state, "shortDetail": "Final"},
                   "period": 2, "displayClock": "5:00"},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "40",
             "team": {"id": LV, "abbreviation": "LV",
                      "displayName": "Las Vegas Aces"}},
            {"homeAway": "away", "score": "38",
             "team": {"id": IND, "abbreviation": "IND",
                      "displayName": "Indiana Fever"}}]}]}]}


def test_the_scoreboard_row_keeps_espns_team_ids():
    from engine.sources.livescores import parse_espn_rows
    r = parse_espn_rows(_board(), "wnba")[0]
    assert (r["home"], r["away"]) == ("LVA", "IND")
    assert (r["home_id"], r["away_id"]) == (LV, IND)
    g = B._row(r)
    assert (g["home_id"], g["away_id"]) == (LV, IND)


def test_a_row_without_ids_writes_no_id_keys():
    """Same rule as `yard_line`: absent, not null, so the reader can tell
    "not given" from "given as nothing"."""
    from engine.sources.livescores import parse_espn_rows
    board = _board()
    for c in board["events"][0]["competitions"][0]["competitors"]:
        c["team"].pop("id")
    g = B._row(parse_espn_rows(board, "wnba")[0])
    assert "home_id" not in g and "away_id" not in g, g


# --- the build ---------------------------------------------------------------
def _games(n_live=2, n_other=1):
    out = []
    for i in range(n_live):
        out.append({"event_id": f"e{i}", "home": "LVA", "away": "IND",
                    "home_id": LV, "away_id": IND,
                    "live": {"state": "live", "start_time": ""}})
    for i in range(n_other):
        out.append({"event_id": f"s{i}", "home": "NY", "away": "CON",
                    "live": {"state": "scheduled", "start_time": ""}})
    return out


def _with_fetch(fn, games, league="wnba"):
    real = E.fetch_summary
    E.fetch_summary = fn
    try:
        return B.attach_plays(games, league)
    finally:
        E.fetch_summary = real


def test_live_hoops_games_are_fetched_and_carry_plays_but_no_drive():
    asked = []

    def fn(league, eid, ttl=30):
        asked.append((league, eid))
        return _payload()
    games = _games()
    note = _with_fetch(fn, games)
    assert asked == [("wnba", "e0"), ("wnba", "e1")], asked
    assert len(games[0]["plays"]) == B.PLAYS_PER_GAME
    assert games[0]["plays"][-1]["kind"] == "hoops"
    assert "drive" not in games[0], "basketball has no drive line"
    assert "plays" not in games[-1]
    assert "plays: 2 of 2 live game(s)" in note, note


def test_the_sides_come_from_the_games_own_scoreboard_ids():
    """With NO box score to fall back on, so only the scoreboard's ids
    can have named the sides — otherwise a build that forgot to pass
    them would pass this test on the fallback."""
    bare_box = _payload()
    bare_box["boxscore"] = {"players": []}
    games = _games()
    _with_fetch(lambda league, eid, ttl=30: bare_box, games)
    teams = {r["team"] for r in games[0]["plays"] if r["team"]}
    assert teams == {"LVA", "IND"}, teams
    # Without ids on the row the box score still names the sides.
    bare = _games()
    for g in bare:
        g.pop("home_id", None); g.pop("away_id", None)
    _with_fetch(lambda league, eid, ttl=30: _payload(), bare)
    assert {r["team"] for r in bare[0]["plays"] if r["team"]} == {"LVA", "IND"}


def test_a_league_with_no_source_is_left_alone_with_a_note():
    asked = []

    def fn(league, eid, ttl=30):
        asked.append(eid)
        return _payload()
    games = _games()
    note = _with_fetch(fn, games, league="ufc")
    assert asked == []
    assert "no play-by-play source yet" in note, note
    assert "plays" not in games[0]


def test_no_hoops_game_in_progress_names_the_noun():
    assert "no plays fetched" in B.attach_plays(_games(n_live=0), "nba")
    assert "no drives fetched" in B.attach_plays(_games(n_live=0), "nfl")


# --- the probe ---------------------------------------------------------------
def test_the_probe_can_walk_to_the_blocks_that_name_the_ids():
    import espnprobe as P
    pay = _payload()
    assert P._walk(pay, "boxscore.players") is pay["boxscore"]["players"]
    # A list on the way is entered at its first item, or the index named.
    assert P._walk(pay, "boxscore.players.team")["id"] == LV
    assert P._walk(pay, "boxscore.players.1.team")["id"] == IND
    assert P._walk(pay, "plays.5")["id"] == "p6"
    assert P._walk(pay, "plays.99") is None
    assert P._walk(pay, "header.competitions") is None, "absent is None, not a crash"
    assert P._walk(pay, "") is pay
    # And what it prints is still shape, never prose.
    out = "\n".join(P.describe(P._walk(pay, "plays.1"), max_depth=3))
    assert TEXT not in out and f"text: str({len(TEXT)})" in out, out


def test_the_probe_offers_the_flag():
    src = (ROOT / "espnprobe.py").read_text()
    assert '"--block"' in src
    assert "_walk(payload, args.block)" in src


# --- the page ----------------------------------------------------------------
def _fn(name):
    src = (ROOT / "web" / "js" / "app.js").read_text()
    i = src.index(f"function {name}(")
    return src[i:src.index("\nfunction ", i + 1)]


def test_the_card_draws_hoops_rows_from_the_numbers():
    body = _fn("playsHTML")
    assert 'p.kind === "hoops"' in body
    i = body.index("const hoopsRow")
    hoops = body[i:body.index("const d = g.drive", i)]
    for field in ("p.period", "p.clock", "p.team", "p.player", "p.event",
                  "p.scoring", "p.points", "p.shot"):
        assert field in hoops, field
    assert "OT" in hoops, "a fifth period is overtime, not Q5"
    assert "p.text" not in body and "p.shortDescription" not in body


def test_the_miss_style_exists():
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    assert ".lb-play .lb-miss" in css


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
