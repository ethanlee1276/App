"""A game script card opens the read underneath it.

Ethan, 2026-09-03: *"on the game script page, we should be able too click
on the games and see a deeper dive into the game with more information
and shit."*

THE DATA WAS ALREADY THERE AND HALF OF IT WAS DRAWN NOWHERE.
`fantasy.game_scripts` has been building `home_def_epa` / `away_def_epa`
all along and the card never showed either — which is the half that
decides a start/sit, because a good offence into a good defence is not
the bet a good offence into a bad one is. The detail crosses them: both
are EPA/play on the same scale, so offence minus the defence it faces is
the matchup in one number.

WHAT IS NEW IN THE PAYLOAD is per-side role and lean, and they come from
`gamescript.for_team` rather than a second if-tree on the page. The card
prints the GAME's archetype; the detail has to say what that archetype
means for THIS club, and those two drifting apart is exactly the bug
engine/gamescript.py was extracted to prevent (tests/test_gamescript.py,
2026-09-02).

NOTHING IS INVENTED. A field the build could not fill — pbp not ingested,
a team with no profile — prints as a dash. A 0.00 EPA reads as "league
average" and a missing one is not that, which is the same rule
`Weather.measured` and `Game.total_is_posted` enforce elsewhere.

AND THE SIGN IS THE POINT. The first cut of the crossing wrote
`offence - defence`, which rated one offence HIGHER the STOUTER the
defence across from it — the matchup inverted, on the page people read to
decide who to start. `def_epa` is the EPA a defence ALLOWS, the same play
value bucketed under the defending team, so the two ADD; and they add
around `teamcontext.league_means`, because EPA/play has no natural zero
and the build now ships the one it measured. Three tests below execute
that arithmetic rather than grepping it.

IN PLACE, NOT A ROUTE. The page is a COMPARISON — eight games read
against each other — and a route answers one question by throwing that
away. The detail also comes off the same row the card does, so there is
no second fetch to justify a page, and a page would imply there is.

Run directly: `python3 tests/test_script_detail.py`
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
CSS = open(os.path.join(ROOT, "web", "css", "styles.css"), encoding="utf-8").read()

from engine.gamescript import for_team                        # noqa: E402


# --- the payload -----------------------------------------------------------
def test_each_sideline_gets_its_own_role_and_lean():
    """KC −3 in a 42.5 game: one favourite, one dog, and the archetype
    read from each bench rather than once for the game."""
    home = for_team(-3.0, 42.5, "KC", "DEN", "KC")
    away = for_team(-3.0, 42.5, "KC", "DEN", "DEN")
    assert home["role"] == "favorite" and away["role"] == "underdog"
    assert home["lean"] and away["lean"] and home["lean"] != away["lean"]
    assert abs(home["team_implied"] - 22.8) < 0.05
    assert abs(away["team_implied"] - 19.8) < 0.05


def test_the_build_puts_them_on_the_row():
    """One definition: the page reads these, it does not recompute them."""
    src = open(os.path.join(ROOT, "engine", "fantasy.py"), encoding="utf-8").read()
    i = src.index("def game_scripts(")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "from .gamescript import for_team" in body, \
        "the page would have to re-derive the lean, which is how the two drift"
    for k in ('"home_role"', '"away_role"', '"home_lean"', '"away_lean"'):
        assert k in body, k


# --- the door --------------------------------------------------------------
def test_the_card_head_is_a_door():
    i = APP.index("const scriptCards")
    block = APP[i:i + 3000]
    assert "data-gs-toggle" in block, "the card does not open anything"
    assert 'role="button"' in block and 'tabindex="0"' in block, \
        "it is a mouse-only door"
    assert 'aria-expanded="false"' in block


def test_the_detail_starts_closed():
    """Sixteen games each opening a full read would bury the comparison
    the page exists for."""
    i = APP.index("const gsDetail")
    assert 'class="gs-detail" hidden' in APP[i:i + 400], \
        "the detail is not hidden until asked for"


def test_the_toggle_is_wired_and_keyboard_reachable():
    i = APP.index("A game script opens its own detail in place")
    seg = APP[i:i + 1600]
    assert 'closest("[data-gs-toggle]")' in seg
    assert "box.hidden = !box.hidden" in seg
    assert 'setAttribute("aria-expanded"' in seg
    assert 'e.key !== "Enter"' in seg, "Enter and space do not open it"


# --- what the detail says --------------------------------------------------
def test_it_draws_the_defence_the_card_never_did():
    i = APP.index("const gsDetail")
    seg = APP[i:i + 2200]
    assert "home_def_epa" in seg and "away_def_epa" in seg, \
        "the detail still leaves the defensive half of the matchup unused"


def test_offence_is_crossed_with_the_defence_it_actually_faces():
    """away offence vs HOME defence, home offence vs AWAY defence. Getting
    this backwards would read plausibly and be exactly wrong."""
    i = APP.index("const gsDetail")
    seg = APP[i:i + 2200]
    assert "[s.away, s.away_role, s.away_lean, s.away_epa, s.home_def_epa]" in seg
    assert "[s.home, s.home_role, s.home_lean, s.home_epa, s.away_def_epa]" in seg


def test_a_missing_number_is_a_dash_and_not_a_zero():
    """0.00 EPA reads as league average. Absent is not average — the same
    rule Weather.measured and Game.total_is_posted enforce."""
    i = APP.index("const gsNum")
    seg = APP[i:i + 300]
    assert "undefined" in seg and '"—"' in seg
    assert "Number(v).toFixed(dp)" in seg


def test_it_reaches_the_usage_board():
    """A game detail on a FANTASY page that does not name a player is
    trivia — the usage board is why anyone is on this page."""
    i = APP.index("const gsPlayers")
    seg = APP[i:i + 900]
    assert "d.usage" in seg
    assert "u.team === home || u.team === away" in seg


def test_the_players_are_read_with_the_fields_the_build_emits():
    """The first cut of this block read `u.pos` and `u.share_last`. Neither
    exists — `usage_movers` emits `position`, `last` and `metric` — so every
    row would have printed a bare name and a dash, and nothing would have
    failed to say so. A field name invented at the render is the quietest
    way to ship an empty column, so both ends are pinned here."""
    src = open(os.path.join(ROOT, "engine", "fantasy.py"), encoding="utf-8").read()
    i = src.index('"metric": "carry share"')
    emitted = src[src.rindex("out.append({", 0, i):i + 700]
    i = APP.index("const gsPlayers")
    seg = APP[i:i + 1200]
    for field in ("position", "last", "metric", "player", "team"):
        assert f'"{field}":' in emitted, f"usage_movers stopped emitting {field}"
        assert f"u.{field}" in seg, f"the detail does not read u.{field}"
    for ghost in ("u.pos ", "u.share_last"):
        assert ghost not in seg, f"{ghost.strip()} is not a field on a usage row"


def test_the_share_uses_the_pages_own_formatter():
    """`pct` is what the usage table two sections up prints these same
    shares with. A second formatter here is how 34% and 34.2% end up on
    one screen for one number."""
    i = APP.index("const gsPlayers")
    assert "pct(u.last)" in APP[i:i + 1200], \
        "the detail formats a share by hand instead of through pct"


def test_the_pace_line_says_it_is_rough():
    i = APP.index("const gsPlays")
    seg = APP[i:i + 700]
    assert "3240" in seg, "the plays estimate lost its clock"
    assert "About" in seg, "an estimate is being printed as a fact"


# --- the matchup arithmetic ------------------------------------------------
def test_a_defence_number_is_what_it_allows():
    """The fact the whole crossing hangs on, pinned at its source.

    `nflpbp` accumulates the SAME play value `v` under the defending team
    that it accumulates under the offence — so `def_epa` is EPA allowed,
    a positive one is a LEAKY defence, and offence and defence share one
    scale and one mean. Read the other way, every matchup on this page
    inverts."""
    src = open(os.path.join(ROOT, "engine", "sources", "nflpbp.py"),
               encoding="utf-8").read()
    i = src.index("defense.setdefault((dt, wk)")
    seg = src[i:i + 160]
    assert "d[0] += v" in seg, \
        "the defence bucket no longer accumulates the offence's own play value"


def test_the_build_ships_the_zero_point():
    """`league_means` is the codebase's own answer to '+0.06 EPA/play means
    nothing on its own'. The page cannot centre the crossing without it,
    and a page that guesses the zero point is inventing a number."""
    src = open(os.path.join(ROOT, "engine", "fantasy.py"), encoding="utf-8").read()
    i = src.index("def game_scripts(")
    seg = src[i:src.index("def upcoming_schedule(")]
    assert "league_means(profs)" in seg, "the league mean is no longer measured"
    assert '"epa_mean"' in seg, "the row does not carry the zero point"
    assert "if epa_mean is not None else None" in seg, \
        "an absent league mean is being shipped as a number"


def _gs_edge(off, dfn, mean):
    """Run the page's own gsEdge, not a Python restatement of it."""
    i = APP.index("  const gsNum = (v, dp, sign)")
    block = APP[i:APP.index("  const scriptCards", i)]
    src = (block + "\nconsole.log(JSON.stringify(gsEdge("
           + json.dumps(off) + "," + json.dumps(dfn) + "," + json.dumps(mean) + ")));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=60)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-1500:]
    html = json.loads(res.stdout)
    m = re.search(r"[-+]\d+\.\d+", html)
    return float(m.group(0)) if m else None


def test_a_soft_defence_helps_the_offence_it_faces():
    """THE BUG THIS EXISTS FOR. The first cut wrote `off - def`, which had
    one offence looking BETTER the STOUTER the defence across from it —
    the matchup exactly inverted, on a page people read to decide who to
    start. Executed rather than grepped, because the sign is the point."""
    if not shutil.which("node"):
        return
    mean, off = -0.012, 0.12
    soft = _gs_edge(off, 0.06, mean)     # allows +0.06/play: leaky
    stout = _gs_edge(off, -0.09, mean)   # allows -0.09/play: stingy
    assert soft is not None and stout is not None
    assert soft > stout, (f"the same offence rates {soft} into a soft defence "
                          f"and {stout} into a stout one — inverted")


def test_the_crossing_is_measured_against_the_league_and_not_zero():
    """(off - mean) + (allowed - mean), to the hundredth the page prints."""
    if not shutil.which("node"):
        return
    got = _gs_edge(0.12, 0.04, -0.012)
    assert abs(got - ((0.12 + 0.012) + (0.04 + 0.012))) < 0.005, got


def test_no_league_mean_draws_no_number():
    """Same rule as every other absent field here: a dash or nothing, never
    a zero point assumed into existence."""
    if not shutil.which("node"):
        return
    assert _gs_edge(0.12, 0.04, None) is None


# --- the styles it needs ---------------------------------------------------
def test_the_two_sidelines_stack_on_a_phone():
    """Two EPA crossings side by side at 360px is four numbers in 150px."""
    i = CSS.index(".gs-sides")
    assert "grid-template-columns: 1fr 1fr" in CSS[i:i + 200]
    j = CSS.rindex(".gs-sides")
    assert "grid-template-columns: 1fr;" in CSS[j:j + 120], \
        "the phone block does not collapse the two sidelines"


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
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
