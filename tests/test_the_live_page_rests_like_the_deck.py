"""v5: the Live page rests like the deck, and six crests share a row.

Ethan, 2026-09-22, on the phone strip: "it still kinda looks like the
same old website." Two things a phone shows most of the day:

- The Live page with nothing on. It opened with two sentences; it opens
  with the deck's quiet card now — the paused dot, one line that says
  no league is live, the sport in view's next start if the card holds
  one still ahead, the bets queued to ride when it comes — and the
  doors to the pages that are never empty, minus this one.
- The league strip. Five crests took the first row and UFC sat alone
  on a second, because the tablet rule gave each button 10px a side.
  The phone block after it narrows that to 4px: six crests, one row,
  the 44px crest still the tap target.
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
APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()
DECLS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


def _strip(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


def _fn(name):
    for head in (f"function {name}(", f"async function {name}("):
        if head in APP:
            i = APP.index(head); break
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
      {_const("LEAGUE_LABEL")}
      {_fn("deckFirstWord")}
      {_fn("formatKickoff")}
      const tzTime = (d) => d.toISOString();
      const liveTrackerRows = (rows) => rows;
      {_fn("firstStartOnCard")}
      {_fn("liveQuietLine")}
      let state = {{ sport: "nfl", data: null }};
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


def test_the_quiet_line_says_only_what_the_card_holds():
    got = _node("""
      const games = [{ away: "KC", home: "LAC", kickoff: "20:15", live: { state: "live" } },
                     { away: "GB", home: "CHI", kickoff: "13:00" }];
      const picks = [{ phase: "upcoming" }, { phase: "live" }];
      const out = {};
      state.data = { games, live_picks: picks, live_potd: [{ phase: "upcoming" }] }; out.full = liveQuietLine();
      state.data = null; out.nothing = liveQuietLine();
      state.data = { games: games.map((g) => ({ ...g, live: { state: "live" } })), live_picks: [{ phase: "live" }] }; out.allOn = liveQuietLine();
      state.sport = "mlb"; state.data = { games: [{ away: "NYY", home: "BOS", kickoff: "2026-09-23T23:10:00Z" }], live_picks: [{ phase: "upcoming" }] }; out.mlb = liveQuietLine();
      return out;""")
    if got is None:
        print("  SKIP node not installed"); return
    # The line under "No games live" (2026-10-28): what is next, one clause a fact.
    assert got["full"] == "NFL kickoff 1:00 PM ET · 2 bets queued", got["full"]
    assert got["nothing"] == "", "nothing ahead and nothing queued: no line at all"
    assert got["allOn"] == "", "every game begun, nothing queued"
    assert got["mlb"].startswith("MLB first pitch ") and got["mlb"].endswith(" · 1 bet queued"), got["mlb"]


def test_the_live_page_opens_quiet_with_the_decks_card_and_nothing_twice():
    """Ethan, 2026-10-28, the top of this tab circled: "fix how cluttered
    this is". The page's name alone, then "No games live" over the line of
    what is next, the feed's reason, and the karma card and your players
    under it; no second line under the name, and no doors to Picks and the
    Record, which the tab bar and the sidebar already are."""
    body = _fn("renderLiveBoard")
    quiet = body[body.index("if (!games.length) {"):body.index("const darkWhy")]
    card = ('<div class="hd-quiet lv-quiet lv-rest"><i class="live-dot paused"></i><span class="lv-rest-t"><b>No games live</b>${\n'
            '        next ? `<span>${escapeHtml(next)}</span>` : ""}</span></div>')
    assert card in quiet, "the deck's quiet card, said once"
    assert '<div class="section-title">Live now</div>\n      ' + card + '\n      ${why}<div class="yp-host"></div>`;\n    return;' in quiet, \
        "under the page's name; the feed's own reason, then the karma card and your players"
    for gone in ("boardEmptyDoors(", "bindEmptyDoors(", "every game in progress across the sports we model"):
        assert gone not in quiet, gone
    assert "every game in progress across the sports we model" not in body, "nor with games on"
    assert "No games in progress\n      right now" not in body, "the two sentences are gone"
    assert ".hd-quiet.lv-quiet { margin: 0 0 18px; }" in CSS and ".hd-quiet.lv-rest { margin-bottom: 12px; }" in CSS
    assert ".lv-rest ~ .yp-host { margin-bottom: 18px; }" in CSS


def test_six_crests_share_one_row_on_a_phone():
    tablet = DECLS.index(".sportbar-in .sport-btn { min-height: 44px; padding: 0 10px; }")
    phone = DECLS.index(".sportbar-in .sport-btn { padding: 0 4px; }")
    assert tablet < phone, "the phone's padding must come after the tablet's, or the tablet's wins"
    block = DECLS.rfind("@media (max-width: 760px) {", 0, phone)
    assert block != -1 and "@media" not in DECLS[block + 10:phone], "inside the phone block"
    crest = int(re.search(r"\.sportbar-in \.sport-btn \.crest \{ width: (\d+)px;", DECLS).group(1))
    side = int(re.search(r"\.sportbar-in \.sport-btn \{ padding: 0 (\d+)px; \}", DECLS).group(1))
    bar = int(re.search(r"\.sportbar-in \{ padding: 6px (\d+)px 2px; \}", DECLS).group(1))
    assert 6 * (crest + 2 * side) <= 360 - 2 * bar, "six crests no longer fit a 360 phone in one row"
    assert crest >= 44, "the crest is the tap target"


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
