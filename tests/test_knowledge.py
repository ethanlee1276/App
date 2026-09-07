"""Knowledge tiers on every reason — NFL_MODEL §2.3.

    "Label your knowledge tiers in every output: (a) verified current data;
    (b) stable historical data; (c) your own inference. The reader must
    always be able to see which is which, BECAUSE THE FIX FOR A BAD BET
    DEPENDS ON WHICH TIER FAILED."

That clause is a debugging argument, not a presentation one. A pick that
lost on a stale usage number needs a feed fix; one that lost because a
1,499-spot comp did not repeat needs nothing; one that lost on the model's
own game-script inference is the only one of the three that means the
MODEL is wrong. All three used to render as identical grey sentences.

Run directly: `python3 tests/test_knowledge.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import knowledge as kn                              # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_the_three_tiers_are_the_specs_three():
    assert set(kn.TIERS) == {"measured", "historical", "inference"}


def test_each_tier_is_recognised_from_a_real_reason():
    """Verbatim from the live boards, not invented for the test."""
    assert kn.tier_of(
        "Usage bridge: 6.8 targets/gm x 7.62 per target") == "measured"
    assert kn.tier_of(
        "Comps: 1,499 past spots with this line went 57% to the under"
    ) == "historical"
    assert kn.tier_of(
        "Game script: 7.5-pt favorite - projected leading script"
    ) == "inference"


def test_an_unknown_reason_gets_no_tier_rather_than_a_guess():
    """THE RULE THE WHOLE MODULE TURNS ON. A classifier that guesses puts
    a confident "measured" on a sentence it has never seen, and a label
    that is sometimes wrong poisons the labels that are right — the reader
    cannot tell which to trust, so none of them can be trusted. A missing
    label says "nobody has classified this yet", which is true."""
    assert kn.tier_of("Some brand new reason nobody has registered") is None
    assert kn.tier_of("") is None
    assert kn.tier_of(None) is None


def test_the_unlabelled_are_listed_so_the_registry_can_be_extended():
    got = kn.unregistered(["Usage bridge: x", "Brand new thing: y",
                           "Brand new thing: z"])
    assert got == ["Brand new thing"]


def test_the_mix_counts_what_a_pick_is_standing_on():
    """A pick standing on three inferences and no measurement is a
    different object from one standing on three measurements."""
    m = kn.mix(["Usage bridge: a", "Game script: b", "Comps: c",
                "unregistered thing"])
    assert m == {"measured": 1, "inference": 1, "historical": 1,
                 "unlabelled": 1}


def test_stamp_writes_a_parallel_list_and_leaves_reasons_alone():
    """A parallel field rather than a rewrite: every existing reader of
    `reasons` keeps working and the preservation baseline does not see a
    shape change on 1,600 strings."""
    result = {"recommendations": [
        {"reasons": ["Usage bridge: a", "unregistered thing"]}]}
    n = kn.stamp(result)
    card = result["recommendations"][0]
    assert card["reasons"] == ["Usage bridge: a", "unregistered thing"]
    assert card["reason_tiers"] == ["measured", None]
    assert n == 1


def test_stamp_covers_the_long_shots_board_too():
    result = {"long_shots": [{"reasons": ["Comps: a"]}],
              "game_bets": [{"reasons": ["Game script: b"]}]}
    kn.stamp(result)
    assert result["long_shots"][0]["reason_tiers"] == ["historical"]
    assert result["game_bets"][0]["reason_tiers"] == ["inference"]


def test_stamp_survives_a_card_with_no_reasons_at_all():
    result = {"recommendations": [{"player": "x"}, {"reasons": []},
                                  "not even a dict"]}
    assert kn.stamp(result) == 0


def test_the_site_never_reclassifies_in_the_browser():
    """One home for the registry. A mirrored copy in JavaScript would be
    correct the day it was written and silently wrong the first time a
    module adds a reason — on the side nothing runs tests against."""
    js = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    assert "reason_tiers" in js, "the site must read the stamped field"
    # The registry's OWN keys, lowercased, which is the exact form a
    # mirrored classifier would have to contain. Checked against those
    # rather than against the prose: a first draft of this test looked for
    # "Game script" and tripped on the "Game scripts" section heading,
    # which has nothing to do with classifying anything.
    for prefix, _ in kn.PREFIXES:
        assert f'"{prefix}"' not in js and f"'{prefix}'" not in js, (
            f"{prefix!r} is registry data and belongs in "
            f"engine/knowledge.py, not in the browser")


def test_both_builds_stamp_before_they_write():
    """A tier computed after the JSON is written reaches nobody."""
    for f in ("mlb_build.py", "nfl_build.py"):
        src = open(os.path.join(ROOT, f), encoding="utf-8").read()
        assert "_tier_stamp(result)" in src, f
        # The write is gate.publish() since 2026-08-16 — it puts the full
        # board outside the web root and the redacted one on the public
        # path. The rule this test is about did not change: a tier
        # computed after the board is written reaches nobody.
        assert src.index("_tier_stamp(result)") < src.index(
            "gate.publish(result, args.out)"), f


def test_the_four_the_live_board_caught_are_classified_from_their_source():
    """Ethan's board on 2026-08-15: 75.7% labelled, four openings unknown.

    Each is registered by reading the module that WRITES it, which is the
    rule this file's subject insists on — a guessed tier is worse than no
    tier, because a label that is sometimes wrong poisons the ones that
    are right. The evidence, in one line each:

      * "Official season split"  engine/mlb/platoon.py — THIS season's
        official SLG vs LHP/RHP from the MLB Stats API, quoted with its
        own PA count. Moves through the season, so (a), by the same
        argument already applied to the Statcast leaderboards.
      * "Market moving toward"   engine/linemoves.py — movement measured
        between our own stored snapshots and now. Retrieved and stamped.
      * "Cold stretch"           engine/mlb/streaks.py — written by the
        same function as "Hot stretch", from the same last-N game logs.
      * "Coherence"              engine/mlb/pipeline.py — reconcile_triple
        nudging our own hits/TB/HR projections until they stop
        contradicting each other. No new fact about the world enters.

    And the one that must NOT move with them: "Platoon edge" is the
    handedness matchup itself, which genuinely does not change, so it
    stays (b). Registering the season split as (a) while leaving that as
    (b) is the distinction, not an inconsistency.
    """
    cases = {
        "Official season split: slugs lefties (.412 SLG in 88 PA, +9% vs his blend)": "measured",
        "Market moving toward the Over — 2.5 to 2.5 (-115 to -130) since our first snapshot": "measured",
        "Cold stretch — last 10 games 0.71 vs his usual 1.02. Measured league-wide": "measured",
        "Coherence: total bases raised to stay above hits": "inference",
        "Platoon edge — LHB vs RHP": "historical",
    }
    for reason, want in cases.items():
        got = kn.tier_of(reason)
        assert got == want, f"{reason[:40]!r} -> {got}, expected {want}"


def test_the_low_end_of_the_barrel_leaderboard_is_labelled_too():
    """Ethan's preflight, 2026-08-18: 98.7% of 8,344 labelled, and every
    listed miss was one shape — the barrel leaderboard read from the
    OTHER end. "Elite barrel rate" was registered on 2026-08-10; the same
    Statcast source arguing against a bet was not, and the percentage
    riding in the opening made each value look like a distinct miss.
    Both emitters, both classified from their source (homeruns.py and
    statcast.py, the same season leaderboard as the elite line — moves
    weekly, so measured)."""
    for reason in ("Low barrel rate 3% — soft contact",
                   "Low barrel rate 3.4% — power profile is thin"):
        assert kn.tier_of(reason) == "measured", reason



def test_a_park_factor_is_labelled_whatever_the_venue_is_called():
    """The pattern matched the word "park", not the shape of the phrase.

    So "Oracle Park boosts home runs" was labelled and "Dodger Stadium
    boosts home runs" was not — and most venues are a Stadium, a Field or
    a Centre. On Ethan's live board that one mistake was the bulk of 37
    unregistered openings.

    The five phrases below are every one engine/mlb/parks.py and
    engine/mlb/homeruns.py can emit, read off the f-strings rather than
    imagined. A park factor is a multi-season measured constant, so (b).
    """
    for venue in ("Dodger Stadium", "Rogers Centre", "Progressive Field",
                  "Coors Field", "Oracle Park", "T-Mobile Park"):
        for phrase in ("boosts home runs (+5% vs average)",
                       "suppresses home runs (-5% vs average)",
                       "plays hitter-friendly (+7% runs)",
                       "plays pitcher-friendly (-4% runs)",
                       "plays big for home runs (+12% HR factor)",
                       "elevates strikeouts (+4%)"):
            reason = f"{venue} {phrase}"
            assert kn.tier_of(reason) == "historical", reason



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
