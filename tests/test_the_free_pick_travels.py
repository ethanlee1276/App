"""Today's free pick travels: on the sign-up screen and the plans, with how it
went once graded, and as a picture to share.

Ethan, 2026-11-03, on the 30 October audit's list — "the free Pick of the
Day travels: ... the pick on the sign-up screen and the plans page, and a
share card (like the karma card): pick, price, result once settled" — "do
all of them". (Its alert is tests/test_the_free_pick_alert.py.) What these
hold:

  * the first-look feed the sign-up and the plans read carries today's free
    pick — the public file's, dated today, on a day it is a bet, never a
    lean, paywall on or off — with the Pick of the Day's own record;
  * the sign-up screen draws it above the members' locked cards and the
    plans draw it with the door to every league's; a day with none draws
    nothing;
  * a graded Pick of the Day says so on its card in the day's file — matched
    to its journal row by the lock's own key, the day's first row — and the
    page shows Won / Lost with the units, and stops offering to bet it;
  * the Share card draws the site's own pick card: who, the bet, the price at
    the book, the fair and the price's chance, then the result once graded,
    or the league's record before.

Run directly: `python3 tests/test_the_free_pick_travels.py`
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import firstlook                                     # noqa: E402

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text(encoding="utf-8")
ACCOUNT = (WEB / "js" / "account.js").read_text(encoding="utf-8")
PAGE = (WEB / "js" / "potd.js").read_text(encoding="utf-8")
TODAY = dt.date(2026, 11, 3)
PROP = {"player": "Jalen Brunson", "team": "NYK", "opponent": "BOS", "market": "points", "market_label": "Points",
        "side": "over", "line": 24.5, "odds": -110, "book": "FanDuel", "fair_prob": 0.574, "evidence": "sharp",
        "price_implied": 0.524, "payout_units": 0.91, "headshot": "https://a.espncdn.com/x.png",
        "reasons": ["a member's reasoning, never on this screen"], "sport": "nba"}


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _web(top=None, rec=None):
    web = Path(tempfile.mkdtemp())
    (web / "data").mkdir()
    if top is not None:
        (web / "data" / "day_top_pick.json").write_text(json.dumps(top), encoding="utf-8")
    if rec is not None:
        (web / "data" / "record.json").write_text(json.dumps(rec), encoding="utf-8")
    return web


def _top(**kw):
    out = {"date": TODAY.isoformat(), "sport": "nba", "pick": dict(PROP),
           "verdict": {"call": "bet", "stake": 1.0, "why": ""}, "runners_up": [], "leagues": {}}
    out.update(kw)
    return out


REC = {"potd": {"wins": 31, "losses": 22, "pushes": 1, "net_units": 6.42, "settled": 54}}


# --- the feed ----------------------------------------------------------------------
def test_the_feed_carries_todays_free_pick_and_its_record():
    got = firstlook.free_pick(_web(_top(), REC), TODAY)
    assert got["player"] == "Jalen Brunson" and got["odds"] == -110 and got["book"] == "FanDuel"
    assert got["sport"] == "nba" and got["record"] == {"w": 31, "l": 22, "p": 1, "units": 6.4}
    assert set(got) <= set(firstlook.FREE_PICK_FIELDS) | {"record"}, "the words and the price, nothing more"
    assert "reasons" not in got


def test_a_lean_yesterday_or_nothing_is_never_shown():
    lean = _top(pick=dict(PROP, below_bar="no league cleared the bar"), verdict={"call": "no bet"})
    assert firstlook.free_pick(_web(lean, REC), TODAY) is None, "paywall off, the full file: still no lean"
    assert firstlook.free_pick(_web(_top(), REC), TODAY + dt.timedelta(days=1)) is None, "yesterday's"
    assert firstlook.free_pick(_web(None), TODAY) is None
    assert firstlook.free_pick(_web(_top(pick=None, sport="")), TODAY) is None
    no_rec = firstlook.free_pick(_web(_top(), {"potd": {"settled": 0}}), TODAY)
    assert no_rec and "record" not in no_rec


# --- a graded pick says so -----------------------------------------------------------
def _ledger_with(rows):
    from engine import ledger as L
    tmp = Path(tempfile.mkdtemp())
    old = L.DEFAULT_DB
    L.DEFAULT_DB = tmp / "ledger.db"
    try:
        with L.connect() as conn:
            for r in rows:
                conn.execute("INSERT INTO bets (ts, sport, date, player, market, side, line, odds, status, "
                             "pnl_units, category) VALUES (?,?,?,?,?,?,?,?,?,?,?)", r)
            conn.commit()
            return L.potd_results(conn, TODAY.isoformat())
    finally:
        L.DEFAULT_DB = old


def test_the_days_first_row_is_its_result_and_only_once_graded():
    day = TODAY.isoformat()
    res = _ledger_with([
        (day + "T09:00:00", "nba", day, "Jalen Brunson", "points", "OVER", 24.5, -110, "won", 0.91, "potd"),
        (day + "T10:00:00", "nba", day, "Someone Later", "points", "OVER", 20.5, -110, "lost", -1.0, "potd"),
        (day + "T09:00:00", "nfl", day, "KC", "moneyline", "OVER", 0.5, -130, "open", 0.0, "potd"),
        (day + "T09:00:00", "nhl", day, "Not the pick", "shots", "OVER", 2.5, -110, "won", 0.9, "edge"),
    ])
    assert res == {"nba": {"status": "won", "units": 0.91, "_key": ("Jalen Brunson", "points", "OVER", 24.5)}}, res


def test_a_card_wears_its_result_when_its_pick_is_the_row():
    import launch
    from engine import ledger as L
    key = L.potd_row_key(PROP)
    top = {"sport": "nba", "pick": dict(PROP), "leagues": {
        "nba": {"pick": dict(PROP)},
        "nhl": {"pick": {"player": "Other Player", "market": "shots", "side": "over", "line": 2.5}}}}
    launch._attach_potd_results(top, {"nba": {"status": "lost", "units": -1.0, "_key": tuple(key)},
                                      "nhl": {"status": "won", "units": 0.9, "_key": ("Moved On", "shots", "OVER", 2.5)}})
    assert top["leagues"]["nba"]["result"] == {"status": "lost", "units": -1.0}
    assert top["result"] == {"status": "lost", "units": -1.0}, "the day's top pick too"
    assert "result" not in top["leagues"]["nhl"], "a card showing another pick than its row says nothing"
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    body = src[src.index("def _write_day_top_pick"):src.index("def _attach_potd_results")]
    assert "_attach_potd_results(top, ledger.potd_results(lconn, today))" in body
    assert body.index("_attach_potd_results(") < body.index('_gate.publish(top, web / "day_top_pick.json"')
    from engine import gate
    assert "result" not in gate.POTD_MEMBERS_ONLY, "how it went is the record's, and free"


# --- on the page --------------------------------------------------------------------
STUBS = """
const state = { sport: "nba", view: "potd" };
const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const escapeAttr = escapeHtml;
const icon = () => "", iconMark = () => "", leagueMark = () => "", playerAvatar = () => "";
const teamNameIn = (sp, t) => ({ NYK: "Knicks", BOS: "Celtics", KC: "Chiefs", BUF: "Bills" })[t] || t;
const teamMarkIn = (sp, t) => "";
const american = (o) => (o > 0 ? "+" + o : String(o).replace("-", "−"));
const settings = () => ({ odds: "american" });
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const MINUS = "−";
const SPORT_META = { nba: { name: "NBA" }, nfl: { name: "NFL" } };
const LEAGUE_LABEL = {};
const betItHTML = () => `<span class="betit-box">Bet it</span>`;
const memberLockHTML = (t) => `<div class="member-lock">${t}</div>`;
const tzTime = () => "3:00 PM";
const pushKind = () => "";
const document = { createElement: () => ({ set innerHTML(v) { this.value = String(v).replace(/&lt;/g, "<").replace(/&amp;/g, "&"); } }) };
"""


def _node(js):
    out = subprocess.run(["node", "-e", STUBS + js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def _account_fn(name):
    return _fn(name, ACCOUNT)


def test_the_signup_and_the_plans_draw_it():
    fl = {"free_pick": dict({k: v for k, v in PROP.items() if k in firstlook.FREE_PICK_FIELDS},
                            record={"w": 31, "l": 22, "p": 1, "units": 6.4})}
    js = (_fn("potdBetText") + ACCOUNT[ACCOUNT.index("const FL_WITNESS"):ACCOUNT.index("function flRecordHTML(")]
          + f"console.log(JSON.stringify([flFreeHTML({json.dumps(fl)}), flFreeHTML({json.dumps(fl)}, true),"
          + " flFreeHTML({}), flFreeHTML(null)]));")
    signup, plans, none, cold = _node(js)
    assert "Free today" in signup and "Jalen Brunson OVER 24.5 Points" in signup
    assert "−110 at FanDuel" in signup and "Knicks vs Celtics" in signup
    assert "<b>57%</b> the sharp book’s fair · the price implies 52%" in signup
    assert "<b>31–22–1</b>" in signup and "+6.4u" in signup and 'href="#potd"' not in signup
    assert 'href="#potd"' in plans, "the plans are reached from inside the site: the door to every league's"
    assert none == "" and cold == ""
    su = _account_fn("signupHTML")
    assert su.index('<div class="fl-free-host">${flFreeHTML(_fl)}</div>') < su.index('<div class="fl-host">'), \
        "above the members' locked cards"
    assert "if (f && fl) f.innerHTML = flFreeHTML(fl);" in _account_fn("flPaint")
    assert 'if (free && fl) free.innerHTML = flFreeHTML(fl, true);' in _account_fn("pwTonight")
    assert '<div class="pw-free"></div><div class="pw-fl"></div>' in ACCOUNT


def _card(result=None, pick=None):
    c = {"sport": "nba", "date": TODAY.isoformat(), "pick": dict(pick or PROP),
         "verdict": {"call": "bet", "stake": 1.0, "why": ""}}
    if result:
        c["result"] = result
    return c


def test_a_graded_card_says_how_it_went_and_stops_offering_the_bet():
    js = ("function potdCallStrip() { return ''; }\n" + _fn("potdBetText") + _fn("oddsTxt") + PAGE
          + f"const ctx = {{ rec: {{}}, locked: {{}}, walled: true, topSport: 'nba' }};"
          + f"console.log(JSON.stringify([pdCardHTML('nba', {json.dumps(_card())}, ctx),"
          + f" pdCardHTML('nba', {json.dumps(_card({'status': 'won', 'units': 0.91}))}, ctx),"
          + f" pdCardHTML('nba', {json.dumps(_card({'status': 'lost', 'units': -1.0}))}, ctx)]));")
    open_, won, lost = _node(js)
    assert "Bet it" in open_ and "Share card" in open_ and "pd-res" not in open_
    assert '<span class="pd-res won">Won +0.91u</span>' in won and "Bet it" not in won and "Share card" in won
    assert '<span class="pd-res lost">Lost −1.00u</span>' in lost
    assert "pdShareWire(host, top || {}, rec);" in PAGE


def test_the_share_card_says_who_the_bet_the_price_and_how_it_went():
    rec = {"potd_by_sport": {"nba": {"wins": 5, "losses": 2, "settled": 7}}}
    ml = {"player": "KC", "team": "KC", "opponent": "BUF", "market": "moneyline", "side": "", "line": None,
          "odds": -130, "book": "DraftKings", "fair_prob": 0.6, "evidence": "model", "price_implied": 0.57}
    js = (_fn("potdBetText") + _fn("oddsTxt") + PAGE
          + f"console.log(JSON.stringify([pdShareData({json.dumps(_card())}, 'nba', {json.dumps(rec)}),"
          + f" pdShareData({json.dumps(_card({'status': 'won', 'units': 0.91}))}, 'nba', {json.dumps(rec)}),"
          + f" pdShareData({json.dumps(dict(_card(pick=ml), sport='nfl'))}, 'nfl', {{}})]));")
    prop, graded, team = _node(js)
    assert prop["title"] == "Jalen Brunson" and prop["pick"] == "OVER 24.5 Points", prop
    assert prop["sub"] == "NBA · Pick of the Day · Nov 3" and prop["odds"] == "-110 · FanDuel"
    assert prop["facts"] == [["Fair", "57%"], ["Implied", "52%"], ["Record", "5–2"]], prop["facts"]
    assert prop["headshot"] and not prop["initials"]
    assert graded["facts"][-1] == ["Result", "Won +0.91u", "good"], "how it went, in place of the record"
    assert team["title"] == "Chiefs" and team["pick"] == "Moneyline" and team["initials"] == "KC"
    assert team["facts"] == [["Implied", "57%"]], "our own number never leads: a model-only fair is not drawn"
    assert not team["headshot"]
    canvas = _fn("shareCardCanvas")
    assert "const initials = d.initials ||" in canvas
    assert '(d.facts || [["Model", d.proj], ["Hit", d.hit], ["Edge", d.edge]])' in canvas
    assert 'tone === "good" ? CARD_GOOD : tone === "bad" ? CARD_BAD' in canvas
    share = _fn("pdShare", PAGE)
    assert "await shareCardCanvas(d)" in share and "exportCard(canvas, `pick-of-the-day-${sport}-qellysbook.png`" in share


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
