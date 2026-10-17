/* NHL team identities (2026-10-03) — same shape as teams_nba.js so the
   shared avatar, monogram and colour helpers work without a special case.
   Keyed by the NHL feed's own abbreviations (engine/sources/nhldata). */
const NHL_TEAMS = {
  "ANA": {
    "name": "Anaheim Ducks",
    "nick": "Ducks",
    "loc": "Anaheim",
    "primary": "#fc4c02",
    "secondary": "#b9975b",
    "tertiary": "#000000"
  },
  "BOS": {
    "name": "Boston Bruins",
    "nick": "Bruins",
    "loc": "Boston",
    "primary": "#fdb927",
    "secondary": "#000000",
    "tertiary": "#ffffff"
  },
  "BUF": {
    "name": "Buffalo Sabres",
    "nick": "Sabres",
    "loc": "Buffalo",
    "primary": "#003087",
    "secondary": "#ffb81c",
    "tertiary": "#ffffff"
  },
  "CGY": {
    "name": "Calgary Flames",
    "nick": "Flames",
    "loc": "Calgary",
    "primary": "#c8102e",
    "secondary": "#f1be48",
    "tertiary": "#ffffff"
  },
  "CAR": {
    "name": "Carolina Hurricanes",
    "nick": "Hurricanes",
    "loc": "Carolina",
    "primary": "#ce1126",
    "secondary": "#000000",
    "tertiary": "#a2aaad"
  },
  "CHI": {
    "name": "Chicago Blackhawks",
    "nick": "Blackhawks",
    "loc": "Chicago",
    "primary": "#cf0a2c",
    "secondary": "#000000",
    "tertiary": "#ff671b"
  },
  "COL": {
    "name": "Colorado Avalanche",
    "nick": "Avalanche",
    "loc": "Colorado",
    "primary": "#6f263d",
    "secondary": "#236192",
    "tertiary": "#a2aaad"
  },
  "CBJ": {
    "name": "Columbus Blue Jackets",
    "nick": "Blue Jackets",
    "loc": "Columbus",
    "primary": "#002654",
    "secondary": "#ce1126",
    "tertiary": "#a4a9ad"
  },
  "DAL": {
    "name": "Dallas Stars",
    "nick": "Stars",
    "loc": "Dallas",
    "primary": "#006847",
    "secondary": "#8f8f8c",
    "tertiary": "#000000"
  },
  "DET": {
    "name": "Detroit Red Wings",
    "nick": "Red Wings",
    "loc": "Detroit",
    "primary": "#ce1126",
    "secondary": "#ffffff",
    "tertiary": "#000000"
  },
  "EDM": {
    "name": "Edmonton Oilers",
    "nick": "Oilers",
    "loc": "Edmonton",
    "primary": "#041e42",
    "secondary": "#ff4c00",
    "tertiary": "#ffffff"
  },
  "FLA": {
    "name": "Florida Panthers",
    "nick": "Panthers",
    "loc": "Florida",
    "primary": "#041e42",
    "secondary": "#c8102e",
    "tertiary": "#b9975b"
  },
  "LAK": {
    "name": "Los Angeles Kings",
    "nick": "Kings",
    "loc": "Los Angeles",
    "primary": "#111111",
    "secondary": "#a2aaad",
    "tertiary": "#ffffff"
  },
  "MIN": {
    "name": "Minnesota Wild",
    "nick": "Wild",
    "loc": "Minnesota",
    "primary": "#154734",
    "secondary": "#a6192e",
    "tertiary": "#eaaa00"
  },
  "MTL": {
    "name": "Montréal Canadiens",
    "nick": "Canadiens",
    "loc": "Montréal",
    "primary": "#af1e2d",
    "secondary": "#192168",
    "tertiary": "#ffffff"
  },
  "NSH": {
    "name": "Nashville Predators",
    "nick": "Predators",
    "loc": "Nashville",
    "primary": "#ffb81c",
    "secondary": "#041e42",
    "tertiary": "#ffffff"
  },
  "NJD": {
    "name": "New Jersey Devils",
    "nick": "Devils",
    "loc": "New Jersey",
    "primary": "#ce1126",
    "secondary": "#000000",
    "tertiary": "#ffffff"
  },
  "NYI": {
    "name": "New York Islanders",
    "nick": "Islanders",
    "loc": "New York",
    "primary": "#00539b",
    "secondary": "#f47d30",
    "tertiary": "#ffffff"
  },
  "NYR": {
    "name": "New York Rangers",
    "nick": "Rangers",
    "loc": "New York",
    "primary": "#0038a8",
    "secondary": "#ce1126",
    "tertiary": "#ffffff"
  },
  "OTT": {
    "name": "Ottawa Senators",
    "nick": "Senators",
    "loc": "Ottawa",
    "primary": "#c52032",
    "secondary": "#000000",
    "tertiary": "#c2912c"
  },
  "PHI": {
    "name": "Philadelphia Flyers",
    "nick": "Flyers",
    "loc": "Philadelphia",
    "primary": "#f74902",
    "secondary": "#000000",
    "tertiary": "#ffffff"
  },
  "PIT": {
    "name": "Pittsburgh Penguins",
    "nick": "Penguins",
    "loc": "Pittsburgh",
    "primary": "#000000",
    "secondary": "#fcb514",
    "tertiary": "#ffffff"
  },
  "SJS": {
    "name": "San Jose Sharks",
    "nick": "Sharks",
    "loc": "San Jose",
    "primary": "#006d75",
    "secondary": "#ea7200",
    "tertiary": "#000000"
  },
  "SEA": {
    "name": "Seattle Kraken",
    "nick": "Kraken",
    "loc": "Seattle",
    "primary": "#001628",
    "secondary": "#99d9d9",
    "tertiary": "#355464"
  },
  "STL": {
    "name": "St. Louis Blues",
    "nick": "Blues",
    "loc": "St. Louis",
    "primary": "#002f87",
    "secondary": "#fcb514",
    "tertiary": "#ffffff"
  },
  "TBL": {
    "name": "Tampa Bay Lightning",
    "nick": "Lightning",
    "loc": "Tampa Bay",
    "primary": "#002868",
    "secondary": "#ffffff",
    "tertiary": "#000000"
  },
  "TOR": {
    "name": "Toronto Maple Leafs",
    "nick": "Maple Leafs",
    "loc": "Toronto",
    "primary": "#00205b",
    "secondary": "#ffffff",
    "tertiary": "#000000"
  },
  "UTA": {
    "name": "Utah Mammoth",
    "nick": "Mammoth",
    "loc": "Utah",
    "primary": "#71afe5",
    "secondary": "#090909",
    "tertiary": "#ffffff"
  },
  "VAN": {
    "name": "Vancouver Canucks",
    "nick": "Canucks",
    "loc": "Vancouver",
    "primary": "#00205b",
    "secondary": "#00843d",
    "tertiary": "#ffffff"
  },
  "VGK": {
    "name": "Vegas Golden Knights",
    "nick": "Golden Knights",
    "loc": "Vegas",
    "primary": "#b4975a",
    "secondary": "#333f42",
    "tertiary": "#c8102e"
  },
  "WSH": {
    "name": "Washington Capitals",
    "nick": "Capitals",
    "loc": "Washington",
    "primary": "#041e42",
    "secondary": "#c8102e",
    "tertiary": "#ffffff"
  },
  "WPG": {
    "name": "Winnipeg Jets",
    "nick": "Jets",
    "loc": "Winnipeg",
    "primary": "#041e42",
    "secondary": "#004c97",
    "tertiary": "#ac162c"
  }
};
