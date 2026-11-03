"""The NBA Cup's knockout bracket: the eight seeded, every round, our line,
the results as they land and the champion (engine/nbacup.bracket).

Ethan, 2026-11-03, on the 30 October audit's list — "NBA Cup knockout
bracket: the eight, quarterfinals at the higher seed, semifinals and the
final, our line on each game, results as they land, the champion" — "do all
of them". What these hold:

  * each conference's three group winners are seeded 1-3 and its wild card
    4th; the quarterfinals are 1 v 4 and 2 v 3 at the higher seed; while a
    group game is left it is the bracket "if group play ended today";
  * a knockout result is read off the knockout nights only, so a winner
    and its own group's wild card meeting again in a quarterfinal is never
    answered by their group game;
  * the semifinal is the quarterfinal winners at the better seed's arena,
    the final East v West in Indianapolis, and its winner the champion; the
    simulation keeps every result in (a team knocked out has no chance
    left, the champion every chance);
  * our line is on each game still to play, at home court but for the
    final, in a paid key; the public copy keeps the bracket whole;
  * the build asks the scoreboard only for knockout nights that have come,
    and keeps building two days past the final.

Run directly: `python3 tests/test_the_nba_cup_bracket.py`
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from engine import gate, nbacup                                  # noqa: E402


class _Cup:
    """The Cup tests' own schedule and ratings (tests/test_the_nba_cup.py),
    imported when first used."""
    def __getattr__(self, name):
        import test_the_nba_cup as C
        return getattr(C, name)


C = _Cup()

HOME, SCALE = 2.4, 8.5


def _built(extra=(), through="2026-11-27", today="2026-11-28", sims=400):
    return nbacup.build(C._schedule(played_through=through) + list(extra), C._ratings(), today, HOME, SCALE,
                        sims=sims, seed=7)


def _ko(home, away, day, hs, as_):
    return C._game(home, away, day, hs, as_)


def test_the_eight_are_seeded_and_the_quarterfinals_are_at_the_higher_seed():
    out = _built()
    br = out["bracket"]
    assert br["set"], "every group game is in"
    for conf in ("East", "West"):
        c = br["conferences"][conf]
        winners = [t for g, t in out["today"]["winners"].items() if nbacup.conference(g) == conf]
        seeds = [s["team"] for s in c["seeds"]]
        assert sorted(seeds[:3]) == sorted(winners) and seeds[3] == out["today"]["wildcards"][conf]
        assert [s["why"] for s in c["seeds"]][3] == "Wild card" and all(s["why"].endswith("winner") for s in c["seeds"][:3])
        q1, q2 = c["quarterfinals"]
        assert (q1["home"], q1["away"], q1["home_seed"], q1["away_seed"]) == (seeds[0], seeds[3], 1, 4)
        assert (q2["home"], q2["away"], q2["home_seed"], q2["away_seed"]) == (seeds[1], seeds[2], 2, 3)
        assert q1["date"] == "2026-12-04" and q1["site"] == "home" and not q1["done"]
        assert c["semifinal"]["home"] is None and c["semifinal"]["from"] == [q1["id"], q2["id"]]
    assert br["final"]["site"] == "Indianapolis" and br["champion"] is None
    early = _built(through="2026-11-07", today="2026-11-08")
    assert not early["bracket"]["set"], "with group games left it is the bracket if it ended today"


def test_results_land_round_by_round_and_the_champion_is_crowned():
    first = _built()["bracket"]["conferences"]
    games = []
    # Quarterfinals: the 4 seed upsets the 1 in the East; the favourites hold elsewhere.
    e, w = first["East"], first["West"]
    es, ws = [s["team"] for s in e["seeds"]], [s["team"] for s in w["seeds"]]
    games += [_ko(es[0], es[3], "2026-12-04", 101, 109), _ko(es[1], es[2], "2026-12-05", 115, 100),
              _ko(ws[0], ws[3], "2026-12-04", 120, 99), _ko(ws[1], ws[2], "2026-12-05", 104, 110)]
    out = _built(games)
    e = out["bracket"]["conferences"]["East"]
    q1, q2 = e["quarterfinals"]
    assert q1["done"] and q1["winner"] == es[3] and (q1["home_score"], q1["away_score"]) == (101, 109)
    sf = e["semifinal"]
    # The 2 seed is the better seed left: the semifinal is at its arena.
    assert (sf["home"], sf["away"], sf["home_seed"], sf["away_seed"]) == (es[1], es[3], 2, 4)
    ch = out["chances"]
    assert ch[es[0]]["cup"] == 0 and ch[es[0]]["semis"] == 0, "knocked out in every simulation"
    assert ch[es[3]]["semis"] == 1.0
    # Semifinals, then the final.
    wsf = out["bracket"]["conferences"]["West"]["semifinal"]
    games += [_ko(sf["home"], sf["away"], "2026-12-08", 98, 102), _ko(wsf["home"], wsf["away"], "2026-12-09", 111, 100)]
    out = _built(games)
    fin = out["bracket"]["final"]
    assert (fin["home"], fin["away"]) == (es[3], wsf["home"]), "East v West"
    games += [_ko(wsf["home"], es[3], "2026-12-11", 99, 104)]      # the scoreboard's own home side
    out = _built(games, today="2026-12-12")
    fin = out["bracket"]["final"]
    assert fin["done"] and fin["winner"] == es[3] and out["bracket"]["champion"] == es[3]
    assert (fin["home"], fin["home_score"], fin["away_score"]) == (es[3], 104, 99), "scores follow the bracket's sides"
    assert out["chances"][es[3]]["cup"] == 1.0 and out["bracket_lines"] == {}


def test_a_group_rematch_is_not_answered_by_the_group_game():
    out = _built()
    c = out["bracket"]["conferences"]["East"]
    q1 = c["quarterfinals"][0]
    # The group game between the same two clubs, already played, is no quarterfinal.
    assert not q1["done"] and q1["winner"] is None
    ko = nbacup.knockout_games([_ko(q1["home"], q1["away"], "2026-11-14", 100, 90)])
    assert ko == {}, "only the knockout nights are read"


def test_our_line_is_on_each_game_still_to_play_and_paid():
    out = _built()
    lines = out["bracket_lines"]
    assert sorted(lines) == ["East-qf1", "East-qf2", "West-qf1", "West-qf2"], lines
    q1 = out["bracket"]["conferences"]["East"]["quarterfinals"][0]
    r = C._ratings()
    mu = r[q1["home"]] - r[q1["away"]] + HOME
    want = nbacup._phi(mu / (nbacup.LOGISTIC_TO_NORMAL * SCALE))
    assert abs(lines["East-qf1"]["p_home"] - round(want, 3)) < 1e-9 and lines["East-qf1"]["margin"] == round(mu, 1)
    assert gate.PAID_KEYS_BY_FILE["nba_cup.json"] == ("chances", "remaining", "swing", "bracket_lines")
    pub = gate.redact(out, "nba_cup.json")
    assert not pub["bracket_lines"] and pub["bracket"] == out["bracket"]
    assert '"p_home"' not in json.dumps(pub)


def test_the_build_asks_only_for_nights_that_have_come_and_runs_past_the_final():
    from engine.sources import espnhoops
    asked = []
    real = espnhoops.load_day
    espnhoops.load_day = lambda date, ttl=None, league="wnba": asked.append((date, league)) or []
    try:
        nbacup.load_knockouts(dt.date(2026, 12, 8))
    finally:
        espnhoops.load_day = real
    assert asked == [("2026-12-04", "nba"), ("2026-12-05", "nba"), ("2026-12-08", "nba")], asked
    src = (ROOT / "engine" / "nbacup.py").read_text(encoding="utf-8")
    assert "games = load_window(day) + load_knockouts(day)" in src
    assert nbacup.AFTER_FINAL_DAYS == 2 and "hi = _dt.date.fromisoformat(KNOCKOUTS[\"final\"]) + _dt.timedelta(days=AFTER_FINAL_DAYS)" in src


# --- on the page ---------------------------------------------------------------------
def _render(payload):
    import subprocess
    race = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
    js = f"""
    const state = {{ sport: "nba", view: "race" }};
    const escapeHtml = (s) => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    const teamMarkIn = (sp, t) => `<i data-mark="${{t}}"></i>`;
    const teamNameIn = (sp, t) => t;
    const plural = (n, w) => `${{n}} ${{w}}${{n === 1 ? "" : "s"}}`;
    const formatGameDate = (s) => s;
    const memberLockHTML = (t, b) => `<div class="card member-lock"><b>${{t}}</b><p>${{b}}</p></div>`;
    {race}
    console.log(JSON.stringify(cupHTML({json.dumps(payload)})));
    """
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_the_bracket_with_our_line_for_a_member_only():
    during = _built(through="2026-11-07", today="2026-11-08")
    html = _render(during)
    assert "If group play ended today" in html and html.index("The wild card race") < html.index("If group play ended today")
    assert "· our line " in html and "Winner of 1 v 4" in html and "East champion" in html and "in Indianapolis" in html
    free = _render(gate.redact(during, "nba_cup.json"))
    assert "If group play ended today" in free and "· our line " not in free and "member-lock" in free
    assert "our line on every knockout game" in free
    after = _built()
    html = _render(after)
    assert html.index("The knockout rounds") < html.index("The groups"), "once group play is over the bracket leads"


def test_a_crowned_champion_tops_the_bracket():
    first = _built()["bracket"]["conferences"]
    es = [s["team"] for s in first["East"]["seeds"]]
    ws = [s["team"] for s in first["West"]["seeds"]]
    games = [_ko(es[0], es[3], "2026-12-04", 110, 100), _ko(es[1], es[2], "2026-12-05", 110, 100),
             _ko(ws[0], ws[3], "2026-12-04", 110, 100), _ko(ws[1], ws[2], "2026-12-05", 110, 100),
             _ko(es[0], es[1], "2026-12-08", 110, 100), _ko(ws[0], ws[1], "2026-12-09", 110, 100),
             _ko(es[0], ws[0], "2026-12-11", 120, 118)]
    out = _built(games, today="2026-12-12")
    names = out["names"]
    html = _render(gate.redact(out, "nba_cup.json"))
    assert f"{names.get(es[0], es[0])} win the NBA Cup" in html and "rc-won" in html and "final score" in html


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
