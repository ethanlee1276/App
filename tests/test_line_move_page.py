"""Line movement on the prop page.

Ethan, 2026-09-05: "line movement on prop page". Every real odds pull
writes a snapshot of each prop at each book, and the card has stamped
"Market with / against pick" off them since August; nothing drew the
line itself. `prop_series` reads today's tape for the pick's side — the
consensus line and the best price at each pull — the three builds that
record snapshots hang it on every priced pick, and the prop page draws
it: opened at, now at, the price then and now, the picture, and which
way that cut for our side.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import linemoves as lm                                  # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _row(ts, player, market, book, line, over, under=-110):
    return {"ts": ts, "player": player, "market": market, "book": book,
            "line": line, "over_odds": over, "under_odds": under}


ROWS = [
    _row(1000, "Ja'Marr Chase", "rec_yds", "DraftKings", 58.5, -110, -114),
    _row(1000, "Ja'Marr Chase", "rec_yds", "FanDuel", 58.5, -112, -110),
    _row(1000, "Ja'Marr Chase", "rec_yds", "BetMGM", 57.5, -105, -118),
    _row(2000, "Ja'Marr Chase", "rec_yds", "DraftKings", 55.5, -110, 0),
    _row(2000, "Ja'Marr Chase", "rec_yds", "FanDuel", 55.5, -115, -108),
    _row(3000, "Ja'Marr Chase", "rec_yds", "FanDuel", 52.5, -110, -110),
    _row(3000, "Ja'Marr Chase", "rec_yds", "DraftKings", 52.5, -114, None),
    _row(1500, "Tee Higgins", "rec_yds", "FanDuel", 60.5, -110, -110),
    _row(2500, "Ja'Marr Chase", "receptions", "FanDuel", 6.5, -120, 100),
]


def test_a_series_is_the_consensus_line_and_the_best_price_for_the_side_per_pull():
    under = lm.prop_series(ROWS, "Ja'Marr Chase", "rec_yds", "UNDER")
    assert [p["ts"] for p in under] == [1000.0, 2000.0, 3000.0], "oldest first, other players and markets ignored"
    assert [p["line"] for p in under] == [58.5, 55.5, 52.5], "the median line across the books at that instant"
    assert [p["odds"] for p in under] == [-110, -108, -110], "the best UNDER price among the books at that line"
    assert [p["book"] for p in under] == ["FanDuel", "FanDuel", "FanDuel"]
    assert [p["books"] for p in under] == [3, 2, 2]
    over = lm.prop_series(ROWS, "Ja'Marr Chase", "rec_yds", "OVER")
    assert [p["odds"] for p in over] == [-110, -110, -110], "the OVER reads the over prices"
    assert over[0]["book"] == "DraftKings"


def test_an_unquoted_side_is_no_price_never_a_fabricated_one():
    only = [_row(1000, "X", "hits", "DraftKings", 1.5, -110, 0), _row(1000, "X", "hits", "FanDuel", 1.5, -105, None)]
    s = lm.prop_series(only, "X", "hits", "UNDER")
    assert s == [{"ts": 1000.0, "line": 1.5, "odds": None, "book": None, "books": 2}], s


def test_a_long_tape_is_thinned_and_keeps_its_open_and_its_now():
    rows = [_row(1000 + i * 60, "X", "hits", "FanDuel", 1.5 + (i % 3) * 0.5, -110) for i in range(200)]
    s = lm.prop_series(rows, "X", "hits", "OVER", limit=10)
    assert len(s) == 10 and s[0]["ts"] == 1000.0 and s[-1]["ts"] == 1000.0 + 199 * 60, (len(s), s[0], s[-1])
    assert [p["ts"] for p in s] == sorted(p["ts"] for p in s)
    assert lm.SERIES_MAX == 48


def test_the_tape_is_hung_on_priced_picks_with_two_points_or_more():
    recs = [
        {"player": "Ja'Marr Chase", "market": "rec_yds", "side": "UNDER"},
        {"player": "Tee Higgins", "market": "rec_yds", "side": "OVER"},
        {"player": "Ja'Marr Chase", "market": "receptions", "side": "OVER", "has_market": False},
        {"player": "Somebody", "market": "rec_yds", "side": "LEAN"},
    ]
    n = lm.attach_series(recs, ROWS)
    assert n == 1
    assert len(recs[0]["line_series"]) == 3 and "line_series" not in recs[1], "one point is not a line"
    assert "line_series" not in recs[2] and "line_series" not in recs[3]


def test_the_three_builds_that_record_snapshots_hang_it_from_the_same_rows():
    for name, call in (("nfl_build.py", 'attach_series(result["recommendations"], _today)'),
                       ("mlb_build.py", 'attach_series(result["recommendations"], _today)'),
                       ("nba_build.py", "_attach_series(recs, _today)")):
        src = (ROOT / name).read_text()
        assert "_today = todays_rows(stream_history())" in src, name
        assert "analyze(_today)" in src, name
        assert call in src, f"{name}: the series must come from the same rows, read once"
        assert src.count("todays_rows(stream_history())") == src.count("_today = todays_rows(stream_history())") \
            + (1 if name == "nfl_build.py" else 0), f"{name}: the snapshot file streamed more than it needs"


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    def fn(name):
        i = APP.index(f"function {name}(")
        ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
        ends = [e for e in ends if e != -1] or [len(APP)]
        return APP[i:min(ends)]
    i = APP.index("const payoutOf = ")
    payout = APP[i:APP.index("\n", i)]
    prog = f"""
      {payout}
      {fn("lineMoveHeadline")}
      {fn("lineMoveSentence")}
      {fn("lineSeriesSVG")}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_reads_which_way_the_market_went_for_our_side():
    got = _node("""
      const S = (pts) => pts.map(([ts, line, odds]) => ({ ts, line, odds }));
      const H = (side, pts) => lineMoveHeadline({ side, line_series: S(pts) });
      const out = {};
      // The line fell six points toward the under and our side's price shortened: both toward us.
      out.underTowards = H("UNDER", [[1000, 58.5, -114], [4600, 52.5, -120]]);
      out.overAway = H("OVER", [[1000, 20.5, -110], [4600, 18.5, -110]]);
      out.priceTowards = H("OVER", [[1000, 20.5, -105], [1600, 20.5, -125]]);
      out.mixed = H("UNDER", [[1000, 58.5, -125], [1600, 52.5, -105]]);
      out.flat = H("OVER", [[1000, 20.5, -110], [1600, 20.5, -110]]);
      out.one = H("OVER", [[1000, 20.5, -110]]);
      out.none = lineMoveHeadline({});
      out.s = Object.fromEntries(Object.entries(out).map(([k, h]) => [k, lineMoveSentence(h)]));
      out.svg = lineSeriesSVG(S([[1000, 58.5, -110], [2000, 55.5, -110], [3000, 52.5, -110]]), 300, 62);
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    u = got["underTowards"]
    assert u["lineMoved"] and u["lineToward"] is True and u["priceMoved"] and u["priceToward"] is True and u["hours"] == 1
    assert got["overAway"]["lineToward"] is False
    assert got["priceTowards"]["lineMoved"] is False and got["priceTowards"]["priceToward"] is True, "our side's price got shorter"
    assert got["mixed"]["lineToward"] is True and got["mixed"]["priceToward"] is False
    assert got["flat"]["lineMoved"] is False and got["flat"]["priceMoved"] is False
    assert got["one"] is None and got["none"] is None
    s = got["s"]
    assert s["underTowards"].startswith("The market has moved toward our side")
    assert s["overAway"].startswith("The market has moved away from our side") and "rides as placed" in s["overAway"]
    assert s["mixed"].startswith("The line moved toward our side and the price away")
    assert s["flat"] == "The number has not moved today." and s["one"] == ""
    assert 'stroke-dasharray="3 3"' in got["svg"] and "<path d=\"M1.0," in got["svg"] and "<circle" in got["svg"]


def test_the_prop_page_draws_it_after_the_shop():
    i = APP.index("function renderPropPage()")
    page = APP[i:APP.index("\n/* ====", i)]
    assert "${lineMoveHTML(r)}" in page
    assert page.index("${booksTableHTML(r)}") < page.index("${lineMoveHTML(r)}") < page.index("Last ${shown} game")
    html = APP[APP.index("function lineMoveHTML("):APP.index("function booksChip(")]
    assert "placedStamp(new Date(Number(ts) * 1000).toISOString())" in html, "the pull's time in the reader's zone"
    assert "How the line moved today" in html and "The dashed line is the open." in html
    assert "moveChip(r)" in html, "the card's own with/against chip, so the two never disagree"
    for sel in (".lm-card", ".lm-row", ".lm-when"):
        assert sel in CSS, sel


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
