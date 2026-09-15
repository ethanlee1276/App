"""No bet is journaled on a game under way, and none is recommended.

Ethan, 2026-09-14, 11:15pm, on the Live tab: "Whatever u did shows the
bets as upcoming again." Under the rows he was looking at sat placed
times of 8:52pm, 10:32pm and 10:51pm — on a game that kicked off at
8:15pm. The launcher never passed `--live` to `nfl_build.py`, so every
build that evening saw the game as scheduled: `pipeline._finish_bet`'s
"already started" rule had nothing to read, the Most Likely board's
refusal of `live`/`started` rows had nothing to refuse, and the journal
had no rule of its own. Adam Trautman over 1.5 receptions went in during
the first quarter; Bo Nix over 217.5 passing yards and Evan Engram over
3.5 receptions in the third; a game-total under 48.5 in the fourth with
41 points already scored.

Three changes, three witnesses:

  · the launcher passes `--live`, and the games-only fallback overlays too;
  · `rules.game_has_started` also reads the game's OWN KICKOFF
    (`clock_says_started`), inside an eight-hour window, so a dead
    scoreboard feed cannot re-open the hole — and props now carry
    `started` like game cards do;
  · `ledger.in_play_reason` refuses at journal time, on all three books.

Every clock here is relative to now — a fixture pinned to a date is a
test that expires.
"""

import datetime as dt
import os
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import ledger, rules                              # noqa: E402
from engine.models import Game, LiveStatus, Weather           # noqa: E402

ET = ZoneInfo("America/New_York")
LAUNCH = (ROOT / "launch.py").read_text()
NFL_BUILD = (ROOT / "nfl_build.py").read_text()
PIPELINE = (ROOT / "engine" / "pipeline.py").read_text()


def _et(minutes):
    """(date, "HH:MM") in Eastern, `minutes` from now — the bare clock an
    NFL game row carries beside its date."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _iso(minutes):
    t = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _game(minutes, **kw):
    d, k = _et(minutes)
    return Game(home="KC", away="DEN", weather=Weather(dome=True),
                date=d, kickoff=k, **kw)


# --- the clock ---------------------------------------------------------------
def test_the_clock_says_started_inside_the_window():
    d, k = _et(-30)
    assert rules.clock_says_started(d, k), "kicked off half an hour ago"
    d, k = _et(90)
    assert not rules.clock_says_started(d, k), "kicks off in ninety minutes"
    d, k = _et(-9 * 60)
    assert not rules.clock_says_started(d, k), \
        "nine hours on is history, not a game in play (rules.IN_PLAY_WINDOW_MIN)"
    assert rules.clock_says_started("", _iso(-30)), "an ISO stamp needs no date"
    assert not rules.clock_says_started("", _iso(30))
    assert not rules.clock_says_started("", "20:15"), "a bare clock with no date cannot be joined"
    assert not rules.clock_says_started("2026-09-14", ""), "no clock, no answer"
    assert not rules.clock_says_started("2026-09-14", "TBD")


def test_game_has_started_reads_the_overlay_first_and_the_clock_second():
    assert rules.game_has_started(_game(-30))
    assert not rules.game_has_started(_game(120))
    # The overlay wins whatever the clock says.
    assert rules.game_has_started(_game(120, live=LiveStatus(state="live", home_score=0, away_score=3)))
    assert rules.game_has_started(_game(120, live=LiveStatus(state="final", home_score=31, away_score=10)))
    # And a scheduled overlay on a game the clock says has started: started.
    assert rules.game_has_started(_game(-30, live=LiveStatus(state="scheduled", home_score=0, away_score=0)))
    assert not rules.game_has_started(Game(home="KC", away="DEN", weather=Weather(dome=True)))


def test_a_prop_carries_started_like_a_game_card():
    i = PIPELINE.index('d["game_kickoff"] = game.kickoff')
    block = PIPELINE[i - 900:i]
    assert 'd["started"] = game_has_started(game)' in block, \
        "props carried only `live`, so the Most Likely board admitted them after the whistle"


# --- the journal's own rule ---------------------------------------------------
def test_in_play_reason_has_three_witnesses():
    assert "under way" in ledger.in_play_reason({"live": True})
    assert "already been played" in ledger.in_play_reason({"started": True})
    d, k = _et(-30)
    why = ledger.in_play_reason({"kickoff": k, "game_date": d})
    assert why and "kicked off" in why and "min ago" in why, why
    d, k = _et(120)
    assert ledger.in_play_reason({"kickoff": k, "game_date": d}) is None
    d, k = _et(-9 * 60)
    assert ledger.in_play_reason({"kickoff": k, "game_date": d}) is None, "history, not in play"
    assert ledger.in_play_reason({}) is None, "no clock, no flag, no refusal"
    assert ledger.in_play_reason({"game_kickoff": _iso(-30)}), "the long-shot row's clock"
    assert ledger.in_play_reason({"commence_time": _iso(-30)}), "the odds row's clock"
    # The board's team map, when the row carries no clock of its own.
    assert ledger.in_play_reason({"team": "KC"}, kick={"KC": _iso(-30)})
    assert ledger.in_play_reason({"team": "KC"}, kick={"KC": _iso(30)}) is None


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _rec(player, team, opp):
    return {"player": player, "market": "rec_yds", "side": "OVER", "line": 62.5,
            "odds": -114, "grade": "A", "stake_units": 1.0, "hit_prob": 0.57,
            "edge": 0.04, "confidence": 8.0, "recommended": True,
            "has_market": True, "team": team, "opponent": opp}


def test_the_edge_journal_refuses_the_row_in_play():
    conn = _conn()
    d1, k1 = _et(-30)
    d2, k2 = _et(120)
    result = {"sport": "nfl", "date": "2026-W02",
              "recommendations": [_rec("Bo Nix", "DEN", "KC"), _rec("Josh Allen", "BUF", "MIA")],
              "games": [{"home": "KC", "away": "DEN", "date": d1, "kickoff": k1},
                        {"home": "BUF", "away": "MIA", "date": d2, "kickoff": k2}]}
    kick = ledger._kickoff_map(result)
    why = ledger.journal_skip_reason(_rec("Bo Nix", "DEN", "KC"), True, kick)
    assert why and "kicked off" in why, why
    assert ledger.journal_skip_reason(_rec("Josh Allen", "BUF", "MIA"), True, kick) is None
    ledger.log_recommendations(conn, result)
    rows = [r[0] for r in conn.execute("SELECT player FROM bets")]
    assert rows == ["Josh Allen"], rows


def test_the_edge_journal_refuses_a_game_bet_in_play():
    """The second loop in `log_recommendations` — game bets — refuses on
    the same witnesses. A sharp-anchored total on a game in its fourth
    quarter is exactly the shape of the 10:51pm row."""
    conn = _conn()
    d1, k1 = _et(-150)
    d2, k2 = _et(120)
    bet = lambda team, opp, d, k, **kw: dict({                # noqa: E731
        "bet_type": "total", "market": "total", "matchup": f"{opp} @ {team}",
        "home": team, "away": opp, "team": "", "side": "UNDER", "line": 48.5,
        "odds": -112, "book": "FanDuel", "win_prob": 0.58, "fair_prob": 0.53,
        "edge": 0.05, "ev_per_unit": 0.06, "confidence": 8.0, "grade": "A",
        "stake_units": 0.8, "recommended": True, "date": d, "kickoff": k,
        "live": False, "started": False}, **kw)
    result = {"sport": "nfl", "date": "2026-W02", "recommendations": [],
              "game_bets": [bet("KC", "DEN", d1, k1), bet("BUF", "MIA", d2, k2)],
              "games": [{"home": "KC", "away": "DEN", "date": d1, "kickoff": k1},
                        {"home": "BUF", "away": "MIA", "date": d2, "kickoff": k2}]}
    ledger.log_recommendations(conn, result)
    rows = [r[0] for r in conn.execute("SELECT player FROM bets")]
    assert rows == ["MIA@BUF"], rows
    # And the flag alone, with no clock on the row.
    conn = _conn()
    ledger.log_recommendations(conn, {"sport": "nfl", "date": "2026-W02", "recommendations": [],
                                      "game_bets": [bet("KC", "DEN", "", "", started=True)],
                                      "games": []})
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0


def test_the_edge_journal_refuses_the_flagged_row_without_a_clock():
    conn = _conn()
    rec = _rec("Bo Nix", "DEN", "KC")
    rec["live"] = True
    ledger.log_recommendations(conn, {"sport": "nfl", "date": "2026-W02",
                                      "recommendations": [rec], "games": []})
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0


def _likely(player, team, minutes, **kw):
    d, k = _et(minutes)
    row = {"player": player, "team": team, "market": "rec_yds", "side": "over",
           "line": 62.5, "odds": -120, "book": "DraftKings", "model_prob": 0.61,
           "implied_prob": 0.545, "projection": 70.0, "game_date": d, "kickoff": k}
    row.update(kw)
    return row


def test_the_likely_journal_refuses_the_row_in_play():
    conn = _conn()
    payload = {"sport": "nfl", "date": "2026-W02",
               "most_likely": [_likely("Adam Trautman", "DEN", -37),
                               _likely("Josh Allen", "BUF", 120)]}
    n = ledger.log_most_likely(conn, payload)
    rows = [r[0] for r in conn.execute("SELECT player FROM bets")]
    assert n == 1 and rows == ["Josh Allen"], (n, rows)
    # A game row too — the total under 48.5 placed in the fourth quarter.
    conn = _conn()
    d, k = _et(-150)
    game_row = {"kind": "game", "bet_type": "total", "market": "total",
                "matchup": "DEN @ KC", "team": "KC", "side": "under", "line": 48.5,
                "odds": -112, "book": "FanDuel", "model_prob": 0.58,
                "implied_prob": 0.53, "player": "Under 48.5", "date": d, "kickoff": k}
    assert ledger.log_most_likely(conn, {"sport": "nfl", "date": "2026-W02",
                                         "most_likely": [game_row]}) == 0


def test_the_long_shot_journal_refuses_the_row_in_play():
    conn = _conn()
    shot = lambda player, when: {                            # noqa: E731
        "player": player, "team": "KC", "market": "anytime_td", "side": "yes",
        "line": 0.5, "odds": 400, "book": "DraftKings", "model_prob": 0.30,
        "implied_prob": 0.20, "projection": None, "ev_per_unit": 0.1,
        "game_kickoff": _iso(when), "game_date": _iso(when)[:10]}
    n = ledger.log_longshots(conn, {"sport": "nfl", "date": "2026-W02",
                                    "long_shots": [shot("Rashee Rice", -45),
                                                   shot("James Cook", 180)]})
    rows = [r[0] for r in conn.execute("SELECT player FROM bets")]
    assert n == 1 and rows == ["James Cook"], (n, rows)


# --- the launcher and the build ---------------------------------------------------
def test_the_launcher_passes_live_to_the_nfl_build():
    i = LAUNCH.index("def refresh_nfl(")
    body = LAUNCH[i:LAUNCH.index("\ndef ", i + 10)]
    assert '"--injuries", "--depth", "--carry", "--live"]' in body, \
        "the full build never learned a game was live"
    j = body.index('"--games-only", "--cached-odds"')
    assert '"--live"' in body[j:j + 80], "and the games-only fallback journals game bets too"


def test_the_games_only_path_overlays_the_scoreboard_too():
    i = NFL_BUILD.index("if args.games_only and args.live:")
    assert "attach_live(_types.SimpleNamespace(games=games))" in NFL_BUILD[i:i + 600]
    assert NFL_BUILD.index("if args.games_only:") > i, "before the early return"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
