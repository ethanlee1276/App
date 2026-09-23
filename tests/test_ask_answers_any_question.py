"""Ask Qellys answers any question, whatever league is open and whoever plays tonight.

Ethan, 2026-09-23: "the ai bot is only responding for [whatever] sport
you have selected. It should work for any question no matter what sport
is selected. And it should also be able [to] pull up any player data.
The lions are playing the Jets this week and I asked it about how the
lions have done against the packers and it wouldn't answer since the
lions play the Jets this week. It should answer any question no matter
the team schedule or player schedule."

What is pinned here (engine/askbot.py):

  * EVERY LEAGUE'S BOARD rides along, and the rows a question names are
    found on whichever board they are on, with their league;
  * THREE LOOKUPS read the history database the Teams and Players pages
    read: `team_history` (his own question — the Lions and the Packers,
    with the Lions playing the Jets tonight), `player_history` (any
    player, any league, misspelled or not) and `tonight_board`;
  * THE LOOP IS CAPPED: rounds, lookups and the size of each answer, and
    the last round is told it may not look anything else up;
  * a lookup never raises, a missing database is never created, and
    every round's tokens reach the usage log.

Every fixture is built in a temp directory; no test reads the box's
history, rosters or fighter dossiers, and no test reaches the network.
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                # noqa: E402
from engine import db as _db                                   # noqa: E402
from engine import explainer as EX                             # noqa: E402
from engine import statlogs                                    # noqa: E402

_TMP = Path(tempfile.mkdtemp())
AB.CACHE_PATH = _TMP / "ask_cache.json"
AB.USAGE_PATH = _TMP / "ask_usage.json"
AB.UFC_PATH = str(_TMP / "no_fighters.json")
AB.ROSTER_DIR = str(_TMP / "rosters")
os.makedirs(AB.ROSTER_DIR, exist_ok=True)

APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()
SERVER = (ROOT / "server.py").read_text()


def _history():
    """Four Lions-Packers meetings across two seasons, a Lions-Jets game,
    a Lions-Bears game, Jahmyr Gibbs's logs in all of them, and a Yankee."""
    path = _TMP / "history.db"
    if path.exists():
        return path
    conn = _db.connect(str(path))
    games = [  # season, week, home, away, home score, away score, HOME spread, total
        (2025, "017", "DET", "GB", 31, 24, -6.5, 51.5),   # Lions by 7, laying 6.5: cover, over
        (2025, "009", "GB", "DET", 20, 27, 2.5, 48.5),    # Lions by 7 as 2.5 favourites away: cover, under
        (2025, "012", "CHI", "DET", 23, 17, 3.0, 45.0),   # Lions lose
        (2025, "003", "NYJ", "DET", 13, 30, 7.5, 44.5),   # the Jets, once before
        (2024, "014", "DET", "GB", 34, 31, -3.5, 51.0),   # Lions by 3, laying 3.5: no cover, over
        (2024, "009", "GB", "DET", 14, 24, 3.0, 49.0),    # Lions by 10: cover, under
    ]
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, home_score, away_score, "
        "spread, total) VALUES ('nfl',?,?,?,?,?,?,?,?,?)",
        [(s, p, f"{h}{a}{s}{p}", h, a, hs, as_, sp, to) for s, p, h, a, hs, as_, sp, to in games])
    rows = []
    for season, wk, opp, home, stats in (
            (2025, "017", "GB", 1, {"rush_yds": 110.0, "receptions": 3.0}),
            (2025, "012", "CHI", 0, {"rush_yds": 72.0, "receptions": 5.0}),
            (2025, "009", "GB", 0, {"rush_yds": 85.0, "receptions": 4.0}),
            (2025, "003", "NYJ", 0, {"rush_yds": 140.0, "receptions": 2.0}),
            (2024, "014", "GB", 1, {"rush_yds": 60.0, "receptions": 6.0})):
        for market, value in stats.items():
            rows.append(dict(sport="nfl", season=season, period=wk, game_id=f"G{season}{wk}",
                             player="Jahmyr Gibbs", team="DET", opponent=opp, position="RB",
                             home=home, market=market, value=value))
    for d, opp, hits in (("2026-08-01", "BOS", 2.0), ("2026-08-02", "BOS", 0.0), ("2026-08-03", "TB", 1.0)):
        rows.append(dict(sport="mlb", season=2026, period=d, game_id=f"M{d}", player="Aaron Judge",
                         team="NYY", opponent=opp, position="RF", home=1, market="hits", value=hits))
    _db.upsert_player_logs(conn, rows)
    conn.commit()
    conn.close()
    return path


AB.HISTORY_DB = str(_history())

#: Tonight: the Lions play the JETS. Nobody plays the Packers.
NFL = {
    "sport": "nfl", "date": "2026-W03", "built_at": "2026-09-23T12:00:00",
    "games": [{"home": "NYJ", "away": "DET", "spread": 6.5, "total": 45.5, "home_ml": 220, "away_ml": -270}],
    "recommendations": [
        {"player": "Jahmyr Gibbs", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
         "market_label": "Rushing Yards", "side": "OVER", "line": 84.5, "odds": -112,
         "hit_prob": 0.57, "recommended": True, "stake_units": 1.0},
        {"player": "Josh Allen", "team": "BUF", "opponent": "MIA", "market": "pass_yds",
         "market_label": "Passing Yards", "side": "UNDER", "line": 259.5, "odds": -108,
         "hit_prob": 0.55, "recommended": True, "stake_units": 1.0},
    ],
    "game_bets": [{"matchup": "DET @ NYJ", "pick_label": "Lions -6.5", "market": "spread",
                   "odds": -110, "win_prob": 0.55, "home": "NYJ", "away": "DET", "team": "DET"}],
}
MLB = {
    "sport": "mlb", "date": "2026-09-23", "built_at": "2026-09-23T11:00:00",
    "games": [{"home": "NYY", "away": "BOS", "total": 8.5}],
    "recommendations": [{"player": "Aaron Judge", "team": "NYY", "opponent": "BOS", "market": "hits",
                         "market_label": "Hits", "side": "OVER", "line": 0.5, "odds": -180,
                         "hit_prob": 0.7, "recommended": True, "stake_units": 1.0}],
}
BOARDS = {"nfl": NFL, "mlb": MLB}


def _facts(req):
    return json.loads(req["messages"][-1]["content"].split("\n\nFacts for this question:\n")[1])


def _block(**kw):
    return types.SimpleNamespace(**kw)


class Script:
    """A client that plays a script of rounds: each entry is a list of
    (tool name, input) calls, or a string — the answer."""
    def __init__(self, *steps, usage=(700, 60, 1800, 0)):
        self.steps, self.calls, self.usage = list(steps), [], usage
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: vars(o))))
        step = self.steps.pop(0) if self.steps else "Done."
        if kw.get("tool_choice") == {"type": "none"} and not isinstance(step, str):
            step = "With what I have: done."
        i, o, r, w = self.usage
        use = types.SimpleNamespace(input_tokens=i, output_tokens=o, cache_read_input_tokens=r,
                                    cache_creation_input_tokens=w)
        if isinstance(step, str):
            return types.SimpleNamespace(content=[_block(type="text", text=step)], stop_reason="end_turn",
                                         usage=use)
        blocks = [_block(type="text", text="Let me look.")] + [
            _block(type="tool_use", id=f"tu{len(self.calls)}_{n}", name=name, input=args)
            for n, (name, args) in enumerate(step)]
        return types.SimpleNamespace(content=blocks, stop_reason="tool_use", usage=use)


# --- his question -------------------------------------------------------------------
def test_the_lions_against_the_packers_with_the_lions_playing_the_jets_tonight():
    h = AB.team_history("Lions", "Packers", "nfl")
    assert (h["team"], h["opponent"], h["sport"]) == ("Detroit Lions", "Green Bay Packers", "nfl")
    assert h["meetings_stored"] == 4 and h["seasons_we_hold"] == "2024-2025"
    assert h["head_to_head"] == {"games": 4, "record": "4-0", "points_per_game": 29.0,
                                 "allowed_per_game": 22.2, "against_the_spread": "3-1",
                                 "over_under": "2 over, 2 under"}
    first = h["meetings"][0]
    assert first == {"when": "2025 week 17", "result": "W 31-24", "where": "home", "line": -6.5,
                     "covered": "yes", "total": 51.5, "went": "over"}, first
    away = h["meetings"][1]
    assert (away["where"], away["line"], away["covered"]) == ("away", -2.5, "yes"), \
        "the line is signed for the Lions, not for the home side"
    assert h["meetings"][2]["covered"] == "no", "won by 3 laying 3.5"
    for prefer in ("mlb", "nba", "cfb", ""):
        again = AB.team_history("lions", "green bay", "", prefer)
        assert again["meetings_stored"] == 4, f"found from the {prefer or 'no'} tab without a sport"


def test_a_team_alone_is_its_seasons_its_ranks_and_its_latest_games():
    t = AB.team_history("Detroit", "", "nfl")
    assert t["all_stored_games"]["record"] == "5-1"
    s25 = t["by_season"][0]
    assert s25["season"] == 2025 and s25["record"] == "3-1" and s25["offense_rank"].endswith("of 4")
    assert [g["vs"] for g in t["latest_games"]] == ["Green Bay Packers", "Chicago Bears",
                                                    "Green Bay Packers", "New York Jets",
                                                    "Green Bay Packers", "Green Bay Packers"]
    assert t["latest_games"][1]["result"] == "L 17-23"
    assert AB.team_history("Raiders", "", "nfl")["found"] is False, "no stored games is a sentence"
    assert AB.team_history("Lions", "Raiders", "nfl")["found"] is False


def test_any_player_any_league_misspelled_or_not():
    g = AB.player_history("Jahmyr Gibs", "", "", "mlb")
    assert (g["player"], g["sport"], g["team"]) == ("Jahmyr Gibbs", "nfl", "DET")
    assert "closest name" in g["matched"], "it says who it found"
    assert g["latest_games"][0] == {"when": "2025 week 17", "team": "DET", "vs": "GB", "where": "home",
                                    "stats": {"Rushing Yards": 110, "Receptions": 3}}
    assert g["season_averages"] == {"season": 2025, "games": 4,
                                    "per_game": {"Rushing Yards": 101.8, "Receptions": 3.5}}
    vs = AB.player_history("Jahmyr Gibbs", "Packers", "nfl")
    assert vs["opponent"] == "Green Bay Packers" and len(vs["games_against"]) == 3
    assert {x["vs"] for x in vs["games_against"]} == {"GB"}, "the Bears game never leaks in"
    assert vs["averages_against"] == {"Rushing Yards": 85, "Receptions": 4.3}
    judge = AB.player_history("aaron judge", "", "", "nfl")
    assert judge["sport"] == "mlb" and judge["latest_games"][0]["stats"] == {"Hits": 1}
    assert AB.player_history("Aaron Judge", "Red Sox")["averages_against"] == {"Hits": 1}
    assert AB.player_history("Nobody Anywhere")["found"] is False
    assert AB.player_history("Jahmyr Gibbs", "Raiders")["note"].startswith("no stored games")


def test_tonight_on_any_league_s_board():
    t = AB.tonight_board(BOARDS, "Lions", "", "mlb")
    assert len(t["boards"]) == 1, "the Lions are on one board tonight, whichever tab asked"
    nfl = t["boards"][0]
    assert nfl["sport"] == "nfl" and [g["game"] for g in nfl["games"]] == ["DET @ NYJ"]
    assert {r.get("player") or r.get("pick_label") for r in nfl["rows"]} >= {"Jahmyr Gibbs", "Lions -6.5"}
    assert "Josh Allen" not in {r.get("player") for r in nfl["rows"]}, "only the Lions' rows"
    assert AB.tonight_board(BOARDS, "Aaron Judge", "", "nfl")["boards"][0]["sport"] == "mlb"
    none = AB.tonight_board(BOARDS, "Packers", "", "nfl")
    assert none["found"] is False and none["leagues_with_a_board_tonight"] == ["mlb", "nfl"]


# --- every league's board, whichever is open ----------------------------------------
def test_a_row_on_another_league_s_board_is_found_with_its_league():
    req = AB.build_request(MLB, "Josh Allen passing yards?", boards=BOARDS)
    rows = _facts(req)["rows_matching_the_question"]
    assert [(r["player"], r["league"]) for r in rows] == [("Josh Allen", "nfl")]
    summary = json.loads(req["system"][1]["text"].split("\n", 1)[1])
    assert summary["sport"] == "mlb", "the summary is the open league's"
    assert summary["every_league_tonight"] == {"mlb": {"games": 1, "our_bets": 1},
                                               "nfl": {"games": 1, "our_bets": 2}}
    both = _facts(AB.build_request(MLB, "Gibbs or Judge tonight?", boards=BOARDS))
    assert [r["league"] for r in both["rows_matching_the_question"]] == ["mlb", "nfl"], \
        "the open league first on a tie"
    assert {g["game"] for g in both["games"]} == {"BOS @ NYY", "DET @ NYJ"}
    pick = AB.build_request(MLB, "Why this pick?", pick="Jahmyr Gibbs|rush_yds|OVER|84.5", boards=BOARDS)
    assert _facts(pick)["the_pick_this_was_asked_from"]["player"] == "Jahmyr Gibbs", \
        "a pick opened on one league is found from another's tab"


def test_the_model_is_told_to_look_things_up_and_never_to_decline_over_a_schedule():
    for rule in ("any league, team, player or game", "Never decline because a team or player is not "
                 "playing tonight, plays someone else this week, or is in another sport",
                 "look it up with the tools before you answer", "Use ONLY the facts",
                 "our data has nothing on it", "Never tell the reader to bet or how much"):
        assert rule in AB.SYSTEM, rule
    assert [t["name"] for t in AB.TOOLS] == sorted(t["name"] for t in AB.TOOLS) == \
        ["player_history", "team_history", "tonight_board"]
    assert json.dumps(AB.TOOLS) == json.dumps(AB.TOOLS), "one fixed definition, cached with the system"


# --- the loop ------------------------------------------------------------------------
def test_his_question_asked_from_the_mlb_tab_looks_the_meetings_up():
    AB.USAGE_PATH.unlink(missing_ok=True)
    f = Script([("team_history", {"team": "Lions", "opponent": "Packers", "sport": "nfl"})],
               "The Lions are 4-0 against the Packers in the games we hold, 3-1 against the spread.")
    out = AB.ask(MLB, "How have the Lions done against the Packers?", client=f, boards=BOARDS,
                 board_name="mlb_recommendations.json")
    assert out["text"].startswith("The Lions are 4-0") and out["lookups"] == 1 and not out["refused"]
    assert len(f.calls) == 2
    assert all(c["tools"] == AB.TOOLS for c in f.calls), "the tools ride on every round"
    assert "tool_choice" not in f.calls[0], "the first round may look things up"
    second = f.calls[1]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["content"][1]["name"] == "team_history"
    result = second[-1]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu1_0" and "is_error" not in result
    got = json.loads(result["content"])
    assert got["opponent"] == "Green Bay Packers" and got["meetings_stored"] == 4
    assert out["sources"][0] == {"label": "Detroit Lions vs Green Bay Packers, past meetings", "prop": ""}
    day = next(iter(json.loads(AB.USAGE_PATH.read_text())["days"].values()))
    assert (day["calls"], day["lookup_rounds"], day["in"], day["cache_read"]) == (1, 1, 1400, 3600), \
        "one question, one lookup round, both rounds' tokens"
    again = AB.ask(MLB, "how have the lions done against the packers", client=f, boards=BOARDS,
                   board_name="mlb_recommendations.json")
    assert again["cached"] and len(f.calls) == 2 and again["sources"] == out["sources"], \
        "asked again, it costs nothing and still says where it came from"
    moved = {**BOARDS, "nfl": {**NFL, "built_at": "2026-09-23T18:00:00"}}
    AB.ask(moved["mlb"], "How have the Lions done against the Packers?", client=f, boards=moved,
           board_name="mlb_recommendations.json")
    assert len(f.calls) == 3, "another league's new build is a new answer"


def test_the_loop_is_capped_and_the_last_round_may_not_look():
    greedy = [[("player_history", {"player": "Jahmyr Gibbs"}), ("team_history", {"team": "Lions"}),
               ("tonight_board", {"query": "Lions"})]] * 10
    f = Script(*greedy)
    out = AB.ask(NFL, "Tell me everything about the Lions", client=f, boards=BOARDS)
    assert len(f.calls) == AB.MAX_TOOL_ROUNDS + 1
    assert f.calls[-1]["tool_choice"] == {"type": "none"} and out["text"] == "With what I have: done."
    results = [b for c in f.calls[1:] for b in c["messages"][-1]["content"]]
    over = [b for b in results if b.get("is_error")]
    assert out["lookups"] == 3 * AB.MAX_TOOL_ROUNDS and len(over) == out["lookups"] - AB.MAX_TOOL_CALLS
    assert "all the lookups one question gets" in over[0]["content"]


def test_a_lookup_never_raises_and_never_creates_a_database():
    assert AB.run_tool("drop_tables", {}, BOARDS)["error"].startswith("there is no lookup")
    assert AB.run_tool("team_history", "not a dict", BOARDS) == {"error": "no team named"}
    saved = AB.HISTORY_DB
    try:
        AB.HISTORY_DB = str(_TMP / "missing" / "none.db")
        assert AB.run_tool("team_history", {"team": "Lions"}, BOARDS)["error"].endswith("not available")
        assert not (_TMP / "missing").exists(), "a lookup never makes a database"
    finally:
        AB.HISTORY_DB = saved
    broken = types.SimpleNamespace(teams=None)
    real = AB.team_history
    try:
        AB.team_history = lambda *a: broken.teams()                        # noqa: E731
        assert AB.run_tool("team_history", {"team": "Lions"}, BOARDS)["error"].startswith("the lookup failed")
    finally:
        AB.team_history = real
    big = {"note": "x", "games": [{"when": "2025 week 1", "stats": {"Rushing Yards": 100}}] * 900}
    text = AB.fit(big)
    assert len(text) <= AB.MAX_TOOL_CHARS and json.loads(text)["note"] == "x", "trimmed, still JSON"


def test_a_failed_round_still_logs_what_it_spent():
    AB.USAGE_PATH.unlink(missing_ok=True)
    f = Script([("team_history", {"team": "Lions"})])
    real = f.messages.create
    n = {"i": 0}

    def flaky(**kw):
        n["i"] += 1
        if n["i"] == 2:
            raise RuntimeError("down")
        return real(**kw)
    f.messages = types.SimpleNamespace(create=flaky)
    try:
        AB.ask(NFL, "Lions lately?", client=f, boards=BOARDS)
        raise AssertionError("a failed round is Unavailable")
    except EX.Unavailable:
        pass
    day = next(iter(json.loads(AB.USAGE_PATH.read_text())["days"].values()))
    assert day["calls"] == 1 and day["in"] == 700, "the round that ran is on the bill"


# --- the server and the page ----------------------------------------------------------
def test_ask_reads_the_boards_and_writes_only_its_cache_and_its_log():
    """tests/test_gate.py lets askbot name the paid boards on this condition."""
    import re
    src = (ROOT / "engine" / "askbot.py").read_text()
    assert re.findall(r"(?<!def )\b_write\((\w+)", src) == ["CACHE_PATH", "USAGE_PATH"]
    assert len(re.findall(r"\.write_text\(|json\.dump\(|os\.replace\(", src)) == 2, \
        "one writer, _write: the temp file and its rename"
    for path in (AB.CACHE_PATH, AB.USAGE_PATH):
        assert path.parent == _TMP, "and the tests point both away from the repo"
    for name in ("CACHE_PATH", "USAGE_PATH"):
        assert f'ROOT / "data" / "ask_' in src.split(f"{name} = ")[1].split("\n")[0], \
            f"{name} lives under data/, never web/data/"


def test_the_server_hands_ask_every_league_s_board():
    body = SERVER.split("    def _ask(self, body):")[1].split("\n    def ")[0]
    assert "for league, name in AB.BOARD_FILES.items():" in body and "boards=boards" in body
    assert "GATE_.full_board_file(name)" in body, "every name through the same resolver"
    fallbacks = {m.split('"')[0] for m in APP.split('fallback: "data/')[1:]}
    assert set(AB.BOARD_FILES.values()) <= fallbacks, "the names the page asks for"
    assert set(AB.BOARD_FILES) == set(AB.LEAGUES) == set(statlogs.SPORT_MARKETS)


def test_the_endpoint_asked_from_the_mlb_tab_answers_about_the_nfl():
    import server
    from engine import gate
    files = {}
    for league, board in BOARDS.items():
        files[AB.BOARD_FILES[league]] = _TMP / AB.BOARD_FILES[league]
        files[AB.BOARD_FILES[league]].write_text(json.dumps(board))
    f = Script([("team_history", {"team": "Lions", "opponent": "Packers"})], "4-0 in the games we hold.")
    AB.CACHE_PATH.unlink(missing_ok=True)                  # asked fresh, not from an earlier test's answer
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
    h._rate_limited = lambda limit, bucket="read": False
    h._account = lambda conn: "reader"
    h._entitled = lambda conn, who: True
    saved = (server._acct, gate.full_board_file, AB.configured, AB._client,
             os.environ.get("ANTHROPIC_API_KEY"))
    server._acct = lambda: types.SimpleNamespace(connect=lambda: types.SimpleNamespace(close=lambda: None))
    gate.full_board_file = lambda name: files.get(name)
    AB.configured = lambda: True
    AB._client = lambda: f
    os.environ["ANTHROPIC_API_KEY"] = "test-placeholder"
    try:
        h._ask({"board": "mlb_recommendations.json", "question": "How have the Lions done against the Packers?"})
    finally:
        server._acct, gate.full_board_file, AB.configured, AB._client = saved[:4]
        if saved[4] is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved[4]
    code, body = sent[-1]
    assert code == 200 and body["text"] == "4-0 in the games we hold.", sent
    assert body["sources"][0]["label"] == "Detroit Lions vs Green Bay Packers, past meetings"
    summary = json.loads(f.calls[0]["system"][1]["text"].split("\n", 1)[1])
    assert summary["sport"] == "mlb" and set(summary["every_league_tonight"]) == {"mlb", "nfl"}, \
        "the open league's summary, and every league's board behind it"
    assert json.loads(f.calls[1]["messages"][-1]["content"][0]["content"])["meetings_stored"] == 4


def test_the_page_says_it_answers_anything():
    assert "Ask about any team, player or game." in APP
    assert "every past game we have stored" in APP and "Looking it up…" in APP
    assert "every past game we have stored — the answer\n              comes from our own numbers" in APP
    assert "Any team, any player, any sport" in APP
    assert 'data-hint="ask about tonight’s board"' not in HTML


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
