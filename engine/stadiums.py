"""NFL stadium reference.

Deliberately thinner than ``engine.mlb.parks``. A ballpark genuinely
changes what a hitter can do — a 310-foot wall and a 420-foot center field
produce different outcomes from identical contact, which is why MLB park
factors are large, stable and worth modelling. An NFL field is 100 yards
everywhere. What actually varies between venues is the *environment*:

  * indoors vs outdoors — the dominant effect, because it removes wind,
    cold and precipitation entirely rather than changing the geometry
  * altitude — thin air in Denver adds a few yards of field-goal range
  * surface — grass vs turf, a real but small influence on speed and a
    contested one on injury rates

Everything else people cite about NFL venues (crowd noise, "the wind
tunnel at Soldier Field") is really a weather or roof story, and the game
card already shows live weather. So this table is context for the game
page, not a source of edges, and nothing here feeds the model.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Stadium:
    team: str
    name: str
    roof: str = "outdoors"       # outdoors | dome | retractable
    surface: str = "grass"       # grass | turf
    altitude_ft: int = 0
    capacity: int = 0
    opened: int = 0
    plays: str = ""


# Home team abbreviation -> stadium. Abbreviations follow nflverse.
STADIUMS: dict[str, Stadium] = {
    "ARI": Stadium("ARI", "State Farm Stadium", "retractable", "grass", 1070, 63400, 2006,
                   "Retractable roof and a roll-out grass field; the roof is usually shut "
                   "against Arizona heat, so weather rarely reaches the game."),
    "ATL": Stadium("ATL", "Mercedes-Benz Stadium", "retractable", "turf", 1050, 71000, 2017,
                   "Effectively an indoor game — the roof is closed for nearly everything. "
                   "Fast turf, no weather, no wind."),
    "BAL": Stadium("BAL", "M&T Bank Stadium", "outdoors", "grass", 33, 71008, 1998,
                   "Open-air Mid-Atlantic: mild early, genuinely cold and windy by "
                   "December."),
    "BUF": Stadium("BUF", "Highmark Stadium", "outdoors", "turf", 600, 71608, 1973,
                   "The most weather-exposed venue in the league. Lake Erie wind and "
                   "lake-effect snow can turn a December game into a different sport — "
                   "check conditions before touching a total here."),
    "CAR": Stadium("CAR", "Bank of America Stadium", "outdoors", "turf", 750, 74867, 1996,
                   "Open air but a mild climate; weather is a factor only late in the year."),
    "CHI": Stadium("CHI", "Soldier Field", "outdoors", "grass", 597, 61500, 1924,
                   "Wind off Lake Michigan is the story — swirling and hard to predict, and "
                   "the single biggest reason kickers and passing games underperform here."),
    "CIN": Stadium("CIN", "Paycor Stadium", "outdoors", "turf", 490, 65515, 2000,
                   "Open air on the Ohio River; cold and wind matter in December."),
    "CLE": Stadium("CLE", "Huntington Bank Field", "outdoors", "grass", 580, 67431, 1999,
                   "On the shore of Lake Erie — wind and cold rival Buffalo's late in the "
                   "season."),
    "DAL": Stadium("DAL", "AT&T Stadium", "retractable", "turf", 595, 80000, 2009,
                   "Roof almost always closed: an indoor game with fast turf and no weather."),
    "DEN": Stadium("DEN", "Empower Field at Mile High", "outdoors", "grass", 5280, 76125, 2001,
                   "A mile above sea level. Thin air adds roughly 5-10% to field-goal range "
                   "and lets the ball carry — the one NFL venue where altitude is a real, "
                   "repeatable effect. Also cold and windy in winter."),
    "DET": Stadium("DET", "Ford Field", "dome", "turf", 600, 65000, 2002,
                   "Fixed dome: identical conditions every week, no weather read needed."),
    "GB": Stadium("GB", "Lambeau Field", "outdoors", "grass", 640, 81441, 1957,
                  "Open air in Wisconsin. Late-season cold here is severe enough to affect "
                  "ball handling and kicking, not just comfort."),
    "HOU": Stadium("HOU", "NRG Stadium", "retractable", "turf", 50, 72220, 2002,
                   "Retractable roof, usually closed against Gulf heat and humidity."),
    "IND": Stadium("IND", "Lucas Oil Stadium", "retractable", "turf", 715, 67000, 2008,
                   "Roof almost always closed — treat as indoors."),
    "JAX": Stadium("JAX", "EverBank Stadium", "outdoors", "grass", 16, 67814, 1995,
                   "Open air in Florida: heat and humidity early, rarely cold."),
    "KC": Stadium("KC", "GEHA Field at Arrowhead Stadium", "outdoors", "grass", 889, 76416, 1972,
                  "Open air, genuinely cold in January, and the loudest stadium in the "
                  "league — the crowd-noise effect shows up as opponent false starts more "
                  "than as scoring."),
    "LA": Stadium("LA", "SoFi Stadium", "dome", "turf", 125, 70240, 2020,
                  "Canopy roof with open sides: no rain, no wind of consequence, mild "
                  "temperatures. Plays as indoors."),
    "LAC": Stadium("LAC", "SoFi Stadium", "dome", "turf", 125, 70240, 2020,
                   "Canopy roof with open sides: no rain, no wind of consequence, mild "
                   "temperatures. Plays as indoors."),
    "LV": Stadium("LV", "Allegiant Stadium", "dome", "turf", 2030, 65000, 2020,
                  "Fixed dome in the desert; conditions are constant week to week."),
    "MIA": Stadium("MIA", "Hard Rock Stadium", "outdoors", "grass", 8, 65326, 1987,
                   "Open air with a canopy over the seats, not the field. September heat and "
                   "humidity here are a real conditioning factor for visiting teams."),
    "MIN": Stadium("MIN", "U.S. Bank Stadium", "dome", "turf", 830, 66655, 2016,
                   "Fixed dome: no weather at all, and one of the louder indoor buildings."),
    "NE": Stadium("NE", "Gillette Stadium", "outdoors", "turf", 285, 65878, 2002,
                  "Open air in New England — cold, wind and rain are all live factors from "
                  "November on."),
    "NO": Stadium("NO", "Caesars Superdome", "dome", "turf", 3, 73208, 1975,
                  "Fixed dome, fast turf, historically one of the highest-scoring "
                  "environments in the league."),
    "NYG": Stadium("NYG", "MetLife Stadium", "outdoors", "turf", 25, 82500, 2010,
                   "Open air in the Meadowlands; swirling wind is a recurring problem for "
                   "kickers."),
    "NYJ": Stadium("NYJ", "MetLife Stadium", "outdoors", "turf", 25, 82500, 2010,
                   "Open air in the Meadowlands; swirling wind is a recurring problem for "
                   "kickers."),
    "PHI": Stadium("PHI", "Lincoln Financial Field", "outdoors", "grass", 39, 69796, 2003,
                   "Open air; wind and cold matter late in the season."),
    "PIT": Stadium("PIT", "Acrisure Stadium", "outdoors", "grass", 730, 68400, 2001,
                   "Open air at the confluence of three rivers; the grass field is often in "
                   "poor condition by December."),
    "SEA": Stadium("SEA", "Lumen Field", "outdoors", "turf", 20, 68740, 2002,
                   "Partial roof over the seats amplifies crowd noise into the bowl. Rain is "
                   "common, extreme cold is not."),
    "SF": Stadium("SF", "Levi's Stadium", "outdoors", "grass", 10, 68500, 2014,
                  "Open air, mild climate; early-season afternoon heat on the sunny side is "
                  "the only notable condition."),
    "TB": Stadium("TB", "Raymond James Stadium", "outdoors", "grass", 15, 69218, 1998,
                  "Open air in Florida: heat and humidity early, thunderstorms possible."),
    "TEN": Stadium("TEN", "Nissan Stadium", "outdoors", "grass", 400, 69143, 1999,
                   "Open air; moderate climate with real cold only in December and January."),
    "WAS": Stadium("WAS", "Northwest Stadium", "outdoors", "grass", 200, 67617, 1997,
                   "Open air in the Mid-Atlantic; weather is a factor late in the year."),
}

GENERIC_STADIUM = Stadium("", "", "outdoors", "grass")


def get_stadium(team: str) -> Stadium:
    return STADIUMS.get((team or "").upper(), GENERIC_STADIUM)


def stadium_to_dict(team: str) -> dict:
    s = get_stadium(team)
    return {
        "team": s.team, "name": s.name, "roof": s.roof, "surface": s.surface,
        "altitude_ft": s.altitude_ft, "capacity": s.capacity,
        "opened": s.opened, "plays": s.plays,
    }
