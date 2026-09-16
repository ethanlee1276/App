"""A Pick of the Day card that says NO BET does not then name a bet.

Ethan, 2026-09-16, reading the MLB card in a screenshot: "I see that
we're showing a pick, but then we're also saying don't bet the pick. So
if we shouldn't be betting a pick, why are we displaying one? ... if
that's a good pick, then we need to say to bet it, not to not bet it."

THE FIRST ANSWER WAS TO LOWER THE BAR SO A PICK EXISTED, and it was
wrong — measurably. `potd_backtest --sweep-ev` over the stored MLB
closes is flat from a 0% EV floor through 2.0% (37 days, 25-12, +27.9%
at every one), and the bar binding on the days that produced nothing is
the same at every setting: the gap is too big to trust. Moving the floor
buys no picks. Worse, the leans that ceiling excludes settled −23.1%
over 12 bets in the same replay, so showing them IS the expensive
choice.

So the card changed instead. This file is the thing that keeps it
changed, and it RUNS THE RENDERER rather than reading its source — a
grep for "A lean, not the Pick of the Day" is satisfied by a card that
prints the team, the price and the book directly above that sentence,
which is exactly the card Ethan was complaining about.

Run directly: `python3 tests/test_the_card_never_names_a_bet_it_refuses.py`
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    """One top-level function, `async` prefix included."""
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def render(payload, sport="mlb", top=None):
    """`renderPickOfTheDay` in node against the real source.

    THE PIECES UNDER TEST ARE THE REAL ONES — the card, the call strip,
    the live strip and the cross-league line all come out of app.js.
    Only the page furniture around them is stubbed, because a stub of
    the thing being tested tests the stub.

    Returns ``(card html, top-pick html)``.
    """
    js = f"""
    const MINUS = "\\u2212";
    const SPORT_META = {{ mlb: {{ name: "MLB" }}, nfl: {{ name: "NFL" }} }};
    const state = {{ sport: {json.dumps(sport)}, view: "recommended",
                    data: {json.dumps(payload)} }};
    {_fn("escapeHtml")}
    const escapeAttr = escapeHtml;
    const icon = () => "";
    const iconMark = () => "";
    const american = (o) => (o > 0 ? `+${{o}}` : `\\u2212${{Math.abs(o)}}`);
    const teamName = (t) => String(t || "");
    const betMark = () => "";
    const ridingAttrs = () => "";
    const liveTrackerRows = (r) => r;
    {_fn("potdLiveRow")}
    {_fn("potdLiveStrip")}
    {_fn("potdCallStrip")}
    const _top = {json.dumps(top)};
    async function loadTopPickOnce() {{ return _top || {{}}; }}
    async function loadRecordOnce() {{ return {{}}; }}
    const _els = {{}};
    const document = {{ getElementById: (id) => _els[id] || null }};
    for (const id of ["potd-zone", "potd-top-pick", "potd-record"]) {{
      _els[id] = {{ innerHTML: "", textContent: "", querySelector: () => null }};
    }}
    {_fn("renderDayTopPick")}
    {_fn("renderPickOfTheDay")}
    renderPickOfTheDay().then(() => console.log(JSON.stringify(
      [_els["potd-zone"].innerHTML, _els["potd-top-pick"].innerHTML])));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# The bet a refused card used to advertise. Everything about it is
# distinctive enough to find in the HTML: the team, the price, the book.
LEAN_ROW = {"below_bar": "the gap is too big to trust",
            "market": "moneyline", "player": "LAD", "team": "LAD",
            "opponent": "SDP", "odds": -130, "book": "DraftKings",
            "fair_prob": 0.59, "price_implied": 0.565, "ev_units": 0.05,
            "payout_units": 0.77, "evidence": "sharp"}


def _payload(row, call):
    return {"pick_of_the_day": {
        "band": [-250, 190], "pick": row,
        "verdict": ({"call": "no bet", "stake": 0.0,
                     "why": row.get("below_bar") or "no pick today"}
                    if call == "no bet"
                    else {"call": "bet", "stake": 1.0, "why": "",
                          "book": row.get("book"), "odds": row.get("odds")})}}


def test_a_refused_day_names_no_team_no_price_and_no_book():
    """The whole complaint, as one assertion per thing he could act on."""
    card, _ = render(_payload(LEAN_ROW, "no bet"))
    assert "NO BET" in card, card
    for thing in ("LAD", "DraftKings", "130", "0.77"):
        assert thing not in card, (
            f"a NO BET card is still advertising {thing!r} — this is the "
            f"card Ethan read as the page arguing with itself:\n{card}")


def test_a_refused_day_still_says_why_and_what_to_do_with_the_day():
    card, _ = render(_payload(LEAN_ROW, "no bet"))
    assert "the gap is too big to trust" in card, \
        "the reader is told there is no bet and not told why"
    assert "board below" in card, \
        "nothing points the reader at the thing that IS on the page"


def test_the_reason_is_given_once_not_twice():
    """The strip carries it. A sentence repeating it word for word reads
    as two separate findings that happen to match."""
    card, _ = render(_payload(LEAN_ROW, "no bet"))
    assert card.count("the gap is too big to trust") == 1, card


def test_a_day_that_cleared_still_draws_the_whole_bet():
    """The other half, and the one a careless fix breaks: if the guard
    is wrong in the other direction the product disappears."""
    row = dict(LEAN_ROW, below_bar="")
    card, _ = render(_payload(row, "bet"))
    assert "BET 1 unit" in card
    for thing in ("LAD Moneyline", "DraftKings", "−130",
                  "pays 0.77u", "59%", "priced between"):
        assert thing in card, f"a qualifying pick lost {thing!r}:\n{card}"


def test_a_board_with_no_card_at_all_still_writes_nothing():
    """The fold cost this zone was granted (tests/test_board_order.py)."""
    card, _ = render({})
    assert card == "", card


def test_a_refused_league_hands_the_day_to_a_league_that_cleared():
    """WHAT FILLS THE HOLE. A blank card is honest and useless; the
    cross-league file already holds a bet a reader can actually place."""
    _, top = render(_payload(LEAN_ROW, "no bet"),
                    top={"sport": "nfl", "runners_up": [],
                         "pick": {"market": "moneyline", "player": "KC",
                                  "team": "KC", "odds": -120}})
    assert "NFL" in top and "KC Moneyline" in top, top
    assert "open it" in top, "the reader cannot get to it"


def test_the_cross_league_line_obeys_the_same_rule():
    """`potd.day_top_pick` hands back the strongest LEAN when no league
    cleared, so this line used to read "Today's strongest lean, across
    every league is in the NFL: KC Moneyline -120 - a lean, not a pick".
    That is the same bet-under-a-refusal, in smaller type."""
    _, top = render(_payload(LEAN_ROW, "no bet"),
                    top={"sport": "nfl", "census": {"the gap is too big to trust": 4},
                         "pick": {"below_bar": "the gap is too big to trust",
                                  "market": "moneyline", "player": "KC",
                                  "team": "KC", "odds": -120}})
    assert "Nothing cleared the bar in any league today" in top, top
    for thing in ("KC", "120", "open it"):
        assert thing not in top, f"the lean is still named: {thing!r}\n{top}"


def test_no_card_state_promises_a_certainty():
    """The banned list, asked of the RENDERED output rather than the
    source, because that is where a promise would reach a reader."""
    banned = ("guarantee", "lock of the day", "sure thing", "risk-free",
              "can't lose", "cannot lose")
    states = [_payload(LEAN_ROW, "no bet"),
              _payload(dict(LEAN_ROW, below_bar=""), "bet"), {}]
    for payload in states:
        for html in render(payload):
            low = html.lower()
            for word in banned:
                assert word not in low, f"{word!r} reached the page: {html}"


def test_one_other_league_is_not_one_other_league_pick():
    """Found by reading the output of the test above it: the possessive
    was built by appending an apostrophe to a word that only sometimes
    took an s, so a single runner-up read "it beat 1 other league' pick"."""
    _, top = render(_payload(dict(LEAN_ROW, below_bar=""), "bet"),
                    top={"sport": "mlb", "runners_up": [1],
                         "pick": dict(LEAN_ROW, below_bar="")})
    assert "one other league’s pick" in top, top
    _, many = render(_payload(dict(LEAN_ROW, below_bar=""), "bet"),
                     top={"sport": "mlb", "runners_up": [1, 2],
                          "pick": dict(LEAN_ROW, below_bar="")})
    assert "2 other leagues’ picks" in many, many


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
