"""A baseball hitter on a projected lineup is shown, and not recorded.

The site audit, 2026-09-24. The MLB pipeline stamps `lineup_confirmed` on
every prop row, and its own comment says the board may SHOW a projected
hitter "with the caveat" while the journal waits for the card: on rest
days a third of projected names never start (31 of 58 long shots,
2026-07-26), and baseball has no absent-player grade
(`ledger.ABSENT_RULE_SPORTS`), so a hitter who sat stays open for good.

The edge book is held upstream (an unconfirmed hitter is "On deck", not
recommended) and the long-shot journal refuses him. The Most Likely book
reads every prop row, recommended or not — staked with real money on MLB
since 2026-09-19 — and its row dropped the flag, so nothing held it; the
Pick of the Day, chosen from those rows and locked by its first journal,
had no rule either. Now the flag rides the row, both journals wait for
the card, and the row and the pick page say "Lineup not posted".
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger                                        # noqa: E402
from engine import likely as K                                   # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _row(player, confirmed):
    return {"kind": "prop", "player": player, "market": "total_bases", "side": "UNDER", "line": 1.5,
            "odds": -180, "book": "FanDuel", "model_prob": 0.68, "implied_prob": 0.62,
            "projection": 0.9, "game_date": "2026-09-24", "lineup_confirmed": confirmed}


def test_the_row_carries_the_flag_the_pipeline_stamped():
    prop = {"player": "A Hitter", "team": "SD", "market": "total_bases", "side": "UNDER", "line": 1.5,
            "odds": -180, "book": "FanDuel", "has_market": True, "hit_prob": 0.68, "fair_prob": 0.62,
            "projection": 0.9, "lineup_confirmed": False}
    row = K._row_from(prop, "total_bases", "mlb", lambda m: True, 0.68, shown=0.68)
    assert row["lineup_confirmed"] is False
    assert K._row_from(dict(prop, lineup_confirmed=None), "total_bases", "mlb",
                       lambda m: True, 0.68, shown=0.68)["lineup_confirmed"] is None


def test_the_likely_book_waits_for_the_card():
    conn = ledger.connect(":memory:")
    n = ledger.log_most_likely(conn, {"sport": "mlb", "date": "2026-09-24", "most_likely": [
        _row("Projected", False), _row("Confirmed", True), _row("No Card", None)]})
    got = {r[0] for r in conn.execute("SELECT player FROM bets")}
    assert n == 2 and got == {"Confirmed", "No Card"}, got
    n = ledger.log_most_likely(conn, {"sport": "mlb", "date": "2026-09-24", "most_likely": [
        _row("Projected", True)]})
    assert n == 1, "once the card posts he journals on the next build"


def test_the_pick_of_the_day_does_not_lock_a_projected_hitter():
    conn = ledger.connect(":memory:")
    pick = dict(_row("Projected", False), sport="mlb")
    assert ledger.log_pick_of_the_day(conn, {"sport": "mlb", "date": "2026-09-24", "pick": pick}) == 0
    assert conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0] == 0, "not journaled, so not locked"
    assert ledger.log_pick_of_the_day(conn, {"sport": "mlb", "date": "2026-09-24",
                                             "pick": dict(pick, lineup_confirmed=True)}) == 1


def test_the_row_and_the_pick_page_say_so():
    node = shutil.which("node")
    fn = APP[APP.index("function likelyTagsHTML("):]
    fn = fn[:fn.index("\n}\n") + 2]
    held = APP[APP.index("function likelyHeld("):]
    held = held[:held.index("\nfunction likelyRow(")]
    assert 'tags.push(["Lineup not posted", "down",' in fn
    why = APP[APP.index("function whyLikelyHTML("):]
    assert "if (lk.lineup_confirmed === false) {" in why[:why.index("\n}\n")]
    if not node:
        print("  SKIP node not installed")
        return
    esc = APP[APP.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    prog = (esc + "const escapeAttr = escapeHtml;\nconst state = {data: {}};\n"
            + "const tzOpts = (o) => o;\nconst tzTime = (d) => String(d);\nconst wholePct = (x) => x;\n"
            + "const LIKELY_NEW_MIN = 60;\n" + held + fn
            + "\nconsole.log(JSON.stringify([{lineup_confirmed: false}, {lineup_confirmed: true}, {}]"
            + ".map(likelyTagsHTML)));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert "Lineup not posted" in got[0] and got[1] == "" and got[2] == ""


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
