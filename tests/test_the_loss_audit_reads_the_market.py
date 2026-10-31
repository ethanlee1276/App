"""The loss audit asks the price question and says who made each board pick.

Ethan's paste of the NFL audits, 2026-10-31: the board's chances had come
honest week by week (said 58%, hit 58% in week 7) and the books still won —
a calibrated pick at a price that needs three points more than it hits
loses about 5%. So lossaudit.py now cuts every book by where the price's
break-even sat against the MARKET'S chance at pick time (pricetrust's: the
field's de-vigged median at the bet's own line, journaled or rebuilt from
our own snapshots, never after the pick), and by whether the line had such
a field at all. And the one board, which pools four makers, is cut by the
maker whose own book holds the same pick (bold first, then the list, the
matchup picks, the scenarios). Offline, on a fixture ledger and a fixture
snapshot file in a temp directory.

Run directly: `python3 tests/test_the_loss_audit_reads_the_market.py`
"""
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import lossaudit as LA                                         # noqa: E402
from engine import ledger                                      # noqa: E402
from engine.odds import american_to_decimal, devig_two_way     # noqa: E402

PICK = dt.datetime(2026, 10, 25, 15, 0, tzinfo=dt.timezone.utc)


def _world():
    tmp = Path(tempfile.mkdtemp())
    db, snaps = tmp / "ledger.db", tmp / "line_history.jsonl"
    conn = ledger.connect(db)

    def add(cat, player, odds, status, side="OVER", line=4.5, fc=None, market="receptions"):
        stake = 0.1
        pnl = stake * (american_to_decimal(odds) - 1) if status == "won" else -stake
        row = {"ts": PICK.strftime("%Y-%m-%dT%H:%M:%S"), "sport": "nfl", "date": "2026-W08",
               "game_day": "2026-10-25", "player": player, "market": market, "side": side, "line": line,
               "book": "draftkings", "odds": odds, "hit_prob": 0.62, "grade": "Strong", "stake_units": stake,
               "status": status, "pnl_units": pnl, "category": cat, "fair_consensus": fc}
        conn.execute(f"INSERT INTO bets ({', '.join(row)}) VALUES ({', '.join('?' * len(row))})",
                     tuple(row.values()))

    # Three board picks: one at a price better than the market's chance,
    # one well worse, one on a line no three books priced.
    add("board", "Value Guy", -130, "won")
    add("board", "Juice Guy", -200, "lost")
    add("board", "Thin Guy", -150, "won", line=1.5)
    # Their makers' own books: the list holds two, the bold rows one of
    # them too (bold is credited first); Thin Guy sits in no other book.
    add("likely", "Value Guy", -130, "won")
    add("likely", "Juice Guy", -200, "lost")
    add("bold", "Juice Guy", -200, "lost")
    # An Edge row whose field was journaled with it (an under: one minus it).
    add("main", "Edge Guy", -110, "won", side="UNDER", fc=0.40)
    conn.commit()
    conn.close()

    t = PICK.timestamp()

    def quote(player, book, over, under, line=4.5, at=t - 1800):
        return {"ts": at, "player": player, "market": "receptions", "book": book, "line": line,
                "over_odds": over, "under_odds": under}

    rows = []
    for book, (o, u) in (("draftkings", (-150, 120)), ("fanduel", (-145, 115)), ("betmgm", (-155, 125))):
        rows.append(quote("Value Guy", book, o, u))           # fair about 58%: -130 needs 56.5%
        rows.append(quote("Juice Guy", book, o, u))           # -200 needs 66.7%: 8+ points worse
    rows.append(quote("Thin Guy", "draftkings", -150, 120, line=1.5))   # one book: no field
    rows.append(quote("Value Guy", "caesars", -400, 300, at=t + 600))   # after the pick: never
    with open(snaps, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return db, snaps


def _slices(report, book):
    return report["books"][book]["slices"]


def test_every_book_is_cut_by_the_price_against_the_markets_chance():
    db, snaps = _world()
    rep = LA.audit(LA.open_ledger(db), sport="nfl", snapshots=str(snaps))
    cut = _slices(rep, "The one board")["the price against the market's chance"]
    assert cut["better than the market's chance"]["n"] == 1, cut
    assert cut["4+ points worse"]["n"] == 1, cut
    assert cut["no market chance on file"]["n"] == 1, cut
    field = _slices(rep, "The one board")["the market's field"]
    assert field["3+ books priced our line"]["n"] == 2 and field["under 3 books at our line"]["n"] == 1, field
    # The Edge row's journaled field, read for its own side.
    edge = _slices(rep, "Edge picks")["the price against the market's chance"]
    assert edge == {"better than the market's chance": edge["better than the market's chance"]}, edge
    assert rep["market_found"] == {"snapshots": 4, "none": 1, "journaled": 1}, rep["market_found"]


def test_the_price_bands_read_the_break_even_against_the_market():
    fair = sorted(devig_two_way(o, u)[0] for o, u in ((-150, 120), (-145, 115), (-155, 125)))[1]
    assert LA.price_vs_market({"odds": -130, "market_p": fair}) == "better than the market's chance"
    assert LA.price_vs_market({"odds": -150, "market_p": 0.59}) == "up to 2 points worse"   # 60.0%
    assert LA.price_vs_market({"odds": -170, "market_p": 0.60}) == "2 to 4 points worse"    # 63.0%
    assert LA.price_vs_market({"odds": -200, "market_p": 0.60}) == "4+ points worse"        # 66.7%
    assert LA.price_vs_market({"odds": -200, "market_p": None}) == "no market chance on file"
    assert LA.field_at_line({}) == "(not looked up)"


def test_the_board_names_who_put_each_pick_up_bold_first():
    db, snaps = _world()
    rep = LA.audit(LA.open_ledger(db), sport="nfl", snapshots=str(snaps))
    who = _slices(rep, "The one board")["who put it up"]
    assert set(who) == {"the Most Likely list", "bolder than the books", "the board alone"}, who
    assert who["bolder than the books"]["n"] == 1 and who["bolder than the books"]["l"] == 1
    assert "who put it up" not in _slices(rep, "Most Likely, paper"), "only the board pools makers"


def test_no_market_skips_the_snapshot_read_and_the_page_still_renders():
    db, snaps = _world()
    rep = LA.audit(LA.open_ledger(db), sport="nfl", snapshots=str(snaps), market=False)
    assert rep["market_found"] == {}
    cut = _slices(rep, "The one board")["the price against the market's chance"]
    assert set(cut) == {"no market chance on file"}, cut
    page = LA.render(LA.audit(LA.open_ledger(db), sport="nfl", snapshots=str(snaps)))
    assert "-- by the price against the market's chance" in page
    assert "-- by who put it up" in page
    assert "the market's chance at pick time: 4 from our snapshots" in page, page[:400]
    assert LA.main(["--db", str(db), "--sport", "nfl", "--no-market"]) == 0


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
