"""The phone home leads with what is live.

Ethan, 2026-09-22, choosing the home screen's job for the redesign:
"Live first." The Figma mock he approved orders the phone home Live now
→ Riding → Tonight's picks → The record → Zeno's picks. This pins that
order, the rules that keep every printed number an earned one, and the
one cost rule — the strip reads the fast scoreboards, never the boards.
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

HTML = (ROOT / "web" / "index.html").read_text()
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head)
            break
    else:
        raise AssertionError(f"no function {name}")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return _strip(APP[i:min(ends)])


def _const(name):
    i = APP.index(f"const {name} = ")
    return APP[i:APP.index(";\n", i) + 1]


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    prog = f"""
      {_const("HOME_DECK_ORDER")}
      {_fn("deckLiveGames")}
      {_fn("deckRidingRows")}
      {_fn("deckFirstWord")}
      {_fn("deckQuietLine")}
      {_fn("deckStateWord")}
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


def test_the_deck_is_the_first_thing_on_the_home_view_and_phones_only():
    view = HTML[HTML.index('id="view-recommended"'):]
    view = re.sub(r"<!--.*?-->", "", view, flags=re.S)
    first = re.search(r"<(div|section|p|h\d)\b[^>]*>", view[view.index(">") + 1:])
    assert first and 'id="home-deck"' in first.group(0), first.group(0) if first else None
    assert '<div id="home-deck" hidden></div>' in view
    assert "#home-deck { display: none; }" in CSS
    phone = CSS[CSS.index("@media (max-width: 760px) {", CSS.index(".tabbar { display: none; }")):]
    assert "#home-deck { display: block;" in phone
    assert "#home-deck[hidden] { display: none; }" in phone
    home = _fn("renderRecommended")
    assert "renderHomeDeck();" in home[:300], "drawn before the zones below it"
    deck = _fn("renderHomeDeck")
    assert 'if (!isPhone()) { host.hidden = true; host.innerHTML = ""; return; }' in deck


def test_the_order_is_live_riding_tonight_record_zeno():
    got = _node("return HOME_DECK_ORDER;")
    if got is None:
        print("  SKIP node not installed"); return
    assert got == ["live", "riding", "tonight", "record", "zeno"], got
    deck = _fn("renderHomeDeck")
    assert 'host.innerHTML = HOME_DECK_ORDER.map((k) => sections[k] || "").join("");' in deck
    assert "host.hidden = !host.innerHTML.trim();" in deck, "five empty sections is no deck at all"
    for k in ("live", "riding", "tonight", "record", "zeno"):
        assert f'data-sec="{k}"' in APP, k


def test_live_games_only_ours_first_and_the_quiet_night_says_what_it_knows():
    got = _node("""
      const g = (a, h, st) => ({ away: a, home: h, live: { state: st } });
      const list = [{ sport: "nfl", g: g("KC", "LAC", "live") }, { sport: "mlb", g: g("NYY", "BOS", "final") },
                    { sport: "nfl", g: g("GB", "CHI", "live") }, { sport: "mlb", g: g("LAD", "SF", "live") },
                    { sport: "nfl", g: g("SEA", "SF", "scheduled") }];
      const riding = [{ phase: "live", game: { away: "GB", home: "CHI" } }, { phase: "live", game: { away: "GB", home: "CHI" } },
                      { phase: "live", game: { away: "LAD", home: "SF" } }];
      const live = deckLiveGames(list, riding, "nfl");
      const rows = deckRidingRows([{ phase: "live", a: 1 }, { phase: "upcoming" }, { phase: "final" }, { phase: "live", a: 2 }]);
      return { live: live.map((x) => [x.sport, x.g.away, x.riding]), rows: rows.map((r) => r.a),
               quietFull: deckQuietLine({ league: "MLB", sport: "mlb", first: "7:05 PM ET", queued: 3 }),
               quietOne: deckQuietLine({ league: "NFL", sport: "nfl", first: "", queued: 1 }),
               quietBare: deckQuietLine({ league: "NBA", sport: "nba", first: "", queued: 0 }),
               tip: deckFirstWord("wnba"), ufc: deckFirstWord("ufc"), cfb: deckFirstWord("cfb"),
               words: ["cleared", "won_pending", "busted", "lost_pending", "dead", "push_pending", "live", undefined]
                 .map((s) => deckStateWord({ status: s })) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["live"] == [["nfl", "GB", 2], ["nfl", "KC", 0], ["mlb", "LAD", 0]], got["live"]
    assert got["rows"] == [1, 2]
    assert got["quietFull"] == "No MLB games live. First pitch 7:05 PM ET. 3 bets queued."
    assert got["quietOne"] == "No NFL games live. 1 bet queued."
    assert got["quietBare"] == "No NBA games live."
    assert got["tip"] == "Tip-off" and got["ufc"] == "First bout" and got["cfb"] == "Kickoff"
    assert got["words"] == [["Won", "good"], ["Won", "good"], ["Gone", "bad"], ["Gone", "bad"],
                            ["Gone", "bad"], ["Push", ""], ["Tracking", ""], ["Tracking", ""]]


def test_the_strip_reads_the_fast_scoreboards_never_the_boards():
    fast = _fn("fetchFastLiveAll")
    assert "Object.entries(LIVE_FAST)" in fast
    assert "LIVE_FEEDS" not in fast, "the boards are megabytes; the strip shows scores"
    assert 'boardFetch(url, { cache: "no-store" })' in fast
    live = _fn("deckLiveHTML")
    assert "await fetchFastLiveAll()" in live
    assert "deckLiveGames(fast, riding, state.sport)" in live
    assert 'filter((r) => r.phase === "upcoming").length' in live, "queued = journaled and not started"
    game = _fn("deckGameHTML")
    assert "liveHoldWord(lv)" in game and 'live-dot${hold ? " paused" : ""}' in game, \
        "a delayed game says so on the home too"
    arm = _fn("armDeckLive")
    assert "if (now !== _deckStamp) { renderHomeDeck(); return; }" in arm, "redraw only when a score moved"


def test_every_printed_number_is_an_earned_one():
    rec = _fn("deckRecordHTML")
    assert "if (ov.settled) {" in rec and "if (zo.settled) {" in rec, "no tile over nothing"
    assert "rec.overall || {}" in rec and "rec.zeno || {}" in rec
    assert "zenoTicketRow(r, false)" in rec, "Zeno's open tickets are the record page's own rows"
    tonight = _fn("deckTonightHTML")
    assert 'String(call) === "bet"' in tonight, "a NO BET day has no Pick of the Day hero"
    assert ".filter(showableLikelyRow)" in tonight, "the board's own gate"
    assert 'if (!showPotd && !likely.length) return "";' in tonight
    row = _fn("deckPickRow")
    assert "isFinite(p) && p > 0 && p < 1" in row, "a certainty is not a forecast"
    riding = _fn("deckRidingHTML")
    assert "trackerBetText(r)" in riding, "the Live tab's sentence, not a second one"
    assert 'r.market !== "moneyline"' in riding, "a moneyline has no progress to show"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
