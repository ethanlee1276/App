"""Why a bet actually won or lost — §11's human tag beside the measured one.

Run directly: `python3 tests/test_whytags.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger, whytags as wt                       # noqa: E402


_SEQ = [0]


def _bet(conn, status="lost", sport="mlb"):
    # Distinct players per row — the journal's UNIQUE key is
    # (sport, date, player, market, category).
    _SEQ[0] += 1
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, "
        "odds, stake_units, status, category) VALUES "
        f"('2026-08-01','{sport}','2026-08-01','P{_SEQ[0]}','strikeouts',"
        f"'OVER',5.5,-120,1.0,'{status}','main')")
    conn.commit()
    return conn.execute("SELECT MAX(id) FROM bets").fetchone()[0]


def test_a_controlled_tag_writes_and_freeform_is_refused():
    """Four spellings of "umpire" are four slices of nothing — the tag is
    for counting, the note is for reading."""
    conn = ledger.connect(":memory:")
    bid = _bet(conn)
    got = wt.tag_bet(conn, bid, "ump-zone", "squeezed all night")
    assert got["tag"] == "ump-zone"
    row = conn.execute("SELECT why_tag, why_note FROM bets WHERE id=?",
                       (bid,)).fetchone()
    assert row[0] == "ump-zone" and row[1] == "squeezed all night"
    try:
        wt.tag_bet(conn, bid, "the ump was terrible")
        raise AssertionError("freeform must be refused")
    except ValueError as exc:
        assert "menu" in str(exc)


def test_an_open_bet_cannot_be_tagged():
    """Tagging an open bet is predicting — the one thing a why-tag must
    never be, or the tags become the model grading itself early."""
    conn = ledger.connect(":memory:")
    bid = _bet(conn, status="open")
    try:
        wt.tag_bet(conn, bid, "variance")
        raise AssertionError("open bets must be refused")
    except ValueError as exc:
        assert "post-mortem" in str(exc)


def test_each_sport_gets_its_own_menu_plus_the_shared_tags():
    assert "ump-zone" in wt.menu_for("mlb")
    assert "judges" in wt.menu_for("ufc")
    assert "ump-zone" not in wt.menu_for("ufc")
    for sport in ("mlb", "ufc", "nfl", "wnba"):
        assert "variance" in wt.menu_for(sport)
        assert "bad-read" in wt.menu_for(sport)


def test_every_tag_answers_what_would_i_do_differently():
    """`bad-read` is deliberately the ONLY tag that means the model needs
    fixing — the §11 point is that the fix depends on the failure, and a
    menu where half the tags implicate the model would tag every loss as
    the model's."""
    blurbs = " ".join(wt.SHARED.values())
    assert "MODEL needs fixing" in wt.SHARED["bad-read"]
    for sport_menu in wt.MENUS.values():
        for tag, blurb in sport_menu.items():
            assert "model" not in blurb.lower(), (
                f"{tag}: only bad-read may implicate the model")
    del blurbs


def test_the_counts_split_by_sport_tag_and_result():
    conn = ledger.connect(":memory:")
    a, b = _bet(conn), _bet(conn, status="won")
    wt.tag_bet(conn, a, "variance")
    wt.tag_bet(conn, b, "variance")
    c = wt.tag_counts(conn)
    assert c["mlb:variance"]["lost"] == 1 and c["mlb:variance"]["won"] == 1


def test_a_missing_bet_id_says_so():
    conn = ledger.connect(":memory:")
    try:
        wt.tag_bet(conn, 999, "variance")
        raise AssertionError("unreachable")
    except ValueError as exc:
        assert "no bet" in str(exc)


def test_the_receipts_export_carries_the_tag():
    src = open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "engine", "ledger.py"), encoding="utf-8").read()
    i = src.index("def recent_settled(")
    assert "why_tag, why_note" in src[i:i + 800]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
