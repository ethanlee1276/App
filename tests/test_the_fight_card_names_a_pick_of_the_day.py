"""The fight card names a Pick of the Day, off the fights Pinnacle priced.

Ethan, 2026-10-14, "do 1-11", to "A Pick of the Day for the UFC card? Every
other league that names one now records it; UFC names none": yes.

`potd.fight_lines` turns every book's pair on a bout (the payload the UFC
build already bought) into one row per fighter: his best price at a book
you can bet, against Pinnacle's de-vigged fair, judged by the bars every
league's pick answers to. The bout is dated on the Eastern clock, a bout
past its listed start is never the pick, and the card's own model can take
a fighter away (it picks his opponent, or he carries a red flag) but never
put one forward. The pick is journaled under the key the fight book
settles on, the record carries a UFC book, and the UFC page draws the card.

Two faults found on the way, fixed and checked here: the card's "best"
price could be Pinnacle's, and a pick on the second fighter wore the first
fighter's book. `ufcbooks.py` lists the past rows each touched, read-only.

Run directly: `python3 tests/test_the_fight_card_names_a_pick_of_the_day.py`
"""

import datetime as _dt
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import ledger, potd                               # noqa: E402
from engine.odds import devig_two_way                         # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)

#: NAIVE UTC, as the builds pass it (see test_the_days_pick_is_decided_once…):
#: Saturday noon Eastern, a card that night.
NOW = _dt.datetime(2026, 10, 17, 16, 0)
DAY = potd.slate_day(NOW)
#: A prelim at 6 PM Eastern and a main event at 10 PM Eastern, which is the
#: next day in UTC.
PRELIM, MAIN = "2026-10-17T22:00:00Z", "2026-10-18T02:00:00Z"


def _bout(a="Ada Striker", b="Bo Grappler", commence=MAIN, **kw):
    """Pinnacle has Ada 58.6% (-150 / +130). DraftKings pays -130 on her
    (+3% EV by that fair); FanDuel has the best price on Bo."""
    out = {"a": a, "b": b, "commence": commence, "price_age_s": 600.0,
           "books": {"Pinnacle": (-150, 130), "DraftKings": (-130, 110),
                     "FanDuel": (-135, 120)}}
    out.update(kw)
    return out


def _lines(*bouts, now=NOW):
    return potd.fight_lines(list(bouts), now=now)


def _row(rows, fighter):
    return next(r for r in rows if r["team"] == fighter)


# --- the rows ----------------------------------------------------------------------
def test_each_fighter_is_a_row_against_pinnacles_fair():
    rows = _lines(_bout())
    assert len(rows) == 2, rows
    ada, bo = _row(rows, "Ada Striker"), _row(rows, "Bo Grappler")
    fair = devig_two_way(-150, 130)
    assert (ada["odds"], ada["book"]) == (-130, "DraftKings"), ada
    assert (bo["odds"], bo["book"]) == (120, "FanDuel"), bo
    assert ada["sharp_fair"] == round(fair[0], 4) and bo["sharp_fair"] == round(fair[1], 4)
    for r in rows:
        assert r["book"] != "Pinnacle", "the sharp reference became the ticket"
        assert r["kind"] == "game" and r["market"] == "moneyline" and r["model_prob"] is None
        assert r["player"] == f"{r['team']} ML", r["player"]
        assert potd.evidence(r) == "sharp" and potd.fair_prob(r) == r["sharp_fair"]
    assert ada["opponent"] == "Bo Grappler" and ada["fight"] == "Ada Striker vs Bo Grappler"


def test_no_two_way_sharp_price_no_row():
    assert _lines(_bout(books={"DraftKings": (-130, 110)})) == [], "priced with no witness"
    assert _lines(_bout(books={"Pinnacle": (-150, None), "DraftKings": (-130, 110)})) == []
    # Only Pinnacle quoting: a fair with no price anyone can take.
    assert _lines(_bout(books={"Pinnacle": (-150, 130)})) == []


def test_the_bout_is_dated_on_the_eastern_clock():
    for commence in (PRELIM, MAIN):
        r = _lines(_bout(commence=commence))[0]
        assert r["game_date"] == DAY == "2026-10-17", (commence, r["game_date"])
        assert r["kickoff"] == commence and not r["started"]
        assert potd.disqualify(r, NOW) == "", potd.disqualify(r, NOW)


def test_a_bout_past_its_listed_start_is_never_the_pick():
    later = NOW.replace(hour=22, minute=5)             # 6:05 PM Eastern
    prelim = _lines(_bout(commence=PRELIM), now=later)[0]
    main = _lines(_bout(commence=MAIN), now=later)[0]
    assert prelim["started"] and potd.disqualify(prelim, later) == potd.STARTED
    assert not main["started"] and potd.disqualify(main, later) == ""


def test_an_old_price_is_refused():
    r = _lines(_bout(price_age_s=7 * 3600.0))[0]
    assert r["price_stale"] and potd.disqualify(r, NOW) == potd.STALE_PRICE
    fresh = _lines(_bout(price_age_s=None))[0]
    assert not fresh["price_stale"], "a price the build just bought read as old"


def test_the_card_can_take_a_fighter_away_never_put_one_forward():
    rows = _lines(_bout(card_pick="Bo Grappler"))
    ada, bo = _row(rows, "Ada Striker"), _row(rows, "Bo Grappler")
    assert potd.shortfall(ada) == "the card’s own model picks Bo Grappler", potd.shortfall(ada)
    assert not bo["card_veto"], "the card's own pick was vetoed"
    flagged = _row(_lines(_bout(a_flags=["missed weight by 2.5 lb"])), "Ada Striker")
    assert potd.shortfall(flagged) == "a red flag on Ada Striker: missed weight by 2.5 lb"
    clean = _row(_lines(_bout()), "Ada Striker")
    assert potd.shortfall(clean) == "", potd.shortfall(clean)
    # A veto is a quality bar, not a hard refusal: the census can name it.
    assert potd.disqualify(ada, NOW) == ""


# --- the selection -----------------------------------------------------------------
def test_the_day_names_the_likeliest_qualifying_fighter():
    """Ada (58.6% by Pinnacle at -130) qualifies; Bo is under the floor. A
    second bout's 66% favourite at -165 is the likelier winner and wins."""
    big = _bout("Cy Champ", "Di Dog", commence=PRELIM,
                books={"Pinnacle": (-210, 175), "BetMGM": (-165, 140)})
    card = potd.build(_lines(_bout(), big), "ufc", DAY, now=NOW)
    pick = card["pick"]
    assert pick and not pick["below_bar"], card
    assert pick["team"] == "Cy Champ" and pick["book"] == "BetMGM", pick
    assert card["verdict"]["call"] == "bet" and pick["evidence"] == "sharp"
    assert pick["model_prob"] is None, "the card claims a number of ours"


def test_a_vetoed_fighter_is_shown_below_the_bar_never_named():
    card = potd.build(_lines(_bout(card_pick="Bo Grappler")), "ufc", DAY, now=NOW)
    assert card["verdict"]["call"] != "bet", card
    assert card["census"].get("the card’s own model picks Bo Grappler") == 1, card["census"]


# --- the journal and the grade -----------------------------------------------------
def _live_bout():
    """A main event three hours ahead of the real clock, held on today's
    Eastern date (the journal reads the real clock)."""
    day, hhmm = _kickoff(180)
    et = _dt.datetime.fromisoformat(f"{day}T{hhmm}:00").replace(tzinfo=ZoneInfo("America/New_York"))
    return day, _bout(commence=et.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))


def test_the_pick_is_journaled_where_the_fight_book_settles_it():
    day, bout = _live_bout()
    board = {"status": "card", "event_date": day}
    potd.attach(board, "ufc", lines=potd.fight_lines([bout]), prev={})
    card = board["pick_of_the_day"]
    assert card["date"] == day, "the fight board's date was lost"
    pick = card["pick"]
    assert pick and not pick["below_bar"], card
    assert ledger.potd_row_key(pick) == ("Ada Striker", "moneyline", "OVER", 0.5)
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    assert ledger.journal_potd(card, conn, path=None) == "Pick of the Day: recorded."
    row = conn.execute("SELECT sport, category, date, player, book, odds, status FROM bets").fetchone()
    assert tuple(row) == ("ufc", "potd", day, "Ada Striker", "DraftKings", -130, "open"), tuple(row)
    asked = []
    n = ledger.settle_ufc(conn, fetch_result=lambda name, since: (
        asked.append((name, since)) or {"won": True, "date": day}))
    assert n == 1 and asked == [("Ada Striker", _dt.date.fromisoformat(day))], asked
    status, pnl = conn.execute("SELECT status, pnl_units FROM bets").fetchone()
    assert status == "won" and abs(pnl - 100 / 130) < 1e-4, (status, pnl)


def test_the_record_carries_a_fight_card_book():
    assert "ufc" in ledger.POTD_LEAGUES
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))
    path = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, path)
    by = json.loads(path.read_text(encoding="utf-8"))["potd_by_sport"]
    assert "ufc" in by and not by["ufc"]["settled"], sorted(by)


def test_the_last_card_is_found_on_the_fight_board():
    built = tempfile.mkdtemp()
    card = {"sport": "ufc", "pick": {"player": "Ada Striker ML"}}
    (Path(built) / "ufc.json").write_text(json.dumps({"pick_of_the_day": card}), encoding="utf-8")
    assert potd.previous_card("ufc", built_dir=built) == card


# --- the build ---------------------------------------------------------------------
def test_the_build_attaches_relocks_publishes_then_journals():
    src = (ROOT / "ufc_build.py").read_text(encoding="utf-8")
    order = [src.index(s) for s in ("_potd.fight_lines(potd_bouts(bouts, out))",
                                    '_potd.attach(out, "ufc", lines=potd_lines)',
                                    "_led.relock_potd(out.get(\"pick_of_the_day\") or {}, potd_lines)",
                                    "gate.publish(out, p)",
                                    "_led.journal_potd(out.get(\"pick_of_the_day\") or {})")]
    assert order == sorted(order), order
    assert "event_cache_age(" in src, "the price's age never reaches the selector"


def test_the_card_read_reaches_each_bout():
    import ufc_build
    bouts = [{"a": "Ada Striker", "b": "Bo Grappler"}, {"a": "Cy Champ", "b": "Di Dog"}]
    board = {"picks": [{"fight": "Ada Striker vs Bo Grappler", "kind": "pick", "pick": "Bo Grappler",
                        "fighters": [{"red_flags": ["two KO losses in three"]}, {"red_flags": []}]}],
             "pass_list": [{"fight": "Cy Champ vs Di Dog", "kind": "pass", "pick": "Cy Champ",
                            "fighters": [{}, {"red_flags": ["missed weight"]}]}]}
    got = ufc_build.potd_bouts(bouts, board)
    assert got[0]["card_pick"] == "Bo Grappler" and got[0]["a_flags"] == ["two KO losses in three"]
    assert got[1]["card_pick"] == "", "a pass is not a pick against anyone"
    assert got[1]["b_flags"] == ["missed weight"]


def test_the_cards_price_is_one_you_can_bet_under_its_own_book():
    import ufc_build
    payload = {"bookmakers": [
        {"key": "pinnacle", "title": "Pinnacle",
         "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": -105}, {"name": "B", "price": 125}]}]},
        {"key": "draftkings", "title": "DraftKings",
         "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": -120}, {"name": "B", "price": 100}]}]},
        {"key": "fanduel", "title": "FanDuel",
         "markets": [{"key": "h2h", "outcomes": [{"name": "A", "price": -125}, {"name": "B", "price": 110}]}]}]}
    got = ufc_build.best_h2h(payload, "A", "B")
    assert (got["a_odds"], got["a_book"]) == (-120, "DraftKings"), got
    assert (got["b_odds"], got["b_book"]) == (110, "FanDuel"), got
    assert got["book"] == "DraftKings"
    sys.path.insert(0, str(ROOT / "tests"))
    from test_ufc import _fighter
    from engine.ufc.model import evaluate_fight
    a, b = _fighter(), _fighter("B", age=36, ko_losses_last3=2, sapm=4.8, r3_decay=0.3)
    # The same fight with the corners swapped: fighter A is the second corner.
    r = evaluate_fight(b, a, {"fighter_a": "B", "fighter_b": "A", "a_odds": -115, "b_odds": -105,
                              "book": "FD", "a_book": "FD", "b_book": "DK"}, "lightweight", 0)
    assert r["pick"] == "A" and r["book"] == "DK", (r["pick"], r["book"])
    ml = {c["selection"]: c.get("book") for c in r["market_board"] if c["market"] == "moneyline"}
    assert ml == {"A": "DK", "B": "FD"}, ml


# --- the page ----------------------------------------------------------------------
def test_the_ufc_page_draws_the_card_on_a_bet_day():
    app = app_js()
    i = app.index("async function renderUFC()")
    body = app[i:app.index("\n}\n", i)]
    assert "${potdHeroHTML(d)}" in body
    assert body.index('class="ufc-hero"') < body.index("${potdHeroHTML(d)}") \
        < body.index('class="stat-cards"'), "the card is not under the banner"


# --- the box check -----------------------------------------------------------------
def test_the_books_check_lists_the_two_faults_and_changes_nothing():
    import ufcbooks
    path = Path(tempfile.mkdtemp()) / "led.db"
    hist = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    pulled = time.time() - 120
    rows = [{"ts": pulled, "player": who, "market": "moneyline", "book": book, "line": 0.5,
             "over_odds": price, "under_odds": -price}
            for who, book, price in (("Ada Striker", "DraftKings", 120), ("Ada Striker", "FanDuel", 130),
                                     ("Bo Grappler", "DraftKings", -110),
                                     ("Cy Champ", "Pinnacle", 140))]
    hist.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    conn = ledger.connect(path)
    ledger.log_ufc_picks(conn, {"status": "card", "event_date": "2026-09-27", "picks": [
        {"pick": "Ada Striker", "odds": 130, "book": "DraftKings", "p_final": 0.5, "stake_units": 1.0},
        {"pick": "Bo Grappler", "odds": -110, "book": "DraftKings", "p_final": 0.6, "stake_units": 1.0},
        {"pick": "Cy Champ", "odds": 140, "book": "Pinnacle", "p_final": 0.5, "stake_units": 1.0},
        {"pick": "Di Unseen", "odds": 105, "book": "BetMGM", "p_final": 0.5, "stake_units": 1.0}]})
    before = sorted(tuple(r) for r in conn.execute("SELECT * FROM bets"))
    conn.close()
    lines = ufcbooks.report(path, hist)
    text = "\n".join(lines)
    assert "4 UFC row(s) in the ledger: 1 at a sharp book, 1 under another book's name, " \
           "1 with no stored pull to check against." in text, text
    assert "Cy Champ (+140, Pinnacle, 1u, ufc)" in text, text
    ada = next(x for x in lines if "Ada Striker" in x)
    assert "FanDuel posted it; DraftKings had +120" in ada, ada
    assert "Bo Grappler" not in text.split("UNDER ANOTHER")[-1], "a correct label was listed"
    after = sorted(tuple(r) for r in ledger.connect(path).execute("SELECT * FROM bets"))
    assert after == before, "the check changed the ledger"
    src = (ROOT / "ufcbooks.py").read_text(encoding="utf-8")
    assert "mode=ro" in src and "UPDATE" not in src and "INSERT" not in src and "DELETE" not in src
    try:
        ufcbooks._ro(Path(tempfile.mkdtemp()) / "missing.db").execute("SELECT 1 FROM bets")
        raise AssertionError("a missing ledger was created")
    except sqlite3.OperationalError:
        pass


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
