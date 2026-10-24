""""Change these" compares the best lineup to the one you have got in.

Ethan, 2026-09-09: *"if you should bench them for that week"*. The League
desk has had a "Change these" section since August and it has never once
rendered.

WHY, and it is structural rather than a typo. `swaps` compared the
computed `starters` against `bench`. But `starters` is `assign`, a
maximum-weight matching — so if a bench player could beat the starter
whose seat he is eligible for, that swap would raise the total and the
matching would already have made it. The list was empty by construction,
on every roster, forever, and the fallback under it printed every week:
"Nothing to change — this is already the best legal lineup on your
roster." Which was TRUE of the lineup we computed and said nothing about
the lineup he had set, the only one he can change.

`test_the_old_rule_could_not_fire` is the load-bearing one here. It
reproduces the old comparison over random rosters and shows it finding
nothing — otherwise "the new rule finds swaps" would just be a fixture I
chose, with no evidence the old one was broken.

Run directly: `python3 tests/test_lineup_swaps.py`
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import fantasy_lineup as FL                      # noqa: E402

SLOTS = ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX"]


def _roster(*spec):
    """`("Name", "WR", points, starting)` → the roster and means pair."""
    roster, means = [], {}
    for name, pos, pts, starting in spec:
        roster.append({"player": name, "position": pos, "starting": starting})
        means[name] = {"position": pos, "fp_ppr": float(pts), "_games": 10}
    return roster, means


def _lineup(*spec):
    roster, means = _roster(*spec)
    return FL.lineup(roster, SLOTS, {}, means)


#: A roster where the manager has benched his best receiver and started a
#: worse one. Everything else is seated correctly, so exactly one change
#: is right and its size is arithmetic anybody can check: 21 − 4.
_MISSET = (
    ("Qb", "QB", 20, True),
    ("Rb1", "RB", 15, True), ("Rb2", "RB", 14, True),
    ("Wr1", "WR", 21, False),           # benched, and he is the best on it
    ("Wr2", "WR", 13, True), ("Wr3", "WR", 12, True),
    ("Te1", "TE", 10, True),
    ("Flex", "RB", 9, True),
    ("Wr4", "WR", 4, True),             # started, and he should not be
)


# ------------------------------------------------- the rule that could not

def test_the_old_rule_could_not_fire():
    """The old comparison, reproduced, over three thousand random
    rosters. It finds nothing — which is the point: the section it fed
    was dead, not merely quiet."""
    random.seed(7)
    found = 0
    for _ in range(3000):
        spec = []
        for i in range(14):
            pos = random.choice(["QB", "RB", "WR", "TE"])
            spec.append((f"P{i}", pos, round(random.uniform(0, 25), 2), False))
        L = _lineup(*spec)
        started = {s["player"] for s in L["starters"] if s.get("player")}
        for s in L["starters"]:
            if not s.get("player"):
                continue
            for b in L["bench"]:
                if (FL._eligible(s["slot"], b["position"])
                        and b["points"] > s["points"] + 1e-9):
                    found += 1
    assert found == 0, (
        f"{found} bench-beats-starter pairs — the maximum-weight matching "
        "is no longer optimal, which is a bigger problem than this file")


# ------------------------------------------------------------- the new rule

def test_a_benched_star_is_named_with_the_man_he_replaces():
    L = _lineup(*_MISSET)
    assert len(L["swaps"]) == 1, L["swaps"]
    w = L["swaps"][0]
    assert w["in"] == "Wr1" and w["out"] == "Wr4", w
    assert w["slot"] in ("WR", "FLEX"), w
    # 12, NOT 21 − 4. Wr4 is not the man whose seat Wr1 takes: benching
    # him promotes Wr3 into the FLEX and everyone shuffles. The gain is
    # the whole lineup re-seated with this one move made, which is the
    # question a manager is actually asking.
    assert abs(w["gain"] - 12.0) < 1e-6, w


def test_the_gain_is_measured_against_the_lineup_he_has_in():
    L = _lineup(*_MISSET)
    assert L["current"] is not None
    # He is starting eight men for seven slots, so his own total is his
    # best seven of them: 20+15+14+13+12+10+9.
    assert abs(L["current"]["total"] - 93.0) < 1e-6, L["current"]
    # The best lineup flexes Wr3 (12), not the 9-point back — 20+15+14+
    # 21+13+10+12.
    assert abs(L["total"] - 105.0) < 1e-6, L["total"]
    assert abs(L["gain_total"] - 12.0) < 1e-6, L["gain_total"]
    assert "Wr1" not in L["current"]["players"]


def test_a_correct_lineup_reports_nothing_to_change():
    """Same roster, Wr1 started instead of Wr4. The distinction that
    matters: an EMPTY list, not a missing one."""
    L = _lineup(
        ("Qb", "QB", 20, True),
        ("Rb1", "RB", 15, True), ("Rb2", "RB", 14, True),
        ("Wr1", "WR", 21, True),
        ("Wr2", "WR", 13, True), ("Wr3", "WR", 12, True),
        ("Te1", "TE", 10, True),
        ("Flex", "RB", 9, True),
        ("Wr4", "WR", 4, False),
    )
    assert L["swaps"] == [], L["swaps"]
    assert L["current"] is not None, "an optimal lineup is not an invisible one"
    assert L["gain_total"] == 0.0, L["gain_total"]


def test_an_empty_slot_is_a_change_with_nobody_coming_out():
    """He left a seat open. There is somebody to put in it and nobody to
    take out, and "out: null" is how the desk draws that."""
    L = _lineup(
        ("Qb", "QB", 20, True),
        ("Rb1", "RB", 15, True), ("Rb2", "RB", 14, True),
        ("Wr1", "WR", 21, True), ("Wr2", "WR", 13, True),
        ("Te1", "TE", 10, True),
        ("Flex", "RB", 9, False),        # the FLEX seat is empty
    )
    assert len(L["swaps"]) == 1, L["swaps"]
    assert L["swaps"][0]["out"] is None
    assert L["swaps"][0]["in"] == "Flex"
    assert abs(L["swaps"][0]["gain"] - 9.0) < 1e-6


# ------------------------------------------------- what it refuses to claim

def test_a_platform_that_never_said_who_you_started_gets_none_not_empty():
    """ESPN and Yahoo hand us a roster with no lineup on it. `None` and
    `[]` mean two different things — "we cannot see it" and "it is
    already right" — and a desk that renders them the same way is lying
    politely."""
    L = _lineup(
        ("Qb", "QB", 20, False), ("Rb1", "RB", 15, False),
        ("Wr1", "WR", 21, False), ("Te1", "TE", 10, False),
    )
    assert L["current"] is None
    assert L["gain_total"] is None
    assert L["swaps"] == []


def test_the_starters_and_the_total_are_untouched_by_all_of_this():
    """The optimiser is not what changed. Same roster, marked two ways —
    the best lineup and its total must be identical."""
    blind = _lineup(*[(n, p, v, False) for n, p, v, _ in _MISSET])
    seen = _lineup(*_MISSET)
    assert blind["total"] == seen["total"]
    assert ([s.get("player") for s in blind["starters"]]
            == [s.get("player") for s in seen["starters"]])



# ------------------------------------------- and the three states, drawn

_APP = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def _fn(name):
    i = _APP.index(f"function {name}(")
    j = _APP.index("{", i)
    depth = 0
    for k in range(j, len(_APP)):
        if _APP[k] == "{":
            depth += 1
        elif _APP[k] == "}":
            depth -= 1
            if depth == 0:
                return _APP[i:k + 1]
    raise AssertionError(name)


def _draw(L):
    """The real `ldSwapsHTML`, executed on a real `lineup()` payload."""
    import json
    import subprocess
    import tempfile
    src = ('function escapeHtml(s){return String(s);}\n'
           'function icon(n){return "["+n+"]";}\n'
           + _fn("ldSwapsHTML")
           + f"\nconsole.log(JSON.stringify(ldSwapsHTML({json.dumps(L)})));")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(src)
        path = fh.name
    try:
        res = subprocess.run(["node", path], capture_output=True,
                             text=True, timeout=120)
    finally:
        os.unlink(path)
    assert res.returncode == 0, res.stderr[-2000:]
    return json.loads(res.stdout)


def test_the_desk_says_what_to_change_and_what_it_is_worth():
    out = _draw(_lineup(*_MISSET))
    assert "Change these" in out
    assert "Wr1" in out and "Wr4" in out
    assert "+12" in out, out            # the header, against his 93
    assert "93" in out


def test_the_desk_tells_an_optimal_lineup_apart_from_an_invisible_one():
    """The whole reason `current` is None rather than []. These are two
    different sentences and drawing them the same way is how a page
    starts lying politely."""
    good = _draw(_lineup(
        ("Qb", "QB", 20, True), ("Rb1", "RB", 15, True), ("Rb2", "RB", 14, True),
        ("Wr1", "WR", 21, True), ("Wr2", "WR", 13, True), ("Wr3", "WR", 12, True),
        ("Te1", "TE", 10, True), ("Flex", "RB", 9, True)))
    blind = _draw(_lineup(
        ("Qb", "QB", 20, False), ("Rb1", "RB", 15, False),
        ("Wr1", "WR", 21, False), ("Te1", "TE", 10, False)))
    # Matched without the line wrap: the copy is written across two
    # source lines and asserting the joined phrase would fail on a
    # reflow that changed nothing.
    assert "Nothing to change" in good
    assert "lineup you have in IS the best" in " ".join(good.split()), good
    assert "not who you have started" in blind
    assert "Nothing to change" not in blind, \
        "an unreadable lineup was reported as a correct one"


def test_an_empty_slot_does_not_bench_a_player_called_null():
    out = _draw(_lineup(
        ("Qb", "QB", 20, True), ("Rb1", "RB", 15, True), ("Rb2", "RB", 14, True),
        ("Wr1", "WR", 21, True), ("Wr2", "WR", 13, True), ("Te1", "TE", 10, True),
        ("Flex", "RB", 9, False)))
    assert "empty slot" in out
    assert "null" not in out and "undefined" not in out


def test_the_sleeper_read_actually_carries_the_lineup_through():
    """The engine can only compare against a lineup somebody hands it.
    Sleeper's roster has `starters`; `rows_for` used to drop it on the
    floor, which is the other half of why this section was dead."""
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _league_desk(")
    body = src[i:src.index("\n    def ", i + 1)]
    j = body.index("def rows_for(")
    rows_for = body[j:body.index("\n        owner = {}", j)]
    assert '.get("starters")' in rows_for, \
        "the desk cannot see the lineup he has set"
    assert '"starting": str(pid) in seated' in rows_for
    # "0" is Sleeper's empty slot. It matches no player id, so it drops
    # out on its own — asserting the set is built from strings is what
    # keeps that true.
    assert "str(x) for x in" in rows_for

if __name__ == "__main__":
    import shutil
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    if not shutil.which("node"):
        print("SKIP(node) the three rendered states — `apt install -y nodejs`")
        fns = [f for f in fns if "desk" not in f.__name__
               and "empty_slot_does_not" not in f.__name__]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
