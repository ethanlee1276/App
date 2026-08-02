"""Ballpark engine.

Each stadium gets a profile of scoring factors; ``evaluate_park`` turns the
profile into per-market multipliers plus reasons. Factors here are directional
approximations of published multi-year park factors — like the NFL weather
coefficients, they're centralised so the ML phase can replace them with values
fit on the historical database.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import (ParkProfile, TOTAL_BASES, HITS, HOME_RUNS, STRIKEOUTS,
                     OUTS)

# All 30 parks. Factors are directional approximations of published
# multi-year park factors (1.0 = league average); the ML phase can refit them
# from the historical database.
PARKS: dict[str, ParkProfile] = {
    "wrigley": ParkProfile("wrigley", "Wrigley Field", "CHC",
                           hr_factor=1.04, run_factor=1.02, k_factor=1.00,
                           lf_ft=355, cf_ft=400, rf_ft=353,
                           lf_wall_ft=11.5, rf_wall_ft=11.5,
                           capacity=41363, opened=1914,
                           plays="The most weather-dependent park in baseball. Wind off "
                                 "Lake Michigan blowing out turns it into a launching pad; "
                                 "blowing in, the same park plays like a pitcher's park. "
                                 "Check the wind before anything else here."),
    "coors": ParkProfile("coors", "Coors Field", "COL",
                         hr_factor=1.22, run_factor=1.28, k_factor=0.92,
                         altitude_ft=5280,
                         lf_ft=347, cf_ft=415, rf_ft=350,
                         lf_wall_ft=8, rf_wall_ft=14,
                         capacity=46897, opened=1995,
                         plays="A mile up, the air is ~18% thinner: fly balls carry roughly "
                               "5-9% farther and breaking pitches break less. The outfield "
                               "is the largest in MLB precisely to fight that, which is why "
                               "Coors inflates doubles and triples even more than homers."),
    "loandepot": ParkProfile("loandepot", "loanDepot park", "MIA",
                             hr_factor=0.88, run_factor=0.92, k_factor=1.05,
                             roof="retractable",
                             lf_ft=344, cf_ft=400, rf_ft=335,
                             capacity=36742, opened=2012,
                             plays="Roof usually closed against Miami heat, so weather rarely "
                                   "matters. Deep left-center and heavy indoor air make this "
                                   "one of the hardest parks in the league to homer in."),
    "yankee": ParkProfile("yankee", "Yankee Stadium", "NYY",
                          hr_factor=1.10, run_factor=1.04, k_factor=1.00,
                          lf_ft=318, cf_ft=408, rf_ft=314,
                          lf_wall_ft=8, rf_wall_ft=8,
                          capacity=46537, opened=2009,
                          plays="The short porch: 314 down the right-field line with a low "
                                "wall. Left-handed pull power plays up here more than at any "
                                "other park — a 335-foot fly that dies elsewhere is a homer."),
    "fenway": ParkProfile("fenway", "Fenway Park", "BOS",
                          hr_factor=0.96, run_factor=1.08, k_factor=0.97,
                          lf_ft=310, cf_ft=420, rf_ft=302,
                          lf_wall_ft=37, rf_wall_ft=5,
                          capacity=37755, opened=1912,
                          plays="The Green Monster is 310 feet away and 37 feet tall, so it "
                                "converts home runs into doubles rather than allowing them. "
                                "That is the whole story of the park: runs well above "
                                "average, home runs slightly below. Deep right-center "
                                "(Triangle, 420) punishes left-handed power."),
    "oracle": ParkProfile("oracle", "Oracle Park", "SF",
                          hr_factor=0.85, run_factor=0.94, k_factor=1.02,
                          lf_ft=339, cf_ft=399, rf_ft=309,
                          lf_wall_ft=8, rf_wall_ft=24,
                          capacity=41265, opened=2000,
                          plays="The toughest home-run park in baseball. Right field is 309 "
                                "down the line but behind a 24-foot wall, and Triples Alley "
                                "in right-center runs out past 415. Cold, damp bay air "
                                "suppresses carry on top of that."),
    "petco": ParkProfile("petco", "Petco Park", "SD",
                         hr_factor=0.92, run_factor=0.93, k_factor=1.04,
                         lf_ft=336, cf_ft=396, rf_ft=322,
                         capacity=40222, opened=2004,
                         plays="The marine layer rolls in after sunset and kills carry — day "
                               "games here play meaningfully different from night games. "
                               "Deep power alleys reinforce it."),
    "gabp": ParkProfile("gabp", "Great American Ball Park", "CIN",
                        hr_factor=1.18, run_factor=1.06, k_factor=1.01,
                        lf_ft=328, cf_ft=404, rf_ft=325,
                        capacity=43500, opened=2003,
                        plays="Nicknamed the Great American Small Park. Short lines, short "
                              "power alleys and warm summer river air make it one of the two "
                              "or three best home-run parks in the majors — for both hands."),
    "tropicana": ParkProfile("tropicana", "Tropicana Field", "TBR",
                             hr_factor=0.94, run_factor=0.95, k_factor=1.03,
                             roof="dome", surface="turf",
                             lf_ft=315, cf_ft=404, rf_ft=322,
                             capacity=25025, opened=1990,
                             plays="Fixed dome: no wind, no temperature, no weather read at "
                                   "all — the one park where conditions are identical every "
                                   "night. Catwalks are in play. Turf speeds up ground balls."),
    "chase": ParkProfile("chase", "Chase Field", "ARI",
                         hr_factor=1.06, run_factor=1.05, k_factor=0.99,
                         roof="retractable",
                         lf_ft=330, cf_ft=407, rf_ft=335,
                         capacity=48686, opened=1998,
                         plays="Desert air used to make this a launching pad; the humidor "
                               "installed in 2018 took a real bite out of that. Still "
                               "hitter-friendly, with a deep center that feeds triples."),
    "rate": ParkProfile("rate", "Rate Field", "CWS",
                        hr_factor=1.10, run_factor=1.02, k_factor=1.00,
                        lf_ft=330, cf_ft=400, rf_ft=335,
                        capacity=40615, opened=1991,
                        plays="Symmetric and unremarkable on paper, but low walls and a "
                              "prevailing summer wind out to right make it consistently one "
                              "of the better home-run parks in the American League."),
    "progressive": ParkProfile("progressive", "Progressive Field", "CLE",
                               hr_factor=0.95, run_factor=0.97, k_factor=1.03,
                               lf_ft=325, cf_ft=405, rf_ft=325,
                               lf_wall_ft=19, rf_wall_ft=8,
                               capacity=34830, opened=1994,
                               plays="Short down the left-field line but a 19-foot wall "
                                     "there turns right-handed pull flies into doubles. "
                                     "Cold April and September nights suppress everything."),
    "comerica": ParkProfile("comerica", "Comerica Park", "DET",
                            hr_factor=0.92, run_factor=0.96, k_factor=1.01,
                            lf_ft=345, cf_ft=412, rf_ft=330,
                            capacity=41083, opened=2000,
                            plays="Comerica National Park: 345 to left and 412 to center "
                                  "swallow right-handed power. Left-handed hitters get a "
                                  "far friendlier park than right-handed ones here."),
    "kauffman": ParkProfile("kauffman", "Kauffman Stadium", "KC",
                            hr_factor=0.87, run_factor=1.00, k_factor=0.98,
                            lf_ft=330, cf_ft=410, rf_ft=330,
                            capacity=37903, opened=1973,
                            plays="One of the largest outfields in baseball. Home runs die "
                                  "here, but balls in the gap roll forever — run scoring is "
                                  "league-average because doubles and triples replace them."),
    "target": ParkProfile("target", "Target Field", "MIN",
                          hr_factor=0.98, run_factor=0.99, k_factor=1.00,
                          lf_ft=339, cf_ft=404, rf_ft=328,
                          lf_wall_ft=8, rf_wall_ft=23,
                          capacity=38544, opened=2010,
                          plays="Close to neutral overall. The 23-foot wall in right cuts "
                                "into left-handed power, and early-season cold in Minnesota "
                                "is a bigger factor than the dimensions."),
    "daikin": ParkProfile("daikin", "Daikin Park", "HOU",
                          hr_factor=1.08, run_factor=1.02, k_factor=1.00,
                          roof="retractable",
                          lf_ft=315, cf_ft=409, rf_ft=326,
                          lf_wall_ft=19, rf_wall_ft=7,
                          capacity=41000, opened=2000,
                          plays="The Crawford Boxes sit 315 feet down the left-field line — "
                                "the single most inviting target in the majors for a "
                                "right-handed pull hitter. Roof is usually closed in summer, "
                                "so wind rarely matters."),
    "angel": ParkProfile("angel", "Angel Stadium", "LAA",
                         hr_factor=1.02, run_factor=0.98, k_factor=1.00,
                         lf_ft=330, cf_ft=400, rf_ft=330,
                         capacity=45517, opened=1966,
                         plays="Symmetric and close to neutral for home runs, with dry "
                               "Southern California air. Slightly run-suppressing because "
                               "the gaps are deep enough to hold doubles down."),
    "sutter": ParkProfile("sutter", "Sutter Health Park", "OAK",
                          hr_factor=1.02, run_factor=1.04, k_factor=0.98,
                          lf_ft=330, cf_ft=403, rf_ft=325,
                          capacity=14014, opened=2000,
                          plays="A minor-league park pressed into major-league service. "
                                "Small, hot in the Sacramento summer, and with far less "
                                "reliable park-factor history than any other venue — treat "
                                "its numbers as provisional."),
    "tmobile": ParkProfile("tmobile", "T-Mobile Park", "SEA",
                           hr_factor=0.98, run_factor=0.90, k_factor=1.08,
                           roof="retractable",
                           lf_ft=331, cf_ft=401, rf_ft=326,
                           capacity=47929, opened=1999,
                           plays="The strongest run suppressor in the league. Cool, heavy "
                                 "marine air at night knocks balls down, and the roof is a "
                                 "cover rather than a seal — it never traps warm air. "
                                 "Strikeouts run high here."),
    "globelife": ParkProfile("globelife", "Globe Life Field", "TEX",
                             hr_factor=0.98, run_factor=0.98, k_factor=1.00,
                             roof="retractable",
                             lf_ft=329, cf_ft=407, rf_ft=326,
                             capacity=40300, opened=2020,
                             plays="Built to be air-conditioned rather than open, and it "
                                   "plays much closer to neutral than the old ballpark in "
                                   "Arlington ever did. Deep right-center is the one real "
                                   "obstacle."),
    "rogers": ParkProfile("rogers", "Rogers Centre", "TOR",
                          hr_factor=1.06, run_factor=1.02, k_factor=0.99,
                          roof="retractable", surface="turf",
                          lf_ft=328, cf_ft=400, rf_ft=328,
                          capacity=39150, opened=1989,
                          plays="The 2023-24 renovation pulled the outfield walls in and "
                                "changed how the park plays — older park factors understate "
                                "it. Turf infield speeds up ground balls."),
    "truist": ParkProfile("truist", "Truist Park", "ATL",
                          hr_factor=1.04, run_factor=1.02, k_factor=1.00,
                          lf_ft=335, cf_ft=400, rf_ft=325,
                          capacity=41084, opened=2017,
                          plays="Mildly hitter-friendly, and Georgia summer heat is doing "
                                "most of that work — July and August here play noticeably "
                                "hotter than the April version of the same park."),
    "citi": ParkProfile("citi", "Citi Field", "NYM",
                        hr_factor=0.97, run_factor=0.94, k_factor=1.03,
                        lf_ft=335, cf_ft=408, rf_ft=330,
                        lf_wall_ft=8, rf_wall_ft=8,
                        capacity=41922, opened=2009,
                        plays="Opened as an extreme pitcher's park; the fences have been "
                              "moved in twice since and it still suppresses. Deep "
                              "right-center remains the reason."),
    "cbp": ParkProfile("cbp", "Citizens Bank Park", "PHI",
                       hr_factor=1.12, run_factor=1.04, k_factor=1.00,
                       lf_ft=329, cf_ft=401, rf_ft=329,
                       capacity=42901, opened=2004,
                       plays="Short, symmetric and consistently one of the best home-run "
                             "parks in the National League. No quirk to learn — the whole "
                             "outfield is simply close."),
    "nationals": ParkProfile("nationals", "Nationals Park", "WSH",
                             hr_factor=1.02, run_factor=1.00, k_factor=1.00,
                             lf_ft=336, cf_ft=402, rf_ft=335,
                             capacity=41339, opened=2008,
                             plays="About as close to a league-average park as exists. "
                                   "Humid DC summers add a little carry; nothing about the "
                                   "shape favors either hand."),
    "amfam": ParkProfile("amfam", "American Family Field", "MIL",
                         hr_factor=1.08, run_factor=1.00, k_factor=1.01,
                         roof="retractable",
                         lf_ft=342, cf_ft=400, rf_ft=345,
                         capacity=41700, opened=2001,
                         plays="Homer-friendly despite unremarkable distances — the roof "
                               "traps warm air when closed, and the enclosed bowl kills the "
                               "wind that would otherwise knock balls down."),
    "busch": ParkProfile("busch", "Busch Stadium", "STL",
                         hr_factor=0.90, run_factor=0.96, k_factor=1.00,
                         lf_ft=336, cf_ft=400, rf_ft=335,
                         capacity=44383, opened=2006,
                         plays="Deep gaps and heavy Midwest summer air make this a genuine "
                               "pitcher's park, particularly for home runs. Doubles survive "
                               "here where homers don't."),
    "pnc": ParkProfile("pnc", "PNC Park", "PIT",
                       lf_ft=325, cf_ft=399, rf_ft=320,
                       lf_wall_ft=6, rf_wall_ft=21,
                       hr_factor=0.88, run_factor=0.96, k_factor=1.00,
                       capacity=38747, opened=2001,
                       plays="Right field is only 320 down the line but the 21-foot Clemente "
                             "Wall stands in front of it, so left-handed power turns into "
                             "doubles. Deep left-center handles the right-handed side."),
    "dodger": ParkProfile("dodger", "Dodger Stadium", "LAD",
                          hr_factor=1.05, run_factor=0.96, k_factor=1.03,
                          lf_ft=330, cf_ft=395, rf_ft=330,
                          capacity=56000, opened=1962,
                          plays="An unusual split: home runs above average, runs below. Dry "
                              "night air and a shallow 395-foot center let fly balls out, "
                              "while big foul territory converts would-be baserunners into "
                              "outs. Strikeouts run high."),
    "camden": ParkProfile("camden", "Oriole Park at Camden Yards", "BAL",
                          hr_factor=1.00, run_factor=0.98, k_factor=1.00,
                          lf_ft=333, cf_ft=400, rf_ft=318,
                          lf_wall_ft=13, rf_wall_ft=21,
                          capacity=44970, opened=1992,
                          plays="Left field was pushed back and raised in 2022, then brought "
                                "partway in again before 2025 — park factors that span those "
                                "seasons are mixing two different ballparks. Right field, at "
                                "318, has stayed friendly to left-handed pull power throughout."),
}

GENERIC_PARK = ParkProfile("generic", "Generic Park", "")


def get_park(key: str) -> ParkProfile:
    return PARKS.get(key, GENERIC_PARK)


# Built once. Every park names the team it belongs to, so the reverse index
# is free — and it is what lets a PAST game be attributed to a ballpark: a
# game log already records the opponent and whether the player was home, and
# those two facts name the venue exactly.
_BY_TEAM: dict[str, ParkProfile] = {p.team: p for p in PARKS.values() if p.team}


def park_for_team(abbr: str) -> ParkProfile | None:
    """The park a team plays its home games in, or None if unknown."""
    return _BY_TEAM.get((abbr or "").upper())


def park_of_game(player_team: str, opponent: str, home: bool) -> ParkProfile | None:
    """Which ballpark a past game was played in.

    The home side's park, whichever side that is. Neutral-site games are rare
    enough in a regular season that treating the home team's park as the
    venue is right far more often than any guess that tries to be clever."""
    return park_for_team(player_team if home else opponent)


@dataclass
class ParkEffect:
    multipliers: dict[str, float]
    reasons: list[str] = field(default_factory=list)


def evaluate_park(park: ParkProfile) -> ParkEffect:
    # Outs stays at 1.0 deliberately. A park moves how often contact goes
    # for damage; how long a manager leaves his starter in is a bullpen and
    # scoreboard decision, and inventing a park factor for it would be
    # decoration.
    mult = {TOTAL_BASES: 1.0, HITS: 1.0, HOME_RUNS: 1.0, STRIKEOUTS: 1.0,
            OUTS: 1.0}
    reasons: list[str] = []

    # HR factor hits home-run props hardest and total bases partially.
    if abs(park.hr_factor - 1.0) >= 0.05:
        mult[HOME_RUNS] *= park.hr_factor
        mult[TOTAL_BASES] *= 1.0 + (park.hr_factor - 1.0) * 0.45
        verb = "boosts" if park.hr_factor > 1 else "suppresses"
        reasons.append(f"{park.name} {verb} home runs "
                       f"({(park.hr_factor - 1) * 100:+.0f}% vs average)")

    # Run factor lifts hits/TB generally.
    if abs(park.run_factor - 1.0) >= 0.04:
        mult[HITS] *= 1.0 + (park.run_factor - 1.0) * 0.6
        mult[TOTAL_BASES] *= 1.0 + (park.run_factor - 1.0) * 0.5
        if park.run_factor > 1:
            reasons.append(f"{park.name} plays hitter-friendly "
                           f"({(park.run_factor - 1) * 100:+.0f}% runs)")
        else:
            reasons.append(f"{park.name} plays pitcher-friendly "
                           f"({(park.run_factor - 1) * 100:+.0f}% runs)")

    # K factor moves pitcher strikeout props (and nudges hitter contact).
    if abs(park.k_factor - 1.0) >= 0.03:
        mult[STRIKEOUTS] *= park.k_factor
        if park.k_factor > 1:
            reasons.append(f"{park.name} elevates strikeouts "
                           f"({(park.k_factor - 1) * 100:+.0f}%)")

    # Altitude: thin air adds carry beyond the baked-in factors' description.
    if park.altitude_ft >= 3000:
        reasons.append(f"Altitude {park.altitude_ft:,} ft — thin air adds carry")

    return ParkEffect(mult, reasons)
