"""The card says whether to bet, and the engine is the one that decides.

Ethan, 2026-09-15: the Pick of the Day card "should say whether to bet".
It did not. It opened with the bet in words, a fair, an edge and a
payout, and left the one question a reader arrives with — do I put money
on this today? — to be inferred from the colour of a 3px border and a
sentence six lines below the fold. A day when nothing cleared the bar
wore the same furniture as a day when something did.

WHAT THESE TESTS ACTUALLY DEFEND is that there is exactly ONE definition
of "is this a bet", it lives in `engine/potd.verdict`, and it is derived
over the payload that was PUBLISHED rather than over the rows the board
happened to hold at the time. The two places that could each grow their
own answer are `relock` — which can turn a card that cleared into a card
showing nothing at all — and `day_top_pick`, which can crown a below-bar
lean from a league whose own board published "no bet" about that very
row. Both are tested here against the payload, not against the intent.

The page half runs `potdCallStrip` in node against the real source, so
an edit to the renderer is an edit these tests read.

Run directly: `python3 tests/test_potd_verdict.py`
"""

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import potd                                       # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
ET = ZoneInfo("America/New_York")


def _et(minutes):
    """(date, "HH:MM") in Eastern, `minutes` from now — relative, because
    a fixture pinned to a date is a test that expires."""
    t = dt.datetime.now(ET) + dt.timedelta(minutes=minutes)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def _row(**kw):
    """A game row that clears every bar, three hours out. The same shape
    `tests/test_potd.py` selects on, kept here rather than imported so a
    change to that file's fixture cannot silently rewrite this one."""
    d, k = _et(180)
    r = {"kind": "game", "player": "Over 3.5", "team": "AAA",
         "opponent": "BBB", "market": "total", "market_label": "Total",
         "side": "OVER", "line": 3.5, "book": "DraftKings", "odds": -110,
         "sharp_anchored": True, "sharp_fair": 0.60, "matchup": "AAA@BBB",
         "model_prob": 0.58, "implied_prob": 0.5238, "rank_auc": 0.71,
         "bettable": True, "injury_status": "", "game_date": d, "kickoff": k}
    r.update(kw)
    return r


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _strip(payload):
    """`potdCallStrip` in node, against the source as it sits."""
    js = f"""
    const escapeHtml = (s) => String(s == null ? "" : s);
    const icon = (n) => `[${{n}}]`;
    {_fn("potdCallStrip")}
    console.log(JSON.stringify(potdCallStrip({json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the call itself ---------------------------------------------------------
def test_a_qualifying_pick_is_a_bet_for_one_flat_unit():
    got = potd.build([_row()], "mlb", _et(180)[0])
    assert got["pick"] is not None and not got["pick"]["below_bar"]
    assert got["verdict"]["call"] == "bet"
    assert got["verdict"]["stake"] == potd.STAKE_UNITS == 1.0
    # The ticket, so the strip does not have to reach back into the row.
    assert got["verdict"]["book"] == "DraftKings"
    assert got["verdict"]["odds"] == -110


def test_a_lean_is_no_bet_and_says_which_bar_it_missed():
    """`build` shows the best row on the board when nothing cleared, and
    `ledger.log_pick_of_the_day` refuses to journal it. Those two facts
    already say the product does not stand behind it, so the call it
    gets is the same call an empty board gets — and the reason travels
    rather than being softened away."""
    near = _row(sharp_anchored=False, sharp_fair=None, bettable=False,
                prob_source="market", implied_prob=0.5238, fair_prob=0.60)
    got = potd.build([near], "mlb", _et(180)[0])
    assert got["pick"] is not None and got["pick"]["below_bar"]
    assert got["verdict"]["call"] == "no bet"
    assert got["verdict"]["stake"] == 0.0
    assert got["verdict"]["why"] == got["pick"]["below_bar"]


def test_an_empty_board_is_no_bet_carrying_the_note():
    got = potd.build([], "mlb", _et(180)[0])
    assert got["pick"] is None
    assert got["verdict"] == {"call": "no bet", "stake": 0.0,
                              "why": got["note"]}


def test_every_way_build_can_end_attaches_a_call():
    """THE FAILURE THIS EXISTS FOR: a verdict attached to two of the
    three outcomes and forgotten on the third is a page that leads with
    "BET" on a day the engine declined. `build` has one exit; this is
    the test that keeps it that way."""
    days = _et(180)[0]
    boards = [potd.build([], "mlb", days),
              potd.build([_row()], "mlb", days),
              potd.build([_row(bettable=False)], "mlb", days)]
    for got in boards:
        assert isinstance(got.get("verdict"), dict), got.keys()
        assert got["verdict"]["call"] in ("bet", "no bet")


def test_a_card_with_no_pick_at_all_never_says_bet():
    """The shape `relock` publishes when a sport locked a pick that has
    left the board and cannot be read back from the journal."""
    assert potd.verdict({"pick": None})["call"] == "no bet"
    assert potd.verdict({})["call"] == "no bet"
    assert potd.verdict({"pick": {}})["call"] == "no bet"


# --- the call is derived over what was published, not over the board ---------
def test_relocking_onto_nothing_takes_the_bet_back():
    """A card that led with BET, re-pointed at a locked pick that is
    gone, must not keep leading with BET. The verdict is recomputed
    after `_repoint` lands, not carried over from `build`."""
    days = _et(180)[0]
    live = potd.build([_row()], "mlb", days)
    assert live["verdict"]["call"] == "bet"
    gone = potd.relock(live, [], ("mlb", "nobody", "total", "99.5", "OVER"))
    assert gone["pick"] is None
    assert gone["relocked"]
    assert gone["verdict"]["call"] == "no bet"


def test_relocking_onto_the_same_pick_keeps_the_bet():
    from engine import ledger
    days = _et(180)[0]
    live = potd.build([_row()], "mlb", days)
    key = ledger.potd_row_key(live["pick"])
    assert key is not None
    same = potd.relock(live, [_row()], key)
    assert same["pick"]["locked"] is True
    assert same["verdict"]["call"] == "bet"


def test_the_cross_board_pick_carries_its_own_call():
    """`day_top_pick` can crown a below-bar lean on a day no league
    cleared. The league it came from published "no bet" about that row,
    and the cross-board card has to say the same thing."""
    days = _et(180)[0]
    lean = potd.build([_row(bettable=False)], "mlb", days)
    assert lean["pick"]["below_bar"]
    top = potd.day_top_pick({"mlb": {"pick_of_the_day": lean}}, days)
    assert top["pick"] is not None and top["sport"] == "mlb"
    assert top["verdict"]["call"] == "no bet"

    clear = potd.build([_row()], "mlb", days)
    from engine import ledger
    locked = {"mlb": ledger.potd_row_key(clear["pick"])}
    won = potd.day_top_pick({"mlb": {"pick_of_the_day": clear}}, days,
                            locked=locked)
    assert won["pick"] is not None
    assert won["verdict"]["call"] == "bet"


def test_no_league_at_all_is_no_bet():
    top = potd.day_top_pick({}, _et(180)[0])
    assert top["pick"] is None
    assert top["verdict"]["call"] == "no bet"
    assert top["verdict"]["why"] == top["note"]


# --- the build log leads with the call too -----------------------------------
def test_the_build_log_line_says_the_call_first():
    """The operator reading `journalctl` is asking the reader's
    question. "pick of the day: Over 3.5 Total at -110" does not answer
    it on a day the engine declined."""
    days = _et(180)[0]
    ok = potd.attach({"most_likely": [_row()], "date": days}, "mlb")
    assert "BET 1u on" in ok, ok
    quiet = potd.attach({"most_likely": [], "date": days}, "mlb")
    assert "NO BET" in quiet, quiet
    lean = potd.attach({"most_likely": [_row(bettable=False)],
                        "date": days}, "mlb")
    assert "NO BET" in lean and "below the bar" in lean, lean


# --- the page ----------------------------------------------------------------
def test_the_strip_draws_the_word_bet_with_the_stake():
    html = _strip({"verdict": {"call": "bet", "stake": 1.0, "why": ""}})
    assert "BET 1 unit" in html
    assert "is-bet" in html and "is-pass" not in html


def test_the_strip_draws_no_bet_with_the_reason():
    html = _strip({"verdict": {"call": "no bet", "stake": 0.0,
                               "why": "this market ranks no better than a coin flip"}})
    assert "NO BET" in html
    assert "coin flip" in html
    assert "is-pass" in html and "is-bet" not in html


def test_a_board_built_before_this_shipped_draws_no_strip():
    """A page that leads with "NO BET" because a field is missing is
    worse than one that leads with nothing: the card below still says
    everything it said before, and it is not wrong."""
    assert _strip({"pick": {"odds": -110}}) == ""
    assert _strip({}) == ""
    assert _strip({"verdict": {}}) == ""
    assert _strip(None) == ""


def test_both_states_of_the_card_lead_with_the_strip():
    """THE STRIP IS ABOVE THE WORKING, in both branches — the one that
    draws a pick and the one that draws only a note. Read off the source
    by position, because a strip rendered below the fair and the edge is
    a strip that has stopped being the lead."""
    body = _fn("renderPickOfTheDay")
    assert body.count("potdCallStrip(got)") == 2, \
        "the call strip is not drawn in both of the card's states"
    for marker in ("No pick today.", "american(pick.odds)"):
        i_strip = body.index("potdCallStrip(got)") if marker == "No pick today." \
            else body.rindex("potdCallStrip(got)")
        assert i_strip < body.index(marker), \
            f"the call is drawn after {marker!r} — it is not leading"


def test_the_strip_never_reads_the_row_to_decide():
    """ONE DEFINITION OF "IS THIS A BET". The renderer is allowed to
    draw the verdict and nothing else; re-deriving it from `pick` and
    `below_bar` in JavaScript would be a second answer in the language
    least able to keep it honest."""
    body = _fn("potdCallStrip")
    for word in ("below_bar", ".pick", "shortfall", "evidence"):
        assert word not in body, \
            f"the strip decides the call itself, off {word!r}"


def test_the_two_states_are_not_told_apart_by_colour_alone():
    """A reader who cannot separate the green from the grey still has to
    be able to read the call — so the word and the mark differ, not just
    the fill. Both marks exist in the icon set."""
    body = _fn("potdCallStrip")
    assert '"check"' in body and '"cross"' in body
    for name in ("check", "cross"):
        assert f"  {name}: '" in APP, f"ICON_PATHS has no {name!r}"
    assert ".potd-call.is-bet" in CSS and ".potd-call.is-pass" in CSS


def test_declining_to_bet_is_not_painted_as_a_loss():
    """Deliberately not red. Declining to bet is not a losing day, and
    drawing it as one would push a reader toward the action on exactly
    the day the engine has just said not to."""
    i = CSS.index(".potd-call {")
    block = CSS[i:i + 1400]
    assert "--bad" not in block, "the no-bet state is painted as a loss"
    assert "--good" in block


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
