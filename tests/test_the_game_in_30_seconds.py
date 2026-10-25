"""The game in 30 seconds: a finished game's story on one card before the
rooms (js/detail.js pbpRecapHTML). Off the game's own file: the play of the
game, a comeback when the winner's win chance fell under thirty, the lead
changes and the biggest lead, the night's best line; a Share.

    python3 tests/test_the_game_in_30_seconds.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DET = (ROOT / "web" / "js" / "detail.js").read_text()


def _run(script):
    src = DET[DET.index("const AWAY_KEY"):DET.index("function pbpAwayHTML(")]
    src += DET[DET.index("function recapTop("):DET.index("if (typeof window !== \"undefined\" && !window._recapBound)")]
    prog = ("const escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
            "const escapeAttr = escapeHtml;\n" + src + "\n" + script)
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True)
    if out.returncode == 127:
        return None
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_a_comeback_the_play_of_the_game_and_the_best_line():
    got = _run("""
      const plays = [
        { event: "Rush", away_score: 13, home_score: 3, wp: 18, rating: 4, players: ["Najee Harris"] },
        { event: "Passing Touchdown", yards: 31, away_score: 13, home_score: 17, wp: 71, rating: 7.8, swing: "go_ahead", players: ["Ja'Marr Chase"] },
        { event: "Field Goal", away_score: 20, home_score: 17, wp: 40, rating: 5 },
        { event: "Rush", away_score: 20, home_score: 24, wp: 99, rating: 6, players: ["Chase Brown"] }];
      const d = { home: "CIN", away: "PIT", live: { state: "final", away_score: 20, home_score: 24 }, plays,
                  players: [{ player: "Joe Burrow", team: "CIN", stats: { pass_yds: 322, pass_td: 3 } },
                            { player: "<i>Kicker</i>", team: "PIT", stats: {} }] };
      console.log(JSON.stringify({ card: pbpRecapHTML(d, "nfl"), live: pbpRecapHTML({ ...d, live: { state: "live" } }, "nfl"),
        facts: recapFacts(d, "nfl") }));""")
    if got is None:
        return
    card, f = got["card"], got["facts"]
    assert "The game in 30 seconds" in card and "PIT <b>20</b> – <b>24</b> CIN" in card
    assert "Go-ahead · Ja&#39;Marr Chase — Passing Touchdown +31 yds" in card and "<em>7.8</em>" in card
    assert "CIN won after falling to 18% to win" in card
    assert f["changes"] == 3 and f["big"] == {"n": 10, "side": "PIT"}, f
    assert "Joe Burrow (CIN): 322 pass yds, 3 TD" in card
    assert got["live"] == "", "a game still on has no recap"


def test_every_page_gets_it_and_share_is_the_phones_own_sheet():
    assert "${pbpAwayHTML(d, league)}${pbpRecapHTML(d, league)}" in DET
    assert "pbpAwayHTML(d, league) + pbpRecapHTML(d, league) + pbpCallItHTML(d, league)" in DET
    share = DET[DET.index("if (typeof window !== \"undefined\" && !window._recapBound)"):]
    assert "navigator.share({ title: \"Qellys Book\", text })" in share[:700] and "navigator.clipboard.writeText(text)" in share[:700]


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
