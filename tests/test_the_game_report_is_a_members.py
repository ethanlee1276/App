"""The game report is a member's, all of it (20 November 2026).

Ethan, 2026-11-20: "Also we need to add that the free accounts DO NOT get the parlays and picks in the game
report. Obv they can get everything else in the game report just not the picks. Ok I take that back I don't want
the game reports to be free. I take back what I said." A free version with the picks taken out was considered and
turned down. What these hold, door by door:

  * the public copy of a board carries none of a game report: not its words, its reads, its call, the answers
    its folded titles carry, its picks or its parlays (engine/gate PAID_KEYS), and not the drive simulation the
    report quotes, which rode every public NFL game row until now (ROW_PAID_KEYS_BY_FILE);
  * the game's facts stay free: the line, the venue, the weather, the scan's numbers;
  * every endpoint that reads a report answers a member only: Ask, a finished game's report, the live tickets
    (a count for everyone else);
  * the page: a free account's game page has the report taken out and one lock card in its place, a live game's
    picks rail locks before the report's tickets, and the sign-up, the plans and the welcome card say the
    reports are for members.

    python3 tests/test_the_game_report_is_a_members.py
"""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gate  # noqa: E402

RESEARCH = __import__("test_the_game_report_reads_like_the_research")   # the report fixture (a sibling test)
REPORT_KEYS = ("game_reports", "game_parlays", "report_bets", "kept_picks", "game_plans", "scan_reads",
               "pick_results", "fight_reports")


def _full_board():
    """The NFL fixture board with its report written, and every other view of the report beside it."""
    from engine import gamereport as R
    b = RESEARCH._board()
    R.attach(b, allowed=RESEARCH.ALLOWED)
    leg = {"player": "Jahmyr Gibbs", "team": "DET", "market": "rush_yds", "side": "OVER", "line": 69.5,
           "odds": -150, "book": "DraftKings", "p": 0.66}
    b["game_parlays"] = {"games": [{"away": "GB", "home": "DET", "threes": [{"legs": [leg] * 3, "joint": 0.31}]}]}
    b["report_bets"] = [dict(leg, sources=["card"])]
    b["kept_picks"] = {"GB@DET": {"likely": [leg]}}
    b["pick_results"] = {"GB@DET": [{"player": "Jahmyr Gibbs", "result": "won"}]}
    return b


def test_the_public_board_carries_none_of_the_report():
    full = _full_board()
    rep = full["game_reports"][0]
    keep = copy.deepcopy(full)
    public = gate.redact(full, "recommendations.json")
    assert full == keep, "the members' copy is never touched"
    for k in REPORT_KEYS:
        assert k in gate.PAID_KEYS, k
        assert not public.get(k), k
    assert public["locked"]["game_reports"] == 1 and public["locked"]["game_parlays"] == 1
    # The drive simulation the report quotes ("our simulation of the game ... the Lions 58%") is a member's too.
    assert all("sim" not in g for g in public["games"]) and public["locked"]["games[].fields"] == 1
    assert full["games"][0]["sim"]["trials"] == 4000, "the members' rows keep it"
    # Not one of the report's words: its titles, the answers beside them, its sentences, its picks.
    text = json.dumps(public, ensure_ascii=False)
    said = [s["title"] for s in rep["sections"]] + [s["hint"] for s in rep["sections"] if s.get("hint")]
    said += [b["text"] for s in rep["sections"] for b in s["blocks"] if b.get("type") == "p" and len(b.get("text") or "") > 40]
    assert len(said) > 20, len(said)
    leaked = [x for x in said if x in text]
    assert not leaked, leaked[:5]
    for words in ("Who we think wins", "Lions 60%", "Breakout candidates", "by our numbers", "Jahmyr Gibbs"):
        assert words not in text, words


def test_a_public_file_written_before_the_cut_is_sealed_at_the_next_start():
    """The startup seal and the server's own check read gate._paid_rows: it counts the rows still carrying a
    paid field now (`_row_fields`), so the NFL file published before this deploy loses its simulation when the
    server starts, not at its board's next build."""
    import tempfile
    full = _full_board()
    public_then = dict(gate.redact(full, "recommendations.json"))
    public_then["games"] = [dict(g, sim={"trials": 4000, "p_home_win": 0.58}) for g in public_then["games"]]
    assert gate._paid_rows(public_then, "recommendations.json") == 1, "the row with the simulation is counted"
    assert gate._paid_rows(gate.redact(public_then, "recommendations.json"), "recommendations.json") == 0
    keep = gate.enabled
    gate.enabled = lambda: True
    try:
        with tempfile.TemporaryDirectory() as d:
            web = Path(d) / "web" / "data"
            web.mkdir(parents=True)
            (web / "recommendations.json").write_text(json.dumps(public_then))
            assert gate.unsealed(web) == [{"board": "recommendations.json", "rows": 1}]
            res = gate.seal(web_data=web, verbose=False)
            assert [x["board"] for x in res["sealed"]] == ["recommendations.json"]
            after = json.loads((web / "recommendations.json").read_text())
            assert all("sim" not in g for g in after["games"]) and gate.unsealed(web) == []
            assert after["games"][0]["spread"] == full["games"][0]["spread"], "the game's facts stay"
    finally:
        gate.enabled = keep


def test_the_games_facts_stay_free():
    public = gate.redact(_full_board(), "recommendations.json")
    g = public["games"][0]
    for k in ("away", "home", "kickoff", "spread", "total", "home_ml", "away_ml", "stadium", "weather", "scan"):
        assert k in g, k
    # The scan's numbers ride on the game, free; its reads (who we think shines) are a member's.
    assert g["scan"].get("units") and not public.get("scan_reads")


def test_every_endpoint_that_reads_a_report_answers_a_member():
    import server
    out = {}
    h = object.__new__(server.Handler)
    h._send = lambda code, body, kind=".json", headers=None: out.update(code=code, body=json.loads(body))
    h._rate_limited = lambda limit, bucket="read": False

    class Conn:
        def close(self):
            pass
    keep = (gate.enabled, server._acct)
    gate.enabled = lambda: True
    server._acct = lambda: type("A", (), {"connect": staticmethod(lambda: Conn())})
    try:
        h._account = lambda conn: {"id": 7, "email": "free@example.com"}
        h._entitled = lambda conn, who: False
        # A finished game's report, graded: refused before anything is read.
        h._report_archive({"league": ["nfl"], "date": ["2026-10-25"], "away": ["GB"], "home": ["DET"]})
        assert out["code"] == 402 and out["body"]["locked"] is True
        # Ask: refused before anything is read or spent, a free account and a stranger alike.
        h._ask({"board": "recommendations.json", "question": "Who wins Packers at Lions?"})
        assert out["code"] == 402 and out["body"]["error"] == "Ask needs a subscription."
        h._account = lambda conn: None
        h._ask({"board": "recommendations.json", "question": "Who wins Packers at Lions?"})
        assert out["code"] == 401
    finally:
        gate.enabled, server._acct = keep
    # The live tickets: a count, never a ticket (tests/test_a_reports_parlays_are_followed_live.py runs it).
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    live = src[src.index("    def _report_live(self):"):src.index("    def _report_archive(self, q):")]
    assert "doc if member else reportlive.counts(doc)" in live


def test_the_page_locks_the_report_for_a_free_account():
    detail = (ROOT / "web" / "js" / "detail.js").read_text(encoding="utf-8")
    wall = detail[detail.index("  if (isWalled()) {\n    host.querySelectorAll(\".gp-jump, #gp-sec-results, #gp-sec-report"):]
    wall = wall[:wall.index("\n  }\n")]
    for sec in ("#gp-sec-results", "#gp-sec-report", "#gp-sec-plan", "#gp-sec-replay", "#gp-sec-scripts"):
        assert sec in wall, sec
    assert 'memberLockHTML("The analysis and every pick on this game"' in wall
    assert "Members read the written game report" in wall
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    rail = app[app.index("function pbpPropsHTML(d, league) {"):app.index("function openPbp(")]
    assert rail.index("if (isWalled())") < rail.index("reportLiveSlot(d, league)"), "the lock comes before the tickets"
    wall_open = app[app.index("const WALL_OPEN = ["):]
    wall_open = wall_open[:wall_open.index("];")]
    assert '"reportpicks"' not in wall_open, "Report Picks is a member's page"
    account = (ROOT / "web" / "js" / "account.js").read_text(encoding="utf-8")
    assert '["Game reports, matchups, line moves and pick alerts", 0],' in account, "the sign-up's table: members"
    assert 'reportpicks: ["Game reports are for members",' in account
    assert "Members read every report before the game." in account


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as e:                                   # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
    if fails:
        sys.exit(1)
    print(f"\n{len(tests)} tests passed.")
