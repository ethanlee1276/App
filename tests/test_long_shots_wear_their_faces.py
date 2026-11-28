"""Long Shots wear their players' faces again, every sport (engine/boardfaces).

Ethan, 2026-11-04, a screenshot of NBA Long Shots with Precious Achiuwa and
Andrew Wiggins drawn as initials: "Also the long shot page is missing
headshots for every sport." Since Long Shots became first-scorer picks
(2026-10-31) its rows came off the first-scorer price list, which has no
photo. What these hold:

  * every first-scorer row (the picks, "who scores first", "our numbers")
    gets the photo the board's own prop rows carry for the same player;
  * a player on no other row gets the sport's stored photo, joined on the
    site's normalised name (the curly apostrophe is the same apostrophe);
  * a name two photos claim is settled by the team, or left as initials —
    never somebody else's face; a row with a photo keeps it;
  * the NFL, college and NBA builds all run it, and the page hands the photo
    to the avatar on all three lists.

Run directly: `python3 tests/test_long_shots_wear_their_faces.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import boardfaces as BF                         # noqa: E402

ACH = "https://a.espncdn.com/i/headshots/nba/players/full/3155526.png"
WIG = "https://a.espncdn.com/i/headshots/nba/players/full/3059319.png"


def _nba_board():
    pick = {"player": "Precious Achiuwa", "team": "SAC", "market": "first_basket", "odds": 1400}
    other = {"player": "Andrew Wiggins", "team": "MIA", "market": "first_basket", "odds": 1000}
    return {
        "recommendations": [
            {"player": "Precious Achiuwa", "team": "SAC", "market": "reb", "headshot": ACH},
            {"player": "Andrew Wiggins", "team": "MIA", "market": "pts", "headshot": WIG},
        ],
        "first_basket": {"rows": [pick, other], "picks": [pick, other],
                         "ours": [{"player": "Andrew Wiggins", "team": "MIA", "game": "MIA@LAC"}]},
        "long_shots": [pick, other],
    }


def test_the_first_basket_picks_wear_the_faces_their_props_carry():
    board = _nba_board()
    n = BF.fill(board, "nba", stored={})
    fb = board["first_basket"]
    assert fb["picks"][0]["headshot"] == ACH and fb["picks"][1]["headshot"] == WIG
    assert board["long_shots"][0]["headshot"] == ACH, "the Long Shots list is the same rows"
    assert fb["ours"][0]["headshot"] == WIG, "our-numbers rows too"
    assert n == 3, "a pick that is also a row is counted once"


def test_a_player_on_no_other_row_gets_the_sports_stored_photo():
    board = {"first_td": {"rows": [{"player": "Ja’Marr Chase", "team": "CIN"}], "picks": [], "ours": []}}
    stored = {"jamarr chase": "https://static.www.nfl.com/image/upload/chase.png"}
    assert BF.fill(board, "nfl", stored=stored) == 1
    assert board["first_td"]["rows"][0]["headshot"].endswith("chase.png"), \
        "the curly apostrophe joins the straight one"


def test_a_name_two_faces_claim_is_settled_by_the_team_or_left_alone():
    board = {
        "recommendations": [
            {"player": "Jalen Williams", "team": "OKC", "headshot": "https://x.example.com/okc.png"},
            {"player": "Jalen Williams", "team": "DEN", "headshot": "https://x.example.com/den.png"},
        ],
        "first_basket": {"rows": [{"player": "Jalen Williams", "team": "DEN"},
                                  {"player": "Jalen Williams", "team": "PHX"}], "picks": [], "ours": []},
    }
    BF.fill(board, "nba", stored={})
    den, phx = board["first_basket"]["rows"]
    assert den["headshot"] == "https://x.example.com/den.png"
    assert "headshot" not in phx, "initials beat somebody else's face"


def test_a_row_with_a_face_keeps_it_and_nothing_breaks_the_build():
    keep = {"player": "Andrew Wiggins", "team": "MIA", "headshot": "https://x.example.com/own.png"}
    board = _nba_board()
    board["first_basket"]["rows"].append(keep)
    BF.fill(board, "nba", stored={})
    assert keep["headshot"] == "https://x.example.com/own.png"
    assert BF.fill(None, "nba", stored={}) == 0
    assert BF.fill({"first_td": {"rows": [None, "x", {"team": "CIN"}]}}, "nfl", stored={}) == 0
    assert BF.fill({"long_shots": [{"player": "Nobody", "team": "XXX"}]}, "nfl", stored={}) == 0


def test_the_stored_photos_are_read_only_when_a_row_still_needs_one():
    board = _nba_board()
    asked = []
    real = BF.stored_faces
    BF.stored_faces = lambda sport, conn=None: asked.append(sport) or {}
    try:
        BF.fill(board, "nba")
    finally:
        BF.stored_faces = real
    assert asked == [], "every row found its face on the board"


def test_every_build_runs_it_and_the_page_draws_it_on_all_three_lists():
    nfl = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    cfb = (ROOT / "cfb_build.py").read_text(encoding="utf-8")
    nba = (ROOT / "nba_build.py").read_text(encoding="utf-8")
    assert "_bfaces.fill(result, 'nfl')" in nfl
    assert "_bfaces.fill(out, 'cfb', conn)" in cfb
    assert "_bfaces.fill(out, args.league, conn)" in nba
    js = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")

    def fn(name):
        i = js.index(f"function {name}(")
        return js[i:js.index("\n}\n", i)]
    assert "headshot: r.headshot" in fn("longShotCard")
    assert "headshot: r.headshot" in fn("watchlistHTML")
    assert "headshot: r.headshot" in fn("firstOursHTML"), "the our-numbers rows drew initials whatever they carried"


def _say(fn):
    """Run `fn` with stdout captured. Returns (value, printed)."""
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        value = fn()
    return value, buf.getvalue()


def _blow_up(*_a, **_k):
    raise RuntimeError("the photo table is gone")


def test_a_failure_says_so_and_a_quiet_board_says_nothing():
    """`fill`'s 0 is also what a board whose rows all have faces answers,
    and `stored_faces`'s {} what a sport with no stored photos answers
    (tests/test_silent_failures). Each failure names itself in the build
    log, the build still gets its board, and a quiet run prints nothing."""
    from engine import rosters
    real_bf, real_fm = BF.board_faces, rosters.face_map
    try:
        BF.board_faces = _blow_up
        n, said = _say(lambda: BF.fill(_nba_board(), "nba", stored={}))
        assert n == 0, "a failure still returns a count; the build carries on"
        assert "Long Shots faces skipped" in said and "nba" in said and "RuntimeError" in said, said
        BF.board_faces = real_bf

        rosters.face_map = _blow_up
        got, said = _say(lambda: BF.stored_faces("cfb", conn=object()))
        assert got == {} and "stored photos unreadable" in said and "cfb" in said and "RuntimeError" in said, said
        rosters.face_map = lambda conn, sport: {}
        got, said = _say(lambda: BF.stored_faces("cfb", conn=object()))
        assert got == {} and not said.strip(), f"an empty store complained: {said!r}"
    finally:
        BF.board_faces, rosters.face_map = real_bf, real_fm
    _n, said = _say(lambda: BF.fill(_nba_board(), "nba", stored={}))
    assert not said.strip(), f"a working fill complained: {said!r}"


def test_the_runbook_and_the_catchup_check_it():
    line = ("cd /srv/qellys && sudo -u qellys python3 -c \"import json; d=json.load(open('data/built/nba.json')); "
            "r=(d.get('first_basket') or {}).get('rows') or []; print(sum(1 for x in r if x.get('headshot')), 'of', len(r))\"")
    assert line in (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text(encoding="utf-8")
    assert line in (ROOT / "tools" / "catchup.sh").read_text(encoding="utf-8")
    assert "catchup.sh JX" in (ROOT / "docs" / "RUN_NEXT.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, f in tests:
        try:
            f()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
