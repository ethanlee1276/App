"""A price alert from Ask, and your starters on tonight's board (engine/alerts
the "price" shape; engine/feed's events carry the market; web/js/ask.js the
price card's Price alert; app.js ffStartersBoardHTML on the league desk).

Ethan, 2026-10-27: "make sure you do all the idea and inventions ... and
make sure its al pushed to the site." The last two of docs/IDEAS.md's
newest list:

  * A PRICE WATCH (Action Network's Line Watcher, Gambly's alerts): on Ask's
    price card the third button sets "Josh Allen under at -105 or better",
    started one notch better than the best price there is; it fires on the
    feed when a book gets there or the bet's line moves, on Alerts and the
    phone like any watch.
  * YOUR STARTERS ON TONIGHT'S BOARD (RotoBot): under the lineup on a linked
    league's desk, each starter with a pick tonight — our side, our chance,
    which board — for a member; a free account is told what membership adds
    and never which of its players have picks.

Run directly: `python3 tests/test_a_price_alert_and_your_starters.py`
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import feed as F                                   # noqa: E402

ASK_JS = (ROOT / "web" / "js" / "ask.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
ASK_CSS = (ROOT / "web" / "css" / "ask.css").read_text(encoding="utf-8")


def _node(src: str):
    out = subprocess.run(["node", "-e", src], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    return json.loads(out.stdout)


def _text(h: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", h).split())


# --- the price watch -----------------------------------------------------------------------
def test_the_feeds_events_name_their_market():
    row = {"player": "Josh Allen", "label": "Passing Yards", "market": "pass_yds", "team": "BUF", "opponent": "KC",
           "side": "UNDER", "line": 259.5, "book": "FanDuel", "odds": -110, "proj": 240.0, "ev": 0.02, "edge": 0.03,
           "rec": True, "priced": True, "velo": None}
    moved = dict(row, odds=-125)
    ev = F.diff({"k": row}, {"k": moved}, "nfl", "2026-10-27T18:00:00Z")
    assert ev and ev[0]["kind"] == "price_move" and ev[0]["market"] == "pass_yds", ev
    lk = F.likely_diff({"k": {**row, "p": 0.6, "odds": -150}}, {"k": {**row, "p": 0.6, "odds": -110}},
                       "nfl", "2026-10-27T18:00:00Z")
    assert lk and lk[0]["market"] == "pass_yds", lk


def test_the_price_card_sets_an_alert_one_notch_better():
    if not shutil.which("node"):
        return
    k = ASK_JS.index("/* AN ANSWER YOU CAN ACT ON")
    block = ASK_JS[k:ASK_JS.index("function askSlipCard(", k)]
    bet = {"sport": "nfl", "player": "Josh Allen", "side": "UNDER", "line": 259.5, "odds": -108, "book": "DraftKings",
           "market": "pass_yds", "market_label": "Passing Yards", "trackable": True}
    got = _node("""
const escapeHtml = (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");
const escapeAttr = escapeHtml;
const slugify = (x) => String(x || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
const surname = (x) => String(x || "").split(" ").slice(-1)[0];
const icon = (n) => `<i data-ic="${n}"></i>`;
const document = { addEventListener() {}, querySelectorAll() { return []; } };
const state = { sport: "nfl" };
const mbLoad = () => [];
const mbSave = () => {};
const slipHas = () => false;
const slipToggle = () => true;
const posted = [], toasts = [];
const tfToast = (t) => toasts.push(t);
const alertsFetch = () => Promise.resolve(null);
const alertsPost = (path, body) => { posted.push([path, body]);
  return Promise.resolve({ watches: [{ kind: "price", value: body.value, label: "x" }] }); };
let _alertsCache = { watches: [] };
""" + block + f"""
const b = {json.dumps(bet)};
const fresh = askActsHTML(b, "prices");
const hits = askActsHTML(b, "hits");
const notches = [-110, -102, -100, 120, 100].map(askNotchBetter);
const form = {{ querySelector: (sel) => sel === "[data-ask-target]" ? {{ value: "−105" }} : {{ textContent: "" }}, hidden: false }};
askActAlert(form, b).then(() => {{
  const done = askActsHTML(b, "prices");
  process.stdout.write(JSON.stringify({{ fresh, hits, notches, posted, toasts, done, hidden: form.hidden }}));
}});""")
    fresh = _text(got["fresh"])
    assert "Price alert" in fresh and "Watch" not in fresh, "on the price card the third button is the alert"
    assert 'data-ask-target value="−105"' in got["fresh"], "one notch better than the best price, −108"
    assert "When any book has it at that price or better, or its line moves" in fresh
    assert "Watch" in _text(got["hits"]) and "Price alert" not in _text(got["hits"]), "the hit card watches the player"
    assert got["notches"] == [-105, -100, 105, 125, 105], got["notches"]
    assert got["posted"] == [["watch", {"kind": "price", "value": "Josh Allen|pass_yds|UNDER|-105"}]], got["posted"]
    assert got["toasts"] == ["Alert set: Josh Allen under at −105 or better."] and got["hidden"] is True
    assert "Alert set" in _text(got["done"]) and got["done"].count(" disabled") == 1


def test_the_two_forms_are_told_apart_and_styled():
    assert '(form.classList.contains("ask-alert") ? askActAlert : askActTrack)(form, b);' in ASK_JS
    assert 'const form = box.querySelector(act === "track" ? ".ask-save" : ".ask-alert");' in ASK_JS
    for cls in (".ask-save", ".ask-alert"):
        assert cls in ASK_CSS, cls
    assert "askActsHTML(c.bet, c.kind)" in ASK_JS


# --- your starters on tonight's board ----------------------------------------------------------
STARTERS = [{"slot": "QB", "player": "Josh Allen"}, {"slot": "WR", "player": "Puka Nacua"},
            {"slot": "RB", "player": "Nobody Tonight"}, {"slot": "FLEX", "player": None}]
BOARD = {"most_likely": [{"player": "Josh Allen", "market": "pass_yds", "market_label": "Passing Yards",
                          "side": "UNDER", "line": 259.5, "model_prob": 0.58},
                         {"player": "Someone Else", "market": "rec", "side": "OVER", "line": 4.5, "model_prob": 0.7}],
         "recommendations": [{"player": "Puka Nacua", "market": "receptions", "market_label": "Receptions",
                              "side": "OVER", "line": 5.5, "hit_prob": 0.66, "recommended": True},
                             {"player": "Josh Allen", "market": "pass_yds", "side": "UNDER", "line": 259.5,
                              "hit_prob": 0.55, "recommended": True},
                             {"player": "Puka Nacua", "market": "rec_yds", "side": "OVER", "line": 70.5,
                              "hit_prob": 0.51, "recommended": False}]}


def test_your_starters_with_a_pick_tonight_for_a_member():
    if not shutil.which("node"):
        return
    fn = APP[APP.index("function ffStartersBoardHTML(starters) {"):]
    fn = fn[:fn.index("\n}\n") + 2]
    run = lambda pw, sport="nfl": _node(f"""
const escapeHtml = (x) => String(x == null ? "" : x).replace(/&/g, "&amp;").replace(/</g, "&lt;");
const escapeAttr = escapeHtml;
const icon = (n) => `<i data-ic="${{n}}"></i>`;
const propId = (r) => `${{r.player}}|${{r.market}}|${{r.side}}|${{r.line}}`;
const state = {{ sport: {json.dumps(sport)}, data: {json.dumps(BOARD)} }};
const _pwStatus = {json.dumps(pw)};
{fn}
process.stdout.write(JSON.stringify(ffStartersBoardHTML({json.dumps(STARTERS)})));""")  # noqa: E731
    member = run({"paywall": True, "entitled": True})
    rows = re.findall(r'<div class="hd-row ff-row"[^>]*>(.*?)</span></div>', member, re.S)
    assert len(rows) == 2, "each starter's pick once, the same bet on both boards counted once"
    assert "Josh Allen Under 259.5 Passing Yards 58% Most Likely" in _text(member)
    assert "Puka Nacua Over 5.5 Receptions 66% Edge" in _text(member)
    assert "Someone Else" not in member and "70.5" not in member, "only your starters, only recommended Edge picks"
    assert 'data-prop="Josh Allen|pass_yds|UNDER|259.5" data-likely="1"' in member, "a door to the pick"
    free = run({"paywall": True, "entitled": False})
    assert "Members see our pick on each of your starters tonight." in free
    assert "Josh Allen" not in free and "Puka" not in free and "2" not in _text(free), \
        "a free account is never told which of its players have picks, nor how many"
    assert run({"paywall": True, "entitled": True}, sport="nba") == "", "the NFL board only"
    assert "ffLineupHTML(d)\n    + ffStartersBoardHTML((d.lineup || {}).starters)" in APP, "under the lineup on the desk"


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
