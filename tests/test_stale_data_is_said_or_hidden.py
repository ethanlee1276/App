"""Stale data on the page: the reader is told, or it is not shown.

Ethan, 2026-09-25: "The whole point of all of this is for the user to go
onto the site and in that moment in real time look at data, look at pics
with real up-to-date information with our models, real up-to-date
estimate … if that shit's stale, then the user should know that or we
shouldn't show it."

Four holes, one test block each:
  * THE BOARD. A board two cycles late only greyed a corner chip until it
    was twelve hours old. Now the banner says how old every number is,
    and past an hour the picks come off the page until a build lands.
  * THE PRICE. `price_age_s` is the price's age when the build ran; a page
    read an hour later printed "priced 4m ago". Rows now carry the pull's
    clock time (`priced_at`) and the page ages it to the second.
  * THE LOCKED PICK. It showed the price it went up at, forever. It now
    carries today's best price at the same number, or says no book lists it.
  * THE MODEL'S INPUTS. The week-table check (engine/freshness) went to the
    build log only. It now rides on the NFL board and the page says which
    tables are behind.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import likely as K                                   # noqa: E402
from engine.sources import oddsapi                               # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()
NFL = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
FITS = {"rush_yds": {"zero": [-0.04, 0.82], "sigma": 0.54}}


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def _node(js, *names, pre=""):
    if not shutil.which("node"):
        return None
    prog = ("var escapeHtml=(s)=>String(s==null?'':s);"
            "var american=(o)=>(o>0?'+':'')+o;"
            "var icon=()=>'';" + pre + "\n"
            + "\n".join(_fn(n) for n in names)
            + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));")
    path = os.path.join(tempfile.mkdtemp(), "s.js")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prog)
    out = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout.strip())


# ── the board ─────────────────────────────────────────────────────────────


def test_a_late_board_says_so_and_a_badly_late_one_withholds_its_picks():
    bar = _fn("renderStaleBar")
    assert bar.index("wireDown()") < bar.index("withholdAfterMs()") < bar.index("staleAfterMs()"), \
        "unreachable first, then withheld, then late"
    assert "Picks are hidden" in bar and "later than usual" in bar
    assert "const STALE_HIDE_FLOOR_MS = 60 * 60 * 1000;" in APP
    assert 'document.body.classList.toggle("picks-withheld", picksWithheld());' in _fn("updateAgo")
    rule = CSS[CSS.index("body.picks-withheld"):]
    rule = rule[:rule.index("}")]
    for host in ("#potd-zone", "#best-bets", "#likely-top", "#likely", "#edge-board",
                 "#props-body", "#longshots", "#cards", "#gp-sec-likely"):
        assert host in rule, host
    assert "display: none" in rule


def test_the_withhold_waits_for_a_slow_machine():
    got = _node("""
      _cycleMs = null; const a = withholdAfterMs();
      _cycleMs = 30 * 60000; const b = withholdAfterMs();
      state.builtAt = Date.now() - 50 * 60000; _cycleMs = null; const c = picksWithheld();
      state.builtAt = Date.now() - 70 * 60000; const d = picksWithheld();
      state.builtAt = null; const e = picksWithheld();
      return [a, b, c, d, e];""", "withholdAfterMs", "picksWithheld",
                pre="var state={}; var _cycleMs=null; const STALE_HIDE_FLOOR_MS=3600000;")
    if got is None:
        return
    assert got == [3600000, 7200000, False, True, False], got


# ── the price ─────────────────────────────────────────────────────────────


def test_a_price_is_aged_to_now_not_to_the_build():
    now = "Date.now()"
    got = _node(f"""
      const at = new Date({now} - 3 * 3600 * 1000).toISOString();
      state.builtAt = {now} - 2 * 3600 * 1000;
      return {{
        stamped: priceAgeChip({{ priced_at: at, price_age_s: 60 }}),
        unstamped: priceAgeChip({{ price_age_s: 60 }}),
        old: priceAgeChip({{ priced_at: new Date({now} - 7 * 3600 * 1000).toISOString() }}),
        locked: priceAgeChip({{ locked: true, priced_at: at }}),
        none: priceAgeChip({{}}),
      }};""", "priceAgeS", "agoText", "priceAgeChip",
                pre="var state={}; const PRICE_FRESH_S = 6 * 3600;")
    if got is None:
        return
    assert "3h ago" in got["stamped"] and "may have moved" not in got["stamped"], got["stamped"]
    assert "2h ago" in got["unstamped"], "an old board's age counts the time since its build"
    assert "7h ago" in got["old"] and "may have moved" in got["old"], got["old"]
    assert "posted price, pulled 3h ago" in got["locked"], got["locked"]
    assert got["none"] == ""


def test_the_page_bar_is_the_engines():
    assert f"const PRICE_FRESH_S = {int(oddsapi.MAX_PROP_PRICE_AGE) // 3600} * 3600;" in APP


def test_priced_at_is_the_build_stamp_less_the_age():
    assert K._priced_at("2026-09-23T20:00:00Z", 600) == "2026-09-23T19:50:00Z"
    assert K._priced_at("2026-09-23T20:00:00Z", None) is None
    assert K._priced_at("junk", 60) is None


# ── the locked pick ───────────────────────────────────────────────────────


def _ln(book, line, over, under):
    return {"book": book, "line": line, "over_odds": over, "under_odds": under}


def _row(projection, alts, age=600):
    return {"player": "Jameson Williams", "team": "DET", "opponent": "NYJ", "market": "rush_yds",
            "market_label": "Rush Yards", "side": "over", "line": 62.5, "book": "DK", "odds": -110,
            "has_market": True, "fair_prob": 0.50, "projection": projection, "ev_per_unit": 0.01,
            "reasons": ["because"], "recent_values": [55, 71, 48, 66], "game_date": "2099-09-27",
            "kickoff": "13:00", "hit_prob": 0.56, "raw_prob": 0.58, "alt_lines": alts,
            "alt_sharp_lines": [], "price_age_s": age}


def _board(props, previous=None, now="2026-09-24T02:00:00Z"):
    real = K.rankable
    K.rankable = lambda m, s="nfl": True
    turn: dict = {}
    try:
        rows = K.build(props, sport="nfl", fits=FITS, previous=previous, now=now, turnover=turn)
    finally:
        K.rankable = real
    return rows, turn


def test_price_at_shops_the_number_across_bettable_books():
    row = _row(60.0, [_ln("DraftKings", 69.5, 180, -230), _ln("FanDuel", 69.5, 170, -205),
                      _ln("Pinnacle", 69.5, 190, -190), _ln("proxy", 69.5, 200, -150),
                      _ln("FanDuel", 70.5, 160, -180)])
    assert K._price_at(row, "under", 69.5) == (-205, "FanDuel")
    assert K._price_at(row, "under", 71.5) is None
    assert K._price_at(None, "under", 69.5) is None


def test_a_locked_pick_carries_todays_price_or_says_none_lists_it():
    posted = [_ln("Novig", 69.5, 300, -212)]
    b0, t0 = _board([_row(52.0, posted)], now="2026-09-23T20:00:00Z")
    (r0,) = b0
    assert (r0["side"], r0["line"]) == ("under", 69.5), r0
    assert r0["priced_at"] == "2026-09-23T19:50:00Z", "a fresh row carries its pull time"
    prev = {"rows": b0, "day": t0.get("day") or {}, "earlier": []}

    # The line has moved to 75.5 and one book still hangs 69.5.
    moved = [_ln("FanDuel", 69.5, 150, -190), _ln("DraftKings", 75.5, 110, -140)]
    b1, _ = _board([_row(90.0, moved, age=120)], previous=prev)
    (r1,) = [r for r in b1 if r.get("locked")]
    assert (r1["odds"], r1["line"]) == (r0["odds"], 69.5), "the posted price stays: it is graded"
    assert r1["priced_at"] == r0["priced_at"], "and keeps the time it was pulled"
    assert r1["now_listed"] is True and (r1["now_odds"], r1["now_book"]) == (-190, "FanDuel"), r1
    assert r1["now_priced_at"] == "2026-09-24T01:58:00Z"

    # Nobody hangs 69.5 any more.
    gone = [_ln("DraftKings", 75.5, 110, -140)]
    b2, _ = _board([_row(90.0, gone)], previous=prev)
    (r2,) = [r for r in b2 if r.get("locked")]
    assert r2["now_listed"] is False and r2["now_odds"] is None, r2


def test_the_card_and_the_row_say_the_price_now():
    assert "${likelyNowHTML(r)}" in _fn("likelyCard")
    assert "likelyNowHTML(r, true)" in _fn("likelyRow")
    assert "priceAgeS(r) > PRICE_FRESH_S" in _fn("likelyRow"), "an old price says so on the row"
    got = _node("""
      const at = new Date(Date.now() - 5 * 60000).toISOString();
      return {
        now: likelyNowHTML({ locked: true, now_listed: true, now_odds: -190, now_book: "FanDuel",
                             now_priced_at: at }),
        gone: likelyNowHTML({ locked: true, now_listed: false }),
        compact: likelyNowHTML({ locked: true, now_listed: true, now_odds: -190 }, true),
        fresh: likelyNowHTML({ now_listed: true, now_odds: -190 }),
        old: likelyNowHTML({ locked: true }),
      };""", "priceAgeS", "agoText", "likelyNowHTML", pre="var state={};")
    if got is None:
        return
    assert "Now -190 at FanDuel · priced 5m ago" in got["now"], got["now"]
    assert "No book lists this number right now" in got["gone"]
    assert got["compact"] == " · now -190"
    assert got["fresh"] == "" and got["old"] == "", "only a locked pick, and only once the build says"


# ── the model's inputs ────────────────────────────────────────────────────


def test_the_nfl_board_carries_its_week_check():
    assert 'result["data_freshness"] = _wk' in NFL


def test_the_page_names_every_table_behind():
    bar = _fn("renderStaleBar")
    assert bar.index("withholdAfterMs()") < bar.index("dataBehind(state.data)"), \
        "a late board outranks a late table"
    got = _node("""
      const d = { data_freshness: { season: 2026, played: 3,
        tables: { "results": 3, "player stats": 2, "snap counts": 3, "unit ratings": null },
        behind: ["player stats", "unit ratings"] } };
      const f = dataBehind(d);
      return { html: dataBehindHTML(f).replace(/<[^>]+>/g, ""),
               none: dataBehind({ data_freshness: { played: 3, behind: [] } }),
               preseason: dataBehind({ data_freshness: { played: null, behind: ["results"] } }) };
    """, "dataBehind", "dataBehindHTML",
                pre='const DATA_TABLE_WORDS = { "results": "final scores", "player stats": "player stats",'
                    ' "snap counts": "snap counts", "unit ratings": "matchup-scan team rankings" };')
    if got is None:
        return
    text = " ".join(got["html"].split())
    assert "Week 3 is played, but our data isn’t all in yet:" in text, text
    assert "player stats through week 2 · matchup-scan team rankings not in for this season" in text
    assert got["none"] is None and got["preseason"] is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
