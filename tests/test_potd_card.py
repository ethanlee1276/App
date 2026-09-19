"""The Pick of the Day on the page: the card, and its spot on the record.

Ethan, 2026-09-15: "We should display the 'pick of the day' at the top
of the dashboard for each sport ... it will have its own spot on the
record page so we can see how it's doing."

THE TEST THAT MATTERS MOST HERE IS THE COPY ONE. He asked for a pick
"that is guaranteed to hit". No bet is, and the engine's header records
why that word was not built (engine/potd.py). This file is what stops it
coming back: a page that promises a paying reader a certainty turns one
ordinary loss into a broken promise, and the promise would live in
exactly these two functions.

`recPotdSection` is pure and runs in node against the real source.
`renderPickOfTheDay` writes to the document, so it is read rather than
run — the assertions are about what it must and must not contain.

Run directly: `python3 tests/test_potd_card.py`
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text()
HTML = (ROOT / "web" / "index.html").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _card():
    return _fn("renderPickOfTheDay")


def _run_section(rep, scope, recent=None):
    """`recPotdSection` in node, against the source as it sits."""
    # The threshold comes from the SOURCE, so the test cannot drift from
    # the value the page actually uses.
    import re as _re
    bar = _re.search(r"const POTD_MIN_N = (\d+);", APP).group(1)
    js = f"""
    const POTD_MIN_N = {bar};
    const MINUS = "\\u2212";
    const SPORT_META = {{ nfl: {{ name: "NFL" }}, mlb: {{ name: "MLB" }} }};
    const escapeHtml = (s) => String(s == null ? "" : s);
    const icon = () => "";
    const american = (o) => (o > 0 ? `+${{o}}` : `\\u2212${{Math.abs(o)}}`);
    const plural = (n, one) => `${{n}} ${{one}}${{n === 1 ? "" : "s"}}`;
    {_fn("recPotdSection")}
    console.log(JSON.stringify(recPotdSection(
        {json.dumps(rep)}, {json.dumps(scope)}, {json.dumps(recent or [])})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the claim the page is allowed to make -----------------------------------
def test_no_surface_promises_a_certainty():
    """The one that must never regress. "Guaranteed" was asked for and
    deliberately not built; if it reappears it will appear here.

    EVERY SURFACE, not just the two that existed when this was written.
    That gap was not hypothetical: the cross-league chooser shipped on
    2026-09-15 was called `lock_of_the_day` end to end and would have
    put those exact four words on the page, in a THIRD renderer this
    test did not know about. A banned list that only reads the
    renderers it was born with is a banned list that stops working the
    first time somebody adds a card.
    """
    banned = ("guarantee", "guaranteed", "lock of the day", "can't lose",
              "cannot lose", "sure thing", "risk-free", "risk free")
    surfaces = [("card", _card()), ("record section", _fn("recPotdSection")),
                ("day top pick", _fn("renderDayTopPick")),
                # FOUND BY THE TEST BELOW, not by anyone reading the file.
                # Both were already clean — the point is that nothing had
                # been holding them that way.
                ("live picks", _fn("renderLivePicks")),
                ("top picks", _fn("renderTopPicks"))]
    for name, body in surfaces:
        low = body.lower()
        for word in banned:
            assert word not in low, f"{name} promises a certainty: {word!r}"


def test_every_pick_renderer_is_on_the_banned_list():
    """THE GUARD ON THE GUARD. The test above can only check surfaces it
    names, so a fourth renderer would be invisible to it exactly the way
    the third one was. This counts them instead: every top-level
    function whose name renders a pick has to be in that list."""
    import re as _re
    src = APP
    found = set(_re.findall(r"async function (render\w*[Pp]ick\w*)\s*\(", src))
    found |= set(_re.findall(r"\bfunction (render\w*[Pp]ick\w*)\s*\(", src))
    checked = {"renderPickOfTheDay", "renderDayTopPick",
               "renderLivePicks", "renderTopPicks"}
    missing = found - checked
    assert not missing, (
        f"these pick renderers are not checked for banned claims: "
        f"{sorted(missing)} — add them to test_no_surface_promises_a_certainty")


def test_the_card_shows_our_number_beside_the_markets():
    """A confidence with no market number next to it is a number nobody
    can weigh."""
    body = _card()
    assert "our number" in body
    assert "the market" in body.lower()


# --- the card's states -------------------------------------------------------
def test_a_board_without_one_draws_nothing():
    """The fold cost this zone was allowed (tests/test_board_order.py) was
    argued on it costing nothing when there is no pick.

    ASKED AS A PROPERTY, not as a character distance. This used to
    require the bail within 400 characters of `const got = …`, which is
    not the rule — the rule is that a board carrying no card writes
    nothing. The window broke on 2026-09-16 when the ERROR check moved
    ABOVE the bail (it had to: `potd.attach`'s failure path leaves no
    card, so the error branch was unreachable in the one state it exists
    for). Nothing about the fold changed; only the distance did.
    """
    body = _card()
    assert 'host.innerHTML = ""' in body, "the empty-board bail is gone"
    i = body.index('host.innerHTML = ""')
    # It is the `!got` branch that bails, not some other empty write.
    guard = body[max(0, i - 200):i]
    assert "!got" in guard and "typeof got" in guard, guard


def test_a_build_that_failed_says_so_rather_than_going_quiet():
    body = _card()
    assert "pick_of_the_day_error" in body
    i = body.index("pick_of_the_day_error")
    assert "warn" in body[i:i + 400]


def test_a_day_that_cleared_nothing_bails_before_the_bet_is_drawn():
    """`below_bar` decides which of two cards is drawn, and it has to
    decide it BEFORE the bet furniture, not label it afterwards.

    REWRITTEN 2026-09-16, and the two versions before it are the reason
    this one is a position rather than a phrase. The first drew the lean
    under "nothing cleared the bar today"; the second renamed the
    headline to "Today’s lean" and kept the team, the price and the book
    in the same bold slot underneath. Ethan read the second one and
    said: "if we shouldn’t be betting a pick, why are we displaying
    one?" Relabelling was never going to answer that.

    The behaviour is tested by RUNNING the renderer in
    tests/test_the_card_never_names_a_bet_it_refuses.py. What is asked
    here is the structural half a rendered-output test cannot see: that
    the refusal is a bail, so no future edit can reach the bet.
    """
    body = _card()
    assert "below_bar" in body
    guard = body.index("if (!pick || below)")
    for later in ("pick-id", "payout_units", "pick.book"):
        assert body.index(later) > guard, (
            f"{later!r} is drawn before the no-bet bail — a refused card "
            f"can reach it again")
    assert "A lean, not the Pick of the Day" not in body, \
        "the lean is back in the card"
    assert "nothing cleared the bar today" not in body, \
        "the old contradiction is back"


def test_the_card_carries_the_band_and_the_payout():
    body = _card()
    assert "payout_units" in body and "pays" in body
    assert "priced between" in body, "the card never states the band it lives in"


def test_the_card_is_drawn_and_drawn_first():
    """Above the picks, which is the fold cost that was argued for."""
    assert 'id="potd-zone"' in HTML
    i = APP.index("function renderAll() {")
    body = APP[i:APP.index("\n}\n", i)]
    assert "renderPickOfTheDay();" in body
    assert body.index("renderPickOfTheDay();") < body.index("renderBestBets();")


# --- the record section ------------------------------------------------------
def test_a_book_with_nothing_in_it_draws_nothing():
    for rep in (None, {}, {"settled": 0, "open": 0}):
        assert _run_section(rep, "nfl") == "", rep


def test_the_record_reads_as_a_record():
    got = _run_section({"settled": 24, "wins": 16, "losses": 8, "pushes": 0,
                        "win_rate": 0.667, "net_units": 3.42, "open": 1}, "nfl")
    assert "16-8" in got and "24 settled" in got
    assert "+3.42u" in got and "67% hit rate" in got
    assert "1 riding" in got
    assert "NFL" in got


def test_a_thin_sample_says_it_is_thin():
    """A 3-1 is not evidence of anything and the section has to say so
    rather than letting a hit rate imply a claim."""
    thin = _run_section({"settled": 4, "wins": 3, "losses": 1, "pushes": 0,
                         "win_rate": 0.75, "net_units": 1.1, "open": 0}, "nfl")
    assert "too few to judge" in thin, thin
    fat = _run_section({"settled": 40, "wins": 24, "losses": 16, "pushes": 0,
                        "win_rate": 0.6, "net_units": 2.0, "open": 0}, "nfl")
    assert "too few to judge" not in fat


def test_a_loss_is_shown_as_a_loss():
    got = _run_section({"settled": 10, "wins": 4, "losses": 6, "pushes": 0,
                        "win_rate": 0.4, "net_units": -2.5, "open": 0}, "nfl")
    assert "−2.50u" in got, "a losing book must print a real minus sign"
    assert "--bad" in got


def test_the_receipts_are_cut_to_the_scope():
    rows = [{"sport": "nfl", "date": "2026-09-14", "player": "A", "market": "receptions",
             "line": 3.5, "odds": -140, "status": "won"},
            {"sport": "mlb", "date": "2026-09-14", "player": "B", "market": "hits",
             "line": 0.5, "odds": -150, "status": "lost"}]
    rep = {"settled": 2, "wins": 1, "losses": 1, "pushes": 0, "win_rate": 0.5,
           "net_units": 0.1, "open": 0}
    nfl = _run_section(rep, "nfl", rows)
    assert ">A\n" in nfl or "A\n" in nfl
    assert "B" not in nfl.replace("bad", "").replace("brand", ""), "another league's row leaked in"
    allsports = _run_section(rep, "", rows)
    assert "All sports" in allsports


def test_the_section_says_what_the_book_is_and_is_not():
    got = _run_section({"settled": 5, "wins": 3, "losses": 2, "pushes": 0,
                        "win_rate": 0.6, "net_units": 0.4, "open": 0}, "nfl")
    assert "no dollar exposure" in got, "a reader cannot tell this from the money book"
    assert "records nothing" in got, "the below-the-bar rule is not stated"


def test_the_record_page_renders_it_scoped_and_pooled():
    i = APP.index("async function renderRecord() {")
    body = APP[i:]
    assert "recPotdSection(scoped ? (d.potd_by_sport || {})[scope] : d.potd," in body


def test_the_copy_uses_the_typographic_apostrophe():
    """The house rule the typography suite enforces site-wide."""
    for body in (_card(), _fn("recPotdSection")):
        for line in body.split("\n"):
            if "'" in line and "escapeHtml" not in line:
                # Apostrophes inside code (quotes, selectors) are fine; the
                # rule is about prose the reader sees.
                assert not any(w in line for w in ("’s the", "n't ", "'s the")), line


def test_the_headline_number_is_the_fair_and_it_names_its_witness():
    """Ethan, 2026-09-15: "we shouldn’t use that 70%." The card used to
    lead with our model’s confidence. It now leads with the fair the
    pick was priced against and says whose fair that is, because "56%"
    means a different thing from Pinnacle than from us — and the
    measurement says the difference runs against us (0.677 to 0.722 on
    NFL moneylines). A regression here would put our own number back at
    the top of the page with nothing marking it as ours."""
    body = _card()
    assert "fair_prob" in body, "the card no longer reads the fair"
    i = body.index("WITNESS")
    block = body[i:i + 400]
    for tier in ("sharp", "market", "model"):
        assert f"{tier}:" in block or f'"{tier}"' in block, tier
    # The witness word is CHOSEN BY THE PICK’S OWN TIER and then drawn.
    # Asserting only that `who` is rendered let a mutant that hard-coded
    # `who = "our number"` survive — the card still said a word, just
    # always the wrong one.
    assert "WITNESS[pick.evidence]" in body, \
        "the witness word is not chosen by the pick’s own tier"
    assert "${who}" in body, "the card computes the witness and never draws it"
    assert "our number says" in body, "the model’s read still travels as context"


def test_a_pick_from_below_the_boards_floor_says_so():
    """DISCLOSURE, NOT A DETAIL. Since 2026-09-15 a reserve row — one
    `likely` shipped from below its own 55% floor — can be the day’s
    pick, but only on a sharper book’s disagreement (engine/potd
    .shortfall). The reserve band is measured at a LOSS on our own
    ranking, so a reader is owed the fact that this row did not clear the
    board’s bar and what got it here instead."""
    body = _card()
    assert "from_reserve" in body, "the card never reads the flag"
    i = body.index("from_reserve")
    block = body[i:i + 400]
    assert "55%" in block or "floor" in block, block[:200]
    assert "sharper book" in block, "it must say what admitted the row"
    # It used to carry an explicit `&& !below` so the disclosure could
    # not land under the lean’s own warn line. The no-bet bail above it
    # makes that guard unreachable, and an unreachable guard is the
    # pattern this codebase keeps finding — so the rule is asked of
    # POSITION instead, which is what actually enforces it now.
    assert body.index("from_reserve") > body.index("if (!pick || below)"), \
        "the reserve disclosure can be reached on a refused card again"


def test_the_card_draws_the_price_break_even_not_the_de_vigged_fair():
    """`implied_prob` on a board row is the DE-VIGGED fair; the number a
    reader needs beside a price is what that PRICE has to beat. The two
    were one field until 2026-09-15."""
    body = _card()
    assert "price_implied" in body, "the card reads the wrong number"
    i = body.index("price_implied")
    assert "implied_prob" in body[i:i + 300], \
        "an older board carries only the de-vigged fair — fall back, do not blank"


def test_a_spread_prints_its_number_once():
    """Ethan’s MLB card, 2026-09-15: "LAA +1.5 1.5 Spread". A game
    spread row carries the SIGNED NUMBER as its side and the same number
    again as `line`, and the naive join printed both. A team total’s
    side is over/under and still needs its line, so the guard asks
    whether the side already IS the number rather than which market it
    is."""
    body = _card()
    i = body.index("const sd = String(pick.side")
    block = body[i:i + 500]
    assert "parseFloat(sd)" in block and "Number(pick.line)" in block, block
    assert "dup ?" in block, "the duplicate is detected and never dropped"

    # Executed, because a guard this fiddly is worth running rather than
    # reading: the spread case collapses, the team total keeps its line.
    js = """
    const teamName = (t) => t, escapeHtml = (s) => String(s == null ? "" : s);
    function render(pick, label) {
      const sd = String(pick.side || "").trim();
      const dup = pick.line != null && Math.abs(parseFloat(sd)) === Math.abs(Number(pick.line));
      return `${teamName(pick.player || pick.team)} ${escapeHtml(sd)}${
        dup ? "" : ` ${pick.line}`} ${escapeHtml(label)}`;
    }
    console.log(JSON.stringify([
      render({player: "LAA", side: "+1.5", line: 1.5}, "Spread"),
      render({player: "LAA", side: "-1.5", line: 1.5}, "Spread"),
      render({player: "SEA", side: "over", line: 4.5}, "Team Total"),
    ]));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    spread_plus, spread_minus, team_total = json.loads(out.stdout)
    assert spread_plus == "LAA +1.5 Spread", spread_plus
    assert spread_minus == "LAA -1.5 Spread", spread_minus
    assert team_total == "SEA over 4.5 Team Total", team_total


def test_a_model_only_lean_never_leads_with_our_own_number():
    """Ethan, 2026-09-15, on the MLB card: "it seems like it’s not
    confident in its own pick?" It was not — and it was shouting
    "**59%**" and "+11.8% edge" while saying so.

    Those are precisely the figures `engine/potd.shortfall` has just
    declined to stand behind: our model measures 0.677 where the market
    measures 0.722, so a price only we dispute is disputed by the weaker
    witness. Printing its edge in bold is the habit this whole rebuild
    removed, and it had crept back into the one state where it does the
    most damage."""
    body = _card()
    assert 'pick.evidence === "model"' in body, \
        "the card draws every tier the same way again"
    # The branch carries a long comment saying WHY, so the copy sits well
    # past a narrow window — search the card rather than a slice of it.
    assert "No sharp book is quoting this market" in body
    assert "not name a day after our own number alone" in body
    # THE EDGE IS DRAWN EXACTLY ONCE, in the branch that earned it. A
    # second occurrence would mean it had crept back into the state where
    # the number is the one we just declined to stand behind.
    #
    # COMMENTS ARE STRIPPED FIRST, because the branch’s own comment
    # QUOTES the card Ethan sent — "+11.8% edge" — and a test that
    # counts prose is measuring the explanation rather than the page.
    import re as _re
    drawn = _re.sub(r"<!--.*?-->", "", body, flags=_re.S)
    assert drawn.count("% edge") == 1, \
        f"the edge is drawn {drawn.count('% edge')} times, not once"
    i_model = drawn.index("No sharp book is quoting this market")
    i_edge = drawn.index("% edge")
    assert i_edge > i_model, \
        "the edge is drawn before the model-only branch — wrong branch"


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
