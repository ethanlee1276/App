"""The touchdown rule reads the measured red-zone share (2026-11-15).

Ethan, choosing between the board's estimate and the play-by-play's own
count for the touchdown rule's red-zone share: "switch". The rule is 45%, or
40% with 30% of the team's red-zone work (engine/likelyboard.td_rule). The
share was an estimate: his expected red-zone chances this week against his
team's red-zone plays a game. The play-by-play has counted his real share of
his team's red-zone touches over his last games since 15 November
(engine/nflusage.red_zone_usage → touchdowns rz_share → his read's
touchdown row, gamescan.stamp_touchdowns), and the board now reads that
first:

  * a measured share wins over the estimate, and the rule says "of his
    team's red-zone touches";
  * with none measured (a college scorer, a newcomer), the estimate stands,
    "of the team's red-zone chances";
  * the rule's bars are the same (45%; 40% with 30%);
  * it switches on after Sunday night's kickoff (Ethan: push it after today's
    games), by one constant, likelyboard.TD_RULE_MEASURED; off, the board is
    what it was, wording and all. These tests read it on (`_on`).

    python3 tests/test_the_touchdown_rule_reads_the_measured_share.py
"""
import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import likelyboard as B                                  # noqa: E402

GAME = {"home": "DET", "away": "NYJ", "spread": -9.5, "total": 44.5,
        "scan": {"units": {}, "redzone": {"NYJ": {"off": 10.0}}}}
SCORER = {"kind": "td", "player": "Breece Hall", "team": "NYJ", "opponent": "DET", "market": "anytime_td",
          "side": "yes", "line": None, "odds": 120, "model_prob": 0.42, "implied_prob": 0.40,
          "rz_chances": 2.0, "position": "RB"}


class _on:
    """The switch on for one test (likelyboard.TD_RULE_MEASURED), put back after."""
    def __enter__(self):
        self.was, B.TD_RULE_MEASURED = B.TD_RULE_MEASURED, True

    def __exit__(self, *exc):
        B.TD_RULE_MEASURED = self.was


def _board(measured=None, on=True):
    if on:
        with _on():
            return _board(measured, on=False)
    reads = {}
    if measured is not None:
        reads = {"NYJ@DET": {"players": [{"player": "Breece Hall", "team": "NYJ", "opp": "DET",
                                          "td": {"rz_share": measured}}]}}
    result = {"games": [copy.deepcopy(GAME)], "recommendations": [], "scan_reads": reads,
              "most_likely": [dict(SCORER)], "matchup_picks": [], "td_scenarios": []}
    b = B.build(result, record={}, sport="nfl", tiers_seen={})
    return next(r for r in b["rows"] + b.get("held", []) if r.get("player") == "Breece Hall")


def test_a_measured_share_wins_over_the_estimate():
    row = _board(measured=0.36)
    assert row["rz_share"] == 0.36 and row["rz_share_measured"] is True, row
    assert row["td_rule"]["meets"] is True, row["td_rule"]
    assert row["td_rule"]["why"] == ("42%, 36% of the team's red-zone touches — meets our touchdown rule "
                                     "(40% with a red-zone role)"), row["td_rule"]


def test_with_none_measured_the_estimate_stands():
    row = _board()
    # 2.0 expected chances against 10 red-zone plays a game: 20%, under the 30%.
    assert row["rz_share"] == 0.2 and not row.get("rz_share_measured"), row
    assert row["td_rule"]["meets"] is False
    assert row["td_rule"]["why"] == ("42%, 20% of the team's red-zone chances — our touchdown rule asks 45%, or "
                                     "40% with 30% of the red-zone work"), row["td_rule"]


def test_a_low_measured_share_holds_where_the_estimate_would_not():
    # The estimate would say 40% (4.0 of 10); the play-by-play says 12%.
    row = _board(measured=0.12)
    assert row["rz_share"] == 0.12 and row["td_rule"]["meets"] is False


def test_the_bars_are_the_same():
    assert (B.TD_RULE_PROB, B.TD_RULE_FALLBACK, B.TD_RULE_RZ_SHARE) == (0.45, 0.40, 0.30)


def test_off_the_board_is_what_it_was():
    """Until the switch: no measured share read, the estimate, the old words."""
    if B.TD_RULE_MEASURED:
        return                                           # switched on: the tests above are the board
    row = _board(measured=0.36, on=False)
    assert row["rz_share"] == 0.2 and not row.get("rz_share_measured"), row
    assert row["td_rule"]["why"] == ("42%, 20% of the team's red-zone chances — our touchdown rule asks 45%, or "
                                     "40% with 30% of the red-zone chances"), row["td_rule"]


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
                traceback.print_exc(limit=6)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
