"""Every bet a league placed shows on that league's Record page.

Ethan, 2026-09-19: *"i want all bets shown on the record page that had
been placed and cfb isnt showing that so fix it."*

Two separate things were hiding college football's rows.

THE BOOKS. `book_records` maps only the categories in `BOOK_SECTIONS`
— main, paper, likely, longshot. College's journal also holds 210 rows
under `stale`, graded, dated, at real prices. The panels that draw that
bucket (`recStaleSection`, `recFormSection`, `recLooseSection`) are
written `scoped ? "" : X`, whole-journal only, because their payloads
have no per-sport cut to draw. So those rows were not hidden by a
decision — they were hidden by the shape of a payload, and a reader who
tapped CFB could not reach them from anywhere.

THE CHIP. Its own comment promises "rows journaled in that scope, open
and settled together" and it counted `overall`, which is
`performance(...)`: the edge book, STAKED. College read 0 there all
season, so the badge said 0 next to a page full of bets.

`SHADOW_SECTIONS` is the same scan as `book_records` over the other
categories, so no future book can go invisible by being forgotten in a
list. `journaled_counts` is one filterless scan, so the chip counts what
it says it counts and the sports still sum to "All bets".

Nothing here moves a row INTO the headline. `performance` still defaults
to ("main","paper"), so the P&L, the curve and the verdict are untouched
— these books are shown, labelled as measurements, not counted as money.

Run directly:
`python3 tests/test_every_bet_placed_reaches_the_record_page.py`
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import ledger

APP = (ROOT / "web" / "js" / "app.js").read_text()
_SEQ = [0]


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    j = APP.index("\n}\n", i)
    return APP[i:j + 3]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "t.db"))


def _bet(conn, sport, category, status, market="hits", pnl=0.0, stake=1.0):
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (sport,date,player,market,side,line,odds,book,"
        "hit_prob,edge,stake_units,stake_dollars,ts,status,category,"
        "pnl_units) VALUES (?,?,?,?,'OVER',0.5,-120,'DK',0.6,0,?,0,"
        "'now',?,?,?)",
        (sport, ledger.RECORD_EPOCH, f"P{_SEQ[0]}", market, stake,
         status, category, pnl))
    conn.commit()


#: College football as Ethan's runs found it: probation (zero stake), a
#: full Most Likely book, and a stale book nothing could reach.
def _cfb(conn):
    for _ in range(3):
        _bet(conn, "cfb", "likely", "won", stake=0.0)
    for _ in range(2):
        _bet(conn, "cfb", "likely", "lost", stake=0.0)
    for _ in range(4):
        _bet(conn, "cfb", "stale", "lost", market="spread", stake=0.0)
    _bet(conn, "cfb", "stale", "won", market="spread", stake=0.0)


# --- the shadow books exist, per sport ---------------------------------
def test_the_stale_book_is_reported_for_the_sport_that_placed_it():
    c = _conn()
    _cfb(c)
    sb = ledger.book_records(c, sections=ledger.SHADOW_SECTIONS)
    assert "cfb" in sb, sb
    assert sb["cfb"]["stale"]["w"] + sb["cfb"]["stale"]["l"] == 5, sb


def test_the_headline_books_do_not_carry_the_shadow_rows():
    """Shown is not the same as counted. The stale rows must not appear
    in the three books the page leads with."""
    c = _conn()
    _cfb(c)
    br = ledger.book_records(c)
    assert "stale" not in br["cfb"], br["cfb"]
    assert br["cfb"]["likely"]["w"] + br["cfb"]["likely"]["l"] == 5


def test_the_shadow_books_do_not_carry_the_headline_rows():
    c = _conn()
    _cfb(c)
    sb = ledger.book_records(c, sections=ledger.SHADOW_SECTIONS)
    assert set(sb["cfb"]) == {"stale"}, sb["cfb"]


def test_the_headline_p_and_l_still_cannot_see_them():
    """THE LINE THAT MUST NOT MOVE. A stale flag is a measurement; if
    one ever lands in the P&L the record stops being the record."""
    c = _conn()
    _cfb(c)
    _bet(c, "cfb", "main", "won", pnl=1.0)
    assert ledger.performance(c, "cfb")["settled"] == 1


def test_potd_and_ufc_are_left_to_their_own_sections():
    """Both already render on a sport's own scope. Listing them here
    would print one book's record twice on one screen."""
    cats = {c for _k, _l, cs in ledger.SHADOW_SECTIONS for c in cs}
    assert "potd" not in cats and "ufc" not in cats, cats
    head = {c for _k, _l, cs in ledger.BOOK_SECTIONS for c in cs}
    assert not (cats & head), cats & head


def test_the_export_carries_the_shadow_books():
    c = _conn()
    _cfb(c)
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(c, out)
    doc = json.loads(out.read_text())
    sb = doc.get("shadow_books")
    assert sb, "the export dropped shadow_books — the page has nothing to draw"
    assert sb["cfb"]["stale"]["l"] == 4, sb


# --- the chip counts what it promises ----------------------------------
def test_the_chip_counts_every_book_not_just_the_staked_one():
    """College's chip read 0 beside a page full of bets, because
    `overall` is the staked edge book."""
    c = _conn()
    _cfb(c)
    _bet(c, "cfb", "likely", "open", stake=0.0)
    jc = ledger.journaled_counts(c, since=ledger.RECORD_EPOCH)
    got = jc["by_sport"].get("cfb")
    assert got is not None, \
        "college is missing from the counts — the scan is filtered again"
    assert got == {"settled": 10, "open": 1}, jc
    assert ledger.performance(c, "cfb")["settled"] == 0, \
        "the edge book is still empty — that is the whole point"


def test_the_sports_still_add_up_to_all_bets():
    """The invariant the chip comment was written to protect."""
    c = _conn()
    _cfb(c)
    _bet(c, "mlb", "main", "won", pnl=1.0)
    _bet(c, "nfl", "longshot", "open")
    jc = ledger.journaled_counts(c, since=ledger.RECORD_EPOCH)
    for key in ("settled", "open"):
        assert jc["all"][key] == sum(v[key] for v in jc["by_sport"].values()), jc


def test_a_voided_bet_is_not_counted_on_the_chip():
    """No result, no stake at risk, and nothing under the chip shows it
    — so counting it would put a number on the badge that the page
    cannot account for. College has 119 of them."""
    c = _conn()
    _bet(c, "cfb", "likely", "void")
    jc = ledger.journaled_counts(c, since=ledger.RECORD_EPOCH)
    # Not merely counted as zero — ABSENT. A league whose only rows are
    # voids has no record to scope to, and a chip reading "0" for it is
    # a different claim from no chip row at all.
    assert "cfb" not in jc["by_sport"], jc
    assert jc["all"] == {"settled": 0, "open": 0}, jc


def test_the_export_carries_the_chip_counts():
    c = _conn()
    _cfb(c)
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(c, out)
    doc = json.loads(out.read_text())
    jc = doc.get("journaled")
    assert jc, "the export dropped the chip counts"
    assert jc["by_sport"].get("cfb", {}).get("settled") == 10, jc


# --- the page reads both -----------------------------------------------
def test_the_scope_bar_reads_the_journaled_counts():
    src = _fn("recordScopeHTML")
    assert "d.journaled" in src, "the chips are back on the staked edge book"
    assert "jc.by_sport" in src and "jc.all" in src, src


def test_the_chip_falls_back_for_a_file_published_before_the_key():
    """The first load after a deploy serves the old file. A row of
    zeros there would be a worse lie than the narrow count."""
    src = _fn("recordScopeHTML")
    assert "|| r.overall" in src and "|| d.overall" in src, src


def test_the_products_room_draws_the_shadow_books_when_scoped():
    src = _fn("_recordRooms")
    assert "recShadowBooks(d.shadow_books, scope)" in src, src
    i = src.index("recShadowBooks")
    assert "scoped ?" in src[max(0, i - 120):i], \
        "the shadow books must be SCOPED — on 'All bets' the panels " \
        "above already draw each of these buckets in full"


def test_the_shadow_renderer_reuses_the_book_arithmetic():
    """A second copy of the ROI math is how one book ends up with two
    different ROIs on one screen."""
    body = _fn("recShadowBooks")
    assert "recBookSections(" in body, body
    # No division, no pnl fields: it passes a label list and nothing
    # else. ("never staked" in the subtitle is prose, not a field.)
    for own in ("net_u", "b.staked", "toFixed", "/ b.", "ROI"):
        assert own not in body, \
            f"the shadow renderer is doing its own arithmetic ({own})"


def test_the_shadow_books_say_they_are_not_money():
    body = _fn("recShadowBooks")
    assert "never staked" in body, body
    for key in ("stale", "form", "loose", "longshot_watch", "predmarket"):
        assert f'"{key}"' in body, f"{key} has no row in the renderer"


def test_the_empty_state_counts_the_shadow_books_too():
    """A league whose only rows are stale flags has still placed bets."""
    js = f"""
    {_fn("recordHasSomething")}
    console.log(JSON.stringify(recordHasSomething(
        {{"settled": 0, "open": 0}}, {{}}, null, {{"stale": {{"w": 1, "l": 4}}}})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) is True


def test_an_empty_shadow_book_does_not_rescue_an_empty_league():
    js = f"""
    {_fn("recordHasSomething")}
    console.log(JSON.stringify(recordHasSomething(
        {{"settled": 0, "open": 0}}, {{}}, null, {{"stale": {{"w": 0, "l": 0}}}})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) is False


def test_the_branch_passes_the_shadow_books():
    src = APP[APP.index("function renderRecord"):]
    src = src[:src.index("\n}\n")]
    assert "(d.shadow_books || {})[scope]" in src, src


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
