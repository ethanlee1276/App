"""Odds credits go to the leagues playing tonight, and to tonight's games.

Ethan, 2026-10-30, with October's credits all but gone and the NBA's Most
Likely board empty: "tonight's games come first. We need to make up a
system of just recognizing what sport has what games live that night and
pulling credits just for those sports. So obviously if NFL and NBA and MLB
and all of them have a game on that night, then we need to pull all of
them. But if just NFL has a game that night, we just need to pull NFL and
so forth." The NFL had spent 661 credits that Friday pricing Sunday.

One rule each:

  * tonight is the slate being played — the boards' own 5 AM Eastern roll;
  * a league with games on its board and none tonight buys nothing, on any
    lane, and the decline is written down (`launch._odds_affordable`);
  * a league playing tonight is metered at tonight's games;
  * a paid pull on a board that holds the week (the NFL's, college's) buys
    tonight's games and reads the rest from the cache;
  * THE DAY BEFORE (Ethan, 2026-11-07, a Saturday: "we need to be show
    picks a day before games"): those two boards also buy TOMORROW's slate,
    so Sunday's NFL picks are up on Saturday; with nothing tonight a
    day-before slate brings its own DAY_BEFORE_PULLS pulls, capped at
    DAY_BEFORE_SHARE_CAP of the day; two days ahead is still nothing, and the
    daily boards keep tonight alone;
  * the month's plan funds tonight's games first and its report says who
    plays (engine/oddsplan; the plan's own tests are tests/test_the_odds_plan.py).

Run directly: `python3 tests/test_credits_go_to_tonights_games.py`
"""
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import oddsbudget as ob                          # noqa: E402
from engine import oddsplan as P                             # noqa: E402

ET = ZoneInfo("America/New_York")
LAUNCH = (ROOT / "launch.py").read_text(encoding="utf-8")


def _at(*when) -> float:
    return dt.datetime(*when, tzinfo=ET).timestamp()


def _iso(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def _fn(src: str, name: str) -> str:
    start = src.index(f"def {name}(")
    return src[start:src.index("\ndef ", start + 1)]


class _Swap:
    def __init__(self, obj, name, val):
        self.obj, self.name, self.val = obj, name, val

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.val)

    def __exit__(self, *a):
        setattr(self.obj, self.name, self.old)


# --- tonight ------------------------------------------------------------------------
def test_tonight_is_the_slate_being_played():
    fri_10am = _at(2026, 10, 30, 10)
    kicks = [_at(2026, 10, 30, 19), _at(2026, 10, 30, 22, 30),      # tonight
             _at(2026, 10, 31, 0, 30),                               # past midnight: still tonight's
             _at(2026, 10, 31, 12), _at(2026, 11, 1, 13)]            # Saturday, Sunday
    assert ob.tonight_games(kicks, fri_10am) == 3
    assert ob.tonight_games(kicks, _at(2026, 10, 31, 2)) == 3, "2 AM is still Friday night"
    assert ob.tonight_games(kicks, _at(2026, 10, 31, 6)) == 1, "after the 5 AM roll it is Saturday"
    assert ob.tonight_games(kicks[3:], fri_10am) == 0, "games on the board, none tonight: a fact"
    assert ob.tonight_games([], fri_10am) is None, "no times at all: unknown, not a night off"
    assert ob.tonight_games([None, "7pm", True], fri_10am) is None
    # Where tonight ends: 5 AM Eastern, across the clock change too.
    assert ob.tonight_ends(fri_10am) == _at(2026, 10, 31, 5)
    assert ob.tonight_ends(_at(2026, 10, 31, 2)) == _at(2026, 10, 31, 5)
    assert ob.tonight_ends(_at(2026, 10, 31, 20)) == _at(2026, 11, 1, 5)
    assert dt.datetime.fromtimestamp(ob.tonight_ends(_at(2026, 10, 31, 20)), ET).hour == 5


# --- the pacer's gate ---------------------------------------------------------------
def _board(games: list) -> str:
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump({"games": games}, fh)
    return path


def _ask(path: str, sport: str = "nfl", **kw):
    """`launch._odds_affordable` with the pacer and the ledger stubbed and a
    quarter of the day's budget: (verdict, the pacer's calls, the decisions
    written)."""
    import launch
    with _Swap(launch, "_budget_share", lambda sport=None: 0.25):
        return _ask_raw(path, sport, **kw)


def _ask_raw(path: str, sport: str = "nfl", **kw):
    """`_ask` without its budget share: the caller sets one."""
    import launch
    asked, written = [], []

    def pacer(n, **k):
        asked.append(dict(k, n=n))
        return True, "refreshing odds"

    def log(lane, ok, reason, credits=None, **extra):
        written.append(dict(extra, lane=lane, ok=ok, reason=reason, credits=credits))

    with _Swap(launch, "_with_odds", lambda: True), \
            _Swap(ob, "should_refresh", pacer), _Swap(ob, "log_decision", log):
        ok = launch._odds_affordable(path, True, sport=sport, **kw)
    return ok, asked, written


def test_a_league_with_no_game_tonight_buys_nothing():
    tomorrow = [{"kickoff": _iso(ob.tonight_ends() + 9 * 3600)}] * 13     # 2 PM tomorrow
    later = [{"kickoff": _iso(ob.tonight_ends() + 33 * 3600)}] * 13       # 2 PM the day after
    cases = [(tomorrow, lane) for lane in ("nba", "nba_lines")]           # a daily board: tonight only
    cases += [(later, lane) for lane in ("nfl", "nfl_lines", "cfb_lines")]  # two days ahead: nothing
    for games, lane in cases:
        ok, asked, written = _ask(_board(games), lane)
        assert ok is False and not asked, (lane, "the pacer was never asked")
        league = ob.budget_sport(lane).upper()
        assert written and written[0]["ok"] is False and written[0]["tonight"] == 0, written
        assert written[0]["reason"] == (f"no {league} game tonight — credits go to the leagues "
                                        f"playing tonight"), written


def test_the_nfl_and_college_buy_tomorrows_slate_the_day_before():
    """Ethan, Saturday 7 November: "its saturday and we are not showing any
    nfl picks for sunday ... we need to be show picks a day before games"."""
    import launch
    tomorrow = [{"kickoff": _iso(ob.tonight_ends() + 8 * 3600)}] * 13     # 1 PM tomorrow
    per = ob.credits_per_event("nfl")
    with _Swap(ob, "daily_allowance", lambda state=None, today=None, **k: 10_000), \
            _Swap(ob, "load", lambda path=None: object()), \
            _Swap(launch, "_budget_share", lambda sport=None: 0.0):
        ok, asked, written = _ask_raw(_board(tomorrow), "nfl")
    assert ok is True and len(asked) == 1, "a day-before slate goes to the pacer"
    assert asked[0]["credits"] == (13 + 1) * per, ("metered at tomorrow's games", asked)
    want = min(ob.DAY_BEFORE_SHARE_CAP, ob.DAY_BEFORE_PULLS * (13 + 1) * per / 10_000)
    assert abs(asked[0]["share"] - want) < 1e-9, ("its own pulls, not the plan's nothing", asked)
    assert written[0]["tonight"] == 0 and written[0]["tomorrow"] == 13, written
    # Capped: a slate whose pulls would take more than the cap gets the cap.
    with _Swap(ob, "daily_allowance", lambda state=None, today=None, **k: 500), \
            _Swap(ob, "load", lambda path=None: object()), \
            _Swap(launch, "_budget_share", lambda sport=None: 0.0):
        ok, asked, _w = _ask_raw(_board(tomorrow), "cfb_lines", credits=3)
    assert ok is True and asked[0]["share"] == min(ob.DAY_BEFORE_SHARE_CAP, 2 * 3 / 500)
    # Playing tonight too: tonight's games and tomorrow's, at the plan's share.
    both = [{"kickoff": _iso(ob.tonight_ends() - 3600)}] + tomorrow
    ok, asked, written = _ask(_board(both), "nfl")
    assert ok is True and asked[0]["credits"] == (1 + 13 + 1) * per and asked[0]["share"] == 0.25
    assert written[0]["tonight"] == 1 and written[0]["tomorrow"] == 13
    # A daily board, with games tonight and tomorrow, buys tonight's alone.
    ok, asked, written = _ask(_board(both), "nba")
    assert ok is True and asked[0]["credits"] == (1 + 1) * ob.credits_per_event("nba")
    assert written[0].get("tomorrow") is None, "a daily board counts no tomorrow"


def test_a_day_before_pull_is_never_narrowed_to_six_hours():
    """A Saturday's six hours ahead hold none of Sunday's slate, and the
    plan's share the narrowing is judged on is the nothing it owes a league
    with no game today: a narrowed pull (`--active-odds`) bought nothing."""
    import launch
    tomorrow = [{"kickoff": _iso(ob.tonight_ends() + 8 * 3600)}] * 13     # 1 PM tomorrow
    both = [{"kickoff": _iso(ob.tonight_ends() - 3600)}] + tomorrow
    with _Swap(ob, "wide_pull_affordable", lambda *a, **k: False):
        assert launch._narrow_pull(_board(tomorrow), "nfl") is False, "tomorrow's slate is bought"
        assert launch._narrow_pull(_board(both), "nfl") is True, "playing tonight: as before"
        assert launch._narrow_pull(_board(tomorrow), "mlb") is True, "a daily league: as before"
    assert launch._day_before_pull(_board(tomorrow), "nfl_lines") is True
    assert launch._day_before_pull(_board(both), "nfl") is False
    assert launch._day_before_pull(_board([]), "nfl") is False
    assert launch._day_before_pull(_board([{"kickoff": "TBD"}]), "nfl") is False
    src = _fn(LAUNCH, "_narrow_pull")
    assert src.index("_day_before_pull(") < src.index("wide_pull_affordable(_games")


def test_the_day_before_window_is_tomorrows_slate():
    sat_6pm = _at(2026, 11, 7, 18)
    sun_1pm, sun_820pm, mon_815pm = _at(2026, 11, 8, 13), _at(2026, 11, 8, 20, 20), _at(2026, 11, 9, 20, 15)
    kicks = [sun_1pm, sun_820pm, mon_815pm]
    assert ob.tonight_games(kicks, sat_6pm) == 0 and ob.tomorrow_games(kicks, sat_6pm) == 2
    assert ob.tomorrow_games(kicks, _at(2026, 11, 8, 2)) == 2, "2 AM Sunday is still Saturday night"
    assert ob.tomorrow_games(kicks, _at(2026, 11, 8, 9)) == 1, "on Sunday, Monday's game is tomorrow's"
    assert ob.tomorrow_games([], sat_6pm) is None
    assert ob.pick_window_ends(sat_6pm) == _at(2026, 11, 9, 5)
    assert ob.pick_window_ends(_at(2026, 11, 8, 2)) == _at(2026, 11, 9, 5)
    # Across the clock change (1 November 2026): still 5 AM Eastern.
    assert ob.pick_window_ends(_at(2026, 10, 31, 12)) == _at(2026, 11, 2, 5)
    assert dt.datetime.fromtimestamp(ob.pick_window_ends(_at(2026, 10, 31, 12)), ET).hour == 5
    assert set(ob.DAY_BEFORE_LEAGUES) == {"nfl", "cfb"}
    assert 0 < ob.DAY_BEFORE_SHARE_CAP <= 0.5 and ob.DAY_BEFORE_PULLS >= 1


def test_a_league_playing_tonight_is_metered_at_tonights_games():
    tonight = ob.tonight_ends() - 3600              # 4 AM: the last hour of tonight's slate
    week = ([{"kickoff": _iso(tonight)}]
            + [{"kickoff": _iso(ob.tonight_ends() + 2 * 86400)}] * 13)
    ok, asked, written = _ask(_board(week), "nfl")
    assert ok is True and len(asked) == 1
    per = ob.credits_per_event("nfl")
    assert asked[0]["credits"] == (1 + 1) * per, ("one game tonight, not the week's fourteen", asked)
    assert asked[0]["n"] == 2
    assert written[0]["tonight"] == 1 and written[0]["ok"] is True
    # Times the board cannot give are not a night off: the pacer decides,
    # metered at every game on the board as before.
    ok, asked, written = _ask(_board([{}] * 5), "nba")
    assert ok is True and asked[0]["credits"] == 6 * ob.credits_per_event("nba")
    assert written[0].get("tonight") is None, written
    # The caller's own count (UFC's card) is used when it gives one.
    ok, asked, written = _ask(_board([]), "ufc", tonight=0)
    assert ok is False and not asked
    ok, asked, written = _ask(_board([]), "ufc", tonight=12)
    assert ok is True and asked[0]["credits"] == 13 * ob.credits_per_event("ufc")


def test_the_gate_stands_before_the_pacer_and_every_paid_lane_passes_it():
    gate = _fn(LAUNCH, "_odds_affordable")
    assert gate.index("if tonight == 0 and not ahead:") < gate.index("should_refresh(")
    assert "tonight=tonight, tomorrow=" in gate, "every decision records tonight's count"
    for fn in ("refresh_nfl", "refresh_cfb", "refresh_mlb", "refresh_nba", "refresh_nhl",
               "refresh_wnba", "refresh_ufc"):
        body = _fn(LAUNCH, fn)
        for flag in ('"--odds"', '"--board-odds"', '"--live-lines"', '"--lines-odds"'):
            if f"args.append({flag})" in body:
                assert body.index("_odds_affordable(") < body.index(f"args.append({flag})"), (fn, flag)


# --- a board that holds the week ------------------------------------------------------
def test_a_paid_pull_on_a_weekly_board_buys_tonights_games_and_reads_the_rest():
    from engine.sources import oddsapi as oa
    from engine.data_loader import Slate
    from engine.models import Team, DefenseProfile, Weather, Game
    teams = {t: Team(t, t, DefenseProfile(t)) for t in ("GB", "CHI", "PHI", "DAL")}
    slate = Slate(date="2026-W10", teams=teams, props=[],
                  games=[Game(home="GB", away="CHI", weather=Weather(dome=False)),
                         Game(home="PHI", away="DAL", weather=Weather(dome=False))])
    thu_8pm, sun_1pm = _at(2026, 11, 5, 20, 15), _at(2026, 11, 8, 13)
    events = [{"id": "tnf", "home_team": "Green Bay Packers", "away_team": "Chicago Bears",
               "commence_time": _iso(thu_8pm).replace("+00:00", "Z"), "bookmakers": []},
              {"id": "sun", "home_team": "Philadelphia Eagles", "away_team": "Dallas Cowboys",
               "commence_time": _iso(sun_1pm).replace("+00:00", "Z"), "bookmakers": []}]
    calls = []

    def fetch(eid, key, markets=None, books=None, ttl=300, sport="nfl", cache_only=False):
        calls.append((eid, cache_only))
        return {"id": eid, "bookmakers": []}, oa.Quota("90000" if not cache_only else "1", "1")

    until = ob.tonight_ends(_at(2026, 11, 5, 10))
    with _Swap(oa, "list_events", lambda key, ttl=300, sport="nfl", cache_only=False: events), \
            _Swap(oa, "fetch_event_odds", fetch):
        res = oa.apply_odds_to_slate(slate, api_key="k", until=until)
        assert sorted(calls) == [("sun", True), ("tnf", False)], calls
        assert res.read_not_bought == 1 and res.quota.remaining == "90000", \
            "the pull's quota, not a cached read's"
        calls.clear()
        oa.apply_odds_to_slate(slate, api_key="k")
        assert sorted(calls) == [("sun", False), ("tnf", False)], "no bound: as before"
    assert oa.starts_after(events[1], until) and not oa.starts_after(events[0], until)
    assert not oa.starts_after({"commence_time": "soon"}, until)
    assert not oa.starts_after(events[1], None)


def test_college_puts_tonights_games_first_and_buys_only_them():
    import cfb_build as CB
    from engine import pricedplayers
    from engine.sources import oddsapi as oa
    fri_3pm = dt.datetime(2026, 11, 6, 15, tzinfo=ET)
    games = [{"game_id": "sat-marquee", "kickoff": _iso(_at(2026, 11, 7, 15, 30)), "weekday": "Saturday",
              "home_conference": "SEC", "away_conference": "SEC", "home_rank": 3, "away_rank": 9},
             {"game_id": "fri-mac", "kickoff": _iso(_at(2026, 11, 6, 19)), "weekday": "Friday",
              "home_conference": "MAC", "away_conference": "MAC"}]
    priced = {g["game_id"]: {"event_id": "ev-" + g["game_id"], "spread": -3, "total": 50} for g in games}
    calls = []

    def fetch(eid, key, markets=None, sport="cfb", ttl=1800, cache_only=False):
        calls.append((eid, cache_only))
        return {"id": eid, "bookmakers": []}, oa.Quota("1", "1")

    class Tracker:
        data: dict = {}

        def see(self, *a, **k):
            return []

        def save(self):
            pass

    until = ob.tonight_ends(fri_3pm.timestamp())
    with _Swap(oa, "fetch_event_odds", fetch), _Swap(oa, "event_cache_age", lambda *a, **k: None), \
            _Swap(pricedplayers, "Tracker", Tracker):
        *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=False, now=fri_3pm,
                                                 cap=1, until=until)
        assert calls == [("ev-fri-mac", False)], ("the cap's one game is tonight's", calls)
        calls.clear()
        *_, note, _age = CB.attach_player_quotes(games, priced, cache_only=False, now=fri_3pm,
                                                 cap=12, until=until)
        assert calls == [("ev-fri-mac", False), ("ev-sat-marquee", True)], calls
        assert "1 after tonight's slate left to the cache, not bought" in note, note
        calls.clear()
        CB.attach_player_quotes(games, priced, cache_only=False, now=fri_3pm, cap=1)
        assert calls == [("ev-sat-marquee", False)], "no bound: attention tier first, as before"


def test_the_launcher_hands_tonights_end_to_the_weekly_builds():
    nfl, cfb = _fn(LAUNCH, "refresh_nfl"), _fn(LAUNCH, "refresh_cfb")
    paid = nfl[nfl.index('args.append("--odds")'):]
    assert paid.index('args += _tonight_args("nfl")') < paid.index("elif _with_odds():"), \
        "the NFL's paid pull carries its bound (tonight's and tomorrow's)"
    assert '"--out", CFB_OUT] + _tonight_args("cfb")' in cfb, "college's every build: tonight first"
    assert '_pick_until("cfb", now)' in _fn(LAUNCH, "_cfb_player_pull_possible")
    assert '_pick_until("cfb", now)' in _fn(LAUNCH, "_cfb_player_events_affordable")
    import launch
    until = launch._tonight_until()
    assert launch._tonight_args() == ["--price-until", str(int(until))], "no league: tonight's"
    assert launch._tonight_args("nba") == ["--price-until", str(int(until))]
    for lg in ("nfl", "cfb", "nfl_lines"):
        assert launch._tonight_args(lg) == ["--price-until", str(int(ob.pick_window_ends()))], lg
    for build in ("nfl_build.py", "cfb_build.py"):
        src = (ROOT / build).read_text(encoding="utf-8")
        assert 'ap.add_argument("--price-until", type=float' in src, build
        assert "until=args.price_until" in src, build


# --- the plan --------------------------------------------------------------------------
def test_the_plan_funds_tonight_first_and_says_who_plays():
    fri = dt.date(2026, 11, 6)
    games = {"nfl": 0, "nba": 9, "nhl": 5, "cfb": 3, "mlb": 0, "ufc": 0, "wnba": 0}
    plan = P.build(fri, 100_000, games, end=dt.date(2026, 12, 1), reset="set")
    assert plan.get("nfl").today_need == plan.get("nfl").envelope == 0, "no NFL game on a Friday"
    assert plan.get("ufc").today_need == 0, "the card is Saturday's"
    for lg in ("nba", "nhl", "cfb"):
        lp = plan.get(lg)
        assert lp.first == lp.today_need > 0 and lp.envelope >= lp.first, lg
    text = P.report(plan)
    assert ("  tonight: CFB 3 · NBA 9 · NHL 5 — funded first; no game: NFL, UFC "
            "(they buy nothing today)") in text, text
    assert "NFL " in text and "· no game tonight" in text
    quiet = P.build(dt.date(2026, 7, 13), 100_000, {lg: 0 for lg in games})
    assert "  tonight: no games — nothing is bought today" in P.report(quiet)
    assert P.tonight_line(P.build(fri, 100_000)) == "", "tonight not counted: no line"


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
