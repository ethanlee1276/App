"""Each game's touchdown pairs are chosen on our research, not on the prices (2026-11-14).

Ethan, 2026-11-14: "make sure we are making the TD parlays based off
reaseerach we do and the breakout canidates and game scripts and all of that
and not just based off the player lines". A football scorer is a leg only
when the research makes a case for him (engine/gameparlays.research: the
matchup — expected points, the defense at his position, red-zone chances
and trips — his usage, the matchup read and the game script), with a
red-zone role; scorers and pairs are ranked on the research first and our
chance second. Hockey's goal-scorer pairs have no read and rank on the
chance as before.

    python3 tests/test_touchdown_pairs_come_from_our_research.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import gameparlays as GP                     # noqa: E402

SCAN = {"n_teams": 32,
        "units": {"WAS": {"def": {"passing": {"rank": 27}, "rushing": {"rank": 22}}},
                  "NYG": {"def": {"passing": {"rank": 12}, "rushing": {"rank": 18}}}},
        "redzone": {"NYG": {"off": 3.1, "off_rel": 0.08, "def": 2.9, "def_rel": 0.02},
                    "WAS": {"off": 3.2, "off_rel": 0.10, "def": 3.3, "def_rel": 0.12}}}


def _game(**kw):
    g = {"home": "NYG", "away": "WAS", "date": "2099-11-12", "kickoff": "20:15", "spread": -2.5, "total": 40.5,
         "scan": SCAN}
    g.update(kw)
    return g


def _read(player, team, pos, read, usage, p, rz, implied=21.5, **kw):
    x = {"player": player, "team": team, "opp": "WAS" if team == "NYG" else "NYG", "pos": pos, "read": read,
         "label": {"breakout": "Breakout candidate", "good": "Good matchup", "neutral": "Neutral",
                   "tough": "Tough matchup", "avoid": "Avoid"}[read],
         "usage": usage, "td": {"model_prob": p, "odds": 150, "implied_total": implied, "rz_chances": rz},
         "pro": [], "con": [], "notes": []}
    x.update(kw)
    return x


def _td(player, team, pos, p, odds=150):
    return {"player": player, "team": team, "opponent": "WAS" if team == "NYG" else "NYG", "position": pos,
            "market": "anytime_td", "side": "Over", "line": 0.5, "model_prob": p, "odds": odds, "book": "FanDuel",
            "home": "NYG", "away": "WAS", "game_date": "2099-11-12", "kickoff": "2099-11-12T20:15:00-05:00",
            "reasons": []}


SKATTEBO = _read("Cam Skattebo", "NYG", "RB", "good", {"carry_share": 0.62}, 0.45, 3.1)
LIKELY = _read("Isaiah Likely", "NYG", "TE", "breakout", {"tgt_share": 0.20}, 0.30, 1.9)
NABERS = _read("Malik Nabers", "NYG", "WR", "neutral", {"tgt_share": 0.27}, 0.36, 1.8)


def test_the_research_reads_the_matchup_the_usage_the_read_and_the_script():
    g = _game()
    r = GP.research({"team": "NYG", "opponent": "WAS"}, SKATTEBO, g, "nfl")
    assert r["points"] == {"offense": 1, "defense": 1, "red_zone": 2, "trips": 1, "usage": 2, "read": 1,
                           "script": 0}, r["points"]
    assert r["score"] == 8 and r["red_zone"] == 2
    assert r["head"][:2] == ["Good matchup", "WAS’s run defense ranks 22nd of 32"], r["head"]
    # A back on a side favoured by a field goal or more: a leading team runs.
    fav = GP.research({"team": "NYG", "opponent": "WAS"}, SKATTEBO, _game(spread=-6.5), "nfl")
    assert fav["points"]["script"] == 1 and any("favored by 6.5" in x for x in fav["head"]), fav["head"]
    # The same back a seven-point underdog: a trailing team runs less.
    dog = GP.research({"team": "NYG", "opponent": "WAS"}, SKATTEBO, _game(spread=7.5), "nfl")
    assert dog["points"]["script"] == -1
    # A receiver in a shootout by the total.
    shoot = GP.research({"team": "NYG", "opponent": "WAS"}, NABERS, _game(total=51.5), "nfl")
    assert shoot["points"]["script"] == 1 and shoot["points"]["read"] == 0
    assert GP.research({}, LIKELY, g, "nfl")["points"]["read"] == 2, "a breakout candidate is the strongest read"


def test_no_read_or_an_avoid_read_is_no_case_and_a_go_to_scorer_keeps_a_tough_draw():
    g = _game()
    assert GP.research({"team": "NYG"}, None, g, "nfl") is None
    assert GP.research({"team": "NYG"}, dict(SKATTEBO, read="avoid", label="Avoid"), g, "nfl") is None
    tough = dict(SKATTEBO, read="tough", label="Tough matchup")
    assert GP.research({}, tough, g, "nfl")["points"]["read"] == -1
    go_to = dict(tough, label="Tough for yards — still the go-to scorer", scoring={"go_to": True})
    got = GP.research({}, go_to, g, "nfl")
    assert got["points"]["read"] == 0 and "Tough for yards" not in " ".join(got["head"])
    # A quarterback is read against the run defence, his share not counted.
    qb = _read("Jayden Daniels", "WAS", "QB", "good", {"carry_share": 0.25}, 0.33, 1.2, implied=19.0)
    q = GP.research({}, qb, g, "nfl")
    assert q["points"]["usage"] == 0 and q["points"]["defense"] == 0, q["points"]   # NYG's run defense 18th


def _board(reads, scorers, game=None):
    return {"date": "2099-W10", "games": [game or _game()], "td_field": scorers,
            "scan_reads": {"WAS@NYG": {"players": reads}}}


def test_a_likelier_scorer_with_no_case_is_never_a_leg():
    reads = [SKATTEBO, LIKELY, NABERS,
             # Priced at 40% with a red-zone role, but nothing else: 3 of 13.
             _read("Rachaad White", "WAS", "RB", "neutral", {"carry_share": 0.45}, 0.40, 1.2, implied=19.0),
             # The scan says to avoid him.
             _read("Terry McLaurin", "WAS", "WR", "avoid", {"tgt_share": 0.25}, 0.38, 1.6, implied=19.0),
             # No red-zone role, whatever else he has.
             _read("Wan'Dale Robinson", "NYG", "WR", "breakout", {"tgt_share": 0.26}, 0.31, 0.4)]
    scorers = [_td(x["player"], x["team"], x["pos"], x["td"]["model_prob"]) for x in reads]
    scorers.append(_td("Deebo Samuel", "WAS", "WR", 0.42))                    # no read on him at all
    gp = GP.build(_board(reads, scorers), "nfl")
    g = gp["games"][0]
    on = {l["player"] for t in g["scorers"] for l in t["legs"]}
    assert on == {"Cam Skattebo", "Isaiah Likely", "Malik Nabers"}, on
    assert len(g["scorers"]) == 3 and g["scorers_priced"] == 7 and g["scorers_read"] == 3
    assert all(t["research"] == sum(l["research"] for l in t["legs"]) for t in g["scorers"])
    card = GP.card(g["scorers"][0], 1, "scorers", "nfl")
    assert all(l["research_of"] == GP.RESEARCH_MAX and l["research"] >= GP.RESEARCH_MIN for l in card["legs"])


def test_the_research_ranks_the_pairs_before_the_chance():
    # Two strong cases at short chances, two thin ones at long ones.
    a = _read("Cam Skattebo", "NYG", "RB", "breakout", {"carry_share": 0.62}, 0.28, 3.1, implied=24.5)
    b = _read("Isaiah Likely", "NYG", "TE", "breakout", {"tgt_share": 0.25}, 0.27, 1.9, implied=24.5)
    c = _read("Rachaad White", "WAS", "RB", "neutral", {"carry_share": 0.45}, 0.50, 1.2, implied=19.0)
    d = _read("Chris Rodriguez", "WAS", "RB", "neutral", {"carry_share": 0.42}, 0.48, 1.6, implied=19.0)
    reads = [a, b, c, d]
    scorers = [_td(x["player"], x["team"], x["pos"], x["td"]["model_prob"]) for x in reads]
    gp = GP.build(_board(reads, scorers), "nfl")
    pairs = gp["games"][0]["scorers"]
    first = {l["player"] for l in pairs[0]["legs"]}
    assert first == {"Cam Skattebo", "Isaiah Likely"}, (first, [(t["research"], t["joint"]) for t in pairs])
    joints = [t["joint"] for t in pairs]
    assert pairs[0]["research"] == max(t["research"] for t in pairs) and joints[0] < max(joints), \
        "the strongest research, not the likeliest pair, comes first"


def test_fewer_pairs_say_why_in_the_research_words():
    reads = [SKATTEBO, LIKELY]
    scorers = [_td("Cam Skattebo", "NYG", "RB", 0.45), _td("Isaiah Likely", "NYG", "TE", 0.30),
               _td("Deebo Samuel", "WAS", "WR", 0.42)]
    g = GP.build(_board(reads, scorers), "nfl")["games"][0]
    assert len(g["scorers"]) == 1
    note = g["scorers_note"]
    assert note.startswith("1 of 3: 2 of the 3 priced scorer(s)") and "research case" in note, note


def test_hockey_ranks_on_the_chance_as_before():
    rows = [{"player": n, "team": t, "opponent": o, "position": "C", "market": "anytime_goal", "side": "Yes",
             "line": 0.5, "model_prob": p, "odds": 180, "book": "FanDuel", "home": "BOS", "away": "TOR",
             "game_date": "2099-11-12", "kickoff": "2099-11-12T19:00:00-05:00"}
            for n, t, o, p in (("A", "BOS", "TOR", 0.40), ("B", "BOS", "TOR", 0.35), ("C", "TOR", "BOS", 0.30))]
    b = {"date": "2099-11-12", "games": [{"home": "BOS", "away": "TOR", "date": "2099-11-12"}], "td_field": rows}
    g = GP.build(b, "nhl")["games"][0]
    assert len(g["scorers"]) == 3 and all("research" not in l for t in g["scorers"] for l in t["legs"])
    assert "scorers_priced" not in g



def test_the_build_says_why_each_priced_scorer_is_no_leg_and_the_audit_prints_it():
    """College's first night on the rule read 9 pairs on 28 games; what held
    the rest is counted (`research_census`) and the picks audit prints it."""
    from engine import pickaudit as PA
    reads = [SKATTEBO, LIKELY,
             _read("Rachaad White", "WAS", "RB", "neutral", {"carry_share": 0.45}, 0.40, 1.2, implied=19.0),
             _read("Wan'Dale Robinson", "NYG", "WR", "breakout", {"tgt_share": 0.26}, 0.31, 0.4),
             _read("Terry McLaurin", "WAS", "WR", "avoid", {"tgt_share": 0.25}, 0.38, 1.6, implied=19.0)]
    scorers = [_td(x["player"], x["team"], x["pos"], x["td"]["model_prob"]) for x in reads]
    scorers.append(_td("Deebo Samuel", "WAS", "WR", 0.42))
    b = _board(reads, scorers)
    gp = GP.build(b, "nfl")
    assert gp["scorers_priced"] == 6 and gp["scorers_researched"] == 2
    assert gp["research_census"] == {"no matchup read on the player": 1, "the read says avoid": 1,
                                     "no red-zone role (under 0.9 expected red-zone chances)": 1,
                                     f"under {GP.RESEARCH_MIN} of the {GP.RESEARCH_MAX} research points": 1}, \
        gp["research_census"]
    b["game_parlays"] = gp
    lines = PA.report("nfl", b)
    assert any("2 of 6 priced scorers carry a research case" in ln for ln in lines), lines
    assert any(ln.strip() == "turned away: the read says avoid — 1" for ln in lines)
    assert "research_census" not in GP.build({"games": [], "td_field": []}, "nhl")

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
