"""The UFC card must fill itself in.

Two things used to be commands a person had to remember: drafting fighter
dossiers, and typing in weigh-in results. Both were load-bearing — "no
dossier, no bet" meant a 34-bout card with 8 dossiers modelled 8 fights,
and the weigh-in was the one fight-week fact the grade could see. A model
whose coverage depends on somebody running a script is a model that is
usually uncovered.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.ufc import weighin, weighin_feed


# --- weigh-in feed ----------------------------------------------------------
def _event(weights):
    """An ESPN-shaped MMA event carrying `weights` = [(name, field, value)]."""
    return {"name": "UFC Test", "competitions": [{
        "type": {"text": "Lightweight Bout"},
        "competitors": [
            {"athlete": {"displayName": n}, field: v}
            for n, field, v in weights
        ]}]}


def test_a_recorded_weight_is_read_and_graded_like_a_typed_one():
    ev = _event([("Alpha Fighter", "weighIn", 155.0),
                 ("Beta Fighter", "weighIn", 157.5)])
    rows = weighin_feed.scan_event(ev)
    assert {r["name"] for r in rows} == {"Alpha Fighter", "Beta Fighter"}
    assert all(r["division"] == "lightweight" for r in rows)
    # 155.0 makes the 156.0 non-title limit; 157.5 does not.
    a = weighin.evaluate(155.0, "lightweight")
    b = weighin.evaluate(157.5, "lightweight")
    assert a["state"] == "made" and b["state"] == "missed"


def test_an_implausible_weight_is_refused_rather_than_recorded():
    """A bad number is worse than no number: it manufactures a "missed
    weight" red flag that blocks a real bet."""
    for bad in (70.0, 0, 900.0, "n/a", None):
        w, _f = weighin_feed.read_weight({"weight": bad})
        assert w is None, f"{bad!r} was accepted as a fighting weight"
    kg = weighin_feed.read_weight({"weight": 70.3})       # kilograms
    assert kg[0] is None


def test_an_explicit_weigh_in_field_beats_a_generic_weight():
    """On some payloads `weight` is the fighter's listed walk-around
    weight, not what the scale said."""
    w, field = weighin_feed.read_weight({"weight": 170.0, "weighIn": 155.5})
    assert (w, field) == (155.5, "weighIn")


def test_a_card_with_no_weights_yet_reports_that_instead_of_guessing():
    ev = _event([])
    assert weighin_feed.scan_event(ev) == []


def test_divisions_survive_the_words_around_them():
    for text, want in (("Women's Flyweight Title Bout", "flyweight"),
                       ("Light Heavyweight Bout", "light heavyweight"),
                       ("Catchweight (178 lbs)", "Catchweight (178 lbs)")):
        assert weighin_feed._division_text(text) == want


def test_light_heavyweight_is_not_read_as_heavyweight():
    """Substring matching, longest-first — otherwise a 205er is checked
    against the 265 limit and every miss goes unseen."""
    assert weighin_feed._division_text("Light Heavyweight Bout") \
        == "light heavyweight"
    assert weighin.limit_for("light heavyweight") == 206.0


def test_refresh_records_every_weight_the_card_carries(monkeypatch=None):
    tmp = os.path.join(tempfile.mkdtemp(), "wi.json")
    ev = _event([("Alpha Fighter", "weighIn", 155.0),
                 ("Beta Fighter", "weighIn", 157.5)])
    orig = weighin_feed.fetch_card
    weighin_feed.fetch_card = lambda date=None: {"events": [ev]}
    try:
        res = weighin_feed.refresh(store_path=tmp, today="2026-08-01")
    finally:
        weighin_feed.fetch_card = orig
    assert res["recorded"] == 2 and res["made"] == 1 and res["missed"] == 1
    store = json.loads(open(tmp).read())
    assert weighin.state_for("Alpha Fighter", store)["state"] == "made"
    assert weighin.state_for("Beta Fighter", store)["state"] == "missed"


def test_an_empty_feed_is_reported_not_silently_swallowed():
    orig = weighin_feed.fetch_card
    weighin_feed.fetch_card = lambda date=None: {"events": []}
    try:
        res = weighin_feed.refresh(store_path=os.path.join(
            tempfile.mkdtemp(), "wi.json"))
    finally:
        weighin_feed.fetch_card = orig
    assert res["recorded"] == 0 and res["note"]


def test_the_probe_explains_a_blank_result():
    """A blank board must never be a mystery."""
    orig = weighin_feed.fetch_card
    weighin_feed.fetch_card = lambda date=None: {"events": [_event([])]}
    try:
        lines = "\n".join(weighin_feed.probe())
    finally:
        weighin_feed.fetch_card = orig
    assert "usable weigh-in weights found: 0" in lines
    assert "--weigh-in" in lines, "the manual escape hatch must stay offered"


# --- dossier auto-draft -----------------------------------------------------
def test_hand_written_dossiers_are_never_overwritten():
    import ufc_dossiers as UD
    book = {"Hand Made": {"archetype": "wrestler", "source": "ethan"},
            "Auto Made": {"archetype": "striker", "source": "espn-auto",
                          "career_fights": 12}}
    assert UD.needs_draft(book, "Hand Made") is False
    assert UD.needs_draft(book, "Hand Made", refresh=True) is False, \
        "--refresh must not clobber a human's work"
    assert UD.needs_draft(book, "Auto Made") is False
    assert UD.needs_draft(book, "Auto Made", refresh=True) is True
    assert UD.needs_draft(book, "Never Seen") is True


def test_a_stale_auto_draft_is_redrafted_without_being_asked():
    import ufc_dossiers as UD
    old = {"Old Auto": {"archetype": "striker", "source": "espn-auto"}}
    assert UD.needs_draft(old, "Old Auto") is True


def test_the_launcher_drafts_dossiers_and_pulls_weighins_on_its_own():
    """The whole point: neither is a command you have to remember."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    fn = src[src.index("def refresh_ufc("):src.index("def refresh_all(")]
    assert "_auto_dossiers(" in fn, "dossiers are still a manual chore"
    assert "_auto_weighins(" in fn, "weigh-ins are still typed in by hand"
    # And the draft must be paced, or one refresh stalls for half an hour.
    draft = src[src.index("def _auto_dossiers("):src.index("def _auto_weighins(")]
    assert "limit=" in draft, "an unpaced draft blocks the refresh loop"
    # Neither may ever take the card down.
    for block in (draft, src[src.index("def _auto_weighins("):
                              src.index("def refresh_ufc(")]):
        assert "except Exception" in block


def test_the_probe_is_dispatched_not_just_defined():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(root, "launch.py"), encoding="utf-8").read()
    assert '"--probe-weighins" in argv' in src


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
