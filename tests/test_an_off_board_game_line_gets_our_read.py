"""A side or a total no board prices still gets our number and our data.

Ethan, 2026-10-13, under a graded slip whose "Milwaukee Brewers moneyline"
and "Milwaukee Brewers @ Los Angeles Dodgers · Under 7.5" both read NOT ON
OUR BOARD: "you didn't add where if there's a pick [not] in the board we use
our data to explain if it's a good pick or not".

What is pinned, offline, on a history database built here:

  * THE READ (engine/slipgame): the league's own game model on a game the
    board never priced — baseball's ratings and starters, hockey's goals
    model and its puck line, the NBA through the futures curve — and a
    bet our models cannot price (a basketball total, a puck line at 2.5)
    said so, with the data beside it all the same;
  * HELD TO THE MARKET: the number pulled toward the market's own as the
    boards hold theirs, the board's posted pair preferred over the slip's
    price, a disagreement past the credible ceiling named;
  * WHICH GAME: "away @ home" read as written, the board's schedule first,
    a name that fits two teams never guessed;
  * THE DATA: form, meetings, how often each side's games went the leg's
    way, where the board's own line sits when it prices another number;
  * THE CARD: counted as our read, said in the conversation, labelled on
    the page, never shown a book's price it does not have.

Run directly: `python3 tests/test_an_off_board_game_line_gets_our_read.py`
"""
import datetime as dt
import os
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import askbot as AB                                   # noqa: E402
from engine import db as DB                                       # noqa: E402
from engine import gamebets as GB                                 # noqa: E402
from engine import slipgame as SGM                                # noqa: E402
from engine import slipgrade as SG                                # noqa: E402
from engine import slipread as SR                                 # noqa: E402

SLIP_JS = ROOT / "web" / "js" / "slip.js"
TODAY = dt.date.today().isoformat()
MLB = {"MIL": 0.9, "LAD": 1.3, "CLE": 0.4, "TBR": 0.2, "NYY": 0.8, "SEA": 0.1, "CHC": 0.3, "BOS": -0.2}


def _history(seed=7):
    """A season of MLB, a season of hockey and one of the NBA, every final
    a real score."""
    path = _SANDBOX / f"h{seed}.db"
    if path.exists():
        path.unlink()
    H = DB.connect(path)
    rng = random.Random(seed)

    def fill(sport, teams, n, base, sd, season, start):
        rows, names = [], list(teams)
        for i in range(n):
            h, a = rng.sample(names, 2)
            hs = max(0, int(round(rng.gauss(base + teams[h], sd))))
            as_ = max(0, int(round(rng.gauss(base + teams[a] - 0.2, sd))))
            if hs == as_:
                hs += 1
            d = (start + dt.timedelta(days=i // 2)).isoformat()
            rows.append({"sport": sport, "season": season, "period": d, "game_id": f"{a}@{h}-{i}", "date": d,
                         "home": h, "away": a, "home_score": float(hs), "away_score": float(as_)})
        DB.upsert_games(H, rows)
    year = dt.date.today().year
    fill("mlb", MLB, 400, 4.5, 3.0, year, dt.date(year, 4, 1))
    fill("nhl", {"TOR": 0.4, "MTL": -0.3, "BOS": 0.2, "NYR": 0.1, "EDM": 0.5, "VAN": -0.1}, 300, 3.0, 1.6,
         2025, dt.date(2025, 10, 8))
    fill("nba", {"BOS": 6, "NYK": 3, "LAL": 1, "GSW": 2, "MIA": -1, "DET": -4}, 300, 112, 12, 2025,
         dt.date(2025, 10, 22))
    H.commit()
    return H, path


def _leg(**kw):
    leg = {"sport": "mlb", "player": "", "team": "", "game": "", "market": "moneyline", "side": "team",
           "line": 0.0, "odds": -110, "text": ""}
    leg.update(kw)
    return leg


def _facts(row):
    return {k: t for k, t in row.get("facts") or []}


# --- the read -------------------------------------------------------------------
def test_the_screenshots_two_legs_get_a_number_and_the_data_behind_it():
    SR.clear_cache()
    H, _ = _history()
    ml = SGM.read({}, _leg(team="Milwaukee Brewers", game="Milwaukee Brewers @ Los Angeles Dodgers",
                           odds=145), conn=H, today=TODAY)
    assert (ml["home"], ml["away"], ml["team"]) == ("LAD", "MIL", "MIL"), "away @ home, as written"
    assert ml["prob"] is not None and ml["raw_prob"] is not None and not ml["refused"]
    f = _facts(ml)
    for k in ("Our read", "Our model", "Ratings", "Starters", "The market", "Held to the market", "Form",
              "Head to head"):
        assert k in f, (k, list(f))
    assert "doesn't have this game on its slate" in f["Our read"] or "no baseball board" in f["Our read"]
    assert "league-average arms" in f["Starters"], "a game off the board has no named starters — said"
    under = SGM.read({}, _leg(game="Milwaukee Brewers @ Los Angeles Dodgers", market="total", side="under",
                              line=7.5, odds=-105), conn=H, today=TODAY)
    fu = _facts(under)
    assert under["proj_total"] is not None and "against 7.5" in fu["Our model"]
    assert "went under 7.5 in" in fu["Totals"], "how often each side's games went the leg's way"
    # The under and the over at one number are complements before the market holds them.
    over = SGM.read({}, _leg(game="Milwaukee Brewers @ Los Angeles Dodgers", market="total", side="over",
                             line=7.5, odds=-115), conn=H, today=TODAY)
    assert abs(over["raw_prob"] + under["raw_prob"] - 1.0) < 1e-3


def test_the_market_holds_the_number_and_a_wild_gap_is_named():
    SR.clear_cache()
    H, _ = _history()
    leg = _leg(team="Dodgers", game="Brewers @ Dodgers", odds=-120)
    row = SGM.read({}, leg, conn=H, today=TODAY)
    fair, raw, prob = row["market_fair"], row["raw_prob"], row["prob"]
    assert row["fair_from"] == "slip" and abs(fair - SG.implied(-120) / (1 + SGM.TYPICAL_MARGIN["moneyline"])) < 1e-3
    assert min(raw, fair) - 1e-6 <= prob <= max(raw, fair) + 1e-6, "pulled toward the market, never past it"
    # The board's own posted pair beats the slip's price when the board has the game.
    board = {"mlb": {"games": [{"home": "LAD", "away": "MIL", "home_ml": -150, "away_ml": 130}], "game_bets": []}}
    on = SGM.read(board, leg, conn=H, today=TODAY)
    from engine.odds import devig_two_way
    assert on["fair_from"] == "board" and abs(on["market_fair"] - devig_two_way(-150, 130)[0]) < 1e-3
    assert "no book had posted this market" in on["why_off"]
    # A raw disagreement past the credible ceiling is called what it is.
    held = SGM.held(0.80, 0.50, "mlb", "moneyline")
    assert held[1] is False and 0.5 < held[0] < 0.8
    assert GB.MAX_CREDIBLE_EDGE < 0.30


def test_starters_and_the_boards_own_number_come_off_its_card():
    SR.clear_cache()
    H, _ = _history()
    board = {"mlb": {"games": [{"home": "LAD", "away": "MIL", "home_ml": -150, "away_ml": 130,
                                "pitchers": {"home": {"name": "Yoshinobu Yamamoto", "xera": 2.9},
                                             "away": {"name": "Freddy Peralta", "xera": 3.5}}}],
                     "game_bets": [{"market": "total", "home": "LAD", "away": "MIL", "line": 8.5, "side": "Over",
                                    "win_prob": 0.5}]}}
    row = SGM.read(board, _leg(game="MIL @ LAD", market="total", side="under", line=7.5), conn=H, today=TODAY)
    assert row["why_off"] == "the board prices this total at 8.5, not 7.5"
    ml = SGM.read(board, _leg(team="LAD", game="MIL @ LAD", odds=-150), conn=H, today=TODAY)
    assert "Yoshinobu Yamamoto (2.90 xERA)" in _facts(ml)["Starters"]
    # The starters move the number the way the board's own curve does.
    ratings, _ = SGM._ratings(H, "mlb", dt.date.today().year)
    h, a = ratings["LAD"], ratings["MIL"]
    assert abs(SGM.model(H, "mlb", "LAD", "MIL", board["mlb"]["games"][0], TODAY)["p_home"]
               - GB.mlb_win_prob(h.net, a.net, 2.9, 3.5)) < 1e-9


def test_the_mlb_margin_is_the_one_the_moneyline_reads():
    for args in ((0.5, 0.2, 3.2, 4.4), (-0.3, 0.6, 4.1, 4.1), (1.0, -1.0, 5.0, 2.8)):
        m = GB.mlb_margin(*args)
        p = GB.normal_cdf(m / GB.MLB_MARGIN_SD)
        assert abs(GB.mlb_win_prob(*args) - max(0.03, min(0.97, p))) < 1e-12


def test_hockey_prices_the_puck_line_and_says_when_it_cannot():
    SR.clear_cache()
    H, _ = _history()
    pl = SGM.read({}, _leg(sport="nhl", team="Maple Leafs", game="Canadiens @ Maple Leafs", market="spread",
                           line=-1.5, odds=160), conn=H, today="2026-01-15")
    assert (pl["home"], pl["away"]) == ("TOR", "MTL") and pl["prob"] is not None
    two = SGM.read({}, _leg(sport="nhl", team="Maple Leafs", game="Canadiens @ Maple Leafs", market="spread",
                            line=-2.5, odds=300), conn=H, today="2026-01-15")
    assert two["prob"] is None and "1.5 goals only" in two["refused"]
    assert "Form" in _facts(two), "no number — and the data all the same"
    tot = SGM.read({}, _leg(sport="nhl", game="Canadiens @ Maple Leafs", market="total", side="over", line=6.5,
                            odds=105), conn=H, today="2026-01-15")
    assert tot["prob"] is not None and "goals" in _facts(tot)["Our model"]


def test_basketball_sides_use_the_futures_curve_and_a_total_gets_facts_only():
    SR.clear_cache()
    H, _ = _history()
    ml = SGM.read({}, _leg(sport="nba", team="Boston Celtics", game="Knicks @ Celtics", odds=-180), conn=H,
                  today="2026-01-15")
    from engine import futures as F
    ratings, _share, _played = SGM._hoops(H, "nba", 2025)
    assert abs(ml["raw_prob"] - max(0.02, min(0.98, F.win_prob("nba", ratings["BOS"], ratings["NYK"])))) < 1e-4
    tot = SGM.read({}, _leg(sport="nba", game="Knicks @ Celtics", market="total", side="over", line=224.5),
                   conn=H, today="2026-01-15")
    assert tot["prob"] is None and "game total in the NBA" in tot["refused"]
    assert "went over 224.5 in" in _facts(tot)["Totals"]


# --- which game -----------------------------------------------------------------
def test_home_and_away_are_read_as_written_and_never_guessed_from_two_names():
    SR.clear_cache()
    H, _ = _history()
    board = {"mlb": {"games": [{"home": "TBR", "away": "CLE"}]}}
    got = SGM.teams_of(board, _leg(team="Rays", game="Guardians vs Rays"), "mlb", H, TODAY)
    assert got[:3] == ("TBR", "CLE", "TBR") and got[4] == "board", "the board's schedule decides first"
    got = SGM.teams_of({}, _leg(team="Brewers", game="Brewers @ Dodgers"), "mlb", H, TODAY)
    assert got[:2] == ("LAD", "MIL") and got[4] == "slip"
    assert SGM.read({}, _leg(team="", game="the night game"), conn=H, today=TODAY) is None


# --- the card -------------------------------------------------------------------
def test_the_card_counts_says_and_shows_the_read():
    SR.clear_cache()
    H, path = _history()
    H.close()
    AB.HISTORY_DB = str(path)
    try:
        boards = {"mlb": {"date": TODAY, "games": [{"home": "TBR", "away": "CLE", "home_ml": -132, "away_ml": 112}],
                          "game_bets": [{"market": "moneyline", "home": "TBR", "away": "CLE", "team": "TBR",
                                         "win_prob": 0.55, "odds": -132, "home_odds": -132, "away_odds": 112,
                                         "fair_prob": 0.55, "reasons": ["Run rating"]}]}}
        slip = {"legs": [
            _leg(team="Tampa Bay Rays", game="CLE @ TBR", odds=-132),
            _leg(team="Milwaukee Brewers", game="Milwaukee Brewers @ Los Angeles Dodgers", odds=145),
            _leg(game="Milwaukee Brewers @ Los Angeles Dodgers", market="total", side="under", line=7.5, odds=-105),
        ], "total_odds": 900}
        card = SG.grade(slip, boards)
    finally:
        AB.HISTORY_DB = None
    by = {l["market"] + (l.get("team") or ""): l for l in card["legs"]}
    assert by["moneylineTBR"]["found"] == "game", "the board's own card still wins where it has one"
    assert by["moneylineMIL"]["found"] == "game_read" and by["moneylineMIL"]["prob"] is not None
    assert by["total"]["found"] == "game_read" and by["total"]["game"] == "MIL @ LAD"
    assert by["moneylineMIL"]["read"]["game_model"] and by["moneylineMIL"]["read"]["raw"] is not None
    assert card["n_read"] == 2 and card["n_priced"] == 3
    ks = [w["k"] for w in by["total"]["why"]]
    assert ks[0] == "Our read" and "The market" in ks and "Totals" in ks
    text = SG.summary(card)
    assert "1 on our boards, 2 more read by our own model off the board" in text
    assert "so we ran our game model on it" in text
    # No book's price is shown for a bet whose row is our model's, not a quote.
    from engine import sliplive as SL
    assert SL._game_prices(by["moneylineMIL"], boards["mlb"]) is None


def test_the_page_labels_a_game_read_and_says_a_refusal():
    js = SLIP_JS.read_text(encoding="utf-8")
    assert 'game_read: "Our read — not on our board"' in js
    assert 'l.found === "game_read" && r && l.prob == null' in js, "a read with no number still says what we know"
    assert "held to the market" in js


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
