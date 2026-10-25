"""While you were away: back at a live game after a few minutes, the page
says what you missed before anything else (js/detail.js pbpAwayHTML).

What these hold: nothing shows on a first visit, a short absence, a game
that isn't live, or when nothing happened since; otherwise the score then
and now, a win-chance swing of five points or more, and the three biggest
plays since in the order they happened, every name escaped; the basketball
and hockey pages get it too; what was seen is kept on the device only.

    python3 tests/test_while_you_were_away.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DET = (ROOT / "web" / "js" / "detail.js").read_text()


def _run(script):
    src = DET[DET.index("const AWAY_KEY"):DET.index("function pbpAwayHTML(")]
    prog = ("const escapeHtml = (s) => String(s).replace(/[&<>\"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":'&#39;'}[c]));\n"
            + src + "\n" + script)
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True)
    if out.returncode == 127:
        return None
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_card_says_the_score_the_swing_and_the_biggest_plays_since():
    got = _run("""
      const t0 = Date.now() - 10 * 60000, at = (m) => new Date(Date.now() + m * 60000).toISOString();
      const plays = [
        { event: "Rush", yards: 3, at: at(-15), wp: 44, rating: 1, players: ["Old Play"] },
        { event: "Pass Reception", yards: 22, at: at(-8), wp: 52, rating: 3.1, players: ["Ja'Marr Chase"] },
        { event: "Sack", yards: -8, at: at(-6), wp: 47, rating: 2.4, players: ["T.J. Watt"] },
        { event: "Passing Touchdown", yards: 31, at: at(-4), wp: 71, rating: 7.8, players: ["<b>x</b>"], scoring: true, swing: "go_ahead" },
        { event: "Rush", yards: 5, at: at(-1), wp: 81, rating: 0.9, players: ["Chase Brown"] }];
      const d = { home: "CIN", away: "PIT", live: { state: "live", away_score: 14, home_score: 17 }, plays };
      const card = awayCardHTML(d, "nfl", { t: t0, a: 14, h: 10, wp: 44 });
      const none = awayCardHTML(d, "nfl", { t: Date.now(), a: 14, h: 17, wp: 81 });
      console.log(JSON.stringify({ card, none }));""")
    if got is None:
        return
    card = got["card"]
    assert "While you were away" in card and "4 plays" in card, "the plays since, not before"
    assert "PIT 14–10 CIN → <b>14–17</b>" in card
    assert "Win chance: PIT 56% → CIN 81%" in card
    li = card[card.index("<ol"):]
    assert li.index("Ja&#39;Marr Chase") < li.index("Go-ahead") < li.index("T.J. Watt") or \
        li.index("Ja&#39;Marr Chase") < li.index("T.J. Watt") < li.index("Go-ahead"), "in the order they happened"
    assert "Chase Brown" not in card, "the three biggest, not every play"
    assert "&lt;b&gt;x&lt;/b&gt;" in card and "<b>x</b>" not in card, "names escaped"
    assert got["none"] == "", "nothing happened since: no card"


def test_it_waits_for_a_real_absence_a_live_game_and_reaches_every_page():
    fn = DET[DET.index("function pbpAwayHTML("):]
    fn = fn[:fn.index("\n}\n")]
    assert '(d.live || {}).state === "live" && Date.now() - was.t > AWAY_MIN_MS' in fn
    assert "AWAY_MIN_MS = 4 * 60 * 1000" in DET
    assert "localStorage.setItem(AWAY_KEY" in fn and ".slice(40)" in fn, "kept on this device, forty games"
    assert "${pbpAwayHTML(d, league)}" in DET
    assert "callit: pbpAwayHTML(d, league) + pbpRecapHTML(d, league) + pbpCallItHTML(d, league)" in DET, \
        "basketball and hockey too"


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
