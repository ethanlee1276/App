"""College passing gets its denominator: attempts, from rows already read.

Ethan, 2026-09-07, on the data a winning model needs: "Player usage data
for props. NFL routes, target share and air yards from Next Gen Stats and
play-by-play, where the model uses snap counts and weekly totals today.
College target and rush share from play-by-play, where today's logs have
passing yards but no attempts."

Rush share college already had (`carries`). Attempts it did not, and the
parser's own note said why: "``pass_yds`` accumulates from completions
with no attempts column". That was true of the parser and false of the
feed. An attempt is a completion, an incompletion or an interception, and
the last two are named columns this file was ALREADY reading to settle
which of two names threw the ball. Counting them gives college the
denominator `engine.nflusage.OPP_BY_MARKET` maps ``pass_yds`` onto, so a
passing projection can be built as recent volume times season-long
efficiency rather than from yards alone.

It also ends one piece of survivorship: with an opportunity column behind
it, a quarterback who attempted passes for no net yards now writes a
``pass_yds`` row instead of vanishing from his own log.

Run directly: `python3 tests/test_cfb_pass_attempts.py`
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.sources import cfbstats as C                     # noqa: E402
from engine import nflusage                                  # noqa: E402

#: ``points: 0`` is the house fixture's own value and it is load-bearing:
#: with real points on the game, `week_modes` audits the week's touchdown
#: coverage, finds none in a fixture that scores nobody, and DROPS every
#: row. A test asserting "this market is absent" would then pass because
#: the whole week vanished, which proves nothing about the market. Zero
#: points means "no final score to audit against", so the rows survive
#: and an absent market is really absent.
GAMES = {"401": {"home": "UGA", "away": "OSU", "home_name": "Georgia",
                 "away_name": "Ohio State", "period": "2024-09-14",
                 "points": 0}}


def _play(**kw):
    row = {"game_id": "401", "season": "2024", "week": "3",
           "team": "Georgia", "opponent": "Ohio State",
           "yards_to_goal": "40", "down": "1", "distance": "10"}
    row.update(kw)
    return row


def _parse(rows):
    return C.parse_player_stats(rows, 2024, GAMES, None)


def _value(out, player, market):
    for row in out["rows"]:
        if row["player"] == player and row["market"] == market:
            return row["value"]
    return None


def _absent(out, player, market):
    """This market has no row — and the parse kept SOMETHING, so the
    absence is about the market rather than about a dropped week."""
    assert out["rows"], "the whole parse came back empty; absence proves nothing"
    return _value(out, player, market) is None


def _completion(yds="14", **kw):
    return _play(completion_player="Carson Beck", reception_player="Arian Smith",
                 completion_yds=yds, reception_yds=yds, **kw)


def test_a_sack_is_not_a_pass_attempt():
    """College scoring and the NFL's agree, which is why this is a subset
    of the columns that identify a passer rather than all of them."""
    assert C.ATTEMPT_COLUMNS == ("incompletion_player",
                                 "interception_thrown_player")
    assert "sack_taken_player" in C.QB_COLUMNS
    assert "sack_taken_player" not in C.ATTEMPT_COLUMNS
    out = _parse([_play(sack_taken_player="Carson Beck", rush_player="Nate Frazier",
                        rush_yds="8")])
    assert _absent(out, "Carson Beck", "pass_att")


def test_every_kind_of_attempt_is_counted_once():
    out = _parse([_completion(), _completion(yds="7"),
                  _play(incompletion_player="Carson Beck"),
                  _play(interception_thrown_player="Carson Beck")])
    assert _value(out, "Carson Beck", "pass_att") == 4.0
    assert _value(out, "Carson Beck", "pass_yds") == 21.0


def test_a_picked_off_pass_counts_once_however_the_feed_spells_it():
    """Feeds disagree about whether an interception also sets the
    incompletion column. Counting per COLUMN would inflate attempts by
    the interception count under one convention; counting per ROW is
    right under both."""
    both = _play(incompletion_player="Carson Beck",
                 interception_thrown_player="Carson Beck")
    assert _value(_parse([both]), "Carson Beck", "pass_att") == 1.0


def test_the_receiver_is_not_credited_with_the_attempt():
    out = _parse([_completion()])
    assert _absent(out, "Arian Smith", "pass_att")
    assert _value(out, "Arian Smith", "receptions") == 1.0
    assert _value(out, "Carson Beck", "pass_att") == 1.0


def test_a_passer_with_no_net_yards_is_on_the_record_now():
    """The survivorship rule: a zero is written where the OPPORTUNITY is,
    and attempts are that opportunity. Before this the game vanished from
    his log, and the trailing average was computed over the games he
    happened to gain yards in."""
    assert C.ZERO_WHEN["pass_yds"] == "pass_att"
    out = _parse([_play(incompletion_player="Carson Beck"),
                  _play(incompletion_player="Carson Beck")])
    assert _value(out, "Carson Beck", "pass_att") == 2.0
    assert _value(out, "Carson Beck", "pass_yds") == 0.0
    # …and a player who never dropped back still writes no passing row.
    out = _parse([_play(rush_player="Nate Frazier", rush_yds="8")])
    assert _absent(out, "Nate Frazier", "pass_yds")
    assert _absent(out, "Nate Frazier", "pass_att")


def test_the_market_is_emitted_and_is_the_one_the_bridge_asks_for():
    assert "pass_att" in C.MARKETS
    assert nflusage.OPP_BY_MARKET["pass_yds"] == "pass_att", (
        "the volume bridge names this column; college now has it")
    # Ordered so an ingest log still reads like a box score.
    assert C.MARKETS.index("pass_att") < C.MARKETS.index("pass_yds")
    # Targets remain genuinely absent — this feed has no target column,
    # so receptions is NOT given a false denominator alongside.
    assert "receptions" not in C.ZERO_WHEN and "targets" not in C.MARKETS


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
