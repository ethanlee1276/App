"""Next man up, on the injuries page.

Ethan, 2026-09-05: "next man up on injurie page". Beside a man who is
Out, Doubtful or on IR: who holds his work now, with the share each
already holds — the same join the waiver board makes, turned to face
the injured man. NFL only, because the usage shares behind it are
measured for the NFL only.

Pinned: the engine names every injured skill player's heirs, ranked by
the share they already hold, never the injured man himself, never a
Questionable man or a lineman, and never an empty list; the board
carries it under the free `waivers` key; the page reads it once,
draws it under the row, and says what it is.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import waivers, gate                                    # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()

# DELIBERATELY OUT OF SHARE ORDER, so the ranking has to be earned; and a
# second Falcons receiver, so a Questionable man WOULD have an heir if the
# status rule ever let him vacate.
USAGE = [
    {"player": "Avery Williams", "team": "ATL", "position": "RB", "season": 0.05, "headshot": ""},
    {"player": "Jase McClellan", "team": "ATL", "position": "RB", "season": 0.02, "headshot": ""},
    {"player": "Bijan Robinson", "team": "ATL", "position": "RB", "season": 0.62, "headshot": "h1"},
    {"player": "Tyler Allgeier", "team": "ATL", "position": "RB", "season": 0.31, "headshot": "h2"},
    {"player": "Drake London", "team": "ATL", "position": "WR", "season": 0.29, "headshot": ""},
    {"player": "Darnell Mooney", "team": "ATL", "position": "WR", "season": 0.22, "headshot": ""},
    {"player": "Saquon Barkley", "team": "PHI", "position": "RB", "season": 0.70, "headshot": ""},
]
INJ = [
    {"team": "Atlanta Falcons", "player": "Bijan Robinson", "position": "RB", "status": "Out"},
    {"team": "Atlanta Falcons", "player": "Drake London", "position": "WR", "status": "Questionable"},
    {"team": "Atlanta Falcons", "player": "Jake Matthews", "position": "OT", "status": "Out"},
    {"team": "Philadelphia Eagles", "player": "Saquon Barkley", "position": "RB", "status": "Injured Reserve"},
    {"team": "Carolina Panthers", "player": "Chuba Hubbard", "position": "RB", "status": "Doubtful"},
]


def _fn(name):
    i = APP.index(f"function {name}(")
    if APP[i - 6:i] == "async ":
        i -= 6
    ends = [APP.find(m, i + 10) for m in ("\nfunction ", "\nasync function ", "\nconst ", "\nlet ", "\n/* ")]
    ends = [e for e in ends if e != -1] or [len(APP)]
    return APP[i:min(ends)]


# --- the engine ------------------------------------------------------------------
def test_every_injured_skill_player_gets_his_heirs_ranked_by_the_share_they_hold():
    got = waivers.next_up(INJ, USAGE)
    assert [e["hurt"] for e in got] == ["Bijan Robinson"], [e["hurt"] for e in got]
    e = got[0]
    assert e["team"] == "Atlanta Falcons" and e["position"] == "RB" and e["status"] == "Out"
    assert [h["player"] for h in e["heirs"]] == ["Tyler Allgeier", "Avery Williams", "Jase McClellan"]
    assert e["heirs"][0]["share"] == 0.31 and e["heirs"][0]["headshot"] == "h2"
    assert all(h["player"] != "Bijan Robinson" for h in e["heirs"]), "the injured man is never his own heir"


def test_a_questionable_man_a_lineman_and_a_man_with_nobody_behind_him_are_left_out():
    got = {e["hurt"] for e in waivers.next_up(INJ, USAGE)}
    assert "Drake London" not in got, "Questionable resolves to played too often to vacate a job"
    assert "Jake Matthews" not in got, "a vacancy at tackle moves nothing anyone can claim"
    assert "Saquon Barkley" not in got, "nobody measured behind him — no entry rather than an empty one"
    assert "Chuba Hubbard" not in got, "a team the usage board does not know"


def test_heirs_are_capped_and_the_cap_is_a_parameter():
    assert waivers.HEIRS == 3
    got = waivers.next_up(INJ, USAGE, heirs=1)
    assert [h["player"] for h in got[0]["heirs"]] == ["Tyler Allgeier"]


def test_the_board_carries_it_under_the_free_waivers_key_and_vacancies_name_the_hurt_man():
    b = waivers.board(USAGE, INJ)
    assert "next_up" in b and b["next_up"][0]["hurt"] == "Bijan Robinson"
    assert "waivers" not in gate.PAID_KEYS_BY_FILE["fantasy.json"], "a measured role is a fact, free like the injuries beside it"
    vac = waivers.vacancies(INJ, USAGE)
    assert vac and vac[0]["hurt"] == "Bijan Robinson" and vac[0]["hurt_status"] == "Out"


# --- the page --------------------------------------------------------------------
def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    k = APP.index("const nextUpKey = ")
    key_line = APP[k:APP.index("\n", k)]
    prog = f"""
      const icon = (n) => `<i data-icon="${{n}}"></i>`;
      {_fn("escapeHtml")}
      const escapeAttr = escapeHtml;
      {_fn("nextUpLine")}
      {key_line}
      console.log(JSON.stringify((() => {{ {js} }})()));
    """
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_line_names_three_heirs_with_their_shares_and_nothing_without_one():
    got = _node("""
      const e = { hurt: "Bijan Robinson", team: "Atlanta Falcons", position: "RB", status: "Out",
                  heirs: [{player: "Tyler Allgeier", share: 0.31}, {player: "Avery Williams", share: 0.05},
                          {player: "Jase McClellan", share: 0.02}, {player: "Fourth Man", share: 0.01}] };
      const strip = (h) => h.replace(/<[^>]+>/g, "");
      return { line: strip(nextUpLine(e)), raw: nextUpLine(e), none: nextUpLine(null), empty: nextUpLine({heirs: []}),
               key: nextUpKey({player: " Bijan Robinson", team: "Atlanta Falcons "}),
               noShare: strip(nextUpLine({heirs: [{player: "X", share: null}]})) };""")
    if got is None:
        print("  SKIP node not installed"); return
    assert got["line"] == " Next man up: Tyler Allgeier 31% · Avery Williams 5% · Jase McClellan 2%", got["line"]
    assert "Fourth Man" not in got["raw"] and 'class="inj-next"' in got["raw"]
    assert "while Bijan Robinson is Out" in got["raw"]
    assert got["none"] == "" and got["empty"] == ""
    assert got["key"] == "bijan robinson|atlanta falcons"
    assert got["noShare"].endswith("X —")


def test_the_page_reads_it_once_draws_it_under_the_row_and_says_what_it_is():
    i = APP.index("async function renderInjuries()")
    body = APP[i:APP.index("\n/* ONE TEAM, FOLDED", i)]
    assert 'if (sport === "nfl") {' in body and "const fx = await loadNextUp();" in body
    assert "_nextUp.set(nextUpKey({ player: e.hurt, team: e.team }), e)" in body
    assert "<b>Next man up</b> names who holds an injured man’s work" in body
    assert "never a\n      claim about who is on your league’s wire" in body
    row = _fn("injRow")
    assert "${nextUpLine(_nextUp.get(nextUpKey(r)))}" in row
    ld = _fn("loadNextUp")
    assert 'paidFetch("fantasy.json")' in ld and "5 * 60e3" in ld, "the same file the fantasy page reads, cached like the injury board"
    assert ".inj-next {" in CSS


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    sys.exit(1 if fails else 0)
