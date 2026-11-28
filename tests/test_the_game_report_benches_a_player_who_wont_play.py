"""The game report does not name a ruled-out player as one to watch, and
marks a questionable one (engine/availability, every sport, 2026-11-14).

Ethan, 2026-11-14, a screenshot of Miami vs Duke: "our player reports ...
doesn't recognize when a player is injured, so it still tells you that an
injured player could have a good matchup or they could do good that game,
even if they're ruled out ... we also need to be careful when a player is
actually ruled out and ruled questionable ... because we don't want to
judge a game off of a player that may or may not be playing." And: "that
issue ... affects all sports, not just cfb". Malachi Toney, out since 31
October, was under "Who could have a big day" and "Could shine".

One rule, in the shared context both report modules build on:
  * out, doubtful, suspended, every book pulled his props: no read;
  * questionable / day-to-day / game-time: kept, marked, and never the
    headline of the short version;
  * no line in his team's last game and no injury listing: the same mark.

    python3 tests/test_the_game_report_benches_a_player_who_wont_play.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import availability as A                 # noqa: E402


def test_the_injury_words_of_every_league_read_to_one_of_three():
    for raw in ("Out", "OUT", "IR", "Injured Reserve", "Inactive", "Suspended",
                "Long Term Injured Reserve", "O"):
        assert A.word(raw) == A.OUT, raw
    for raw in ("Doubtful", "DOUBTFUL"):
        assert A.word(raw) == A.DOUBTFUL, raw
    for raw in ("Questionable", "GTD", "Game Time Decision", "Day-To-Day", "DTD", "Q"):
        assert A.word(raw) == A.QUESTIONABLE, raw
    for raw in ("Probable", "Active", "Available", "", None, "Healthy"):
        assert A.word(raw) == "", repr(raw)


class _Ctx:
    def __init__(self, reads, scan=None, meta=None, form=None, g=None, sport="cfb"):
        self.reads, self.scan, self.meta = reads, scan or {}, meta or {}
        self.form, self.g, self.sport = form or {}, g or {}, sport
        self.result, self.teams, self.season = {}, ("MIA", "DUKE"), 2026

    def name(self, t):
        return {"MIA": "Miami", "DUKE": "Duke", "ND": "Notre Dame"}.get(t, t)


def test_a_ruled_out_player_gets_no_read():
    c = _Ctx([{"player": "Malachi Toney", "team": "MIA", "pos": "WR", "read": "good", "pro": ["x"]},
              {"player": "Cooper Barkate", "team": "MIA", "pos": "WR", "read": "breakout", "pro": ["y"]}],
             scan={"injuries": [{"player": "Malachi Toney", "status": "Out"}]})
    rows = A.annotate(c)
    assert [r["player"] for r in rows] == ["Cooper Barkate"], "the out man is gone, the other kept"
    assert not rows[0].get("availability"), "a healthy player is unmarked"


def test_every_book_pulled_his_props_counts_as_out():
    c = _Ctx([{"player": "Zay Flowers", "team": "MIA", "pos": "WR", "read": "good", "pro": ["x"]}],
             scan={"injuries": [], "pulled": ["Zay Flowers"]})
    assert A.annotate(c) == [], "no book prices him — treated as out"


def test_a_questionable_player_is_kept_and_marked_and_not_the_headline():
    c = _Ctx([{"player": "Carson Beck", "team": "MIA", "pos": "QB", "read": "good", "pro": ["z"]}],
             scan={"injuries": [{"player": "Carson Beck", "status": "Questionable"}]})
    rows = A.annotate(c)
    assert len(rows) == 1 and rows[0]["availability"] == A.QUESTIONABLE
    assert "only holds if the player plays" in rows[0]["availability_note"]
    assert not A.sure(rows[0]), "the short version may not sum the game up through him"
    # A read with its own questionable status, with nothing on the scan.
    c2 = _Ctx([{"player": "Carson Beck", "team": "MIA", "pos": "QB", "read": "good",
                "own_status": "QUESTIONABLE", "pro": ["z"]}])
    assert A.annotate(c2)[0]["availability"] == A.QUESTIONABLE, "his own listing counts"


def test_a_player_absent_from_his_teams_last_game_is_marked():
    c = _Ctx([{"player": "Cooper Barkate", "team": "MIA", "pos": "WR", "read": "good", "pro": ["y"]},
              {"player": "Elija Lofton", "team": "MIA", "pos": "WR", "read": "good", "pro": ["y"]}],
             form={"Cooper Barkate": {"games": [{"team": "MIA", "day": "2026-11-08", "opp": "ND",
                                                 "where": "away", "season": 2026}]},
                   "Elija Lofton": {"games": [{"team": "MIA", "day": "2026-10-31", "opp": "UNC",
                                               "where": "away", "season": 2026}]}})
    rows = {r["player"]: r for r in A.annotate(c)}
    assert rows["Cooper Barkate"].get("availability") is None, "he played the newest game"
    assert rows["Elija Lofton"]["availability"] == A.MISSED, "his newest game is a week older"
    note = rows["Elija Lofton"]["availability_note"]
    assert "Nov. 8 at Notre Dame" in note and "no stat line" in note, note


def test_the_report_context_runs_every_read_through_it():
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    assert "from .availability import annotate" in src and "self.reads = annotate(self)" in src
    # The short version drops a may-sit read before it ranks the big days.
    i = src.index("def shine_lines(")
    assert "r.get(\"availability\")" in src[i:i + 500]
    page = (ROOT / "web" / "js" / "report.js").read_text(encoding="utf-8")
    assert 'v.status ? `<span class="ms-read-tag gr-status">' in page


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
