"""A matchup read counts each factor once, never calls a featured player
"avoid", and says when a tough matchup is still the go-to scorer's
(engine/readlogic, every league, 2026-11-14).

Ethan, 2026-11-14: "we're kind of judging too many things off too many
factors. Like, for example, this Duke versus Miami game, Duke's running
back has 17 touchdowns, and yet we're marking him as a bad matchup. But I
feel like he's probably their go-to guy to score. He has four catching
touchdowns and like 13 rushing touchdowns. And yes, Miami's defense is
ranked 5th in rushing, but that doesn't mean that he won't have a single
opportunity to score, because the total's high in that game ... We need to
be more logical ... audit all of that for every sport".

What was wrong, league by league: every read counted its reasons a point
each, so one strong defence counted two or three times (a back's defence
by its rushing yards and again by the touchdowns it allows backs; a
basketball defence once a stat; a hockey defence by its shots and again by
its chances; a starter by his slugging allowed and again by his expected
ERA), nothing a player did himself could stop "avoid", and the college
read was never handed the lines.

    python3 tests/test_a_read_counts_each_factor_once.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import readlogic as RL                    # noqa: E402


def test_one_vote_a_family():
    fam = {"a": RL.DEFENSE, "b": RL.DEFENSE, "c": RL.POINTS}
    assert RL.score([], ["a", "b"], fam) == -1, "two numbers about one defence are one reason"
    assert RL.score(["c"], ["a", "b"], fam) == 0, "the points the lines expect offset it"
    assert RL.score(["a"], ["b"], fam) == 0, "a family split both ways votes nothing"
    assert RL.score(["x"], ["y", "z"]) == -1, "a reason with no family votes alone, as before"


def test_a_featured_player_is_never_avoid():
    assert RL.ladder(-1) == "tough" and RL.ladder(-2) == "avoid"
    assert RL.ladder(-2, featured=True) == "tough"
    assert RL.ladder(-5, featured=True) == "tough"
    assert RL.ladder(2, breakout_ok=True) == "breakout" and RL.ladder(2) == "good"
    assert RL.ladder(1, good_at=2) == "neutral", "the other leagues keep their own bar"


def test_the_bar_is_the_same_both_ways_and_a_featured_player_needs_one_more():
    """Ethan, 2026-11-14, two won parlays on Nate Sheppard (a touchdown and
    63 rushing yards by the second quarter at Miami): "based off our game
    reports, one of these players was unfavorable which was wrong"."""
    assert RL.ladder(-1, featured=True) == "neutral", "one family against a workhorse: a stingy defense"
    two = dict(good_at=2, breakout_at=3)
    assert RL.ladder(2, **two) == "good" and RL.ladder(-1, **two) == "neutral", "one reason is not a lean either way"
    assert RL.ladder(-2, **two) == "tough" and RL.ladder(-3, **two) == "avoid"
    assert RL.ladder(-2, featured=True, **two) == "neutral" and RL.ladder(-3, featured=True, **two) == "tough"
    assert RL.ladder(-9, featured=True, **two) == "tough", "never avoid"


def _back(**kw):
    from engine import gamescan as G
    usage = {"carry_share": 0.62, "carries_pg": 19.0, "games": 9, "targets_pg": 1.5, "rush_yds_pg": 101.0}
    ratings = {"MIA": {"def": {"rushing": {"rank": 5}, "stuff": {"rank": 60}}},
               "DUKE": {"off": {"rushing": {"rank": 32}, "line": {"rank": 69}}}}
    base = dict(usage=usage, ratings=ratings, room={}, scheme={}, split={}, tackling={}, line_out=[],
                mates_out=[], n_teams=134)
    base.update(kw)
    return G.player_read("Duke Back", "DUKE", "MIA", "RB", **base)


def test_dukes_back_at_miami_reads_neutral_with_the_defense_said():
    """The read the report printed UNFAVORABLE on 14 November: 62% of the
    carries, one reason against him (Miami's run defense ranked 5th). Said,
    and it no longer makes a workhorse unfavorable on its own."""
    x = _back(points=21.0, line_words="+13.5 on the road, total 55.5")
    assert x["read"] == "neutral", x
    assert x["con"] == ["MIA's run defense ranks 5th"], x["con"]
    committee = _back(points=21.0, usage={"carry_share": 0.40, "carries_pg": 12.0, "games": 9})
    assert committee["read"] == "tough", "a back without the volume still reads the defense"
    low = _back(points=17.0)
    assert low["read"] == "tough", "two families against the workhorse: the defense and the points"
    # The college read hears the lines now (gamescan.implied_points_row).
    from engine import gamescan as G
    pts, words = G.implied_points_row({"home": "MIA", "away": "DUKE", "spread": -13.5, "total": 55.5})
    assert pts == {"MIA": 34.5, "DUKE": 21.0} and words["DUKE"] == "+13.5 on the road, total 55.5"
    assert G.implied_points_row({"home": "MIA", "away": "DUKE", "spread": None, "total": 55.5}) == ({}, {})
    # A stingy front takes yards a carry, not the carries: a read that rests
    # on the defence alone leans his yards and leaves his carries be.
    assert "rush_yds" in x["lean"] and "rush_att" not in x["lean"], x["lean"]
    rain = _back(points=17.0)
    assert "rush_att" in rain["lean"], "the points the lines expect do move a back's carries"


def test_the_go_to_scorer_says_both():
    reads = {"DUKE@MIA": {"players": [
        {"player": "Duke Back", "team": "DUKE", "pos": "RB", "read": "tough", "label": "Tough matchup",
         "td": {"model_prob": 0.48, "implied_total": 21.0}},
        {"player": "Duke Receiver", "team": "DUKE", "pos": "WR", "read": "good", "label": "Good matchup",
         "td": {"model_prob": 0.22}},
        {"player": "Miami Receiver", "team": "MIA", "pos": "WR", "read": "neutral", "label": "Neutral",
         "td": {"model_prob": 0.30}},
        {"player": "Duke QB", "team": "DUKE", "pos": "QB", "read": "tough", "td": {"model_prob": 0.9}}]}}
    assert RL.mark_scorers(reads) == 1
    rows = {x["player"]: x for x in reads["DUKE@MIA"]["players"]}
    back = rows["Duke Back"]
    assert back["scoring"]["go_to"] and back["read"] == "tough", "the yards read stands"
    assert back["label"] == "Tough for yards — still the go-to scorer"
    assert "scoring" not in rows["Duke Receiver"], "one go-to scorer a team"
    assert "scoring" not in rows["Miami Receiver"], "30% is under the go-to bar"
    assert "scoring" not in rows["Duke QB"], "a quarterback's passing touchdowns are not his to score"
    said = RL.scoring_words(back, team_words="Duke")
    assert said == "Duke's likeliest scorer by our touchdown numbers (48%), with Duke expected to score about 21"


class _Ctx:
    def __init__(self, reads, form=None):
        from engine.gamereport import Ctx  # noqa: F401  (the real class is heavy; this is its shape)
        self.reads, self.form, self.teams, self.sport, self.season = reads, form or {}, ("DUKE", "MIA"), "cfb", 2026
        self.scan, self.result, self.g = {}, {}, {}

    def name(self, t):
        return {"DUKE": "Duke", "MIA": "Miami"}.get(t, t)


def test_the_report_names_the_scorer_and_keeps_him_off_the_hard_day_list():
    from engine import gamereport as GR
    back = {"player": "Duke Back", "team": "DUKE", "pos": "RB", "read": "tough", "con": ["MIA's run defense ranks 5th"],
            "scoring": {"go_to": True, "prob": 0.48, "implied": 21.0}, "usage": {"carry_share": 0.62}}
    form = {"Duke Back": {"season": {"games": 9, "s": {"rush_td": 13, "rec_td": 4}}}}
    c = _Ctx([back], form)
    words = GR.scorer_words(c, back)
    assert words == ("17 touchdowns in 9 games this season (13 rushing, 4 receiving); Duke's likeliest scorer "
                     "by our touchdown numbers (48%), with Duke expected to score about 21"), words
    src = (ROOT / "engine" / "gamereport.py").read_text(encoding="utf-8")
    i = src.index("def shine_lines(")
    assert "and not _go_to(r)" in src[i:i + 1500], "the short version's hard-day list skips him"
    j = src.index("def sec_watch(")
    assert "and not _go_to(r)" in src[j:j + 600], "and so does Could struggle"
    assert '"TOUGH FOR YARDS — STILL THE GO-TO SCORER"' in src and "UNFAVORABLE FOR YARDS" not in src
    assert "scorers = scorer_sentence(c)" in src


def test_basketball_counts_its_defence_once_and_keeps_a_starter():
    from engine.nba import scan as S
    assert S.FEATURED_USAGE == 0.25
    src = (ROOT / "engine" / "nba" / "scan.py").read_text(encoding="utf-8")
    assert "said(con, x, RL.DEFENSE)" in src and "score = RL.score(pro, con, fam)" in src
    assert "RL.ladder(score, featured=featured, breakout_ok=role, good_at=2, breakout_at=3)" in src


def test_hockey_and_baseball_count_their_defence_and_their_starter_once():
    from engine.nhl import scan as H
    from engine.mlb import scan as B
    fam = {"shots": RL.DEFENSE, "chances": RL.DEFENSE}
    key, _ = H._label([], ["shots", "chances"], False, fam)
    assert key == "neutral", "the shots and the chances a defence allows are one reason, and one is no lean"
    key, _ = H._label([], ["shots", "chances", "goalie"], False, {**fam, "goalie": RL.GOALIE})
    assert key == "tough", "two families lean a hockey read"
    key, _ = H._label([], ["shots", "chances", "goalie", "rest"], False,
                      {**fam, "goalie": RL.GOALIE, "rest": RL.SCHEDULE}, featured=True)
    assert key == "tough", "a skater who shoots three times a night is never avoid"
    fam = {"slg": RL.PITCHER, "xera": RL.PITCHER, "whiff": RL.PITCHER}
    key, _ = B._label([], ["slg", "xera", "whiff"], False, fam)
    assert key == "neutral", "a starter's slugging allowed and his expected ERA are one reason"


if __name__ == "__main__":
    import inspect
    fails = ran = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                import traceback
                traceback.print_exc(limit=4)
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
