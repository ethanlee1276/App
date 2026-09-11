"""Which group each team plays in — conference, division, or neither.

Standings without groups is a list of thirty teams, and nobody reads a
league that way. The alignments below are static facts about how each
league is organised, kept next to each other so a standings table, a
playoff seeding and a division race all agree about what a division is.

Two things this file is careful about:

* **Abbreviations are the ones OUR data uses**, not the ones a style guide
  prefers. A mapping keyed on "WSH" when the games table says "WAS" is a
  team that silently vanishes from its own division, so aliases are listed
  rather than assumed.
* **College football is not here.** 134 programs across a conference map
  that changes every summer is not a static fact — it rides in the ESPN
  payload with the games, and `engine.standings` reads it from there.
  Hard-coding it would be a table that is wrong by September.
"""

from __future__ import annotations

# (conference, division) per team.
NFL = {
    "BUF": ("AFC", "East"), "MIA": ("AFC", "East"),
    "NE": ("AFC", "East"), "NYJ": ("AFC", "East"),
    "BAL": ("AFC", "North"), "CIN": ("AFC", "North"),
    "CLE": ("AFC", "North"), "PIT": ("AFC", "North"),
    "HOU": ("AFC", "South"), "IND": ("AFC", "South"),
    "JAX": ("AFC", "South"), "TEN": ("AFC", "South"),
    "DEN": ("AFC", "West"), "KC": ("AFC", "West"),
    "LV": ("AFC", "West"), "LAC": ("AFC", "West"),
    "DAL": ("NFC", "East"), "NYG": ("NFC", "East"),
    "PHI": ("NFC", "East"), "WAS": ("NFC", "East"),
    "CHI": ("NFC", "North"), "DET": ("NFC", "North"),
    "GB": ("NFC", "North"), "MIN": ("NFC", "North"),
    "ATL": ("NFC", "South"), "CAR": ("NFC", "South"),
    "NO": ("NFC", "South"), "TB": ("NFC", "South"),
    "ARI": ("NFC", "West"), "LA": ("NFC", "West"),
    "SF": ("NFC", "West"), "SEA": ("NFC", "West"),
}

MLB = {
    "BAL": ("AL", "East"), "BOS": ("AL", "East"), "NYY": ("AL", "East"),
    "TBR": ("AL", "East"), "TOR": ("AL", "East"),
    "CWS": ("AL", "Central"), "CLE": ("AL", "Central"),
    "DET": ("AL", "Central"), "KC": ("AL", "Central"),
    "MIN": ("AL", "Central"),
    "HOU": ("AL", "West"), "LAA": ("AL", "West"), "OAK": ("AL", "West"),
    "SEA": ("AL", "West"), "TEX": ("AL", "West"),
    "ATL": ("NL", "East"), "MIA": ("NL", "East"), "NYM": ("NL", "East"),
    "PHI": ("NL", "East"), "WSH": ("NL", "East"),
    "CHC": ("NL", "Central"), "CIN": ("NL", "Central"),
    "MIL": ("NL", "Central"), "PIT": ("NL", "Central"),
    "STL": ("NL", "Central"),
    "ARI": ("NL", "West"), "COL": ("NL", "West"), "LAD": ("NL", "West"),
    "SD": ("NL", "West"), "SF": ("NL", "West"),
}

NBA = {
    "BOS": ("East", "Atlantic"), "BKN": ("East", "Atlantic"),
    "NYK": ("East", "Atlantic"), "PHI": ("East", "Atlantic"),
    "TOR": ("East", "Atlantic"),
    "CHI": ("East", "Central"), "CLE": ("East", "Central"),
    "DET": ("East", "Central"), "IND": ("East", "Central"),
    "MIL": ("East", "Central"),
    "ATL": ("East", "Southeast"), "CHA": ("East", "Southeast"),
    "MIA": ("East", "Southeast"), "ORL": ("East", "Southeast"),
    "WAS": ("East", "Southeast"),
    "DEN": ("West", "Northwest"), "MIN": ("West", "Northwest"),
    "OKC": ("West", "Northwest"), "POR": ("West", "Northwest"),
    "UTA": ("West", "Northwest"),
    "GSW": ("West", "Pacific"), "LAC": ("West", "Pacific"),
    "LAL": ("West", "Pacific"), "PHX": ("West", "Pacific"),
    "SAC": ("West", "Pacific"),
    "DAL": ("West", "Southwest"), "HOU": ("West", "Southwest"),
    "MEM": ("West", "Southwest"), "NOP": ("West", "Southwest"),
    "SAS": ("West", "Southwest"),
}

# The WNBA runs conferences with no divisions inside them, and its
# alignment genuinely moves — Golden State arrived in 2025, Toronto and
# Portland in 2026. A team missing from this map still appears in the
# standings under "League"; it does not disappear.
WNBA = {
    "ATL": ("East", ""), "CHI": ("East", ""), "CON": ("East", ""),
    "IND": ("East", ""), "NYL": ("East", ""), "WAS": ("East", ""),
    "TOR": ("East", ""),
    "DAL": ("West", ""), "GSV": ("West", ""), "LVA": ("West", ""),
    "LAS": ("West", ""), "MIN": ("West", ""), "PHX": ("West", ""),
    "SEA": ("West", ""), "POR": ("West", ""),
}

MAPS = {"nfl": NFL, "mlb": MLB, "nba": NBA, "wnba": WNBA}

# Abbreviations that mean the same club. Our history spans six seasons and
# relocations are in it: a 2021 Oakland game and a 2026 Las Vegas game are
# the same franchise's record, and splitting them would show two half
# teams instead of one.
ALIASES = {
    "nfl": {"LAR": "LA", "STL": "LA", "OAK": "LV", "SD": "LAC",
            "WSH": "WAS", "ARZ": "ARI"},
    "mlb": {"WAS": "WSH", "TB": "TBR", "CHW": "CWS", "SDP": "SD",
            "SFG": "SF", "KCR": "KC", "ATH": "OAK"},
    "nba": {"NO": "NOP", "NY": "NYK", "GS": "GSW", "SA": "SAS",
            "PHO": "PHX", "BRK": "BKN", "CHO": "CHA", "WSH": "WAS"},
    "wnba": {"LV": "LVA", "NY": "NYL", "LA": "LAS", "GS": "GSV",
             "CONN": "CON"},
}


def canonical(sport: str, team: str) -> str:
    """The one abbreviation this league's map is keyed on."""
    t = (team or "").strip().upper()
    return ALIASES.get(sport, {}).get(t, t)


def group_of(sport: str, team: str) -> tuple[str, str]:
    """``(conference, division)`` — either may be empty.

    An unknown team returns empty strings rather than raising. A standings
    page that crashes on an expansion franchise is worse than one that
    lists it under "League" until somebody adds the row.
    """
    return MAPS.get(sport, {}).get(canonical(sport, team), ("", ""))


def has_divisions(sport: str) -> bool:
    return any(div for _conf, div in MAPS.get(sport, {}).values())
