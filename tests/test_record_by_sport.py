"""One record per model, because the aggregate hides the thing you'd fix.

The combined page answers "is the system making money" — the owner's
question. A per-sport page answers "is THIS model any good", which is what
the next change to it depends on, and averaging six models actively
conceals it: a baseball model reading four points hot and a football model
four points cold produce a perfect calibration line nobody should trust.

Built from a journal where that is literally true — MLB +1.8%, NFL -18.9%,
combined -7.1%.
"""

import datetime
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import ledger

# (win rate, bets) — chosen so the combined number tells you nothing.
PLAN = {"mlb": (0.75, 40), "nfl": (0.25, 40), "nba": (0.50, 20)}


def _journal():
    conn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    d0 = datetime.date(2026, 4, 1)
    for sport, (rate, n) in PLAN.items():
        wins = int(n * rate)
        for i in range(n):
            won = i < wins
            conn.execute(
                "INSERT INTO bets (sport, date, player, market, side, line,"
                " odds, grade, stake_units, stake_dollars, status, category,"
                " pnl_units, hit_prob, edge, closing_line)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (sport, (d0 + datetime.timedelta(days=i)).isoformat(),
                 f"{sport} Player {i}", "total", "OVER", 1.5, -110, "A",
                 1.0, 10.0, "won" if won else "lost", "main",
                 0.909 if won else -1.0, 0.60, 0.04, 2.5))
    # Open bets on ONE sport only — the bug this file was written after.
    for i in range(3):
        conn.execute(
            "INSERT INTO bets (sport, date, player, market, side, line, odds,"
            " grade, stake_units, stake_dollars, status, category)"
            " VALUES ('mlb','2026-09-01',?,'total','OVER',1.5,-110,'A',"
            "1.0,10.0,'open','main')", (f"Open {i}",))
    conn.commit()
    return conn


# --- the bug that made this necessary ---------------------------------------
def test_open_bets_are_counted_per_sport():
    """`performance(conn, "mlb")` filtered every number by sport EXCEPT the
    open count, which read the whole journal — so football's open bets were
    reported as baseball's. Invisible while one board was live, and exactly
    wrong the moment six are."""
    conn = _journal()
    per = {sp: ledger.performance(conn, sp)["open"] for sp in PLAN}
    assert per == {"mlb": 3, "nfl": 0, "nba": 0}, per
    assert sum(per.values()) == ledger.performance(conn)["open"]


def test_the_parts_sum_to_the_whole():
    conn = _journal()
    total = ledger.performance(conn)
    parts = [ledger.performance(conn, sp) for sp in PLAN]
    assert sum(p["wins"] for p in parts) == total["wins"]
    assert sum(p["losses"] for p in parts) == total["losses"]
    assert abs(sum(p["net_units"] for p in parts) - total["net_units"]) < 1e-6


# --- what the aggregate hides -----------------------------------------------
def test_a_good_model_and_a_bad_one_do_not_average_into_an_opinion():
    conn = _journal()
    mlb = ledger.sport_report(conn, "mlb")["overall"]
    nfl = ledger.sport_report(conn, "nfl")["overall"]
    combined = ledger.performance(conn)
    assert mlb["roi"] > 0 > nfl["roi"], "the fixture is not testing anything"
    # The combined number sits between them and describes neither.
    assert nfl["roi"] < combined["roi"] < mlb["roi"]


def test_calibration_is_scoped_too():
    """An aggregate calibration answers "is the SYSTEM honest", which is
    not the question somebody tuning one model is asking."""
    conn = _journal()
    mlb = ledger.calibration(conn, sport="mlb")
    nfl = ledger.calibration(conn, sport="nfl")
    allc = ledger.calibration(conn)
    n = lambda c: sum(b["n"] for b in c["buckets"])
    assert n(mlb) == 40 and n(nfl) == 40 and n(allc) == 100
    # Same claimed probability, opposite realities — the whole point.
    assert mlb["buckets"] != nfl["buckets"]


def test_the_receipts_are_scoped_too():
    conn = _journal()
    rows = ledger.recent_settled(conn, 50, sport="nfl")
    assert rows and all(r["sport"] == "nfl" for r in rows)


def test_a_thin_record_says_so_rather_than_printing_a_percentage_alone():
    """A 3-1 record is not a 75% win rate, and a page that shows one
    without the other invites exactly that read."""
    conn = _journal()
    assert ledger.sport_report(conn, "nba")["thin"] is True    # 20 bets
    assert ledger.sport_report(conn, "mlb")["thin"] is False   # 40
    assert ledger.sport_report(conn, "mlb")["min_graded"] == \
        ledger.MIN_GRADED_FOR_SIGNAL


def test_a_sport_with_nothing_journaled_still_reports():
    """Hiding it would make "no bets yet" and "no such board" look
    identical."""
    conn = _journal()
    r = ledger.sport_report(conn, "wnba")
    assert r["overall"]["settled"] == 0 and r["overall"]["open"] == 0
    assert r["curve"] == [] and r["recent"] == []


def test_every_board_that_journals_a_bet_is_tracked():
    assert set(ledger.TRACKED_SPORTS) == {"nfl", "cfb", "mlb", "nba",
                                          "wnba", "ufc"}
    # Polymarket is deliberately absent: its flags are not wagers in this
    # ledger, and folding a flag rate into a betting P&L would make both
    # numbers mean nothing.
    assert "intel" not in ledger.TRACKED_SPORTS
    assert "polymarket" not in ledger.TRACKED_SPORTS


def test_the_export_carries_every_sport():
    import json
    conn = _journal()
    path = os.path.join(tempfile.mkdtemp(), "record.json")
    ledger.export_json(conn, path)
    blob = json.loads(open(path).read())
    assert set(blob["by_sport"]) == set(ledger.TRACKED_SPORTS)
    assert blob["tracked_sports"] == list(ledger.TRACKED_SPORTS)
    for sp, r in blob["by_sport"].items():
        assert r["sport"] == sp
        assert "overall" in r and "calibration" in r and "curve" in r


# --- the page ---------------------------------------------------------------
def _read(*parts):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_the_record_page_defaults_to_the_sport_you_came_from():
    js = _read("web", "js", "app.js")
    assert "_recordScope" in js
    fn = js[js.index("async function renderRecord()"):]
    assert "tracked.includes(state.sport) ? state.sport : \"all\"" in fn


def test_panels_read_one_source_rather_than_being_filtered_each_time():
    """Scoping by swapping the source means a panel cannot quietly keep
    showing the combined number next to a per-sport one."""
    js = _read("web", "js", "app.js")
    fn = js[js.index("async function renderRecord()"):
            js.index("function recStaleSection(")]
    assert "const src = scoped || d;" in fn
    # recAnalytics wraps recCurveChart since Ethan's analytics render
    # (2026-08-11) — same scoping contract, now with range chips.
    for panel in ("recAnalytics(src.curve", "recCalibrationSection(src.calibration"):
        assert panel in fn, f"{panel} still reads the combined payload"


def test_whole_journal_panels_do_not_repeat_under_a_sport():
    """A per-book limit risk and a cross-sport promotion bar are not
    per-sport questions, so they must not appear with an unscoped number
    under a sport's name."""
    js = _read("web", "js", "app.js")
    fn = js[js.index("async function renderRecord()"):
            js.index("function recStaleSection(")]
    for panel in ("recHealthSection", "recLongshotSection", "recStaleSection",
                  "recFormSection", "recLooseSection", "recEraSection"):
        i = fn.index(panel + "(d.")
        assert "scoped" in fn[max(0, i - 120):i], \
            f"{panel} is shown unscoped under a per-sport record"


def test_polymarket_has_its_own_scope_and_is_not_a_betting_pnl():
    js = _read("web", "js", "app.js")
    # Renamed 2026-08-18 — Ethan: "change the name of the polly market
    # page to 'prediction market'". Scope id stays "intel".
    assert 'btn("intel", "Prediction Market"' in js
    fn = js[js.index("async function renderRecord()"):]
    assert 'scope === "intel"' in fn
    # It must not fall through to the betting KPIs, which would all read
    # zero and look like a losing model rather than a different thing.
    i = fn.index('if (scope === "intel")')
    assert "recPolymarketSection" in fn[i:i + 400]
    assert "return;" in fn[i:i + 900]


def test_ufc_gets_a_scope_like_every_other_board():
    assert "ufc" in ledger.TRACKED_SPORTS
    js = _read("web", "js", "app.js")
    assert 'scope !== "ufc"' in js, "the UFC bucket ignores the scope"


def test_the_running_pnl_marks_where_the_model_changed():
    """Ethan, 2026-08-23, with the 1W and ALL charts side by side: "how
    has the mlb been doing so good lately and it's been showing on the
    weekly graph but it doesn't seem like the all time numbers r moving."

    They were moving — the week climbed 7.05u of a 25.82u hole, 27% of
    it. But the all-time line draws two different models as one
    continuous story, so an upturn at the end reads as noise in a long
    decline rather than as the point where the board started pricing
    differently. A dashed rule at each era start says what the era table
    below already says in words.

    Driven under node rather than read, because "the rule lands on the
    right day" is the only part that matters and it is arithmetic."""
    node = shutil.which("node")
    if not node:
        return
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = open(os.path.join(root, "web", "js", "app.js"),
               encoding="utf-8").read()

    # Past the PARAMETER LIST before hunting the body: `opts = {}` is a
    # brace too, and starting at the first `{` after the name lands on
    # that default instead of the function.
    i = app.index("function recCurveChart(")
    j, depth = app.index("(", i), 0
    while j < len(app):
        if app[j] == "(":
            depth += 1
        elif app[j] == ")":
            depth -= 1
            if not depth:
                break
        j += 1
    start, d = app.index("{", j), 0
    for k in range(start, len(app)):
        if app[k] == "{":
            d += 1
        elif app[k] == "}":
            d -= 1
            if not d:
                body = app[i:k + 1]
                break

    check = body + """
const escapeHtml = (s) => String(s);
const escapeAttr = escapeHtml;
const toneOf = (v) => (v > 0 ? "good" : v < 0 ? "bad" : "");
const F = (m) => { console.error(m); process.exit(1); };
const curve = []; let cum = 0;
for (let i = 0; i < 40; i++) {
  const day = i < 28 ? -0.92 : 0.59; cum += day;
  curve.push({ date: new Date(Date.UTC(2026, 6, 15 + i)).toISOString().slice(0, 10),
               cum_u: +cum.toFixed(2), day_u: day, n: 5 });
}
const eras = [{ key: "v1", from: null }, { key: "v2", from: "2026-07-29" },
              { key: "v3", from: "2026-08-13" }];
const rules = (h) => (h.match(/stroke-dasharray="3 3"/g) || []).length;
const full = recCurveChart(curve, { head: false, eras });
if (rules(full) !== 2) F("expected 2 rules, got " + rules(full));
if (!full.includes(">07/29<") || !full.includes(">08/13<")) F("labels missing");
// The first era has no start date and must not draw one.
if (full.includes(">null<")) F("an open-ended era drew a rule");
// A short window must not stack every marker on its left edge.
if (rules(recCurveChart(curve.slice(-7), { head: false, eras })))
  F("a marker outside the window was drawn");
// Absent, empty and pre-history eras are all harmless.
if (rules(recCurveChart(curve, { head: false }))) F("no eras still drew one");
if (rules(recCurveChart(curve, { head: false, eras: [] }))) F("empty eras");
if (rules(recCurveChart(curve, { head: false,
    eras: [{ key: "old", from: "2020-01-01" }] })))
  F("an era older than the whole curve drew a rule at index 0");
console.log("ok");
"""
    out = subprocess.run([node, "-e", check], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr.strip() or out.stdout.strip()


def test_the_chart_is_handed_the_eras_it_draws():
    """The wiring, which the node check above cannot see: the payload
    already carried model_eras for the table underneath, and the chart
    was never given them."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = open(os.path.join(root, "web", "js", "app.js"),
               encoding="utf-8").read()
    assert "recAnalytics(src.curve, o, ((d.model_eras || {}).eras) || [])" in app
    assert "recCurveChart(sliced, { head: false, eras })" in app


def test_the_era_row_shows_whether_the_claims_came_true():
    """The section is called "did the re-tune work?" and could only
    answer in W-L, ROI and CLV — all of which need a season. The claim
    gap converges on every settled bet, so it is the one number that can
    answer the question the heading asks."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = open(os.path.join(root, "web", "js", "app.js"),
               encoding="utf-8").read()
    i = app.index("function recEraSection(")
    body = app[i:app.index("\nfunction ", i + 10)]
    assert "e.claim" in body, "the row never reads the claim gap"
    assert "landed" in body and "said" in body, (
        "the row does not show both numbers a reader could check")
    # Toned only when it clears two standard errors — under that it is a
    # sample, and colouring it would be the site claiming a finding it
    # does not have.
    assert "cl.se" in body and "<= -2" in body, (
        "a claim gap inside the noise is being coloured as a verdict")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
