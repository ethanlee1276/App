"""The Pick of the Day while its game is running.

Ethan, 2026-09-16, with the MLB board open: "The live page does not show
the pick of the day when it's live, and also, we should show it's live on
this page in the screenshot as well."

THE ROOT CAUSE WAS ONE TUPLE. `livepicks.TRACKER_CATEGORIES` is
("main", "longshot", "likely") — the three books the Live tab's query
asks for. The Pick of the Day journals to a fourth (`ledger.
POTD_CATEGORY`), so the one bet the front page is named after was the one
bet that disappeared at first pitch. It was not a rendering gap; the row
never reached the page.

IT IS NOT FIXED BY ADDING "potd" TO THAT TUPLE, and this file's first
test is why: the pick comes off the Most Likely board, so the same wager
is already journaled under `likely`. One list built from both books draws
a reader the same ticket twice and makes the tab's own count disagree
with the journal. Its own key, its own card.

THE THIRD TEST IS THE PAYWALL ONE. `live_potd` carries the player, the
market, the side, the line and the price we took — `pick_of_the_day` with
a score beside it, under a new name. engine/gate's own header records
four previous times a new view of a paid board shipped under a key
nobody had added; this is the fifth, remembered in the same edit that
made it, which is the only time it costs nothing.

Run directly: `python3 tests/test_potd_live.py`
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gate, ledger, livepicks                    # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _conn():
    """A journal in memory, with the schema `ledger.connect` builds."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(ledger.SCHEMA)
    return conn


def _bet(conn, category, player="TOR ML", market="moneyline",
         date="2026-09-16", sport="mlb"):
    conn.execute(
        "INSERT INTO bets (sport, date, player, market, side, line, odds, "
        "stake_units, category, status, ts) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (sport, date, player, market, "OVER", 0.0, -118, 1.0, category,
         "open", "2026-09-16T18:00:00Z"))
    conn.commit()


# --- the row reaches the page at all -----------------------------------------
def test_the_pick_of_the_day_is_read_from_its_own_book():
    """The bug, in one assertion: the tracker's default query never saw
    the day's pick."""
    conn = _conn()
    _bet(conn, ledger.POTD_CATEGORY)
    today, _ = livepicks.open_bets_for(conn, "mlb", "2026-09-16")
    assert today == [], "the potd leaked into the open-bet list"
    mine, _ = livepicks.open_bets_for(conn, "mlb", "2026-09-16",
                                      livepicks.POTD_TRACKER_CATEGORIES)
    assert len(mine) == 1 and mine[0]["category"] == "potd"


def test_the_two_lists_never_hold_the_same_ticket_twice():
    """THE REASON IT IS NOT ONE QUERY. The pick comes off the Most Likely
    board, so the same wager sits in the journal under two books; a
    single list built from both draws it twice."""
    conn = _conn()
    _bet(conn, "likely")
    _bet(conn, ledger.POTD_CATEGORY)
    open_rows, _ = livepicks.open_bets_for(conn, "mlb", "2026-09-16")
    potd_rows, _ = livepicks.open_bets_for(
        conn, "mlb", "2026-09-16", livepicks.POTD_TRACKER_CATEGORIES)
    assert len(open_rows) == 1 and len(potd_rows) == 1
    assert ledger.POTD_CATEGORY not in livepicks.TRACKER_CATEGORIES, (
        "the day's pick is back in the open-bet query — it will draw twice")
    keys = {(r["player"], r["market"]) for r in open_rows}
    assert keys == {(r["player"], r["market"]) for r in potd_rows}, (
        "the fixture no longer models the duplicate this guards against")


def test_the_board_carries_the_key_even_on_a_day_with_no_pick():
    """A missing key and an empty list are different facts, and the page
    reads one of them as "no board built yet". `attach_tracker` sets it
    either way."""
    conn = _conn()
    result = {"date": "2026-09-16", "recommendations": [], "games": []}
    livepicks.attach_tracker(result, "mlb", conn=conn, progress={})
    assert result.get("live_potd") == []
    assert "live_picks_error" not in result


def test_a_tracked_pick_is_named_in_the_build_log():
    """A Pick of the Day that stops being tracked is invisible
    everywhere else: the card still draws from the board and the journal
    still holds the row, so only the log can say the tracker lost it."""
    conn = _conn()
    _bet(conn, ledger.POTD_CATEGORY)
    result = {"date": "2026-09-16", "recommendations": [], "games": []}
    note = livepicks.attach_tracker(result, "mlb", conn=conn, progress={})
    assert len(result["live_potd"]) == 1
    assert "pick of the day tracked" in note, note


# --- the paywall --------------------------------------------------------------
def test_the_live_pick_is_behind_the_wall():
    """`live_potd` is `pick_of_the_day` with a score beside it. Both are
    the product."""
    assert "live_potd" in gate.PAID_KEYS
    assert "pick_of_the_day" in gate.PAID_KEYS
    board = {"date": "2026-09-16", "live_potd": [{"player": "TOR ML"}],
             "pick_of_the_day": {"pick": {"player": "TOR ML"}},
             "games": [{"home": "SEA"}]}
    out = gate.redact(board, "mlb_picks.json")
    assert not out.get("live_potd"), "the running pick is published free"
    assert not out.get("pick_of_the_day")
    # AND THE FREE FACTS STAY FREE. A guard that strips the board is not
    # a paywall, it is an outage.
    assert out.get("games") == [{"home": "SEA"}]


# --- the Live tab -------------------------------------------------------------
def test_the_live_tab_draws_the_pick_above_the_open_bets():
    body = _fn("renderLivePicks")
    assert "live_potd" in body, "the Live tab never reads the key"
    assert "potdPanel + panel(" in body, \
        "the day's pick is not drawn above the open-bet panels"
    i_potd = body.index("const potdPanel")
    assert i_potd < body.index('panel(edge, "Open edge bets"')


def test_the_hero_reuses_the_same_row_internals_as_every_other_bet():
    """ONE DEFINITION of the progress bar, the live probability and the
    market line. A headline card with its own copy is a headline card
    that drifts from the rows below it."""
    body = _fn("renderLivePicks")
    assert "potdRows.map(rowHTML)" in body


def test_a_day_with_no_open_bets_still_shows_a_live_pick():
    """The empty slate returns early. Before this, a night whose only
    open wager WAS the Pick of the Day rendered "No open bets on today's
    card" over a running bet."""
    body = _fn("renderLivePicks")
    assert "if (!rows.length && !elsewhere && !potdRows.length) {" in body


def test_the_hero_says_live_while_the_game_runs():
    body = _fn("renderLivePicks")
    assert "LIVE NOW" in body and "live-dot" in body
    assert 'r.phase === "live"' in body


# --- the dashboard card -------------------------------------------------------
def test_the_card_says_it_is_live():
    body = _fn("renderPickOfTheDay")
    assert "potdLiveStrip(liveNow)" in body
    assert "in play" in body, "the heading never says the bet is running"
    assert 'liveNow ? "var(--bad)"' in body, \
        "the card's border does not change while the bet runs"


def test_the_card_reads_the_trackers_row_and_derives_nothing():
    """ONE DEFINITION of "is this game on". Deriving a second answer from
    the board's own games would disagree with the tracker over exactly
    the forty-five minutes between builds where it matters."""
    body = _fn("potdLiveRow")
    assert "live_potd" in body and "liveTrackerRows" in body
    for invented in ("state.data.games", "kickoff", "Date.now"):
        assert invented not in body, f"the card decides liveness itself, off {invented}"


def test_the_live_strip_is_below_the_call_not_above_it():
    """"BET 1 unit" is still the lead. This says that bet is running."""
    body = _fn("renderPickOfTheDay")
    assert body.index("potdCallStrip(got)") < body.index("potdLiveStrip(liveNow)")


def test_a_certainty_is_not_drawn_as_a_forecast():
    """The same rule the Live tab follows: a bet already home says
    CLEARED in words, and repeating it as "100%" reads as a model
    boasting about a fact it did not predict."""
    body = _fn("potdLiveStrip")
    assert "p <= 0 || p >= 1" in body
    assert "CLEARED" in body and "GONE" in body


def test_an_old_board_with_no_live_key_draws_what_it_always_drew():
    """Three different facts — no key, no row, game not started — and
    all three mean the card is unchanged."""
    body = _fn("potdLiveStrip")
    assert 'if (!row) return "";' in body
    assert '|| []' in _fn("potdLiveRow")


# --- the styling --------------------------------------------------------------
def test_live_is_the_same_colour_here_as_everywhere_else():
    """Red is live on the game cards, the play-by-play rail and the Live
    tab's panel headers. A fourth colour for the same fact would make the
    one card that matters most the one a reader has to learn separately."""
    i = CSS.index(".potd-live-strip {")
    block = CSS[i:i + 2200]
    assert "--bad" in block
    assert "--good" not in block, "the live strip paints a running bet as won"


def test_the_motion_stops_for_anyone_who_asked_for_less():
    i = CSS.index(".potd-live-strip {")
    block = CSS[i:i + 2600]
    assert "prefers-reduced-motion" in block
    assert "potdSweep" in block


def test_the_hero_is_separated_by_line_weight_and_not_by_a_glow():
    """`--shadow` is `none` site-wide and has been since the redesign."""
    i = CSS.index(".card.potd-live.is-live")
    block = CSS[i:i + 200]
    assert "box-shadow" not in block
    assert "border-color" in block


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
