"""The any-platform draft assistant and the plan on the page.

Ethan, 2026-09-02: "a tool to help users in their draft while they are
doing it." The Sleeper room had one; every other room did not. These pin
the endpoint the assistant posts to, the bounds it puts on a stranger's
input, and the page functions that draw the plan and take the marks.

Run directly: `python3 tests/test_draft_assistant.py`
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import server                                                  # noqa: E402
from engine import fantasy_ranks                               # noqa: E402


def _board():
    names = [("Christian McCaffrey", "RB", 12.5), ("Bijan Robinson", "RB", 8.8),
             ("Puka Nacua", "WR", 8.6), ("Trey McBride", "TE", 7.7),
             ("Jahmyr Gibbs", "RB", 7.6), ("Ja'Marr Chase", "WR", 7.1),
             ("Josh Allen", "QB", 5.7), ("Amon-Ra St. Brown", "WR", 6.0),
             ("Chase Brown", "RB", 5.1), ("Chris Olave", "WR", 4.3)]
    board = [{"key": fantasy_ranks.normalize(n), "player": n, "position": p,
              "vorp": v, "proj": v + 12, "tier": 1 + i // 3, "team": "T"}
             for i, (n, p, v) in enumerate(names)]
    ranks = {r["key"]: i + 1 for i, r in enumerate(board)}
    return board, ranks


def _handler(board, ranks):
    h = object.__new__(server.Handler)
    sent = []
    h._send = lambda code, body, ext=".json": sent.append((code, json.loads(body)))
    h._kit_and_ranks = lambda: (board, ranks, {})
    return h, sent


def test_the_endpoint_returns_advice_and_a_plan_for_a_marked_draft():
    board, ranks = _board()
    h, sent = _handler(board, ranks)
    h._draft_plan({"teams": 2, "slot": 1, "rounds": 4,
                   "order": [{"player": "Christian McCaffrey", "mine": True},
                             {"player": "Bijan Robinson", "mine": False},
                             {"player": "Puka Nacua", "mine": False}]})
    code, out = sent[0]
    assert code == 200
    a, plan = out["advice"], out["plan"]
    assert a["slot"] == 1 and a["picks_made"] == 3 and a["on_the_clock"] is True
    assert a["have"] == {"RB": 1}
    assert plan["picks_made"] == 3 and plan["rounds"][0]["pick"] == 4
    gone = {"christian mccaffrey", "bijan robinson", "puka nacua"}
    planned = {r["plan"]["key"] for r in plan["rounds"] if r["plan"]}
    assert not planned & gone
    assert out["board_rounds"][0]["tag"] in ("fair", "value", "reach")


def test_a_strangers_numbers_are_clamped_not_trusted():
    board, ranks = _board()
    h, sent = _handler(board, ranks)
    h._draft_plan({"teams": 999, "slot": -4, "rounds": 10 ** 6,
                   "slots": {"QB": 40, "RB": "x"}})
    code, out = sent[0]
    assert code == 200
    assert out["plan"]["teams"] == 20 and out["plan"]["slot"] == 1
    assert out["plan"]["n_rounds"] == 30 and len(out["plan"]["rounds"]) == 30
    assert out["slots"]["QB"] == 4 and out["slots"]["RB"] == 2
    h._draft_plan({"teams": "twelve"})
    assert sent[1][0] == 400


def test_a_gated_reader_gets_an_honest_empty_not_a_plan_over_nothing():
    h, sent = _handler([], {})
    h._draft_plan({"teams": 12, "slot": 3})
    code, out = sent[0]
    assert code == 200 and out["empty"] is True and "not available" in out["note"]


def test_the_route_is_a_post_beside_the_parlay_check():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def do_POST(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert '"/api/draftplan"' in body
    assert "return self._draft_plan(body)" in body


def test_the_live_room_and_the_marked_room_read_one_kit():
    src = open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()
    i = src.index("def _draft_plan(")
    body = src[i:src.index("\n    def ", i + 1)]
    assert "self._kit_and_ranks()" in body
    assert "fantasy_pick.advice(draft, picks, ranks, board, \"me\"" in body
    assert "draftplan.build(" in body


def _app():
    return open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()


def test_the_page_draws_the_plan_and_the_assistant_inside_the_kit():
    app = _app()
    from _windows import function
    kit = function(app, "function draftKitHTML(")
    assert "${dkAssistantHTML(kit)}" in kit and "${dkPlanHTML(kit)}" in kit
    for fn in ("dkPlanHTML", "dkAssistantHTML", "dkPlanRefresh", "dkBindPlan",
               "dkAssistSearch", "dkAssistMark", "dkPlanBodyHTML", "dkAssistAdviceHTML"):
        assert f"function {fn}(" in app, fn


def test_the_assistant_posts_the_marked_picks_and_survives_a_sleeping_phone():
    app = _app()
    from _windows import function
    body = function(app, "async function dkPlanRefresh(")
    assert 'fetch("/api/draftplan"' in body and 'method: "POST"' in body
    assert "taken: dkPlan.order.filter((o) => !o.mine)" in body
    save = function(app, "function dkPlanSave(")
    assert "localStorage.setItem(DK_PLAN_KEY" in save


def test_marks_cross_players_off_every_surface():
    app = _app()
    from _windows import function
    body = function(app, "function dkCrossOff(")
    assert "dkAssistTaken()" in body
    assert "new Set([...(live || []), ...marked])" in body


def test_the_plan_binds_where_the_kit_binds():
    app = _app()
    from _windows import function
    body = function(app, "function dkBindMore(")
    assert "dkBindPlan();" in body


def test_the_doc_exists_and_names_both_tools():
    doc = open(os.path.join(ROOT, "docs", "DRAFT_PLAN.md"), encoding="utf-8").read()
    assert "POST /api/draftplan" in doc and "engine/draftplan.py" in doc


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
