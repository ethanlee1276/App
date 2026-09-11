"""A row ranked on the market's number is not refused for the model disagreeing with it.

Ethan, 2026-09-08: "Ok it seems like we have player props just barley
any money money lines are touchdown crap so maybe we should look into
that for the NFL most likely bets."

THE MONEYLINE HALF. Since 2026-09-07 a football moneyline row ranks on
the book's de-vigged number, because that number sorts winners better
than the model's (likely.GAME_RANK_MARKET: 0.722 against 0.677 on the
NFL). The row's claim is therefore the market's. `likely.engine_credible`
— the Gelof guard, written for a prop whose raw model claim was thirty
points from a price that could not be real — was still asked of that
row, and refused it whenever the model's own rating sat more than ten
points from the book. Measured on this box's closes (2026-09-08,
`python3 -m engine.gamerank --sport nfl --raw-bar`; 1,356 quoted games
on the ratings the build ships):

    favourites the board could carry (fair >= 55%, price >= -250)   681
    …the raw bar would refuse                                        207   30%
    the market's number on the rows kept:     claimed 61.4%  landed 64.3%
    the market's number on the rows refused:  claimed 61.4%  landed 62.3%
    refused minus kept, 95% by game                        [-9.8%, +5.7%]
    by size of the disagreement: 10-15 pts +2.2 · 15-20 -0.6 · 20-30 -1.9

College, the same walk (2,729 games): 1,066 eligible, 401 refused (38%);
kept claimed 62.2% landed 60.2%; refused claimed 64.0% landed 63.8%;
95% [-4.3%, +7.8%].

The market lands where it claims on the games the model disputes, at
every size of dispute — what `gamecal` already said of the same model
from the other side (slope of its disagreement against the close,
-0.057 +/- 0.135). A bar that removes three rows in ten and changes
nothing measurable is a shelf a third empty.

What this pins:

  * `engine_credible` answers True for a market-ranked row whatever the
    raw gap, and still False for a model-ranked one;
  * the MIN -220 card from tests/test_game_claim.py ships through
    `build` with an empty census, its note printing the model's own
    53% as the model's and saying why the disagreement does not bar it;
  * a row that ranks on the model still answers the RAW refusal;
  * the page keeps such a row (`showableLikelyRow`) and its card labels
    the hero tile "Market" with a "Model" tile beside it;
  * the board lint prints the disagreement as OWN READ, not RAW GAP;
  * `gamerank.measure_raw_bar` is proven on a synthetic book — the
    suite never reads the box it runs on — and the docs carry the
    droplet command.

Run directly: `python3 tests/test_market_ranked_raw_bar.py`
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine import boardlint as L, db, gamebets as G, gamerank as R, likely as K   # noqa: E402
import engine.gamecal as gamecal                                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
RAW = "the raw model claim, before the shrink, disagrees with the market by more than we credit"


def _no_information(fn):
    """NFL's measured moneyline haircut: priced at the market."""
    def run(*a, **k):
        real = gamecal.shrink_for
        gamecal.shrink_for = lambda sport, market: 0.0
        try:
            return fn(*a, **k)
        finally:
            gamecal.shrink_for = real
    run.__name__ = fn.__name__
    run.__doc__ = fn.__doc__
    return run


def _ml(home, away, home_rating, away_rating, home_ml, away_ml):
    wp = G.nfl_win_prob(home_rating, away_rating)
    # THE BOOK RIDES ON THE CARD. `moneyline_to_dict` does not carry one
    # — `pipeline._finish_bet` fills it off the `Game` — and the Most
    # Likely board refuses a football game price it cannot attribute
    # (2026-09-09, tests/test_game_price_names_its_book.py). Adding it
    # here is what `_finish_bet` would have done on the real path.
    return {**G.moneyline_to_dict(
        G.price_moneyline(home, away, wp, home_ml, away_ml, sport="nfl")),
        "book": "DraftKings"}


def _the_card():
    """GB @ MIN: our ratings make GB the better side, the feed makes MIN
    a -220 favourite — the 2026-09-03 screenshot."""
    return _ml("MIN", "GB", 0.5, 1.1, -220, +200)


# --- the bar ------------------------------------------------------------------
def test_the_raw_bar_does_not_apply_to_a_market_ranked_row():
    row = {"model_prob": 0.67, "engine_raw_prob": 0.33, "fair_prob": 0.67,
           "prob_source": "market"}
    assert K.engine_credible(row) is True
    assert K.engine_credible(dict(row, prob_source="model")) is False
    assert K.engine_credible(dict(row, prob_source="sharp")) is False, \
        "a sharp-ranked row carries no raw claim; one that does is still asked"
    assert K.engine_credible(dict(row, engine_raw_prob=0.60, prob_source="model")) is True


def test_a_model_ranked_row_still_answers_the_raw_refusal():
    row = {"model_prob": 0.67, "side": "", "odds": -180, "book": "best",
           "implied_prob": 0.64, "fair_prob": 0.64, "engine_raw_prob": 0.40,
           "prob_source": "model", "win_prob": 0.67}
    assert K.admissible(row) == RAW
    assert K.admissible(dict(row, prob_source="market", win_prob=0.64)) == ""


# --- the screenshot's row, end to end ----------------------------------------
@_no_information
def test_the_screenshots_row_reaches_the_board_with_both_numbers_named():
    card = _the_card()
    census: dict = {}
    board = K.build([], game_bets=[dict(card)], sport="nfl", census=census)
    assert len(board) == 1 and census == {}, (board, census)
    row = board[0]
    assert row["player"] == "MIN ML" and row["prob_source"] == "market"
    assert row["flipped"] is True and abs(row["model_prob"] - 0.67) < 0.02, row["model_prob"]
    # The model's own number, flipped with the side, stays on the row…
    assert abs(row["engine_raw_prob"] - (1.0 - card["engine_raw_prob"])) < 1e-9
    assert abs(row["engine_raw_prob"] - row["fair_prob"]) > 0.10, "wrong fixture"
    # …and the note prints it as the model's, then says why it does not bar.
    note = row["rank_note"]
    assert "Ranked on the market’s number, 67%" in note, note
    assert f'The model’s own rating has this side at {row["engine_raw_prob"]:.0%}' in note, note
    assert "own rating has this side at 53%" in note, "the ratings' coin flip, not the book's 67%"
    assert "That disagreement does not bar the row" in note, note
    assert "gamerank --raw-bar" in note


@_no_information
def test_a_favourite_the_model_agrees_with_says_nothing_about_a_bar():
    row = K.from_game_bet(dict(_ml("KC", "DEN", 6.0, 0.0, -220, +200)), "nfl")
    assert row is not None and K.admissible(row) == ""
    assert "own rating has this side at" in row["rank_note"]
    assert "does not bar" not in row["rank_note"], row["rank_note"]


@_no_information
def test_the_page_never_sees_the_books_number_under_the_word_model():
    """The card's hero tile is labelled by the number it holds, and the
    model's own read gets its own tile beside it."""
    card = APP[APP.index("function likelyCard("):]
    card = card[:card.index("\nfunction ", 10)]
    assert '<div class="k">${r.prob_source === "market" ? "Market" : "Model"}</div>' in card
    assert "${likelyOwnReadTile(r)}" in card
    tile = APP[APP.index("function likelyOwnReadTile("):]
    tile = tile[:tile.index("\n}") + 2]
    assert 'r.prob_source !== "market"' in tile
    assert "r.engine_raw_prob != null ? r.engine_raw_prob : r.win_prob" in tile


# --- the page, run ------------------------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}", i) + 2]


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 2]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("MAX_CREDIBLE_EDGE")}
      {_const("LIKELY_HEAVIEST_PRICE")}
      var pct = (v) => Math.round(Number(v) * 100) + "%";
      {_fn("shrinkArtefact")}
      {_fn("showableLikelyRow")}
      {_fn("likelyOwnReadTile")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_keeps_a_market_ranked_row_and_tiles_its_own_read():
    got = _node("""
      const row = { odds: -220, model_prob: 0.67, engine_raw_prob: 0.33, fair_prob: 0.67,
                    win_prob: 0.67, prob_source: "market" };
      return {
        market: showableLikelyRow(row),
        model: showableLikelyRow({ ...row, prob_source: "model" }),
        agreeing: showableLikelyRow({ ...row, prob_source: "model", engine_raw_prob: 0.62 }),
        chalk: showableLikelyRow({ ...row, odds: -300 }),
        tile: likelyOwnReadTile(row),
        tileNoRaw: likelyOwnReadTile({ ...row, engine_raw_prob: null, win_prob: 0.61 }),
        tileModelRanked: likelyOwnReadTile({ ...row, prob_source: "model" }),
        tileNothing: likelyOwnReadTile({ prob_source: "market" }),
      };
    """)
    if got is None:
        return
    assert got["market"] is True and got["model"] is False and got["agreeing"] is True, got
    assert got["chalk"] is False, "the price cap still applies to a market-ranked row"
    assert ">Model<" in got["tile"] and "33%" in got["tile"], got["tile"]
    assert "61%" in got["tileNoRaw"]
    assert got["tileModelRanked"] == "" and got["tileNothing"] == ""


# --- the lint -----------------------------------------------------------------
def test_the_lint_reads_the_disagreement_as_information_not_a_fault():
    row = {"kind": "game", "player": "MIN ML", "team": "MIN", "home": "MIN", "away": "GB",
           "market": "moneyline", "bet_type": "moneyline", "side": "", "odds": -220,
           "model_prob": 0.67, "implied_prob": 0.67, "engine_raw_prob": 0.33,
           "fair_prob": 0.67, "prob_source": "market", "ranked": True,
           "game_date": "2099-01-01"}
    flags = L.lint_likely([row], {})[0]["flags"]
    assert not any(f.startswith("RAW GAP") for f in flags), flags
    assert any(f.startswith("OWN READ model 33% vs market 67%") for f in flags), flags
    flags = L.lint_likely([dict(row, prob_source="model")], {})[0]["flags"]
    assert any(f.startswith("RAW GAP") for f in flags), flags
    assert not any(f.startswith("OWN READ") for f in flags), flags


# --- the measurement, on a synthetic book -------------------------------------
def _row(season, week, home, away, hs, as_, ml=None):
    extra = {"spread_odds": [-110, -110], "total_odds": [-110, -110]}
    if ml:
        extra["ml"] = list(ml)
    return {"sport": "nfl", "season": season, "period": f"{week:03d}",
            "game_id": f"{season}-{week}-{away}@{home}", "home": home, "away": away,
            "home_score": hs, "away_score": as_, "spread": -3.0, "total": 44.0,
            "roof": "outdoors", "surface": "grass", "temp": None, "wind": None,
            "extra": json.dumps(extra), "date": f"{season}-10-{week:02d}"}


def _book():
    """Two pairs of teams. A crushes B every week, so the model's raw
    number for A sits far above a -200 close: the bar's refusals. C edges
    D by a field goal, so the raw sits near that same close: the rows
    the bar keeps. Each pair then plays six quoted games at -200/+170;
    A wins four of six, C five of six — so the two halves land apart
    and a report that pooled them would be caught."""
    rows = []
    for wk in range(1, 5):
        rows.append(_row(2025, wk, "A", "B", 42, 3))
        rows.append(_row(2025, wk, "C", "D", 23, 20))
    for wk in range(5, 11):
        a_won, c_won = wk % 3 != 0, wk != 9
        rows.append(_row(2025, wk, "A", "B", 42 if a_won else 3, 3 if a_won else 42, ml=(-200, 170)))
        rows.append(_row(2025, wk, "C", "D", 23 if c_won else 20, 20 if c_won else 23, ml=(-200, 170)))
    conn = db.connect(":memory:")
    db.upsert_games(conn, rows)
    return conn


def test_the_measurement_splits_the_boards_favourites_by_the_bar():
    r = R.measure_raw_bar(_book(), "nfl", resamples=200)
    assert r.games == 12 and r.eligible == 12, (r.games, r.eligible)
    assert r.refused == 6, r.refused                   # the A rows, every one
    assert r.kept_claimed is not None and abs(r.kept_claimed - r.refused_claimed) < 1e-9, \
        "both halves are priced at the same close"
    assert abs(r.kept_landed - 5 / 6) < 1e-9 and abs(r.refused_landed - 4 / 6) < 1e-9, \
        (r.kept_landed, r.refused_landed)
    # The interval is of refused-minus-kept: a sixth apart here, and the
    # point sits inside its own bootstrap.
    assert r.ci is not None and r.ci[0] <= -1 / 6 <= r.ci[1], r.ci
    assert sum(n for _lo, _hi, n, _c, _l in r.bands) == 6
    lines = R.raw_bar_lines(r)
    assert lines[0].startswith("raw-claim bar on market-ranked NFL moneylines · 12 quoted games")
    assert any("would refuse: 6 (50%)" in ln for ln in lines), lines
    assert any("rows refused: claimed" in ln and "landed  66.7%" in ln for ln in lines), lines
    assert any("rows kept:    claimed" in ln and "landed  83.3%" in ln for ln in lines), lines


def test_the_measurement_says_when_there_is_nothing_to_measure():
    conn = db.connect(":memory:")
    db.upsert_games(conn, [_row(2025, wk, "A", "B", 24, 20) for wk in range(1, 6)])
    r = R.measure_raw_bar(conn, "nfl", resamples=10)
    assert r.games == 0 and "nothing to measure" in r.note, r
    assert R.raw_bar_lines(r)[-1].strip() == r.note
    assert "raw claim" in R.measure_raw_bar(conn, "mlb").note


def test_the_docs_carry_the_measurement_and_the_command():
    docs = open(os.path.join(ROOT, "docs", "LIKELY_GAME_LINES.md"), encoding="utf-8").read()
    checks = open(os.path.join(ROOT, "docs", "DROPLET_CHECKS.md"), encoding="utf-8").read()
    assert "## The raw claim on a market-ranked row (2026-09-08)" in docs
    assert "python3 -m engine.gamerank --sport nfl --raw-bar" in docs
    assert "python3 -m engine.gamerank --sport nfl --raw-bar" in checks
    assert "681" in docs and "207" in docs


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
