"""A listed player's newest word reaches his game's page (step ABT, 22 November 2026).

Ethan, the Sunday morning: "we need to do better on reporting on injuries, figuring out which players are in or
out for all sports, for all game reports". ESPN's injury board files a blurb with each designation, and on a
Sunday morning the blurb moves while the designation stands: at 7:24 AM ET Baker Mayfield was still listed
"Questionable" and his blurb said "Mayfield (foot/right thumb) is slated to play in Sunday's game against the
Lions, Ian Rapoport of NFL Network reports"; Ladd McConkey's and Carnell Tate's said the same within the quarter
hour. The report watch (engine/reportwatch) kept only designations, so none of it reached a game's page. What
these hold, on the morning's own blurbs:

  * a blurb leans "in" or "out" on its player's next game, or neither: one about the rest of a game under way,
    one naming another day's game (eight NBA players read "Day-To-Day" that morning with a blurb about the
    night before), and one that leans both ways (about someone else) lean neither;
  * a listed player whose blurb changed and leans is an update with his designation on both sides and the
    word beside it; an unchanged blurb, an old one, a player cleared or already out, the league's first look
    and the first look after this step (a player seen before it) are not;
  * the game's report and its page say it: "questionable (foot strain), now expected to play, per Ian
    Rapoport of NFL Network", the page's line marked as good news;
  * nothing moves a number: the board reads the designation, as before.

    python3 tests/test_a_listed_players_newest_word_reaches_his_game.py
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gamereport as GR, reportwatch as RW                 # noqa: E402

NOW = dt.datetime(2026, 11, 22, 15, 0, tzinfo=dt.timezone.utc).timestamp()   # Sunday, 10 AM ET

MAYFIELD = ("Mayfield (foot/right thumb) is slated to play in Sunday's game against the Lions, Ian Rapoport of "
            "NFL Network reports.")


def _iso(hours):
    return dt.datetime.fromtimestamp(NOW + hours * 3600, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def test_a_blurb_leans_on_his_next_game_or_neither():
    cases = [
        (MAYFIELD, "Sunday", "in"),
        ("McConkey (back) is expected to play in Sunday's game against the Jets, Ian Rapoport of NFL Network "
         "reports.", "Sunday", "in"),
        ("Head coach Sean McVay said Saturday that Williams is tending to a sore toe but is expected to play "
         "Wednesday against the Packers, Sarah Barshop of ESPN reports.", "Wednesday", "in"),
        ("Pettersson (upper body) isn't expected to play against Chicago on Sunday, per Canucks play-by-play "
         "announcer Brendan Batchelor.", "Sunday", "out"),
        ("Smith (illness) is out for Friday's game against the Wizards, Joel Lorenzi of The Athletic reports.",
         "Friday", "out"),
        ("Rice (knee) is not expected to play Sunday.", "Sunday", "out"),
        # Another day's game: read on the Sunday, about the Saturday.
        ("Tatum (rest) has been ruled out for Saturday's game against the Kings.", "Monday", None),
        ("Towns (illness) won't play in Saturday's game versus the Trail Blazers.", "Monday", None),
        # The rest of a game under way.
        ("Melton (thigh) has been ruled out for the rest of Sunday's game against the Vikings, Rob Demovsky of "
         "ESPN.com reports.", "Sunday", None),
        # Both ways: about someone else.
        ("With Omar Cooper (ankle) ruled out, Mitchell is expected to play an elevated role on offense Sunday "
         "against the Chargers.", "Sunday", None),
        ("Rice (knee) is listed as questionable.", "Sunday", None),
        ("", "Sunday", None),
    ]
    for text, day, want in cases:
        assert RW.lean(text, day) == want, (text, RW.lean(text, day))
    assert RW.reported_by(MAYFIELD) == "Ian Rapoport of NFL Network"
    assert RW.reported_by("Smith (illness) is out, Joel Lorenzi of The Athletic reports.") == "Joel Lorenzi of The Athletic"
    assert RW.reported_by("Rice (knee) is not expected to play Sunday.") == ""


BOARD = {"games": [{"away": "TB", "home": "DET", "kickoff": _iso(3), "away_name": "Tampa Bay Buccaneers",
                    "home_name": "Detroit Lions"}]}


def _row(status="Questionable", comment="Mayfield (foot/right thumb) is listed as questionable.", hours=-2):
    return [{"team": "Tampa Bay Buccaneers", "player": "Baker Mayfield", "pos": "QB", "status": status,
             "injury": "Foot Strain", "date": _iso(hours), "comment": comment}]


def _run(state, rows, at=0.0):
    return RW.run(now=NOW + at, leagues=("nfl",), boards={"nfl": BOARD}, state_path=state, publish=False,
                  fetch_injuries=lambda _l: rows, fetch_news=lambda _l: [], fetch_rss=lambda _l: [])


def _ups(doc):
    return doc["leagues"]["nfl"]["games"]["TB@DET"]["updates"]


def test_a_changed_blurb_that_leans_is_an_update_beside_the_same_designation():
    state = Path(tempfile.mkdtemp()) / "state.json"
    assert _ups(_run(state, _row())) == [], "the first look only remembers"
    assert _ups(_run(state, _row(), at=60)) == [], "nothing changed"
    doc = _run(state, _row(comment=MAYFIELD, hours=-0.5), at=120)
    ups = _ups(doc)
    assert [(u["player"], u["from"], u["to"], u["word"], u["by"]) for u in ups] == \
        [("Baker Mayfield", "Questionable", "Questionable", "in", "Ian Rapoport of NFL Network")], ups
    assert _ups(_run(state, _row(comment=MAYFIELD, hours=-0.5), at=180)) == ups, "said once, kept for the week"
    # Ruled out after it: the designation's own update, as before.
    later = _ups(_run(state, _row(status="Out", comment="Mayfield won't play Sunday.", hours=0), at=240))
    assert [(u["from"], u["to"], u.get("word")) for u in later][:1] == [("Questionable", "Out", None)], later


def test_what_is_not_a_word():
    def fresh():
        st = Path(tempfile.mkdtemp()) / "state.json"
        _run(st, _row())
        return st
    # An old blurb.
    st = fresh()
    assert _ups(_run(st, _row(comment=MAYFIELD, hours=-40), at=60)) == []
    # Another day's game.
    st = fresh()
    assert _ups(_run(st, _row(comment="Mayfield won't play in Saturday's game.", hours=-1), at=60)) == []
    # A player already out has nothing left to lean.
    st = Path(tempfile.mkdtemp()) / "state.json"
    _run(st, _row(status="Out"))
    assert _ups(_run(st, _row(status="Out", comment="Mayfield won't play Sunday.", hours=-1), at=60)) == []
    # A player seen before this step (no "said" kept): the look after the deploy only remembers.
    st = Path(tempfile.mkdtemp()) / "state.json"
    _run(st, _row())
    doc = json.loads(st.read_text())
    for v in doc["leagues"]["nfl"]["seen"].values():
        v.pop("said", None)
    st.write_text(json.dumps(doc))
    assert _ups(_run(st, _row(comment=MAYFIELD, hours=-0.5), at=60)) == []
    assert _ups(_run(st, _row(comment=MAYFIELD + " More.", hours=-0.4), at=120)) != [], "and the next word is said"
    assert RW.next_days([{"home": "DET", "away": "TB", "start": NOW + 3 * 3600}]) == {"DET": "Sunday", "TB": "Sunday"}


def test_the_report_and_the_page_say_it():
    u = {"at": "2026-11-22T12:30:00Z", "team": "TB", "player": "Baker Mayfield", "pos": "QB", "from": "Questionable",
         "to": "Questionable", "word": "in", "by": "Ian Rapoport of NFL Network", "injury": "Foot Strain"}
    c = GR.Ctx({"away": "TB", "home": "DET"}, {}, sport="nfl", names={"TB": "Buccaneers", "DET": "Lions"})
    assert GR.update_words(c, u) == ("Baker Mayfield, the Buccaneers' quarterback: questionable (foot strain), now "
                                     "expected to play, per Ian Rapoport of NFL Network, seen Sun 7:30 AM ET"), \
        GR.update_words(c, u)
    out = dict(u, word="out", by="")
    assert GR.update_words(c, out).endswith("questionable (foot strain), now expected to miss the game, seen Sun 7:30 AM ET")
    node = shutil.which("node") or "/opt/node22/bin/node"
    if not Path(node).exists():
        print("  SKIP node not installed")
        return
    r = {"game": "TB@DET", "watch_at": "2026-11-22T12:00:00Z", "minutes": 4, "sections": [
        {"key": "card", "title": "Our picks", "blocks": [{"type": "picks", "items": [
            {"rank": 1, "player": "Baker Mayfield", "team": "TB", "pick": "Baker Mayfield over 245.5 passing yards",
             "price": "DraftKings -115", "chance": 0.58}]}]}]}
    watch = {"checked_at": "2026-11-22T13:00:00Z", "news": [], "updates": [u, dict(out, player="Mike Evans")]}
    js = ("const vm = require('vm'); const fs = require('fs');"
          "const esc = (s) => String(s == null ? '' : s).replace(/[&<>\"']/g, (c) => '&#' + c.charCodeAt(0) + ';');"
          "const ctx = { window: {}, escapeHtml: esc, escapeAttr: esc, icon: () => '', playerAvatar: () => '',"
          " slugify: (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-'), teamName: (t) => t };"
          "vm.createContext(ctx);"
          f"vm.runInContext(fs.readFileSync({json.dumps(str(ROOT / 'web' / 'js' / 'report.js'))}, 'utf8'), ctx);"
          f"const html = ctx.window.QBReport.html({json.dumps(r)}, {{ watch: {json.dumps(watch)}, sport: 'nfl' }});"
          "const card = html.slice(html.indexOf('gr-watch'), html.indexOf('gr-card'));"
          "process.stdout.write(JSON.stringify(card.split('<li').slice(1)));")
    got = subprocess.run([node, "-e", js], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-1500:]
    may, evans = json.loads(got.stdout)
    may, evans = " ".join(may.split()), " ".join(evans.split())
    assert may.startswith('class="up"') and \
        "questionable (foot strain), now expected to play, per Ian Rapoport of NFL Network" in may, may
    assert "In this report" not in may, "good news needs no warning"
    assert evans.startswith('class="down"') and "now expected to miss the game" in evans, evans


def test_nothing_moves_a_number():
    src = (ROOT / "engine" / "reportwatch.py").read_text(encoding="utf-8")
    assert "Nothing here moves a number: the board reads the designation, as before." in src
    for f in ("engine/sources/injuries.py", "engine/injurymerge.py", "engine/pipeline.py"):
        assert "reportwatch" not in (ROOT / f).read_text(encoding="utf-8"), f


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
