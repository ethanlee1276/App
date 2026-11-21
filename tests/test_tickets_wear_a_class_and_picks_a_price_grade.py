"""Each parlay wears its class and names its one book; the NBA's and hockey's picks wear a price grade
(step AAB, 2026-11-20).

Ethan, to the decisions put to them after their "NFL Prop Bot — Master Instructions v3.1" went in beside
the site's own logic: "1. Yes 2. Yes 3. Yes". The second was SAFE / BALANCED / POP on each ticket and the
one book that prices every leg (v3.1 sections 10 and 1); the third the Green / Yellow / Red price grade
(section 2) on the NBA's and hockey's picks. What these hold:

  * THE PRICE GRADE (engine/pricegrade). Green where the price's break-even is at or under our number,
    Yellow up to 2 points over it, Red beyond; the take-at is the price our number is worth, never
    heavier than -250. Only the NBA's and hockey's player props with a real price that are bets wear it
    (no read, no game line, no touchdown, no proxy price), and a switch turns it off. It is a label: no
    pick's chance or tier moves. Each grade says what picks like it have done on our own record, once
    twenty of them have settled at that chance.
  * It rides from the board's rows to the report's card, Report Picks and the Most Likely card, and the
    heartbeat counts each grade.
  * THE TICKET CLASS (engine/gameparlays.ticket_class). Safe: every leg 64% or better and 40% together.
    Balanced: every leg 60% or better and 36% together. Pop: 25% together. Under that, a long shot.
    Where the league grades prices, Safe also needs every leg at a Green price and Balanced one. A
    class says why it is not the class above. Football stands on the chances alone. A scorer pair is
    not classed.
  * THE ONE BOOK (`one_book`). The book quoting every leg at its own number and side, the one that pays
    most on them, read off the board's prop rows, its pick rows and each leg's own book; "no one book"
    only where every leg's books are on file and none has them all; nothing where a leg's books are
    unknown and the legs' own books differ. The heartbeat counts, leg by leg, why a quote was missing.
    (A pick carried at its posted number is held in tests/test_a_parlay_says_when_a_legs_number_is_gone.py.)
  * Both ride on the server's card and the page's card; the record splits each league's tickets by
    class from the chances and prices they were journaled with; the heartbeat counts classes by size
    and one-book tickets.

    python3 tests/test_tickets_wear_a_class_and_picks_a_price_grade.py
"""
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP, likelyboard as LB, parlayledger as PL, pricegrade as PG  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
GAME = EG.GAME
HOOPS = ("pts", "reb", "ast", "threes", "pts", "reb", "ast", "pts")


class _Env:
    def __init__(self, **kw):
        self.kw, self.old = kw, {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.old[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def __exit__(self, *a):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _prop(prob, odds, **kw):
    return {"kind": "prop", "player": "Jalen Brunson", "team": "NYK", "opponent": "BOS", "market": "ast",
            "side": "OVER", "line": 6.5, "odds": odds, "book": "FanDuel", "has_market": True,
            "model_prob": prob, "sources": ["likely"], **kw}


def _hoops_board():
    b = EG.board()
    for r, m in zip(b["most_likely"], HOOPS):
        r["market"], r["market_label"] = m, m
    return b


def _js(name):
    return (ROOT / "web" / "js" / f"{name}.js").read_text(encoding="utf-8")


# --- the price grade ---------------------------------------------------------------------------
def test_green_yellow_and_red_by_their_own_bars():
    # -150 needs 60.0% to break even.
    assert abs(PG.need(-150) - 0.60) < 1e-9 and abs(PG.need(120) - 100 / 220) < 1e-9 and PG.need(None) is None
    assert PG.grade_of(0.64, -150) == "green" and PG.grade_of(0.60, -150) == "green", "at the take-at is Green"
    assert PG.grade_of(0.59, -150) == "yellow" and PG.grade_of(0.58, -150) == "yellow", "up to 2 points worse"
    assert PG.grade_of(0.579, -150) == "red" and PG.grade_of(0.50, -150) == "red"
    assert PG.grade_of(0.55, 110) == "green", "a plus price our number clears"
    assert PG.grade_of(None, -150) is None and PG.grade_of(0.6, None) is None and PG.grade_of(0.6, 0) is None
    assert PG.YELLOW_MAX == 0.02 and PG.GRADES == ("green", "yellow", "red")


def test_the_take_at_is_the_price_our_number_is_worth():
    assert PG.take_at(0.60) == -150 and PG.take_at(0.50) == -100 and PG.take_at(0.40) == 150
    assert PG.take_at(0.80) == PG.TAKE_CAP == -250, "never heavier than the price gate"
    assert PG.take_at(None) is None and PG.take_at(1.2) is None


def test_the_words_say_the_price_the_need_and_our_number():
    g = PG.grade(0.64, -150, "nba")
    assert g["grade"] == "green" and g["label"] == "Green price" and g["gap"] == -0.04 and g["take_at"] == -178
    assert g["words"] == "Green price: −150 needs 60% to break even and our number is 64%", g["words"]
    y = PG.grade(0.63, -180, "nba")
    assert y["grade"] == "yellow" and y["words"] == "Yellow price: −180 needs 64% to break even, 1.3 points over our 63%"
    r = PG.grade(0.64, -220, "nhl")
    assert r["grade"] == "red" and r["words"].startswith("Red price: −220 needs 69% to break even, 4.7 points over our 64%")
    # The price to take is not said twice: the card says it in its own words.
    assert "or better" not in y["words"] and y["take_at"] == -170


def test_only_the_nbas_and_hockeys_bets_wear_it():
    with _Env(QB_PRICE_GRADE=None):
        assert PG.GRADE_SPORTS == ("nba", "nhl") and PG.on("nba") and PG.on("NHL")
        assert not any(PG.on(s) for s in ("nfl", "cfb", "cbb", "wnba", "mlb", ""))
        rows = [_prop(0.66, -150), _prop(0.66, -200, player="B"), _prop(0.66, -230, player="C"),
                _prop(0.66, -230, player="Read", bettable=False), _prop(0.66, -150, player="Proxy", book="proxy"),
                _prop(0.66, -150, player="Bare", has_market=False), _prop(0.5, 120, player="TD", market="anytime_td"),
                {"kind": "game", "market": "moneyline", "odds": -150, "model_prob": 0.7},
                _prop(0.66, None, player="No price")]
        got = PG.stamp(rows, "nba")
        assert got == {"on": True, "rows": 3, "green": 1, "yellow": 1, "red": 1}, got
        assert [r.get("price_grade", {}).get("grade") for r in rows] == ["green", "yellow", "red"] + [None] * 6
        # No pick's number or tier is touched.
        assert all(r["model_prob"] in (0.66, 0.5, 0.7) for r in rows)
        # Football keeps none, and a row that wore one loses it.
        assert PG.stamp(rows, "nfl") == {"on": False, "rows": 0, "green": 0, "yellow": 0, "red": 0}
        assert not any("price_grade" in r for r in rows)
    with _Env(QB_PRICE_GRADE="off"):
        assert not PG.on("nba") and PG.stamp([_prop(0.66, -150)], "nba")["rows"] == 0


def test_each_grade_says_what_picks_like_it_have_done():
    from engine import ledger
    conn = ledger.connect(":memory:")
    # 25 red-priced NBA picks at 66% and -230 (the price needs 69.7%): 17 won. And 5 green ones: too few to say.
    for i in range(25):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, book, odds, hit_prob, status, "
                     "category) VALUES ('nba', '2026-11-01', ?, 'ast', 'OVER', 5.5, 'FanDuel', -230, 0.66, ?, 'likely')",
                     (f"R{i}", "won" if i < 17 else "lost"))
    for i in range(5):
        conn.execute("INSERT INTO bets (sport, date, player, market, side, line, book, odds, hit_prob, status, "
                     "category) VALUES ('nba', '2026-11-01', ?, 'ast', 'OVER', 5.5, 'FanDuel', -150, 0.66, 'won', 'likely')",
                     (f"G{i}",))
    # The same pick in a second book of the journal counts once; another league's never.
    conn.execute("INSERT INTO bets (sport, date, player, market, side, line, book, odds, hit_prob, status, category) "
                 "VALUES ('nba', '2026-11-01', 'R0', 'ast', 'OVER', 5.5, 'FanDuel', -230, 0.66, 'won', 'board')")
    conn.execute("INSERT INTO bets (sport, date, player, market, side, line, book, odds, hit_prob, status, category) "
                 "VALUES ('nhl', '2026-11-01', 'X', 'shots', 'OVER', 2.5, 'FanDuel', -230, 0.66, 'won', 'likely')")
    conn.commit()
    rec = PG.record(conn, "nba")
    red, green = rec[("red", 0.60)], rec[("green", 0.60)]
    assert (red["n"], red["hits"]) == (25, 17) and (green["n"], green["hits"]) == (5, 5), rec
    assert abs(red["units"] - (17 * 100 / 230 - 8)) < 1e-9, "one unit a pick at its own price"
    said = PG.record_words(rec, "nba", "red", 0.66)
    assert said == "NBA picks at this chance and a red price: 68% of 25 hit, −2.4% a bet", said
    assert PG.record_words(rec, "nba", "green", 0.66) == "", "five settled is too few to say"
    g = PG.grade(0.66, -230, "nba", rec)
    assert g["words"].endswith(". " + said) and g["grade"] == "red"
    assert PG.record(None, "nba") == {}, "no journal, no record, no error"


def test_the_board_stamps_its_rows_and_counts_them():
    from engine import ledger
    conn = ledger.connect(":memory:")
    rows = [_prop(0.66, -150, player="A"), _prop(0.63, -180, player="B"), _prop(0.62, -230, player="C")]
    result = {"games": [], "most_likely": rows, "matchup_picks": [], "td_scenarios": [], "recommendations": []}
    with _Env(QB_PRICE_GRADE=None):
        LB.attach(result, "nba", conn)
    board = result["likely_board"]
    by = {r["player"]: r for r in board["rows"] + (board.get("held") or [])}
    assert board["price_grade"]["on"] is True and board["price_grade"]["rows"] == len(
        [r for r in board["rows"] if r.get("price_grade")])
    for who, want in (("A", "green"), ("B", "yellow"), ("C", "red")):
        if who in {r["player"] for r in board["rows"]}:
            assert by[who]["price_grade"]["grade"] == want, (who, by[who].get("price_grade"))
    assert {r["player"] for r in board["rows"]} >= {"A"}, "the fixture's strongest row is posted"
    # Football's board grades nothing.
    nfl = {"games": [], "most_likely": [_prop(0.66, -150, market="receptions")], "matchup_picks": [],
           "td_scenarios": [], "recommendations": []}
    LB.attach(nfl, "nfl", conn)
    assert nfl["likely_board"]["price_grade"]["on"] is False
    assert not any("price_grade" in r for r in nfl["likely_board"]["rows"])


def test_the_grade_rides_to_the_card_report_picks_and_the_heartbeat():
    from engine import reportbets as RB
    assert "price_grade" in RB.FIELDS
    gr = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert '{"price_grade": {k: r["price_grade"].get(k) for k in ("grade", "label", "words")}}' in gr
    assert 'if isinstance(r.get("price_grade"), dict) and not read_only(r) else {}' in gr, "a read wears none"
    report, picks, app = _js("report"), _js("reportpicks"), _js("app")
    assert '<span class="gr-pick-grade ${escapeAttr(v.price_grade.grade)}">' in report
    assert '<p class="gr-pick-gradewhy">${escapeHtml(v.price_grade.words)}</p>' in report
    assert "const grade = r && r.price_grade && !r.read_only && r.price_grade.label ? r.price_grade : null;" in picks
    assert '<span class="rpk-grade ${escapeAttr(grade.grade || "")}"' in picks, "the words wear the grade's colour"
    rp_css = (ROOT / "web" / "css" / "reportpicks.css").read_text(encoding="utf-8")
    assert all(f".rpk-grade.{g} " in rp_css for g in PG.GRADES)
    # The Most Likely card: the board's grade, or the same bars on the tier's real rate where its ring
    # shows that, so the ring and the price cannot disagree; an ungraded row keeps the old line.
    grade = app[app.index("function obGradeHTML(r)"):app.index("function obPriceHTML(r)")]
    assert "if (!g || !OB_GRADE_LABEL[g.grade]) return \"\";" in grade
    assert 'const grade = !tier ? g.grade : gap <= 1e-9 ? "green" : gap <= 0.02 + 1e-9 ? "yellow" : "red";' in grade
    assert 'class="ob-fair grade-${grade}"' in grade and "take at ${american(fair)} or better" in grade
    price = app[app.index("function obPriceHTML(r)"):app.index("function obPriceHTML(r)") + 200]
    assert "const graded = obGradeHTML(r);" in price and "if (graded) return graded;" in price
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8") \
        + (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")
    for cls in (".gr-pick-grade.green", ".gr-pick-grade.yellow", ".gr-pick-grade.red", ".ob-fair.grade-red"):
        assert cls in css, cls
    import launch as L
    board = {"most_likely": [], "recommendations": [], "game_bets": [],
             "likely_board": {"rows": [], "price_grade": {"on": True, "rows": 9, "green": 4, "yellow": 2, "red": 3}}}
    off = {"most_likely": [], "recommendations": [], "game_bets": [],
           "likely_board": {"rows": [], "price_grade": {"on": False, "rows": 0, "green": 0, "yellow": 0, "red": 0}}}
    got = []
    for b in (board, off):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "b.json")
            with open(path, "w") as fh:
                json.dump(b, fh)
            was = L._full_copy
            L._full_copy = lambda p: p
            try:
                got.append(L._board_counts(path))
            finally:
                L._full_copy = was
    assert got[0]["price_grade"] == {"rows": 9, "green": 4, "yellow": 2, "red": 3}, got[0]
    assert "price_grade" not in got[1], "a league that grades nothing says nothing"


# --- a ticket's class --------------------------------------------------------------------------
def _t(joint, *legs):
    return {"joint": joint, "legs": [{"p": p, "odds": o} for p, o in legs]}


def test_safe_balanced_pop_and_a_long_shot_by_their_bars():
    assert (GP.CLASS_SAFE_LEG, GP.CLASS_BALANCED_LEG) == (0.64, 0.60)
    assert (GP.CLASS_SAFE_JOINT, GP.CLASS_BALANCED_JOINT, GP.CLASS_POP_JOINT) == (0.40, 0.36, 0.25)
    with _Env(QB_PRICE_GRADE=None):
        safe = GP.ticket_class("nfl", _t(0.45, (0.68, -220), (0.66, -210)))
        assert safe == {"class": "safe", "label": "Safe", "why": "Safe: every leg 64% or better, 45% together"}, safe
        bal = GP.ticket_class("nfl", _t(0.40, (0.66, -210), (0.61, -170)))
        assert bal["class"] == "balanced" and bal["why"] == \
            "Balanced: every leg 60% or better, 40% together. Not Safe: a leg under 64%", bal
        low = GP.ticket_class("nfl", _t(0.38, (0.65, -200), (0.64, -200)))
        assert low["class"] == "balanced" and low["why"].endswith("Not Safe: under 40% together"), low
        pop = GP.ticket_class("nfl", _t(0.31, (0.62, -180), (0.55, -130)))
        assert pop["class"] == "pop" and pop["why"] == \
            "Pop: 31% together. Not Balanced: a leg under 60% and under 36% together", pop
        three = GP.ticket_class("nfl", _t(0.30, (0.70, -220), (0.68, -210), (0.66, -200)))
        assert three["class"] == "pop" and three["why"] == "Pop: 30% together. Not Balanced: under 36% together", \
            "three good legs are a Pop: what three legs are"
        long = GP.ticket_class("cfb", _t(0.17, (0.56, -130), (0.55, -125), (0.55, -125)))
        assert long == {"class": "long", "label": "Long shot",
                        "why": "Long shot: 17% together, under the 25% a Pop ticket needs"}, long
        assert GP.ticket_class("nfl", {"legs": [], "joint": 0.5}) == {}
        assert GP.CLASSES == ("safe", "balanced", "pop", "long") and set(GP.CLASS_WORDS) == set(GP.CLASSES)


def test_where_prices_are_graded_safe_needs_green_legs():
    with _Env(QB_PRICE_GRADE=None):
        # Both legs over their price: Safe, and it says so.
        both = GP.ticket_class("nba", _t(0.46, (0.70, -200), (0.66, -180)))
        assert both["class"] == "safe" and both["why"] == \
            "Safe: every leg 64% or better at a Green price, 46% together", both
        # One leg's price costs more than our number: Balanced, and why it is not Safe.
        one = GP.ticket_class("nhl", _t(0.46, (0.70, -200), (0.66, -230)))
        assert one["class"] == "balanced" and one["why"] == ("Balanced: every leg 60% or better, one at a Green "
                                                             "price, 46% together. Not Safe: not every leg at a Green price"), one
        # Neither: a Pop, whatever the chances.
        none = GP.ticket_class("nba", _t(0.46, (0.70, -250), (0.66, -230)))
        assert none["class"] == "pop" and none["why"] == "Pop: 46% together. Not Balanced: no leg at a Green price", none
        # The same ticket in football, whose prices are not graded, stands on its chances.
        assert GP.ticket_class("nfl", _t(0.46, (0.70, -250), (0.66, -230)))["class"] == "safe"
    with _Env(QB_PRICE_GRADE="off"):
        assert GP.ticket_class("nba", _t(0.46, (0.70, -250), (0.66, -230)))["class"] == "safe", "the switch"


def test_every_player_prop_ticket_is_classed_and_no_scorer_pair():
    with _Env(QB_PRICE_GRADE=None):
        g = GP.build(EG.board(), "nfl")["games"][0]
        assert [t["class"] for t in g["twos"]] == ["safe", "safe", "balanced"], [t.get("class") for t in g["twos"]]
        assert [t["class"] for t in g["threes"]] == ["pop", "pop", "pop"]
        assert all(t["class_why"].startswith(GP.CLASS_WORDS[t["class"]] + ": ") for t in g["twos"] + g["threes"])
        assert not any("class" in t for t in g["scorers"]), "a touchdown pair says its own rule"
        # A report's rebuild labels its tickets too.
        tp = __import__("test_the_parlays_are_made_of_the_reports_picks")
        b = EG.board()
        b["game_parlays"] = GP.build(b, "nfl")
        x = GP.from_report(b, "nfl", GAME, tp.PICKS)
        assert all(t.get("class") in GP.CLASSES for t in x["twos"] + x["threes"])
        hoops = GP.build(_hoops_board(), "nba")["games"][0]
        assert all(t.get("class") in GP.CLASSES for t in hoops["twos"] + hoops["threes"])


# --- the one book ------------------------------------------------------------------------------
def _quotes(*books):
    return [{"book": b, "line": line, "over_odds": o, "under_odds": u} for b, line, o, u in books]


def _priced_board():
    return {"recommendations": [
        {"player": "Malik Nabers", "market": "receptions", "side": "OVER", "line": 4.5,
         "all_lines": _quotes(("DraftKings", 4.5, -150, 120), ("FanDuel", 4.5, -140, 110), ("BetMGM", 5.5, 105, -135))},
        {"player": "Jayden Daniels", "market": "rush_yds", "side": "OVER", "line": 24.5,
         "all_lines": _quotes(("DraftKings", 24.5, -180, 140), ("FanDuel", 29.5, -115, -115)),
         "alt_lines": _quotes(("FanDuel", 24.5, -200, 150))},
        {"player": "Cam Skattebo", "market": "rush_att", "side": "UNDER", "line": 11.5,
         "all_lines": _quotes(("BetMGM", 11.5, -130, 100))}]}


def _leg(player, market, side, line):
    return {"player": player, "market": market, "side": side, "line": line}


def test_the_one_book_is_the_one_that_has_every_leg_and_pays_most():
    idx = GP.quote_index(_priced_board())
    a, b = _leg("Malik Nabers", "receptions", "Over", 4.5), _leg("Jayden Daniels", "rush_yds", "Over", 24.5)
    assert GP.book_prices(a, idx) == {"draftkings": ("DraftKings", -150), "fanduel": ("FanDuel", -140)}, \
        "the books at this number: BetMGM hangs another line"
    assert GP.book_prices(b, idx) == {"draftkings": ("DraftKings", -180), "fanduel": ("FanDuel", -200)}, \
        "the main line and the ladder both count"
    got = GP.one_book([a, b], idx)
    # DraftKings pays 1.667 x 1.556 = 2.59; FanDuel 1.714 x 1.5 = 2.57.
    assert got == {"book": "DraftKings", "odds": [-150, -180], "books": 2,
                   "words": "One book has every leg: DraftKings (-150, -180)"}, got
    # An under reads the under price.
    assert GP.book_prices(_leg("Cam Skattebo", "rush_att", "Under", 11.5), idx) == {"betmgm": ("BetMGM", 100)}


def test_no_one_book_says_so_and_a_leg_with_no_quote_says_nothing():
    idx = GP.quote_index(_priced_board())
    a, b = _leg("Malik Nabers", "receptions", "Over", 4.5), _leg("Jayden Daniels", "rush_yds", "Over", 24.5)
    c = _leg("Cam Skattebo", "rush_att", "Under", 11.5)
    two = GP.one_book([a, c], idx)
    assert two == {"none": True, "words": "No one book in our pull has both legs at these numbers"}, two
    three = GP.one_book([a, b, c], idx)
    assert three["none"] is True and three["words"] == \
        "No one book in our pull has every leg at these numbers; FanDuel has 2 of the 3", three
    # A leg we hold no quote for: nothing to tell, so nothing is said.
    assert GP.one_book([a, _leg("Nobody", "receptions", "Over", 2.5)], idx) is None
    assert GP.one_book([a, _leg("Jayden Daniels", "rush_yds", "Over", 99.5)], idx) is None
    assert GP.one_book([a], idx) is None and GP.quote_index({}) == {} and GP.book_prices(a, {}) == {}
    assert [GP.leg_quoted(l, idx) for l in (a, _leg("Jayden Daniels", "rush_yds", "Over", 99.5),
                                            _leg("Nobody", "receptions", "Over", 2.5))] == ["quoted", "no_quote", "no_row"]


def test_a_legs_own_book_counts_and_no_one_book_needs_every_legs_quotes():
    idx = GP.quote_index(_priced_board())
    nabers = dict(_leg("Malik Nabers", "receptions", "Over", 4.5), book="FanDuel", odds=-140)
    # Two props with no quote list on file, each naming its own book and price.
    x = dict(_leg("Chig Okonkwo", "receptions", "Over", 2.5), book="FanDuel", odds=-160)
    y = dict(_leg("Rachaad White", "rush_yds", "Over", 29.5), book="BetMGM", odds=-150)
    # Their own books agree with a book that has the other leg: that book has every leg, whatever else is unknown.
    got = GP.one_book([nabers, x], idx)
    assert got == {"book": "FanDuel", "odds": [-140, -160], "books": 1,
                   "words": "One book has every leg: FanDuel (-140, -160)"}, got
    assert GP.one_book([x, dict(y, book="FanDuel")], {})["book"] == "FanDuel", "with no quotes on file at all"
    # They differ, and one leg's other books are unknown: nothing is said, never "no one book".
    assert GP.one_book([nabers, y], idx) is None and GP.one_book([x, y], idx) is None
    # A proxy price is no book.
    assert GP.one_book([dict(x, book="proxy"), dict(y, book="proxy")], idx) is None


def test_the_quotes_are_read_off_the_pick_rows_too():
    row = {"player": "Chig Okonkwo", "market": "receptions", "side": "OVER", "line": 2.5,
           "all_lines": _quotes(("DraftKings", 2.5, -165, 130), ("FanDuel", 2.5, -160, 125))}
    # (The matchup picks are listed a game at a time, engine/matchpicks: its touchdown rows and its prop rows.)
    for where, rows in (("most_likely", [row]), ("matchup_picks", [{"game": "WAS@NYG", "td": [], "props": [row]}])):
        idx = GP.quote_index({"recommendations": [], where: rows})
        assert GP.book_prices(_leg("Chig Okonkwo", "receptions", "Over", 2.5), idx) == \
            {"draftkings": ("DraftKings", -165), "fanduel": ("FanDuel", -160)}, where
    idx = GP.quote_index({"likely_board": {"rows": [row]}})
    assert GP.leg_quoted(_leg("Chig Okonkwo", "receptions", "Over", 2.5), idx) == "quoted"
    assert GP.QUOTE_LISTS == ("recommendations", "most_likely", "matchup_picks")


def test_a_built_game_names_each_tickets_book():
    b = EG.board()
    # Every Most Likely row's own number at two books, DraftKings the better payer.
    b["recommendations"] = [
        {"player": r["player"], "market": r["market"], "side": r["side"], "line": r["line"],
         "all_lines": _quotes(("DraftKings", r["line"], -150, 120), ("FanDuel", r["line"], -160, 125))}
        for r in b["most_likely"]]
    g = GP.build(b, "nfl")["games"][0]
    for t in g["twos"] + g["threes"]:
        assert t["one_book"]["book"] == "DraftKings" and t["one_book"]["books"] == 2, t.get("one_book")
        assert t["one_book"]["odds"] == [-150] * len(t["legs"])
    assert not any("one_book" in t for t in g["scorers"])
    # The fixture board files no book's quotes: its legs' own book (DraftKings on every one) is the
    # one book, and none says "no one book".
    plain = GP.build(EG.board(), "nfl")["games"][0]
    assert all(t["one_book"]["book"] == "DraftKings" for t in plain["twos"] + plain["threes"])
    assert not any((t.get("one_book") or {}).get("none") for t in plain["twos"] + plain["threes"])


# --- the cards, the record and the heartbeat ---------------------------------------------------
def test_the_cards_carry_the_class_and_the_book():
    with _Env(QB_PRICE_GRADE=None):
        b = EG.board()
        b["recommendations"] = [
            {"player": r["player"], "market": r["market"], "side": r["side"], "line": r["line"],
             "all_lines": _quotes(("DraftKings", r["line"], -150, 120))} for r in b["most_likely"]]
        g = GP.build(b, "nfl")["games"][0]
        c = GP.card(g["twos"][0], 1, "two", "nfl")
        assert (c["cls"], c["cls_label"]) == ("safe", "Safe") and c["cls_why"].startswith("Safe: every leg 64% or better")
        assert c["one_book"] == "One book has every leg: DraftKings (-150, -150)", c.get("one_book")
        pair = GP.card(g["scorers"][0], 1, "scorers", "nfl")
        assert "cls" not in pair and "one_book" not in pair
    report = _js("report")
    assert 'const CLASS_WORDS = { safe: "Safe", balanced: "Balanced", pop: "Pop", long: "Long shot" };' in report
    assert '<span class="gr-parlay-class ${escapeAttr(t.cls)}">${escapeHtml(t.cls_label || "")}</span>' in report
    assert '<p class="gr-parlay-classwhy">${escapeHtml(t.cls_why)}</p>' in report
    assert '<p class="gr-parlay-book${t.one_book_gone ? " gone" : ""}">${escapeHtml(t.one_book)}</p>' in report
    assert "one_book: (t.one_book || {}).words || \"\"," in report, "the page's own card carries it too"
    css = (ROOT / "web" / "css" / "report.css").read_text(encoding="utf-8")
    for cls in (".gr-parlay-class.safe", ".gr-parlay-class.balanced", ".gr-parlay-class.pop", ".gr-parlay-class.long"):
        assert cls in css, cls


def test_the_record_splits_each_leagues_tickets_by_class():
    from engine import ledger
    conn = ledger.connect(":memory:")
    PL.ensure_schema(conn)

    def ticket(key, status, joint, legs, sport="nfl", source="game_two"):
        cur = conn.execute(
            "INSERT INTO parlays (ts, sport, date, legs_key, parlay_type, n_legs, grade, source, status, at_start, "
            "modeled_joint, pnl_units) VALUES ('2026-11-21T12:00', ?, '2026-11-21', ?, 'same_game', ?, 'A@B', ?, ?, 1, ?, ?)",
            (sport, key, len(legs), source, status, joint, 1.5 if status == "won" else -1.0))
        for n, (p, odds) in enumerate(legs, 1):
            conn.execute("INSERT INTO parlay_legs (parlay_id, leg_no, player, market, side, line, odds, p_final, status) "
                         "VALUES (?, ?, ?, 'receptions', 'OVER', 2.5, ?, ?, ?)",
                         (cur.lastrowid, n, f"{key}{n}", odds, p, "won" if status == "won" else "lost"))
    ticket("s1", "won", 0.45, [(0.68, -200), (0.66, -190)])
    ticket("s2", "won", 0.44, [(0.67, -200), (0.66, -190)])
    ticket("s3", "lost", 0.43, [(0.66, -200), (0.65, -190)])
    ticket("b1", "lost", 0.38, [(0.63, -170), (0.61, -160)])
    ticket("p1", "lost", 0.30, [(0.56, -130), (0.54, -120)])
    ticket("t1", "lost", 0.30, [(0.68, -200), (0.67, -200), (0.66, -190)], source="game_three")
    ticket("td", "won", 0.16, [(0.45, 130), (0.36, 165)], source="game_td")
    conn.commit()
    with _Env(QB_PRICE_GRADE=None):
        rec = PL.game_parlay_record(conn)
    two = rec["nfl"]["two"]["by_class"]
    assert list(two) == ["safe", "balanced", "pop"], list(two)
    assert (two["safe"]["graded"], two["safe"]["wins"], two["safe"]["chance"], two["safe"]["net_units"]) == (3, 2, 0.44, 2.0)
    assert (two["balanced"]["graded"], two["balanced"]["wins"]) == (1, 0) and (two["pop"]["graded"], two["pop"]["wins"]) == (1, 0)
    assert rec["nfl"]["three"]["by_class"] == {"pop": {"graded": 1, "wins": 0, "chance": 0.3, "net_units": -1.0}}
    assert "by_class" not in rec["nfl"]["scorers"], "a scorer pair is not classed"
    assert PL.CLASS_KINDS == ("three", "two")
    record = _js("record")
    assert 'const GP_CLASSES = [["safe", "Safe"], ["balanced", "Balanced"], ["pop", "Pop"], ["long", "Long shots"]];' in record
    assert "${close}${rebuilt}${madeUp}${byClass}" in record and "By class: " in record


def test_the_heartbeat_counts_classes_by_size_and_one_book_tickets():
    import launch as L
    with _Env(QB_PRICE_GRADE=None):
        b = EG.board()
        b["recommendations"] = [
            {"player": r["player"], "market": r["market"], "side": r["side"], "line": r["line"],
             "all_lines": _quotes(("DraftKings", r["line"], -150, 120))} for r in b["most_likely"]]
        GP.attach(b, "nfl")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "b.json")
        with open(path, "w") as fh:
            json.dump(b, fh)
        was = L._full_copy
        L._full_copy = lambda p: p
        try:
            got = L._board_counts(path)
        finally:
            L._full_copy = was
    assert got["ticket_classes"] == {"three": {"pop": 3}, "two": {"safe": 2, "balanced": 1}}, got.get("ticket_classes")
    assert got["one_book"] == {"one": 6, "none": 0, "gone": 0, "unknown": 0}, got.get("one_book")
    # Leg by leg: nine three-leg legs and six two-leg ones, every one with a book's quote on file.
    assert got["one_book_legs"] == {"quoted": 15, "unlisted": 0, "no_quote": 0, "no_row": 0}, got.get("one_book_legs")


if __name__ == "__main__":
    fails = 0
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
