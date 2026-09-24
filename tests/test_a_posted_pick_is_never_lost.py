"""A Most Likely pick, once posted, is on the board or listed as pulled.

Ethan, 2026-09-24, the evening after the hold shipped: "we still have
most likley and edge bets dissaperring from the board. there was most
likley bets i saw for the packers game yesterday that are no where to be
found."

Two holes let that happen. The seats are slate-wide — eight a market over
a whole NFL week — so on Thursday, with Sunday's props priced, likelier
picks from other games took tonight's seats and the Packers picks were
simply gone: from the board, the shelf and their own game page. And a
pick that left for any reason was remembered for an hour, after which
nothing anywhere said it had existed.

Now a posted pick keeps its seat while it clears every bar (a likelier
newcomer comes in beside it — `HELD_SEATS`), and one that does come off
is listed until its game with when it went up, when it came off and why
(`likely_turnover.earlier`), on the Most Likely page and on its game page.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                               # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}


def _ln(book, line, over):
    return {"book": book, "line": line, "over_odds": over, "under_odds": 0}


def _row(player, team="GB", opponent="ATL", projection=62.0, **kw):
    got = {"player": player, "team": team, "opponent": opponent, "market": "rush_yds",
           "market_label": "Rush Yards", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
           "has_market": True, "fair_prob": 0.50, "projection": projection, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [55, 71, 48, 66],
           # Thursday Night Football, the way the NFL board writes it: a
           # bare Eastern clock time beside the date.
           "game_date": "2026-09-24", "kickoff": "20:15", "hit_prob": 0.56, "raw_prob": 0.58,
           "alt_lines": [_ln("DraftKings", 40.5, -240), _ln("FanDuel", 40.5, -230),
                         _ln("DraftKings", 50.5, -160), _ln("FanDuel", 50.5, -155)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got


def _sunday(player, projection=66.0):
    return _row(player, team="KC", opponent="LV", projection=projection,
                game_date="2026-09-27", kickoff="13:00")


def _board(props, previous=None, now="2026-09-24T15:00:00Z", limit=8):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    turn: dict = {}
    try:
        rows = K.build(props, sport="nfl", fits=FITS, previous=previous, now=now,
                       turnover=turn, limit=limit)
    finally:
        K.rankable = real
    return rows, turn


def _prev(rows, turn):
    """What `previous_board` hands the next build."""
    return {"rows": list(rows) + list(turn.get("held_out") or []),
            "day": turn.get("day") or {}, "earlier": turn.get("earlier") or []}


def _players(rows):
    return {r["player"] for r in rows}


# ── the seat ──────────────────────────────────────────────────────────────


def test_sundays_props_do_not_take_thursdays_seats():
    wed = [_row(f"GB{i}", projection=56.0 + i * 0.4) for i in range(8)]    # 63-66%
    b0, t0 = _board(wed, now="2026-09-23T20:00:00Z")
    assert _players(b0) == {f"GB{i}" for i in range(8)}, "Wednesday: the Packers hold the seats"
    thu = wed + [_sunday(f"KC{i}", projection=64.0 + i * 0.5) for i in range(8)]   # 71-75%
    cold, _ = _board(thu)
    assert not any(p.startswith("GB") for p in _players(cold)), \
        "with no memory the likelier Sunday picks take every seat — the bug"
    b1, t1 = _board(thu, previous=_prev(b0, t0))
    assert {f"GB{i}" for i in range(8)} <= _players(b1), "a posted pick keeps its seat"
    assert {f"KC{i}" for i in range(8)} <= _players(b1), "the likelier newcomers come in beside it"
    assert not t1["earlier"], "nothing was pulled"


def test_the_market_grows_to_a_ceiling_and_no_further():
    held = {K.hold_key(r): r for r in [{"kind": "prop", "player": f"H{i}", "team": "T",
                                         "market": "rec_yds", "model_prob": 0.60} for i in range(16)]}
    rows = [{"kind": "prop", "player": f"H{i}", "team": "T", "market": "rec_yds",
             "model_prob": 0.60 - i * 0.001} for i in range(16)]
    rows += [{"kind": "prop", "player": f"N{i}", "team": "T", "market": "rec_yds",
              "model_prob": 0.80} for i in range(8)]
    kept = K._cut_players(rows, 8, held=held)
    assert len(kept) == 8 * K.HELD_SEATS, len(kept)
    assert {f"N{i}" for i in range(8)} <= _players(kept)
    assert "H15" not in _players(kept), "past the ceiling the weakest posted pick gives way"


# ── pulled, and listed until its game ─────────────────────────────────────


def test_a_pick_that_comes_off_is_listed_until_kickoff_with_why():
    b0, t0 = _board([_row("Josh Jacobs")], now="2026-09-23T20:00:00Z")
    assert _players(b0) == {"Josh Jacobs"}
    # Thursday lunchtime: the final injury report lists him questionable.
    b1, t1 = _board([_row("Josh Jacobs", injury_status="Questionable")],
                    previous=_prev(b0, t0), now="2026-09-24T16:00:00Z")
    assert not b1
    (e,) = t1["earlier"]
    assert e["player"] == "Josh Jacobs" and e["out_at"] == "2026-09-24T16:00:00Z"
    assert e["since"] == "2026-09-23T20:00:00Z", "when it went up rides along"
    assert e["out_note"] == "listed Questionable — held until inactives confirm"
    assert e["odds"] and e["market_label"] == "Rush Yards", "enough to draw the row a reader saw"
    # Three hours later — long past the hour a ghost is kept to come back
    # as the same pick — it is still listed.
    b2, t2 = _board([_row("Josh Jacobs", injury_status="Questionable")],
                    previous=_prev(b1, t1), now="2026-09-24T19:00:00Z")
    assert [x["player"] for x in t2["earlier"]] == ["Josh Jacobs"]
    # 8:16 PM Eastern: his game has started, and the list lets him go.
    b3, t3 = _board([], previous=_prev(b2, t2), now="2026-09-25T00:16:00Z")
    assert t3["earlier"] == []


def test_a_pick_back_on_the_board_leaves_the_list():
    b0, t0 = _board([_row("Josh Jacobs")], now="2026-09-23T20:00:00Z")
    b1, t1 = _board([_row("Josh Jacobs", injury_status="Questionable")],
                    previous=_prev(b0, t0), now="2026-09-24T16:00:00Z")
    b2, t2 = _board([_row("Josh Jacobs")], previous=_prev(b1, t1), now="2026-09-24T19:30:00Z")
    assert _players(b2) == {"Josh Jacobs"} and t2["earlier"] == []


def test_the_nfl_clock_time_reads_as_a_kickoff():
    row = {"game_date": "2026-09-24", "kickoff": "20:15"}
    assert not K._kicked_off(row, "2026-09-25T00:14:00Z"), "8:14 PM Eastern"
    assert K._kicked_off(row, "2026-09-25T00:15:00Z")
    assert K._kicked_off(row, "2026-09-26T12:00:00Z"), "a day later"
    assert not K._kicked_off({"game_date": "2026-09-27", "kickoff": "13:00"}, "2026-09-25T00:15:00Z")
    assert K._kicked_off({"game_date": "2026-09-24", "kickoff": "7:05 PM"}, "2026-09-24T23:06:00Z")
    assert not K._kicked_off({"kickoff": "soon"}, "2026-09-25T00:15:00Z"), "unreadable is never a guess"


def test_every_reason_reads_as_a_fact_about_the_bet():
    assert K.reader_reason("heavier than -250 — chalk, not a pick") \
        == "the price moved past −250, too heavy to call a pick"
    assert K.reader_reason("under the likelihood floor after calibration") \
        == "the model’s chance for it fell under our bar"
    assert K.reader_reason("no longer offered") == "the books stopped offering it"
    assert K.reader_reason("a likelier pick took its seat") == "the board filled with likelier picks"
    assert K.reader_reason("listed Out — held until inactives confirm") \
        == "listed Out — held until inactives confirm"


def test_the_next_build_reads_the_list_back():
    src = open(os.path.join(ROOT, "engine", "likely.py"), encoding="utf-8").read()
    i = src.index("def previous_board(")
    fn = src[i:src.index("\ndef ", i + 10)]
    assert '"earlier": [r for r in turn.get("earlier") or [] if isinstance(r, dict)]' in fn


# ── the page ──────────────────────────────────────────────────────────────


def test_the_page_lists_them_on_the_board_and_on_the_game():
    assert "(t.earlier || []).filter(" in APP
    i = APP.index("function renderLikely(")
    assert "likelyPulledHTML(likelyPulled())" in APP[i:APP.index("\n}\n", i)]
    j = APP.index("function renderGamePage(")
    page = APP[j:APP.index("\n}\n", j)]
    assert "const pulled = likelyPulled().filter(" in page
    assert 'likelyPulledHTML(pulled, { title: "Pulled from this game", open: !likelies.length })' in page
    assert ".ml-pulled-why {" in CSS


def test_the_board_note_says_how_a_pick_stays_up():
    assert "a likelier pick is\n    added beside it, never swapped in" in APP
    assert "a pick 3 points\n    likelier takes the seat" not in APP


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
