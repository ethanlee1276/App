"""The NCAA tournament race: college basketball's NBA Cup page (engine/ncaarace).

Ethan, 2026-11-14: "make it like nba cup and shit I want all the features
like this is a complete sport. We want college basketball to feel complete
and done."

Guarded here, on a made-up season of twelve twelve-school conferences, a
three-school one too small for an automatic bid, and small schools below
Division I:

  * the numbers measured in docs/CBB_LAB.md are the ones the code carries;
  * a conference final is read by its round, whatever the event calls
    itself ("Playoffs"), and the finals played on selection Sunday count;
  * the selection: every champion in, the best scores at large, never a
    losing record, the First Four the four lowest of each; the S-curve
    snakes and a First Four pair shares one place;
  * a bracket keeps every result already played, and every round adds up;
  * the season played out adds up (68 in every run, one champion, one
    automatic bid a conference, a crowned champion in every time);
  * the page if the season ended today, and what a reader without a plan
    is served of it;
  * from selection Sunday the page is the bracket off the scoreboard;
  * the season is read off the scoreboard a few days a build, kept small,
    and the race is played out at most every two hours;
  * the college build plays it.

    python3 tests/test_the_ncaa_tournament_race.py
"""
import datetime as dt
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import cbbratings as CR                           # noqa: E402
from engine import gate                                       # noqa: E402
from engine import ncaarace as NR                             # noqa: E402

SEASON = 2026
CONFS = [f"c{k}" for k in range(1, 13)]
TODAY = "2027-01-20"


def _teams():
    """{code: (conference, strength)}: 144 Division I schools, best first,
    and the three of a conference too small to send a bid."""
    out = {}
    i = 0
    for k in range(12):
        for c in CONFS:
            out[f"T{i:03d}"] = (c, 20.0 - i * 0.28)
            i += 1
    for j in range(3):
        out[f"S{j}"] = ("c99", -8.0 - j)
    return out


def season(today=TODAY, seed=3, tourneys=False):
    """A season's compact games (`ncaarace.compact`'s shape): ten games out
    of conference in November and December (two against small schools
    below Division I), a double round robin's first half in conference from
    January into March, and — with ``tourneys`` — each conference's
    tournament final, billed by its round, on selection Sunday. Games from
    ``today`` on carry no score."""
    rng = random.Random(seed)
    teams = _teams()
    codes = [t for t in teams if t.startswith("T")]
    games, gid = [], 0

    def add(date, h, a, neutral=False, notes=""):
        nonlocal gid
        gid += 1
        hc = teams[h][0] if h in teams else ""
        ac = teams[a][0] if a in teams else ""
        sh = teams[h][1] if h in teams else CR.NON_DI
        sa = teams[a][1] if a in teams else CR.NON_DI
        m = sh - sa + (0 if neutral else CR.HCA) + rng.gauss(0, 10.0)
        m = round(m) or 1
        done = date < today
        games.append({"id": f"g{gid}", "date": date, "home": h, "away": a, "hc": hc, "ac": ac,
                      "home_score": float(70 + max(m, 0)) if done else None,
                      "away_score": float(70 + max(-m, 0)) if done else None,
                      "neutral": neutral, "st": 2, "notes": notes, "hseed": None, "aseed": None})
    start = dt.date(SEASON, 11, 10)
    for r in range(10):
        day = (start + dt.timedelta(days=5 * r)).isoformat()
        order = codes[:]
        rng.shuffle(order)
        for k in range(0, len(order), 2):
            a, b = order[k], order[k + 1]
            if r < 2 and k % 4 == 0:
                add(day, a, f"espn:{9000 + k}")
                add(day, b, f"espn:{9100 + k}")
            else:
                add(day, a, b, neutral=(r == 5))
    for j, s in enumerate(("S0", "S1", "S2")):
        add((start + dt.timedelta(days=2 + j)).isoformat(), s, ("S1", "S2", "S0")[j])
        add((start + dt.timedelta(days=9 + j)).isoformat(), s, codes[-1 - j])
    jan = dt.date(SEASON + 1, 1, 2)
    for c in CONFS:
        mem = [t for t in codes if teams[t][0] == c]
        for r in range(11):
            day = (jan + dt.timedelta(days=5 * r)).isoformat()
            rot = mem[:1] + mem[1:][r:] + mem[1:][:r]
            for k in range(6):
                h, a = rot[k], rot[11 - k]
                add(day, *((h, a) if (r + k) % 2 else (a, h)))
    if tourneys:
        sel = NR.selection_day(SEASON).isoformat()
        for n, c in enumerate(CONFS):
            mem = [t for t in codes if teams[t][0] == c]
            event = "Playoffs" if n == 0 else "Tournament"
            add(sel if n < 2 else "2027-03-13", mem[0], mem[1], neutral=True, notes=f"Conf {c} {event} - Final")
    return games


def ratings(games, today=TODAY):
    return CR.adjusted([g for g in games if g["home_score"] is not None and g["date"] < today])


def built(today=TODAY, sims=300, games=None):
    games = games if games is not None else season(today)
    return NR.build(games, ratings(games, today), today, names={t: f"School {t}" for t in _teams()},
                    sims=sims, seed=5)


# --- the measured numbers ----------------------------------------------------------------
def test_the_numbers_are_the_labs():
    """docs/CBB_LAB.md, "The tournament model": four seasons of fortnight-
    ahead predictions, and the committee's fields of 2024 to 2026."""
    assert (CR.HCA, CR.CAP, CR.NON_DI, CR.PRIOR_DECAY, CR.PRIOR_GAMES, CR.SD) == (2.8, 30.0, -23.5, 1.0, 3.0, 10.75)
    assert (NR.RESUME_POINTS, NR.BUBBLE_RANK) == (1.5, 45)
    assert NR.FIELD == 68 and NR.MIN_CONFERENCE == 6 and NR.AT_LARGE_MIN_PCT == 0.5
    lab = (ROOT / "docs" / "CBB_LAB.md").read_text()
    assert "## The tournament model" in lab
    for line in ("104 of", "0.69", "2.8", "10.75"):
        assert line in lab, line


# --- the conference tournaments --------------------------------------------------------------
def test_a_conference_final_is_read_by_its_round_through_selection_sunday():
    """2026's A-10 and Ivy finals were played on selection Sunday, and the
    America East bills its event "Playoffs": all three were missed by a
    first reading that wanted "Tournament" in the name and stopped the day
    before (docs/CBB_LAB.md)."""
    sel = NR.selection_day(SEASON).isoformat()
    g = {"id": "x", "date": sel, "home": "A", "away": "B", "hc": "1", "ac": "1", "home_score": 60.0,
         "away_score": 70.0, "st": 2, "notes": "America East Playoffs - Final", "neutral": False}
    semi = dict(g, id="y", date="2027-03-12", home="A", away="C", home_score=80.0, away_score=50.0,
                notes="America East Playoffs - Semifinal")
    other = dict(g, id="z", hc="1", ac="2", notes="Players Era Festival - Final", date="2026-11-28")
    nc = dict(g, id="w", notes="NCAA Men's Basketball Championship - East Region - 1st Round", st=3)
    assert NR.conf_tourney(g) and NR.conf_tourney(semi)
    assert not NR.conf_tourney(other), "two conferences: an early-season event, not a conference's"
    assert not NR.conf_tourney(nc)
    played, _left = NR.split([g, semi, other], SEASON, sel)
    assert {x["id"] for x in played} == {"x", "y", "z"}, "selection Sunday's finals are in"
    st = NR.conf_state(played)
    assert st["1"]["champion"] == "B" and st["1"]["out"] == {"A", "C"}


def test_the_games_left_leave_out_the_tournaments_the_race_plays_itself():
    games = season("2027-02-10", tourneys=True)
    played, left = NR.split(games, SEASON, "2027-02-10")
    assert left and all(g["date"] >= "2027-02-10" for g in left)
    finals = [g for g in games if NR.conf_tourney(g)]
    assert len(finals) == 12 and not any(NR.conf_tourney(g) for g in left), \
        "the stand-in plays the conference tournaments"
    # a game whose day has gone by with no score was put off: not a game left
    gone = dict(left[0], date="2027-02-08")
    assert not NR.split([gone], SEASON, "2027-02-10")[1]


# --- the selection --------------------------------------------------------------------------
def test_the_selection_takes_every_champion_and_the_best_scores_at_large():
    teams = [f"t{i:03d}" for i in range(120)]
    score = {t: 100.0 - i for i, t in enumerate(teams)}
    recs = {t: {"w": 20, "l": 10} for t in teams}
    recs["t005"] = {"w": 14, "l": 16}                       # a losing record: never at large
    auto = {f"c{k}": teams[60 + k] for k in range(30)}       # thirty champions, all from far down
    picked = NR.select(auto, score, recs)
    assert len(picked["order"]) == 68 and len(set(picked["order"])) == 68
    assert set(auto.values()) <= set(picked["order"])
    assert len(picked["at_large"]) == 38 and "t005" not in picked["at_large"]
    assert picked["at_large"] == [t for t in teams if t not in auto.values() and t != "t005"][:38]
    assert picked["out"] == [t for t in teams if t not in auto.values() and t != "t005"][38:46]
    ff = {t for p in picked["pairs"] for t in p}
    assert len(picked["pairs"]) == 4 and len(ff) == 8
    assert ff >= set(sorted(picked["at_large"], key=lambda t: score[t])[:4])
    assert ff >= set(sorted(auto.values(), key=lambda t: score[t])[:4])


def test_the_s_curve_snakes_and_a_first_four_pair_shares_a_place():
    order = [f"t{i:02d}" for i in range(68)]
    pairs = [("t60", "t67"), ("t61", "t66"), ("t44", "t47"), ("t45", "t46")]
    regions, seeds = NR.s_curve(order, pairs)
    assert [seeds[t] for t in order[:8]] == [(1, 0), (1, 1), (1, 2), (1, 3), (2, 3), (2, 2), (2, 1), (2, 0)]
    for reg in regions:
        assert sorted(reg) == list(range(1, 17))
    assert len(seeds) == 68
    for a, b in pairs:
        assert seeds[a] == seeds[b]
        line, r = seeds[a]
        assert regions[r][line] == (a, b)


# --- the bracket ------------------------------------------------------------------------------
def _regions(n=68):
    order = [f"t{i:02d}" for i in range(n)]
    return NR.s_curve(order, [("t60", "t67"), ("t61", "t66"), ("t44", "t47"), ("t45", "t46")])


def test_a_bracket_keeps_every_result_played_and_every_round_adds_up():
    regions, _seeds = _regions()
    rng = random.Random(1)
    tally = {r: {} for r in ("r64", "r32", "s16", "e8", "f4", "final", "title")}

    class T(dict):
        def __missing__(self, k):
            return 0
    tally = {r: T() for r in tally}
    # every First Four game to the worse team, every 1 seed out in the first round
    results = {frozenset(p): p[1] for p in (("t60", "t67"), ("t61", "t66"), ("t44", "t47"), ("t45", "t46"))}
    ones = [reg[1] for reg in regions]
    for reg in regions:
        results[frozenset((reg[1], reg[16]))] = reg[16]
    for _ in range(200):
        champ = NR.play_bracket(regions, NR.SEMIS, lambda a, b: 0.5, rng, results, tally)
        assert champ not in ones
    for r, n in (("r64", 64), ("r32", 32), ("s16", 16), ("e8", 8), ("f4", 4), ("final", 2), ("title", 1)):
        assert sum(tally[r].values()) == 200 * n, r
    assert all(tally["r32"][t] == 0 for t in ones)
    assert tally["r64"]["t67"] == 200 and tally["r64"]["t60"] == 0


def test_the_season_played_out_adds_up():
    games = season()
    played, left = NR.split(games, SEASON, TODAY)
    sim = NR.simulate(played, left, ratings(games), sims=200, seed=2)
    n = sim["sims"]
    assert sum(sim["tally"]["field"]) == 68 * n
    assert sum(sim["tally"]["title"]) == n and sum(sim["tally"]["final"]) == 2 * n
    assert sum(sim["auto"]) == 12 * n, "one automatic bid a conference; the three-school one sends none"
    i = sim["teams"].index("T000")
    assert sim["tally"]["field"][i] == n and sim["top4"][i] == n


def test_a_crowned_champion_is_in_every_time():
    """The Monday after selection Sunday: every final played (two of them
    on the Sunday), every champion in every run whatever its record."""
    games = season("2027-03-15", tourneys=True)
    played, left = NR.split(games, SEASON, "2027-03-15")
    crowned = NR.conf_state(played)
    champs = {c: s["champion"] for c, s in crowned.items() if s["champion"]}
    assert len(champs) == 12
    sim = NR.simulate(played, left, ratings(games, "2027-03-15"), sims=100, seed=4)
    for c, t in champs.items():
        i = sim["teams"].index(t)
        assert sim["auto"][i] == 100 and sim["tally"]["field"][i] == 100, (c, t)


# --- the page ---------------------------------------------------------------------------------
def test_the_page_if_the_season_ended_today():
    out = built()
    t = out["today"]
    assert t["set"] is False and len(t["field"]) == 68
    assert sum(1 for r in t["field"] if r["bid"] == "auto") == 12 == out["format"]["auto"]
    assert out["format"]["at_large"] == 56
    lines = {}
    for r in t["field"]:
        lines.setdefault((r["seed"], r["region"]), []).append(r["team"])
    assert len(lines) == 64 and sum(1 for v in lines.values() if len(v) == 2) == 4
    inside = {r["team"] for r in t["field"]}
    assert len(t["last_four_in"]) == 4 and {r["team"] for r in t["last_four_in"]} <= inside
    assert len(t["first_four_out"]) == 4 and not ({r["team"] for r in t["first_four_out"]} & inside)
    assert len(t["region_tops"]) == 4 and all(t["region_tops"])
    assert "c99" not in json.dumps(t["auto_bids"]) and len(out["conferences"]) == 13
    small = next(v for v in out["conferences"].values() if v["teams"][0]["team"].startswith("S"))
    assert small["auto_bid"] is False
    assert set(out["chances"]) <= {r["team"] for r in out["teams"]}
    top = out["teams"][0]["team"]
    c = out["chances"][top]
    for k in ("field", "r64", "r32", "s16", "e8", "f4", "final", "title", "auto", "top4", "seed", "proj", "conf_proj"):
        assert k in c, k
    assert 0 < len(out["remaining"][top]) <= NR.NEXT_GAMES
    assert abs(sum(x["title"] for x in out["chances"].values()) - 1.0) < 0.02
    for g in out["swing"]:
        assert g["moves"] and 0 < g["p_home"] < 1
    assert out["bracket"] is None and out["bracket_lines"] == {}
    assert out["names"]["T000"] == "School T000"


def test_a_reader_without_a_plan_gets_the_facts_only():
    out = built()
    pub = gate.redact(out, "ncaa_race.json")
    for k in ("chances", "remaining", "swing", "bracket_lines", "bids"):
        assert not pub.get(k), k
    assert pub["today"]["field"] == out["today"]["field"] and pub["conferences"] == out["conferences"]
    assert "ncaa_race.json" in gate.MIXED_FILES
    assert gate.PAID_KEYS_BY_FILE["ncaa_race.json"] == ("chances", "remaining", "swing", "bracket_lines", "bids")


def _tournament(done_through="r64"):
    """The season to selection Sunday with each conference's final, then
    the bracket the stand-in names, billed as ESPN bills it; the First Four
    and (with ``done_through``) the first round played, the better seed
    winning."""
    games = season("2027-03-15", tourneys=True)
    out = built("2027-03-15", sims=50, games=games)
    seeds = {r["team"]: (r["seed"], r["region"]) for r in out["today"]["field"]}
    regions, _ = NR.s_curve([r["team"] for r in out["today"]["field"]],
                            [tuple(p) for p in out["today"]["first_four"]])
    nights = NR.nights(SEASON)
    gid = 0
    added = []

    def bill(day, a, b, rnd, region, done):
        nonlocal gid
        gid += 1
        added.append({"id": f"n{gid}", "date": day, "home": a, "away": b, "hc": "", "ac": "",
                      "home_score": 80.0 if done else None, "away_score": 60.0 if done else None,
                      "neutral": True, "st": 3, "hseed": seeds[a][0], "aseed": seeds[b][0],
                      "notes": f"NCAA Men's Basketball Championship - {region} Region - {rnd}"})
    for r, reg in enumerate(regions):
        name = NR.REGIONS[r]
        line = {}
        for s, x in reg.items():
            if isinstance(x, tuple):
                bill(nights["first_four"][0], x[0], x[1], "First Four", name, True)
                line[s] = x[0]
            else:
                line[s] = x
        for a, b in NR.FIRST_ROUND:
            bill(nights["r64"][0], line[a], line[b], "1st Round", name, done_through == "r64")
    return games + added


def test_from_selection_sunday_the_page_is_the_bracket():
    games = _tournament()
    day = NR.nights(SEASON)["r32"][0]
    out = NR.build(games, ratings(games, day), day, sims=200, seed=1)
    b = out["bracket"]
    assert b and b["set"] and out["today"]["set"]
    assert [len(r) for r in b["regions"][0]["rounds"]] == [8, 4, 2, 1]
    assert len(b["first_four"]) == 4 and all(s["w"] == s["a"] or s["w"] == s["b"] for s in b["first_four"])
    first = b["regions"][0]["rounds"][0]
    assert all(s["w"] for s in first), "the first round is played"
    second = b["regions"][0]["rounds"][1]
    assert all(s["a"] and s["b"] and not s["w"] for s in second), "the winners meet, still to play"
    assert b["semis_from"] == "ours" and len(b["final_four"]) == 2 and b["champion"] == ""
    assert len(b["seeds"]) == 68
    ch = out["chances"]
    assert abs(sum(c["title"] for c in ch.values()) - 1.0) < 1e-6
    losers = {s["a"] if s["w"] == s["b"] else s["b"] for reg in b["regions"] for s in reg["rounds"][0]}
    assert all(ch[t]["r32"] == 0 for t in losers if t in ch)
    assert out["swing"] == [] and out["remaining"] == {}


def test_a_line_on_each_tournament_game_still_to_play():
    games = _tournament(done_through="")
    day = NR.nights(SEASON)["r64"][0]
    out = NR.build(games, ratings(games, day), day, sims=100, seed=1)
    lines = out["bracket_lines"]
    assert len(lines) == 32 and all(0 < x["p_home"] < 1 and x["home"] for x in lines.values())
    assert gate.redact(out, "ncaa_race.json").get("bracket_lines") in ({}, None)


def test_the_final_four_pairs_off_the_scoreboard_once_it_lists_them():
    games = _tournament()
    seeds = {}
    for g in NR.bracket_games(games):
        seeds.update({g["home"]: (g["home_seed"], g["region"]), g["away"]: (g["away_seed"], g["region"])})
    by_region = {}
    for t, (s, r) in seeds.items():
        if s == 1:
            by_region[r] = t
    f4 = {"id": "f4", "date": NR.nights(SEASON)["f4"][0], "home": by_region["East"], "away": by_region["West"],
          "hc": "", "ac": "", "home_score": None, "away_score": None, "neutral": True, "st": 3,
          "hseed": 1, "aseed": 1, "notes": "NCAA Men's Basketball Championship - Final Four"}
    bg = NR.bracket_games(games + [f4])
    real = NR.real_field(bg)
    pairs, how = NR.real_semis(bg, real, NR.real_regions(real), {})
    assert how == "named" and pairs == ((0, 2), (1, 3))


# --- the box ----------------------------------------------------------------------------------
class _Cache:
    """The scoreboard cache moved to a temporary folder for one test."""

    def __enter__(self):
        from engine.sources import fetch as F
        self.F, self.keep = F, F.CACHE_DIR
        F.CACHE_DIR = Path(tempfile.mkdtemp())
        return F.CACHE_DIR

    def __exit__(self, *a):
        self.F.CACHE_DIR = self.keep


def _scoreboard(asked):
    """A fake scoreboard read: the made-up season's games on that day, in
    `espnhoops.parse_scoreboard`'s shape; every day asked is counted."""
    games = season(TODAY)

    def fetch(date):
        asked.append(date)
        return [{"game_id": g["id"], "home": g["home"], "away": g["away"], "home_conf": g["hc"],
                 "away_conf": g["ac"], "completed": g["home_score"] is not None,
                 "home_score": g["home_score"], "away_score": g["away_score"], "neutral": g["neutral"],
                 "season_type": 2, "notes": g["notes"], "home_rank": None, "away_rank": None}
                for g in games if g["date"] == date]
    return fetch


def test_the_season_is_read_a_few_days_a_build_and_kept_small():
    day = dt.date.fromisoformat(TODAY)
    with _Cache() as cache:
        asked = []
        games, missing = NR.load_season(SEASON, day, _scoreboard(asked), reads=40)
        assert len(asked) == 40 and missing > 0, "a fresh box reads in steps"
        assert max(asked) <= TODAY, "the days to date first"
        while missing:
            games, missing = NR.load_season(SEASON, day, _scoreboard(asked), reads=40)
        first = len(asked)
        games, missing = NR.load_season(SEASON, day, _scoreboard(asked), reads=40)
        again = asked[first:]
        assert again and all(d > TODAY or d >= (day - dt.timedelta(days=3)).isoformat() for d in again), \
            "a settled day is never asked again"
        assert {g["id"] for g in games} >= {g["id"] for g in season(TODAY) if g["date"] < TODAY}
        files = list(cache.glob("cbb_slate_*.json"))
        assert files and sum(f.stat().st_size for f in files) < 2_000_000


def test_the_race_is_published_through_the_gate_and_held_two_hours():
    day = dt.date.fromisoformat(TODAY)
    out = Path(tempfile.mkdtemp()) / "web" / "data" / "ncaa_race.json"
    keep = NR.SIMS
    NR.SIMS = 120
    try:
        with _Cache():
            asked = []
            line = ""
            for _ in range(12):
                line = NR.publish(None, day, out_path=str(out), fetch=_scoreboard(asked))
                if "still reading" not in line:
                    break
            assert line.startswith("NCAA race:") and "seasons" in line, line
            full = json.loads(Path(gate.board_source(out)).read_text())
            pub = json.loads(out.read_text())
            # Both copies written; with the paywall on the public one is
            # `gate.redact`'s (test_a_reader_without_a_plan_gets_the_facts_only).
            assert full["chances"] and pub["today"]["field"]
            assert full["inputs"] and full["generated_at"]
            n = len(asked)
            line = NR.publish(None, day, out_path=str(out), fetch=_scoreboard(asked))
            assert "min ago" in line and len(asked) == n, "held: nothing read, nothing played"
            # Two hours on, with the whole season read, the same games and
            # ratings keep the race as it is (engine/racecache).
            src = Path(gate.board_source(out))

            def two_hours_on():
                held = json.loads(src.read_text())
                held["generated_at"] = (dt.datetime.now() - dt.timedelta(hours=3)).isoformat(timespec="seconds")
                src.write_text(json.dumps(held))
            NR.load_season(SEASON, day, _scoreboard(asked), reads=500)
            two_hours_on()
            line = NR.publish(None, day, out_path=str(out), fetch=_scoreboard(asked))
            assert "seasons" in line, "the days ahead read since: played again"
            two_hours_on()
            line = NR.publish(None, day, out_path=str(out), fetch=_scoreboard(asked))
            assert line == "NCAA race: no score or game has moved since its last build — kept", line
    finally:
        NR.SIMS = keep
    assert NR.publish(None, dt.date(2026, 7, 4), out_path=str(out)) == "NCAA race: out of season, not built"


def test_a_scoreboard_row_is_kept_compact():
    row = NR.compact({"game_id": "401", "home": "DUKE", "away": "espn:2000", "home_conf": "2", "away_conf": "",
                      "completed": True, "home_score": 90.0, "away_score": 50.0, "neutral": False,
                      "season_type": 2, "notes": "Coaches vs Cancer · extra", "home_rank": 3, "away_rank": None,
                      "home_info": {"logo": "x"}, "broadcast": "ESPN"}, "2026-11-14")
    assert row == {"id": "401", "date": "2026-11-14", "home": "DUKE", "away": "espn:2000", "hc": "2", "ac": "",
                   "home_score": 90.0, "away_score": 50.0, "neutral": False, "st": 2,
                   "notes": "Coaches vs Cancer", "hseed": 3, "aseed": None}
    assert NR.compact({"home": "A", "away": "B", "preseason": True}, "2026-10-30") is None


def test_the_college_build_plays_it():
    src = (ROOT / "nba_build.py").read_text()
    block = src[src.index("# THE NCAA TOURNAMENT (engine/ncaarace"):src.index('_clock.mark("pick of the day journal + NBA Cup")')]
    assert 'if args.league == "cbb":' in block and "_ncaa.publish(" in block
    assert "with_name('ncaa_race.json')" in block and "NCAA race skipped" in block
    assert "ncaa_race.json" in gate.__dict__.get("PAID_KEYS_BY_FILE", {})


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
                traceback.print_exc()
                print(f"  FAIL {name}: {exc!r}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
