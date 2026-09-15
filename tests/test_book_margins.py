"""What each book charges, and the claim that idea replaced.

The build this file guards started as something else: an exchange
DETECTOR, auto-promoting a near-zero-vig book to the top of
`potd.EVIDENCE` on the theory that de-vigging a book means assuming how
its margin is shared across the two sides, and a book with no margin
needs no assumption.

The premise was measured before it was built and it did not survive.
`bookvig.assumption_points` is that measurement, kept: inside the Pick
of the Day band a sharp book’s pair moves by under four tenths of a
point across the three standard de-vigs — a fifth of `potd.MIN_EV`.
Not a reason to move a book a whole tier.

So what shipped measures and stores; it does not promote. These tests
hold BOTH halves of that, because the second half is the one a future
change would break without noticing: a census that quietly started
pricing bets would look like a feature.

Run directly: `python3 tests/test_book_margins.py`
"""

import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import book_margins                                           # noqa: E402
from engine import bookvig, potd                              # noqa: E402
from engine.odds import american_to_prob                      # noqa: E402


def _event(**books):
    """One h2h event carrying a named price pair per book."""
    return {"bookmakers": [
        {"key": key, "markets": [{"key": "h2h", "outcomes": [
            {"name": "Home Club", "price": pair[0]},
            {"name": "Away Club", "price": pair[1]}]}]}
        for key, pair in books.items()]}


# ── what a margin is ────────────────────────────────────────────────

def test_an_even_pair_at_minus_110_charges_what_the_arithmetic_says():
    """-110/-110 is the canonical 4.76% hold. A census that got this
    wrong would mis-rank every book against every other."""
    got = bookvig.pair_overround(-110, -110)
    assert got is not None and abs(got - 1.0476) < 0.0005, got


def test_a_one_sided_quote_has_no_measurable_margin():
    """There is no second price to measure the first against, and
    assuming one is the move this whole module exists to size."""
    assert bookvig.pair_overround(-110, None) is None
    assert bookvig.pair_overround(-110, 0) is None


def test_a_book_quoting_an_arbitrage_against_itself_is_refused():
    """One book posting +150/+150 is a data error — a stale side or two
    different lines parsed as one — not a generous venue. De-vig
    arithmetic on it returns confident nonsense rather than failing, so
    the refusal has to happen here."""
    assert american_to_prob(150) * 2 < bookvig.MIN_OVERROUND
    assert bookvig.pair_overround(150, 150) is None


def test_a_market_with_a_suspended_side_is_refused_at_the_top_end():
    assert bookvig.pair_overround(-10000, -10000) is None


# ── the measurement that replaced the feature ───────────────────────

def test_at_even_money_every_devig_agrees_however_big_the_margin():
    """THE SHAPE OF THE WHOLE FINDING. All three methods must return two
    numbers summing to one, and at a true 50/50 the only such answer is
    50/50 — so they cannot disagree, whatever the vig. Which is why the
    exchange tier could not be justified on de-vig grounds: this
    feature’s band is pinned near even money by construction."""
    for pair in ((-110, -110), (-150, -150), (-102, -102)):
        assert bookvig.assumption_points(*pair) == 0.0, pair


def test_a_sharp_books_pair_costs_under_a_point_across_the_whole_band():
    """The number the module docstring turns on, and the reason nothing
    got promoted. If a change ever makes this large, the exchange tier
    HAS an argument again and the docstring is wrong.

    ACROSS THE WHOLE BAND, which the first version of this test did not
    do: it asserted a single -150/+132 pair (a fair near 0.58) and read
    as though it covered the band. The plus-money end at +190 implies
    0.345, where the same margin moves nearly twice as far. A test that
    samples the comfortable end of a range is how a docstring ends up
    quoting a number half the size of the real one."""
    lo = american_to_prob(potd.MAX_ODDS)
    hi = american_to_prob(potd.MIN_ODDS)

    def american(p):
        return int(round(-100 * p / (1 - p))) if p >= 0.5 \
            else int(round(100 * (1 - p) / p))

    worst, at, n = 0.0, None, 0
    for step in range(0, 241):
        fair = lo + (hi - lo) * step / 240.0
        for overround in (1.01, 1.02, 1.03):
            got = bookvig.assumption_points(american(fair * overround),
                                            american((1.0 - fair) * overround))
            if got is None:
                continue
            n += 1
            if got > worst:
                worst, at = got, fair
    assert n > 500, f"the sweep stopped covering the band: {n} pairs"
    assert worst < 1.0, (worst, at)
    assert worst < potd.MIN_EV * 100 / 2.0, (worst, at, potd.MIN_EV)


def test_the_disagreement_is_driven_by_distance_from_even_money():
    """Not by the size of the vig, which is the counter-intuitive half.
    A +900 longshot at a TIGHTER hold disagrees by many times more than
    a -150 favourite at a wider one."""
    longshot = bookvig.assumption_points(900, -2000)
    favourite = bookvig.assumption_points(-150, 132)
    assert longshot > favourite * 5, (longshot, favourite)


def test_all_three_devigs_are_present_and_none_of_them_agree():
    """`assumption_points` is the SPREAD of three methods, so it stays
    small and reassuring if a method quietly stops being computed or
    starts duplicating another. Two mutants proved that: dropping the
    power de-vig, and making the additive one a copy of the
    proportional, both left every magnitude test in this file passing.

    Measured on a lopsided pair, where the methods are supposed to
    disagree — at even money they legitimately do not, which is the
    finding this module exists to record."""
    ms = bookvig.devig_methods(-300, 240)
    assert set(ms) == {"proportional", "additive", "power"}, ms
    rounded = {round(v, 6) for v in ms.values()}
    assert len(rounded) == 3, ms


def test_no_devig_can_return_something_that_is_not_a_probability():
    """The invariant that makes `assumption_points` mean anything: it is
    the spread of three PROBABILITIES, so a method escaping (0,1) would
    make the gap between them arithmetic rather than disagreement.

    Nothing enforces this — a filter that did was removed as dead code,
    because it cannot happen. With S = ra + rb, an additive de-vig goes
    negative only if ra + 1 < rb, and rb < 1 always; it exceeds one only
    if ra - rb > 1, and ra < 1 always. This walks a lopsided grid to say
    so out loud, since the proof lives in a comment and comments do not
    run."""
    worst_lo, worst_hi, n = 1.0, 0.0, 0
    for a in (-20000, -5000, -800, -300, -150, -120, -105):
        for b in (105, 120, 150, 300, 800, 5000, 20000,
                  -105, -120, -150, -300, -20000):
            ms = bookvig.devig_methods(a, b)
            if not ms:
                continue
            n += 1
            worst_lo = min(worst_lo, min(ms.values()))
            worst_hi = max(worst_hi, max(ms.values()))
    # A FLOOR ON THE GRID ITSELF. Most of these pairs are refused by
    # the band guard, which is correct — and it means a change that
    # refused EVERYTHING would leave this test passing vacuously.
    assert n >= 30, f"the grid stopped covering anything: {n} pairs"
    assert 0.0 < worst_lo and worst_hi < 1.0, (worst_lo, worst_hi)


# ── the census ──────────────────────────────────────────────────────

def test_every_book_on_an_event_is_measured_not_just_the_sharp_one():
    """The loop this rides on kept one book in seventeen. If it goes
    back to doing that, the census silently becomes a Pinnacle report."""
    got = bookvig.overrounds(
        _event(pinnacle=(-150, 132), draftkings=(-155, 130),
               novig=(-143, 141)), {})
    assert set(got) == {"Pinnacle", "DraftKings", "Novig"}, got
    assert got["Novig"] < got["Pinnacle"] < got["DraftKings"], got


def test_a_team_name_the_map_does_not_know_is_still_measured():
    """College football builds its team map at runtime and UFC has none
    at all. A census that needed one would silently exclude exactly the
    leagues nobody has ever measured a book’s margin on."""
    got = bookvig.overrounds(_event(pinnacle=(-150, 132)), {})
    assert got == {"Pinnacle": 1.031}, got


def test_a_three_way_market_is_never_paired():
    """The two-outcome check is what makes the loose team key safe: with
    a draw in the payload there is no pair, and inventing one would
    report a fictional margin."""
    ev = {"bookmakers": [{"key": "pinnacle", "markets": [{"key": "h2h",
          "outcomes": [{"name": "A", "price": -150},
                       {"name": "B", "price": 132},
                       {"name": "Draw", "price": 300}]}]}]}
    assert bookvig.overrounds(ev, {}) == {}


def test_the_census_adopts_its_store_rather_than_copying_it():
    """Three builds accumulate into a plain dict on a dataclass, wrapping
    it per event. A Census that copied would count every game and report
    none of them."""
    store: dict = {}
    for _ in range(3):
        bookvig.Census(store).add_event(_event(pinnacle=(-150, 132)), {})
    assert bookvig.Census(store).summary()["Pinnacle"]["games"] == 3, store


def test_one_suspended_market_cannot_describe_a_books_whole_slate():
    """The median, for the reason `consensus_h2h_fair` gives one level
    up. A mean would let a single 20% hold move the book’s figure."""
    c = bookvig.Census()
    for _ in range(9):
        c.add("Some Book", 1.04)
    c.add("Some Book", 1.24)
    assert c.summary()["Some Book"]["median"] == 1.04
    assert c.summary()["Some Book"]["max"] == 1.24


def test_a_book_we_asked_for_and_never_saw_is_named_not_counted():
    """The point of the census. "3 books missing" sends somebody to the
    source to find out which; the names are the whole answer."""
    c = bookvig.Census()
    c.add_event(_event(pinnacle=(-150, 132)), {})
    gone = c.missing(("pinnacle", "novig", "prophetx"))
    assert gone == ["Novig", "ProphetX"], gone


def test_three_keys_for_one_book_are_not_three_missing_books():
    """espnbet, thescorebet and thescore are the same book renamed
    twice. Asking for all three is right — they cost nothing and one of
    them resolves — but reporting it three times is not."""
    gone = bookvig.Census().missing(("espnbet", "thescorebet", "thescore"))
    assert gone == ["theScore Bet"], gone


def test_a_census_that_read_nothing_says_so_rather_than_printing_blank():
    """The failure shape this repository keeps finding in itself —
    `lineledger.record_note` and the rankings section were both dragged
    out of it."""
    out = bookvig.report(bookvig.Census(), "nfl")
    assert out.strip(), "a silent census is the bug, not the empty case"
    assert "no book quoted both sides" in out, out


# ── it measures; it must never price ────────────────────────────────

def test_nothing_in_the_pick_selector_reads_a_books_margin():
    """THE LOAD-BEARING REFUSAL. The measurement says a tier promotion
    is not earned; this is what stops one arriving by accident later.
    A census that quietly started choosing picks would look like a
    feature rather than an unmeasured pricing change."""
    body = inspect.getsource(potd)
    assert "bookvig" not in body, "the selector has started reading margins"
    assert "overround" not in body, "the selector has started reading margins"


def test_the_ladder_still_ranks_evidence_not_margin():
    assert potd.EVIDENCE == ("exchange", "sharp", "market", "model"), \
        potd.EVIDENCE


# ── the field must not be dead ──────────────────────────────────────

def test_every_build_that_measures_margins_also_prints_them():
    """A field written and never read is a failure this repository has
    caught in itself before — the sharp-book list check was computed and
    never shown, and the rankings section returned "" for a month.

    The census rides along inside a loop that was already running, which
    makes it cheap AND makes it easy to leave unwired: nothing breaks,
    the board looks fine, and the number nobody can see is the number
    that would have said a book key stopped resolving.

    COUNTED, NOT MERELY PRESENT. The first version of this asked whether
    the string "bookvig.report(" appeared at all, which the NFL build
    passes with one of its two censuses unwired — and two pulls is
    exactly where one would go quiet. Every census a build constructs
    has to be reported."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checked = 0
    for build in ("nfl_build.py", "mlb_build.py", "cfb_build.py"):
        with open(os.path.join(here, build), encoding="utf-8") as fh:
            src = fh.read()
        built = src.count("bookvig.Census(")
        if not built:
            continue                      # this build does not measure
        checked += 1
        assert src.count("bookvig.report(") == built, (
            f"{build} builds {built} margin census(es) and prints "
            f"{src.count('bookvig.report(')}")
    assert checked == 3, f"only {checked} build(s) measure margins"


def test_the_two_nfl_pulls_are_counted_apart():
    """The event pull and the board pull ask for different markets and
    can return different books. One merged figure would hide a book that
    answers one and not the other, which is the whole question."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, "nfl_build.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert '"book_margins"' in src and '"board_book_margins"' in src, \
        "the NFL build no longer separates its two pulls' margins"


# ── the droplet tool ────────────────────────────────────────────────

def test_a_board_pull_with_no_cache_tag_is_filed_under_its_league():
    """`odds_board_mlb.json` has nothing after the league, so splitting
    the basename on "_" returned "mlb.json" and carried it into every
    heading and the --sports filter. Found by running the thing."""
    assert book_margins.sport_of("odds_board_mlb.json") == "mlb"
    assert book_margins.sport_of("odds_board_nfl_early.json") == "nfl"
    assert book_margins.sport_of("odds_event_cfb_abc_9f3.json") == "cfb"
    assert book_margins.sport_of("games.csv") == ""


def test_the_census_counts_each_event_once_not_once_per_book():
    """`Census.add_event` walks the whole payload itself — every book in
    it, in one call. Putting that call inside the per-book loop that sits
    above it adds the same event once for each bookmaker quoting it, so
    on a well-covered game every margin is counted fifteen-odd times.

    IT READ PLAUSIBLY ANYWAY, which is why it survived. Each book in an
    event is over-counted by the SAME factor, so the ORDER of the margins
    — the only thing the report is really for — came out right; only the
    row counts were wrong, and wrong by a different multiple per sport
    and per slate, so there was nothing to compare them against.

    Checked on the SYNTAX TREE rather than by eye or by indentation
    string: the two call sites are three hundred lines apart in
    `oddsapi`, one of them drifted a level in, and the invariant is
    exactly "this call is not inside that loop"."""
    import ast
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(here, "engine", "sources", "oddsapi.py"),
               encoding="utf-8").read()

    def _calls(node, name):
        return [n for n in ast.walk(node) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == name]

    tree = ast.parse(src)
    loops = [n for n in ast.walk(tree) if isinstance(n, ast.For)
             and _calls(n.iter, "items")
             and "parse_event_h2h_by_book" in ast.dump(n.iter)]
    assert len(loops) == 2, f"the per-book loops moved: found {len(loops)}"
    for loop in loops:
        inside = [c for stmt in loop.body for c in _calls(stmt, "add_event")]
        assert not inside, (
            "bookvig.Census(...).add_event is inside the per-book loop — "
            "every event is counted once per bookmaker")

    # And it is still called — a fix that simply deleted it would pass the
    # assertion above and silently stop measuring anything.
    assert len(_calls(tree, "add_event")) == 2, \
        "both pull paths should still feed the census exactly once"


def test_a_cache_name_with_no_league_in_it_is_filed_under_no_league():
    """The droplet holds hundreds of `odds_event_<EVENTID>_<tag>.json`
    with no sport in the name at all. Returning the token in that
    position made the report print several hundred hex-string
    "leagues", each saying no book quoted both sides, with the four
    real ones buried in the middle. Found by running it on the box."""
    hexed = "odds_event_8F42799432660532A3E011A06B8356_1a2b.json"
    assert book_margins.sport_of(hexed) == ""

    # And the guard is the one list of leagues we pull, not a hex test:
    # a plausible-looking token that is not a league we buy is still no
    # league, or the next name shape reopens the same hole.
    assert book_margins.sport_of("odds_event_soccer_abc_9f3.json") == ""
    assert book_margins.sport_of("odds_board_epl.json") == ""

    # Every league we do pull survives the guard. Spelled from the
    # config rather than a list here, so adding a sport cannot make
    # this tool quietly stop reporting it.
    from engine.sources.oddsapi import SPORT_CONFIG
    for league in SPORT_CONFIG:
        assert book_margins.sport_of(f"odds_board_{league}.json") == league
        assert book_margins.sport_of(f"odds_event_{league}_abc_9f3.json") == league


def test_both_cached_payload_shapes_are_read():
    """A board pull is a LIST of events; an event pull is ONE event
    object. A reader that handled either alone would report a book as
    missing because its payloads happened to be the other shape."""
    one = _event(pinnacle=(-150, 132))
    assert len(book_margins.events_in(one)) == 1
    assert len(book_margins.events_in([one, one])) == 2
    assert len(book_margins.events_in({"data": [one]})) == 1
    assert book_margins.events_in({"message": "no key"}) == []
    assert book_margins.events_in(None) == []


def test_the_tool_says_where_to_look_when_the_cache_is_empty():
    """On a box with no pulls this prints something a person can act on
    rather than nothing at all."""
    out = book_margins.render({}, ())
    assert "data/cache" in out and out.strip(), out


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
