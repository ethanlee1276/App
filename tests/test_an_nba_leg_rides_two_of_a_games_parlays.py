"""An NBA leg rides at most two of a game's six parlays (step ABG, 22 November 2026).

Decision 18, as put to Ethan: "Should one NBA leg be limited to 2 of a game's 6 parlays? Right now it can be
on up to 4." His answer, 22 November: "Yes limit it". MAX_USES held a leg to two tickets of each list, so one
NBA leg could ride four of a game's six parlays, two three-leg and two two-leg; on the NBA's tickets graded
at their start, 8 legs rode four tickets each, and 4 of them lost and took 16 tickets with them. What these
hold:

  * in the NBA a leg rides at most GAME_CAP_USES of a game's three-leg and two-leg tickets together, the
    three-leg ones chosen first as before, on the board's build and a report's rebuild alike;
  * a game with too few legs for six posts fewer two-leg tickets and says the cap is why;
  * a posted game's tickets stand as posted (one posted before this step too); its open places, and a list
    it never posted, fill under the cap, and its two-leg tickets are chosen around the three-leg ones it
    posted;
  * every other league builds as it did, and QB_GAME_LEG_CAP=off goes back to the rule before.

    python3 tests/test_an_nba_leg_rides_two_of_a_games_parlays.py
"""
from __future__ import annotations

import copy
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gameparlays as GP  # noqa: E402

EG = __import__("test_each_game_gets_its_parlays")                  # the shared fixture (a sibling test file)
TL = __import__("test_every_league_posts_three_two_leg_parlays")    # its league boards
GAME = EG.GAME
KEY = f"{GAME['away']}@{GAME['home']}|{GAME['date']}"
SRC = (ROOT / "engine" / "gameparlays.py").read_text(encoding="utf-8")

#: Ten NBA props across the game's two clubs, the likeliest first.
ROWS = [("Jalen Brunson", "NYG", "pts", "Over", 22.5, 0.74, -260), ("Josh Hart", "NYG", "reb", "Over", 6.5, 0.72, -250),
        ("Mikal Bridges", "NYG", "pts", "Over", 14.5, 0.70, -230), ("OG Anunoby", "NYG", "reb", "Over", 4.5, 0.69, -220),
        ("Karl-Anthony Towns", "NYG", "reb", "Over", 9.5, 0.68, -210), ("Jordan Poole", "WAS", "pts", "Over", 15.5, 0.67, -205),
        ("Kyle Kuzma", "WAS", "reb", "Over", 5.5, 0.66, -195), ("Bilal Coulibaly", "WAS", "ast", "Over", 2.5, 0.65, -190),
        ("Alex Sarr", "WAS", "reb", "Over", 6.5, 0.64, -180), ("Bub Carrington", "WAS", "ast", "Over", 3.5, 0.63, -175)]


class _Env:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        self.was = os.environ.get(GP.GAME_CAP_ENV)
        if self.value is None:
            os.environ.pop(GP.GAME_CAP_ENV, None)
        else:
            os.environ[GP.GAME_CAP_ENV] = self.value

    def __exit__(self, *exc):
        if self.was is None:
            os.environ.pop(GP.GAME_CAP_ENV, None)
        else:
            os.environ[GP.GAME_CAP_ENV] = self.was


def _board():
    b = EG.board()
    b["most_likely"] = [EG._ml(p, t, "G", m, s, l, pr, o, m) for p, t, m, s, l, pr, o in ROWS]
    b["td_field"] = []
    return b


def _picks():
    return [{"player": p, "market": m, "side": s, "line": l} for p, _t, m, s, l, _pr, _o in ROWS]


def _uses(*lists):
    return GP.game_uses(*lists)


def _legs(ts):
    return [[(l["player"], l["market"], str(l["side"]).upper()) for l in t["legs"]] for t in ts]


def test_the_boards_build_holds_a_leg_to_two_of_the_games_parlays():
    with _Env(None):
        g = GP.build(_board(), "nba")["games"][0]
    u = _uses(g["threes"], g["twos"])
    assert len(g["threes"]) == 3 and len(g["twos"]) == 2, (len(g["threes"]), len(g["twos"]))
    assert max(u.values()) <= GP.GAME_CAP_USES == 2, u
    assert g["twos_note"].endswith("with no leg on more than 2 of the game's parlays"), g["twos_note"]
    # The three-leg tickets are chosen first, as before: the same as with no cap.
    with _Env("off"):
        old = GP.build(_board(), "nba")["games"][0]
    assert _legs(g["threes"]) == _legs(old["threes"])
    assert len(old["twos"]) == 3 and max(_uses(old["threes"], old["twos"]).values()) == 3, \
        "without the cap this game rides a leg on three of its parlays"


def test_a_reports_rebuild_holds_it_too():
    with _Env(None):
        b = _board()
        b["game_parlays"] = GP.build(b, "nba")
        x = GP.from_report(b, "nba", GAME, _picks())
    assert x["threes"] and x["twos"], x.get("twos_note")
    assert max(_uses(x["threes"], x["twos"]).values()) <= 2


def test_the_two_leg_tickets_are_chosen_around_the_three_leg_ones_it_posted():
    with _Env(None):
        b = _board()
        b["game_parlays"] = GP.build(b, "nba")
        first = GP.from_report(b, "nba", GAME, _picks())
        # The game posted three-leg tickets that ride two legs twice each (an earlier build's).
        held = copy.deepcopy(first["threes"])
        one, two = held[0]["legs"][0], held[0]["legs"][1]
        pair = {one["player"], two["player"]}
        rest = [l for t in held for l in t["legs"] if l["player"] not in pair]
        held[1]["legs"] = [one, two, rest[0]]
        held[2]["legs"] = [rest[1], rest[2], rest[3]] if len(rest) > 3 else held[2]["legs"]
        b2 = _board()
        b2["game_parlays"] = GP.build(b2, "nba")
        b2[GP.POSTED_KEY] = {KEY: {"threes": [list(map(list, GP.ident(t))) for t in held],
                                   GP.POSTED_TICKETS: {"threes": held}}}
        assert GP._cap_prior(b2, GAME, "nba", first["threes"]) == GP.game_uses(held)
        x = GP.from_report(b2, "nba", GAME, _picks())
    assert x["twos"], x.get("twos_note")
    assert not any(l["player"] in pair for t in x["twos"] for l in t["legs"]), (pair, _legs(x["twos"]))
    assert max(_uses(held, x["twos"]).values()) <= 2
    assert GP._cap_prior(b2, GAME, "nfl", first["threes"]) is None, "no other league"


def _t(*players):
    return {"legs": [{"player": p, "market": "pts", "side": "OVER", "line": 10.5} for p in players]}


def test_a_posted_game_stands_as_posted_and_fills_under_the_cap():
    # Posted before this step: A on four tickets. It stands, every ticket as posted, and its open places fill.
    posted = {"threes": [_t("A", "B", "C"), _t("A", "D", "E")], "twos": [_t("A", "F"), _t("A", "G")]}
    x = {"threes": [_t("H", "I", "J")], "twos": [_t("K", "L")]}
    with _Env(None):
        GP.hold_posted(x, {GP.POSTED_TICKETS: copy.deepcopy(posted)}, sport="nba")
    assert _legs(x["threes"]) == _legs(posted["threes"] + [_t("H", "I", "J")])
    assert _legs(x["twos"]) == _legs(posted["twos"] + [_t("K", "L")])
    # The open places fill under the cap: A rides two posted three-leg tickets, so no two-leg ticket with A
    # fills a place, where the lock's own rule (two a list) let one in; B, on one, may ride one more.
    posted = {"threes": [_t("A", "B", "C"), _t("A", "D", "E")], "twos": [_t("F", "G"), _t("H", "I")]}
    fresh = {"threes": [_t("A", "H", "J"), _t("J", "K", "L")], "twos": [_t("A", "M"), _t("B", "N"), _t("M", "N")]}
    x = copy.deepcopy(fresh)
    with _Env(None):
        GP.hold_posted(x, {GP.POSTED_TICKETS: copy.deepcopy(posted)}, sport="nba")
    assert _legs(x["threes"][2:]) == _legs([_t("J", "K", "L")]), _legs(x["threes"])
    assert _legs(x["twos"][2:]) == _legs([_t("B", "N")]), _legs(x["twos"])
    assert max(_uses(x["threes"], x["twos"]).values()) <= 2
    y = copy.deepcopy(fresh)
    GP.hold_posted(y, {GP.POSTED_TICKETS: copy.deepcopy(posted)}, sport="nfl")
    assert _legs(y["twos"][2:]) == _legs([_t("A", "M")]), "another league: the lock's own rule, two a list"


def test_a_list_the_game_never_posted_is_kept_under_the_cap():
    posted = {"threes": [_t("A", "B", "C"), _t("A", "D", "E")]}
    x = {"threes": [], "twos": [_t("A", "F"), _t("B", "G"), _t("F", "G")]}
    with _Env(None):
        GP.hold_posted(x, {GP.POSTED_TICKETS: copy.deepcopy(posted)}, sport="nba")
    assert _legs(x["twos"]) == _legs([_t("B", "G"), _t("F", "G")]), _legs(x["twos"])
    with _Env("off"):
        z = {"threes": [], "twos": [_t("A", "F"), _t("B", "G"), _t("F", "G")]}
        GP.hold_posted(z, {GP.POSTED_TICKETS: copy.deepcopy(posted)}, sport="nba")
    assert len(z["twos"]) == 3, "off: as the lock always did"


def test_every_other_league_builds_as_it_did():
    for sport in ("nfl", "cfb", "nhl", "cbb", "mlb"):
        with _Env(None):
            on = GP.build(TL._board(sport), sport)["games"][0]
        with _Env("off"):
            off = GP.build(TL._board(sport), sport)["games"][0]
        for k in ("threes", "twos", "scorers"):
            assert _legs(on.get(k) or []) == _legs(off.get(k) or []), (sport, k)
    assert GP.GAME_CAP_SPORTS == ("nba",) and GP.game_cap_on("nba") and not GP.game_cap_on("wnba")
    with _Env("off"):
        assert not GP.game_cap_on("nba")


def test_the_rule_says_why_and_how_to_turn_it_off():
    for words in ('decision 18: "Yes limit it"', "8 legs rode four tickets each; 4 of those 8 lost",
                  "Off without a deploy: ``sudo ./deploy/setenv.sh QB_GAME_LEG_CAP off``"):
        assert words in " ".join(SRC.replace("#:", " ").split()), words
    body = SRC[SRC.index("def report_only("):SRC.index("def ", SRC.index("def report_only(") + 10)]
    assert 'hold_posted(x, mine, sport=str(gp.get("sport") or "").lower())' in body


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    fails = 0
    for fn in tests:
        try:
            fn()
            print(f"  ok  {fn.__name__}")
        except Exception as exc:                              # noqa: BLE001
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {fn.__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed.")
    sys.exit(1 if fails else 0)
