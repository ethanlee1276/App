"""A lineup is confirmed when BOTH cards are posted, not one.

Ethan, 2026-08-14, on a board two hours from first pitch: "why is it still
showing lineup pending".

Chasing that produced the opposite finding — the flag was not pending too
long, it was clearing too early, and for half the hitters in every game.

HOW THE HOLE WORKED. `build_live_slate` read one field:

    lineups_confirmed = bool(box["teams"]["home"]["battingOrder"])

Home only. Then pass 2 built hitter props for BOTH sides, and for a side
whose card had not posted it fell back to `projected_lineup` — last game's
batting order, a guess we make so the morning board has something to price.

§5's hold is two conditions joined by OR (rules.py):

    prop.lineup_spot == 0 or not game.lineups_confirmed

and the half-posted state defeated both at once for the away team. The
projected spot is a real number, so the first condition passed. The home
card was in, so the second passed too. Every away hitter was recommendable
off a guessed batting order with nothing official behind it — and the site
said "lineups confirmed" while it happened.

Home cards post first often enough that this is not a rare corner: MLB
clubs post at their own pace and the home side is usually first out.

WHY `all` AND NOT A COUNT. Two sides, both required — a count would invite
"one is enough for the props on that side", which is a different and much
larger change: the flag is game-level and every consumer treats it that
way. Making it honest is this commit; making it per-side is not.

Also pinned here: the second half of the same report — the pull estimate
that read 2:21 PM under a first pitch of 2:20.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from engine.mlb.sources import statslogs as sl        # noqa: E402


def _box(home, away):
    """A boxscore with whichever cards are posted."""
    return {"teams": {
        "home": {"battingOrder": [1, 2, 3] if home else []},
        "away": {"battingOrder": [4, 5, 6] if away else []},
    }}


def _slate(box):
    """Run the orchestrator offline and hand back the one game."""
    sched = {"dates": [{"games": [{
        "gamePk": 1, "venue": {"name": "Wrigley Field"},
        "teams": {"home": {"team": {"id": 112}}, "away": {"team": {"id": 143}}},
    }]}]}
    saved = (sl._get_json, sl.fetch_boxscore, sl.park_weather,
             sl.projected_lineup)
    sl._get_json = lambda url, cache, ttl=600: sched
    sl.fetch_boxscore = lambda pk: box
    sl.park_weather = lambda key: None
    sl.projected_lineup = lambda tid, date: []
    try:
        return sl.build_live_slate("2026-08-14", hitter_markets=())
    finally:
        (sl._get_json, sl.fetch_boxscore, sl.park_weather,
         sl.projected_lineup) = saved


# --- the flag itself --------------------------------------------------------
def test_both_cards_posted_is_confirmed():
    assert _slate(_box(True, True)).games[0].lineups_confirmed is True


def test_home_card_only_is_not_confirmed():
    """The exact bug. Before this commit it read True."""
    assert _slate(_box(True, False)).games[0].lineups_confirmed is False


def test_away_card_only_is_not_confirmed():
    """The symmetric case, which the old code got right by accident — it
    never looked at the away side at all."""
    assert _slate(_box(False, True)).games[0].lineups_confirmed is False


def test_neither_card_is_not_confirmed():
    assert _slate(_box(False, False)).games[0].lineups_confirmed is False


def test_a_missing_boxscore_is_not_confirmed():
    """No feed is not a posted lineup. An empty dict has to fall to False
    rather than throw or default open."""
    assert _slate({}).games[0].lineups_confirmed is False


def test_the_source_reads_both_sides():
    """Guards the regression directly: a future edit that drops back to a
    single-side read passes every fixture above only until someone changes
    the fixture."""
    src = open(os.path.join(ROOT, "engine", "mlb", "sources", "statslogs.py"),
               encoding="utf-8").read()
    i = src.index("lineups_confirmed = ")
    block = src[i:i + 220]
    assert '"home"' in block and '"away"' in block, \
        "the confirmation check is back to one dugout"


# What the flag then DOES — a projected hitter held, and released once the
# card posts — is already pinned end-to-end by
# `test_mlb_live.test_projected_lineup_holds_recommendations`. It is the
# same assertion either way, so it is not restated here; this file's job is
# the input that test takes for granted.


# --- the pull estimate ------------------------------------------------------
def test_next_pull_is_predicted_under_the_rules_that_will_be_in_force():
    """Same report, other half: the board said "today's pricing starts
    11:50 AM" and "next pull 2:21 PM" for a 2:20 first pitch.

    Nothing was actually late. `next_pull_at` was computed with the pacer's
    state at BUILD time — 11:38 AM, off-peak, where the interval is
    stretched ×4 — and then printed as a prediction about a moment that
    would be inside prime time. The pacer re-decides every cycle; the
    estimate was the only frozen thing on the page.

    The fix asks the question at the moment being predicted, and floors the
    answer at the window's own opening."""
    src = open(os.path.join(ROOT, "mlb_build.py"), encoding="utf-8").read()
    i = src.index("next_pull_at")
    block = src[max(0, i - 1400):i + 200]
    assert "PRIME_BEFORE_S" in block, "the estimate no longer knows when the window opens"
    assert re.search(r"prime_window\(\s*kicks,\s*_at\s*\)", block), \
        "the window state is still read at build time, not at the predicted time"
    assert re.search(r"max\(\s*_next,\s*_opens\s*\)", block), \
        "the estimate can still land before pricing opens"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
