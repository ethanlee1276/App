"""Football and baseball get the basketball page's scoreboard.

Ethan, 2026-10-27, two screenshots, the NBA game page's scoreboard circled
beside the NFL one: "The background and shit looks so good compared too the
nfl one. We want all of these too look like nba for all sports." Hockey had
it already (js/rinkcast.js); football (NFL, college) and baseball drew a
plain card. js/detail.js pbpBoardHTML now draws the same board for them.
What these hold:

  - each club's own colour washes in from its own edge: a colour too dark
    to read on the card is lifted, same hue (the Cowboys' navy, the Eagles'
    green), black gives way to the club's next colour, the away side takes
    another of its colours when the two would look alike, and a club with
    no colours is grey, never the site's gold;
  - each side is its crest, its city over its nickname (a college: its
    mascot over its school), its record, and its score, with the ball
    beside the side that has it: football's drive, baseball's half;
  - the middle says where the game is in that sport: the quarter, the clock
    and the down; the inning, the runners, the outs and the count; "Final"
    (with OT or F/10); "Kickoff" / "First pitch"; and a hold reads as one,
    its word, where play stopped and why, never as Live;
  - live, the Watch row is under the board; before and after, the carrier;
  - a college game opened from an alert, with no college table yet, reads
    the college board once for its crests, colours and schools.

    python3 tests/test_every_sport_gets_the_basketball_scoreboard.py
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DETAIL = open(os.path.join(ROOT, "web", "js", "detail.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "detail.css"), encoding="utf-8").read()
BLOCK = DETAIL[DETAIL.index("const PBP_READS"):DETAIL.index("async function renderPbpPage(")]

STUBS = r"""
const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const icon = (n) => `<i data-icon="${n}"></i>`;
const miniDiamond = (b) => `<svg class="lb-diamond" data-bases="${(b || []).join(",")}"></svg>`;
const liveHoldWord = (lv) => ((lv || {}).hold ? String(lv.hold) : "");
const pbpOrd = (n) => n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
const pbpTime = (iso) => (iso ? "7:15 PM" : "");
const pbpAgo = (s) => (s ? "updated 5s ago" : "");
const teamMarkIn = (lg, a, size) => `<span class="team-mark-wrap" data-a="${a}" data-size="${size}"></span>`;
let _cfbTeams = null;
const TABLES = {
  nfl: { DAL: { name: "Dallas Cowboys", nick: "Cowboys", loc: "Dallas", primary: "#002244", secondary: "#b0b7bc", tertiary: "#acc0c6" },
         PHI: { name: "Philadelphia Eagles", nick: "Eagles", loc: "Philadelphia", primary: "#004953", secondary: "#a5acaf", tertiary: "#acc0c6" },
         CIN: { name: "Cincinnati Bengals", nick: "Bengals", loc: "Cincinnati", primary: "#000000", secondary: "#fb4f14", tertiary: "" },
         CLE: { name: "Cleveland Browns", nick: "Browns", loc: "Cleveland", primary: "#fb4f14", secondary: "#a5acaf", tertiary: "" },
         NYJ: { name: "New York Jets", nick: "Jets", loc: "NY Jets", primary: "#203731", secondary: "#1c2d25", tertiary: "" },
         TB: { name: "Tampa Bay Buccaneers", nick: "Buccaneers", loc: "Tampa Bay", primary: "#d50a0a", secondary: "#34302b", tertiary: "" },
         ARI: { name: "Arizona Cardinals", nick: "Cardinals", loc: "Arizona", primary: "#97233f", secondary: "#000000", tertiary: "#ffb612" } },
  mlb: { BOS: { name: "Boston Red Sox", nick: "Red Sox", loc: "Boston", primary: "#bd3039", secondary: "#0c2340", tertiary: "#ffffff" },
         NYY: { name: "New York Yankees", nick: "Yankees", loc: "New York", primary: "#0c2340", secondary: "#c4ced4", tertiary: "#ffffff" },
         ARI: { name: "Arizona Diamondbacks", nick: "D-backs", loc: "Arizona", primary: "#a71930", secondary: "#e3d4ad", tertiary: "#000000" } },
};
const teamsIn = (lg) => (lg === "cfb" ? (_cfbTeams || {}) : (TABLES[lg] || {}));
const teamNameIn = (lg, a) => (teamsIn(lg)[a] || {}).nick || a;
const watchHTML = (d, lg, cls) => `<div class="watch ${cls}"></div>`;
const pbpNewInjuriesHTML = () => "";
const pbpBirthdaysHTML = () => "";
const LIVE_FEEDS = { cfb: "data/cfb.json" };
const CFB = { ALA: { id: "333", name: "Alabama Crimson Tide", nick: "Alabama", primary: "#9e1b32", alt: "#ffffff" },
              MISS: { id: "145", name: "Ole Miss Rebels", nick: "Ole Miss", primary: "#13294b", alt: "#c8102e" } };
const fetched = [];
const boardFetch = (url) => { fetched.push(url); return Promise.resolve({ ok: true, json: () => Promise.resolve({ games: [], teams: CFB }) }); };
const state = { view: "pbp", pbp: { league: "cfb" } };
let redraws = 0;
const renderPbpPage = () => { redraws++; };
"""


def _node(body):
    js = f"{STUBS}\n{BLOCK}\n(async () => {{ const out = await (async () => {{ {body} }})();"
    js += " console.log(JSON.stringify(out)); })();"
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _doc(league, home, away, **live):
    lv = {"state": "live", "home_score": 14, "away_score": 17}
    lv.update(live)
    return {"league": league, "event_id": "1", "home": home, "away": away, "live": lv, "generated_at": "x",
            "records": {home: "2-4", away: "5-1"}, "tv": ["ESPN"]}


def _board(doc, **extra):
    d = dict(doc, **extra)
    return _node(f"const d = {json.dumps(d)}; return pbpBoardHTML(d, d.league, d.live || {{}});")


# --- the colours ---------------------------------------------------------------------
def test_each_club_wears_its_own_colour():
    got = _node("""return [pbpSideColours("nfl", { home: "DAL", away: "TB" }),
                           pbpSideColours("nfl", { home: "PHI", away: "DAL" }),
                           pbpSideColours("nfl", { home: "CLE", away: "CIN" }),
                           pbpSideColours("nfl", { home: "NYJ", away: "XXX" }),
                           pbpSideColours("mlb", { home: "NYY", away: "BOS" }),
                           pbpSideColours("nfl", { home: "ARI", away: "ARI" })];""")
    cowboys, eagles, browns, jets, yanks, same = got
    # The Cowboys' navy, lifted: their blue, not the grey the basketball
    # page's rule gave them.
    assert cowboys == {"home": "#3b5d84", "away": "#d50a0a"}, cowboys
    # The Eagles' midnight green, lifted; beside it the Cowboys' blue would
    # look the same, so the away side takes their silver.
    assert eagles == {"home": "#28656f", "away": "#b0b7bc"}, eagles
    # Black gives way to the Bengals' orange; the Browns' orange is too close
    # to it, so the away side keeps the only colour it has.
    assert browns == {"home": "#fb4f14", "away": "#fb4f14"}, browns
    # The table's two Jets greens: the first, lifted. No colours: grey, never gold.
    assert jets == {"home": "#4a625c", "away": "var(--text-mute)"}, jets
    assert yanks == {"home": "#455e7f", "away": "#bd3039"}, "the Yankees' navy, lifted; the Red Sox red"
    assert same == {"home": "#97233f", "away": "#ffb612"}, "a side that would look alike takes its next colour"


def test_the_colours_wash_in_from_each_sides_own_edge():
    html = _board(_doc("nfl", "PHI", "DAL"))
    assert html.startswith('<div class="card pbp-hero" style="--ca:#b0b7bc;--ch:#28656f">'), html[:120]
    grad = CSS[CSS.index("--grad-pbp-sb:"):]
    grad = grad[:grad.index(";")]
    assert grad.index("var(--ca)") < grad.index("var(--ch)"), "the away colour on the left edge, the home on the right"
    rule = CSS[CSS.index(".pbp-hero {"):]
    assert "background: var(--grad-pbp-sb);" in rule[:rule.index("}")]


# --- the sides -----------------------------------------------------------------------
def test_each_side_is_its_crest_its_city_over_its_name_its_record_and_its_score():
    html = _board(_doc("nfl", "PHI", "DAL"))
    away = html[html.index('<div class="pbp-sb-side away">'):html.index('<div class="pbp-sb-mid">')]
    home = html[html.index('<div class="pbp-sb-side home">'):]
    assert 'data-a="DAL" data-size="56"' in away and 'data-a="PHI" data-size="56"' in home, "the basketball board's crest"
    assert '<span class="pbp-sb-loc">Dallas</span>' in away and '<b class="pbp-sb-nick">Cowboys</b>' in away
    assert '<span class="pbp-sb-rec">5-1</span>' in away and '<span class="pbp-sb-rec">2-4</span>' in home
    assert re.search(r'<b class="pbp-sb-pts">17</b>', away) and re.search(r'<b class="pbp-sb-pts">14</b>', home)
    assert html.index('<div class="pbp-sb-side away">') < html.index('<div class="pbp-sb-mid">') \
        < html.index('<div class="pbp-sb-side home">'), "away, the clock, home"


def test_the_names_a_city_never_says_the_nickname_twice_and_a_college_goes_by_its_school():
    got = _node("""return [pbpSideNames("nfl", TABLES.nfl.NYJ, "New York Jets"),
                           pbpSideNames("mlb", TABLES.mlb.ARI, "Arizona Diamondbacks"),
                           pbpSideNames("cfb", CFB.MISS, "Ole Miss Rebels"),
                           pbpSideNames("cfb", { nick: "UConn", name: "Connecticut Huskies" }, "x"),
                           pbpSideNames("cfb", {}, "Alabama Crimson Tide"),
                           pbpSideNames("nfl", {}, "Dallas Cowboys")];""")
    jets, dbacks, miss, uconn, unknown, bare = got
    assert jets == {"big": "Jets", "small": "New York"}, "not the table's 'NY Jets' over 'Jets'"
    assert dbacks == {"big": "D-backs", "small": "Arizona"}, "a short nickname: the table's city"
    assert miss == {"big": "Ole Miss", "small": "Rebels"}, "the school big, the mascot over it"
    assert uconn == {"big": "UConn", "small": ""}, "a full name that does not start with the school: no guess"
    assert unknown == {"big": "Alabama Crimson Tide", "small": ""} and bare == {"big": "Dallas Cowboys", "small": ""}


def test_the_ball_is_beside_the_side_that_has_it():
    got = _node("""const fb = { home: "PHI", away: "DAL", drive: { team: "DAL" } };
      const bb = (half) => ({ home: "NYY", away: "BOS", current: { half } });
      return [pbpBallSide(fb, "nfl", { state: "live" }), pbpBallSide(Object.assign({}, fb, { drive: { team: "PHI" } }), "cfb", { state: "live" }),
              pbpBallSide(fb, "nfl", { state: "final" }), pbpBallSide(bb("T"), "mlb", { state: "live" }),
              pbpBallSide(bb("B"), "mlb", { state: "live" }), pbpBallSide({ home: "PHI", away: "DAL" }, "nfl", { state: "live" })];""")
    assert got == ["away", "home", "", "away", "home", ""], got
    html = _board(_doc("nfl", "PHI", "DAL"), drive={"team": "DAL"})
    away = html[:html.index('<div class="pbp-sb-mid">')]
    assert '<span class="pbp-sb-ball" title="Ball"><i data-icon="football"></i></span>17' in away
    assert "pbp-sb-ball" not in html[html.index('<div class="pbp-sb-side home">'):]
    mlb = _board(_doc("mlb", "NYY", "BOS"), current={"half": "B", "inning": 7})
    assert '<span class="pbp-sb-ball" title="At bat"><i data-icon="baseball"></i></span>14' in mlb


# --- the middle ----------------------------------------------------------------------
def _mid(league, lv, **doc):
    d = dict({"home": "PHI", "away": "DAL"}, **doc)
    return _node(f"return pbpBoardMidHTML({json.dumps(d)}, {json.dumps(league)}, {json.dumps(lv)});")


def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def test_the_middle_says_where_the_game_is_in_each_sport():
    fb = _mid("nfl", {"state": "live", "period": "Q2", "clock": "2:00", "detail": "2nd & 8 at DAL 4"})
    assert _text(fb) == "2nd quarter 2:00 2nd &amp; 8 at DAL 4 Live", fb
    one = _mid("mlb", {"state": "live", "outs": 1}, current={"half": "B", "inning": 9})
    assert _text(one) == "Bottom 9th 1 out Live"


def test_a_hold_reads_as_one_never_as_live():
    """tests/test_a_delayed_game_says_so.py: the box blanks a held game's
    frozen clock and down; the board says the hold, where play stopped and
    the feed's reason, and nothing pulses."""
    storm = _mid("nfl", {"state": "live", "period": "Q2", "clock": "", "detail": "", "hold": "Delayed — Lightning"})
    assert _text(storm) == "Delayed 2nd quarter · Lightning", storm
    assert '<b class="pbp-sb-clock"></b>' in storm and "pbp-sb-live" not in storm
    half = _mid("nfl", {"state": "live", "period": "Q2", "clock": "0:00", "hold": "Halftime"})
    assert _text(half) == "Halftime" and '<b class="pbp-sb-clock"></b>' in half, "it already says where"
    assert _text(_mid("cfb", {"state": "live", "period": "Q3", "hold": "End of 3rd"})) == "End of 3rd"
    rain = _mid("mlb", {"state": "live", "period": "Top 7", "outs": 2, "balls": 3, "strikes": 1, "bases": [2],
                        "hold": "Delayed — Rain"}, current={"half": "T", "inning": 7})
    assert _text(rain) == "Delayed Top 7th · 2 outs Rain" and 'data-bases="2"' in rain, rain
    assert "pbp-sb-live" not in rain, "no count and no Live through a rain delay"
    bb = _mid("mlb", {"state": "live", "period": "Top 7", "outs": 2, "balls": 1, "strikes": 2, "bases": [1, 3]},
              current={"half": "T", "inning": 7})
    assert _text(bb) == "Top 7th 2 outs · 1-2 Live" and 'data-bases="1,3"' in bb, bb


def test_before_and_after():
    assert _text(_mid("nfl", {"state": "final", "period": "Final"})) == "Final"
    assert _text(_mid("nfl", {"state": "final", "period": "Final/OT"})) == "Final OT"
    assert _text(_mid("mlb", {"state": "final"}, current={"inning": 10})) == "Final F/10"
    assert _text(_mid("mlb", {"state": "final"}, current={"inning": 9})) == "Final"
    assert _text(_mid("nfl", {"state": "scheduled", "start_time": "2026-10-27T00:15:00Z"})) == "Kickoff 7:15 PM"
    assert _text(_mid("mlb", {"state": "scheduled"})) == "First pitch —"


def test_live_the_watch_row_before_and_after_the_carrier():
    live = _board(_doc("nfl", "PHI", "DAL"))
    assert '<div class="watch pbp-watch"></div>' in live and "pbp-sb-tv" not in live
    assert live.index('<div class="pbp-sb-side home">') < live.index("pbp-watch"), "the row under the board"
    final = _board(_doc("nfl", "PHI", "DAL", state="final"))
    assert '<span class="pbp-sb-tv">ESPN</span>' in final and "pbp-watch" not in final


# --- college, from an alert ----------------------------------------------------------
def test_a_college_game_from_an_alert_reads_the_college_table_once():
    got = _node("""const d = { league: "cfb", home: "ALA", away: "MISS", home_name: "Alabama Crimson Tide",
                     away_name: "Ole Miss Rebels", live: { state: "live", home_score: 21, away_score: 24 } };
      const first = pbpBoardHTML(d, "cfb", d.live);
      await new Promise((r) => setTimeout(r, 0));
      const second = pbpBoardHTML(d, "cfb", d.live);
      pbpBoardHTML(d, "cfb", d.live);
      return { first, second, fetched, redraws };""")
    assert got["fetched"] == ["data/cfb.json"], "read once"
    assert got["redraws"] == 1, "and the page drawn again when it lands"
    assert '<b class="pbp-sb-nick">Alabama Crimson Tide</b>' in got["first"], "the full name until it does"
    assert '<span class="pbp-sb-loc">Crimson Tide</span>' in got["second"]
    assert '<b class="pbp-sb-nick">Alabama</b>' in got["second"] and '<b class="pbp-sb-nick">Ole Miss</b>' in got["second"]
    assert 'style="--ca:#465f85;--ch:#9e1b32"' in got["second"], \
        "Ole Miss's red is too near the Crimson Tide's crimson: its navy, lifted"


def test_the_old_header_is_gone_and_the_page_draws_the_board():
    page = DETAIL[DETAIL.index("async function renderPbpPage("):]
    page = page[:page.index("\n}\n")]
    assert "${pbpBoardHTML(d, league, lv)}" in page
    for old in ("pbp-hero-side", "pbp-hero-score", "pbp-hero-mid", "pbp-nm-nick", "const stateWord"):
        assert old not in DETAIL and old not in CSS, old


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
