"""On the game page, each team's name opens that team's page.

Ethan, 2026-09-24, circling "Cardinals @ 49ers" at the top of a game
page: "We should add when you click on the teams names it will pull you
to the team page where it shows the whole teams data."

The names go through the door the team search's chips already use,
`[data-team-open]` with the league on the button (`data-team-sport`) —
the one listener that opens `#team/<sport>/<team>`. The team key is the
board's own abbreviation, which `/api/team` matches exactly before it
tries any name.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "styles.css").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i) + 2]


def test_both_names_in_the_header_are_doors():
    page = _fn("renderGamePage")
    head = page[page.index('<div class="gp-teams">'):]
    head = head[:head.index("</div>")]
    assert head.count("gpTeamDoor(") == 2
    assert "${gpTeamDoor(g.away, g.home)} ${score(\"away\")}" in head
    assert "${gpTeamDoor(g.home, g.away)} ${score(\"home\")}" in head


def test_the_door_is_the_team_searchs_door():
    door = _fn("gpTeamDoor")
    assert '<button type="button" class="gp-team"' in door
    assert 'data-team-sport="${escapeAttr(state.sport)}"' in door
    assert 'data-team-open="${escapeAttr(team)}"' in door
    assert 'const pick = e.target.closest && e.target.closest("[data-team-open]");' in APP
    assert "openTeam(pick.dataset.teamSport || _teamState.sport || state.sport," in APP


def test_it_renders_the_name_and_crest_it_replaced():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed")
        return
    prog = "\n".join([
        "const escapeAttr = (s) => String(s);", "const escapeHtml = (s) => String(s);",
        "const teamName = (t) => ({ ARI: 'Cardinals' }[t] || t);",
        "const teamMark = (t, n) => `<i data-mark='${t}' data-size='${n}'></i>`;",
        "const state = { sport: 'nfl' };", _fn("gpTeamDoor"),
        "process.stdout.write(JSON.stringify(gpTeamDoor('ARI')));"])
    out = subprocess.run([node, "-e", prog], capture_output=True, text=True, timeout=60, check=True)
    html = json.loads(out.stdout)
    assert 'data-team-sport="nfl"' in html and 'data-team-open="ARI"' in html
    assert "<i data-mark='ARI' data-size='26'></i>" in html
    assert '<span class="gp-team-name">Cardinals</span>' in html
    assert 'title="Cardinals team page"' in html


def test_it_keeps_the_headings_type_and_reads_as_tappable():
    i = CSS.index(".gp-team {")
    rule = CSS[i:CSS.index("}", i)]
    for bit in ("font: inherit", "color: inherit", "background: none", "min-height: 24px"):
        assert bit in rule, bit
    name = CSS[CSS.index(".gp-team-name {"):]
    assert "text-decoration: underline" in name[:name.index("}")]



def test_the_header_carries_the_cards_lines():
    """Ethan, 2026-09-24, circling the spread · ML · total grid on the Home
    card: "In the second screenshot [the game page], we should be showing
    the info I have circled." The same function draws both."""
    page = _fn("renderGamePage")
    assert "const gpLines = gameMarketsHTML(g, { mlb, isFinal });" in page
    head = page[page.index('<div class="gp-sub">'):page.index('<div class="chips gp-chips">')]
    assert "gpLines}" in head, "under the date, above the chips"
    chips = page[page.index('<div class="chips gp-chips">'):][:900]
    assert '${gpLines ? "" : `<span class="chip">O/U' in chips, "the O/U chip only when the grid is absent"
    assert "${gpLines ? \"\" : g.favorite ?" in chips
    assert ".gp-meta .gc-mkts {" in CSS


def test_the_header_is_dressed_as_the_pick_of_the_day():
    """Ethan, 2026-09-24, beside the Pick of the Day card: "overlay the
    venue on this part like how we do for the pick of the day". The art
    fills the top band and fades into the panel under a gold eyebrow and
    the matchup in the headline serif."""
    page = _fn("renderGamePage")
    assert '<div class="gp-hero is-hero">' in page and 'class="gp-eyebrow"' in page
    hero = CSS[CSS.index(".gp-hero.is-hero { display: block;"):]
    assert "background: var(--grad-gp-fade)" in hero and "z-index: 1" in hero
    assert "font-family: var(--font-headline)" in hero, "the matchup in the POTD's serif"
    assert ".gp-hero.is-hero .gp-sub { font-family: var(--font-mono)" in hero
    assert "--grad-gp-fade: linear-gradient(" in CSS

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
