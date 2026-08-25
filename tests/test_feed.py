"""The live feed: rebuilds diffed into events.

Ethan, 2026-08-24: "The board rebuilds every 60s and the site shows only
the latest snapshot. Diff consecutive builds and publish the diff as a
live activity feed... every entry is a reason someone opened the app at
2:47pm."

THE ONE RULE UNDER EVERY EVENT: an event is a change the board already
believes, never a re-derivation. "Edge appeared" is the board's own
`recommended` flag turning on — the same gates that decide the card
decide the feed, so the two can never disagree about what qualifies.

The cases these tests exist for:

  * COLD START IS SILENT. The first scan has nothing to diff against; a
    feed that greets its first reader with two hundred "appeared" rows
    is announcing its own deployment, not the market.
  * ONE CHANGE, ONE ROW. When an edge dies BECAUSE the line moved, the
    died event carries the move — a second line_move row for the same
    key in the same diff is noise wearing a timestamp.
  * FRINGE CHURN IS NOT NEWS. Boards add and drop non-recommended rows
    every rebuild; only rows the gates believe in make events.
  * THE FEED IS PAID. Every entry names a pick, so feed.json goes
    through gate.publish like any board.

Run directly: `python3 tests/test_feed.py`
"""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import feed, gate                                # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

TS = "2026-08-24T14:41:00"
TS2 = "2026-08-24T14:42:00"


def _row(p="Juan Soto", mkt="total_bases", label="Total Bases", side="OVER",
         line=1.5, odds=-115, book="FanDuel", proj=2.1, ev=0.03,
         rec=False, priced=True):
    return {"player": p, "market": mkt, "market_label": label, "side": side,
            "line": line, "odds": odds, "book": book, "projection": proj,
            "ev_per_unit": ev, "edge": ev, "recommended": rec,
            "has_market": priced}


def _dig(rows):
    return feed.digest({"recommendations": rows})


# --- the diff --------------------------------------------------------------

def test_the_gates_flag_is_the_event_not_a_rederivation():
    prev = _dig([_row(rec=False)])
    cur = _dig([_row(rec=True, ev=0.072, odds=-105)])
    evs = feed.diff(prev, cur, "mlb", TS)
    assert [e["kind"] for e in evs] == ["edge_appeared"]
    assert evs[0]["player"] == "Juan Soto" and evs[0]["ev"] == 0.072


def test_an_edge_dying_names_its_killer():
    base = _row(p="Cole", mkt="strikeouts", label="Strikeouts",
                line=6.5, proj=7.9, rec=True)
    for change, why in (({"line": 7.5}, "line_moved"),
                        ({"odds": -160}, "price_moved"),
                        ({"ev_per_unit": 0.001}, "gates")):
        # The row's key is `recommended` — dict(base, rec=False) sets a
        # junk key and leaves the real one True, which is how this test
        # failed its own first run.
        cur = dict(base, recommended=False, **change)
        evs = feed.diff(_dig([base]), _dig([cur]), "mlb", TS)
        assert [e["kind"] for e in evs] == ["edge_died"], (change, evs)
        assert evs[0]["reason"] == why, (change, evs[0]["reason"])
    evs = feed.diff(_dig([base]), _dig([]), "mlb", TS)
    assert evs[0]["reason"] == "left_board"


def test_one_change_is_one_row():
    """The line move that killed the edge rides IN the died event."""
    prev = _dig([_row(rec=True)])
    cur = _dig([_row(rec=False, line=2.5)])
    evs = feed.diff(prev, cur, "mlb", TS)
    assert [e["kind"] for e in evs] == ["edge_died"]
    assert (evs[0]["frm"], evs[0]["to"]) == (1.5, 2.5)


def test_a_line_move_says_whether_the_model_held():
    prev = _dig([_row(p="Cole", line=6.5, proj=7.9, rec=True)])
    cur = _dig([_row(p="Cole", line=7.5, proj=7.9, rec=True)])
    evs = feed.diff(prev, cur, "mlb", TS)
    assert [e["kind"] for e in evs] == ["line_move"]
    assert evs[0]["model_held"] is True and evs[0]["proj"] == 7.9
    cur2 = _dig([_row(p="Cole", line=7.5, proj=8.4, rec=True)])
    assert feed.diff(prev, cur2, "mlb", TS)[0]["model_held"] is False


def test_a_price_move_needs_two_implied_points():
    prev = _dig([_row(odds=-110)])
    small = _dig([_row(odds=-115)])          # ~1 point: churn, not news
    big = _dig([_row(odds=-135)])            # ~5 points
    assert feed.diff(prev, small, "mlb", TS) == []
    evs = feed.diff(prev, big, "mlb", TS)
    assert [e["kind"] for e in evs] == ["price_move"]
    assert evs[0]["imp_delta"] > 0.02


def test_releases_are_one_wave_not_n_rows():
    held = [_row(p=f"Held {i}", mkt="hits", label="Hits", odds=None,
                 priced=False) for i in range(5)]
    priced = [dict(h, has_market=True, odds=-110) for h in held]
    evs = feed.diff(_dig(held), _dig(priced), "mlb", TS)
    assert [e["kind"] for e in evs] == ["released"]
    assert evs[0]["n"] == 5 and len(evs[0]["players"]) <= 4


def test_fringe_churn_is_not_news():
    """A non-recommended row appearing or vanishing is every rebuild."""
    assert feed.diff(_dig([]), _dig([_row(rec=False)]), "mlb", TS) == []
    assert feed.diff(_dig([_row(rec=False)]), _dig([]), "mlb", TS) == []


# --- the state -------------------------------------------------------------

def test_cold_start_is_silent():
    tmp = tempfile.mkdtemp()
    old_state, old_cwd = feed.STATE_DIR, os.getcwd()
    feed.STATE_DIR = __import__("pathlib").Path(tmp) / "feedstate"
    board = os.path.join(tmp, "b.json")
    try:
        json.dump({"recommendations": [_row(rec=True)]}, open(board, "w"))
        assert feed.scan("mlb", board, now=TS) == [], \
            "the first scan announced its own deployment"
        json.dump({"recommendations": [_row(rec=True, line=2.5)]},
                  open(board, "w"))
        evs = feed.scan("mlb", board, now="2026-08-24T14:42:00")
        assert [e["kind"] for e in evs] == ["line_move"]
    finally:
        feed.STATE_DIR = old_state
        os.chdir(old_cwd)


def test_a_locked_stub_never_reaches_the_differ():
    """With the paywall on, the public copy is a locked stub; diffing it
    against a real digest would read as every pick dying at once."""
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "b.json")
    json.dump({"locked": {"whole_board": 3}}, open(p, "w"))
    assert feed.scan("mlb", p, now=TS) == []


def test_prune_keeps_the_window_and_the_cap():
    evs = [{"id": str(i), "ts": f"2026-08-24T{10 + (i % 12):02d}:00:00"}
           for i in range(300)]
    evs.append({"id": "old", "ts": "2026-08-20T10:00:00"})
    out = feed.prune(evs, now="2026-08-24T22:00:00")
    assert len(out) <= feed.MAX_EVENTS
    assert all(e["id"] != "old" for e in out), "a 4-day-old event survived"
    assert out == sorted(out, key=lambda e: e["ts"], reverse=True)


def test_event_ids_are_stable_so_merges_cannot_duplicate():
    a = feed.diff(_dig([_row(rec=False)]), _dig([_row(rec=True)]), "mlb", TS)
    b = feed.diff(_dig([_row(rec=False)]), _dig([_row(rec=True)]), "mlb", TS)
    assert a[0]["id"] == b[0]["id"]


# --- the wire --------------------------------------------------------------

def test_a_velocity_red_flag_fires_once_when_the_number_lands():
    """The roadmap's fifth promised event kind ("starter down 1.4mph on
    the four-seam"), the last to ship. Warm-up readings land once per
    start: the event fires on the build where the flag first crosses
    -1.0, and never again while it stays crossed."""
    before = _dig([dict(_row(p="Gerrit Cole", mkt="strikeouts"))])
    flagged_row = dict(_row(p="Gerrit Cole", mkt="strikeouts"))
    flagged_row["velo_delta"] = -1.4
    after = _dig([flagged_row])
    evs = feed.diff(before, after, "mlb", TS)
    flags = [e for e in evs if e["kind"] == "velocity_flag"]
    assert len(flags) == 1 and flags[0]["delta"] == -1.4
    # Still flagged next build: silence.
    assert not [e for e in feed.diff(after, after, "mlb", TS2)
                if e["kind"] == "velocity_flag"]
    # A mild dip is not a red flag.
    mild = dict(_row(p="Gerrit Cole", mkt="strikeouts"))
    mild["velo_delta"] = -0.6
    assert not [e for e in feed.diff(before, _dig([mild]), "mlb", TS)
                if e["kind"] == "velocity_flag"]


def test_stale_lines_fire_on_arrival_and_never_repeat():
    """The sniper: the Scanner has always held the stale TABLE; the feed
    marks the MOMENT a book falls behind the field. One event per quote,
    however long it stays behind, and in-play quotes never fire — a live
    "stale" price is a book pausing its trading, not lagging it."""
    row = {"player": "Juan Soto", "bet": "Juan Soto OVER 1.5 Total Bases",
           "book": "FanDuel", "side": "OVER", "line": 1.5, "odds": -105,
           "edge": 0.035, "consensus": 0.58, "live": False,
           "started": False}
    evs, keys = feed.stale_diff(set(), [row], "mlb", TS)
    assert len(evs) == 1 and evs[0]["kind"] == "stale_line"
    assert evs[0]["book"] == "FanDuel" and evs[0]["gap"] == 0.035
    # The same quote next build: remembered, silent.
    evs2, _ = feed.stale_diff(set(keys), [row], "mlb", TS2)
    assert evs2 == []
    # A live row never fires.
    assert feed.stale_diff(set(), [dict(row, live=True)], "mlb", TS)[0] == []
    # A wall of new stales is capped to the widest few.
    many = [dict(row, player=f"P{i}", bet=f"P{i} OVER", edge=0.02 + i / 100)
            for i in range(8)]
    evs3, _ = feed.stale_diff(set(), many, "mlb", TS)
    assert len(evs3) == feed.STALE_MAX_PER_BUILD
    assert evs3[0]["gap"] >= evs3[-1]["gap"], "not ranked by the gap"


def test_the_page_renders_the_new_kinds():
    app = open(os.path.join(ROOT, "web", "js", "app.js"),
               encoding="utf-8").read()
    for kind in ("velocity_flag", "stale_line", "autopsy_posted"):
        assert f'case "{kind}"' in app, f"{kind} events render as nothing"


def test_the_feed_is_a_paid_board():
    assert "feed.json" in gate.PAID_FILES, \
        "every feed entry names a pick — it cannot publish whole"
    assert "feed.json" in gate.KNOWN_BOARDS, \
        "the gate census has never heard of feed.json"


def test_the_loop_publishes_it_as_a_sweep():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def refresh_all(")
    body = src[i:src.index("\ndef ", i + 1)]
    assert "_publish_feed(quiet=quiet)" in body, \
        "the feed left the refresh sweep — nothing publishes it now"
    j = src.index("def _publish_feed(")
    fn = src[j:src.index("\ndef ", j + 1)]
    for sport in ("MLB_OUT", "NFL_OUT", "NBA_OUT", "WNBA_OUT", "CFB_OUT"):
        assert sport in fn, f"the feed no longer scans {sport}"


def test_the_page_leads_with_the_feed():
    i = APP.index("function renderAlerts(")
    body = APP[i:APP.index("\nfunction ", i + 10)]
    assert 'host.innerHTML = `<div id="feed-zone"></div>`' in body, \
        "the feed zone no longer leads the Alerts page"
    assert "renderFeedZone()" in body, \
        "the zone div renders but nothing ever fills it"
    fn = APP[APP.index("async function renderFeedZone("):]
    fn = fn[:fn.index("\nfunction ")]
    for kind in ("edge_appeared", "edge_died", "line_move",
                 "price_move", "released"):
        assert f'case "{kind}"' in fn, f"the page cannot say {kind}"
    assert 'e.ts.endsWith("Z") ? ts' not in fn  # (guard below is the claim)
    assert 'ts.endsWith("Z") ? ts : ts + "Z"' in fn, \
        "server-naive timestamps will parse as browser-local time"
    assert "d.locked" in fn, "a locked stub would render as an empty card"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
