"""Team form: tracking, the season audit, and the form sampler.

The discipline being tested is the ORDER: track from our own ingested
results, measure whether hot form predicts anything, and journal the hot
side at REAL prices in a quarantined bucket — never adjust the model on
vibes. Also: form must never leak a day's own result into that day's form.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine import db
from engine.mlb.teamform import (team_form, form_score, hot_cold, audit,
                                 FORM_GAP_BAR)


def _seed(conn, rows):
    """rows: (date, home, away, hs, as_)"""
    conn.executemany(
        "INSERT INTO games (sport, season, period, game_id, home, away, "
        "home_score, away_score) VALUES ('mlb', 2026, ?, ?, ?, ?, ?, ?)",
        [(d, f"{d}_{a}@{h}", h, a, hs, as_) for d, h, a, hs, as_ in rows])
    conn.commit()


def _streaky_db():
    """NYA win everything by a lot; COL lose everything by a lot; two
    neutral teams trade close games."""
    conn = db.connect(":memory:")
    rows = []
    for i in range(1, 9):
        d = f"2026-07-{20 + i:02d}"
        rows.append((d, "NYA", "COL", 9, 2))
        rows.append((d, "BOS", "TBA", 4 + (i % 2), 4 + ((i + 1) % 2)))
    _seed(conn, rows)
    return conn


def test_form_counts_window_and_streak():
    conn = _streaky_db()
    f = team_form(conn, "2026-07-29", window_days=7)
    assert f["NYA"]["w"] == 7 and f["NYA"]["l"] == 0
    assert f["NYA"]["streak"] >= 7
    assert f["COL"]["streak"] <= -7
    assert f["NYA"]["diff_pg"] == 7.0
    # delta vs the team's own season average: a team that has ALWAYS won
    # by 7 is not "hot" relative to itself.
    assert abs(f["NYA"]["delta_diff"]) < 0.01


def test_form_never_includes_the_day_itself():
    conn = _streaky_db()
    _seed(conn, [("2026-07-29", "NYA", "COL", 0, 20)])   # tonight's blowout
    f = team_form(conn, "2026-07-29", window_days=7)
    assert f["NYA"]["l"] == 0                             # not leaked


def test_hot_cold_orders_by_composite_score():
    conn = db.connect(":memory:")
    rows = []
    for i in range(1, 8):
        d = f"2026-07-{20 + i:02d}"
        # SEA cold lately (season .500-ish overall), TEX hot lately.
        rows.append((d, "TEX", "SEA", 8, 1))
    for i in range(1, 8):
        d = f"2026-07-{10 + i:02d}"                       # outside the window
        rows.append((d, "SEA", "TEX", 8, 1))
    _seed(conn, rows)
    f = team_form(conn, "2026-07-28", window_days=7)
    hot, cold = hot_cold(f)
    assert hot and hot[0]["team"] == "TEX"
    assert cold and cold[0]["team"] == "SEA"
    assert form_score(f["TEX"]) > 0 > form_score(f["SEA"])


def test_audit_reports_honestly():
    # A world where hot teams keep winning: the audit must see it...
    conn = _streaky_db()
    _seed(conn, [(f"2026-07-{29 + 0:02d}", "NYA", "COL", 6, 1)])
    rep = audit(conn, min_games=3)
    # NYA (hot) wins every counted matchup; one early BOS/TBA coin-flip
    # also clears the gap bar and loses — the audit counts it honestly.
    assert rep["n"] >= 5 and rep["hot_win_rate"] >= 0.8
    assert "sampler" in rep["verdict"] or "priced" in rep["verdict"]
    # ...and an empty DB must say so instead of inventing a number.
    empty = audit(db.connect(":memory:"))
    assert empty["n"] == 0 and "accrues" in empty["verdict"]


def test_form_sampler_journals_hot_side_at_real_prices():
    from engine import ledger
    lpath = os.path.join(tempfile.mkdtemp(), "led.db")
    lconn = ledger.connect(lpath)
    hist = _streaky_db()
    form = team_form(hist, "2026-07-29", window_days=7)
    result = {"sport": "mlb", "date": "2026-07-29", "games": [
        {"home": "NYA", "away": "COL", "home_ml": -160, "away_ml": 140},
        {"home": "BOS", "away": "TBA", "home_ml": -110, "away_ml": -110},  # no gap
        {"home": "NYA", "away": "COL", "home_ml": 0, "away_ml": 0,
         "date": "2026-07-30"},                                            # no price
    ]}
    n = ledger.log_form_picks(lconn, result, form)
    assert n == 1
    b = lconn.execute("SELECT * FROM bets WHERE category='form'").fetchone()
    assert b["player"] == "NYA" and b["market"] == "moneyline"
    assert b["odds"] == -160 and b["stake_units"] == 0.1
    assert b["edge"] >= FORM_GAP_BAR

    # Settles through the existing moneyline path from the games table.
    _seed(hist, [("2026-07-29", "NYA", "COL", 5, 3)])
    assert ledger.settle_from_history(lconn, hist, sport="mlb") == 1
    rep = ledger.form_report(lconn)
    assert rep["wins"] == 1 and rep["losses"] == 0
    assert rep["recent"] and rep["recent"][0]["player"] == "NYA"
    assert rep["avg_taken_implied"] is not None
    lconn.close()


def test_the_team_form_heading_uses_a_name_that_exists():
    """The block was silently missing from every MLB view for 13 days.

    The emoji sweep (#50, 2026-08-02) replaced the heading's emoji with
    `${mark}` and left the helper's parameter called `icon`. So the
    template referenced a name that did not exist in that scope, and the
    whole of `renderTeamForm` threw "mark is not defined".

    THREE THINGS HID IT, and they are the reason this test is worth its
    lines:

      * it throws inside an `async` function, so it surfaced as an
        unhandled rejection, not a visible error — the page finished
        rendering and just lost this section;
      * `renderTeamForm` returns early when `team_form` is absent, so any
        board without form data never reaches the bug. The dev container
        has no team form, which is exactly why a 42-view headless sweep
        there came back clean while Ethan's machine crashed on 22 of 28;
      * `let mark` DOES exist further down app.js, inside an unrelated
        function, so grepping the file for the name finds it and proves
        nothing.

    Checked by parsing the helper rather than grepping: every `${name}`
    in its template must be one of its own parameters.
    """
    import re
    app = open(os.path.join(os.path.dirname(__file__), "..",
                            "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("async function renderTeamForm(")
    body = app[i:app.index("\n}\n", i)]
    m = re.search(r"const col = \(([^)]*)\) =>\s*`(.*?)`;", body, re.S)
    assert m, "the team-form column helper is gone or reshaped"
    params = {p.strip() for p in m.group(1).split(",") if p.strip()}
    refs = set(re.findall(r"\$\{\s*([A-Za-z_$][\w$]*)\s*\}", m.group(2)))
    missing = refs - params
    assert not missing, (
        f"the heading references {sorted(missing)}, which is not a "
        f"parameter of col{sorted(params)} — this is the 'mark is not "
        f"defined' crash again")



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
