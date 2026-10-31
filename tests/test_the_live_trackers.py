"""The live pages track the game (2026-10-15).

Ethan, with the hockey page open and a red line drawn across the rink:
"Are we able too do like a animation of a hockey puck moving back and forth
across the ice when we show the switching of positions and shit on the live
view. Also think and do any other ideas you have for the tracking of the
live games for all sports."

One shared timeline (js/gamecast.js `track`) moves the mark on every page:
the puck runs the period's last events on the hockey page, the ball the
last shots on the basketball page (their own tests pin those pages). Here:

  * the timeline itself — its clock, a whistle's jump, an arc, a redraw that
    carries on from where the run was, and a reader who asked for less
    motion getting the end state;
  * football's drive tracker — the field from above, every snap of the drive
    a bar from where it was snapped to where it ended, a flag's walk dashed,
    the ball running the drive and coming to rest on the line of scrimmage,
    the line to gain, the red zone — and the whole game a drive a row on the
    Play-by-play tab;
  * baseball's at-bat — the league's own pitch tracking on each pitch row,
    and the strike zone with every pitch of the at-bat where it crossed,
    numbered and coloured by what came of it, the newest flying in;
  * the same runs on Ethan's photographs (his question the same day: "are we
    still using all our renders … All the animations should work flawlessly
    with the stadium art and field art"), on the cards' clock: the drive on
    the field render through a camera measured off its painted lines, the
    at-bat on the ballpark render from the pitcher's hand to the plate;
  * the stylesheets' rules, and the page in a browser (opt-in).

Run directly: `python3 tests/test_the_live_trackers.py`
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
sys.path.insert(0, str(ROOT / "tests"))

import livescore_build as B                                  # noqa: E402
from engine.mlb.sources import pbp as MP                     # noqa: E402
from _app import app_js  # noqa: E402  (app.js and the rooms it loads on first use)


def _G():
    """The gamecast test's own Bucs @ Cowboys summary builders, imported
    where they are used: a sibling test file is not a module-scope import
    (test_doctor's rule)."""
    import test_gamecast
    return test_gamecast

APP = app_js()
GC = (ROOT / "web" / "js" / "gamecast.js").read_text(encoding="utf-8")
GC_CSS = (ROOT / "web" / "css" / "gamecast.css").read_text(encoding="utf-8")
RC_CSS = (ROOT / "web" / "css" / "rinkcast.css").read_text(encoding="utf-8")
HC_CSS = (ROOT / "web" / "css" / "hoopscast.css").read_text(encoding="utf-8")
STYLES = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")

STUBS = """
  globalThis.window = globalThis;
  let NOW = 1.7e12;
  Date.now = () => NOW;
  globalThis.escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  globalThis.escapeAttr = escapeHtml;
  globalThis.icon = (n) => `<i class="ico-${n}"></i>`;
  globalThis.teamMarkIn = (lg, a) => `<span class="mark">${a}</span>`;
  globalThis.teamNameIn = (lg, a) => ({ DAL: "Cowboys", TB: "Buccaneers" })[a] || a;
  globalThis.teamsForSport = () => ({ DAL: { primary: "#002244", secondary: "#b0b7bc" }, TB: { primary: "#d50a0a", secondary: "#34302b" } });
  globalThis.pbpOrd = (n) => n === 1 ? "1st" : n === 2 ? "2nd" : n === 3 ? "3rd" : `${n}th`;
  globalThis.pbpAgo = () => "just now";
  globalThis.trueMinus = (s) => s;
  globalThis.hockeyPeriod = (n) => `P${n}`;
  globalThis.panelEmpty = (t) => `<p>${t}</p>`;
  globalThis.gameId = (g) => g.id || "g";
  globalThis.playsHTML = (g) => (g.plays || []).map((p) => `<div class="lb-play">${p.event}</div>`).join("");
  globalThis.pbpGroups = () => [];
  globalThis.pbpPropsHTML = () => "<div>picks</div>";
  globalThis.lineTrackHTML = () => "<div>track</div>";
"""


def _node(js, calm=False):
    """gamecast.js under node, the page's helpers stubbed, the clock in the
    test's hands (`NOW`, milliseconds; move it to move time)."""
    node = shutil.which("node")
    if not node:
        return None
    still = 'globalThis.matchMedia = () => ({ matches: true });' if calm else ""
    prog = f"{STUBS}\n{still}\n{GC}\nconsole.log(JSON.stringify((() => {{ const Q = window.QBGamecast; {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


# --- the timeline ---------------------------------------------------------------
PTS = [{"x": 0, "y": 0}, {"x": 100, "y": 0, "leg": 1, "hold": 0.5}, {"x": 100, "y": 50, "leg": 0.5, "hold": 0, "jump": True}]


def test_the_timeline_keeps_its_own_clock_and_a_whistle_is_a_jump():
    got = _node(f"""const T = Q.track({json.dumps(PTS)}, {{ elapsed: 0 }});
      return {{ at: T.at, go: T.go, dur: T.dur, still: T.still, motion: T.motion }};""")
    if got is None:
        print("  SKIP node not installed"); return
    # Fades in (0.2), holds (0.3), glides a second, holds half a second, then
    # a jump: out where it was, in where it lands (0.2 + 0.01 + 0.2).
    assert [round(v, 2) for v in got["at"]] == [0, 1.5, 2.41] and [round(v, 2) for v in got["go"]] == [0, 0.5, 2.0]
    assert round(got["dur"], 2) == 2.41 and not got["still"]
    assert '<animateTransform attributeName="transform" type="translate"' in got["motion"]
    assert 'values="0.0 0.0;0.0 0.0;' in got["motion"], "the run starts on its first point"
    opac = re.search(r'attributeName="opacity" calcMode="linear" values="([^"]+)"', got["motion"]).group(1).split(";")
    assert opac[0] == "0" and opac[-1] == "1" and opac.count("0") == 3, "faded in at the start; out and in again at the jump"


def test_a_redraw_carries_on_from_where_the_run_was():
    got = _node(f"""const T = Q.track({json.dumps(PTS)}, {{ elapsed: 1.0 }});
      return {{ left: T.left, past: [T.past(0.9), T.past(1.5)], begin: T.begin(2.0), motion: T.motion,
               steps: T.steps("opacity", ["a", "b", "c"], "z") }};""")
    if got is None:
        return
    assert round(got["left"], 2) == 1.41
    assert got["past"] == [True, False] and got["begin"] == "1.00s"
    assert 'values="50.0 0.0;100.0 0.0;' in got["motion"], "cut at the moment: halfway along the glide"
    assert 'values="b;c;z"' in got["steps"] and 'keyTimes="0;0.7092;1"' in got["steps"], got["steps"]


def test_a_run_over_or_a_reader_who_asked_for_less_motion_gets_the_end_state():
    over = _node(f"""const T = Q.track({json.dumps(PTS)}, {{ elapsed: 9 }});
      return {{ still: T.still, motion: T.motion, left: T.left, past: T.past(99), steps: T.steps("x", ["1", "2", "3"], "4") }};""")
    if over is None:
        return
    assert over == {"still": True, "motion": "", "left": 0, "past": True, "steps": ""}
    calm = _node(f"""const T = Q.track({json.dumps(PTS)}, {{ elapsed: 0 }}); return [T.still, T.motion];""", calm=True)
    assert calm == [True, ""]
    none = _node("const T = Q.track([], {}); return [T.still, T.dur];")
    assert none == [True, 0]


def test_an_arc_is_sampled_along_its_curve():
    got = _node("""const a = Q.track([{ x: 0, y: 0 }, { x: 100, y: 0, leg: 1, via: [50, -60] }], {});
      const b = Q.track([{ x: 0, y: 0 }, { x: 100, y: 0, leg: 1 }], {});
      const n = (T) => /type="translate" calcMode="linear" values="([^"]+)"/.exec(T.motion)[1].split(";").length;
      return { arc: n(a), line: n(b), up: Math.min(...(/values="([^"]+)"/.exec(a.motion)[1].split(";").map((v) => Number(v.split(" ")[1])))) };""")
    if got is None:
        return
    assert got["arc"] == got["line"] + 5, "five points along the curve between the two"
    assert -31 < got["up"] < -29, "the quadratic's top, half the control point's height"


# --- football: the drive on the field ------------------------------------------------
def _fb_summary():
    """TB @ DAL, DAL home: a TB punt drive, a DAL touchdown drive, a TB
    interception, and the DAL drive in progress — a run with a flag walked
    off after it, an incompletion, a penalty, a sack."""
    G = _G()
    n = iter(range(1, 999))

    def P(team, to_go, yards, ptype, penalty=False, **kw):
        p = G._play(f"q{next(n)}", team=team, to_go=to_go, yards=yards, ptype=ptype, text="", **kw)
        p["isPenalty"] = penalty
        return p

    def drive(did, team, plays, result, period):
        d = {"id": did, "team": team, "offensivePlays": len(plays), "yards": 30, "timeElapsed": {"displayValue": "2:00"},
             "start": {"yardLine": 25, "period": {"number": period}}, "plays": plays}
        if result:
            d["displayResult"] = result
        return d
    d1 = drive("d1", G.TB, [P("27", 65, 0, "Kickoff", down=0), P("27", 75, 6, "Rush"), P("27", 69, -8, "Sack", down=2, dist=4),
                            P("27", 77, 44, "Punt", down=3, dist=12)], "Punt", 1)
    d2 = drive("d2", G.DAL, [P("6", 75, 4, "Rush"), P("6", 71, 18, "Pass Reception", down=2, dist=6),
                             P("6", 53, 53, "Passing Touchdown", scoring=True, home=6),
                             P("6", 15, 0, "Extra Point Good", down=0, scoring=True, home=7)], "Touchdown", 1)
    d3 = drive("d3", G.TB, [P("27", 65, 0, "Kickoff", down=0, period=2, home=7),
                            P("27", 60, 0, "Pass Interception Return", turnover=True, period=2, home=7)], "Interception", 2)
    d4 = drive("d4", G.DAL, [P("6", 35, 4, "Rush", period=3, home=7), P("6", 26, 0, "Pass Incompletion", period=3, home=7),
                             P("6", 26, 5, "Penalty", penalty=True, period=3, home=7),
                             P("6", 21, -3, "Sack", down=2, dist=5, period=3, home=7)], "", 3)
    s = G._summary()
    s["drives"] = {"previous": [d1, d2, d3, d4], "current": d4}
    return s


def _fb_doc(yard_line=76, detail="3rd & 8 at TB 24", state="live", spots=True):
    g = _G()._game(state=state)
    g["live"].update({"yard_line": yard_line, "detail": detail, "possession": "DAL", "period": "Q3"})
    doc = B.pbp_doc("nfl", g, _fb_summary())
    if not spots:
        for dr in doc.get("drives") or []:
            for p in dr.get("plays") or []:
                p.pop("spot", None)
    return doc


def test_a_drive_is_its_snaps_where_they_started_and_where_they_ended():
    d = _fb_doc()
    got = _node(f"""const d = {json.dumps(d)};
      return d.drives.map((dr) => Q.driveRows(d, dr).map((r) => [r.kind, r.label, r.from, r.to, r.ext, r.fly]));""")
    if got is None:
        return
    punt, td, pick, now = got
    # A kickoff's spot is the kicking side's, and a try is no snap: neither is drawn.
    assert [r[1] for r in punt] == ["+6 RUN", "−8 SACK", "PUNT"], punt
    assert punt[0][2:4] == [75, 69] and punt[1][2:4] == [69, 77], "the away side drives toward 0; a sack takes it back"
    # A punt's yards are its return (the real PIT @ NO feed, 2026-10-25:
    # -3, 0, 20), so it is not flown that far: it sits at its snap.
    assert punt[2][0] == "kick" and punt[2][5] is None, "a punt is not flown its return's length"
    assert [r[1] for r in td] == ["+4 RUN", "+18 PASS", "+53 TD"] and td[2][3] == 100, "a touchdown runs to the goal line"
    assert pick == [["to", "INT", 60, 60, None, None]], "a turnover stays where the ball was snapped"
    assert [r[0] for r in now] == ["run", "inc", "flag", "loss"]
    assert [r[1] for r in now] == ["+4 RUN", "INC", "+5 FLAG", "−3 SACK"]
    assert now[0][2:5] == [65, 69, 74], "the next snap is five yards on from where the run ended: a flag walked off"
    assert now[1][2:5] == [74, 74, None] and now[3][2:4] == [79, 76]


def test_the_scoreboard_says_where_the_next_snap_is_and_what_it_needs():
    got = _node("""const d = { home: "DAL", away: "TB" };
      const at = (yl, detail) => Q.nextSnap(Object.assign({}, d, { live: { yard_line: yl, detail } }), 1);
      return [at(76, "3rd & 8 at TB 24"), at(91, "1st & Goal at TB 9"), at(null, "2nd & 5 at TB 30"), at(95, "4th & 9 at TB 5")];""")
    if got is None:
        return
    assert got[0] == {"los": 76, "gain": 84, "goal": False, "words": "3rd & 8"}
    assert got[1] == {"los": 91, "gain": None, "goal": True, "words": "1st & Goal"}, "goal to go: the goal line is the line"
    assert got[2] is None, "no spot, no line"
    assert got[3]["gain"] == 100, "never past the goal line"


def test_the_drive_card_draws_the_field_the_lines_and_the_ball_running_the_drive():
    d = _fb_doc()
    got = _node(f"""const d = {json.dumps(d)};
      const ctx = {{ d, league: "nfl", faces: {{}}, boardGame: null }};
      const first = Q.panel("gamecast", ctx);
      NOW += 60000;                                        // the page's redraw, a minute on
      const later = Q.panel("gamecast", ctx);
      return {{ first, later }};""")
    if got is None:
        return
    g = got["first"]
    assert "Current drive" in g and g.count('data-gc-fd') == 1 and 'data-gc-replay' in g
    assert g.count('class="gc-fd-svg wide"') == 1 and g.count('class="gc-fd-svg narrow"') == 1, "one field for a desktop, one for a phone"
    for svg in re.findall(r'<svg class="gc-fd-svg.*?</svg>', g, re.S):
        assert svg.count('class="gc-fd-lbl') == 4, "a word for every snap"
        assert 'class="gc-fd-los"' in svg and 'class="gc-fd-gain"' in svg and ">3rd &amp; 8<" in svg
        assert 'class="gc-fd-ext"' in svg, "the flag's walk"
        assert '<g class="gc-fd-ball"' in svg and '<animateTransform attributeName="transform" type="translate"' in svg
        assert 'style="--tm:#002244"' in svg, "the field wears the offence's colour"
    assert ">DAL<" in g and ">TB<" in g, "the end zones are named"
    assert "Line of scrimmage" in g and "Line to gain" in g and "Red zone" not in g
    assert "<animate" not in got["later"].split("gc-fd")[1], "a redraw after the run draws it at rest"
    assert got["later"].count('class="gc-fd-lbl') == 8
    # The Down and Ball on tiles went (2026-10-25): the header says the
    # next snap's down and spot, and the strip under the photograph says
    # where the ball is — three places was the repetition Ethan asked
    # to lose.
    assert ">Down<" not in g and ">Ball on<" not in g and "gc-tiles" not in g


def test_a_new_play_runs_from_the_last_one_seen_and_the_red_zone_lights():
    d = _fb_doc()
    more = _fb_doc(yard_line=88, detail="4th & 1 at TB 12")
    snap = {"kind": "football", "id": "q99", "period": 3, "clock": "9:00", "team": "DAL", "event": "Rush", "down": 3,
            "distance": 8, "yards": 12, "scoring": False, "turnover": False, "penalty": False, "spot": 76}
    more["drives"][-1]["plays"].append(snap)
    got = _node(f"""const ctx = (d) => ({{ d, league: "nfl", faces: {{}}, boardGame: null }});
      Q.panel("gamecast", ctx({json.dumps(d)}));
      NOW += 60000;
      Q.panel("gamecast", ctx({json.dumps(d)}));
      NOW += 1000;
      return Q.panel("gamecast", ctx({json.dumps(more)}));""")
    if got is None:
        return
    wide = re.search(r'<svg class="gc-fd-svg wide".*?</svg>', got, re.S).group(0)
    assert '<animateTransform attributeName="transform" type="translate"' in wide, "the new play runs"
    assert wide.count("stroke-dasharray") == 2, "only the new play's bar draws itself (its line and its halo)"
    assert "+12 RUN" in wide and 'class="gc-fd-rz"' in wide and 'class="gc-rz">Red zone<' in got
    assert ">4th &amp; 1<" in wide


def test_no_spot_no_field_and_a_final_has_no_drive():
    bare = _node(f"""const d = {json.dumps(_fb_doc(spots=False))};
      return Q.panel("gamecast", {{ d, league: "nfl", faces: {{}}, boardGame: null }});""")
    if bare is None:
        return
    assert "Current drive" in bare and "data-gc-fd" not in bare and "data-gc-replay" not in bare
    final = _node(f"""const d = {json.dumps(_fb_doc(state="final"))};
      return Q.panel("gamecast", {{ d, league: "nfl", faces: {{}}, boardGame: null }});""")
    assert "Current drive" not in final and "data-gc-fd" not in final


def test_the_plays_tab_leads_with_the_whole_game_a_drive_a_row():
    d = _fb_doc()
    got = _node(f"""const d = {json.dumps(d)};
      const ctx = {{ d, league: "nfl", faces: {{}}, boardGame: null }};
      return [Q.panel("plays", ctx), Q.panel("plays", ctx)];""")
    if got is None:
        return
    first, again = got
    assert first.index('class="card gc-chart"') < first.index('class="card gc-dr'), "the chart, then the drives"
    wide = re.search(r'<svg class="gc-fd-svg wide".*?</svg>', first, re.S).group(0)
    assert wide.count('class="gc-dc-row') == 4
    tags = re.findall(r'class="gc-dc-tag (\w*)"[^>]*>([^<]+)<', wide)
    assert tags == [("", "PUNT"), ("score", "TD"), ("bad", "INT"), ("now", "NOW")], tags
    assert re.findall(r'class="gc-dc-ql"[^>]*>(\w+)<', wide) == ["Q1", "Q2", "Q3"]
    assert 'class="gc-fd-ezt band"' in wide, "a chart whose rows fill the field names the end zones over it"
    assert " grow" in first and " grow" not in again, "drawn in once, not on every redraw"
    assert "DAL drives right, TB left" in first


# --- baseball: the at-bat, pitch by pitch -------------------------------------------
def _pitch(n, code, x=None, z=None, balls=0, strikes=0, ptype="Four-Seam Fastball", speed=96.0, top=3.5, bot=1.6):
    pd = {"startSpeed": speed}
    if x is not None:
        pd["coordinates"] = {"pX": x, "pZ": z}
        pd["strikeZoneTop"], pd["strikeZoneBottom"] = top, bot
    return {"isPitch": True, "pitchNumber": n, "details": {"type": {"description": ptype}, "call": {"code": code}, "isInPlay": code == "X"},
            "pitchData": pd, "count": {"balls": balls, "strikes": strikes}}


def _mlb_payload(done=False):
    events = [_pitch(1, "C", -0.5, 3.0, strikes=1), _pitch(2, "B", 1.3, 1.4, balls=1, strikes=1),
              _pitch(3, "S", 0.6, 1.2, balls=1, strikes=2), _pitch(4, "B", None, balls=2, strikes=2),
              _pitch(5, "F", 0.1, 2.2, balls=2, strikes=2)]
    if done:
        events.append(_pitch(6, "S", 0.9, 1.0, balls=2, strikes=3))
    return {"allPlays": [{
        "about": {"atBatIndex": 7, "inning": 6, "halfInning": "top"},
        "matchup": {"batter": {"fullName": "Giancarlo Stanton"}, "pitcher": {"fullName": "Tarik Skubal"}},
        "result": {"event": "Strikeout" if done else "", "awayScore": 3, "homeScore": 2},
        "playEvents": events}]}


def _mlb_doc(done=False, state="live"):
    pay = _mlb_payload(done)
    return {"league": "mlb", "event_id": "777001", "home": "DET", "away": "NYY", "live": {"state": state},
            "events": MP.game_events(pay), "current": MP.current_at_bat(pay)}


def test_a_pitch_row_carries_where_it_crossed_and_the_batters_zone():
    rows = [r for r in MP.game_events(_mlb_payload()) if r["kind"] == "pitch"]
    assert (rows[0]["px"], rows[0]["pz"], rows[0]["sz"]) == (-0.5, 3.0, [3.5, 1.6])
    assert "px" not in rows[3] and "sz" not in rows[3], "a pitch the cameras did not track has no location, not a zero"
    odd = _mlb_payload()
    odd["allPlays"][0]["playEvents"][0]["pitchData"]["coordinates"] = {"pX": 9.0, "pZ": 2.0}
    odd["allPlays"][0]["playEvents"][1]["pitchData"]["strikeZoneTop"] = 1.0       # a top under the bottom
    rows = [r for r in MP.game_events(odd) if r["kind"] == "pitch"]
    assert "px" not in rows[0], "nine feet off the plate is no pitch"
    assert "px" in rows[1] and "sz" not in rows[1], "a zone upside down is not a zone"


def test_the_zone_draws_the_at_bat_numbered_and_coloured_and_the_newest_flies_in():
    got = _node(f"""const d = {json.dumps(_mlb_doc())};
      const first = Q.zone(d);
      NOW += 60000;
      return {{ first, later: Q.zone(d) }};""")
    if got is None:
        return
    z = got["first"]
    assert "data-gc-pz" in z and "This at-bat · 5 pitches" in z and "Giancarlo Stanton" in z and "Tarik Skubal" in z
    dots = re.findall(r'class="gc-pz-dot (\w)"', z)
    assert dots == ["c", "b", "w", "f"], "four located: a called strike, a ball, a whiff, a foul (the fourth was not tracked)"
    assert re.findall(r'class="gc-pz-num \w"[^>]*>(\d)<', z) == ["1", "2", "3", "5"]
    assert z.count('class="gc-pz-ring"') == 1, "the newest, ringed"
    assert len(re.findall(r'<li class="gc-pz-row', z)) == 5 and 'gc-pz-row now' in z, "every pitch in the list, tracked or not"
    assert "96 mph Four-Seam Fastball" in z and ">2-2<" in z
    assert '<animate attributeName="cx"' in z, "the at-bat flies in on a first look"
    assert '<animate attributeName="cx"' not in got["later"], "and a redraw draws it at rest"
    assert "data-gc-pz-replay" in z


def test_between_at_bats_the_last_one_stays_with_how_it_ended_and_a_final_draws_none():
    got = _node(f"""return [Q.zone({json.dumps(_mlb_doc(done=True))}), Q.zone({json.dumps(_mlb_doc(state="final"))}),
                            Q.zone({{ live: {{ state: "live" }}, events: [] }})];""")
    if got is None:
        return
    done, final, empty = got
    assert "Last at-bat · 6 pitches" in done and ">Strikeout<" in done
    assert final == "" and empty == ""


def test_the_mlb_page_loads_the_module_and_draws_the_zone_under_the_at_bat():
    assert '${pbpSituationHTML(d, league, faces)}${league === "mlb" && window.QBGamecast && QBGamecast.zone ? QBGamecast.zone(d) : ""}' in APP
    assert 'if (!window.QBGamecast) {\n    loadGamecast().then((mod) => { if (mod && state.view === "pbp") renderPbpPage(); });' in APP
    assert 'const GC = league === "mlb" ? null : (window.QBGamecast || null);' in APP, "baseball keeps its own rooms"
    assert "zone," in GC.split("window.QBGamecast = {")[1]


# --- on Ethan's photographs -------------------------------------------------------------
# Ethan, 2026-10-15: "are we still using all our renders I've been giving you for
# the stadium art … All the animations should work flawlessly with the stadium art
# and field art and shit we already have." The drive runs on the field render and
# the at-bat on the ballpark render, on the same clock as the cards under them.
def _pop_at(svg, label):
    """When `label` shows: the last `begin` written before it (its fade-in)."""
    i = svg.index(f">{label}<")
    return float(re.findall(r'begin="([\d.]+)s"', svg[:i])[-1])


def _art(d, hit, league="nfl", setup=""):
    return _node(f"""{setup} const d = {json.dumps(d)};
      return Q.art(d, "{league}", {json.dumps(hit)}, null);""")


def test_the_timeline_scales_the_mark_with_its_size():
    got = _node("""const a = Q.track([{ x: 0, y: 0, size: 1 }, { x: 0, y: -50, size: 0.5, leg: 1, via: [0, -90] }], {});
      const b = Q.track([{ x: 0, y: 0 }, { x: 0, y: -50, leg: 1 }], {});
      const vals = /type="scale" additive="sum" calcMode="linear" values="([^"]+)"/.exec(a.motion);
      const keys = (m) => [...m.matchAll(/keyTimes="([^"]+)"/g)].map((k) => k[1]);
      return { sizes: vals ? vals[1].split(";").map(Number) : null, same: new Set(keys(a.motion)).size, none: b.motion.includes('type="scale"') };""")
    if got is None:
        return
    s = got["sizes"]
    assert s and s[0] == 1 and s[-1] == 0.5, s
    assert all(x >= y for x, y in zip(s, s[1:])), "evenly smaller along the arc: its rise is height, not distance"
    assert got["same"] == 1, "the size keeps the place's clock"
    assert got["none"] is False, "a mark with no size is not scaled"


def test_the_drive_on_the_photograph_runs_on_the_cards_clock():
    d = _fb_doc()
    hit = [p for p in d["plays"] if p.get("kind") == "football"][-1]
    got = _node(f"""const d = {json.dumps(d)}, hit = {json.dumps(hit)};
      const card = Q.panel("gamecast", {{ d, league: "nfl", faces: {{}}, boardGame: null }});
      const photo = Q.art(d, "nfl", hit, null);
      NOW += 60000;
      return {{ card, photo, rest: Q.art(d, "nfl", hit, null) }};""")
    if got is None:
        return
    photo = got["photo"]
    wide = re.search(r'<svg class="gc-fd-svg wide".*?</svg>', got["card"], re.S).group(0)
    assert photo.count("data-gc-art") == 1 and 'data-gc-replay' in photo, "Replay on the photograph too"
    assert 'class="gc-art-los" x1="0.0" y1="115.4" x2="240.0"' in photo, "the line of scrimmage under the ball, side to side"
    # Each snap's own line to gain: 1st & 10 on the painted 40 (95.4), 2nd & 5 after the flag.
    assert '<line class="gc-art-gain" x1="0.0" y1="95.7"' in photo
    assert 'type="scale" additive="sum"' in photo, "the ball is smaller down the field"
    for label in ("+4 RUN", "INC", "+5 FLAG", "−3 SACK"):
        assert _pop_at(photo, label) == _pop_at(wide, label), f"{label}: the photograph and the card land it together"
    assert ">3rd &amp; 8<" in photo and ">TB 24<" in photo, "the run ends on the next snap"
    rest = got["rest"]
    assert "<animate" not in rest, "a redraw after the run draws it at rest"
    assert '<line class="gc-art-gain" x1="0.0" y1="98.8"' in rest, "3rd & 8: eight yards on"
    assert 'transform="translate(117.6 117.4) scale(1.000)"' in rest, "the ball under the centre"
    assert ">3rd &amp; 8<" in rest and "+4 RUN" not in rest


def test_the_photograph_and_app_js_draw_with_one_measured_camera():
    cam = re.search(r"const CAM = \{ A: ([\d.]+), B: ([\d.]+), C: ([\d.]+), los: ([\d.]+), back: ([\d.]+), vx: \d+, ball: \[([\d.]+), ([\d.]+)\],\s+qb: ([\d.]+)", GC)
    field = re.search(r"qb: \[([\d.]+), ([\d.]+)\],.*?\n\s+los: ([\d.]+), goal: \d+,\n\s+A: ([\d.]+), B: -([\d.]+), C: ([\d.]+),", APP)
    assert cam and field, "both cameras found"
    A, B, C, los, back, bx, by, qb = (float(v) for v in cam.groups())
    qx, qy, flos, fA, fB, fC = (float(v) for v in field.groups())
    assert (A, B, C, los) == (fA, fB, fC, flos), "the drive and app.js's own play on one camera"
    assert (bx, qb) == (qx, qy), "and the passer in the same place"
    # Pinned to the painted lines: the 30 the ball is on, then the 35, 40, 45.
    y = lambda yd: A + B / (yd + C)
    for yd, painted in ((0, 115.3), (5, 103.9), (10, 95.4), (15, 88.6)):
        assert abs(y(yd) - painted) < 0.6, (yd, y(yd))
    assert abs(los + back * 5 - 129.9) < 0.2, "five yards back: the painted 25"


def test_the_photograph_keeps_app_js_play_when_it_has_no_drive_to_draw():
    if not shutil.which("node"):
        return
    d = _fb_doc()
    tb = dict([p for p in d["plays"] if p.get("kind") == "football"][-1], team="TB")
    got = [_art(d, tb), _art(_fb_doc(spots=False), None), _art(d, None, league="nba")]
    assert got == [None, None, None], "another side's frame, no spots, another sport: app.js draws its own"


def test_a_drive_that_ended_keeps_its_last_play_on_the_photograph():
    td = _fb_doc()
    td["drives"] = td["drives"][:2]
    fg = json.loads(json.dumps(td))
    kick = [p for p in fg["drives"][1]["plays"] if "Touchdown" in str(p.get("event"))][0]
    kick.update({"event": "Field Goal Good", "yards": 0})
    got = _node(f"""const run = (d) => {{ const dr = d.drives[d.drives.length - 1]; const hit = dr.plays[dr.plays.length - 1];
        Q.art(d, "nfl", hit, null); NOW += 60000; return Q.art(d, "nfl", hit, null); }};
      return [run({json.dumps(td)}), run({json.dumps(fg)})];""")
    if got is None:
        return
    td_rest, fg_rest = got
    assert ">+53 TD<" in td_rest and 'class="gc-art-goal"' in td_rest, "a touchdown keeps its goal line"
    assert 'transform="translate(119.1 65.5)' in td_rest, "the ball on it, fifty-three yards on"
    assert "gc-art-gain" not in td_rest, "the line to gain is spent"
    assert ">FG<" in fg_rest and 'transform="translate(119.8 47.0)' in fg_rest, "a field goal goes through the posts in the picture"
    assert 'class="gc-art-kick"' in fg_rest


def test_the_ballpark_throws_the_at_bat_on_the_zones_clock():
    d = _mlb_doc()
    got = _node(f"""const d = {json.dumps(d)};
      const photo = Q.art(d, "mlb", null, null), zone = Q.zone(d);
      NOW += 60000;
      return {{ photo, zone, rest: Q.art(d, "mlb", null, null) }};""")
    if got is None:
        return
    photo, zone = got["photo"], got["zone"]
    flights = lambda s: re.findall(r'attributeName="cx"[^>]*?begin="([\d.]+)s"', s)
    assert flights(photo) == flights(zone) and len(flights(photo)) == 4, "every tracked pitch leaves the hand as the zone's does"
    assert 'from="119.5" to="118.1"' in photo, "from the pitcher's hand to where it crossed: -0.5 ft, 3.0 ft up"
    assert re.findall(r'class="gc-art-dot (\w)"', photo) == ["c", "b", "w", "f"], "the pitch chart's colours; the untracked fourth not thrown"
    assert 'class="gc-art-zone"' in photo and "data-gc-pz-replay" in photo
    chips = re.findall(r'<text class="t"[^>]*>([^<]+)<', photo)
    assert chips == ["1 · Called strike", "2 · Ball", "3 · Swinging strike", "5 · Foul"], "each tracked pitch named as it lands, the newest last"
    rest = got["rest"]
    assert "<animate" not in rest and ">5 · Foul<" in rest, "a redraw draws the at-bat at rest, the newest pitch named"


def test_a_ball_in_play_flies_on_from_the_plate_and_an_old_one_stays_faint():
    done = _mlb_doc(done=True)
    ab = [r for r in done["events"] if r["kind"] == "atbat"][-1]
    ab.update({"event": "Home Run", "scoring": True, "hit": {"distance": 421, "trajectory": "fly_ball", "launch_speed": 108.4}})
    old = _mlb_doc()
    earlier = dict(ab, at_bat=6)
    stub = ('globalThis.pbpFlight = () => ({ H: [118, 131], C: [112, 60], L: [100, 58], len: 80, over: true });'
            ' globalThis.PBP_TRAJ = { fly_ball: "Fly ball" };')
    got = _node(f"""{stub}
      const hr = Q.art({json.dumps(done)}, "mlb", {json.dumps(ab)}, null);
      const faint = Q.art({json.dumps(old)}, "mlb", {json.dumps(earlier)}, null);
      return {{ hr, faint }};""")
    if got is None:
        return
    hr = got["hr"]
    last_lands = max(float(b) for b in re.findall(r'attributeName="cx"[^>]*?begin="([\d.]+)s"', hr)) + 0.42
    motion = float(re.search(r'<animateMotion begin="([\d.]+)s"', hr).group(1))
    assert abs(motion - (last_lands + 0.1)) < 0.011, "the ball leaves the bat as the last pitch lands"
    assert ">Home Run<" in hr and ">Fly ball<" in hr and "421 FT" in hr
    assert 'class="gc-art-old"' in got["faint"] and ">Fly ball<" not in got["faint"], "an earlier ball in play stays, faint, under the pitches"


def test_the_live_page_asks_for_the_photographs_drawing():
    assert "const fx = window.QBGamecast && QBGamecast.art && QBGamecast.art(d, league, hitRow, boardGame);" in APP
    assert "const arc = fx || (league === \"mlb\" && hitRow && hitRow.hit" in APP, "and keeps its own when there is none"
    assert "art," in GC.split("window.QBGamecast = {")[1]


# --- the stylesheets ------------------------------------------------------------------
def test_the_stylesheet_is_the_sites_tokens_and_motion_stops_for_a_reader_who_asked():
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", GC_CSS), "tokens only: it re-tints in light mode with the rest"
    defined = set(re.findall(r"(--[\w-]+)\s*:", STYLES + GC_CSS + GC))
    for name in set(re.findall(r"var\((--[\w-]+)", GC_CSS + GC)):
        assert name in defined, f"{name} is read and never defined"
    for m in re.finditer(r"transition:[^;]+;", GC_CSS):
        assert "var(--dur-" in m.group(0) and "var(--ease-" in m.group(0), m.group(0)
    for rule in ("@media (prefers-reduced-motion: reduce) { .gc-replay { display: none; } }",
                 "@media (prefers-reduced-motion: reduce) { .gc-fd-ring { animation: none; opacity: 0; } }",
                 "@media (prefers-reduced-motion: reduce) { .gc-dc-row.grow { animation: none; } }",
                 "@media (prefers-reduced-motion: reduce) { .gc-pz-ring { animation: none; opacity: .7; } }"):
        assert rule in GC_CSS, rule
    assert "@container (max-width: 480px)" in GC_CSS and ".gc-fd { margin-top: 12px; container-type: inline-size; }" in GC_CSS
    # A line that draws itself must take its dashes from the drawing, not a rule.
    for cls in ("gc-fd-bar", "gc-fd-halo", "gc-art-bar", "gc-art-halo", "gc-art-trail", "gc-art-arc"):
        rules = re.findall(r"\." + cls + r"(?:\.(?!flag)\w+)?\s*\{[^}]*\}", GC_CSS)
        assert rules and not any("stroke-dasharray" in r for r in rules), cls
    assert "onclick" not in GC and "onerror" not in GC
    # On the photographs: a night game in either theme keeps its own colours,
    # the broadcast's blue line on the card as well, and the ring stops.
    art = re.search(r"\.gc-art \{([^}]*)\}", GC_CSS).group(1)
    for name in ("--art-ink", "--art-gold", "--art-blue", "--art-red", "--art-shade"):
        assert name + ":" in art, name
    assert ".gc-fd-los { stroke: var(--gc-los);" in GC_CSS and ':root[data-theme="light"] { --gc-los:' in GC_CSS
    assert "@media (prefers-reduced-motion: reduce) { .gc-art-ring { animation: none; opacity: 0; } }" in GC_CSS
    assert ".pbp-park > .gc-art-replay { position: absolute; top: 8px; right: 8px; z-index: 1; }" in GC_CSS


def test_the_views_bars_fit_with_replay_from_a_phone_to_a_desktop():
    assert "@media (max-width: 480px) {\n  .rc-view .ic { display: none; }\n}" in RC_CSS
    assert "@media (max-width: 400px) {\n  .rc-views { gap: 5px; }\n  .rc-view { padding: 8px 7px; }\n}" in RC_CSS
    assert "@media (min-width: 1101px) and (max-width: 1299px) {" in RC_CSS, "a desktop with the plays beside the rink"
    assert "@media (max-width: 420px) {\n  .hc-view .ic { display: none; }\n}" in HC_CSS


# --- the page in a browser (opt-in) ------------------------------------------------
def test_the_trackers_in_a_browser_at_390_and_1280():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("      (skipped: no Playwright)")
        return
    import rendercheck
    chromium = os.environ.get("CHROMIUM_PATH", "/opt/pw-browsers/chromium")
    fb = _fb_doc()
    fb["event_id"] = "e9"
    fb_strip = {"generated_at": fb["generated_at"], "league": "nfl", "games": [
        {"event_id": "e9", "home": "DAL", "away": "TB", "live": fb["live"], "plays_state": "ok"}]}
    mlb = _mlb_doc()
    mlb.update({"generated_at": fb["generated_at"], "home_name": "Detroit Tigers", "away_name": "New York Yankees", "plays": [],
                "live": {"state": "live", "home_score": 2, "away_score": 3, "outs": 1, "balls": 2, "strikes": 2, "bases": [1]}})
    mlb_strip = {"generated_at": fb["generated_at"], "games": [{"game_pk": 777001, "home": "DET", "away": "NYY", "live": mlb["live"]}]}
    serve = lambda body: (lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(body)))
    srv, port = rendercheck._serve()
    try:
        with sync_playwright() as pw:
            kw = {"args": ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-background-networking"]}
            if os.path.exists(chromium):
                kw["executable_path"] = chromium
            browser = pw.chromium.launch(**kw)
            try:
                for width in (390, 1280):
                    ctx = browser.new_context(viewport={"width": width, "height": 900}, is_mobile=width < 600,
                                              has_touch=width < 600, service_workers="block")
                    page = ctx.new_page()
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    # Nothing leaves the machine: fonts, logos and faces are refused.
                    page.route(lambda url: not url.startswith(f"http://127.0.0.1:{port}/"), lambda r: r.abort())
                    page.route("**/data/pbp/nfl_e9.json*", serve(fb))
                    page.route("**/data/live_nfl.json*", serve(fb_strip))
                    page.route("**/data/pbp/mlb_777001.json*", serve(mlb))
                    page.route("**/data/live_mlb.json*", serve(mlb_strip))
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/nfl/e9", wait_until="load")
                    page.wait_for_selector(".gc-drive [data-gc-fd]", timeout=15000)
                    page.evaluate("document.querySelectorAll('#tour-overlay, .tour-pop').forEach((n) => n.remove())")
                    # The card shows the one field that fits it.
                    shown = page.evaluate("""[...document.querySelectorAll('.gc-drive .gc-fd-svg')]
                        .filter((s) => getComputedStyle(s).display !== 'none').map((s) => s.classList.contains('narrow') ? 'narrow' : 'wide')""")
                    assert shown == (["narrow"] if width < 600 else ["wide"]), shown
                    assert page.evaluate("""[...document.querySelectorAll('.gc-drive .gc-fd-svg')]
                        .find((s) => getComputedStyle(s).display !== 'none').getBoundingClientRect().height""") > 100
                    # The drive on the photograph sits exactly on it, at every width.
                    page.wait_for_selector(".pbp-park [data-gc-art]", state="attached", timeout=5000)
                    boxes = page.evaluate("""(() => { const p = document.querySelector('.pbp-park');
                        const r = (e) => { const b = e.getBoundingClientRect(); return [b.x, b.y, b.width, b.height].map((v) => Math.round(v)); };
                        return [r(p.querySelector('.pbp-photo')), r(p.querySelector('[data-gc-art]'))]; })()""")
                    assert boxes[0] == boxes[1], boxes
                    # Replay (the photograph's) draws both again, and both balls run.
                    page.click(".pbp-park [data-gc-replay]")
                    assert page.query_selector(".gc-drive .gc-fd-ball animateTransform"), "the card's ball runs again"
                    assert page.query_selector(".pbp-park .gc-art-ball animateTransform"), "and the photograph's"
                    page.click('.pbp-tab[data-pbp-tab="plays"]')
                    page.wait_for_selector(".gc-chart .gc-dc-row", state="attached", timeout=5000)
                    assert page.evaluate("""[...document.querySelectorAll('.gc-chart .gc-fd-svg')]
                        .find((s) => getComputedStyle(s).display !== 'none').querySelectorAll('.gc-dc-row').length""") == 4
                    assert page.evaluate("document.scrollingElement.scrollWidth") <= width
                    page.goto(f"http://127.0.0.1:{port}/index.html#pbp/mlb/777001", wait_until="load")
                    page.wait_for_selector(".gc-pz .gc-pz-dot", timeout=15000)
                    assert len(page.query_selector_all(".gc-pz-svg .gc-pz-dot")) == 4
                    assert len(page.query_selector_all(".gc-pz-row")) == 5
                    assert len(page.query_selector_all(".pbp-park [data-gc-art] .gc-art-dot")) == 4, "the same four on the ballpark"
                    page.click(".pbp-park [data-gc-pz-replay]")
                    assert page.query_selector(".gc-pz-svg animate"), "the at-bat flies in again"
                    assert page.query_selector(".pbp-park [data-gc-art] animate"), "on the ballpark too"
                    assert page.evaluate("document.scrollingElement.scrollWidth") <= width
                    assert not errors, errors
                    ctx.close()
            finally:
                browser.close()
    finally:
        srv.shutdown()


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
