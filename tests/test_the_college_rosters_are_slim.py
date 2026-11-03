"""The college rosters file carries a field only when it says something
(rosters_build.slim_rows).

The 30 October audit: rosters_cfb.json held every college roster in one
file — 41,878 players across 492 schools, 13.3 MB — and the Rosters page and
the player search parse all of it on the phone. Since 3 November a free
account opens it too. A per-team split does not fit: both searches match a
name across the whole league. Most of every row was an empty status, a
false flag or a null, and without them the file is about 5.6 MB. What these
hold:

  * a row keeps who, where and what position always; drops None, False and
    "" — never a 0, which is a value (a rookie's years, a jersey, a game
    count) — and a depth-chart position that only repeats his position;
  * the build applies it to college, and to college only;
  * the page draws a slim row exactly as it drew the full one, in both of
    the Rosters page's layouts;
  * the server's roster readers answer the same from a slim file as from
    the full one.

Run directly: `python3 tests/test_the_college_rosters_are_slim.py`
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import rosters_build as RB                                       # noqa: E402

FULL = [
    {"player": "Keelon Russell", "team": "ALA", "position": "QB", "depth_pos": "QB", "depth_order": None,
     "status": "", "unavailable": False, "injury_status": "", "questionable": False, "injury": "",
     "rookie": False, "years_exp": None, "number": "12", "age": None, "games": 18, "last_seen": "2026-10-24",
     "headshot": "https://a.espncdn.com/i/headshots/college-football/players/full/5141629.png"},
    {"player": "Zero Day", "team": "ALA", "position": "WR", "depth_pos": "SLOT", "depth_order": 2,
     "status": "Questionable", "unavailable": False, "injury_status": "Q", "questionable": True,
     "injury": "Ankle", "rookie": True, "years_exp": 0, "number": "0", "age": 19, "games": 0,
     "last_seen": "", "headshot": ""},
    {"player": "Out Man", "team": "ALA", "position": "", "depth_pos": "", "depth_order": 1,
     "status": "Out", "unavailable": True, "injury_status": "O", "questionable": False, "injury": "Knee",
     "rookie": False, "years_exp": 3, "number": "", "age": None, "games": None, "last_seen": None,
     "headshot": None},
]


def _blob(rows=FULL):
    return {"sport": "cfb", "source": "roster", "feed": "live",
            "teams": {"ALA": {"players": json.loads(json.dumps(rows)), "count": len(rows),
                              "unavailable": 1, "rookies": 1}}}


def _slim():
    return RB.slim_rows(_blob())["teams"]["ALA"]["players"]


def test_a_row_keeps_what_it_says_and_drops_what_it_does_not():
    a, b, c = _slim()
    assert a == {"player": "Keelon Russell", "team": "ALA", "position": "QB", "number": "12", "games": 18,
                 "last_seen": "2026-10-24",
                 "headshot": "https://a.espncdn.com/i/headshots/college-football/players/full/5141629.png"}, a
    # A zero is a value: the rookie's years, the jersey, the games.
    assert b["years_exp"] == 0 and b["number"] == "0" and b["games"] == 0
    assert b["depth_pos"] == "SLOT", "a depth position that says something else is kept"
    assert b["questionable"] is True and b["rookie"] is True and b["age"] == 19
    # Who, where and what position stay even when empty.
    assert c["position"] == "" and c["unavailable"] is True and "headshot" not in c and "games" not in c


def test_the_build_slims_college_and_only_college():
    assert RB.SLIM_SPORTS == ("cfb",)
    keep = (RB.payload_for, RB.connect)
    try:
        RB.connect = lambda: type("C", (), {"close": lambda self: None})()
        RB.payload_for = lambda conn, sport, today=None: dict(_blob(), sport=sport)
        from engine.sources import cfbdata
        keep_teams = cfbdata.fetch_teams

        def _no_feed(*a, **k):
            raise OSError("no network in the suite")
        cfbdata.fetch_teams = _no_feed
        try:
            out = Path(tempfile.mkdtemp())
            RB.write("cfb", out_dir=out)
            cfb = json.loads((out / "rosters_cfb.json").read_text())["teams"]["ALA"]["players"]
            assert cfb == _slim() and "status" not in cfb[0]
            RB.write("nfl", out_dir=out)
            nfl = json.loads((out / "rosters_nfl.json").read_text())["teams"]["ALA"]["players"]
            assert nfl == FULL, "another league's file is untouched"
        finally:
            cfbdata.fetch_teams = keep_teams
    finally:
        RB.payload_for, RB.connect = keep


def _render_rows(rows, by_appearance):
    more = (ROOT / "web" / "js" / "more.js").read_text(encoding="utf-8")
    i = more.index("function rosterPlayerHTML(")
    fn = more[i:more.index("\n}\n", i) + 2]
    js = f"""
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const icon = (n) => `<i class="i-${{n}}"></i>`;
    const nflMap = () => ({{}});
    const playerAvatar = (name, team, o) => `<img data-p="${{name}}" data-t="${{team}}" data-h="${{(o || {{}}).headshot || ""}}">`;
    {fn}
    const rows = {json.dumps(rows)};
    console.log(JSON.stringify(rows.map((p) => rosterPlayerHTML(p, {json.dumps(by_appearance)}))));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_a_slim_row_exactly_as_it_drew_the_full_one():
    for by_appearance in (False, True):
        assert _render_rows(_slim(), by_appearance) == _render_rows(FULL, by_appearance), by_appearance


def test_the_servers_readers_answer_the_same():
    from engine import statlogs
    full_dir, slim_dir = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    (full_dir / "rosters_cfb.json").write_text(json.dumps(_blob()))
    (slim_dir / "rosters_cfb.json").write_text(json.dumps(RB.slim_rows(_blob())))
    assert statlogs._roster_players("cfb", str(full_dir)) == statlogs._roster_players("cfb", str(slim_dir))
    from engine import routes
    web_full, web_slim = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
    for web, d in ((web_full, full_dir), (web_slim, slim_dir)):
        (web / "data").mkdir()
        (web / "data" / "rosters_cfb.json").write_text((d / "rosters_cfb.json").read_text())
    assert routes._roster("cfb", web_full)["teams"]["ALA"]["count"] == 3
    from engine import askbot
    keep = ("position", "depth_pos", "depth_order", "number", "status", "injury", "age", "years_exp", "college")
    # The Ask lookup's answer is the same, less a depth position that only
    # repeated the position beside it.
    for full, slim in zip(FULL, _slim()):
        want = {k: v for k, v in askbot._slim(full, keep).items()
                if not (k == "depth_pos" and v == full["position"])}
        assert askbot._slim(slim, keep) == want, (full, slim)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
