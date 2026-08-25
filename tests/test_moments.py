"""Anchored daily moments: the day's rhythm as feed events.

Ethan's roadmap, item 3: "Structure the day so there are 4-5 known times
to check in... ~9am 'The Card': today's board + last night's settle
recap. Two dopamine hits in one visit."

NOTHING IS SCHEDULED AND EVERYTHING FIRES ONCE — the two clauses that
make a rhythm instead of an alarm clock. Each moment announces a thing
that actually happened (the pipeline's own rhythm IS the schedule), and
the state file remembers what has been said, because the loop passes
this way every sixty seconds and "The card is up" forty times before
noon is spam wearing a timestamp.

The cases pinned here:

  * A HALF-GRADED NIGHT IS NOT A RECAP. The recap waits for the LAST
    open bet of that date to close — recapping early means restating
    different numbers every hour, which is a correction, not a moment.
  * A CREW CHANGE RE-ANNOUNCES. The ump moment keys on the NAME, so a
    late swap fires again; the same name never does.
  * A NEUTRAL UMP HAS NO TILT SENTENCE. Under the threshold the profile
    is noise wearing a name, and the event says "neutral" instead.
  * A NEW DAY FORGETS — except the recap marker, which is keyed by the
    night it recaps, or day two would recap night one again.

Run directly: `python3 tests/test_moments.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger, moments                           # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()

TODAY = "2026-08-24"
NOW = "2026-08-24T13:05:00"


def _board(recs=1, ump="", kf=None):
    return {"recommendations": [
        {"player": f"P{i}", "market": "hits", "market_label": "Hits",
         "side": "OVER", "line": 0.5, "ev_per_unit": 0.03 + i / 100,
         "recommended": True} for i in range(recs)],
        "games": [{"home": "NYM", "away": "ATL", "game_number": 1,
                   "plate_umpire": ump, "ump_k_factor": kf}]}


def _recap(w=2, l=1, open_=0, date="2026-08-23"):
    return {"date": date, "w": w, "l": l, "p": 0, "net_u": 0.4,
            "open": open_}


def test_each_moment_fires_once():
    evs, st = moments.derive(_board(), [{"live": {"state": "live"}}],
                             _recap(), {}, TODAY, NOW)
    assert sorted(e["kind"] for e in evs) == \
        ["card_posted", "first_pitch", "settle_recap"]
    evs2, _ = moments.derive(_board(), [{"live": {"state": "live"}}],
                             _recap(), st, TODAY, "2026-08-24T13:06:00")
    assert evs2 == [], "the loop's second pass repeated the announcements"


def test_a_half_graded_night_is_not_a_recap():
    evs, st = moments.derive({}, [], _recap(open_=2), {}, TODAY, NOW)
    assert not any(e["kind"] == "settle_recap" for e in evs), \
        "a night with open bets was recapped — the numbers will change"
    evs, _ = moments.derive({}, [], _recap(open_=0), st, TODAY, NOW)
    assert [e["kind"] for e in evs] == ["settle_recap"]
    assert evs[0]["w"] == 2 and evs[0]["net_u"] == 0.4


def test_a_night_with_no_bets_is_silence_not_zero_zero():
    evs, _ = moments.derive({}, [], _recap(w=0, l=0), {}, TODAY, NOW)
    assert evs == [], 'a betless night announced "went 0-0"'


def test_the_card_needs_recommended_picks():
    evs, _ = moments.derive(_board(recs=0), [], None, {}, TODAY, NOW)
    assert evs == [], "an empty board announced a card"
    evs, _ = moments.derive(_board(recs=3), [], None, {}, TODAY, NOW)
    assert evs[0]["kind"] == "card_posted" and evs[0]["n_picks"] == 3
    assert evs[0]["best"]["player"] == "P2", "best is not the top EV pick"


def test_a_crew_change_reannounces_and_the_same_name_never_does():
    evs, st = moments.derive(_board(ump="Angel Hernandez", kf=1.06),
                             [], None, {}, TODAY, NOW)
    umps = [e for e in evs if e["kind"] == "ump_assigned"]
    assert len(umps) == 1 and umps[0]["k_tilt"] == "over"
    evs, st = moments.derive(_board(ump="Angel Hernandez", kf=1.06),
                             [], None, st, TODAY, NOW)
    assert not any(e["kind"] == "ump_assigned" for e in evs)
    evs, _ = moments.derive(_board(ump="Pat Hoberg", kf=0.99),
                            [], None, st, TODAY, NOW)
    umps = [e for e in evs if e["kind"] == "ump_assigned"]
    assert len(umps) == 1 and umps[0]["ump"] == "Pat Hoberg"
    assert umps[0]["k_tilt"] is None, \
        "a 1% profile got a tilt sentence — noise wearing a name"


def test_a_new_day_forgets_everything_except_the_recap_marker():
    _, st = moments.derive(_board(ump="X", kf=1.1),
                           [{"live": {"state": "live"}}],
                           _recap(), {}, TODAY, NOW)
    evs, st2 = moments.derive(_board(ump="X", kf=1.1),
                              [{"live": {"state": "live"}}],
                              _recap(date="2026-08-24"),
                              st, "2026-08-25", "2026-08-25T09:00:00")
    kinds = sorted(e["kind"] for e in evs)
    assert kinds == ["card_posted", "first_pitch", "settle_recap",
                     "ump_assigned"], kinds
    # …but the OLD night, already recapped, never comes back.
    evs, _ = moments.derive({}, [], _recap(date="2026-08-23"),
                            st2, "2026-08-25", "2026-08-25T09:01:00")
    assert evs == [], "day two recapped night one again"


def test_event_ids_are_stable():
    a, _ = moments.derive(_board(), [], None, {}, TODAY, NOW)
    b, _ = moments.derive(_board(), [], None, {}, TODAY,
                          "2026-08-24T14:00:00")
    assert a[0]["id"] == b[0]["id"], \
        "the same moment gets a new id each pass — merges will duplicate"


def test_last_night_reads_the_journal():
    conn = ledger.connect(":memory:")
    for st, pnl in (("won", 0.9), ("lost", -1.0), ("open", 0.0)):
        conn.execute(
            "INSERT INTO bets (ts,sport,date,player,market,side,line,book,"
            "odds,stake_units,stake_dollars,status,category,pnl_units) "
            "VALUES ('t','mlb','2026-08-23',?,'hits','OVER',0.5,'DK',-110,"
            "1,10,?,'main',?)", (f"P{st}{pnl}", st, pnl))
    conn.commit()
    r = moments.last_night(conn, TODAY)
    assert r == {"date": "2026-08-23", "w": 1, "l": 1, "p": 0,
                 "net_u": -0.1, "open": 1}


# --- the wire --------------------------------------------------------------

def test_the_loop_runs_moments_in_the_sweep():
    src = open(os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    i = src.index("def _publish_feed(")
    fn = src[i:src.index("\ndef ", i + 1)]
    assert "_moments.run(quiet=quiet)" in fn, \
        "moments left the refresh sweep"


def test_the_board_ships_the_umpire():
    src = open(os.path.join(ROOT, "engine", "mlb", "pipeline.py"),
               encoding="utf-8").read()
    assert '"plate_umpire": getattr(g, "plate_umpire", "")' in src
    assert '"ump_k_factor": getattr(g, "ump_k_factor", None)' in src


def test_the_page_speaks_all_four_kinds():
    fn = APP[APP.index("async function renderFeedZone("):]
    fn = fn[:fn.index("\nfunction ")]
    for kind in ("settle_recap", "card_posted", "ump_assigned",
                 "first_pitch"):
        assert f'case "{kind}"' in fn, f"the feed cannot say {kind}"
    assert "behind the plate" in fn
    assert "the sweat is on" in fn


def test_the_morning_strip_leads_the_home_board():
    html = open(os.path.join(ROOT, "web", "index.html"),
                encoding="utf-8").read()
    assert 'id="daycard-zone"' in html
    i = APP.index("async function renderDayCard(")
    fn = APP[i:APP.index("\nfunction renderRecommended", i)]
    assert 'e.kind === "settle_recap"' in fn, \
        "the strip invents its own recap instead of reading the event"
    assert "d.locked" in fn
    j = APP.index("function renderRecommended() {")
    assert "renderDayCard();" in APP[j:j + 120], \
        "nothing fills the strip on the page it lives on"


def test_the_autopsy_announces_once_and_moves_forward_only():
    """#6's celebration and the day's late-night anchor: the nightly
    postmortem landing is a moment. Same monotonic discipline as the
    recap — one announcement per date, older entries never re-fire."""
    autopsy = {"date": "2026-08-23",
               "headline": "The unders died in one inning"}
    evs, st = moments.derive({}, [], None, {}, TODAY, NOW, autopsy=autopsy)
    kinds = [e["kind"] for e in evs]
    assert kinds == ["autopsy_posted"]
    assert evs[0]["headline"].startswith("The unders died")
    # Again with the same entry: silence.
    evs2, st = moments.derive({}, [], None, st, TODAY, NOW, autopsy=autopsy)
    assert evs2 == []
    # An OLDER entry handed in later must not re-announce.
    older = {"date": "2026-08-20", "headline": "old news"}
    evs3, _ = moments.derive({}, [], None, st, TODAY, NOW, autopsy=older)
    assert evs3 == []


def test_the_autopsy_marker_survives_the_new_day():
    _, st = moments.derive({}, [], None, {}, TODAY, NOW,
                           autopsy={"date": "2026-08-23", "headline": "x"})
    assert st["autopsied"] == "2026-08-23"
    _, st2 = moments.derive({}, [], None, st, "2026-08-25",
                            "2026-08-25T09:00:00",
                            autopsy={"date": "2026-08-23", "headline": "x"})
    assert st2["autopsied"] == "2026-08-23", \
        "day two re-announced night one's autopsy"


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
