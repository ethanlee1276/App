"""A player read says when his quarterback is out, and what that did.

Ethan, 2026-09-28, on Colston Loveland with Caleb Williams out: "are we
using that in our picks … I don't see it displayed here like it's a factor
for these players." engine/qbchange prices it where measured (receivers'
yards and catches behind a downgrade); tight ends, backs and touchdowns
are shown and left alone. The read now says which.

Run directly: `python3 tests/test_a_read_says_who_is_throwing.py`
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
QB = (ROOT / "engine" / "qbchange.py").read_text(encoding="utf-8")


def _fn(name):
    i = APP.index(f"function {name}(")
    depth, j = 0, APP.index("{", i)
    for k in range(j, len(APP)):
        depth += {"{": 1, "}": -1}.get(APP[k], 0)
        if depth == 0:
            return APP[i:k + 1]


def test_the_read_card_draws_it():
    assert "${scanQbLine(x)}" in _fn("scanReadHTML")


def test_the_words_match_what_was_measured():
    assert '("rec_yds", "WR", "downgrade"): 0.897' in QB and '("receptions", "WR", "downgrade"): 0.912' in QB
    fn = _fn("scanQbLine")
    assert "about 10% of their yards and 9% of their catches" in fn


def test_each_position_gets_its_own_sentence():
    if not shutil.which("node"):
        print("  SKIP node is not installed")
        return
    prog = "const escapeHtml = (s) => String(s);\n" + _fn("scanQbLine") + """
const state = {data: {qb_changes: [{team: "CHI", starter: "Caleb Williams", status: "OUT",
  replacement: "Tyson Bagent", tier: "downgrade", headline: "Caleb Williams (OUT) — Tyson Bagent starts"}]}};
const out = {
  te: scanQbLine({team: "CHI", pos: "TE", player: "Colston Loveland"}),
  wr: scanQbLine({team: "CHI", pos: "WR", player: "Luther Burden III"}),
  qb: scanQbLine({team: "CHI", pos: "QB", player: "Tyson Bagent"}),
  rb: scanQbLine({team: "CHI", pos: "RB", player: "Kyle Monangai"}),
  other: scanQbLine({team: "PHI", pos: "WR", player: "A. J. Brown"})};
console.log(JSON.stringify(out));
"""
    got = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    assert got.returncode == 0, got.stderr[-400:]
    import json
    o = json.loads(got.stdout)
    # Tight ends are named as the exception since 2026-09-28: their catches
    # rose behind a backup (qbfit, 2021-25), not enough to price.
    assert "Tyson Bagent starts" in o["te"] and "Tight ends are the exception" in o["te"] and "left alone" in o["te"]
    assert "taken off his numbers" in o["wr"]
    assert "Starting in place of Caleb Williams" in o["qb"]
    assert "ran only about 3% more often" in o["rb"] and "carries and yards did not move" in o["rb"]
    assert o["other"] == "", "the other team's players are not told about CHI's quarterback"
    assert "ms-read-qb-vol" not in o["wr"], "no volume line on a card that carries none"


def test_every_team_with_a_change_says_what_those_teams_did():
    """Ethan, 2026-09-28, on the Bears: "they will probably be loosing which
    will cause more throwing … they might run more" — then "you should do
    it for all the teams". The measured team volume rides every QB-change
    card (qbchange.card) and every read of that team."""
    from engine import qbchange as Q
    assert Q.volume_line("downgrade") == ("Teams behind a quarterback this far below the starter (236 games, "
                                         "2021–25): 3% fewer pass attempts, 5% fewer completions, "
                                         "7% fewer passing yards, 1% more carries")
    assert Q.volume_line("similar").startswith("Teams behind a quarterback who had thrown like the starter (193 games")
    assert Q.volume_line(None) == "" and Q.volume_line("unknown") == ""
    ch = {"team": "CHI", "starter": "Caleb Williams", "status": "OUT", "replacement": "Case Keenum",
          "tier": "downgrade", "starter_ypa": 7.1, "replacement_ypa": 5.9, "replacement_attempts": 40}
    assert Q.card(ch)["volume"] == Q.volume_line("downgrade")
    assert Q.card(dict(ch, status="RETURNS"))["volume"] == "", "a starter back gets no backup numbers"
    fit = (ROOT / "engine" / "qbfit.py").read_text(encoding="utf-8")
    assert '"team_pass_att": ("attempts", "QB")' in fit and '"team_carries": ("carries", None)' in fit, \
        "the numbers are re-measurable, not typed in"
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert '${c.volume ? `<div class="mu-line">${escapeHtml(c.volume)}.</div>` : ""}' in app, "the pick card's QB box"
    if not shutil.which("node"):
        return
    prog = "const escapeHtml = (s) => String(s);\n" + _fn("scanQbLine") + """
const state = {data: {qb_changes: [{team: "CHI", starter: "Caleb Williams", status: "OUT", replacement: "Case Keenum",
  tier: "downgrade", headline: "x", volume: "Teams behind a quarterback this far below the starter (236 games, 2021–25): 3% fewer pass attempts"}]}};
console.log(JSON.stringify([scanQbLine({team: "CHI", pos: "WR", player: "A"}), scanQbLine({team: "CHI", pos: "RB", player: "B"})]));
"""
    got = subprocess.run(["node", "-e", prog], capture_output=True, text=True, timeout=60)
    import json
    wr, rb = json.loads(got.stdout)
    for line in (wr, rb):
        assert '<span class="ms-read-qb-vol">Teams behind a quarterback this far below the starter' in line


def test_the_carries_claim_was_measured_not_assumed():
    """Both of Ethan's Eagles-Bears reports bet a back's carries on "Keenum
    starting means more runs"; the harness now measures carries and the
    team's run share beside the rest, and neither cleared the bar."""
    qf = (ROOT / "engine" / "qbfit.py").read_text(encoding="utf-8")
    assert '"rush_att": ("carries", 5.0)' in qf and 'TEAM_RUN_SHARE = "team_run_share"' in qf
    assert 'if m in ("rush_yds", "rush_att") and pos != "RB":' in qf
    assert ("rush_att", "RB", "downgrade") not in __import__("engine.qbchange", fromlist=["EFFECT"]).EFFECT


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
