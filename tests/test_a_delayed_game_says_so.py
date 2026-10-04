"""A delayed game says it is delayed, on every page that draws it.

Ethan, 2026-09-21: *"When a game is delayed, we need to show that on the
live tab. There was an nfl game that was delayed while it was live and
it just sat there thinking it was in the middle of a play."*

THE CAUSE. ESPN keeps `status.type.state` at "in" through a weather
delay, a suspension and halftime, and freezes `displayClock` and the
situation's `downDistanceText` where play stopped. A reader that looks
only at the state — which is what the live board did — keeps drawing
"2nd & 7 · 4:12" as if the snap were seconds away, for as long as the
delay lasts. The state was never wrong; it just was not the whole
status.

THE FIX IS ONE FIELD, `hold`, set from `status.type.name` — and the
frozen clock and down are BLANKED with it, because a frozen clock reads
as a live one. The page draws a held game through one pair of helpers,
so the board card, the live tab and the game page cannot disagree.

Run directly:
`python3 tests/test_a_delayed_game_says_so.py`
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine.sources import livescores as ls                   # noqa: E402


def _event(name="STATUS_IN_PROGRESS", detail="4:12 - 2nd Quarter",
           short="4:12 - 2nd", state="in", clock="4:12", down="2nd & 7 at DEN 45"):
    return {"events": [{
        "id": "401", "date": "2026-09-21T20:15Z",
        "status": {"type": {"state": state, "name": name, "detail": detail,
                            "shortDetail": short},
                   "period": 2, "displayClock": clock},
        "competitions": [{
            "competitors": [
                {"homeAway": "home", "score": "10",
                 "team": {"id": "7", "abbreviation": "DEN", "displayName": "Denver Broncos"}},
                {"homeAway": "away", "score": "7",
                 "team": {"id": "12", "abbreviation": "KC", "displayName": "Kansas City Chiefs"}}],
            "situation": {"downDistanceText": down, "possession": "7",
                          "possessionText": "DEN 45"}}]}]}


def _live(**kw):
    rows = ls.parse_espn_rows(_event(**kw), "nfl")
    assert len(rows) == 1, rows
    return rows[0]["live"]


# --- the parser ----------------------------------------------------------
def test_a_game_in_play_carries_no_hold_and_keeps_its_clock_and_down():
    lv = _live()
    assert lv.state == "live" and lv.hold == ""
    assert lv.clock == "4:12" and lv.detail == "2nd & 7 at DEN 45"


def test_a_weather_delay_is_a_hold_and_the_frozen_clock_and_down_go_dark():
    """THE BUG. Same `state: "in"`, same frozen clock, same frozen down —
    and the card drew all three as live for an hour."""
    lv = _live(name="STATUS_DELAYED", detail="Delayed - Lightning", short="Delayed")
    assert lv.state == "live", "a delayed game is still in progress"
    assert lv.hold == "Delayed - Lightning", lv.hold
    assert lv.clock == "", "a frozen clock reads as a live one"
    assert lv.detail == "", "a frozen down reads as a live one"


def test_halftime_suspension_and_end_of_period_are_holds_too():
    assert _live(name="STATUS_HALFTIME", detail="Halftime", short="Half").hold == "Halftime"
    assert _live(name="STATUS_SUSPENDED", detail="", short="").hold == "Suspended"
    # ESPN's own "End of 3rd" beats a generic "End of period".
    assert _live(name="STATUS_END_PERIOD", detail="End of 3rd", short="End 3rd").hold == "End of 3rd"


def test_a_delay_the_name_did_not_spell_out_but_the_prose_did_is_caught():
    lv = _live(name="STATUS_IN_PROGRESS", detail="Delayed", short="Delayed")
    assert lv.hold == "Delayed", lv.hold


def test_the_hold_word_leads_and_the_feeds_reason_follows():
    assert ls.hold_for({"name": "STATUS_DELAYED", "detail": "Lightning"}) \
        == "Delayed — Lightning"
    assert ls.hold_for({"name": "STATUS_DELAYED", "detail": "Delayed"}) == "Delayed"


def test_a_scheduled_or_final_game_never_holds():
    assert _live(state="pre", name="STATUS_SCHEDULED", detail="", short="9/21 - 8:15 PM").hold == ""
    assert _live(state="post", name="STATUS_FINAL", detail="Final", short="Final").hold == ""


# --- the build -------------------------------------------------------------
def test_the_page_gets_the_hold_only_when_there_is_one():
    import livescore_build as lb
    held = lb._row(ls.parse_espn_rows(_event(name="STATUS_DELAYED",
                                             detail="Delayed - Lightning"), "nfl")[0], "nfl")
    assert held["live"]["hold"] == "Delayed - Lightning", held["live"]
    assert held["live"]["clock"] == "" and held["live"]["detail"] == ""
    live = lb._row(ls.parse_espn_rows(_event(), "nfl")[0], "nfl")
    assert "hold" not in live["live"], "absent means play is live; a key that is always there cannot say that"


# --- the page ---------------------------------------------------------------
def _js():
    return (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")


def test_every_place_that_draws_a_live_game_asks_about_the_hold():
    """THE BOARD CARD, THE LIVE TAB'S CARD AND THE GAME PAGE. A hold
    honoured on one and forgotten on the others is the `game_day` shape
    — eight inserts of eleven."""
    src = re.sub(r"/\*.*?\*/", "", _js(), flags=re.S)
    src = re.sub(r"(?m)^\s*//.*$", "", src)

    def body(name):
        # SCOPED TO THE FUNCTION. The first cut grepped the whole file,
        # and a mutation run deleted the board card's badge branch and
        # passed anyway — the identical line in the card's DETAIL branch
        # satisfied the grep, and the live tab's line is the same text
        # as the game page's. A marker has to be found where it belongs.
        i = src.index(f"function {name}(")
        j = src.find("\nfunction ", i + 1)
        k = src.find("\nasync function ", i + 1)
        end = min(x for x in (j, k, len(src)) if x > 0)
        return src[i:end]
    card = body("gameCard")
    assert card.count("if (isLive && liveHoldWord(live))") == 2, \
        "the board card draws a held game in one place but not the other"
    assert "badge = liveHoldBadgeHTML(live)" in card
    assert "liveDetail = liveHoldDetailHTML(live)" in card
    assert "if (liveHoldWord(lv)) situation +=" in body("liveCardHTML"), \
        "the live tab does not draw a held game"
    assert 'lv.state === "live" && liveHoldWord(lv)' in body("renderPbpPage"), \
        "the game page still says LIVE through a hold"
    assert "if (liveHoldWord(lv)) situation +=" in body("renderPbpPage")
    assert ".live-dot.paused { animation: none" in \
        (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8"), \
        "the dot keeps pulsing on a game that has stopped"


def _render(live):
    import json
    import shutil
    if not shutil.which("node"):
        return None
    src = _js()
    body = src[src.index("function liveHoldWord"):src.index("async function renderLiveBoard")]
    harness = ('const escapeHtml=(x)=>String(x==null?"":x);\n' + body +
               '\nconst lv=JSON.parse(process.argv[2]);'
               'process.stdout.write(liveHoldBadgeHTML(lv)+"|"+liveHoldDetailHTML(lv));')
    path = os.path.join(tempfile.mkdtemp(), "r.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    out = subprocess.run(["node", path, json.dumps(live)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    return out.stdout


def test_a_held_game_reads_delayed_not_live_and_the_dot_stops():
    got = _render({"state": "live", "period": "Q2", "hold": "Delayed — Lightning"})
    if got is None:
        return
    badge, detail = got.split("|")
    text = re.sub(r"<[^>]+>", " ", badge)
    assert "DELAYED" in text and "Q2" in text, text
    assert ">LIVE<" not in badge and "LIVE\n" not in badge, badge
    assert 'live-dot paused' in badge, "the dot still pulses"
    assert "Delayed — Lightning" in detail, detail
    # And a game actually in play draws nothing here — the normal badge does.
    assert _render({"state": "live", "period": "Q2", "clock": "4:12"}) == "|"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
