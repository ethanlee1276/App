"""The play-by-play page to Ethan's render.

Ethan, 2026-09-05, with the render: "Look how I also gave the live games
at the top, that looks pretty good. Also see if we can do the animations
and shit that's in the middle with the park. It's the animation of the
ball getting hit. Also u can see the play by play on the right."

Three things, pinned: the strip of the league's games across the top,
live first; the park with the batted ball's arc animated over the game
page's own art, scaled by the park's fences; and the rail reading at
the pitch, grouped by half-inning with the batting team, each row timed.
The arc's geometry is exercised for real in node (skipped without it);
the rest are source pins on the page.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _fn(name):
    i = APP.index(f"function {name}(")
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the strip ------------------------------------------------------------------
def test_the_strip_reads_the_leagues_fast_scoreboard_live_first():
    body = _fn("pbpStripGames")
    assert "const url = LIVE_FAST[league];" in body
    assert "await boardFetch(url, { cache: \"no-store\" })" in body, "counted toward the wire-down banner"
    assert "({ live: 0, scheduled: 1, final: 2 })" in body, "live first, then by first pitch, then finals"
    assert "start_time" in body


def test_a_strip_chip_is_a_door_only_when_there_is_something_to_read():
    body = _fn("pbpStripHTML")
    assert 'const door = !!id && (lv.state === "live" || lv.state === "final");' in body
    assert 'data-pbp="${escapeAttr(id)}"' in body and '" disabled"' in body
    assert "teamMarkIn(league, abbr, 16)" in body
    page = _fn("renderPbpPage")
    assert 'host.querySelectorAll(".pbp-chip.door")' in page
    assert "openPbp(league, el.dataset.pbp)" in page


# --- the ball in flight -----------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    src = "\n".join(_fn(n) for n in ("pbpFieldToArt", "pbpWallPoint", "pbpFenceFt", "pbpFlight"))
    const = APP[APP.index("const PBP_POLE_DEG"):APP.index("\n", APP.index("const PBP_POLE_DEG"))]
    prog = f"{const}\n{src}\n{js}"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_fence_is_the_parks_own_feet_with_a_default_park():
    got = _node("""
      console.log(JSON.stringify({
        cf: pbpFenceFt({lf_ft: 310, cf_ft: 420, rf_ft: 302}, 0),
        lf: pbpFenceFt({lf_ft: 310, cf_ft: 420, rf_ft: 302}, -47.8),
        rf: pbpFenceFt({lf_ft: 310, cf_ft: 420, rf_ft: 302}, 47.8),
        dflt: [pbpFenceFt(null, 0), pbpFenceFt({}, -47.8)],
      }));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["cf"] == 420 and got["lf"] == 310 and got["rf"] == 302, got
    assert got["dflt"] == [400, 330], got


def test_a_ball_short_of_the_wall_lands_inside_it_and_a_homer_lands_past_it():
    got = _node("""
      const park = {lf_ft: 330, cf_ft: 400, rf_ft: 330};
      const inside = pbpFlight({distance: 379, launch_speed: 102.4, trajectory: "line_drive",
                                x: 125.42, y: 100}, park);        // straight to centre
      const homer = pbpFlight({distance: 440, trajectory: "fly_ball", x: 125.42, y: 100}, park);
      const nothing = pbpFlight({launch_speed: 90}, park);        // no distance: no arc
      const wall = pbpWallPoint(0);
      console.log(JSON.stringify({inside, homer, nothing, wall}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["nothing"] is None
    i, h, w = got["inside"], got["homer"], got["wall"]
    assert i["over"] is False and h["over"] is True
    assert abs(i["phi"]) < 1e-6, "straight to centre is 0°"
    # Home plate (the art's) sits low; the wall at centre sits high; the
    # landing point of a 379-ft ball to a 400-ft fence sits just short.
    assert i["H"][1] > i["L"][1] > w[1], (i["H"], i["L"], w)
    assert h["L"][1] < w[1], "past the wall is past the wall"
    assert i["len"] > 0


def test_pull_and_push_lean_the_landing_toward_the_lines():
    got = _node("""
      const park = {lf_ft: 330, cf_ft: 400, rf_ft: 330};
      const left = pbpFlight({distance: 300, x: 60, y: 120}, park);    // toward left field
      const right = pbpFlight({distance: 300, x: 190, y: 120}, park);  // toward right field
      console.log(JSON.stringify({left: left.L, right: right.L, lphi: left.phi, rphi: right.phi}));""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["lphi"] < 0 < got["rphi"]
    assert got["left"][0] < 120 < got["right"][0], got


def test_the_arc_animates_and_respects_reduced_motion():
    body = _fn("pbpArcSVG")
    assert '<animateMotion dur="1.2s" fill="freeze"><mpath href="#${id}"/></animateMotion>' in body
    assert 'attributeName="stroke-dashoffset"' in body, "the path draws on"
    assert 'matchMedia("(prefers-reduced-motion: reduce)").matches' in body
    assert "PBP_TRAJ[hit.trajectory]" in body and "mph" in body and "ft" in body
    assert "escapeHtml(label)" in body


def test_the_park_is_the_game_pages_own_art_in_the_leagues_colours():
    body = _fn("pbpParkHTML")
    assert 'ballpark(game, { w: 640, h: 400 })' in body
    assert 'court(game, { w: 640, h: 400 })' in body and 'stadium(game, { w: 640, h: 400 })' in body
    assert "window.ACTIVE_TEAMS = teamsForSport(league);" in body
    assert "window.ACTIVE_TEAMS = keep;" in body, "restored for the page underneath"
    assert 'league === "mlb" && hitRow && hitRow.hit' in body, "the arc is baseball's"
    assert "pbpArcSVG(hitRow.hit, (boardGame || {}).park)" in body, "scaled by the park's fences"
    page = _fn("renderPbpPage")
    assert 'r.kind === "atbat" && r.hit' in page, "the newest ball in play is the one drawn"


# --- the situation strip ---------------------------------------------------------------
def test_the_strip_under_the_park_reads_the_at_bat_and_the_fast_rows_count():
    body = _fn("pbpSituationHTML")
    assert 'if (league !== "mlb") return "";' in body
    for field in ("cur.batter", "cur.pitcher", "lv.balls", "lv.strikes", "lv.outs", "miniDiamond(lv.bases)"):
        assert field in body, field
    assert "const cur = d.current || {};" in body


def test_faces_come_off_the_board_only_when_standing_on_that_league():
    body = _fn("pbpFaces")
    assert "if (state.sport !== league || !state.data) return {};" in body
    assert "state.data.recommendations" in body and "state.data.long_shots" in body


# --- the rail ------------------------------------------------------------------------
def test_the_baseball_rail_reads_events_grouped_by_half_inning_with_the_batting_team():
    body = _fn("pbpBaseballGroups")
    assert "(d.events && d.events.length) ? d.events" in body
    assert '(d.plays || []).map((p) => ({ ...p, kind: "atbat" }))' in body, "an older file still reads"
    assert 'r.half === "T" ? d.away : r.half === "B" ? d.home : ""' in body
    assert "batting" in body and "groups.forEach((g) => g.rows.reverse());" in body
    assert "return groups.reverse();" in body


def test_a_pitch_row_has_a_call_dot_and_an_at_bat_row_the_batting_teams_mark():
    body = _fn("pbpRowHTML")
    assert 'if (r.kind === "pitch") {' in body
    assert "PBP_CALL_KIND(r.code)" in body and 'class="pbp-dot ${kind}"' in body
    assert "teamMarkIn(league, batting, 18)" in body
    assert "pbpTime(r.time)" in body
    assert "h.launch_speed" in body and "h.distance" in body
    kinds = APP[APP.index("const PBP_CALL_KIND"):APP.index("function pbpBaseballGroups")]
    assert '"ball"' in kinds and '"foul"' in kinds and '"inplay"' in kinds and '"strike"' in kinds


def test_the_rail_shows_the_newest_forty_and_offers_the_rest():
    body = _fn("pbpRailHTML")
    assert "const PEEK = 40;" in body
    assert "_pbpShowAll ? Infinity : PEEK" in body
    assert 'id="pbp-more"' in body and "View full play by play" in body
    assert "playsHTML({ plays: g.rows })" in body, "football and hoops keep the card's rows"
    page = _fn("renderPbpPage")
    assert "_pbpShowAll = true; renderPbpPage();" in page


def test_win_probability_is_the_boards_track_when_the_board_matches():
    page = _fn("renderPbpPage")
    assert "const boardGame = (state.sport === league && state.data)" in page
    assert "boardGame && boardGame.line_track ? `<div class=\"card\">${lineTrackHTML(boardGame)}</div>` : \"\"" in page
    assert 'id="pbp-game-door"' in page and "openGame(g.dataset.gid)" in page


def test_the_page_still_reads_only_the_deep_file_and_never_prose():
    page = _fn("renderPbpPage")
    assert "boardFetch(`data/pbp/${encodeURIComponent(league)}_${encodeURIComponent(event)}.json`" in page
    assert "await fetch(" not in page and "paidFetch" not in page
    for prose in ("p.text", "p.description", "shortDescription", "r.description"):
        assert prose not in APP[APP.index("function pbpRowHTML"):APP.index("async function renderPbpPage")], prose
    assert 'if (lv.state === "live") again();' in page
    assert 'if (state.view !== "pbp") return;' in page


def test_the_styles_exist():
    for cls in (".pbp-strip", ".pbp-chip.active", ".pbp-layout", ".pbp-hero", ".pbp-park > svg",
                ".pbp-sit", ".pbp-face", ".pbp-row.atbat", ".pbp-dot.ball", ".pbp-dot.strike",
                ".pbp-dot.foul", ".pbp-dot.inplay", ".pbp-rail"):
        assert cls in CSS, cls


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
