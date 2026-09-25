"""A player the matchup scan says could shine gets his Most Likely pick.

Ethan, 2026-09-25, with the dashboard's "Who could shine" open: "how do
we show dalton kincaid, garret willson, and Adonia Mitchell all as
breakout candidates but then don't have any most likely bets for them?
It doesn't make any sense."

Two causes, both in engine/likely: a prop's row was the likeliest number
on EITHER side of its ladder, so a breakout could come out as an under;
and the seats are eight a market across a whole NFL week, so his over,
clearing every bar, lost its seat. The scan now runs before the board
(`pipeline.run_slate`'s `before_likely`, `cfb_build`) and its reads lean
the board: the read picks the side among numbers that already clear and
keeps the agreeing pick a seat (READ_SEATS). The number never moves —
engine/scanfit measured no lift in the scan's signals. A read with no
pick says why on its card.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gamescan as G                                 # noqa: E402
from engine import likely as K                                   # noqa: E402

FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}


def _ln(book, line, over):
    return {"book": book, "line": line, "over_odds": over, "under_odds": 0}


def _row(player, team="GB", opponent="ATL", projection=62.0, **kw):
    """A priced rushing prop with a ladder, the shape tests/
    test_a_posted_pick_is_never_lost.py builds."""
    got = {"player": player, "team": team, "opponent": opponent, "market": "rush_yds",
           "market_label": "Rush Yards", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
           "has_market": True, "fair_prob": 0.50, "projection": projection, "ev_per_unit": 0.01,
           "reasons": ["because"], "recent_values": [55, 71, 48, 66],
           "game_date": "2026-09-24", "kickoff": "20:15", "hit_prob": 0.56, "raw_prob": 0.58,
           "alt_lines": [_ln("DraftKings", 40.5, -240), _ln("FanDuel", 40.5, -230),
                         _ln("DraftKings", 50.5, -160), _ln("FanDuel", 50.5, -155)],
           "alt_sharp_lines": []}
    got.update(kw)
    return got

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
PIPE = open(os.path.join(ROOT, "engine", "pipeline.py"), encoding="utf-8").read()
CFB = open(os.path.join(ROOT, "cfb_build.py"), encoding="utf-8").read()

NOW = "2026-09-24T15:00:00Z"
OVER = {"side": "over", "read": "breakout", "label": "Breakout candidate"}


def _build(rows, leans=None, **kw):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    rep: dict = {}
    try:
        board = K.build(rows, sport="nfl", fits=FITS, now=NOW, turnover={},
                        leans=leans, lean_report=rep, **kw)
    finally:
        K.rankable = real
    return board, rep


def _both(name="Both"):
    """A back whose ladder has an under likelier than his over."""
    return _row(name, projection=62.0, alt_lines=[
        _ln("DraftKings", 40.5, -240), _ln("FanDuel", 40.5, -230),
        {"book": "DraftKings", "line": 95.5, "over_odds": 400, "under_odds": -250}])


# ── the reads become leans ────────────────────────────────────────────────


def test_shine_leans_over_struggle_under_neutral_nowhere():
    reads = {"A@B": {"players": [
        {"player": "K", "team": "BUF", "read": "breakout", "label": "Breakout candidate",
         "lean": ["receptions", "rec_yds", "anytime_td"]},
        {"player": "H", "team": "LAC", "read": "tough", "label": "Tough matchup", "lean": ["rush_yds"]},
        {"player": "N", "team": "LAC", "read": "neutral", "label": "Neutral", "lean": ["rec_yds"]}]}}
    got = G.leans_from_reads(reads)
    assert got[("K", "BUF", "rec_yds")]["side"] == "over"
    assert got[("H", "LAC", "rush_yds")]["side"] == "under"
    assert ("K", "BUF", "anytime_td") not in got, "a scorer row is always yes"
    assert not any(k[0] == "N" for k in got)


# ── the board ─────────────────────────────────────────────────────────────


def test_the_read_picks_the_side_among_numbers_that_clear():
    plain, _ = _build([_both()])
    assert (plain[0]["side"], plain[0]["line"]) == ("under", 95.5), "the likeliest number, either side"
    leaned, rep = _build([_both()], {("Both", "GB", "rush_yds"): OVER})
    (r,) = leaned
    assert (r["side"], r["line"]) == ("over", 40.5), r
    assert r["model_prob"] >= K.MIN_PROB and int(r["odds"]) >= K.HEAVIEST_PRICE, "every bar, as before"
    assert r["scan_read"] == "breakout" and r["scan_label"] == "Breakout candidate"
    assert rep[("Both", "GB")]["status"] == "pick"


def test_the_number_never_moves():
    plain, _ = _build([_row("Solo", projection=60.0)])
    leaned, _ = _build([_row("Solo", projection=60.0)], {("Solo", "GB", "rush_yds"): OVER})
    assert [(r["side"], r["line"], r["model_prob"]) for r in plain] == \
        [(r["side"], r["line"], r["model_prob"]) for r in leaned]


def test_his_pick_keeps_a_seat_past_the_caps():
    rows = [_row(f"P{i}", projection=60.0 + i * 0.5) for i in range(8)] + [_row("Leaned", projection=56.0)]
    plain, _ = _build(rows, limit=8)
    assert "Leaned" not in {r["player"] for r in plain}, "the cap cut him — the bug"
    leaned, _ = _build(rows, {("Leaned", "GB", "rush_yds"): OVER}, limit=8)
    assert "Leaned" in {r["player"] for r in leaned}
    assert len(leaned) == len(plain) + K.READ_SEATS


def test_a_read_the_board_cannot_agree_with_says_so():
    under_only = _row("Under", projection=62.0, alt_lines=[
        {"book": "DraftKings", "line": 95.5, "over_odds": 400, "under_odds": -250}])
    _, rep = _build([under_only], {("Under", "GB", "rush_yds"): OVER})
    assert rep[("Under", "GB")]["status"] == "other_side", rep
    _, rep = _build([], {("Nobody", "GB", "rush_yds"): OVER})
    assert rep[("Nobody", "GB")] == {"status": "none", "priced": False, "refused": "", "best": None}


def test_a_turned_down_pick_says_the_boards_reason():
    """Jahmyr Gibbs, 2026-09-25: "No Most Likely pick" beside a 72% over.
    A ladder the board never reads (no main-line price) is not offered as
    his best number, and the card names the reason."""
    no_main = _row("Gibbs", team="DET", opponent="NYJ", has_market=False)
    board, rep = _build([no_main], {("Gibbs", "DET", "rush_yds"): OVER})
    assert not board
    got = rep[("Gibbs", "DET")]
    assert got["status"] == "none" and got["best"] is None, got
    assert got["refused"], got


def test_the_likeliest_number_includes_his_main_line():
    """Ladd McConkey, 2026-09-25: the card called Over 109.5 at +700 (4%)
    "his likeliest over" — a real alternate rung, but only the rungs were
    read, never his main line near 45. The main line is a candidate now."""
    low = _row("Low", projection=40.0, line=45.5, side="under", odds=-110,
               all_lines=[{"book": "DraftKings", "line": 45.5, "over_odds": -115, "under_odds": -105}],
               alt_lines=[_ln("DraftKings", 109.5, 700)])
    board, rep = _build([low], {("Low", "GB", "rush_yds"): OVER})
    assert not [r for r in board if r["side"] == "over"], "no over clears the floor"
    best = rep[("Low", "GB")]["best"]
    assert best is not None and best["line"] == 45.5, best
    assert (best["side"], best["odds"], best["book"]) == ("over", -115, "DraftKings"), best
    assert best["model_prob"] < K.MIN_PROB


def test_a_longshot_is_never_called_his_likeliest():
    """Droplet self-check, 2026-09-25: "Quinshon Judkins over 109.5 +900
    at 1%", "David Montgomery over 99.5 +980 at 0%". With only a far rung
    left on his side, the card says none of his numbers is one we would
    stand behind — never that a 1% number is his likeliest."""
    far = _row("Far", projection=40.0, line=45.5, side="under", odds=-110,
               all_lines=[], alt_lines=[_ln("DraftKings", 109.5, 900)])
    _, rep = _build([far], {("Far", "GB", "rush_yds"): OVER})
    got = rep[("Far", "GB")]
    assert got["status"] == "none" and got["priced"] and got["best"] is None, got
    from engine import boardtruth
    assert K.LEAN_BEST_MIN_PROB == boardtruth.LONGSHOT_PROB


def test_the_stamp_lands_on_the_read():
    reads = {"A@B": {"players": [{"player": "Both", "team": "GB", "read": "good"},
                                 {"player": "Nobody", "team": "GB", "read": "good"}]}}
    n = G.stamp_picks(reads, {("Both", "GB"): {"status": "pick", "pick": {"line": 40.5}},
                              ("Nobody", "GB"): {"status": "none", "priced": False, "best": None}})
    both, nobody = reads["A@B"]["players"]
    assert n == 2 and both["pick"] == {"line": 40.5}
    assert nobody["no_pick"] == {"best": None, "priced": False, "refused": ""}


# ── the builds run the scan first ─────────────────────────────────────────


def test_the_scan_runs_before_the_board_in_both_builds():
    assert PIPE.index("_leans = before_likely(_partial)") < PIPE.index("_likely = _likely_board(")
    assert "leans=_leans," in PIPE and "stamp_picks(_partial[\"scan_reads\"], _lean_report, board=_likely)" in PIPE
    assert CFB.index("_cfb_leans = _scan.leans_from_reads(") < CFB.index("out[\"most_likely\"] = _likely(")
    assert "leans=_cfb_leans," in CFB


# ── the page ──────────────────────────────────────────────────────────────


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_every_read_says_what_the_board_did_with_it():
    assert "${scanPickHTML(x)}" in _fn("scanReadHTML")
    assert '${scanPickHTML(x, "sct-pick")}' in _fn("scanTopRowHTML")
    assert "const own = market ? null : (scanPickRow(x)" in _fn("scanDoor")
    assert "if (r.scan_label) {" in _fn("likelyTagsHTML"), "the pick's card names the read"
    if not shutil.which("node"):
        return
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);"
               "const oddsTxt=(o)=>(o>0?'+':'')+o;"
               "const wholePct=(x)=>Math.round(Number(x)*100)+'%';\n" + _fn("scanPickHTML")
               + "\nconst xs=JSON.parse(process.argv[2]);"
               "process.stdout.write(JSON.stringify(xs.map((x)=>scanPickHTML(x).replace(/<[^>]+>/g,''))));")
    path = os.path.join(tempfile.mkdtemp(), "p.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(harness)
    pick = {"player": "K", "market": "receptions", "market_label": "Receptions", "side": "over",
            "line": 3.5, "odds": -180, "model_prob": 0.68}
    xs = [{"read": "breakout", "pick": pick},
          {"read": "good", "pick_other_side": dict(pick, side="under", line=6.5)},
          {"read": "good", "no_pick": {"priced": True, "best": dict(pick, line=5.5, model_prob=0.51)}},
          {"read": "tough", "no_pick": {"priced": False, "best": None}},
          {"read": "neutral"}]
    out = subprocess.run(["node", path, json.dumps(xs)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-400:]
    got = [" ".join(t.split()) for t in json.loads(out.stdout)]
    assert got[0] == "Most Likely pick: Over 3.5 Receptions · -180 · 68%", got[0]
    assert "goes the other way: Under 6.5" in got[1] and "disagrees with this read" in got[1]
    assert "his likeliest over at −250 or better is Over 5.5 Receptions" in got[2]
    assert "under the 55% the board needs" in got[2]
    assert got[3] == "No Most Likely pick — the books have not priced his props yet.", got[3]
    assert got[4] == ""


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
