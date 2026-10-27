"""Your week as a to-do list, and the pickups for YOUR roster.

Ethan, 2026-10-27: "I don't know how fantasy works … make sure … the fantasy
room is actually a useful tool and doing what it's supposed to be." The desk
had every answer in its own section; a newcomer could not tell which one
mattered today, and its pickups were the league's best rather than the best
for his team. What these hold (engine/fantasy_waivers, engine/fantasy_todo,
the desks in server.py, js/fantasyweek.js):

  - a pickup is worth what he adds to THIS roster's best lineup this week,
    under its scoring and slots; whom he pushes out is named; a fourth
    quarterback is worth nothing to a team that starts one;
  - a FAAB league gets a bid range from what is left of the budget, a
    stream (a kicker, a defense) a dollar, nothing past a quarter;
  - the drop is the bench player worth least over the season, never a
    starter, never one on IR, never the last at a position the league must
    start;
  - the to-do list runs in the order a week is lost in: a starter who will
    not play, the other fixes by points, a starter who may not play and when
    his game kicks off, the win chance, the best pickup with its bid and
    drop, next week's byes, a trade both sides gain from;
  - all three desks publish both; the desk draws the list first.

    python3 tests/test_your_week_and_pickups_for_your_roster.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import fantasy_todo as TD       # noqa: E402
from engine import fantasy_waivers as WV    # noqa: E402

SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
WEEK_JS = (ROOT / "web" / "js" / "fantasyweek.js").read_text(encoding="utf-8")
APP_JS = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "K", "DEF"]
FLEX = {"FLEX": "FLEX"}


def _p(name, pos, team="DAL", pts=10.0, play=1.0, status=None):
    return {"player": name, "team": team, "position": pos, "opponent": "PHI", "expected": pts * play,
            "ppr": pts, "play": play, **({"status": status} if status else {})}


def _week(*rows):
    return {"week": 9, "season": 2026, "players": list(rows),
            "teams": {"DAL": {"date": "2026-11-01", "kickoff": "16:25"}, "NYG": {"date": "2026-11-01", "kickoff": "13:00"}}}


def _means(doc):
    from engine import fantasyweek as FW
    return {r["player"]: FW.week_entry(r, {"position": r["position"]}) for r in doc["players"]}


MINE = [{"player": "QB One", "position": "QB"}, {"player": "RB One", "position": "RB"},
        {"player": "RB Two", "position": "RB"}, {"player": "WR One", "position": "WR"},
        {"player": "WR Two", "position": "WR"}, {"player": "TE One", "position": "TE"},
        {"player": "WR Bench", "position": "WR"}, {"player": "K One", "position": "K"},
        {"player": "Eagles D/ST", "position": "DEF"}, {"player": "RB IR", "position": "RB"},
        {"player": "TE Bench", "position": "TE"}]
OWN = [_p("QB One", "QB", pts=20), _p("RB One", "RB", pts=15), _p("RB Two", "RB", pts=6),
       _p("WR One", "WR", pts=14), _p("WR Two", "WR", pts=9), _p("TE One", "TE", pts=8),
       _p("WR Bench", "WR", pts=7), _p("K One", "K", pts=8), _p("RB IR", "RB", pts=0, play=0, status="IR"),
       _p("TE Bench", "TE", pts=4)]
FAS = [_p("FA Back", "RB", team="NYG", pts=13), _p("FA Quarterback", "QB", team="NYG", pts=24),
       _p("FA Kicker", "K", team="NYG", pts=9.2), _p("FA Scrub", "WR", team="NYG", pts=3)]
SEASON = {"WR Bench": {"fp_ppr": 6.5}, "RB Two": {"fp_ppr": 9.0}, "RB IR": {"fp_ppr": 1.0}, "FA Back": {"fp_ppr": 11.2},
          "TE Bench": {"fp_ppr": 3.0}}


def _desk(budget=None):
    doc = _week(*(OWN + FAS))
    means = _means(doc)
    rostered = [r["player"] for r in MINE]
    return WV.for_roster(MINE, SLOTS, {}, means, doc, rostered, season_means=SEASON,
                         statuses={"RB IR": "IR"}, budget_left=budget, week=9, playoff_start=15)


# --- the pickups ---------------------------------------------------------------------------
def test_a_pickup_is_what_he_adds_to_this_rosters_best_lineup():
    P = _desk()
    names = [r["player"] for r in P["pickups"]]
    assert names[0] == "FA Back", names
    back = P["pickups"][0]
    assert back["gain"] == 13 - 6 and back["replaces"] == "RB Two", "in for the weakest back he can replace"
    assert back["season_ppg"] == 11.2
    qb = next(r for r in P["pickups"] if r["player"] == "FA Quarterback")
    assert qb["gain"] == 4.0, "a better quarterback is worth only the difference over his own"
    assert "FA Scrub" not in names, "no pickup the lineup would not start"


def test_a_faab_league_gets_a_bid_and_a_stream_gets_a_dollar():
    P = _desk(budget=72)
    back = P["pickups"][0]
    # +7 a week is the top tier (15-25% of what is left), six weeks before
    # the playoffs three-quarters of it: $8-$14 of $72.
    assert back["bid"] == {"low": 8, "high": 14, "of": 72, "rule": "thumb"}, back["bid"]
    k = next(r for r in P["pickups"] if r["player"] == "FA Kicker")
    assert k["bid"]["rule"] == "stream" and k["bid"]["high"] == 1
    assert WV.bid(8.0, "WR", 100, 2)["high"] < WV.bid(8.0, "WR", 100, 8)["high"], "fewer weeks left, less"
    assert WV.bid(20.0, "RB", 100, 10)["high"] <= 25, "never past a quarter"
    assert _desk()["pickups"][0]["bid"] is None, "no budget, no bid"


def test_the_drop_is_the_bench_player_worth_least():
    drop = _desk()["drop"]
    # RB IR is worth least of all, and an IR slot costs no roster spot; the
    # starters (the bench WR flexes this week) are never it.
    assert drop == {"player": "TE Bench", "position": "TE", "ppg": 3.0}, drop
    best = {"starters": [{"player": "A"}]}
    assert WV.drop_candidate([{"player": "A", "position": "QB"}, {"player": "K1", "position": "K"}],
                             best, {}, SLOTS) is None, "the only kicker is never the drop"


# --- the to-do list ------------------------------------------------------------------------
def test_the_list_runs_in_the_order_a_week_is_lost_in():
    lineup = {
        "starters": [{"player": "Puka", "week": {"bye": True}},
                     {"player": "Q Back", "week": {"play": 0.64, "status": "Questionable", "team": "DAL"}}],
        "bench": [], "current": {"players": ["Puka", "Q Back"]},
        "swaps": [{"in": "Small Fix", "out": "Q Back", "gain": 1.2}, {"in": "Waddle", "out": "Puka", "gain": 11.2},
                  {"in": "Tiny", "out": "X", "gain": 0.2}],
    }
    h2h = {"me": {"points": 112.4}, "them": {"points": 106.0}, "win_prob": 0.62, "opponent": "Team B"}
    pickups = {"pickups": [{"player": "FA Back", "position": "RB", "gain": 6.0, "replaces": "RB Two",
                            "bid": {"low": 6, "high": 11, "of": 72, "rule": "thumb"}}],
               "drop": {"player": "WR Bench", "ppg": 6.5}}
    trades = [{"with": "Team C", "give": ["A"], "get": ["B"], "my_gain": 2.1, "their_gain": -0.3},
              {"with": "Team D", "give": ["C"], "get": ["D"], "my_gain": 1.4, "their_gain": 0.8}]
    out = TD.build(lineup=lineup, h2h=h2h, pickups=pickups, trades=trades, next_byes=[("WR One", "DAL")],
                   kickoffs=TD.kickoffs_from(_week()), week=9)
    kinds = [t["kind"] for t in out]
    assert kinds == ["lineup", "lineup", "risk", "matchup", "pickup", "byes", "trade"], kinds
    assert out[0]["title"] == "Puka is on a bye: start Waddle" and out[0]["tone"] == "act" and out[0]["gain"] == 11.2
    assert out[1]["title"] == "Start Small Fix over Q Back", "the smaller fix after; a fix under half a point is not listed"
    assert out[2]["title"] == "Q Back is questionable: 64% to play" and "Sun 4:25 PM ET" in out[2]["detail"]
    assert out[3]["title"] == "62% to win against Team B" and out[3]["tone"] == "good"
    assert out[4]["title"] == "Pick up FA Back (RB)" and "Bid $6–$11 of your $72" in out[4]["detail"] \
        and "Drop WR Bench (6.5 a game)" in out[4]["detail"]
    assert out[5]["title"] == "Next week: 1 starter on a bye"
    assert "Team D" in out[6]["title"], "a trade one side loses is not an idea"


def test_a_platform_that_hides_the_lineup_says_set_this_one():
    out = TD.build(lineup={"starters": [{"player": "A"}, {"player": "B"}], "current": None, "swaps": []})
    assert out == [{"kind": "lineup", "tone": "do", "title": "Set this lineup", "detail": "A, B",
                    "gain": None, "section": "lineup"}]
    assert TD.build() == []
    assert TD._why_out({"play": 0, "status": "IR"}) == "on IR" and TD._why_out({"play": 0, "status": "Out"}) == "out"
    assert TD._clock("13:00") == "1:00 PM ET" and TD._clock("20:15") == "8:15 PM ET"


# --- the desks and the page ------------------------------------------------------------------
def test_every_desk_publishes_both():
    assert SERVER.count("self._desk_extras(out, mine=mine,") == 3, "Sleeper, ESPN and Yahoo"
    assert 'if int(lset.get("waiver_type") or 0) == 2 and lset.get("waiver_budget") is not None:' in SERVER
    assert 'out["todo"] = fantasy_todo.build(' in SERVER and 'out["pickups"] = fantasy_waivers.for_roster(' in SERVER


def _render(d):
    js = f"""
    const window = {{}};
    const escapeHtml = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const escapeAttr = escapeHtml, icon = () => "", nflName = (t) => t, nflMap = () => ({{}});
    const playerAvatar = () => "", teamMark = () => "", panelEmpty = (s) => s;
    {WEEK_JS}
    console.log(JSON.stringify([window.QBWeek.todo({json.dumps(d)}), window.QBWeek.pickups({json.dumps(d)})]));"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_the_desk_draws_the_list_first_and_the_pickups_with_their_bids():
    assert "host.innerHTML = (W ? W.todo(d) : \"\") + ffH2HHTML(d)" in APP_JS and "if (W) W.todoBind(host);" in APP_JS
    d = {"week": 9, "todo": [{"kind": "lineup", "tone": "act", "title": "Puka is on a bye: start Waddle",
                              "detail": "+11.2 projected points this week", "gain": 11.2, "section": "lineup"}],
         "pickups": {"pickups": [{"player": "FA Back", "position": "RB", "gain": 6.0, "replaces": "RB Two",
                                  "season_ppg": 11.2, "bid": {"low": 6, "high": 11, "of": 72, "rule": "thumb"}}],
                     "drop": {"player": "WR Bench", "position": "WR", "ppg": 6.5}},
         "free_agents": {}}
    todo, picks = _render(d)
    assert '<li class="fft-item act" data-fftsec="lineup"' in todo and "Week 9 · what to do now" in todo
    assert '<span class="fft-gain">+11.2</span>' in todo
    assert "Pickups for your roster" in picks and "in for RB Two" in picks and "Bid $6–$11 of your $72" in picks
    assert "drop WR Bench (WR," in picks and "a rule of thumb, not\n        a measurement" in picks
    empty, _ = _render({"todo": []})
    assert "Nothing to do: your lineup is set" in empty
    assert _render({})[0] == "", "an older desk with no list draws nothing"



def test_a_kickoff_written_in_utc_reads_on_the_eastern_clock():
    """The board writes a kickoff as nflverse's Eastern "13:00" or as an ISO
    time in UTC; the to-do list's "kicks off" reads both the same."""
    k = TD.kickoffs_from({"teams": {"MIA": {"date": "2026-11-01", "kickoff": "13:00"},
                                    "CIN": {"date": "2026-10-25", "kickoff": "2026-10-25T17:00:00Z"},
                                    "NYJ": {}}})
    assert TD._when(k, "MIA") == TD._when(k, "CIN") == "Sun 1:00 PM ET"
    assert TD._when(k, "NYJ") == "" and TD._when(k, "LV") == ""

if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
