"""Tom Brady on a 2026 draft board.

Ethan, 2026-08-24, on the live site: "the fantasy draft is using old
retired players. it used tom brady and kenneth gainwell in it and they
dont play in the nfl anymore."

TWO FAULTS STACKED. The kit builds from latest_season() — the newest
season INGESTED, which nothing compared to the newest season there IS.
On a box whose NFL ingest stopped years ago, "last season's usage run
forward" silently meant 2021's. And the roster layer already knew the
truth: apply_current_rosters stamps `roster_flag: "inactive"` on exactly
these rows — but a flag only annotates, and the mock simulator drafts
straight from the board, so simulated rooms spent real picks on retired
men.

THE TWO FIXES, EACH TESTED HERE:

  * A player Sleeper positively marks inactive is DROPPED from the kit
    before tiers and replacement are computed — nobody can draft him, so
    he belongs at no rank. A free agent (active, teamless) keeps his
    flag and his slot: somebody may yet sign him. A usage row with no
    Sleeper match at all is kept, because a name-join failure must never
    erase a real player.
  * usage_freshness() compares the built season against the season the
    calendar says it should be, and the page wears the answer as a
    banner instead of letting a four-year-old board pass as current.

Run directly: `python3 tests/test_draft_pool.py`
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import db                                        # noqa: E402
from engine.fantasy import usage_freshness                   # noqa: E402
from engine.fantasy_draft import build_draft_kit             # noqa: E402

APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _row(player, team, pos, wk, market, value):
    return {"sport": "nfl", "season": 2025, "period": f"{wk:03d}",
            "game_id": f"{team}-{wk:03d}", "player": player, "team": team,
            "opponent": "OPP", "position": pos, "home": 1,
            "market": market, "value": value}


def _seed(conn, n_weeks=10):
    rows = []
    wr_targets = {"WR One": 12, "WR Two": 11, "WR Three": 7,
                  "WR Four": 6, "WR Five": 5, "WR Six": 4}
    rb_carries = {"RB One": 18, "RB Two": 15, "RB Three": 9, "RB Four": 6}
    for wk in range(1, n_weeks + 1):
        for name, t in wr_targets.items():
            rows += [_row(name, "AAA", "WR", wk, "targets", t),
                     _row(name, "AAA", "WR", wk, "fp_ppr", t * 1.8)]
        for name, c in rb_carries.items():
            rows += [_row(name, "BBB", "RB", wk, "carries", c),
                     _row(name, "BBB", "RB", wk, "fp_ppr", c * 0.9)]
        rows += [_row("TE Guy", "AAA", "TE", wk, "targets", 6),
                 _row("TE Guy", "AAA", "TE", wk, "fp_ppr", 6 * 1.8)]
    db.upsert_player_logs(conn, rows)
    return conn


def _sleeper(**overrides):
    """A players blob shaped like Sleeper's: id -> record. Everyone from
    the seed except TE Guy (deliberately unknown to Sleeper), everyone
    active and rostered unless overridden."""
    blob = {}
    names = ["WR One", "WR Two", "WR Three", "WR Four", "WR Five",
             "WR Six", "RB One", "RB Two", "RB Three", "RB Four"]
    for i, name in enumerate(names):
        first, last = name.split(" ", 1)
        pos = name[:2]
        rec = {"first_name": first, "last_name": last, "full_name": name,
               "position": pos, "team": "KC", "active": True,
               "status": "Active", "search_rank": i + 1}
        rec.update(overrides.get(name, {}))
        blob[str(1000 + i)] = rec
    return blob


def _kit(sleeper):
    conn = _seed(db.connect(":memory:"))
    return build_draft_kit(conn, 2025, sleeper=sleeper)


def _names(rows):
    return [r["player"] for r in rows]


# --- the drop --------------------------------------------------------------

def test_a_retired_player_is_off_the_board_entirely():
    """BOTH doors. The fixture gives WR One search_rank 1, so this test
    caught the second hole on its first run: the usage side dropped him
    and draftmarket.place_missing put him straight back as a market row,
    because Sleeper keeps search_rank on retired players. from_sleeper
    now skips explicit inactives, so the market door is closed too."""
    kit = _kit(_sleeper(**{"WR One": {"active": False, "team": None,
                                      "status": "Inactive"}}))
    assert "WR One" not in _names(kit["board"]), \
        "a player Sleeper marks inactive is still on the draft board"
    assert "WR One" not in _names(kit["tiers"]["WR"]), \
        "the retired player still holds a tier slot"
    assert "WR One" not in _names(kit["sleepers"])
    assert kit["dropped_inactive"] == {"n": 1, "players": ["WR One"]}


def test_the_drop_happens_before_ranks_and_replacement():
    """WR Two inherits WR1 — the board is re-ranked over people who
    exist, not left with a hole at the top."""
    kit = _kit(_sleeper(**{"WR One": {"active": False, "team": None}}))
    wr = kit["tiers"]["WR"]
    assert wr and wr[0]["player"] == "WR Two" and wr[0]["pos_rank"] == 1


def test_an_active_free_agent_keeps_his_slot():
    """Teamless but active is the free-agent case: somebody may sign
    him, so he is draftable and stays — the roster_flag layer annotates
    him downstream."""
    kit = _kit(_sleeper(**{"RB One": {"team": None}}))
    assert "RB One" in _names(kit["board"])
    assert kit["dropped_inactive"]["n"] == 0


def test_a_player_sleeper_has_never_heard_of_is_kept():
    """TE Guy is in our usage and absent from the blob. A name-join
    failure must never erase a real player."""
    kit = _kit(_sleeper(**{"WR One": {"active": False, "team": None}}))
    assert "TE Guy" in _names(kit["board"])


def test_no_blob_means_no_drops():
    kit = _kit(None)
    assert "WR One" in _names(kit["board"])
    assert kit["dropped_inactive"] == {"n": 0, "players": []}


# --- the freshness check ---------------------------------------------------

def test_the_calendar_decides_what_current_means():
    # August 2026 sits in the offseason gap: the season a usage board
    # should be built from is 2025, the one that just finished.
    assert usage_freshness(2025, "2026-08-24") is None
    assert usage_freshness(2021, "2026-08-24") == \
        {"have": 2021, "expected": 2025}
    # Mid-season, the current season's own accruing weeks are current.
    assert usage_freshness(2026, "2026-11-01") is None
    assert usage_freshness(None, "2026-08-24") is None


def test_the_build_stamps_it_and_says_the_fix():
    src = open(os.path.join(ROOT, "fantasy_build.py"), encoding="utf-8").read()
    assert '"usage_stale": fantasy.usage_freshness(season)' in src, \
        "the payload no longer says whether its season is current"
    assert "python3 ingest.py nfl --seasons" in src, \
        "the build log stopped printing the command that fixes staleness"


def test_the_page_wears_the_staleness_above_the_tiers():
    i = APP.index("d.usage_stale")
    seg = APP[i:i + 800]
    for phrase in ("built from the ${staleU.have} season",
                   "has not been loaded yet"):
        assert phrase in seg, f"the banner lost: {phrase}"
    # And it renders ahead of the tab content, not in a footer.
    assert APP.index("const staleU") < APP.index(
        'subtabbedHTML("fantasy"'), "the banner sank below the tabs"


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
