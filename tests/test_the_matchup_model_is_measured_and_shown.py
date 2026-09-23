"""The NFL matchup: what a defence gives up to each position, measured, used and shown.

Ethan, 2026-09-23: top and worst offences and defences, and position
matchups ("a really good offense and tight end might be playing a really bad
corner"), won him bets — the Lions secondary giving up big days, so Bills
receivers for touchdowns. "I want to make sure we are gathering that data
and we are using that data for our most likely and edge bets and we are
also displaying that information under the picks."

What this file holds the work to (engine/defensevs.py, defensefit.py):

  * the ratings are per GAME by position group — yards, catches and
    touchdowns — walk-forward, shrunk toward last season by games played,
    and rank 1 means "gives up the most";
  * the model reads only what was measured to predict, at the measured
    strength: receivers through the defence's pass defence, backs and
    quarterbacks through their own position, and touchdowns to receivers
    and tight ends not at all (they were noise in every held-out season);
  * the yards model and the touchdown model both use it, and fall back to
    the old numbers where there are no ratings;
  * every prop and touchdown row carries a card, and the page draws it
    under the pick, coloured for the pick's own side.
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

from engine import defensefit as F                             # noqa: E402
from engine import defensevs as D                              # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()


def _row(pid, pos, week, opp, **stats):
    return {"player_id": pid, "player_display_name": pid, "position": pos, "week": str(week),
            "season_type": "REG", "opponent_team": opp, **{k: str(v) for k, v in stats.items()}}


def test_ratings_are_per_game_by_position_and_walk_forward():
    rows = [
        # Week 1: DET faces five receivers for 200 yards; NYJ three for 200.
        *[_row(f"a{i}", "WR", 1, "DET", receiving_yards=40, receptions=3) for i in range(5)],
        *[_row(f"b{i}", "WR", 1, "NYJ", receiving_yards=200 / 3, receptions=5) for i in range(3)],
        _row("te", "TE", 1, "DET", receiving_yards=80, receptions=6, receiving_tds=2),
        _row("rb", "RB", 1, "NYJ", rushing_yards=150, rushing_tds=1),
        _row("late", "WR", 2, "DET", receiving_yards=500),                  # after the cut
        {**_row("post", "WR", 1, "DET", receiving_yards=900), "season_type": "POST"},
    ]
    r = D.ratings(rows, upto_week=2, shrink=0)
    assert r["DET"]["wr_rec_yds"]["pg"] == r["NYJ"]["wr_rec_yds"]["pg"] == 200.0, \
        "per GAME: five receivers or three, the defence gave up 200"
    assert r["DET"]["te_td"]["pg"] == 2.0 and r["NYJ"]["rb_rush_yds"]["pg"] == 150.0
    assert r["DET"]["te_rec_yds"]["rank"] == 1 and r["NYJ"]["te_rec_yds"]["rank"] == 2, "1 = gives up the most"
    assert r["DET"]["te_rec_yds"]["raw"] == 2.0 and r["DET"]["te_rec_yds"]["factor"] == 2.0
    shrunk = D.ratings(rows, upto_week=2, shrink=3)
    assert shrunk["DET"]["te_rec_yds"]["factor"] == 1 + (2.0 - 1) * 1 / (1 + 3), "one game against three"
    prior = {"DET": {"te_rec_yds": {"factor": 1.5}}}
    assert D.ratings(rows, upto_week=2, shrink=3, prior=prior)["DET"]["te_rec_yds"]["factor"] == \
        1.5 + (2.0 - 1.5) * 1 / 4, "and it starts from last season, not from average"
    assert D.SHRINK_GAMES == 12.0


def test_the_model_reads_what_was_measured_at_the_measured_strength():
    assert D.model_stat("WR", "rec_yds") == D.model_stat("TE", "receptions") == "qb_pass_yds", \
        "receivers through the pass defence: their own position's number did not predict"
    assert D.model_stat("WR", "anytime_td") is None and D.model_stat("TE", "anytime_td") is None, \
        "touchdowns to receivers were noise in every held-out season"
    assert D.model_stat("RB", "anytime_td") == "rb_td" and D.model_stat("RB", "rush_yds") == "rb_rush_yds"
    assert D.model_stat("QB", "pass_yds") == "qb_pass_yds"
    assert D.stat_for("WR", "rec_yds") == "wr_rec_yds", "what is SHOWN is his own position's"
    assert D.transfer("QB", "pass_yds") == 0.73 and D.transfer("RB", "rush_yds") == 0.72
    assert D.transfer("WR", "anytime_td") == 0.0 and D.transfer("K", "rec_yds") == 0.0
    assert set(D.TRANSFER) == {("pass_yds", "QB"), ("rush_yds", "RB"), ("rec_yds", "RB"), ("receptions", "RB"),
                               ("anytime_td", "RB"), ("rec_yds", "WR"), ("receptions", "WR"), ("rec_yds", "TE"),
                               ("receptions", "TE")}


def _rating(**factors):
    base = {s: {"pg": 10.0, "league": 10.0, "raw": 1.0, "factor": 1.0, "rank": 16, "of": 32, "games": 2}
            for s in D.STATS}
    for s, (f, rank, pg) in factors.items():
        base[s] = {**base[s], "factor": f, "rank": rank, "pg": pg}
    return base


def test_the_effect_its_card_and_its_words():
    rating = _rating(wr_rec_yds=(1.16, 1, 218.5), qb_pass_yds=(1.09, 2, 329.0), wr_td=(1.0, 14, 1.0),
                     rb_td=(0.9, 30, 0.4), rb_rush_yds=(0.8, 32, 70.0))
    f, why, card = D.effect("DET", rating, "WR", "rec_yds")
    assert abs(f - (1 + 0.57 * 0.09)) < 1e-9
    assert why.startswith("Soft matchup — DET allow the 2nd-most passing yards (329 a game)")
    assert card["text"] == ("DET allow 218.5 receiving yards to WRs a game, the 1st-most (league 10), over 2 games; "
                            "1.0 TDs to WRs a game (14th-most)"), "the card is his own position's, with TDs beside it"
    assert card["model"] == {"reads": "passing yards", "applied": round(f, 3)}
    f, why, card = D.effect("DET", rating, "WR", "anytime_td")
    assert (f, why) == (1.0, "") and card["model"]["reads"] is None and "leaves it out" in card["model"]["note"]
    assert card["stat"] == "TDs to WRs" and card["also"]["stat"] == "receiving yards to WRs"
    f, why, _card = D.effect("DET", rating, "RB", "rush_yds")
    assert abs(f - (1 + 0.72 * -0.2)) < 1e-9 and why.startswith("Tough matchup — DET allow the 1st-fewest rushing")
    assert abs(D.effect("DET", rating, "RB", "anytime_td")[0] - (1 + 0.45 * -0.1)) < 1e-9
    assert D.effect("DET", _rating(qb_pass_yds=(3.0, 1, 999.0)), "QB", "pass_yds")[0] == 1.25, "clamped"
    assert D.effect("DET", {}, "WR", "rec_yds") == (1.0, "", None)
    # Passing touchdowns: measured 2026-09-23, nothing predicted them, so
    # the card shows the defence and the number is left alone.
    qb = _rating(qb_pass_td=(1.3, 1, 2.4), qb_pass_yds=(1.1, 3, 260.0))
    f, why, card = D.effect("DET", qb, "QB", "pass_td")
    assert (f, why) == (1.0, "") and card["stat"] == "passing TDs" and "leaves it out" in card["model"]["note"]
    assert card["also"]["stat"] == "passing yards", "a quarterback's two markets sit under each other"
    assert D.effect("DET", qb, "QB", "pass_yds")[2]["also"]["stat"] == "passing TDs"
    saved = dict(D.TRANSFER)
    try:
        D.TRANSFER.pop(("rec_yds", "WR"))
        f, why, card = D.effect("DET", rating, "WR", "rec_yds")
        assert (f, why, card["model"]["reads"]) == (1.0, "", None), \
            "a rating with no measured strength is shown, not applied, and says so"
    finally:
        D.TRANSFER.clear()
        D.TRANSFER.update(saved)


def test_the_slate_s_profiles_carry_the_ratings_and_keep_their_old_meanings():
    from engine.sources.nflverse import build_defense_profiles
    rows = [_row("r1", "RB", 1, "DET", rushing_yards=40), _row("r2", "RB", 1, "NYJ", rushing_yards=160),
            _row("q1", "QB", 1, "DET", passing_yards=300), _row("q2", "QB", 1, "NYJ", passing_yards=200)]
    p = build_defense_profiles(rows, 2)
    assert p["DET"].ratings["rb_rush_yds"]["pg"] == 40.0 and p["DET"].rush_rank == 1, \
        "rush_rank still means 1 = toughest"
    assert p["NYJ"].rush_rank == 2 and p["DET"].pass_rank == 2
    assert p["DET"].vs_rb_rush == p["DET"].ratings["rb_rush_yds"]["factor"]
    prior = build_defense_profiles(rows, 2, prior_rows=rows)
    assert prior["DET"].vs_rb_rush != p["DET"].vs_rb_rush, "last season is where it starts"
    src = (ROOT / "engine" / "sources" / "nflverse.py").read_text()
    assert "last_season = load_weekly_stats(season - 1)" in src and \
        "defenses = build_defense_profiles(stats, upto_week, last_season)" in src, "and the slate hands it over"


def test_both_models_use_it_and_fall_back_without_it():
    import inspect
    from engine.matchup import evaluate_matchup
    from engine.models import DefenseProfile, Game, Prop, Team, Weather
    from engine import touchdowns as T

    def req(cls, given):
        sig = inspect.signature(cls)
        return {**{k: None for k in sig.parameters if k not in given and sig.parameters[k].default is inspect._empty},
                **given}
    rating = _rating(qb_pass_yds=(1.2, 1, 300.0), rb_td=(1.2, 1, 1.5))
    rated = DefenseProfile(team="DET", ratings=rating)
    bare = DefenseProfile(team="DET", vs_wr1=1.2)
    prop = Prop(**req(Prop, dict(player="A", team="NO", opponent="DET", position="WR", market="rec_yds",
                                 logs=[], lines=[], usage_role="wr1")))
    game = Game(**req(Game, dict(home="DET", away="NO", weather=Weather())))
    eff = evaluate_matchup(prop, rated, game, measured_context=True)
    assert abs(eff.multiplier - (1 + 0.57 * 0.2)) < 1e-9 and eff.card and eff.card["opponent"] == "DET"
    old = evaluate_matchup(prop, bare, game, measured_context=True)
    assert abs(old.multiplier - (1 + 0.24 * 0.2)) < 1e-9 and old.card is None, "no ratings: the old path"
    assert T.defense_td_multiplier(Team(abbr="DET", name="DET", defense=rated), "WR") == (1.0, []), \
        "no more lending a receiver the yards number at full strength"
    assert abs(T.defense_td_multiplier(Team(abbr="DET", name="DET", defense=rated), "RB")[0] - (1 + 0.45 * 0.2)) < 1e-9
    assert T.defense_td_multiplier(Team(abbr="DET", name="DET", defense=bare), "WR")[0] == 1.2


def test_every_row_that_can_carry_the_card_does():
    pipe = (ROOT / "engine" / "pipeline.py").read_text()
    assert '"matchup_card": getattr(getattr(proj, "matchup", None), "card", None),' in pipe
    likely = (ROOT / "engine" / "likely.py").read_text()
    assert likely.count('"matchup_card": row.get("matchup_card"),') == 2, "props and touchdowns on Most Likely"
    td = (ROOT / "engine" / "touchdowns.py").read_text()
    assert '"matchup_card": info.get("matchup_card"),' in td and "pick.matchup_card = info.get(\"matchup_card\")" in td
    ls = (ROOT / "engine" / "longshots.py").read_text()
    assert '"matchup_card": self.matchup_card,' in ls


def test_the_measurement_recovers_a_known_transfer():
    pts = [(10.0, d, 10.0 * (1 + 0.5 * d)) for d in (-0.2, -0.1, 0.1, 0.2) for _ in range(20)]
    assert F.fit(pts)["b"] == 0.5 and F.gain(pts, 0.5) == 1.0 and F.gain(pts, 0.0) == 0.0
    assert F.fit(pts[:10])["b"] == 0.0, "too few to say"
    assert (ROOT / "defensefit.py").exists() and "def _legacy(" in (ROOT / "engine" / "defensefit.py").read_text()


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    esc = APP[APP.index("function escapeHtml("):]
    esc = esc[:esc.index("\n}\n") + 2]
    fn = APP[APP.index("const MU_EDGE"):APP.index("function pickInjuryNote(")]
    prog = esc + fn + f"\nconsole.log(JSON.stringify((() => {{ {js} }})()));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(prog)
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_page_draws_it_under_the_pick_coloured_for_its_side():
    card = {"opponent": "DET", "stat": "receiving yards to WRs", "per_game": 218.5, "league": 146.4, "rank": 1,
            "of": 32, "games": 2, "also": {"stat": "TDs to WRs", "per_game": 1.0, "rank": 14, "of": 32},
            "model": {"reads": "passing yards", "applied": 1.05}}
    got = _node(f"""const c = {json.dumps(card)};
      return [matchupCardHTML({{ side: "OVER", matchup_card: c }}), matchupCardHTML({{ side: "UNDER", matchup_card: c }}),
              matchupCardHTML({{ side: "YES", matchup_card: {{ ...c, model: {{ reads: null, applied: 1 }} }} }}),
              matchupCardHTML({{ side: "OVER" }})];""")
    if got is None:
        print("  SKIP node not installed")
        return
    over, under, td, none = got
    assert "Matchup vs DET" in over and "this season, 2 games" in over
    assert '<b>218.5</b> receiving yards to WRs a game <span class="mu-avg">(avg 146.4)</span>' in over
    assert 'class="mu-rank good">1st-most of 32' in over and "<b>1.0</b> TDs to WRs a game" in over
    assert 'class="mu-rank">14th-most of 32' in over, "the middle of the league is not coloured"
    assert 'class="mu-rank bad">1st-most of 32' in under, "a soft defence is bad news for an under"
    assert "Model: their passing yards allowed moves this projection +5%" in over
    assert "The model leaves this one out" in td and none == ""
    for where in ("${matchupCardHTML(r)}${reasons ?", "${matchupCardHTML(r)}\n    ${why ?",
                  'const mu = qbCardHTML(r.qb_card) + mateCardHTML(r.mate_card) + matchupCardHTML({ ...r, side: r.side || "YES" });',
                  '${matchupCardHTML({ ...r, side: r.side || "YES" })}', "${r.matchup_card ? `<div class=\"section-title minor\">Matchup"):
        assert where in APP, where
    assert ".mu-rank.good { color: var(--good);" in CSS and ".mu-rank.bad { color: var(--bad);" in CSS


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
