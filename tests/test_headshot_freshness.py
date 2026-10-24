"""A man on IR wore last season's photograph.

Ethan, 2026-09-04: "I see some players on nfl don't have any and a lot
are last year headshots."

`build_slate` fills faces from three sources, first one wins: this
season's weekly stats, then the roster, then last season's stats. The
comment above it says the order is "the order a face is most likely to
be current", and it is — the bug was in what the middle source contains.

THE MIDDLE SOURCE WAS `roster_index`, WHICH IS FILTERED TO ACT. That
filter is right where it lives: `roster_index` decides who gets a prop
BUILT, and its own docstring says "a player on reserve or already cut
should not have a prop built for him off last season's numbers". Reading
FACES out of it inherited the filter for free. So every player on IR,
PUP, the practice squad or suspended had no current-season face at all,
fell through to last season's weekly stats, and wore a photograph a year
old on a live card.

`headshot_map` reads the SAME roster file with no status filter, and has
said why since the day it was written: "a face on the usage board does
not stop being his face because he moved to IR". It was wired only to
the fantasy pages. Now it is the board's middle source too.

IT IS ALSO UNCONDITIONAL. `roster` is populated inside `if carry:`, so a
build without that flag had no middle source whatsoever and sent EVERY
face to last season's file. Production passes --carry; nothing should
depend on that for a photograph.

Run directly: `python3 tests/test_headshot_freshness.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.sources import nflverse as nv                     # noqa: E402

THIS_YEAR = "https://static.nfl.com/2026/hurt-guy.png"
LAST_YEAR = "https://static.nfl.com/2025/hurt-guy-OLD.png"
ACT_FACE = "https://static.nfl.com/2026/act.png"


def _rosters(season):
    """One roster file: an active player and a man on reserve, both
    carrying a CURRENT-season portrait."""
    if season != 2026:
        return []
    return [{"full_name": "Active Guy", "status": "ACT", "team": "BUF",
             "position": "WR", "headshot_url": ACT_FACE},
            {"full_name": "Hurt Guy", "status": "RES", "team": "BUF",
             "position": "WR", "headshot_url": THIS_YEAR}]


class _Rosters:
    def __enter__(self):
        self.real = nv.load_rosters
        nv.load_rosters = _rosters
        return self

    def __exit__(self, *_):
        nv.load_rosters = self.real


def _chain(middle):
    """The three-source fill exactly as `build_slate` performs it, on a
    week-one board: no games played, so this season's stats are empty."""
    out: dict = {}
    for name, url in middle.items():
        out.setdefault(name, url)
    for r in [{"player_display_name": "Hurt Guy", "headshot_url": LAST_YEAR}]:
        out.setdefault(r["player_display_name"], r["headshot_url"])
    return out


# --- the two readers of one file ---------------------------------------------
def test_the_act_filter_hides_a_player_who_still_has_a_face():
    """The premise. If `roster_index` ever stops filtering, this test is
    the one that says the bug it caused is gone for a different reason."""
    with _Rosters():
        assert sorted(nv.roster_index(2026)) == ["Active Guy"]
        assert sorted(nv.headshot_map(2026)) == ["Active Guy", "Hurt Guy"]


def test_the_reserve_player_gets_this_years_photograph():
    """THE BUG, and the fix, through the same arithmetic the builder
    runs. Executed rather than source-read: a face silently one year old
    raises nothing and looks like a working card."""
    with _Rosters():
        old_middle = {n: r["headshot"]
                      for n, r in nv.roster_index(2026).items()
                      if r.get("headshot")}
        stale = _chain(old_middle)
        fresh = _chain(nv.headshot_map(2026))
    assert stale["Hurt Guy"] == LAST_YEAR, \
        "the premise is gone — the old middle source was not stale"
    assert fresh["Hurt Guy"] == THIS_YEAR, \
        "a player on reserve still wears last season's photograph"
    assert fresh["Active Guy"] == ACT_FACE, "the active player regressed"


def test_the_board_reads_the_unfiltered_map():
    import inspect
    src = inspect.getsource(nv.build_slate)
    assert "headshot_map(season)" in src, \
        "the board is back on a status-filtered source for faces"
    i = src.index("headshots: dict[str, str] = {}")
    seg = src[i:i + 900]
    assert "for name, row in roster.items()" not in seg, \
        "the ACT-filtered roster is feeding faces again"


def test_the_face_source_does_not_depend_on_carry():
    """`roster` is populated only under `if carry:`. A photograph is not
    a modelling decision and must not ride on a modelling flag."""
    import inspect
    src = inspect.getsource(nv.build_slate)
    carry_at = src.index("if carry:")
    face_at = src.index("headshot_map(season)")
    seg = src[carry_at:face_at]
    assert seg.count("\n    ") > 0, "sanity: the two sites are in one function"
    line = [ln for ln in src.splitlines() if "headshot_map(season)" in ln][0]
    assert len(line) - len(line.lstrip()) == 4, \
        f"the face fill is nested under a conditional: {line!r}"


def test_an_unreachable_roster_costs_faces_not_the_build():
    """`headshot_map` swallows DataUnavailable by design — "faces are
    polish, so an unreachable roster file is an empty map, not an
    error". The board must still build."""
    from engine.sources.fetch import DataUnavailable

    def boom(season):
        raise DataUnavailable("nflverse down")
    real = nv.load_rosters
    nv.load_rosters = boom
    try:
        assert nv.headshot_map(2026) == {}
    finally:
        nv.load_rosters = real


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
