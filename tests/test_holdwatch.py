"""The one-sided hold: journaled, settled, measured — never invented.

Ethan circled the anytime-TD card's caveat (2026-08-26): "the vig is
assumed at 6% rather than measured off both prices." A Yes-only market
has no two-way pair to read, so the only honest measurement is the whole
quoted board settled against what actually happened — which is exactly
what engine/holdwatch journals. What this file pins:

  * ONLY IDENTITIES AND PRICES enter the journal — no projection, no
    model output, nothing a subscriber pays for.
  * A WEEK SETTLES ONLY WHEN PLAYED, a quoted scratch is a VOID (books
    refund those tickets; counting them as juice would inflate the fit).
  * THE GATE AND THE RAILS hold: no fit below MIN_SETTLED, no fit
    outside sane hold territory, and the pricing path falls back to the
    conservative assumption whenever the measurement is not ready.

Run directly: `python3 tests/test_holdwatch.py`
"""

import json
import os
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db, holdwatch                             # noqa: E402
from engine.models import SportsbookLine                     # noqa: E402
from engine.odds import american_to_prob                     # noqa: E402


class _P:
    def __init__(self, player, market, lines):
        self.player, self.market, self.lines = player, market, lines


def _line(odds, book="dk"):
    return SportsbookLine(book=book, line=0.5, over_odds=odds)


def _setup():
    tmp = tempfile.mkdtemp()
    conn = db.connect(os.path.join(tmp, "h.db"))
    # STATE_PATH is repo-relative; point it into the tempdir so a test
    # run can never write a measured hold into the working tree.
    holdwatch.STATE_PATH = os.path.join(tmp, "hold.json")
    holdwatch._cache.clear()
    return conn


def _td_row(player, period, value, sport="nfl", market="anytime_td"):
    return {"sport": sport, "season": 2026, "period": str(period),
            "player": player, "team": "TB", "market": market,
            "value": value, "opponent": "NO", "home": 1}


def test_the_journal_takes_identities_and_prices_only():
    conn = _setup()
    slate = types.SimpleNamespace(props=[
        _P("Rachaad White", "anytime_td", [_line(+140), _line(+150, "fd")]),
        _P("Chris Godwin", "rec_yds", [_line(-110)]),
        _P("Unpriced Guy", "anytime_td", []),
    ])
    n = holdwatch.record_slate(conn, slate, "nfl", 2026, "001")
    assert n == 2, "one TD player at two books is two quotes, nothing else"
    cols = [c[1] for c in conn.execute("PRAGMA table_info(quote_board)")]
    for word in ("model", "prob", "edge", "projection"):
        assert not any(word in c for c in cols), \
            f"the journal grew a {word} column — that is paid content"


def test_a_rebuild_overwrites_with_the_fresher_price():
    conn = _setup()
    s1 = types.SimpleNamespace(props=[_P("Bucky Irving", "anytime_td",
                                         [_line(+120)])])
    s2 = types.SimpleNamespace(props=[_P("Bucky Irving", "anytime_td",
                                         [_line(+105)])])
    holdwatch.record_slate(conn, s1, "nfl", 2026, "001")
    holdwatch.record_slate(conn, s2, "nfl", 2026, "001")
    rows = conn.execute("SELECT odds FROM quote_board").fetchall()
    assert [r["odds"] for r in rows] == [105], \
        "the journal should hold the LAST quote seen, once"


def test_settlement_waits_for_the_week_and_voids_the_scratches():
    conn = _setup()
    slate = types.SimpleNamespace(props=[
        _P("Scorer", "anytime_td", [_line(+150)]),
        _P("Blanked", "anytime_td", [_line(+300)]),
        _P("Scratched", "anytime_td", [_line(+400)]),
    ])
    holdwatch.record_slate(conn, slate, "nfl", 2026, "001")
    assert holdwatch.settle(conn) == 0, \
        "an unplayed week settled — those quotes have no truth to grade against"
    db.upsert_player_logs(conn, [_td_row("Scorer", "001", 1.0),
                                 _td_row("Blanked", "001", 0.0)])
    holdwatch.settle(conn)
    out = {r["player"]: (r["settled"], r["outcome"]) for r in conn.execute(
        "SELECT player, settled, outcome FROM quote_board")}
    assert out["Scorer"] == (1, 1.0)
    assert out["Blanked"] == (1, 0.0)
    assert out["Scratched"] == (1, None), \
        "a scratch must settle as a VOID, not wait forever or count as a miss"


def test_the_period_key_is_whatever_that_sports_logs_use():
    """The first cut stored an INTEGER week and formatted it "%03d" at
    settle time — the NFL's shape wearing a general name, under which no
    MLB or CFB quote could ever have joined. `period` is TEXT and holds
    exactly what player_game_logs holds."""
    conn = _setup()
    slate = types.SimpleNamespace(props=[
        _P("Shohei Ohtani", "home_runs", [_line(+310)])])
    holdwatch.record_slate(conn, slate, "mlb", 2026, "2026-08-30",
                           market="home_runs")
    # Read AFTER the lazy create — the table does not exist before it.
    cols = {c[1] for c in conn.execute("PRAGMA table_info(quote_board)")}
    assert "period" in cols and "week" not in cols
    db.upsert_player_logs(conn, [_td_row("Shohei Ohtani", "2026-08-30", 1.0,
                                         sport="mlb", market="home_runs")])
    assert holdwatch.settle(conn, sport="mlb", market="home_runs") == 1
    row = conn.execute("SELECT outcome FROM quote_board").fetchone()
    assert row["outcome"] == 1.0, "an MLB date-keyed quote could not settle"


def test_each_market_fits_its_own_hold():
    """A touchdown book and a home-run book do not price the same juice,
    and the pricing path asks per (sport, market) — so a fit must never
    leak across either."""
    conn = _setup()
    slate = types.SimpleNamespace(props=[
        _P(f"HR{i}", "home_runs", [_line(+300)]) for i in range(60)])
    holdwatch.record_slate(conn, slate, "mlb", 2026, "2026-08-30",
                           market="home_runs")
    db.upsert_player_logs(conn, [
        _td_row(f"HR{i}", "2026-08-30", 1.0 if i < 14 else 0.0,
                sport="mlb", market="home_runs") for i in range(60)])
    holdwatch.settle(conn, sport="mlb", market="home_runs")
    keep = holdwatch.MIN_SETTLED
    try:
        holdwatch.MIN_SETTLED = 20
        got = holdwatch.fit(conn, sport="mlb", market="home_runs")
        assert got, "the MLB home-run hold never fit"
        assert holdwatch.load_hold("mlb", "home_runs")
        assert holdwatch.load_hold("nfl", "anytime_td") is None, \
            "one market's hold leaked into another's"
    finally:
        holdwatch.MIN_SETTLED = keep


def test_the_scorer_quote_shape_journals_too():
    """CFB's TD board never becomes a slate of Props — the pull returns
    quotes keyed by player, so it reaches the same journal by the other
    door."""
    conn = _setup()
    n = holdwatch.record_quotes(conn, {
        "jeremiah smith": [{"book": "dk", "yes_odds": 120, "no_odds": None},
                           {"book": "fd", "yes_odds": 115}],
        "no price": [{"book": "dk", "yes_odds": None}],
    }, sport="cfb", season=2026, period="2026-08-30")
    assert n == 2, "a quote with no Yes price was journaled"


def test_settlement_normalizes_both_sides_of_the_name():
    """The join CFB actually needs: its scorer pull keys players by the
    NORMALIZED name (the board never sees another form), while the stat
    rows carry what ESPN's box score wrote. Both sides go through the
    same normalizer at settle time or no CFB quote settles at all."""
    conn = _setup()
    holdwatch.record_quotes(conn, {"jeremiah smith": [{"book": "dk",
                                                       "yes_odds": 150}]},
                            sport="cfb", season=2026, period="2026-08-30")
    db.upsert_player_logs(conn, [_td_row("Jeremiah Smith", "2026-08-30", 1.0,
                                         sport="cfb")])
    assert holdwatch.settle(conn, sport="cfb") == 1
    row = conn.execute("SELECT outcome FROM quote_board").fetchone()
    assert row["outcome"] == 1.0, "the normalized join failed"


def test_the_fit_measures_the_hold_and_keeps_its_gate_and_rails():
    conn = _setup()
    # A deterministic board: 100 players at +300 (implied 0.25), of whom
    # exactly 23 score — the market overstated by 25/23, a 8.7% hold.
    slate = types.SimpleNamespace(props=[
        _P(f"P{i}", "anytime_td", [_line(+300)]) for i in range(100)])
    holdwatch.record_slate(conn, slate, "nfl", 2026, "001")
    db.upsert_player_logs(conn, [
        _td_row(f"P{i}", "001", 1.0 if i < 23 else 0.0) for i in range(100)])
    holdwatch.settle(conn)
    keep = holdwatch.MIN_SETTLED
    try:
        assert holdwatch.fit(conn) is None, "the sample gate did not hold"
        holdwatch.MIN_SETTLED = 50
        fit = holdwatch.fit(conn)
        want = (100 * american_to_prob(300)) / 23
        assert fit and abs(fit["hold"] - want) < 0.001, fit
        assert fit["n"] == 100
        # the rails: a nonsense ratio (half the board "scored") writes nothing
        conn.execute("UPDATE quote_board SET outcome=1.0")
        conn.commit()
        assert holdwatch.fit(conn) is None, \
            "a hold below the rails was believed — that is a data bug, not a market"
    finally:
        holdwatch.MIN_SETTLED = keep


def test_the_pricing_path_prefers_measured_and_survives_no_file():
    from engine import longshots
    conn = _setup()
    assert longshots.one_sided_hold("nfl", "anytime_td") == \
        (longshots.ONE_SIDED_HOLD, 0), \
        "with nothing measured the conservative assumption must price"
    with open(holdwatch.STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump({"nfl:anytime_td": {"hold": 1.083, "n": 1200}}, fh)
    holdwatch._cache.clear()
    assert longshots.one_sided_hold("nfl", "anytime_td") == (1.083, 1200)
    # a corrupt state file costs the measurement, never the board
    with open(holdwatch.STATE_PATH, "w", encoding="utf-8") as fh:
        fh.write("{broken")
    holdwatch._cache.clear()
    assert longshots.one_sided_hold("nfl", "anytime_td") == \
        (longshots.ONE_SIDED_HOLD, 0)


def test_the_card_says_which_number_it_is_wearing():
    src = open(os.path.join(ROOT, "engine", "longshots.py"),
               encoding="utf-8").read()
    i = src.index("def build_pick")
    body = src[i:src.index("\ndef ", i)]
    assert "It is measured instead" in body
    assert "assumed at {hold - 1:.0%}" in body
    assert "one_sided_hold(sport, market)" in body
    # AND THE FALLBACK NAMES BOTH FAILURES. There are three ways to know
    # the margin — a two-way pair, the game's own scorer board, or a
    # standing number — so reaching the standing number means BOTH
    # measurements were unavailable. The copy used to blame the missing
    # NO side alone, which left a reader thinking a two-sided quote was
    # all that stood between them and a measured hold.
    assert "couldn't be measured either" in body
    # Matched on a contiguous fragment: the sentence wraps across two
    # source lines, so a phrase spanning the break is never in the text.
    assert "is still filling in" in body


def test_the_build_and_the_chores_carry_the_journal():
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert "holdwatch.record_slate(" in build, \
        "the build stopped journaling the quoted board"
    mlb = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    assert '_hw.record_slate(' in mlb and 'market="home_runs"' in mlb, \
        "the home-run board stopped journaling its quotes"
    cfb = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()
    assert "_hw.record_quotes(" in cfb, \
        "the CFB TD board stopped journaling its quotes"
    maint = open(os.path.join(ROOT, "engine", "maintenance.py"),
                 encoding="utf-8").read()
    assert "_hw.settle(" in maint and "_hw.fit(" in maint, \
        "nothing settles or refits the journal"
    from engine import maintenance as _mt
    assert set(_mt.HOLD_MARKETS) == {("nfl", "anytime_td"),
                                     ("mlb", "home_runs"),
                                     ("cfb", "anytime_td")}
    # OUTSIDE the NFL-season guard: baseball settles from April, and a
    # journal that only ran Aug-Feb would bin a summer of quotes.
    i = maint.index("for _hsport, _hmarket in HOLD_MARKETS")
    guard = maint.index("if today.month >= 8 or today.month <= 2:")
    assert i > guard, "the loop is in the file"
    assert not maint[i - 400:i].rstrip().endswith(":"), \
        "the settle loop is nested inside a seasonal guard again"


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
