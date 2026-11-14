"""Fantasy 101: the game in a minute, at the top of the Fantasy room.

Ethan, 2026-10-27: "I don't know how fantasy works. I don't know how that
shit works." What these hold (js/fantasy.js ff101HTML):

  - the card opens the room on both of its paths (with the usage board and
    without it), above everything else;
  - it says the game (draft, a lineup a week, real stats are points, one
    opponent a week), the scoring, the week's rhythm and the words every
    tab uses, and where to start;
  - it is open on the first visit and then as the reader left it (seen
    once, it folds to its one line), decided once a page load, in a
    storage that may be refused.

    python3 tests/test_fantasy_101.py
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FANTASY = (ROOT / "web" / "js" / "fantasy.js").read_text(encoding="utf-8")
CSS = (ROOT / "web" / "css" / "fantasy.css").read_text(encoding="utf-8")


def _fn(name):
    i = FANTASY.index(f"function {name}(")
    return FANTASY[i:FANTASY.index("\n}\n", i) + 3]


def _const(name):
    i = FANTASY.index(f"const {name} = ")
    return FANTASY[i:FANTASY.index(";\n", i) + 2]


def _card(stored, again=False):
    js = f"""
    const escapeHtml = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    let store = {json.dumps(stored)};
    const localStorage = {{ getItem: (k) => {{ if (store === "throws") throw new Error("denied"); return store; }},
                           setItem: (k, v) => {{ store = v; }} }};
    {_const("FF101_KEY")}
    {_const("FF101_TERMS")}
    let _ff101Now = null;
    {_fn("ff101Open")}
    {_fn("ff101HTML")}
    const first = ff101HTML();
    {"_ff101Now = null;" if again else ""}
    console.log(JSON.stringify({"ff101HTML()" if again else "first"}));"""
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_it_opens_the_room_on_both_paths():
    body = FANTASY[FANTASY.index("async function renderFantasy("):]
    body = body[:body.index("\n}\n")]
    assert body.count("ff101HTML()") == 2, "with the usage board and without it"
    assert "const _ffLead = `${ff101HTML()}" in body and "host.innerHTML = _ffLead + " in body
    assert body.count("ff101Bind(host);") == 2


def test_it_says_the_game_the_points_the_week_and_the_words():
    html = _card(None)
    text = re.sub(r"<[^>]+>", " ", html)
    for said in ("Draft a team.", "Start a lineup every week.", "Their real games are your points.",
                 "Beat one team a week.", "a point per catch", "Inactives come out 90 minutes before kickoff",
                 "Start here:", "FAAB", "Handcuff", "Floor / ceiling", "Q / D / Out / IR"):
        assert said in text, said


def test_open_on_the_first_visit_then_as_the_reader_left_it():
    assert "<details class=\"card ff101\" open>" in _card(None), "a first visit opens it"
    assert "<details class=\"card ff101\">" in _card(None, again=True), "seen once, the next visit folds it"
    assert "<details class=\"card ff101\">" in _card("closed")
    assert "<details class=\"card ff101\">" in _card("seen")
    assert "<details class=\"card ff101\" open>" in _card("open"), "left open, it opens open"
    assert "<details class=\"card ff101\" open>" in _card("throws"), "a refused storage still shows it"
    assert "let _ff101Now = null;" in FANTASY, "decided once a page load: a redraw never shuts it"
    bind = _fn("ff101Bind")
    assert 'localStorage.setItem(FF101_KEY, d.open ? "open" : "closed")' in bind and "catch (e)" in bind
    assert "_ff101Now = d.open;" in bind


def test_its_styles_are_the_rooms():
    for cls in ("ff101", "ff101-k", "ff101-steps", "ff101-n", "ff101-week", "ff101-start", "ff101-words",
                "ff101-terms"):
        assert f".{cls}" in CSS, cls


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
    sys.exit(0)
