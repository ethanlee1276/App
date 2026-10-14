"""Every league's Pick of the Day reaches its record.

Ethan, 2026-10-14: "Also we only show the pick of the day record for nfl
and mlb but no other sport. Fix that"

THE CAUSE WAS ORDER. The college and basketball builds called
`ledger.log_pick_of_the_day` inside their journal blocks, and those blocks
run BEFORE `potd.attach` puts the card on the board — so every build
journaled an absent card and recorded nothing, from the day the feature
shipped (2026-09-15) to this fix, while the college card led its page with
BET. The NFL and MLB builds journal after the attach, which is why theirs
were the only records. Both now call `ledger.journal_potd` after the
attach, the relock and the publish, and this file holds every build to it.

The basketball and hockey boards hand the selector player props only, so
their card now says it has no game line rather than "nothing in the band
at a real price"; and the Record page draws the Pick of the Day section on
every league's scope, an empty book included.

Run directly: `python3 tests/test_every_league_records_its_pick_of_the_day.py`
"""

import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import ledger, potd                               # noqa: E402

BUILDS = ("nfl_build.py", "mlb_build.py", "cfb_build.py", "nba_build.py")


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _moneyline(team="AAA", other="BBB", **kw):
    """A game row that clears every bar, three hours out: Pinnacle's
    de-vig says 55% and DraftKings pays -110 (52.4%), +5.0% EV."""
    d, k = _kickoff(180)
    r = {"kind": "game", "player": f"{team} ML", "team": team, "opponent": other,
         "home": team, "away": other, "matchup": f"{other} @ {team}",
         "market": "moneyline", "bet_type": "moneyline", "market_label": "Moneyline",
         "side": "", "line": None, "book": "DraftKings", "odds": -110,
         "sharp_anchored": True, "sharp_fair": 0.55, "model_prob": 0.56,
         "implied_prob": 0.5238, "rank_auc": 0.75, "bettable": True,
         "injury_status": "", "game_date": d, "kickoff": k}
    r.update(kw)
    return r


def _prop(**kw):
    d, k = _kickoff(180)
    r = {"kind": "prop", "player": "A Player", "team": "AAA", "opponent": "BBB",
         "market": "points", "side": "OVER", "line": 20.5, "book": "DraftKings",
         "odds": -110, "model_prob": 0.6, "implied_prob": 0.52, "bettable": True,
         "game_date": d, "kickoff": k}
    r.update(kw)
    return r


def _board(*rows):
    return {"date": _kickoff(180)[0], "most_likely": list(rows)}


def _build_once(conn, out, sport, built):
    """A build's tail, in the order the five builds now run it: attach,
    relock, (publish), journal."""
    potd.attach(out, sport, built_dir=built)
    out["pick_of_the_day"] = ledger.relock_potd(
        out.get("pick_of_the_day") or {}, out.get("most_likely") or [], conn=conn)
    return ledger.journal_potd(out.get("pick_of_the_day") or {}, conn=conn, path=None)


def _potd_rows(conn):
    return conn.execute("SELECT sport, player, market, category, status FROM bets "
                        "WHERE category=?", (ledger.POTD_CATEGORY,)).fetchall()


# --- the bug, replayed --------------------------------------------------------
def test_the_old_order_recorded_nothing_and_the_new_one_records_the_pick():
    """The college and basketball journal blocks read the card before
    `potd.attach` had made it. Same board, both orders."""
    for sport in ("cfb", "nba"):
        conn, built = _conn(), tempfile.mkdtemp()
        out = _board(_moneyline())
        # THE OLD ORDER: the journal block ran first and found no card.
        assert ledger.log_pick_of_the_day(conn, out.get("pick_of_the_day") or {}) == 0
        assert _potd_rows(conn) == []
        # THE NEW ORDER: the card exists, is relocked, then journaled.
        assert _build_once(conn, out, sport, built) == "Pick of the Day: recorded."
        rows = _potd_rows(conn)
        assert [(r["sport"], r["player"], r["market"], r["status"]) for r in rows] \
            == [(sport, "AAA", "moneyline", "open")], [tuple(r) for r in rows]
        assert out["pick_of_the_day"]["verdict"]["call"] == "bet"


def test_a_rebuilt_board_points_at_the_lock_and_records_nothing_twice():
    """The boards rebuild all day. The second build's favourite is a
    different game; the day's pick stays the first one, on the card and
    in the record."""
    conn, built = _conn(), tempfile.mkdtemp()
    first = _board(_moneyline("AAA", "BBB"))
    assert _build_once(conn, first, "cfb", built) == "Pick of the Day: recorded."
    later = _board(_moneyline("CCC", "DDD", sharp_fair=0.57), _moneyline("AAA", "BBB"))
    assert _build_once(conn, later, "cfb", built) == ""
    assert [r["player"] for r in _potd_rows(conn)] == ["AAA"]
    card = later["pick_of_the_day"]["pick"]
    assert (card["team"], card.get("locked")) == ("AAA", True), card


def test_a_lean_below_the_bar_is_shown_and_never_recorded():
    conn, built = _conn(), tempfile.mkdtemp()
    out = _board(_moneyline(sharp_fair=0.48, odds=+105))        # under the 50% floor
    assert _build_once(conn, out, "cfb", built) == ""
    assert out["pick_of_the_day"]["pick"]["below_bar"]
    assert _potd_rows(conn) == []


# --- the helper ---------------------------------------------------------------
def test_the_record_is_exported_only_when_a_row_is_written():
    conn, built = _conn(), tempfile.mkdtemp()
    path = Path(tempfile.mkdtemp()) / "record.json"
    assert ledger.journal_potd({}, conn=conn, path=str(path)) == ""
    assert not path.exists(), "an empty card rewrote the record"
    out = _board(_moneyline())
    potd.attach(out, "cfb", built_dir=built)
    assert ledger.journal_potd(out["pick_of_the_day"], conn=conn, path=str(path)) \
        == "Pick of the Day: recorded."
    got = json.loads(path.read_text(encoding="utf-8"))
    assert got["potd_by_sport"]["cfb"]["open"] == 1, got["potd_by_sport"]


def test_a_journal_that_will_not_open_costs_a_warning_not_the_build():
    conn = _conn()
    conn.close()
    out = _board(_moneyline())
    potd.attach(out, "nba", built_dir=tempfile.mkdtemp())
    line = ledger.journal_potd(out["pick_of_the_day"], conn=conn, path=None)
    assert line.startswith("⚠️  Pick of the Day journal skipped"), line


def test_every_league_with_a_pick_reaches_the_record_and_the_bench_does_not():
    """College, basketball and hockey each land under their own name the
    moment a pick is journaled; a benched league still records, off the
    page (Ethan, 2026-09-21)."""
    conn = _conn()
    for sport in ("cfb", "nba", "nhl", "wnba"):
        out = _board(_moneyline())
        out["pick_of_the_day"] = potd.build(out["most_likely"], sport, out["date"])
        assert ledger.journal_potd(out["pick_of_the_day"], conn=conn, path=None), sport
    path = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, path)
    got = json.loads(path.read_text(encoding="utf-8"))
    by = got["potd_by_sport"]
    assert {"cfb", "nba", "nhl"} <= set(by), sorted(by)
    assert "wnba" not in by, "the bench reached the record page"
    assert got["potd"]["open"] == 3, got["potd"]


# --- every build, in order ------------------------------------------------------
def test_every_build_journals_the_pick_after_it_exists():
    """THE ORDER IS THE FIX. A check that both calls appear in a file
    passed throughout the month college recorded nothing; this asks where
    they are."""
    for fn in BUILDS:
        src = (ROOT / fn).read_text(encoding="utf-8")
        at = src.index("_potd.attach(")
        calls = [m.start() for m in re.finditer(r"log_pick_of_the_day\(|journal_potd\(", src)]
        assert calls, f"{fn} records no Pick of the Day"
        assert min(calls) > at, f"{fn} journals the Pick of the Day before it exists"


def test_college_and_basketball_journal_after_the_lock_is_applied():
    """College applies the lock inside `_write`; basketball applies it in
    `main`. Either way the journal reads the card after it."""
    cfb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    main = cfb[cfb.index("def main("):cfb.index("def _write(")]
    assert main.index("journal_potd(") > main.rindex("_write(out, args.out)"), \
        "cfb_build journals before `_write` relocks the card"
    nba = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert nba.index("journal_potd(") > nba.index("relock_potd("), \
        "nba_build journals before the relock"
    for src in (cfb, nba):
        assert "log_pick_of_the_day(" not in src, "the early, empty journal call came back"


def test_hockey_journals_after_its_hook_has_made_the_card():
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    main = src[src.index("def main("):]
    assert main.index('("pick of the day",') < main.index("journal(out, args.date)")
    body = src[src.index("def journal("):src.index("def main(")]
    assert "log_pick_of_the_day(" in body


# --- what the card says when it cannot pick -----------------------------------
def test_a_board_with_no_game_line_says_so():
    """Basketball and hockey hand the selector props only. The note says
    the board has no game line, not that nothing was in the band."""
    card = potd.build([_prop(), _prop(player="B Player")], "nba", "2026-10-21")
    assert card["pick"] is None
    assert "no game line on this board" in card["note"], card["note"]
    assert potd.build([], "nba", "2026-10-21")["note"] == "No pick today: the board had no rows"
    priced_out = potd.build([_moneyline(odds=-400)], "cfb", "2026-10-17")
    assert "nothing on the board is in the band" in priced_out["note"], priced_out["note"]


# --- the box check --------------------------------------------------------------
def test_the_box_check_tells_a_recorded_pick_from_a_shown_one():
    """potdcheck.py's two lines per league: what the journal holds, and
    what the card says — and whether the card's BET is the pick the
    journal holds for today."""
    import potdcheck
    conn, built = _conn(), tempfile.mkdtemp()
    college = _board(_moneyline())
    assert _build_once(conn, college, "cfb", built) == "Pick of the Day: recorded."
    hoops = _board(_moneyline("EEE", "FFF"))
    potd.attach(hoops, "nba", built_dir=built)           # shown, never journaled
    hockey = _board(_prop())
    potd.attach(hockey, "nhl", built_dir=built)
    cards = {"cfb": college["pick_of_the_day"], "nba": hoops["pick_of_the_day"],
             "nhl": hockey["pick_of_the_day"]}
    lines = potdcheck.report(conn, cards, {"potd_by_sport": {"cfb": {}}, "potd": {"open": 1}},
                             day=potd.slate_day())
    text = "\n".join(lines)
    cfb = lines[lines.index(next(x for x in lines if x.startswith("cfb "))) + 1]
    assert "1 recorded (1 riding) 0-0-0" in text
    assert "BET AAA ML at -110 DraftKings (sharp fair 55%) — recorded today" in cfb, cfb
    nba = lines[lines.index(next(x for x in lines if x.startswith("nba "))) + 1]
    assert "NOT RECORDED" in nba, nba
    nhl = lines[lines.index(next(x for x in lines if x.startswith("nhl "))) + 1]
    assert "NO BET" in nhl and "no game line on this board" in nhl, nhl
    assert next(x for x in lines if x.startswith("ufc ")).endswith("none ever")
    assert "card:    no card on this board" in text
    assert "(benched — off the Record page)" in next(x for x in lines if x.startswith("wnba"))
    assert lines[-1].startswith("record.json: a Pick of the Day record for cfb"), lines[-1]


# --- the record page ------------------------------------------------------------
def test_every_league_scope_draws_its_section_even_when_empty():
    from test_potd_card import _run_section
    for scope in ("cfb", "nba", "nhl", "ufc"):
        got = _run_section(None, scope)
        assert "Pick of the Day" in got and "Nothing settled yet." in got, (scope, got)
        assert scope.upper() in got, (scope, got)
    assert _run_section(None, "") == "", "an empty pooled book drew a section"


if __name__ == "__main__":
    fails = ran = 0
    for _n, _f in sorted(globals().items()):
        if _n.startswith("test_") and callable(_f):
            try:
                _f(); ran += 1; print(f"  ok  {_n}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {_n}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1; print(f"  FAIL {_n}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
