"""One game script, said one way, on every page.

Ethan, 2026-09-02: "conflicting data with our most likely page and the
fantasy game script page … lions vs saint, ur showing it to be a heavy RB
running game for the lions but then recommending Goffs over passing
yards. Also we should b showing the game script under the player props
too."

Detroit −7 at 49.5 is the worked case throughout: implied 28.25 / 21.25,
the Fantasy page's "Favorite runs, dog throws", +7% TD equity for a Lions
back — and, since 2026-10-12, NO tilt on Goff's passing volume or his
receivers' targets: the spread tilt was measured again on the board's
current base and retired (engine/matchup.SCRIPT_COEF_PASS's note), and the
card says so.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gamescript as G
from engine import fantasy as F
from engine import likely as L


class _Game:
    def __init__(self, home, away, spread, total):
        self.home, self.away, self.spread, self.total = home, away, spread, total


def test_the_lions_saints_read_by_hand():
    d = G.describe(-7.0, 49.5, "DET", "NO")
    assert d["home_implied"] == 28.2 and d["away_implied"] == 21.2   # 24.75 ± 3.5, rounded
    assert d["favorite"] == "DET"
    assert d["archetype"] == "Favorite runs, dog throws"
    assert d["confidence"].startswith("high")


def test_the_same_table_the_fantasy_page_uses():
    assert F.SCRIPT_ARCHETYPES is G.ARCHETYPES
    for (t, s), (name, _) in G.ARCHETYPES.items():
        total = 50.0 if t == "high" else 40.0
        spread = -10.0 if s == "big" else -1.5
        assert G.describe(spread, total)["archetype"] == name


def test_each_sideline_reads_its_own_role():
    det = G.for_team(-7.0, 49.5, "DET", "NO", "DET")
    no = G.for_team(-7.0, 49.5, "DET", "NO", "NO")
    assert det["role"] == "favorite" and det["team_spread"] == -7.0
    assert no["role"] == "underdog" and no["team_spread"] == 7.0
    assert det["team_implied"] == 28.2 and no["team_implied"] == 21.2
    assert "run" in det["lean"] and "throw" in no["lean"]
    assert G.for_team(0.5, 45.0, "A", "B", "A")["role"] == "pick'em"


def test_the_card_says_what_the_projection_actually_did():
    """The tilt on the card is the projection's own: since 2026-10-12 the
    spread moves no passing volume (measured and retired), so Goff's card
    says no tilt is applied and why, on both sidelines; the rush market
    still says plainly that none is applied; the touchdown model's own
    script slopes are untouched."""
    g = _Game("DET", "NO", -7.0, 49.5)
    goff = G.for_prop(g, "DET", "pass_yds", "QB")
    assert goff["tilt"] == 1.0
    assert "an underdog quarterback does not throw for more" in goff["applied"]
    assert goff["archetype"] == "Favorite runs, dog throws"
    assert "Favorite runs, dog throws" in goff["summary"] and "DET favorite by 7" in goff["summary"]
    carr = G.for_prop(g, "NO", "pass_yds", "QB")
    assert carr["tilt"] == 1.0 and "measured" in carr["applied"]
    for m in ("pass_att", "pass_cmp"):
        assert G.for_prop(g, "NO", m, "QB")["tilt"] == 1.0
    olave = G.for_prop(g, "NO", "receptions", "WR")
    assert olave["tilt"] == 1.0 and "adds nothing to his targets" in olave["applied"]
    gibbs = G.for_prop(g, "DET", "rush_yds", "RB")
    assert gibbs["tilt"] == 1.0 and "no rush tilt is applied" in gibbs["applied"]
    td = G.for_prop(g, "DET", "anytime_td", "RB")
    assert abs(td["tilt"] - 1.07) < 1e-9 and "+7% TD equity" in td["applied"]
    wr = G.for_prop(g, "DET", "anytime_td", "WR")
    assert abs(wr["tilt"] - 0.972) < 1e-9


def test_the_tilt_matches_the_matchup_module_constant():
    """The card and the projection read one set (SCRIPT_MARKETS), so they
    cannot drift: put a market back in it and the card follows the
    projection's own formula; take it out and both say 1.0."""
    from engine import matchup as M
    for m in ("pass_yds", "rec_yds", "receptions"):
        assert m not in M.SCRIPT_MARKETS
        assert G.projection_tilt(-7.0, m)[0] == 1.0
    saved = M.SCRIPT_MARKETS
    try:
        M.SCRIPT_MARKETS = frozenset({"receptions"})
        for spread in (-14.0, -7.0, -3.0, 0.0, 3.0, 10.0):
            mult, _ = G.projection_tilt(spread, "receptions")
            want = max(M.SCRIPT_CLAMP[0], min(M.SCRIPT_CLAMP[1], 1.0 + M.SCRIPT_COEF_PASS * spread))
            assert abs(mult - want) < 1e-9
    finally:
        M.SCRIPT_MARKETS = saved


def test_no_line_means_no_script_not_a_guess():
    assert G.describe(None, 44.0) is None
    assert G.describe(-3.0, 0.0) is None
    assert G.for_prop(_Game("A", "B", -3.0, 0.0), "A", "pass_yds") is None
    assert G.for_prop(None, "A", "pass_yds") is None


def test_every_football_prop_row_carries_the_script():
    from engine.pipeline import run_slate
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = run_slate(os.path.join(here, "data", "sample_slate.json"))
    rows = out["recommendations"]
    assert rows
    with_script = [r for r in rows if r.get("game_script")]
    assert len(with_script) == len(rows), "a prop row has no game_script"
    r = with_script[0]
    for key in ("archetype", "read", "line", "team", "role", "team_implied",
                "opp_implied", "lean", "tilt", "applied", "summary", "confidence"):
        assert key in r["game_script"], key
    # the archetype on the row is the archetype the Fantasy page would name
    g = next(x for x in out["games"] if x["home"] in (r["team"], r["opponent"]))
    assert r["game_script"]["archetype"] == G.describe(g["spread"], g["total"])["archetype"]


def test_the_most_likely_rows_carry_the_same_script():
    row = {"player": "P", "team": "DET", "opponent": "NO", "market": "receptions",
           "market_label": "receptions", "side": "over", "line": 5.5,
           "book": "DK", "odds": -110, "hit_prob": 0.62, "fair_prob": 0.52,
           "projection": 6.1, "ev_per_unit": 0.03, "has_market": True,
           "reasons": ["because"], "recent_values": [5, 7, 6],
           "date": "2026-09-13", "model_prob": 0.62,
           "game_script": {"archetype": "Favorite runs, dog throws"}}
    got = L.from_prop(row, lambda m: True)
    assert got["game_script"]["archetype"] == "Favorite runs, dog throws"
    assert L.from_watch(row)["game_script"]["archetype"] == "Favorite runs, dog throws"


def test_the_page_renders_it_in_three_places():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = open(os.path.join(here, "web", "js", "app.js"), encoding="utf-8").read()
    assert "function scriptChip(r)" in js and "function scriptCardHTML(r)" in js
    assert "${scriptChip(r)}" in js                 # the board card
    assert "${scriptCardHTML(r)}" in js             # the prop page
    assert "r.game_script.lean" in js               # the Most Likely card


def test_a_low_total_is_never_called_a_shootout():
    """Found 2026-10-12 grading a parlay: WAS by 3.5 at 41.5 read "favored in
    a shootout — everyone eats", and gameplan.script_sign scores "everyone
    eats" as every over backed. A low, close game says so and backs no side."""
    from engine.gameplan import script_sign
    low = G.for_team(-3.5, 41.5, "WAS", "NYG", "WAS")
    assert low["archetype"] == "Nobody's good"
    assert "shootout" not in low["lean"] and "eats" not in low["lean"], low["lean"]
    assert low["lean"] == "favored in a low-scoring, close game"
    assert all(script_sign(low["lean"], m) == 0 for m in ("rush_yds", "pass_yds", "receptions"))
    high = G.for_team(-3.5, 52.5, "WAS", "NYG", "WAS")
    assert high["lean"] == "favored in a shootout — everyone eats", "a high total still is one"
    assert script_sign(high["lean"], "rush_yds") == 1
    dog = G.for_team(-3.5, 41.5, "WAS", "NYG", "NYG")
    assert dog["lean"] != low["lean"], "each sideline keeps its own lean"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
