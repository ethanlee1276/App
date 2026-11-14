"""The Pick of the Day page wears each pick's real logo and names (2026-11-14).

Ethan, with two screenshots of the page: "Also the pick of the day screen is
missing logos and shit." What they showed:

  * both college cards (CFB, NCAAB) wore a grey "NCAA" text box where the
    NBA's and the NHL's cards wore their league's mark — ESPN files
    college's schools under "ncaa" but keeps no league logo by that name;
  * the Rice pick wore a "RIC" text badge and read "RICE vs TULN": the page
    loads no league's board, and college's schools ride only in theirs;
  * the bet read "RICE ML Moneyline" — the journal's name for the bet,
    printed before the team's;
  * the NBA's "Best on the board" line named Cameron Boozer with no face.

    python3 tests/test_the_pick_of_the_day_wears_its_logos.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _slate_clock import kickoff as _kickoff                 # noqa: E402  (path set above)

from engine import gate, potd                                 # noqa: E402

WEB = ROOT / "web"
APP = (WEB / "js" / "app.js").read_text()
VIS = (WEB / "js" / "visuals.js").read_text()
PAGE = (WEB / "js" / "potd.js").read_text()

RICE = {"id": "242", "name": "Rice Owls", "nick": "Rice", "primary": "#00205b", "alt": "#c1c6c8"}
TULN = {"id": "2655", "name": "Tulane Green Wave", "nick": "Tulane", "primary": "#005837", "alt": "#43b02a"}


def _fn(name, src=APP):
    i = src.index(f"function {name}(")
    return src[i:src.index("\n}\n", i) + 3]


def _const(name, src):
    i = src.index(f"const {name} = ")
    return src[i:src.index("};\n", i) + 3]


def _node(js):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


# --- the engine: the card carries its teams ------------------------------------
def test_the_boards_own_table_names_the_teams_and_their_colours():
    board = {"teams": {"RICE": RICE, "TULN": TULN, "SMU": {"nick": "SMU"}}}
    m = potd.team_marks(board, "RICE", "TULN", "NOPE", None)
    assert set(m) == {"RICE", "TULN"}, "a team the table does not hold is left out"
    assert m["RICE"]["id"] == "242" and m["RICE"]["nick"] == "Rice"
    assert m["RICE"]["secondary"] == "#c1c6c8", "college football's alt colour is the page's secondary"
    assert potd.team_marks({}, "RICE") == {} and potd.team_marks({"teams": None}, "RICE") == {}


def test_a_no_bet_cards_best_bet_carries_its_teams_and_face():
    d, k = _kickoff(180)
    board = {"sport": "cfb", "date": d, "most_likely": [], "teams": {"RICE": RICE, "TULN": TULN},
             "game_bets": [{"market": "moneyline", "team": "RICE", "opponent": "TULN", "odds": 120,
                            "book": "DraftKings", "recommended": True, "stake_units": 1.0,
                            "ev_per_unit": 0.05, "game_date": d, "kickoff": k}]}
    potd.attach(board, "cfb", prev={})
    card = board["pick_of_the_day"]
    best = card["board_best"]
    assert best["opponent"] == "TULN"
    assert set(best["marks"]) == {"RICE", "TULN"} and best["marks"]["RICE"]["id"] == "242"
    assert "marks" not in card, "no pick, no pick's teams"
    assert "headshot" in potd.BOARD_BEST_FIELDS


def test_the_pick_is_stamped_every_build_from_the_board():
    src = (ROOT / "engine" / "potd.py").read_text()
    i = src.index("THE CARD'S TEAMS, AS THE PAGE DRAWS THEM")
    body = src[i:i + 900]
    assert 'got.pop("marks", None)' in body, "a carried card wears today's, never yesterday's"
    assert 'team_marks(result, got["pick"].get("team"), got["pick"].get("opponent"))' in body


def test_the_public_copy_keeps_the_teams_only_with_the_pick():
    bet = {"sport": "cfb", "pick": {"team": "RICE", "market": "moneyline", "below_bar": ""},
           "verdict": {"call": "bet"}, "marks": {"RICE": {"id": "242"}}}
    assert gate.free_potd(bet)["marks"] == {"RICE": {"id": "242"}}, "a free pick wears its logo"
    lean = {**bet, "pick": {**bet["pick"], "below_bar": "short of the bar"}}
    out = gate.free_potd(lean)
    assert out["pick"] is None and "marks" not in out, "a lean's two schools are the lean, in another key"
    best = {"sport": "cfb", "pick": None, "board_best": {"label": "RICE Moneyline", "marks": {"RICE": {}}}}
    assert "board_best" not in gate.free_potd(best), "the best bet and its teams are members'"


# --- the page: names, logos, the bet in words -----------------------------------
def _words(pick, names=None, table=None):
    js = f"""
    const TABLE = {json.dumps(table or {})};
    const teamNameIn = (sp, a) => (TABLE[a] && TABLE[a].nick) || String(a ?? "");
    const escapeHtml = (s) => String(s == null ? "" : s);
    {_fn("potdBetText")}
    console.log(JSON.stringify(potdBetText({json.dumps(pick)}, "cfb", {json.dumps(names)})));
    """
    return _node(js)


def test_a_moneyline_reads_as_the_team_not_the_journals_name():
    pick = {"player": "RICE ML", "team": "RICE", "market": "moneyline"}
    assert _words(pick) == "RICE Moneyline"
    assert _words(pick, {"RICE": {"nick": "Rice"}}) == "Rice Moneyline"
    assert _words({"player": "RICE ML", "market": "moneyline"}) == "RICE Moneyline", "no team: the name less its ML"
    assert _words({"player": "KC", "team": "KC", "market": "moneyline"}, table={"KC": {"nick": "Chiefs"}}) \
        == "Chiefs Moneyline", "a league whose table is loaded reads as it did"


def _page(top):
    stubs = f"""
    const state = {{ sport: "nfl", view: "potd" }};
    const pushKind = () => "", pushSaved = () => null;
    const setSwitch = () => "";
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const escapeAttr = escapeHtml;
    const icon = () => "", iconMark = () => "";
    const teamNameIn = (sp, t) => t, teamMarkIn = (sp, t) => `<i data-table="${{t}}"></i>`;
    const teamMark = (a, size, map, sport) => `<i data-logo="${{(map[a] || {{}}).id}}"></i>`;
    const leagueMark = (s) => "", playerAvatar = (n, t, o) => `<i data-face="${{o.headshot}}"></i>`;
    const american = (o) => (o > 0 ? "+" + o : String(o));
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const MINUS = "−";
    const SPORT_META = {{ cfb: {{ name: "CFB" }}, nba: {{ name: "NBA" }} }};
    const LEAGUE_LABEL = {{}};
    const betItHTML = () => "";
    const memberLockHTML = () => "";
    const tzTime = () => "3:00 PM";
    {_fn("potdCallStrip")}
    {_fn("potdBetText")}
    {PAGE}
    console.log(JSON.stringify(pdPageHTML({json.dumps(top)}, {{}}, false)));
    """
    return _node(stubs)


def _top():
    pick = {"player": "RICE ML", "team": "RICE", "opponent": "TULN", "market": "moneyline",
            "odds": -140, "book": "theScore Bet", "fair_prob": 0.60, "price_implied": 0.58,
            "evidence": "exchange", "payout_units": 0.71, "below_bar": ""}
    return {"date": "2026-11-14", "sport": "cfb", "pick": dict(pick, sport="cfb"),
            "verdict": {"call": "bet", "stake": 1.0}, "runners_up": [],
            "leagues": {
                "cfb": {"sport": "cfb", "date": "2026-11-14", "pick": pick, "verdict": {"call": "bet", "stake": 1.0},
                        "marks": {"RICE": {"id": "242", "nick": "Rice"}, "TULN": {"id": "2655", "nick": "Tulane"}}},
                "nba": {"sport": "nba", "date": "2026-11-14", "pick": None,
                        "verdict": {"call": "no bet", "why": "the price is not far enough off the fair"},
                        "board_best": {"player": "Cameron Boozer", "team": "SAC", "market": "pra", "odds": -114,
                                       "book": "FanDuel", "headshot": "https://faces.test/boozer.png",
                                       "label": "Cameron Boozer OVER 31.5 Pts+Reb+Ast", "tonight": True}},
            }}


def test_the_college_pick_wears_its_schools_logo_and_names():
    html = _page(_top())
    assert 'data-logo="242"' in html, "Rice's ESPN id reaches the logo"
    assert "Rice Moneyline" in html and "Rice vs Tulane" in html
    assert "RICE ML" not in html and "RIC<" not in html


def test_the_best_bet_line_wears_his_face():
    html = _page(_top())
    i = html.index("Best on the board")
    assert 'class="pd-best-mark"><i data-face="https://faces.test/boozer.png">' in html[i:i + 400]


def test_a_card_without_marks_reads_as_it_did():
    top = _top()
    top["leagues"]["cfb"].pop("marks")
    html = _page(top)
    assert 'data-table="RICE"' in html and "RICE vs TULN" in html


# --- the league's own mark --------------------------------------------------------
def _mark(sport):
    js = f"""
    const storeArt = () => false;
    const escapeAttr = (s) => String(s);
    {_const("ICON_PATHS", APP)}
    {_const("ESPN_LEAGUE", VIS) if "const ESPN_LEAGUE = {" in VIS else ""}
    {_const("COLLEGE_GLYPH", VIS)}
    {_fn("leagueMark", VIS)}
    console.log(JSON.stringify(leagueMark({json.dumps(sport)}, 22)));
    """
    return _node(js)


def test_college_leagues_draw_their_ball_and_ask_for_no_dead_logo():
    for sport, label in (("cfb", "College football"), ("cbb", "College basketball")):
        html = _mark(sport)
        assert "<g transform" in html and f'aria-label="{label}"' in html, sport
        assert "teamlogos/leagues" not in html and ">NCAA<" not in html, sport
    nba = _mark("nba")
    assert "teamlogos/leagues/500/nba.png" in nba and "<g transform" not in nba, "the pro leagues keep their logo"


def test_the_college_table_is_never_another_leagues():
    i = APP.index("function teamsForSport(")
    body = APP[i:APP.index("\n}\n", i)]
    assert 'if (sport === "cfb") return _cfbTeams || (state.sport === "cfb" && state.data && state.data.teams) || {};' in body


# --- a league whose season is over has no card -------------------------------------
def test_a_league_out_of_season_is_left_off_the_page():
    """MLB's and the WNBA's boards still build each November day, dated
    today, so the page showed "No pick today: the board had no rows" for
    both between the leagues that play (Ethan's first screenshot)."""
    import datetime as _dt
    import tempfile
    import launch
    from test_day_top_pick import _run_writer
    today = _dt.date.today().isoformat()
    empty = {"date": today, "pick": None, "note": "No pick today: the board had no rows",
             "verdict": {"call": "no bet", "why": "No pick today: the board had no rows"}}
    boards = {"mlb": {"pick_of_the_day": dict(empty, sport="mlb")},
              "nba": {"pick_of_the_day": dict(empty, sport="nba", note="nothing cleared")}}
    was = launch._seasons_public
    launch._seasons_public = lambda day=None: {"over": ["mlb", "wnba"]}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            payload, printed, _claims = _run_writer(tmp, boards)
    finally:
        launch._seasons_public = was
    assert payload is not None, printed
    assert "nba" in payload["leagues"] and "mlb" not in payload["leagues"], payload["leagues"].keys()
    src = (ROOT / "launch.py").read_text()
    assert 'if s not in over or s == top.get("sport")}' in src, "the day's top pick keeps its own league's card"


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
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
