"""Every game report line that names a rank says the number behind it (step AHR, 25 November 2026).

Ethan, after the Tucker Kraft fade (step AHO): "keep going and fix the rest of the game reports too". The fade read
"the Rams give up the second-fewest passing yards" with nothing on what they give up to tight ends; the same shortcut,
a rank or a word ("lately") with no number, was in other report sections. What holds:

  * the short version's big-day and hard-day line, for a receiver or a tight end read on the pass defence overall,
    adds what the defence gives up to his own position ("and 151 receiving yards a game to wide receivers (the
    ninth-most)");
  * the trenches' pass-protection line says how often each side's pressure lands, beside the ranks;
  * a hockey goalie's form says the games it covers ("over the last 18 games", not "lately"), and his starts say of
    how many ("started 70% of the Bruins' last 10 games");
  * hockey's busy-night line says the shots a game beside the ranks;
  * a basketball injury line says what the player puts up (minutes and points a game over the last ten);
  * a breakout or fade card says his share once, on its role line, and the next note takes the place.

    python3 tests/test_every_report_line_says_its_numbers.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import gamereport as GR                                  # noqa: E402


def _section(rep, key):
    return next(s for s in rep["sections"] if s["key"] == key)


def _items(sec):
    return [x for b in sec["blocks"] for x in (b.get("items") or []) if isinstance(x, str)]


def test_the_short_version_says_a_receivers_own_position():
    import test_the_game_report_reads_like_the_research as T
    allowed = {k: dict(v) for k, v in T.ALLOWED.items()}
    allowed["DET"]["wr_rec_yds"] = {"pg": 151.0, "league": 140.0, "rank": 9, "of": 32, "games": 5}
    rep = T._report(allowed=allowed)
    big = next(x for x in _items(_section(rep, "short")) if x.startswith("Who could have a big day"))
    assert ("Christian Watson, the Packers' wide receiver — the Lions give up the most passing yards (320 a game), "
            "and 151 receiving yards a game to wide receivers (the ninth-most)") in big, big
    # Without the number, the reason as it was.
    rep = T._report()
    big = next(x for x in _items(_section(rep, "short")) if x.startswith("Who could have a big day"))
    assert "the Lions give up the most passing yards (320 a game)." in big, big


def test_the_trenches_say_the_pressure_rates():
    import test_the_game_report_reads_like_the_research as T
    lines = _items(_section(T._report(), "trenches"))
    assert ("GB's pass protection ranks 22nd (pressure on 16% of dropbacks) against DET's pass rush (5th, pressure on "
            "16%) — edge DET.") in lines, lines


def test_a_goalies_form_says_its_games():
    from engine.nhl import scan as N
    assert N.gsax_words(4.2, 20) == "has stopped 4.2 more goals than expected over the last 20 games"
    assert N.gsax_words(-3.4, 1) == "has let in 3.4 more goals than expected in the last game"
    assert N.gsax_words(-3.4) == "has let in 3.4 more goals than expected lately", "no window known, the old word"
    teams = {f"T{i:02d}": {"sog_against": 25.0 + i * 0.3, "ga": 2.5, "xga_ev": 2.0, "sog_for": 30.0} for i in range(32)}
    ctx = {"BOS": {"starter": "Jeremy Swayman", "starter_sure": True, "gsax": -3.4, "gsax_games": 18}}
    r = N.read_skater("Auston Matthews", {"games": []}, "T00", "BOS", teams, ctx, {})
    assert "Faces Jeremy Swayman, who has let in 3.4 more goals than expected over the last 18 games" in r["pro"], r
    src = (ROOT / "nhl_build.py").read_text(encoding="utf-8")
    assert 'gsax_games=gk[starter].get("games")' in src


def test_hockeys_report_says_the_shots_and_the_starts():
    import test_every_league_gets_a_game_report as T
    rep, _line = T._attach(T._nhl_board(), "nhl")
    tape = _items(_section(rep, "tape"))
    assert ("TOR takes the second-most shots (33.2 a game), and BOS allows the sixth-most (31.5 a game) — a busy "
            "night for BOS's goalie.") in tape, tape
    net = _items(_section(rep, "goalies"))
    assert any(x.endswith("started 70% of the Bruins' last 10 games.") for x in net), net


def test_a_basketball_injury_says_what_goes_missing():
    import test_every_league_gets_a_game_report as T
    board, meta = T._nba_board()
    rep, _line = T._attach(board, "nba", meta=meta)
    inj = _items(_section(rep, "injuries"))
    assert "Tyler Herro (MIA) — out, ankle — 34 minutes and 22.7 points a game over the last 3." in inj, inj
    from engine import leaguereport as L
    assert L._recent_line({"minutes": [30, 31]}) == {}, "two games say nothing"


def test_a_card_says_his_share_once():
    """The card's role line says his share; the read's own share note gives its place to the next note."""
    from engine import breakouts as BO, gamescan as S
    allowed = {"qb_pass_yds": {"pg": 198.0, "rank": 31, "of": 32, "games": 11},
               "wr_rec_yds": {"pg": 111.0, "rank": 31, "of": 32, "games": 11}}
    r = S.player_read("Puka Nacua", "LA", "GB", "WR", usage={"tgt_share": 0.31, "targets_pg": 10.0, "games": 11},
                      ratings={}, room=None, scheme=None, split=None, tackling=None, line_out=None, mates_out=None,
                      n_teams=32, allowed=allowed, points=22.0, line_words="", weather=None)
    assert r["notes"][0] == r["role"][0] == "Commands 31% of the targets (10 a game)", r["notes"]
    why = BO.card(r, "down", role="31% of the targets (10 a game)")["why"]
    assert not any("Commands 31%" in w for w in why), why
    assert any(w.startswith("Against wide receivers, GB allows 111 receiving yards") for w in why), why
    assert any("Commands 31%" in w for w in BO.card(r, "down")["why"]), "no role line on the card: the note stays"


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
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
