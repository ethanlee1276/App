"""The NFL playoff race: the seeds if it ended today, the tiebreakers, and the
season played out (engine/nflrace).

Ethan, 2026-11-03, on the 30 October audit's list — "an NFL playoff race:
the same engine (play out the rest of the season with our game model) gives
each team's chance at the playoffs, the seeds if it ended today, and the
Sunday games that swing it" — "do all of them". What these hold:

  * seven a conference: the four division leaders seeded 1-4 by record,
    even below a better wild card, then the three best records left;
  * a tie is broken the league's way as far as the schedule tells it —
    head-to-head, then division record inside a division, then conference
    record — and a wild card takes each division's best club first;
  * the chances add up (fourteen berths, one champion), a game left is
    priced off the Futures page's own win chance, and the swing games are
    next week's, each with the clubs it moves;
  * the standings and the seeds are free, the chances, games left and swing
    games paid; the NFL build writes the file and the page reads it.

Run directly: `python3 tests/test_the_nfl_playoff_race.py`
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import futures as FU                                  # noqa: E402
from engine import gate                                           # noqa: E402
from engine import nflrace as R                                   # noqa: E402

CLUBS = R.league()
TEAMS = [t for t, _c, _d in CLUBS]
DIV = {t: f"{c} {d}" for t, c, d in CLUBS}


def _row(week, home, away, hs=None, as_=None, day=None):
    return {"season": "2026", "game_type": "REG", "week": str(week), "gameday": day or f"2026-09-{week + 6:02d}",
            "home_team": home, "away_team": away, "location": "Home",
            "home_score": "" if hs is None else str(hs), "away_score": "" if as_ is None else str(as_)}


def _season():
    """A season of rows: every club plays a game a week, the lower code at
    home; weeks 1-6 played (the stronger code wins), weeks 7-8 to come."""
    rows = []
    for week in range(1, 9):
        order = TEAMS[week % 32:] + TEAMS[:week % 32]
        for k in range(16):
            h, a = order[k], order[31 - k]
            if week <= 6:
                win_h = (TEAMS.index(h) * 7 + week) % 5 != 0
                rows.append(_row(week, h, a, 24 if win_h else 17, 17 if win_h else 24))
            else:
                rows.append(_row(week, h, a))
    return rows


def _table(results):
    """A table off (home, away, home score, away score) results."""
    n = len(TEAMS)
    tb = R._Table(n, [c for _t, c, _d in CLUBS], [DIV[t] for t in TEAMS], [0.0] * n)
    ix = {t: i for i, t in enumerate(TEAMS)}
    for h, a, hs, as_ in results:
        tb.add(ix[h], ix[a], hs, as_)
    return tb, ix


def test_two_clubs_in_a_division_go_by_head_to_head_then_division_record():
    tb, ix = _table([("BUF", "MIA", 20, 17), ("MIA", "NYJ", 30, 10), ("NE", "BUF", 21, 14)])
    # BUF and MIA both 1-1; BUF beat MIA.
    assert R.order([ix["MIA"], ix["BUF"]], tb, True) == [ix["BUF"], ix["MIA"]]
    tb, ix = _table([("BUF", "KC", 20, 17), ("MIA", "NYJ", 30, 10), ("NE", "BUF", 21, 14), ("LV", "MIA", 27, 3)])
    # Never met: BUF 0-1 in the division, MIA 1-0, both 1-1 overall.
    assert R.order([ix["BUF"], ix["MIA"]], tb, True) == [ix["MIA"], ix["BUF"]]


def test_a_tie_game_is_half_a_win():
    tb, ix = _table([("DAL", "NYG", 20, 20), ("PHI", "WAS", 27, 24), ("WAS", "DAL", 10, 13)])
    assert tb.record(ix["DAL"]) == "1-0-1" and abs(tb.pct(ix["DAL"]) - 0.75) < 1e-9
    assert R.order([ix["DAL"], ix["PHI"]], tb, True) == [ix["PHI"], ix["DAL"]], "1-0 (1.000) is ahead of 1-0-1 (.750)"


def test_division_leaders_take_the_top_four_even_below_a_better_wild_card():
    # PIT 4-0 leads the North over BAL 3-1; BUF 1-1 leads the East and KC
    # 1-1 the West. BAL's .750 is better than both, and it is still the 5.
    results = [("BUF", "NYJ", 20, 10), ("KC", "BUF", 20, 10),
               ("PIT", "CLE", 20, 10), ("PIT", "CIN", 20, 10), ("PIT", "LV", 20, 10), ("PIT", "BAL", 20, 17),
               ("BAL", "KC", 20, 10), ("BAL", "DEN", 20, 10), ("BAL", "LAC", 20, 10)]
    tb, ix = _table(results)
    members = {}
    for t, c, d in CLUBS:
        members.setdefault((c, d), []).append(ix[t])
    seeds, divs, out = R.seed(tb, members)["AFC"]
    names = [TEAMS[i] for i in seeds]
    assert names[0] == "PIT" and "BUF" in names[:4] and "KC" in names[:4], names
    assert names[4] == "BAL", ("BAL, 3-1, is the 5 below 1-1 division leaders", names)
    assert TEAMS[divs["North"][0]] == "PIT" and len(seeds) == 7 and len(out) == 9


def test_a_wild_card_tie_takes_each_divisions_best_club_first():
    # MIA and NYJ (East) and KC (West) all 1-0 outside the leaders; NYJ beat... none.
    tb, ix = _table([("MIA", "NYJ", 24, 21), ("NYJ", "CLE", 30, 3), ("MIA", "CIN", 30, 3), ("KC", "LV", 30, 3)])
    div_rank = {ix["MIA"]: 0, ix["NYJ"]: 1, ix["KC"]: 1}
    got = [TEAMS[i] for i in R.order([ix["NYJ"], ix["KC"], ix["MIA"]], tb, False, div_rank)]
    assert got.index("MIA") < got.index("NYJ"), ("NYJ cannot go before MIA, its division's better club", got)


def test_the_season_played_out_adds_up_and_prices_with_the_futures_page():
    rows = _season()
    ratings = {t: (i % 9) - 4.0 for i, t in enumerate(TEAMS)}
    out = R.build(rows, ratings, "2026-10-15", season=2026, sims=1500, seed_=3)
    assert out["games_played"] == 96 and out["games_left"] == 32 and out["week"] == 7
    ch = out["chances"]
    assert abs(sum(c["playoffs"] for c in ch.values()) - 14) < 0.02
    assert abs(sum(c["title"] for c in ch.values()) - 1) < 0.02
    assert abs(sum(c["division"] for c in ch.values()) - 8) < 0.02
    assert abs(sum(c["bye"] for c in ch.values()) - 2) < 0.02
    team = TEAMS[0]
    g = out["remaining"][team][0]
    opp = g["opp"]
    want = FU.win_prob("nfl", ratings[team], ratings[opp]) if g["home"] else 1 - FU.win_prob("nfl", ratings[opp], ratings[team])
    assert abs(g["p"] - round(want, 3)) < 1e-9, "the Futures page's own win chance"
    for c in ("AFC", "NFC"):
        seeds = out["today"][c]["seeds"]
        assert [s["seed"] for s in seeds] == list(range(1, 8))
        assert all(s["why"].endswith("leader") for s in seeds[:4]) and all(s["why"] == "Wild card" for s in seeds[4:])
        assert len(out["today"][c]["hunt"]) == R.HUNT_SHOWN
    assert len(out["standings"]) == 8 and all(len(v) == 4 for v in out["standings"].values())
    conf = {t: c for t, c, _d in CLUBS}
    for s in out["swing"]:
        assert s["week"] == 7 and s["moves"], s
        for m in s["moves"]:
            assert abs(m["if_home"] - m["if_away"]) >= R.SWING_FLOOR
            assert conf[m["team"]] in (conf[s["home"]], conf[s["away"]]), ("a game moves only its own conferences", s)


def test_the_model_half_is_paid_and_the_facts_are_free():
    out = R.build(_season(), {}, "2026-10-15", season=2026, sims=300, seed_=1)
    assert gate.PAID_KEYS_BY_FILE["nfl_race.json"] == ("chances", "remaining", "swing")
    assert "nfl_race.json" in gate.KNOWN_BOARDS and "nfl_race.json" in gate.MIXED_FILES
    pub = gate.redact(out, "nfl_race.json")
    assert not pub.get("chances") and not pub.get("remaining") and not pub.get("swing")
    assert pub["today"] == out["today"] and pub["standings"] == out["standings"]


def test_the_nfl_build_writes_it_and_the_page_reads_it():
    build = (ROOT / "nfl_build.py").read_text(encoding="utf-8")
    assert "_race.publish(_rdt.date.today(), out_path=str(_RPath(args.out).with_name('nfl_race.json')))" in build
    race = (ROOT / "web" / "js" / "race.js").read_text(encoding="utf-8")
    assert 'nfl: "nfl_race.json"' in race and "function nflHTML(d)" in race
    app = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
    assert "  nfl: [], mlb: [\"race\"]," in app


def test_out_of_season_it_is_not_built():
    rows = [r for r in _season() if r["home_score"]]
    assert R.schedule(rows, 2026)[1] == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn(); print(f"  ok  {name}")
    print(f"\n{sum(1 for n in globals() if n.startswith('test_'))} tests passed.")
