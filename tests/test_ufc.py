"""Tests for the Scalpy MMA engine — cap, joint, clamp, gate, pass list."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc.model import (
    win_probability, method_conditionals, joint_method, clamp_weight,
    humility_clamp, approval_gate, stake_units, evaluate_fight, run_card,
    age_mult, style_read, WIN_CAP,
)


def _fighter(name="A", **over):
    d = {"name": name, "age": 29, "division": "lightweight",
         "archetype": "pressure", "ufc_fights": 8, "fights": 14,
         "slpm": 4.5, "sapm": 3.5, "kd_per100": 1.2, "td_per15": 1.0,
         "td_acc": 0.40, "tdd": 0.65, "ctrl_per15": 2.0,
         "sub_att_per15": 0.4, "ko_losses": 1, "ko_losses_last3": 0,
         "times_finished": 2, "r3_decay": 0.12, "red_flags": []}
    d.update(over)
    return d


def test_win_probability_is_hard_capped():
    # A style edge on top of a stats wipeout — the only road to the cap.
    monster = _fighter(archetype="wrestler", slpm=8.0, sapm=1.5, tdd=0.95,
                       td_per15=4.0, td_acc=0.6, ctrl_per15=8.0, kd_per100=4.0)
    tomato = _fighter("B", archetype="striker_poor_tdd", slpm=2.0, sapm=6.0,
                      tdd=0.2, ko_losses=6, ko_losses_last3=2, r3_decay=0.5,
                      age=38)
    p, _ = win_probability(monster, tomato)
    # Four-ounce gloves: nobody is safer than 88%.
    assert p <= WIN_CAP
    assert p >= 0.75                                  # still a huge favorite
    p_even, _ = win_probability(_fighter(), _fighter("B"))
    assert abs(p_even - 0.5) < 0.03


def test_age_curve():
    assert age_mult(29) == 1.0 and age_mult(33) == 0.97
    assert age_mult(36) == 0.85 and age_mult(40) == 0.85


def test_style_matrix_mirrors():
    s, lean, _ = style_read("counter", "wild_aggressor")
    assert s > 0 and lean == "ko"                     # highest KO matchup
    s2, lean2, _ = style_read("wild_aggressor", "counter")
    assert s2 == -s and lean2 == "ko"                 # mirrored
    assert style_read("pressure", "pressure")[1] is None


def test_method_joint_sums_to_one():
    a, b = _fighter(), _fighter("B", ko_losses_last3=2, tdd=0.4)
    ca = method_conditionals(a, b, "lightweight")
    cb = method_conditionals(b, a, "lightweight")
    assert abs(sum(ca.values()) - 1.0) < 1e-6
    joint = joint_method(0.60, ca, cb)
    total = sum(v for k, v in joint.items() if k != "distance")
    assert abs(total - 1.0) < 0.005                   # the whole discipline
    # Chin damage pushes the opponent's KO conditional up.
    ca_soft = method_conditionals(a, _fighter("B"), "lightweight")
    assert ca["ko"] > ca_soft["ko"]


def test_wrestlers_win_decisions_not_subs():
    wrestler = _fighter(archetype="wrestler", sub_att_per15=0.2)
    c = method_conditionals(wrestler, _fighter("B", tdd=0.3), "welterweight")
    assert c["dec"] > c["sub"]
    hunter = _fighter(archetype="submission", sub_att_per15=1.8)
    c2 = method_conditionals(hunter, _fighter("B", tdd=0.3), "welterweight")
    assert c2["sub"] > c["sub"]


def test_durable_opponents_drag_to_decision():
    a = _fighter()
    iron = _fighter("B", times_finished=0, fights=20)
    glass = _fighter("B", times_finished=8, fights=12)
    assert method_conditionals(a, iron, "lightweight")["dec"] > \
        method_conditionals(a, glass, "lightweight")["dec"]


def test_clamp_weights_and_debutant_no_bet():
    assert clamp_weight(_fighter(), _fighter("B")) == 0.55       # both 5+
    assert clamp_weight(_fighter(ufc_fights=3), _fighter("B")) == 0.45
    assert clamp_weight(_fighter(ufc_fights=2), _fighter("B")) == 0.20
    assert clamp_weight(_fighter(short_notice=True), _fighter("B")) == 0.20
    assert clamp_weight(_fighter(ufc_fights=0), _fighter("B")) is None
    p, _ = humility_clamp(0.60, 0.52, 0.55)
    assert abs(p - (0.55 * 0.60 + 0.45 * 0.52)) < 1e-9


def test_gate_is_not_mathematically_closed():
    """REGRESSION (2026-07-29): with the old w=0.25, the largest clamped
    edge (w x kill-diff = 3.75pts vs fair, ~1.75 over break-even) could
    never satisfy the 4-point moneyline gate — only the unpriced-news
    branch could ever produce a bet. The standard clamp must clear the
    gate by a real margin; thin samples stay closed on purpose."""
    from engine.ufc.model import (CLAMP_KILL_DIFF, GATE_EDGE_ML,
                                  GATE_EDGE_PROP)
    vig = 0.02                                    # ~break-even minus fair
    standard = clamp_weight(_fighter(ufc_fights=3), _fighter("B"))
    experienced = clamp_weight(_fighter(), _fighter("B"))
    assert standard * CLAMP_KILL_DIFF - vig - GATE_EDGE_ML >= 0.005
    assert experienced * CLAMP_KILL_DIFF - vig - GATE_EDGE_PROP >= 0.005
    thin = clamp_weight(_fighter(ufc_fights=2), _fighter("B"))
    assert thin * CLAMP_KILL_DIFF - vig < GATE_EDGE_ML     # closed by design
    killed, why = humility_clamp(0.75, 0.55, 0.35)
    assert killed is None and "not that soft" in why


def test_gate_mma_rules():
    assert approval_gate(0.62, -120, "moneyline", [], 0) == []
    assert any("−300" in f for f in approval_gate(0.85, -400, "moneyline", [], 0))
    assert any("red flag" in f for f in
               approval_gate(0.62, -120, "moneyline", ["missed weight"], 0))
    # No headcount cap: the tenth qualifying fight on a card is judged on
    # its own merits, exactly like the first. Money is what gets capped —
    # see test_card_money_cap_replaces_the_headcount_cap.
    assert approval_gate(0.62, -120, "moneyline", [], 9) == []
    # Props need 5 points over break-even, not 4 (re-tuned from 6 — the
    # old bar was unreachable under the clamp; see the welded-door test).
    assert any("edge" in f for f in approval_gate(0.570, -110, "method", [], 0))
    assert approval_gate(0.578, -110, "method", [], 0) == []
    # One-fifth Kelly, capped at 2.5% of roll — which on the shared scale
    # (1u = 1% of bankroll, engine/staking.py) is 2.5u, not the 0.5u the
    # old twenty-unit ruler displayed for the same real-money cap.
    assert 0 < stake_units(0.62, -120) <= 2.5


def test_evaluate_fight_paths():
    a, b = _fighter(), _fighter("B", age=36, ko_losses_last3=2, sapm=4.8,
                                r3_decay=0.3)
    prices = {"fighter_a": "A", "fighter_b": "B", "a_odds": -105,
              "b_odds": -115, "book": "DK"}
    r = evaluate_fight(a, b, prices, "lightweight", 0)
    assert r["kind"] in ("pick", "pass")
    if r["kind"] == "pick":
        assert r["pick"] == "A" and r["stake_units"] > 0
        assert abs(sum(v for k, v in r["method"].items() if k != "distance")
                   - 1.0) < 0.005
    # No dossier, no bet — the spec's rule, verbatim.
    r2 = evaluate_fight(None, b, prices, "lightweight", 0)
    assert r2["kind"] == "pass" and "no dossier" in r2["why"]
    assert r2["reason_code"] == "no_dossier" and "A" in r2["why"]
    # Fighters with no stat coverage are unmodelable — and the reason says
    # WHY honestly: a 19-3 regional veteran is not a "debutant".
    r3 = evaluate_fight(_fighter(ufc_fights=0), b, prices, "lightweight", 0)
    assert r3["kind"] == "pass" and r3["reason_code"] == "no_data"
    assert "no fight-by-fight stats for A" in r3["why"]
    assert "debutant" not in r3["why"]
    # Every result carries both corners' briefs so the page can show the
    # matchup even when the model passes.
    assert [f["name"] for f in r3["fighters"]] == ["A", "B"]
    assert r3["fighters"][1]["has_dossier"] and r3["fighters"][1]["record"] is None
    # Missing prices are their own reason code, not lumped with "no data".
    r4 = evaluate_fight(a, b, {"fighter_a": "A", "fighter_b": "B"},
                        "lightweight", 0)
    assert r4["reason_code"] == "no_price"


def test_run_card_discipline_and_pass_list():
    chin = dict(age=37, ko_losses_last3=2, ko_losses=4, sapm=5.2,
                r3_decay=0.35, times_finished=6, tdd=0.4)
    fights = []
    for i in range(6):
        fights.append({"a": _fighter(f"A{i}"),
                       "b": _fighter(f"B{i}", **chin),
                       "prices": {"fighter_a": f"A{i}", "fighter_b": f"B{i}",
                                  "a_odds": 100, "b_odds": -120, "book": "DK"},
                       "division": "lightweight"})
    # Two unmodelable bouts pad the card.
    fights.append({"a": None, "b": None,
                   "prices": {"fighter_a": "X", "fighter_b": "Y"},
                   "division": ""})
    fights.append({"a": _fighter("Deb", ufc_fights=0), "b": _fighter("Vet"),
                   "prices": {"fighter_a": "Deb", "fighter_b": "Vet",
                              "a_odds": -110, "b_odds": -110}, "division": ""})
    r = run_card(fights)
    assert r["counts"]["picks"] <= 3                  # max 3 bets per card
    # EVERY unbet fight is on the pass list with a reason.
    assert r["counts"]["picks"] + len(r["pass_list"]) == len(fights)
    assert all(p.get("why") for p in r["pass_list"])


def test_journal_and_settle_from_fight_results():
    """The honest-subset loop end to end: a card's picks journal at their
    real prices (category='ufc'), settle from injected fight results —
    win, loss, and a draw/NC that voids like a book would — and the
    report aggregates for the Record page."""
    import os
    import tempfile
    import datetime as dt
    from engine import ledger

    lconn = ledger.connect(os.path.join(tempfile.mkdtemp(), "led.db"))
    card = {"status": "card", "event_date": "2026-08-01", "picks": [
        {"pick": "Ada Striker", "odds": 120, "book": "DK", "p_final": 0.51,
         "edge": 0.06, "stake_units": 0.4},
        {"pick": "Bo Grappler", "odds": -140, "book": "FD", "p_final": 0.62,
         "edge": 0.04, "stake_units": 0.3},
        {"pick": "Cy Draw", "odds": 105, "book": "DK", "p_final": 0.52,
         "edge": 0.05, "stake_units": 0.2},
        {"pick": "No Price Guy", "odds": None},          # never journals
    ]}
    assert ledger.log_ufc_picks(lconn, card) == 3
    assert ledger.log_ufc_picks(lconn, card) == 0        # idempotent

    results = {"Ada Striker": {"won": True, "date": "2026-08-01"},
               "Bo Grappler": {"won": False, "date": "2026-08-01"},
               "Cy Draw": {"won": None, "date": "2026-08-01"}}

    def fake_fetch(name, since):
        assert since == dt.date(2026, 8, 1)
        return results.get(name)

    assert ledger.settle_ufc(lconn, fetch_result=fake_fetch) == 3
    rep = ledger.ufc_report(lconn)
    assert rep["wins"] == 1 and rep["losses"] == 1
    assert rep["open"] == 0
    # The draw voided: zero P&L, excluded from the record.
    void = lconn.execute("SELECT status FROM bets WHERE player='Cy Draw'").fetchone()
    assert void["status"] == "void"
    # The winner paid plus-money: +0.4 x 1.2 units.
    win = lconn.execute("SELECT pnl_units FROM bets WHERE player='Ada Striker'").fetchone()
    assert abs(win["pnl_units"] - 0.48) < 1e-6
    assert rep["recent"][0]["player"] in ("Ada Striker", "Bo Grappler")
    lconn.close()


# The runner stays at the TRUE END of the file — a test defined after it
# never runs (this exact bug has now bitten three test files).
# --- telling a misspelling from a missing fighter (#96) ----------------------
def test_a_dossier_that_matches_is_returned_and_nothing_is_flagged():
    import ufc_build
    d = {"khamzat chimaev": {"name": "Khamzat Chimaev"}}
    got, close = ufc_build._lookup(d, "Khamzat Chimaev")
    assert got is d["khamzat chimaev"] and close is None


def test_a_near_miss_names_the_closest_dossier_we_hold():
    """THE TWO CAUSES OF `no_dossier` LOOKED IDENTICAL. An exact dict hit
    means "never written up" and "written up, spelled differently" produce
    the same pass line — and only the second is a one-line JSON fix. Two
    of twelve bouts on 2026-08-08 passed this way with no way to tell
    which kind they were without opening the file."""
    import ufc_build
    d = {"jose aldo": {"name": "Jose Aldo"}}
    # `Jr.` IS folded by normalize_name's suffix rule; the spelled-out
    # `Junior` is not in that list, so an odds feed writing it out in full
    # misses a dossier we hold. Measured, not assumed — this test was
    # first written asserting the opposite.
    assert ufc_build._lookup(d, "Jos\u00e9 Aldo Jr.")[0] is not None
    got, close = ufc_build._lookup(d, "Jos\u00e9 Aldo Junior")
    assert got is None, "the spelled-out suffix is not folded"
    assert close == "jose aldo", close
    got, close = ufc_build._lookup(d, "Jose Aldos")
    assert got is None and close == "jose aldo"


def test_it_never_matches_on_the_near_name():
    """A fighter is not a name similarity. Pricing a bout against the
    wrong man's record is worse than not pricing it, which is what `no
    dossier, no bet` is for — so the near name is REPORTED, never
    substituted."""
    import ufc_build
    d = {"jose aldo": {"name": "Jose Aldo"}}
    got, close = ufc_build._lookup(d, "Jose Aldos")
    assert got is None, "a near name must never stand in for a dossier"
    assert close


def test_a_genuinely_absent_fighter_gets_no_suggestion():
    """No near name is itself the answer: nobody has written him up."""
    import ufc_build
    d = {"jose aldo": {"name": "Jose Aldo"}, "sean omalley": {"name": "x"}}
    got, close = ufc_build._lookup(d, "Ilia Topuria")
    assert got is None and close is None


def test_an_empty_dossier_file_suggests_nothing_rather_than_crashing():
    import ufc_build
    assert ufc_build._lookup({}, "Anybody") == (None, None)
    assert ufc_build._lookup({"a b": {}}, "") == (None, None)


def test_an_extra_middle_name_is_recognised_as_the_same_man():
    """String distance alone cannot do this. `jose aldo junior` against
    `jose aldo` scores 0.72 — under any cutoff loose enough to be safe —
    and it is obviously the same fighter. Token containment catches added
    words; the distance test catches altered letters."""
    import ufc_build
    d = {"jose aldo": {"name": "Jose Aldo"}}
    assert ufc_build._closest("jose aldo junior", d) == "jose aldo"
    assert ufc_build._closest("jose roberto aldo", d) == "jose aldo"


def test_a_single_token_is_never_enough_to_suggest_anyone():
    """One shared word is a coincidence, not a fighter. Half the roster
    shares a first name."""
    import ufc_build
    d = {"jose aldo": {}, "jose maria": {}}
    assert ufc_build._closest("jose", d) is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
