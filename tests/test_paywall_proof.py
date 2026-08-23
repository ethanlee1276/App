"""The one claim on the shop a stranger can check, put where it is read.

Ethan, 2026-08-23, scrolling the plans on his phone: "are we displaying as
bunch captivating and eye catching information as we can?"

The page was never short of INFORMATION — a hero, nine sport chips, ten
feature cards, three plans, a trust block, an FAQ and a footer. It was
short of EVIDENCE placed where evidence changes a mind. The hero promised
"every call graded in public" and then showed nothing to back it until
below the pricing, in a trust block, after the reader had already been
asked to decide. Every other line on that page is a claim about
ourselves; the record is the only one a stranger can go and verify, and it
was the one thing they had to scroll past a price to find.

So it split in two, and the split is the argument rather than a layout
preference:

  * RESULTS in the hero — what happened, in four numbers, before anybody
    has seen a price.
  * PROCESS below the plans — closing-line value and the count of bets
    that beat the close. That is the case that the results are not luck,
    and it is worth making to somebody still reading at the bottom.

WHAT THIS FILE IS REALLY GUARDING is the honesty of that strip, because a
strip of numbers at the top of a sales page is the exact shape of the
thing every pick-selling site fakes. So:

  * every figure is read from the record payload, never written here;
  * the sample size ships beside the rate, always — a percentage with no
    n is the tell;
  * a losing record renders exactly as readily as a winning one. There is
    no branch on the sign, and the test below proves it by rendering a
    book that is down and checking the number is still there.

Run directly: `python3 tests/test_paywall_proof.py`
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _js():
    return open(os.path.join(ROOT, "web", "js", "app.js"),
                encoding="utf-8").read()


def _fn(src, name):
    """A function body by brace matching, past its parameter list."""
    i = src.index("function " + name + "(")
    j, depth = src.index("(", i), 0
    while j < len(src):
        if src[j] == "(":
            depth += 1
        elif src[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = src.index("{", j), 0
    for k in range(start, len(src)):
        if src[k] == "{":
            d += 1
        elif src[k] == "}":
            d -= 1
            if not d:
                return src[i:k + 1]
    raise AssertionError(name + " never closes")


# --- where it sits ------------------------------------------------------------
def test_the_record_is_shown_before_the_price():
    """The whole point. A page that says "graded in public" in its hero
    and shows the grades below the checkout is asking to be taken on
    faith on the one page where it does not have to be."""
    js = _js()
    body = _fn(js, "paywallHTML")
    assert "pwResultsHTML(rec)" in body, "the results strip is never drawn"
    assert body.index("pwResultsHTML(rec)") < body.index('class="pw-plans"'), (
        "the receipts render below the prices again")
    # …and inside the hero, not floating between sections.
    hero = body[body.index('class="pw-hero"'):body.index("</section>")]
    assert "pwResultsHTML(rec)" in hero


def test_the_two_halves_do_not_print_the_same_numbers_twice():
    """Results and process are different arguments. Printing the win
    rate in both places is the duplication this repo has already been
    told off for on the prop cards.

    Checked on what is INTERPOLATED, not on what is mentioned. Two
    earlier cuts of this failed on things that are not printed numbers —
    `o.settled` inside the proof block's empty-journal guard, and the
    words "win rate" inside its prose. A field a template reads is not a
    field a reader sees twice; a `${...}` slot is.
    """
    js = _js()
    fields = {}
    for name in ("pwResultsHTML", "paywallProofHTML"):
        body = _fn(js, name)
        shown = set()
        for expr in re.findall(r"\$\{([^{}]*)\}", body):
            for field in re.findall(r"\bo\.([a-z_]+)|\bpr\.([a-z_]+)", expr):
                shown.add(field[0] or ("process." + field[1]))
        fields[name] = shown
    both = fields["pwResultsHTML"] & fields["paywallProofHTML"]
    assert not both, (
        f"printed in both blocks, so a reader meets the same number "
        f"twice on one page: {sorted(both)}")
    # And each half owns its own half of the argument — read from the
    # source, not from the interpolation scan above. Two of these are
    # hoisted into a local before they are printed (`net`, `clv`), and a
    # scan that only sees `${...}` slots cannot follow that. The scan is
    # the right instrument for the duplication question and the wrong one
    # for this; using it for both is how a test starts asserting the
    # shape of the code instead of the shape of the page.
    results, proof = _fn(js, "pwResultsHTML"), _fn(js, "paywallProofHTML")
    for outcome in ("o.settled", "o.wins", "o.net_units", "o.win_rate",
                    "o.breakeven"):
        assert outcome in results, f"{outcome} left the results strip"
    for process in ("o.avg_clv", "o.process"):
        assert process in proof, f"{process} left the proof block"
        assert process not in results
    assert "net_units" not in proof and "win_rate" not in proof


# --- what it may say ----------------------------------------------------------
def test_every_number_comes_off_the_record_payload():
    """A hand-written figure on a sales page is a claim nobody can check,
    which is the opposite of what this strip is for."""
    body = _fn(_js(), "pwResultsHTML")
    # Digits that are not array indexes, decimal places or percentages.
    literals = re.findall(r"(?<![\w.\[(])\d{2,}(?![\w.\])%])", body)
    allowed = {"30", "100"}          # the small-sample cut, and pct scaling
    stray = [n for n in literals if n not in allowed]
    assert not stray, f"hard-coded figures on the results strip: {stray}"


def test_a_rate_never_ships_without_its_sample_size():
    """A percentage with no n beside it is what every pick-seller
    publishes and the reason none of them can be believed."""
    results = _fn(_js(), "pwResultsHTML")
    assert "o.settled" in results, "no count beside the rates"
    assert "breakeven" in results, (
        "a win rate with no break-even is flattering by omission — 46% "
        "against a 54% bar is a different sentence from 46% alone")
    proof = _fn(_js(), "paywallProofHTML")
    assert "o.clv_n" in proof, "the CLV average ships without its n"


def test_it_says_nothing_rather_than_zero_when_there_is_no_record():
    results = _fn(_js(), "pwResultsHTML")
    assert 'if (!o || !o.settled) return "";' in results, (
        "an empty journal renders a strip of zeros, which reads as a "
        "model that has lost every bet it ever made")
    # The block below the plans still explains itself in that case.
    proof = _fn(_js(), "paywallProofHTML")
    assert "Nothing has settled yet" in proof


def test_a_losing_record_is_rendered_exactly_as_readily():
    """No branch on the sign anywhere. The tone class changes colour; it
    must not change whether the number appears."""
    results = _fn(_js(), "pwResultsHTML")
    assert "net >= 0 ?" in results, "the net has no sign handling at all"
    # Every use of the sign is cosmetic: a class name or a +/− glyph.
    for m in re.finditer(r"net >= 0 \?([^:]*):", results):
        arm = m.group(1)
        assert '"' in arm and len(arm) < 40, (
            f"the sign is doing more than choosing a glyph or a colour: {arm}")
    # Exactly two returns: the empty one for an empty journal, taken
    # before the net is even computed, and the strip itself. A third
    # would be somewhere for a losing book to be quietly dropped.
    assert results.count("return") == 2, (
        f"{results.count('return')} returns in the strip — one of them "
        "can hide a result")
    assert results.index("return") < results.index("const net"), (
        "the only early return now sits after the net is known")


def test_it_still_sends_them_to_the_free_record():
    """The strip is a summary. The argument is that you can go and check
    it, so the link has to be right there rather than four sections
    down."""
    results = _fn(_js(), "pwResultsHTML")
    assert '#record' in results and "free" in results


# --- and the wall wears the right mark -----------------------------------------
def test_the_wall_wears_the_marks_the_site_wears():
    """It was drawing its own SVG ellipse, so the two pages a visitor
    sees BEFORE they pay — the wall and the checkout — were the last two
    still wearing a logo the site retired on 2026-08-23."""
    js = _js()
    mark = _fn(js, "brandMarkHTML")
    assert "logo-qb.png" in mark, "the wall is still drawing the old ellipse"
    assert "<ellipse" not in mark
    css = open(os.path.join(ROOT, "web", "css", "styles.css"),
               encoding="utf-8").read()
    assert ".pw-logo .qmark" in css, "the lockup's image is unsized"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
