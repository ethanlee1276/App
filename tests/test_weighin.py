"""Missed weight has to actually void the bet.

Every UFC card the model prints already carries this line:

    kill_if: "missed weight, late replacement, or visible cut damage at
              weigh-ins → automatic void"

It was a promise with nothing behind it. A fighter could miss by three
pounds on Friday morning and his bet would still show as a pick on
Saturday, under a card that said it wouldn't. These tests are the
enforcement — the last one runs the real model end to end and asserts the
pick becomes a pass.

The other thing being pinned is the difference between "made weight" and
"nobody has looked". Those are opposite facts and they must never render
the same way, which is the whole reason "unrecorded" is a state rather
than an absence.
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc import weighin


def test_the_non_title_allowance_is_one_pound():
    # 155.5 at lightweight: legal on a Fight Night, a miss for a belt. Same
    # number, two answers — which is why the limit is computed, not typed.
    assert weighin.evaluate(155.5, "lightweight")["state"] == "made"
    assert weighin.evaluate(155.5, "lightweight", title_fight=True)["state"] == "missed"
    assert weighin.limit_for("lightweight") == 156.0
    assert weighin.limit_for("lightweight", title_fight=True) == 155.0


def test_heavyweight_gets_no_allowance():
    assert weighin.limit_for("heavyweight") == 265.0
    assert weighin.evaluate(265.5, "heavyweight")["state"] == "missed"


def test_a_miss_reports_how_far_over():
    r = weighin.evaluate(158.0, "lightweight")
    assert r["state"] == "missed" and r["over"] == 2.0


def test_a_catchweight_is_not_judged():
    # No standard limit exists, so no verdict is invented.
    r = weighin.evaluate(163.0, "catchweight")
    assert r["state"] == "unknown_division" and r["limit"] is None


def test_unrecorded_is_a_state_not_an_absence():
    assert weighin.state_for("Nobody", {})["state"] == "unrecorded"


def test_last_months_weigh_in_does_not_clear_this_fight():
    """Weigh-ins are per event. A stale number must not stand in."""
    old = {"state": "made", "recorded_at": "2026-06-01"}
    assert weighin.stale(old, today="2026-07-31")
    assert not weighin.stale({"state": "made", "recorded_at": "2026-07-30"},
                             today="2026-07-31")
    assert weighin.stale({}, today="2026-07-31"), "no date = not trustworthy"


def test_only_a_miss_earns_a_red_flag():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "w.json")
        weighin.record("Made It", 155.0, "lightweight", path=path,
                       today="2026-07-31")
        weighin.record("Missed It", 157.0, "lightweight", path=path,
                       today="2026-07-31")
        store = weighin.load_store(path)
        assert weighin.red_flags("Made It", store, today="2026-07-31") == []
        flags = weighin.red_flags("Missed It", store, today="2026-07-31")
        assert len(flags) == 1 and "missed weight by 1 lb" in flags[0]
        # An unrecorded weigh-in does NOT gate: they land the morning
        # before the card, and gating until then leaves the board empty for
        # most of fight week, which is silence rather than honesty.
        assert weighin.red_flags("Never Weighed", store) == []


def test_a_stale_record_stops_flagging():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "w.json")
        weighin.record("Old Miss", 157.0, "lightweight", path=path,
                       today="2026-06-01")
        store = weighin.load_store(path)
        assert weighin.red_flags("Old Miss", store, today="2026-07-31") == []


def test_a_missed_weight_turns_a_pick_into_a_pass():
    """The end-to-end claim, through the real model."""
    from engine.ufc.model import evaluate_fight

    def _dossier(name, edge):
        return {"name": name, "division": "lightweight", "ufc_fights": 12,
                "fights": 20, "age": 29, "archetype": "pressure boxer",
                "slpm": 5.5 + edge, "sapm": 3.0 - edge, "str_def": .60 + edge / 20,
                "td_per15": 2.0 + edge, "tdd": .75, "td_acc": .45,
                "sub_att_per15": 0.8, "ctrl_per15": 90, "kd_per100": 1.2,
                "ko_losses": 0, "ko_losses_last3": 0, "times_finished": 0,
                "r3_decay": 0.0, "red_flags": []}

    made = {"state": "made"}

    def run(flags):
        # A fixture that earns its pick: a named style mismatch, a real
        # price edge, both fighters on the scale, and a known venue. The
        # §10 grade needs all of that — a bet that merely scrapes past the
        # edge threshold is exactly what "below 70: no bet" refuses.
        a = {**_dossier("Alpha Fighter", 1.6), "archetype": "wrestler",
             "red_flags": list(flags)}
        b = {**_dossier("Beta Fighter", 0.0),
             "archetype": "striker_poor_tdd"}
        return evaluate_fight(a, b, {"fighter_a": "Alpha Fighter",
                                     "fighter_b": "Beta Fighter",
                                     "a_odds": -120, "b_odds": 98,
                                     "book": "test",
                                     "venue": "T-Mobile Arena",
                                     "city": "Las Vegas",
                                     "weigh_in": {"a": made, "b": made}},
                              "lightweight", 0)

    clean = run([])
    if clean["kind"] != "pick":
        # The fixture didn't clear the gate on its own merits, so the
        # comparison below would prove nothing. Say so rather than pass.
        raise AssertionError(
            f"fixture never became a pick ({clean.get('why')}) — the test "
            f"cannot show that a weigh-in miss is what killed it")
    flagged = run(["missed weight by 2 lb (157.0 vs 155.0)"])
    assert flagged["kind"] == "pass", "a missed weight still showed as a pick"
    assert "missed weight" in flagged["why"]


def test_the_card_summary_counts_what_is_missing():
    fights = [
        {"weigh_in": {"a": {"state": "made"}, "b": {"state": "missed"}}},
        {"weigh_in": {"a": {"state": "unrecorded"}, "b": {"state": "made"}}},
    ]
    s = weighin.card_summary(fights)
    assert s == {"made": 2, "missed": 1, "unrecorded": 1, "complete": False}


def test_annotating_a_fight_gates_it_through_the_existing_red_flags():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "w.json")
        weighin.record("Missed It", 158.0, "lightweight", path=path,
                       today="2026-07-31")
        store = weighin.load_store(path)
        fight = {"a": {"name": "Missed It", "red_flags": []},
                 "b": {"name": "Other Guy", "red_flags": []},
                 "prices": {"fighter_a": "Missed It", "fighter_b": "Other Guy"}}
        weighin.annotate_fight(fight, store, today="2026-07-31")
        assert fight["weigh_in"]["a"]["state"] == "missed"
        assert fight["weigh_in"]["b"]["state"] == "unrecorded"
        assert any("missed weight" in f for f in fight["a"]["red_flags"])
        assert fight["b"]["red_flags"] == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
