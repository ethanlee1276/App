"""The exchange's own number, and the guards that decide it is worth using.

Ethan, 2026-09-15: "I want to make sure that we're using every single
piece of data."

WE WERE ALREADY PULLING THE BEST ONE AND NOT USING IT. `sources/kalshi`
fetches a CFTC-regulated exchange, parses its order book, matches a
market to one of our games and knows which side the YES contract is —
and it fed the Prediction Desk and nothing else. The Pick of the Day, a
feature built entirely around finding a trustworthy fair, never saw it.

WHY THIS RANKS ABOVE THE SHARP BOOK, which is the claim most worth
guarding: de-vigging Pinnacle means ASSUMING how its margin is spread
across the two sides. An exchange has no margin to strip. That is the
only reason for the ordering, and if the guards below ever stop holding
then the ordering becomes a way to prefer a worse number — so the
guards are the test, not the plumbing.

Run directly: `python3 tests/test_exchange_fair.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import exchangefair as X, potd                    # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _mkt(**kw):
    """A healthy two-sided exchange market."""
    m = {"ticker": "KXMLBGAME-26SEP15SEALAA-LAA", "title": "Angels vs Mariners",
         "subtitle": "Los Angeles Angels", "prob": 0.58, "price_basis": "book",
         "spread_cents": 2.0, "volume_24h": 4000.0, "open_interest": 1200.0}
    m.update(kw)
    return m


# --- the guards, which are the whole argument --------------------------------
def test_a_healthy_book_is_usable():
    assert X.quality(_mkt()) == ""


def test_a_last_trade_is_not_a_market_opinion():
    """`kalshi.parse_markets` says it itself: "a fair value with no book
    behind it is a weaker claim". One stale print on a market nobody has
    touched since Tuesday is not the exchange's number."""
    why = X.quality(_mkt(price_basis="last_trade", spread_cents=None))
    assert "no two-sided book" in why, why


def test_a_wide_book_cannot_settle_a_question_this_fine():
    """THE ARITHMETIC, executed. A book 10 cents wide puts the true
    number five points either side of the mid; `potd.MIN_EV` asks for
    two. A guard wider than the edge it protects is not a guard.

    IF THE CONFIDENCE FLOOR EVER BECOMES THE BINDING BAR — `MIN_FAIR` is
    the one constant `--sweep-conf` exists to raise — this comparison
    moves with it: the exchange's own bid/ask width must not be big
    enough to be the reason a pick looks confident either. Half a
    four-cent spread is two points, so a floor set less than four points
    above a coin flip would need the cap tightened."""
    assert X.MAX_SPREAD_CENTS / 100.0 <= potd.MIN_EV * 2, (
        "the spread cap admits more slop than the EV floor asks for")
    assert X.quality(_mkt(spread_cents=X.MAX_SPREAD_CENTS)) == ""
    why = X.quality(_mkt(spread_cents=X.MAX_SPREAD_CENTS + 0.5))
    assert "wide" in why, why


def test_a_thin_book_is_two_people_not_a_market():
    why = X.quality(_mkt(volume_24h=10.0, open_interest=5.0))
    assert "thin" in why, why
    # Either measure clearing the floor is enough — open interest with no
    # volume today is still real money on the line.
    assert X.quality(_mkt(volume_24h=0.0,
                          open_interest=X.MIN_LIQUIDITY + 1)) == ""


def test_an_unreadable_market_is_refused_rather_than_guessed_at():
    for bad in ({"price_basis": "book", "spread_cents": "x"},
                {"price_basis": "book", "spread_cents": None}):
        assert X.quality(_mkt(**bad)) != ""


# --- which side is which, where an error would look like confidence ----------
def test_the_yes_side_and_the_other_side_are_not_confused():
    """A side error here would not read as a bug. It would read as a
    confident pick on the wrong team."""
    game = {"home": "LAA", "away": "SEA", "home_name": "Los Angeles Angels",
            "away_name": "Seattle Mariners"}
    m = _mkt(prob=0.58)
    laa = X.fair_for_team(m, "LAA", game)
    sea = X.fair_for_team(m, "SEA", game)
    if laa is None and sea is None:
        # The matcher could not name a side on this fixture; the function
        # must then price NEITHER rather than guess one.
        return
    assert laa is not None and sea is not None, (laa, sea)
    assert abs((laa + sea) - 1.0) < 1e-9, (laa, sea)
    assert 0.0 < laa < 1.0 and 0.0 < sea < 1.0


def test_a_team_the_contract_says_nothing_about_is_priced_at_nothing():
    """THE GUARD THAT SURVIVED A MUTANT until this test existed. A
    game-winner contract settles two outcomes and names both. Asked
    about a third team, the honest answer is silence — returning either
    `p` or `1-p` would be inventing a price for a club the market has no
    opinion on, and it would arrive on the board looking exactly like a
    real one."""
    game = {"home": "LAA", "away": "SEA", "home_name": "Los Angeles Angels",
            "away_name": "Seattle Mariners"}
    m = _mkt(prob=0.58)
    assert X.fair_for_team(m, "NYY", game) is None
    assert X.fair_for_team(m, "", game) is None
    # And a game missing a side cannot name the other one either.
    assert X.fair_for_team(m, "LAA", {"home": "LAA", "away": ""}) is None


def test_an_impossible_probability_prices_nothing():
    game = {"home": "LAA", "away": "SEA"}
    for bad in (0.0, 1.0, -0.2, 1.4, None, "x"):
        assert X.fair_for_team(_mkt(prob=bad), "LAA", game) is None, bad


# --- what it will and will not speak to --------------------------------------
def test_only_the_moneyline_is_priced_from_a_game_winner_contract():
    """Kalshi lists who wins. It does not list our run line, and letting
    a win probability settle a spread is the silent coercion this
    codebase keeps finding in its own history."""
    assert X.MARKETS == ("moneyline",)
    rows = [{"market": "spread", "team": "LAA"},
            {"market": "total", "team": "LAA"}]
    census = X.attach(rows, [_mkt()], [{"home": "LAA", "away": "SEA"}], "mlb")
    assert census["rows"] == 0, "a non-moneyline row was considered"
    assert all("exchange_fair" not in r for r in rows)


def test_a_row_it_cannot_match_is_left_exactly_as_it_was():
    row = {"market": "moneyline", "team": "NYY", "model_prob": 0.6}
    before = dict(row)
    X.attach([row], [_mkt()], [{"home": "LAA", "away": "SEA"}], "mlb")
    assert row == before or "exchange_fair" not in row


def test_the_census_says_which_guard_rejected_a_market():
    census = X.attach([{"market": "moneyline", "team": "LAA"}],
                      [_mkt(spread_cents=30.0), _mkt(volume_24h=1.0,
                                                     open_interest=1.0)],
                      [{"home": "LAA", "away": "SEA"}], "mlb")
    assert census["usable markets"] == 0
    reasons = [k for k in census if k not in ("rows", "attached", "usable markets")]
    assert reasons, census
    assert any("wide" in r for r in reasons), reasons
    assert any("thin" in r for r in reasons), reasons


# --- the tier, and the ordering that makes it worth anything -----------------
def test_the_exchange_outranks_the_sharp_book_and_carries_its_own_number():
    row = {"exchange_fair": 0.58, "sharp_anchored": True, "sharp_fair": 0.55,
           "implied_prob": 0.52, "model_prob": 0.61, "odds": -110}
    assert potd.evidence(row) == "exchange"
    assert potd.fair_prob(row) == 0.58, "it must price on the exchange's number"
    assert potd.EVIDENCE.index("exchange") < potd.EVIDENCE.index("sharp")


def test_without_an_exchange_number_the_ladder_is_unchanged():
    """The new rung must not disturb the three below it."""
    sharp = {"sharp_anchored": True, "sharp_fair": 0.6, "odds": -110}
    assert potd.evidence(sharp) == "sharp" and potd.fair_prob(sharp) == 0.6
    mkt = {"prob_source": "market", "implied_prob": 0.56, "odds": -110}
    assert potd.evidence(mkt) == "market" and potd.fair_prob(mkt) == 0.56
    ours = {"model_prob": 0.7, "odds": -110}
    assert potd.evidence(ours) == "model"


def test_every_build_prices_the_board_BEFORE_it_picks():
    """THE ORDER IS LOAD-BEARING AND ITS FAILURE IS INVISIBLE. `potd
    .attach` selects off these rows. A build that priced them afterwards
    would publish a board carrying exchange fairs and a pick chosen
    without them — no error, no empty section, nothing to notice."""
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py", "nba_build.py"):
        src = open(os.path.join(ROOT, fn), encoding="utf-8").read()
        code = "\n".join(ln for ln in src.splitlines()
                         if not ln.lstrip().startswith("#"))
        assert "exchangefair" in code, f"{fn} never prices the board"
        assert code.index("attach_to_board") < code.index("_potd.attach("), \
            f"{fn} picks before it prices"


def test_the_hook_survives_a_feed_that_is_down():
    """It fetches a live venue, so this promise does real work: an
    exchange having a bad morning costs us the tier for one build and
    nothing else."""
    import engine.sources.kalshi as k
    real = k.fetch_sports_markets
    try:
        k.fetch_sports_markets = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("kalshi is down"))
        out = {"most_likely": [{"market": "moneyline", "team": "LAA"}],
               "games": []}
        note = X.attach_to_board(out, "mlb")
        assert "unavailable" in note and "kalshi is down" in note, note
        assert out["exchange_fair_error"], "the failure must reach the JSON"
    finally:
        k.fetch_sports_markets = real


# ── the names the matcher was written against, and never got ────────

def test_the_board_gives_the_matcher_no_names_to_match_on():
    """THE PREMISE, stated first so the rest cannot pass for the wrong
    reason. `pipeline._game_to_dict` writes the board's `games`, and it
    writes abbreviations only — no `home_name`, no `away_name`. Asserted
    against the real function rather than a fixture, because a fixture
    would just be me agreeing with myself."""
    import inspect
    from engine import pipeline
    from engine.mlb import pipeline as mlb_pipeline
    for mod in (pipeline, mlb_pipeline):
        src = inspect.getsource(mod._game_to_dict)
        assert '"home_name"' not in src, (
            f"{mod.__name__}._game_to_dict now writes names — if that is "
            f"deliberate, `exchangefair.with_names` can stop filling them")


def test_a_two_letter_abbreviation_can_never_match_on_its_own():
    """WHY THE FALLBACK WAS NOT ENOUGH, and it is arithmetic rather than
    bad luck. `kalshi._name_tokens` drops anything under three characters,
    so SD, SF, LA, KC, TB, NY and NE are not tokens at all — and
    `match_game` needs BOTH teams to hit. Half of baseball could never
    match however good the exchange's book was."""
    from engine.sources import kalshi
    short = [t for t in ("SD", "SF", "LA", "KC", "TB", "NY", "NE")
             if t not in kalshi._name_tokens(f"KXMLBGAME-26SEP15LAD{t} {t}")]
    assert short == ["SD", "SF", "LA", "KC", "TB", "NY", "NE"], short


def test_attach_prices_a_board_that_carries_only_abbreviations():
    """THE MUTANT THIS EXISTS FOR. Testing `with_names` alone left
    `attach` free to stop calling it and nothing failed — the fix was
    proved and the wiring was not. This is the shape Ethan's board
    actually publishes: `{"home": "LAA", "away": "SEA"}` and no names."""
    rows = [{"market": "moneyline", "team": "LAA", "odds": -130}]
    markets = [_mkt()]
    games = [{"home": "LAA", "away": "SEA"}]
    census = X.attach(rows, markets, games, "mlb")
    assert census["attached"] == 1, census
    assert rows[0].get("exchange_fair") is not None, rows[0]


def test_the_names_are_filled_in_and_the_match_then_lands():
    """The fix, end to end, on the shape Ethan's board actually
    publishes: abbreviations and nothing else, against a market titled
    the way the exchange titles them."""
    from engine.sources import kalshi
    board_games = [{"home": "LAD", "away": "SD"}]
    market = {"title": "Will the Dodgers beat the Padres?", "subtitle": "",
              "event_ticker": "KXMLBGAME-26SEP15LADSD"}
    assert kalshi.match_game(market, board_games) is None, \
        "the premise is gone: this matched without names"
    named = X.with_names(board_games, "mlb")
    assert kalshi.match_game(market, named) is not None


def test_every_spelling_a_club_goes_by_is_carried():
    """`SPORT_CONFIG` maps more than one name to the same club — MLB has
    both "Oakland Athletics" and "Athletics" for OAK. Inverting to a
    single winner throws away whichever one the exchange happens to use.

    COMPARED AGAINST THE CONFIG, not against two words I picked. The
    first version of this asserted "Oakland" and "Athletics" were both
    present, which "Oakland Athletics" satisfies on its own — so keeping
    one spelling passed it. Every name the config maps to a club has to
    survive, and the tokens have to survive as tokens."""
    from engine.sources.oddsapi import SPORT_CONFIG
    from engine.sources.kalshi import _name_tokens
    teams = SPORT_CONFIG["mlb"]["teams"]
    names = X.names_for("mlb")
    multi = [a for a in names
             if len([n for n, ab in teams.items() if ab == a]) > 1]
    assert multi, "no club in this league has two spellings; test is moot"
    for abbr in multi:
        got = _name_tokens(names[abbr])
        for spelling, ab in teams.items():
            if ab == abbr:
                assert _name_tokens(spelling) <= got, (abbr, spelling, names[abbr])


def test_a_name_the_board_already_carries_is_not_overwritten():
    """A real name beats one looked up from three letters.

    TESTED ON A LEAGUE THAT HAS A MAP. The first version used cfb, where
    `names_for` returns {} and so nothing is ever written — an overwrite
    bug could not have been seen. Here the lookup has a different answer
    ready and must not use it."""
    board = [{"home": "LAD", "away": "SD",
              "home_name": "Brooklyn Dodgers", "away_name": "SD Padres"}]
    assert X.names_for("mlb")["LAD"] != "Brooklyn Dodgers", "fixture is moot"
    got = X.with_names(board, "mlb")
    assert got[0]["home_name"] == "Brooklyn Dodgers", got[0]
    assert got[0]["away_name"] == "SD Padres", got[0]


def test_college_has_no_map_and_does_not_invent_one():
    """188 teams and no abbreviation table; its builder stamps the names
    itself. Guessing here would be worse than leaving it alone."""
    assert X.names_for("cfb") == {}
    got = X.with_names([{"home": "SYR", "away": "CLEM"}], "cfb")
    assert not got[0].get("home_name"), got[0]


def test_it_never_mutates_the_board_it_was_handed():
    """`attach` is given the published board's own `games` list. Writing
    names into it would put a field on the page that the build did not
    put there."""
    original = {"home": "LAD", "away": "SD"}
    games = [original]
    X.with_names(games, "mlb")
    assert original == {"home": "LAD", "away": "SD"}, original


def test_a_row_that_found_no_market_is_tallied_apart_from_a_refused_one():
    """One census, two different questions, and `potd_report` has to tell
    them apart to say anything useful. Pinned on the constant so the two
    modules cannot drift to different spellings.

    ASKED OF THE CENSUS, NOT OF THE SOURCE. This used to assert the
    literal string `_tally(NO_MATCH)` appeared in `attach`, which broke
    the moment the reason was split in two and, worse, would have gone on
    passing if the tally had been moved to a branch that never runs.
    """
    assert X.NO_MATCH == "no exchange market for this game"
    census = X.attach([{"market": "moneyline", "team": "NYY",
                        "home": "BOS", "away": "NYY"}],
                      [_mkt()], [{"home": "BOS", "away": "NYY"}], "mlb")
    assert census[X.NO_MATCH] == 1, census
    assert census["attached"] == 0


# --- the census names WHICH step lost the row --------------------------------
def test_a_game_the_exchange_priced_is_not_reported_as_unmatched():
    """THE DISTINCTION THIS WAS SPLIT FOR, 2026-09-16. The NFL board
    reported nine rows, 58 usable markets and zero matches, and the
    census could not say whether that was our name matching, a stale
    board, or a side we could not resolve. Those have three different
    fixes and had one bucket.

    Here the market matches the game and the ROW's team is not a side of
    it — so the exchange did price this game, and saying "no exchange
    market for this game" would send a reader hunting for a naming bug
    that is not there."""
    game = {"home": "LAA", "away": "SEA"}
    census = X.attach([{"market": "moneyline", "team": "NYY",
                        "home": "LAA", "away": "SEA"}],
                      [_mkt()], [game], "mlb")
    assert census.get(X.NO_SIDE) == 1, census
    assert X.NO_MATCH not in census, census
    assert census["markets matched to a game"] == 1


def test_the_two_reasons_are_never_both_charged_for_one_row():
    """A row is lost at exactly one step, or the counts stop adding up
    to the rows."""
    rows = [{"market": "moneyline", "team": "NYY", "home": "LAA",
             "away": "SEA"},
            {"market": "moneyline", "team": "ZZZ", "home": "ZZZ",
             "away": "YYY"}]
    census = X.attach(rows, [_mkt()], [{"home": "LAA", "away": "SEA"}], "mlb")
    lost = census.get(X.NO_MATCH, 0) + census.get(X.NO_SIDE, 0)
    assert lost + census["attached"] == census["rows"], census


def test_an_unmatched_market_carries_both_spellings_back():
    """The only way to tell a naming problem from a stale board is to
    print what each side called the game. A census that says "0 matched"
    and nothing else costs an evening."""
    # An NFL market (so `sport_of` keeps it) naming a game the board
    # does not have — which is what a stale board or a spelling mismatch
    # both look like from here, and the reason both strings come back.
    census = X.attach([{"market": "moneyline", "team": "KC",
                        "home": "KC", "away": "BUF"}],
                      [_mkt(ticker="KXNFLGAME-25SEP07SFSEA-SF",
                            title="Angels vs Mariners", subtitle="")],
                      [{"home": "KC", "away": "BUF"}], "nfl")
    assert census["markets matched to a game"] == 0
    assert census["games on the board"] == 1
    assert census["unmatched market titles"] == ["Angels vs Mariners"]
    assert census["board matchups"] == ["BUF @ KC"]


def test_the_log_line_prints_both_spellings_when_nothing_lands():
    """…and it has to reach a reader, not just the JSON."""
    import engine.exchangefair as mod
    result = {"most_likely": [{"market": "moneyline", "team": "KC",
                               "home": "KC", "away": "BUF"}],
              "games": [{"home": "KC", "away": "BUF"}]}
    real = mod.attach
    try:
        mod.attach = lambda *a, **k: {
            "rows": 1, "attached": 0, "usable markets": 58,
            "games on the board": 1, "markets matched to a game": 0,
            mod.NO_MATCH: 1,
            "unmatched market titles": ["Angels vs Mariners"],
            "board matchups": ["BUF @ KC"]}
        import engine.sources.kalshi as kx
        fetch = kx.fetch_sports_markets
        try:
            kx.fetch_sports_markets = lambda parse: ([{"x": 1}], {})
            line = mod.attach_to_board(result, "nfl")
        finally:
            kx.fetch_sports_markets = fetch
    finally:
        mod.attach = real
    assert "Angels vs Mariners" in line, line
    assert "BUF @ KC" in line, line
    assert "1 game(s), 0 matched" in line, line
    # The sample lists are not summed into the reason counts.
    assert "unmatched market titles" not in line, line


def test_the_markets_are_matched_once_not_once_per_row():
    """A 9-row board against 58 markets used to run `match_game` 522
    times to answer 58 questions — and could not say afterwards whether
    the MARKETS had failed to match or the ROWS had, because the two were
    computed in the same loop."""
    import engine.sources.kalshi as kx
    calls = []
    real = kx.match_game
    try:
        kx.match_game = lambda m, g: (calls.append(m) or real(m, g))
        rows = [{"market": "moneyline", "team": "LAA", "home": "LAA",
                 "away": "SEA"} for _ in range(5)]
        X.attach(rows, [_mkt(), _mkt(ticker="KXMLBGAME-26SEP15NYYBOS-NYY",
                                     title="Yankees vs Red Sox")],
                 [{"home": "LAA", "away": "SEA"}], "mlb")
    finally:
        kx.match_game = real
    assert len(calls) == 2, f"{len(calls)} match_game calls for 2 markets"


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
