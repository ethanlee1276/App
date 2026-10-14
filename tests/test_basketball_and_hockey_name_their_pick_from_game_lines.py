"""Basketball and hockey name a Pick of the Day, off the game lines Pinnacle quoted.

Ethan, 2026-10-14: "Also we only show the pick of the day record for nfl
and mlb but no other sport. Fix that"

The college and basketball builds journaled the card before it existed
(tests/test_every_league_records_its_pick_of_the_day.py). That was half of
it. The other half: the NBA and NHL boards hand the selector player props
only — no game market is measured for either league, so the Most Likely
board keeps every game line off (Ethan's own rule, 2026-09-02), and the
day's pick is game markets only — so neither league could ever name one.

`potd.game_lines` turns the game lines the odds pull already hangs on the
slate (Pinnacle's two-way pair and the best soft price, per side) into
rows the selector judges by the bars every sharp-anchored pick answers to.
They are never seated on the Most Likely board; the build hands them to
the relock beside it. This file holds the rows, the selection, the lock,
the journal, the grading and the wiring.

Run directly: `python3 tests/test_basketball_and_hockey_name_their_pick_from_game_lines.py`
"""

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import db, ledger, potd                           # noqa: E402


class _Game:
    """A slate game the way the builds' `_Game` carries one after the
    odds pull (`oddsapi.apply_odds_to_slate` sets these attributes)."""

    def __init__(self, home="BOS", away="NYK", **kw):
        self.home, self.away = home, away
        self.kickoff = _kickoff(180)[1]
        self.live = None
        self.spread = self.total = None
        self.home_ml = self.away_ml = 0
        for k, v in kw.items():
            setattr(self, k, v)


def _priced(home="BOS", away="NYK", **kw):
    """Pinnacle has the home side 58% (-150 / +130); DraftKings pays -130
    on it, +2.6% EV. The away side is the worse half of the same pair."""
    g = dict(sharp_home_ml=-150, sharp_away_ml=130, home_ml=-130, away_ml=120,
             home_ml_book="DraftKings", away_ml_book="FanDuel")
    g.update(kw)
    return _Game(home, away, **g)


def _day():
    return _kickoff(180)[0]


def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _board(*rows):
    return {"date": _day(), "most_likely": list(rows)}


def _prop():
    d, k = _kickoff(180)
    return {"kind": "prop", "player": "A Player", "team": "BOS", "opponent": "NYK",
            "market": "points", "side": "OVER", "line": 20.5, "book": "DraftKings",
            "odds": -110, "model_prob": 0.6, "implied_prob": 0.52, "bettable": True,
            "game_date": d, "kickoff": k}


# --- the rows ------------------------------------------------------------------
def test_a_moneyline_pinnacle_quoted_becomes_two_rows_at_its_fair():
    rows = potd.game_lines([_priced()], _day())
    ml = {r["team"]: r for r in rows if r["market"] == "moneyline"}
    assert set(ml) == {"BOS", "NYK"}, rows
    assert abs(ml["BOS"]["sharp_fair"] + ml["NYK"]["sharp_fair"] - 1.0) < 1e-3
    bos = ml["BOS"]
    assert (bos["odds"], bos["book"], bos["player"]) == (-130, "DraftKings", "BOS ML")
    assert bos["sharp_anchored"] and potd.evidence(bos) == "sharp"
    assert bos["model_prob"] is None, "a game line no model of ours priced claims no number of ours"
    assert bos["from_game_lines"] and bos["kind"] == "game" and bos["game_date"] == _day()


def test_a_spread_or_total_counts_only_at_the_line_pinnacle_quoted():
    """A fair at 221.5 says nothing about a bet at 222."""
    same = _priced(spread=-3.5, sharp_spread=-3.5, spread_home_odds=-105, spread_away_odds=-115,
                   sharp_spread_home_odds=-110, sharp_spread_away_odds=-110,
                   home_spread_book="BetMGM", away_spread_book="Caesars",
                   total=221.5, sharp_total=221.5, total_over_odds=-108, total_under_odds=-112,
                   sharp_total_over_odds=-105, sharp_total_under_odds=-115,
                   total_over_book="FanDuel", total_under_book="DraftKings")
    rows = potd.game_lines([same], _day())
    spreads = {r["team"]: r for r in rows if r["market"] == "spread"}
    assert (spreads["BOS"]["line"], spreads["BOS"]["side"]) == (-3.5, "-3.5")
    assert (spreads["NYK"]["line"], spreads["NYK"]["side"]) == (3.5, "+3.5")
    totals = {r["side"]: r for r in rows if r["market"] == "total"}
    assert set(totals) == {"Over", "Under"} and totals["Over"]["line"] == 221.5
    assert totals["Under"]["sharp_fair"] > totals["Over"]["sharp_fair"], "-115 is the likelier side"
    moved = _priced(spread=-3.5, sharp_spread=-4.0, spread_home_odds=-105, spread_away_odds=-115,
                    sharp_spread_home_odds=-110, sharp_spread_away_odds=-110,
                    home_spread_book="BetMGM", away_spread_book="Caesars",
                    total=222.0, sharp_total=221.5, total_over_odds=-108, total_under_odds=-112,
                    sharp_total_over_odds=-105, sharp_total_under_odds=-115,
                    total_over_book="FanDuel", total_under_book="DraftKings")
    assert {r["market"] for r in potd.game_lines([moved], _day())} == {"moneyline"}


def test_no_pinnacle_pair_or_no_book_is_no_row():
    assert potd.game_lines([_Game(home_ml=-130, away_ml=120, home_ml_book="DraftKings",
                                  away_ml_book="FanDuel")], _day()) == []
    half = potd.game_lines([_priced(away_ml_book="")], _day())
    assert [r["team"] for r in half] == ["BOS"], "a side no book is posting is no row"


def test_a_game_under_way_is_marked_from_the_boards_own_state():
    rows = potd.game_lines([_priced()], _day(),
                           [{"home": "BOS", "away": "NYK", "live": {"state": "live"}}])
    assert rows and all(r["live"] and r["started"] for r in rows)
    assert potd.disqualify(rows[0]) == potd.STARTED


# --- the selection ---------------------------------------------------------------
def test_a_props_only_board_names_a_pick_from_its_game_lines():
    out = _board(_prop())
    lines = potd.game_lines([_priced()], _day())
    potd.attach(out, "nba", built_dir=tempfile.mkdtemp(), lines=lines)
    card = out["pick_of_the_day"]
    assert card["verdict"]["call"] == "bet", card
    pick = card["pick"]
    assert (pick["team"], pick["market"], pick["evidence"]) == ("BOS", "moneyline", "sharp")
    assert pick["from_game_lines"] and round(pick["fair_prob"], 2) == 0.58
    assert pick["model_prob"] is None
    assert [r["player"] for r in out["most_likely"]] == ["A Player"], \
        "a game line was seated on a Most Likely board that measures none"


def test_without_its_game_lines_the_same_board_says_it_has_none():
    out = _board(_prop())
    potd.attach(out, "nba", built_dir=tempfile.mkdtemp())
    assert out["pick_of_the_day"]["pick"] is None
    assert "no game line on this board" in out["pick_of_the_day"]["note"]


def test_a_line_the_board_already_holds_is_the_boards_row():
    lines = potd.game_lines([_priced()], _day())
    board_row = dict(next(r for r in lines if r["team"] == "BOS"), from_game_lines=False)
    out = _board(board_row)
    potd.attach(out, "nhl", built_dir=tempfile.mkdtemp(), lines=lines)
    assert out["pick_of_the_day"]["considered"] == 2, "the board's own line was counted twice"
    assert out["pick_of_the_day"]["pick"]["from_game_lines"] is False


def test_the_bars_still_hold_on_a_game_line():
    """No floor moves for these rows: a price too short of the fair, a gap
    too big to trust and a side under 50% are all refused."""
    for kw, why in ((dict(home_ml=-150), "not far enough"),
                    (dict(home_ml=+110), "too big to trust")):
        out = _board()
        potd.attach(out, "nba", built_dir=tempfile.mkdtemp(),
                    lines=[r for r in potd.game_lines([_priced(**kw)], _day()) if r["team"] == "BOS"])
        pick = out["pick_of_the_day"]["pick"]
        assert pick is not None and why in pick["below_bar"], (kw, pick)


# --- the lock, the journal and the grade -------------------------------------------
def test_a_later_build_finds_the_locked_line_among_the_lines():
    """The day's pick is the first one recorded. A later build whose
    selector likes another game re-points the card at the locked line —
    found among the game lines, priced from today's row, not read back
    from the journal as a pick the board no longer carries."""
    conn, built = _conn(), tempfile.mkdtemp()
    first_lines = potd.game_lines([_priced()], _day())
    first = _board(_prop())
    potd.attach(first, "nba", built_dir=built, lines=first_lines)
    assert ledger.journal_potd(first["pick_of_the_day"], conn=conn, path=None)
    later_lines = potd.game_lines(
        [_priced(), _priced("CHI", "MIA", sharp_home_ml=-170, sharp_away_ml=145,
                             home_ml=-140)], _day())     # Pinnacle 61%, +4.0% EV
    later = _board(_prop())
    potd.attach(later, "nba", built_dir=built, lines=later_lines)
    assert later["pick_of_the_day"]["pick"]["team"] == "CHI", "the fixture lost its better line"
    card = ledger.relock_potd(later["pick_of_the_day"], later["most_likely"] + later_lines, conn=conn)
    assert (card["pick"]["team"], card["pick"].get("locked")) == ("BOS", True), card["pick"]
    assert not card["pick"].get("off_board"), card.get("relocked")
    assert ledger.journal_potd(card, conn=conn, path=None) == ""


def test_the_record_holds_the_claim_the_card_printed():
    conn = _conn()
    out = _board(_prop())
    potd.attach(out, "nhl", built_dir=tempfile.mkdtemp(),
                lines=potd.game_lines([_priced("TOR", "MTL")], _day()))
    assert ledger.journal_potd(out["pick_of_the_day"], conn=conn, path=None)
    row = conn.execute("SELECT sport, player, market, side, line, odds, book, hit_prob, edge, "
                       "evidence, category, stake_units FROM bets").fetchone()
    assert (row["sport"], row["player"], row["market"], row["side"], row["line"]) == \
        ("nhl", "TOR", "moneyline", "OVER", 0.5)
    assert (row["odds"], row["book"], row["category"], row["stake_units"]) == \
        (-130, "DraftKings", "potd", 1.0)
    assert round(row["hit_prob"], 2) == 0.58, "the claim is the sharp fair the card printed"
    assert row["edge"] is None and row["evidence"] == "sharp"


def test_a_game_line_pick_grades_off_the_final():
    """Moneyline, spread and total, each from the stored final — the
    basketball schedule's numeric game id included, which a total's
    matchup key cannot match directly."""
    t = Path(tempfile.mkdtemp())
    L, H = ledger.connect(t / "l.db"), db.connect(t / "h.db")
    day = _day()
    H.execute("INSERT INTO games (sport, season, period, game_id, date, home, away, "
              "home_score, away_score) VALUES ('nba', 2026, ?, '0022600123', ?, 'BOS', 'NYK', 110, 101)",
              (day, day))
    H.commit()
    for market, player, side, line in (("moneyline", "BOS", "OVER", 0.5),
                                       ("spread", "BOS", "OVER", 3.5),
                                       ("total", "NYK@BOS", "UNDER", 221.5)):
        L.execute("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, "
                  "stake_units, stake_dollars, status, category) VALUES "
                  "(?, 'nba', ?, ?, ?, ?, ?, ?, -110, 1, 0, 'open', 'potd')",
                  (f"{day}T15:00:00", day, day, player, market, side, line))
    L.commit()
    assert ledger.settle_from_history(L, H, sport="nba") == 3
    got = dict(L.execute("SELECT market, status FROM bets").fetchall())
    assert got == {"moneyline": "won", "spread": "won", "total": "won"}, got


# --- the wiring ----------------------------------------------------------------------
def test_basketball_and_hockey_hand_their_lines_to_the_pick_and_the_lock():
    for fn in ("nba_build.py", "nhl_build.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        assert "game_lines(slate.games" in src, f"{fn} makes no game lines"
        assert "lines=potd_lines" in src, f"{fn} does not hand them to the pick"
        assert "+ potd_lines" in src, f"{fn} does not hand them to the relock"
    assert set(potd.LINE_LEAGUES) == {"nba", "wnba", "nhl"}


def test_football_and_baseball_keep_their_boards_own_bars():
    """Their Most Likely boards carry measured game rows, and a row that
    board refused on the merits must not reach the pick by another door."""
    for fn in ("nfl_build.py", "cfb_build.py", "mlb_build.py"):
        src = (ROOT / fn).read_text(encoding="utf-8")
        assert "game_lines(" not in src and "lines=" not in src.split("_potd.attach(")[1][:80], fn


# --- the record page -------------------------------------------------------------------
def test_every_league_that_names_a_pick_has_a_book_and_ufc_has_none():
    conn = _conn()
    path = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, path)
    by = json.loads(path.read_text(encoding="utf-8"))["potd_by_sport"]
    assert {"nfl", "cfb", "mlb", "nba", "nhl"} <= set(by), sorted(by)
    assert "ufc" not in by, "the fight card makes no Pick of the Day"
    assert "wnba" not in by, "the bench reached the record page"
    assert all(not v["settled"] and not v["open"] for v in by.values())


def test_the_section_follows_the_book():
    from test_potd_card import _run_section
    assert "Nothing settled yet." in _run_section({"settled": 0, "open": 0}, "nba")
    assert _run_section(None, "ufc") == "", "a league with no book drew its section"


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
