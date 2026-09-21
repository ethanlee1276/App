"""MLB's Most Likely board is staked, and the Edge book is walled off.

Ethan, 2026-09-19, shown the paper record and asked whether +2.1% over
586 was enough to go live: *"yeah id rather stake regardless."*

It is his money and his call, made with the arithmetic in front of him.
What the arithmetic said, and what these tests exist to keep visible:

    586 settled, 407-179, claimed 66.4% -> hit 69.5%
    paper ROI +2.1% at an implied average price of -213
    standard error +/-2.8%   ->   z = 0.75
    95% interval -3.4% .. +7.6%

Zero is inside that interval. So this file is NOT a promotion test in the
way `test_the_stale_book_can_earn_the_edge_book.py` is — that book earned
its way in past a bar. This one was let in, deliberately, below the bar,
and the tests here guard the two things that must stay true anyway:

  * THE EDGE BOOK CANNOT MOVE. `performance` reads ('main','paper'), and
    a thin signal must be able to fail in public without taking down the
    one number in this project that has been kept honest longest.
  * THE PAPER HISTORY IS NOT REWRITTEN. The 586 settled rows were never
    at risk. Converting them into money rows would make the public ROI
    describe bets nobody placed — the same rule the stale promotion is
    tested on: the evidence is not rewritten by the thing it licensed.

Run directly: `python3 tests/test_the_likelihood_board_plays_for_money.py`
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger                                      # noqa: E402

_SEQ = [0]


def _conn():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))
    ledger.configure_bankroll(conn, starting=1000, unit_pct=1.0)
    return conn


def _board(sport, n=1):
    _SEQ[0] += 1
    return {"sport": sport, "date": "2026-09-20", "most_likely": [
        {"player": f"P{_SEQ[0]}_{i}", "market": "total_bases", "side": "OVER",
         "line": 1.5, "odds": -210, "book": "DK", "model_prob": 0.68,
         "implied_prob": 0.677, "game_date": "2026-09-20"}
        for i in range(n)]}


def _rows(conn):
    return conn.execute(
        "SELECT category, stake_units, stake_dollars, grade FROM bets"
    ).fetchall()


# --- the league Ethan named plays for money ----------------------------
def test_the_mlb_board_is_staked():
    conn = _conn()
    assert ledger.log_most_likely(conn, _board("mlb")) == 1
    r = _rows(conn)[0]
    assert r["category"] == ledger.LIKELY_LIVE_CATEGORY, dict(r)
    assert r["stake_units"] == ledger.LIKELY_LIVE_STAKE, dict(r)
    assert r["stake_dollars"] > 0, dict(r)


def test_every_league_with_a_likelihood_board_is_staked():
    """RE-ANCHORED the same afternoon. This asserted that only MLB was
    staked; Ethan then said *"after that do this for all the other
    sports with most likely paper bets"*, so the list is now every
    league that HAS such a board.

    The honest note, kept here because it is the thing a later reader
    will want: MLB is the only one of these with a record worth the
    name. The football seasons are two and three weeks old, so for most
    of these this is not a thin edge staked anyway — it is a board with
    no settled record at all, staked from the start."""
    for sport in ("nfl", "cfb", "nba", "mlb"):
        conn = _conn()
        ledger.log_most_likely(conn, _board(sport))
        r = _rows(conn)[0]
        assert r["category"] == ledger.LIKELY_LIVE_CATEGORY, (sport, dict(r))
        assert r["stake_dollars"] > 0, (sport, dict(r))
        assert ledger.performance(conn, sport)["open"] == 0, sport


def test_the_whole_boards_settled_count_survives_the_per_market_loop():
    """THE BUG THAT HID EVERY OTHER ONE. `p["enough"]` read a bare `n`
    set at the calibration query and read ninety lines and three loops
    later — and the by-market loop rebound it to whichever shelf came
    last out of GROUP BY. So Ethan's NFL board, 160 settled against a
    bar of 100, reported `enough: False` because its last shelf was a
    two-row spread, and the page answered him with "100 needed before
    this can say anything" on a board that had cleared the bar weeks
    earlier. The verdict it withheld was the sentence that says real
    money is on this book."""
    conn = _conn()
    big, small = "anytime_td", "spread"          # `small` sorts last
    for i in range(120):
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " odds, hit_prob, stake_units, stake_dollars, status, category,"
            " pnl_units) VALUES ('t','nfl','2026-09-01',?,?,'OVER',0.5,-150,"
            "0.66,0.1,0.0,?,'likely',?)",
            (f"A{i}", big, "won" if i % 3 else "lost",
             0.066 if i % 3 else -0.1))
    for i in range(2):
        conn.execute(
            "INSERT INTO bets (ts, sport, date, player, market, side, line,"
            " odds, hit_prob, stake_units, stake_dollars, status, category,"
            " pnl_units) VALUES ('t','nfl','2026-09-01',?,?,'OVER',0.5,-110,"
            "0.66,0.1,0.0,'won','likely',0.09)", (f"Z{i}", small))
    conn.commit()
    r = ledger.likely_report(conn, sport="nfl")
    assert r["calibration"]["n"] == 122, r["calibration"]["n"]
    assert r["enough"] is True, (
        "the board's own count was overwritten by a shelf's")
    assert "needed before this can say anything" not in r["verdict"], \
        r["verdict"]
    # …and the per-market counts are still each market's own, which is
    # the thing the rename must not have broken.
    assert r["by_market"][big]["n"] == 120
    assert r["by_market"][small]["n"] == 2


def test_the_page_is_told_which_leagues_carry_money_and_how_much():
    """The section's copy is written from these. `likely_is_staked(None)`
    is False, so the POOLED report said "no money staked" over a book
    that has had real dollars in it since 2026-09-19 — the pooled view
    is a mix and has to be able to say so instead of picking the
    comfortable half."""
    conn = _conn()
    pooled = ledger.likely_report(conn)
    assert pooled["staked_sports"] == [
        sp for sp in ledger.LIKELY_LIVE_SPORTS if not ledger.is_benched(sp)]
    assert pooled["stake_units"] == ledger.LIKELY_LIVE_STAKE
    assert ledger.likely_report(conn, sport="nfl")["staked_sports"] == ["nfl"]
    assert ledger.likely_report(conn, sport="ufc")["staked_sports"] == []


def test_the_section_stops_promising_no_money_once_money_is_on_it():
    """THE COPY FOLLOWS THE MONEY, and for two days it did not. Every
    sentence in this section was the paper one, hard coded — "ZERO
    dollars behind it", "nothing here is a position", "real money stays
    off until the ROI column has earned it" — and it kept saying so
    while four leagues staked 0.25u a row. Telling a reader no money is
    on a book while money is on it is the worst thing this section can
    do."""
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "web", "js", "app.js"),
              encoding="utf-8") as fh:
        src = fh.read()
    i = src.index("function recLikelySection")
    body = src[i:src.index("function recLikelyGameLines")]
    # COMMENTS OUT FIRST. The note above this function quotes the paper
    # copy in order to explain why it is now on a branch, and a scan
    # that counted the quotation would find the claim in the staked half
    # and fail — which is exactly what it did. The same trap caught the
    # Pick-of-the-Day copy test earlier the same day.
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    assert "lk.staked_sports" in body, \
        "the section does not ask whether money is on the book"
    # The paper claims must sit on the branch that is only reached when
    # nothing is staked — never printed unconditionally.
    for claim in ("ZERO dollars behind it", "no money staked",
                  "nothing here\n      is a position"):
        assert claim in body, claim
    # …and the staked branch, which runs from the disclosure call to the
    # paper branch that follows it, must not repeat any of them.
    start = body.index("recDisclosure")
    end = body.index("ZERO dollars behind it")
    staked_half = body[start:end]
    assert "staked from 2026-09-19" in staked_half, staked_half[:300]
    assert "REAL money" in staked_half, staked_half[:300]
    assert "no money" not in staked_half, staked_half[:300]
    assert "at no risk" not in staked_half, staked_half[:300]


def _render_likely(lk):
    """Run `recLikelySection` for real and return the HTML.

    TEXT MATCHING WAS NOT ENOUGH, and a mutation run proved it: replacing
    the whole money test with `const money = false` left every
    source-scan assertion passing, because the staked copy was still IN
    the file — on a branch nothing could reach. The only way to hold a
    page to what it SAYS is to make it say it.
    """
    import json
    import shutil
    import subprocess
    if not shutil.which("node"):
        return None                       # node absent: caller skips
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "web", "js", "app.js"),
              encoding="utf-8") as fh:
        src = fh.read()
    body = src[src.index("function recLikelySection"):
               src.index("function recLikelyGameLines")]
    harness = """
const SPORT_META = {nfl: {name: "NFL"}};
const escapeHtml = (x) => String(x == null ? "" : x);
const toneOf = () => "";
const marketWord = (m) => m;
const recDisclosure = (t, b) => `<disclosure>${t}|${b}</disclosure>`;
const recTile = (label, value, sub) => `<tile>${label}|${value}|${sub}</tile>`;
const recLikelyGameLines = () => "";
""" + body + """
process.stdout.write(recLikelySection(JSON.parse(process.argv[2]), "all"));
"""
    path = os.path.join(tempfile.mkdtemp(), "render.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    out = subprocess.run(["node", path, json.dumps(lk)],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr[-600:]
    return out.stdout


def _payload(**kw):
    lk = {"sport": "nfl", "settled": 160, "open": 3, "wins": 113,
          "losses": 47, "roi": 0.095, "needed": 100, "enough": True,
          "verdict": "v", "bands": [], "by_market": {},
          "calibration": {"n": 160, "claimed": 0.654, "actual": 0.706,
                          "gap": 0.052, "real": False},
          "staked": True, "staked_sports": ["nfl"], "stake_units": 0.25}
    lk.update(kw)
    return lk


def test_the_page_SAYS_there_is_money_on_a_staked_board():
    """THE SENTENCE ETHAN WAS READING WAS FALSE. On 2026-09-21 his NFL
    Most Likely section said "THE PAPER RECORD", "no money staked" and
    "real money stays off until the ROI column has earned it" — while
    that board had been staking 0.25u a row of real money since
    2026-09-19. He then asked to "make this real and not paper", which
    is the page's copy talking, not the ledger.

    A page that tells its owner no money is on a book while money is on
    it is the worst thing this section can do."""
    got = _render_likely(_payload())
    if got is None:
        return                             # no node on this box
    for lie in ("no money staked", "ZERO dollars", "the paper record",
                "at no risk", "nothing here is a position",
                "real money stays off"):
        assert lie not in got, f"{lie!r} still printed over a staked book"
    assert "0.25u" in got, got[:400]
    assert "REAL money" in got, got[:400]
    # The tile LABEL too, not only its subtitle. "Paper ROI" over a
    # number earned with real dollars is the same false sentence in
    # two words instead of six.
    assert "<tile>ROI|" in got, got[:400]
    assert "Paper ROI" not in got, got[:400]
    assert "2026-09-19" in got, "it does not say when the money went on"


def test_the_page_still_says_PAPER_when_nothing_is_staked():
    """The other half, so the fix is a branch and not a rewrite: a book
    with no money on it must still make the paper promise, in full."""
    got = _render_likely(_payload(sport="ufc", staked=False,
                                 staked_sports=[]))
    if got is None:
        return
    assert "no money staked" in got, got[:400]
    assert "ZERO dollars" in got, got[:400]
    assert "REAL money" not in got, got[:400]


def test_the_POOLED_section_cannot_call_a_mixed_book_paper():
    """`likely_is_staked(None)` is False, so the pooled view took the
    paper branch over a book that pools four staked leagues with the
    unstaked ones. It has to say it is a mix rather than pick the
    comfortable half."""
    got = _render_likely(_payload(sport="", staked=False,
                                 staked_sports=["mlb", "nfl", "cfb", "nba"]))
    if got is None:
        return
    assert "no money staked" not in got, got[:500]
    assert "MLB" in got and "NFL" in got, got[:500]
    assert "still paper" in got, "it does not say the pool is mixed"


def test_a_BENCHED_leagues_board_came_back_off_the_money():
    """WNBA LEFT THE LIST ABOVE ON 2026-09-21. Ethan: "remove wnba from
    the record so it's not hurting us. Make it all paper." It had been
    staked here since 2026-09-19, so "all paper" had to reach this board
    as well — the Edge book is the headline, but it is not the only
    place this site was putting dollars on that league.

    The board still RUNS. It is journaled, graded and readable at its own
    scope; what stopped is the money."""
    conn = _conn()
    ledger.log_most_likely(conn, _board("wnba"))
    r = _rows(conn)[0]
    assert r["category"] == "likely", dict(r)
    assert r["stake_dollars"] == 0.0, dict(r)
    assert r["stake_units"] > 0, "the board stopped measuring, not just paying"


def test_a_league_with_no_likelihood_board_is_not_staked():
    """UFC keeps its own book and never reaches `log_most_likely`, so it
    must not be swept in by a list that says "all the other sports"."""
    assert not ledger.likely_is_staked("ufc")
    assert ledger.likely_category("ufc") == "likely"


def test_the_staked_rows_carry_real_dollars_off_the_real_roll():
    """0.25u at 1% of a 1,000 bankroll is $2.50. A units column with no
    dollars behind it is the paper book wearing a different name."""
    conn = _conn()
    ledger.log_most_likely(conn, _board("mlb"))
    assert _rows(conn)[0]["stake_dollars"] == 2.5, _rows(conn)[0]["stake_dollars"]


def test_the_stake_is_flat_and_smaller_than_the_book_that_earned_it():
    """Flat because the evidence is a flat-stake ROI; smaller because
    the stale book cleared its bar and this one did not."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "ledger.py"),
        encoding="utf-8").read()
    body = src[src.index("def log_most_likely("):]
    body = body[:body.index("\ndef ", 10)]
    assert "kelly" not in body.lower(), "the staked rows are being sized"
    assert ledger.LIKELY_LIVE_STAKE < ledger.STALE_PROMOTED_STAKE


# --- and the edge book cannot feel any of it ---------------------------
def test_a_staked_likely_bet_never_reaches_the_headline_record():
    """THE INVARIANT. `performance` is the number on the front of this
    project. A signal at z 0.75 must not be able to move it."""
    conn = _conn()
    before = ledger.performance(conn, "mlb")
    ledger.log_most_likely(conn, _board("mlb", n=5))
    after = ledger.performance(conn, "mlb")
    assert after["open"] == before["open"], (before, after)
    assert after["settled"] == before["settled"], (before, after)


def test_the_headline_book_is_still_only_main_and_paper():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "engine", "ledger.py"),
        encoding="utf-8").read()
    assert ledger.LIKELY_LIVE_CATEGORY not in src[
        src.index("def performance("):src.index("def performance(") + 3000], \
        "the staked book has been let into the headline"


def test_the_staked_book_has_its_own_section_not_a_shared_one():
    keys = [k for k, _l, _c in ledger.BOOK_SECTIONS]
    assert "likely_live" in keys, keys
    cats = {k: cs for k, _l, cs in ledger.BOOK_SECTIONS}
    assert cats["edge"] == ("main", "paper"), cats["edge"]
    assert cats["likely"] == ("likely",), cats["likely"]
    assert cats["likely_live"] == (ledger.LIKELY_LIVE_CATEGORY,)


def test_a_placed_bet_is_counted_on_the_scope_chip():
    """It is a bet that was placed, so the reader's "all bets" number has
    to include it — the complaint that started the book audit."""
    assert ledger.LIKELY_LIVE_CATEGORY in ledger.RECOMMENDED_CATEGORIES


# --- the paper history stays what it was -------------------------------
def test_the_paper_record_is_not_rewritten_by_the_promotion():
    """The 586 settled rows were never at risk. Moving them into the
    money book would make the public ROI describe bets nobody placed."""
    conn = _conn()
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
        "pnl_units) VALUES ('mlb','2026-09-01','Old','total_bases','OVER',"
        "1.5,-210,'DK',0.68,0,0.1,0,'now','won','likely',0.0476)")
    conn.commit()
    ledger.log_most_likely(conn, _board("mlb"))
    still = conn.execute(
        "SELECT stake_dollars, category FROM bets WHERE player='Old'"
    ).fetchone()
    assert still["category"] == "likely", dict(still)
    assert still["stake_dollars"] == 0, dict(still)


# --- the verdict says what it actually knows ---------------------------
def _verdict(roi, n=586, hit=0.695, staked=False):
    return ledger._likely_verdict({
        "calibration": {"n": n, "claimed": 0.664, "actual": hit,
                        "real": False, "gap": 0.03},
        "enough": n >= ledger.LIKELY_VERDICT_N, "needed": ledger.LIKELY_VERDICT_N,
        "roi": roi, "staked": staked})


def test_a_positive_roi_inside_the_noise_is_not_called_a_result():
    """THE SENTENCE THIS REPLACED read "money stays off until that is
    positive over a sample this size" — while the number WAS positive.
    It was a refusal whose own condition had been met, which tells a
    reader nothing about what would change the answer."""
    v = _verdict(0.021)
    assert "z +0.75" in v, v
    assert "not yet distinguishable from break-even" in v, v
    assert "money stays off until that is positive" not in v, v


def test_the_refusal_says_what_would_change_it():
    v = _verdict(0.021)
    assert "4,1" in v and "settled would settle it" in v, v


def test_an_roi_clear_of_the_noise_is_allowed_to_say_so():
    """The hedge has to END, or it is just a verdict that cannot be
    passed."""
    v = _verdict(0.021, n=6000)
    assert "clear of the noise band" in v, v


def test_a_real_loss_is_named_as_one():
    v = _verdict(-0.09, n=4000, hit=0.60)
    assert "LOSING" in v, v


def test_the_verdict_says_whether_money_is_on_it():
    assert "No money is staked" in _verdict(0.021, staked=False)
    assert "Staked with real money" in _verdict(0.021, staked=True)


# --- the arithmetic behind the verdict ---------------------------------
def test_the_z_matches_the_number_the_decision_was_made_on():
    """586 settled at 69.5% and +2.1% is z 0.75 — the figure Ethan was
    shown before he said stake it anyway. If this drifts, the sentence on
    the page stops describing the decision that was made."""
    assert ledger._roi_z(0.695, 0.021, 586) == 0.75


def test_a_bigger_sample_of_the_same_edge_is_more_significant():
    small = ledger._roi_z(0.695, 0.021, 586)
    big = ledger._roi_z(0.695, 0.021, 5860)
    assert big > small * 2.5, (small, big)


def test_the_z_refuses_nonsense_rather_than_inventing_one():
    for bad in ((None, 0.02, 100), (0.695, None, 100), (0.695, 0.02, 0),
                (0.0, 0.02, 100), (1.0, 0.02, 100)):
        assert ledger._roi_z(*bad) is None, bad


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
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
