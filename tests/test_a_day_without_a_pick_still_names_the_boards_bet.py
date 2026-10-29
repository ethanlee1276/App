"""A day the Pick of the Day sits out is not a day without a bet.

Ethan, 2026-10-29, after screenshots of the NBA card reading NO BET over a
board that staked 66 bets, to three proposals ("measure how often it says
NO BET; on those days show the best on the board tonight for members"):
"do all 3".

What is guarded:

  * the card names the BOARD'S OWN strongest staked bet still to play —
    never the lean the day's bar refused (tests/test_the_card_never_names_
    a_bet_it_refuses.py is the other half of that rule, and still holds);
  * it rides inside `pick_of_the_day`, so it is paid exactly as the card
    is, and the public copy carries none of it;
  * the record says how often the pick names one (`ledger.potd_days`),
    through yesterday and never today, and the card prints it;
  * the box can print the same count (`potd_report.py --sitout`).

    python3 tests/test_a_day_without_a_pick_still_names_the_boards_bet.py
"""

import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import gate, ledger, potd                         # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()


def _row(**kw):
    """A staked prop on today's slate, three hours from tip."""
    d, k = _kickoff(180)
    r = {"player": "Jalen Brunson", "team": "NYK", "market": "points",
         "market_label": "Points", "side": "Over", "line": 26.5,
         "odds": -115, "book": "FanDuel", "recommended": True,
         "stake_units": 1.5, "ev_per_unit": 0.06, "has_market": True,
         "headline": "Jalen Brunson Over 26.5 Points",
         "game_date": d, "kickoff": k}
    r.update(kw)
    return r


# --- the engine: which bet, and how many --------------------------------------
def test_the_strongest_staked_bet_still_to_play_is_named():
    board = {"recommendations": [
        _row(player="Small", stake_units=0.5, headline="Small Over 9.5 Points"),
        _row(),
        _row(player="Unstaked", recommended=False, stake_units=3.0),
        _row(player="Gone", stake_units=4.0, started=True),
        _row(player="Proxy", stake_units=4.0, book="proxy"),
        _row(player="Unpriced", stake_units=4.0, has_market=False),
    ]}
    best, n = potd.board_best(board)
    assert best["player"] == "Jalen Brunson" and best["label"] == "Jalen Brunson Over 26.5 Points"
    assert n == 2, "only staked, priced bets still to play are counted"
    assert best["tonight"] is True
    assert "recommended" not in best and "reasons" not in best, "the card carries what it prints"


def test_the_game_bets_count_and_read_in_words():
    board = {"game_bets": [
        {"market": "moneyline", "team": "BOS", "odds": 120, "book": "DraftKings",
         "recommended": True, "stake_units": 2.0, "ev_per_unit": 0.08,
         "game_date": _kickoff(180)[0], "kickoff": _kickoff(180)[1]}]}
    best, n = potd.board_best(board)
    assert n == 1 and best["label"] == "BOS Moneyline"
    assert potd._bet_words({"market": "spread", "team": "DAL", "side": "+3.5", "line": 3.5}) == "DAL +3.5 Spread"
    assert potd._bet_words({"market": "spread", "team": "DAL", "side": "", "line": -2.5}) == "DAL -2.5 Spread"
    assert potd._bet_words({"market": "total", "side": "under", "line": 221.5,
                            "home": "NYK", "away": "BOS"}) == "Under 221.5 · BOS @ NYK"


def test_a_board_with_nothing_staked_names_nothing():
    assert potd.board_best({"recommendations": [_row(recommended=False)]}) == (None, 0)
    assert potd.board_best({}) == (None, 0)


def _board_for_attach(staked=True):
    return {"sport": "nba", "date": _kickoff(180)[0], "most_likely": [],
            "recommendations": [_row()] if staked else []}


def test_a_no_bet_card_carries_the_boards_bet_and_a_bet_card_does_not():
    res = _board_for_attach()
    potd.attach(res, "nba", prev={})
    card = res["pick_of_the_day"]
    assert card["verdict"]["call"] == "no bet"
    assert card["board_best"]["label"] == "Jalen Brunson Over 26.5 Points"
    assert card["board_staked"] == 1
    empty = _board_for_attach(staked=False)
    potd.attach(empty, "nba", prev={})
    assert "board_best" not in empty["pick_of_the_day"], "nothing staked, nothing named"


def test_a_card_relocked_on_todays_pick_drops_the_boards_bet():
    card = {"pick": None, "board_best": {"label": "x"}, "board_staked": 3}
    pick = {"player": "BOS", "team": "BOS", "market": "moneyline", "side": "",
            "line": 0, "odds": -110, "book": "DraftKings"}
    out = potd.relock(card, [], None, journal_pick=None)
    assert out.get("board_best"), "no lock, nothing moves"
    key = ledger.potd_row_key(pick)
    out = potd.relock(card, [], key, journal_pick=pick)
    assert "board_best" not in out and "board_staked" not in out


def test_the_boards_bet_is_paid_with_the_card():
    res = _board_for_attach()
    potd.attach(res, "nba", prev={})
    public = gate.redact(res, "nba.json")
    assert public["pick_of_the_day"] == {}
    assert "Jalen Brunson" not in json.dumps(public), "the public copy names the bet"


# --- the ledger: how often it names one -----------------------------------------
def _conn():
    return ledger.connect(os.path.join(tempfile.mkdtemp(), "l.db"))


def _bet(conn, sport, day, category, player="P"):
    conn.execute(
        "INSERT INTO bets (ts, sport, date, player, market, side, line, odds, "
        "stake_units, category, game_day, status) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'open')",
        (day + "T12:00:00", sport, day, f"{player}{category}", "points", "OVER", 1.5,
         -110, 1.0, category, day))


def test_the_count_is_slates_with_a_pick_through_yesterday():
    conn = _conn()
    today = dt.date(2026, 10, 29)
    for back in range(1, 6):                      # five NBA slates, picks on two
        day = (today - dt.timedelta(days=back)).isoformat()
        _bet(conn, "nba", day, "likely")
        if back in (1, 3):
            _bet(conn, "nba", day, "potd")
    _bet(conn, "nba", today.isoformat(), "potd")  # today: never counted
    _bet(conn, "nba", "2026-09-01", "potd")       # outside the window
    _bet(conn, "wnba", "2026-10-27", "likely")    # benched: left out
    conn.commit()
    got = ledger.potd_days(conn, today="2026-10-29")
    assert got["through"] == "2026-10-28" and got["days"] == 28
    assert got["by_sport"] == {"nba": {"slates": 5, "picked": 2}}
    assert (got["slates"], got["picked"]) == (5, 2)


def test_an_nfl_slate_counts_only_on_a_pick_day():
    conn = _conn()
    _bet(conn, "nfl", "2026-10-25", "main")       # Sunday: a pick day
    _bet(conn, "nfl", "2026-10-25", "potd")
    _bet(conn, "nfl", "2026-10-24", "main")       # Saturday: never a pick day
    conn.commit()
    days = potd.PICK_WEEKDAYS
    try:
        potd.PICK_WEEKDAYS = {"nfl": (0, 3, 6)}
        got = ledger.potd_days(conn, today="2026-10-29")
    finally:
        potd.PICK_WEEKDAYS = days
    assert got["by_sport"]["nfl"] == {"slates": 1, "picked": 1}


def test_the_record_carries_the_count_and_never_breaks_for_it():
    src = (ROOT / "engine" / "ledger.py").read_text()
    assert '"potd_days": _potd_days_or_empty(conn),' in src
    assert "potd_days" not in ledger.RECORD_PAGE_ONLY, "the home card reads it off the slim copy"


# --- the box: the same count, printed --------------------------------------------
def test_the_report_prints_the_sitout_table():
    import potd_report as R
    path = os.path.join(tempfile.mkdtemp(), "l.db")
    conn = ledger.connect(path)
    yday = (dt.date.fromisoformat(potd.slate_day()) - dt.timedelta(days=1)).isoformat()
    _bet(conn, "nba", yday, "likely")
    _bet(conn, "nba", yday, "potd")
    conn.commit()
    conn.close()
    old = ledger.DEFAULT_DB
    ledger.DEFAULT_DB = path
    try:
        out = io.StringIO()
        with redirect_stdout(out):
            assert R.main(["--sitout"]) == 0
    finally:
        ledger.DEFAULT_DB = old
    text = out.getvalue()
    assert "NBA" in text and "1 of   1 slates" in text and "100% named a pick" in text, text


def test_the_report_names_the_boards_bet_under_no_bet():
    import potd_report as R
    lines = R._published_call({"pick_of_the_day": {
        "verdict": {"call": "no bet", "why": "nothing cleared the bar"},
        "board_best": {"label": "Jalen Brunson Over 26.5 Points", "odds": -115,
                       "book": "FanDuel", "stake_units": 1.5}, "board_staked": 66}})
    assert any("BOARD BEST" in ln and "Jalen Brunson" in ln and "66 staked" in ln for ln in lines), lines


# --- the page: the card a member reads ---------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[max(0, i - 6):i] == "async ":
        i -= 6
    return APP[i:APP.index("\n}\n", i) + 3]


def render(card, record=None):
    js = f"""
    const MINUS = "\\u2212";
    const SPORT_META = {{ nba: {{ name: "NBA" }} }};
    const state = {{ sport: "nba", view: "recommended", data: {{ pick_of_the_day: {json.dumps(card)} }} }};
    {_fn("escapeHtml")}
    const escapeAttr = escapeHtml;
    const icon = () => "", iconMark = () => "";
    const american = (o) => (o > 0 ? `+${{o}}` : `\\u2212${{Math.abs(o)}}`);
    const teamName = (t) => String(t || ""), betMark = () => "", betItHTML = () => "";
    const ridingAttrs = (b) => ` data-door="${{b.label}}"`;
    const liveTrackerRows = (r) => r;
    const VENUE_FAMILY = {{}}, activeTeams = () => ({{}}), venueSrc = (s) => s, venueVariant = () => "";
    {_fn("pluralWord")}
    {_fn("plural")}
    {_fn("absoluteSrc")}
    {_fn("potdLiveRow")}
    {_fn("potdLiveStrip")}
    {_fn("potdCallStrip")}
    {APP[APP.index("const POTD_BALL = "):APP.index(chr(10), APP.index("const POTD_BALL = "))]}
    {_fn("potdBallArt")}
    {_fn("potdVenueArt")}
    async function loadTopPickOnce() {{ return {{}}; }}
    async function loadRecordOnce() {{ return {json.dumps(record or {})}; }}
    const _els = {{}};
    const document = {{ getElementById: (id) => _els[id] || null }};
    for (const id of ["potd-zone", "potd-top-pick", "potd-record"]) {{
      _els[id] = {{ innerHTML: "", textContent: "", querySelector: () => null }};
    }}
    {_fn("renderDayTopPick")}
    {_fn("renderPickOfTheDay")}
    renderPickOfTheDay().then(() => new Promise((r) => setTimeout(r, 5))).then(() => console.log(JSON.stringify(
      [_els["potd-zone"].innerHTML, _els["potd-record"].innerHTML || _els["potd-record"].textContent])));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


LEAN = {"below_bar": "the gap is too big to trust", "market": "moneyline",
        "player": "LAD", "team": "LAD", "odds": -130, "book": "DraftKings"}
BEST = {"label": "Jalen Brunson Over 26.5 Points", "player": "Jalen Brunson",
        "market": "points", "side": "Over", "line": 26.5, "odds": -115,
        "book": "FanDuel", "stake_units": 1.5, "tonight": True}


def _card(**kw):
    c = {"band": [-250, 190], "pick": LEAN,
         "verdict": {"call": "no bet", "stake": 0.0, "why": LEAN["below_bar"]}}
    c.update(kw)
    return c


def test_a_member_meets_the_boards_bet_and_not_the_lean():
    card, _ = render(_card(board_best=BEST, board_staked=66))
    assert "NO PICK TODAY" in card and "NO BET" not in card, card
    for thing in ("Best on the board tonight", "Jalen Brunson Over 26.5 Points",
                  "−115", "at FanDuel", "1.5u", "one of 66 staked", 'data-door="'):
        assert thing in card, f"{thing!r} missing:\n{card}"
    for thing in ("LAD", "DraftKings", "130"):
        assert thing not in card, f"the refused lean is named: {thing!r}\n{card}"


def test_a_day_with_nothing_staked_still_reads_no_bet():
    card, _ = render(_card())
    assert "NO BET" in card and "Best on the board" not in card, card


def test_not_tonight_is_not_called_tonight():
    card, _ = render(_card(board_best=dict(BEST, tonight=False), board_staked=1))
    assert "Best on the board:" in card and "tonight" not in card.split("Best on the board")[1][:12]
    assert "one of" not in card, "one bet is not one of one"


def test_the_card_says_how_often_the_pick_names_one():
    rec = {"potd_by_sport": {"nba": {"settled": 5, "wins": 3, "losses": 2, "net_units": 0.85,
                                     "win_rate": 0.6}},
           "potd_days": {"by_sport": {"nba": {"slates": 9, "picked": 5}}}}
    _, line = render(_card(board_best=BEST, board_staked=66), record=rec)
    assert "3-2" in line and "a pick on 5 of the last 9 slates" in line, line


def test_the_record_page_prints_the_count_for_everyone():
    rec = (ROOT / "web" / "js" / "record.js").read_text()
    i = rec.index("function recPotdSection(")
    fn = rec[i:rec.index("\n}\n", i) + 3]
    js = f"""
    const POTD_MIN_N = 20, MINUS = "\\u2212";
    const SPORT_META = {{ nba: {{ name: "NBA" }} }};
    const escapeHtml = (s) => String(s == null ? "" : s), icon = () => "", american = (o) => String(o);
    {_fn("pluralWord")}
    {_fn("plural")}
    {fn}
    const sit = {{ slates: 27, picked: 23, by_sport: {{ nba: {{ slates: 9, picked: 5 }} }} }};
    const rep = {{ settled: 5, wins: 3, losses: 2, net_units: 0.85, win_rate: 0.6 }};
    console.log(JSON.stringify([recPotdSection(rep, "nba", [], sit), recPotdSection(rep, "", [], sit),
                                recPotdSection(rep, "nfl", [], sit), recPotdSection(rep, "nba", [])]));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    league, every, other, none = json.loads(out.stdout)
    assert "A pick on 5 of the last 9 slates" in league
    assert "at least one league on 23 of the last 27 days" in every
    assert "A pick on" not in other and "A pick on" not in none, "no count, no line"
    assert "recPotdSection(scoped ? (d.potd_by_sport || {})[scope] : d.potd,\n                     scope, d.potd_recent || [], d.potd_days)" in rec

if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
