"""The Record grades Best Parlays by tier (Ethan's answer to decision 15, 21 November: "yes"; step AAX).

The decision, as put to him: "Track Best Parlays' tiers on the Record, so we can see whether Top parlays
really hit more often than Strong ones." The Best Parlays page ranks each game's tickets in three tiers by
how its checks agree (engine/gameparlays.rank_checks, rank_tier) and leaves a game off once it starts.
Now the tier each ticket wore then is read off the set its report carried at the start (the set the
record counts, parlayledger.mark_at_start) by those same checks and kept on its journal row (`tier`),
the record says how each tier has done (`by_tier`), and the Record page draws it under each kind's card.

    python3 tests/test_the_record_grades_best_parlays_by_tier.py
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP          # noqa: E402
from engine import parlayledger as PL         # noqa: E402
from engine import reportarchive              # noqa: E402

REC = (ROOT / "web" / "js" / "record.js").read_text(encoding="utf-8")


def _conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    PL.ensure_schema(c)
    return c


def _leg(player, market="receptions", p=0.7):
    return {"player": player, "team": "KC", "market": market, "side": "OVER", "line": 1.5, "odds": -150,
            "book": "DraftKings", "p": p}


def _t(*players, market="receptions", p=0.7, **kw):
    return {"legs": [_leg(x, market, p) for x in players], "joint": 0.40, "take_dec": 3.4, "naive_dec": 3.3,
            "independent": 0.41, **kw}


# Every check agrees: Top. One against (no one book has it whole): Strong. Two against: Worth a look.
TOP = _t("T1", "T2", "T3", **{"class": "pop", "one_book": {"book": "DraftKings"}, "playable": True})
STRONG = _t("S1", "S2", "S3", **{"class": "pop", "one_book": {"none": True}, "playable": True})
LOOK = _t("L1", "L2", "L3", **{"class": "long", "one_book": {"none": True}, "playable": True})
GONE = _t("G1", "G2", "G3", **{"class": "pop", "one_book": {"gone": True}})
OLD = _t("O1", "O2", "O3", **{"class": "pop", "one_book": {"book": "DraftKings"}})
TWO = _t("W1", "W2", **{"class": "safe", "one_book": {"book": "FanDuel"}, "playable": True})
PAIR = _t("P1", "P2", market="anytime_td", p=0.45)
LOW_PAIR = _t("Q1", "Q2", market="anytime_td", p=0.30)


def _game(**lists):
    return {"away": "DEN", "home": "KC", "game": "DEN@KC", "date": "2026-11-23", **lists}


def _tiers(c):
    return {r["legs_key"].split("|")[0]: r["tier"] for r in c.execute("SELECT legs_key, tier FROM parlays")}


def test_the_checks_put_each_kind_of_ticket_in_the_tier_the_page_shows():
    assert [GP.rank_tier(GP.rank_checks(t, "threes", "nfl")) for t in (TOP, STRONG, LOOK)] == ["top", "strong", "look"]
    assert GP.rank_tier(GP.rank_checks(PAIR, "scorers", "nfl")) == "top"
    assert GP.rank_tier(GP.rank_checks(LOW_PAIR, "scorers", "nfl")) == "strong", "a scorer under our 40% rule"
    assert PL.TIER_ORDER == tuple(t for t, _w, _x in GP.RANK_TIERS) and set(PL.TIER_KINDS) == set(GP.RANK_KINDS)


def test_the_tier_at_the_start_is_kept_on_each_counted_ticket_and_on_no_other():
    c = _conn()
    assert "tier" in {r[1] for r in c.execute("PRAGMA table_info(parlays)")}
    PL.ensure_schema(c)                                     # a second pass adds nothing and raises nothing
    day = "2026-W12"
    # The morning's build posts OLD; the afternoon's replaces it. GONE has a leg no book lists any more.
    assert PL.log_game_parlays(c, {"games": [_game(threes=[OLD, STRONG], twos=[TWO], scorers=[PAIR])]}, "nfl", day) == 4
    assert PL.log_game_parlays(c, {"games": [_game(threes=[TOP, STRONG, LOOK, GONE], twos=[TWO],
                                                   scorers=[PAIR, LOW_PAIR])]}, "nfl", day) == 4
    kept = _game(threes=[TOP, STRONG, LOOK, GONE], twos=[TWO], scorers=[PAIR, LOW_PAIR], kept="Sun 1:00 PM ET")
    # What the marking returns is unchanged: the tickets marked, not the tiers.
    assert PL.mark_started_games(c, {"games": [kept]}, "nfl", day) == 8
    got = _tiers(c)
    assert got == {"t1": "top", "s1": "strong", "l1": "look", "w1": "top", "p1": "top", "q1": "strong",
                   "g1": None, "o1": None}, got
    # The first reading stands: a later pass with other checks changes nothing.
    later = _game(threes=[dict(TOP, playable=False)], kept="x")
    PL.mark_started_games(c, {"games": [later]}, "nfl", day)
    assert _tiers(c)["t1"] == "top"
    assert PL.kept_tiers(None, "nfl") == {} and PL.kept_tiers({"threes": [{"legs": ["no"]}]}, "nfl") == {}


def test_a_set_marked_before_the_journal_kept_tiers_gains_them_from_its_archive():
    c = _conn()
    day = "2026-W12"
    PL.log_game_parlays(c, {"games": [_game(threes=[TOP, LOOK])]}, "nfl", day)
    # Marked the day before this step: counted, no tier.
    c.execute("UPDATE parlays SET at_start=1")
    c.commit()
    where = Path(tempfile.mkdtemp())
    path = reportarchive.path_for(where, "nfl", "2026-11-23", "DEN", "KC")
    reportarchive.write(path, {"sport": "nfl", "date": "2026-11-23", "label": day, "game": "DEN@KC",
                               "away": "DEN", "home": "KC", "parlays": _game(threes=[TOP, LOOK])})
    assert PL.mark_from_archive(c, where) == 0, "no ticket newly marked"
    c2 = sqlite3.connect(":memory:")                        # the tiers were committed, not left in a transaction
    c.backup(c2)
    assert {r[0] for r in c2.execute("SELECT tier FROM parlays")} == {"top", "look"}


def test_the_record_says_how_each_tier_has_done():
    c = _conn()
    day = "2026-W12"
    PL.log_game_parlays(c, {"games": [_game(threes=[TOP, STRONG, LOOK], scorers=[PAIR, LOW_PAIR])]}, "nfl", day)
    PL.mark_started_games(c, {"games": [_game(threes=[TOP, STRONG, LOOK], scorers=[PAIR, LOW_PAIR], kept="x")]},
                          "nfl", day)
    grade = {"t1": ("won", 2.4), "s1": ("lost", -1.0), "l1": ("open", None), "p1": ("won", 3.0), "q1": ("lost", -1.0)}
    for r in c.execute("SELECT id, legs_key FROM parlays").fetchall():
        st, pnl = grade[r["legs_key"].split("|")[0]]
        c.execute("UPDATE parlays SET status=?, pnl_units=? WHERE id=?", (st, pnl, r["id"]))
    c.commit()
    rec = PL.game_parlay_record(c)["nfl"]
    assert rec["three"]["by_tier"] == {
        "top": {"graded": 1, "wins": 1, "open": 0, "chance": 0.4, "net_units": 2.4},
        "strong": {"graded": 1, "wins": 0, "open": 0, "chance": 0.4, "net_units": -1.0},
        "look": {"graded": 0, "wins": 0, "open": 1, "chance": None, "net_units": 0.0}}, rec["three"]["by_tier"]
    assert list(rec["three"]["by_tier"]) == ["top", "strong", "look"], "the page's order"
    assert rec["scorers"]["by_tier"]["top"]["wins"] == 1 and rec["scorers"]["by_tier"]["strong"]["graded"] == 1
    # A league whose tickets wear no tier says nothing about tiers.
    c2 = _conn()
    PL.log_game_parlays(c2, {"games": [_game(threes=[TOP])]}, "nba", "2026-11-23")
    c2.execute("UPDATE parlays SET at_start=1, status='won', pnl_units=2.0")
    c2.commit()
    assert "by_tier" not in PL.game_parlay_record(c2)["nba"]["three"]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    i = REC.index("function gpBlockHTML(")
    block = REC[i:REC.index("\n}\n", i) + 3]
    consts = "\n".join(REC[REC.index(f"const {n} = "):REC.index(";\n", REC.index(f"const {n} = ")) + 2]
                       for n in ("GP_CLASSES", "GP_TIERS", "GP_TIERS_SINCE", "GP_FILL_WORDS"))
    prog = f"""
      const escapeHtml = (s) => String(s);
      const recTile = () => "", tlUnits = (u) => String(u), toneOf = () => "", icon = () => "";
      const marketWord = (m) => m, gpKindWord = (k) => k, american = (x) => x, tlAmerican = (x) => x;
      const gpDay = (d) => d === "2026-11-21" ? "Sat, Nov 21" : d;
      const gpTicketLegs = () => ({{ text: "", tone: "" }}), gpLegsHTML = () => "";
      const PARLAY_RATE_FLOOR = 10;
      {consts}
      {block}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    import json
    return json.loads(out.stdout.strip())


def test_the_record_page_draws_each_tier_under_its_card():
    got = _node("""
      const bt = { top: { graded: 8, wins: 3, open: 2, chance: 0.41 }, strong: { graded: 9, wins: 2, open: 0, chance: 0.33 },
                   look: { graded: 0, wins: 0, open: 1, chance: null } };
      const html = gpBlockHTML({ graded: 17, wins: 5, legs: {}, by_tier: bt }, "three", "nfl");
      const none = gpBlockHTML({ graded: 17, wins: 5, legs: {} }, "three", "nfl");
      return { html, none };""")
    if got is None:
        print("  SKIP node not installed"); return
    line = re.search(r"<p class=\"rec-gp-close\" data-rec-tiers>(.*?)</p>", got["html"], re.S)
    assert line, got["html"]
    words = " ".join(line.group(1).split())
    assert words == ("By Best Parlays tier: Top parlays 3 of 8 hit (we gave 41%) · Strong 2 of 9 hit (we gave 33%)"
                     " · Worth a look none graded yet · 3 waiting on their games. Each ticket’s tier is the one it had"
                     " when its game started; games before the page went up on Sat, Nov 21 are tiered by the same"
                     " checks."), words
    assert "data-rec-tiers" not in got["none"], "no tiers, no line"
    assert "${byClass}${byTier}" in REC


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
