"""The headline record is the model's own book, under the same floor
everywhere, with every wider total labelled and second.

Audit 2026-09-30, P1-1 / P1-6 / V-5 (roadmap #4, Ethan's yes 2026-09-30):

  * `adoptPooledRecord` seated the POOLED journal — the edge board, the
    staked Most Likely rows and the 0.1u Most Likely favourites — as
    "the record" on Home, the Record page and the paywall. Roughly half
    its wins were flat 0.1u paper favourites. The headline is now the
    edge board (`pooled.edge`); the pooled total stays, labelled, second.
  * The ribbons printed "+90.9% ROI" with a full ring on a 1-0 book while
    the sidebar refused an ROI under `min_graded`. One floor now, one
    helper (`recFloor`), every ribbon.
  * "1 money + 1 paper" of 1 settled: paper is settled minus money.
  * "Everything we've bet" led, headlined units while the model tile
    headlined ROI, and never said who Zeno is.
  * The Top Pick claim log was written every cycle and never published.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text()


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head)
            return APP[i:APP.index("\n}\n", i) + 2]
    raise AssertionError(name)


STUBS = ("const MINUS='\\u2212';const escapeHtml=(x)=>String(x==null?'':x);"
         "let _recMinGraded=30;const zenoMoney=(v)=>'$'+Number(v).toFixed(2);"
         "const pikkitBadgeHTML=()=>'[pikkit]';const trueMinus=(s)=>s;\n")


def _node(body: str, call: str, arg):
    if not shutil.which("node"):
        return None
    path = os.path.join(tempfile.mkdtemp(), "h.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(STUBS + body + "\nconst a=JSON.parse(process.argv[2]);"
                 f"process.stdout.write(JSON.stringify({call}));")
    out = subprocess.run(["node", path, json.dumps(arg)], capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


def _ribbons(rec, ov):
    body = _fn("recFloor") + _fn("recordRibbonsHTML")
    got = _node(body, "recordRibbonsHTML(a.rec, a.ov, [])", {"rec": rec, "ov": ov})
    return None if got is None else re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", got))


def test_under_the_floor_a_ribbon_prints_its_count_and_no_roi():
    txt = _ribbons({"min_graded": 30},
                   {"settled": 1, "wins": 1, "losses": 0, "roi": 0.909, "net_units": 0.91})
    if txt is None:
        return
    assert "1 of 30" in txt, txt
    assert "ROI" not in txt and "90.9" not in txt and "91%" not in txt, txt


def test_over_the_floor_the_roi_prints():
    txt = _ribbons({"min_graded": 30},
                   {"settled": 40, "wins": 24, "losses": 16, "roi": 0.051, "net_units": 2.0})
    if txt is None:
        return
    assert "+5.1% ROI" in txt, txt


def test_the_models_tile_leads_and_every_total_is_labelled_second():
    rec = {"min_graded": 30,
           "pooled_overall": {"settled": 120, "wins": 70, "losses": 50, "roi": 0.02,
                              "net_units": 3.0},
           "combined": {"settled": 1400, "wins": 300, "losses": 1100, "roi": 0.26,
                        "net_units": 800.0,
                        "split": {"model": {"net_units": 3.0}, "zeno": {"net_units": 797.0}}}}
    txt = _ribbons(rec, {"settled": 60, "wins": 33, "losses": 27, "roi": 0.03,
                         "net_units": 2.0})
    if txt is None:
        return
    a = txt.index("Model")
    b = txt.index("Combined · edge + Most Likely boards")
    c = txt.index("Combined · Zeno’s book + ours")
    assert a < b < c, txt
    # One headline metric: the combined tile leads with its ROI too.
    assert "+26.0% ROI" in txt[c:c + 200], txt[c:c + 200]


def test_the_floor_is_one_helper_shared_by_the_rail_and_the_ribbons():
    assert "recFloor(" in _fn("recordRibbonsHTML")
    assert "recFloor(rec, o)" in _fn("renderStandingRecord")


def test_the_headline_is_the_edge_board_and_the_pool_is_kept_beside_it():
    rec = {"overall": {"settled": 9, "tag": "book"}, "curve": ["b"], "recent": ["b"],
           "pooled": {"overall": {"settled": 20, "tag": "pooled"},
                      "edge": {"settled": 12, "tag": "edge"},
                      "edge_curve": ["e"], "edge_recent": ["e"]}}
    got = _node(_fn("adoptPooledRecord"), "adoptPooledRecord(a)", rec)
    if got is None:
        return
    assert got["overall"]["tag"] == "edge"
    assert got["pooled_overall"]["tag"] == "pooled"
    assert got["curve"] == ["e"] and got["recent"] == ["e"]


def test_paper_is_settled_minus_money():
    got = _node(_fn("moneySplitHTML"), "moneySplitHTML(a)",
                {"money_bets": 1, "paper_bets": 1, "settled": 1, "net_dollars": 5})
    if got is None:
        return
    assert "Every settled pick here had real money on it" in got, got


def test_the_paywall_and_the_record_page_pass_the_pool_and_the_floor():
    i = APP.index("const ribbon = recordRibbonsHTML({ combined: rec && rec.combined")
    call = APP[i:i + 300]
    assert "pooled_overall" in call and "min_graded" in call
    assert "pooled_overall: winO ? null : src.pooled_overall" in APP


def test_the_verdict_names_the_combined_line():
    assert "src.pooled_overall" in _fn("recordVerdictHTML")


def test_the_page_says_who_zeno_is():
    assert "the site owner’s own bets" in _fn("zenoWhoHTML")
    assert "${zenoWhoHTML(rec)}" in _fn("deckRecordHTML")
    assert "${zenoWhoHTML(rec)}" in _fn("pwResultsHTML")


# --- the engine --------------------------------------------------------------
def test_the_pooled_report_carries_the_edge_boards_own_curve():
    from engine import ledger
    conn = ledger.connect(":memory:")
    rep = ledger.pooled_report(conn)
    assert "edge_curve" in rep and "edge_recent" in rep


def test_the_top_pick_claims_are_published():
    from engine import ledger
    conn = ledger.connect(":memory:")
    ledger.record_top_pick_claim(conn, {
        "date": "2026-09-29", "sport": "nfl",
        "pick": {"player": "A", "market": "receptions", "side": "over",
                 "line": 4.5, "odds": -110, "evidence": "sharp"}})
    got = ledger.recent_top_pick_claims(conn, days=14, today="2026-09-30")
    assert got and got[0]["date"] == "2026-09-29" and got[0]["claims"][0]["player"] == "A"
    out = Path(tempfile.mkdtemp()) / "record.json"
    ledger.export_json(conn, out)
    assert "potd_claims" in json.loads(out.read_text())
    assert "d.potd_claims" in APP, "the page reads it"


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items())
           if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
