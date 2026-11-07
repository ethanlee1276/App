// MLB team colors & names (official primary/secondary palettes).
// Kept in a separate dict from the NFL TEAMS because abbreviations collide
// across leagues (CIN, ATL, SF, TB, ...). app.js points window.ACTIVE_TEAMS
// at the right dict for the current sport.
const MLB_TEAMS = {
  "ARI": { "name": "Arizona Diamondbacks", "nick": "D-backs", "loc": "Arizona", "primary": "#a71930", "secondary": "#e3d4ad", "tertiary": "#000000" },
  "ATL": { "name": "Atlanta Braves", "nick": "Braves", "loc": "Atlanta", "primary": "#ce1141", "secondary": "#13274f", "tertiary": "#eaaa00" },
  "BAL": { "name": "Baltimore Orioles", "nick": "Orioles", "loc": "Baltimore", "primary": "#df4601", "secondary": "#000000", "tertiary": "#ffffff" },
  "BOS": { "name": "Boston Red Sox", "nick": "Red Sox", "loc": "Boston", "primary": "#bd3039", "secondary": "#0c2340", "tertiary": "#ffffff" },
  "CHC": { "name": "Chicago Cubs", "nick": "Cubs", "loc": "Chicago", "primary": "#0e3386", "secondary": "#cc3433", "tertiary": "#ffffff" },
  "CWS": { "name": "Chicago White Sox", "nick": "White Sox", "loc": "Chicago", "primary": "#27251f", "secondary": "#c4ced4", "tertiary": "#ffffff" },
  "CIN": { "name": "Cincinnati Reds", "nick": "Reds", "loc": "Cincinnati", "primary": "#c6011f", "secondary": "#000000", "tertiary": "#ffffff" },
  "CLE": { "name": "Cleveland Guardians", "nick": "Guardians", "loc": "Cleveland", "primary": "#e31937", "secondary": "#0c2340", "tertiary": "#ffffff" },
  "COL": { "name": "Colorado Rockies", "nick": "Rockies", "loc": "Colorado", "primary": "#33006f", "secondary": "#c4ced4", "tertiary": "#000000" },
  "DET": { "name": "Detroit Tigers", "nick": "Tigers", "loc": "Detroit", "primary": "#0c2340", "secondary": "#fa4616", "tertiary": "#ffffff" },
  "HOU": { "name": "Houston Astros", "nick": "Astros", "loc": "Houston", "primary": "#002d62", "secondary": "#eb6e1f", "tertiary": "#f4911e" },
  "KC": { "name": "Kansas City Royals", "nick": "Royals", "loc": "Kansas City", "primary": "#004687", "secondary": "#bd9b60", "tertiary": "#ffffff" },
  "LAA": { "name": "Los Angeles Angels", "nick": "Angels", "loc": "Los Angeles", "primary": "#ba0021", "secondary": "#003263", "tertiary": "#c4ced4" },
  "LAD": { "name": "Los Angeles Dodgers", "nick": "Dodgers", "loc": "Los Angeles", "primary": "#005a9c", "secondary": "#a5acaf", "tertiary": "#ef3e42" },
  "MIA": { "name": "Miami Marlins", "nick": "Marlins", "loc": "Miami", "primary": "#00a3e0", "secondary": "#ef3340", "tertiary": "#000000" },
  "MIL": { "name": "Milwaukee Brewers", "nick": "Brewers", "loc": "Milwaukee", "primary": "#12284b", "secondary": "#ffc52f", "tertiary": "#ffffff" },
  "MIN": { "name": "Minnesota Twins", "nick": "Twins", "loc": "Minnesota", "primary": "#002b5c", "secondary": "#d31145", "tertiary": "#cfab7a" },
  "NYM": { "name": "New York Mets", "nick": "Mets", "loc": "New York", "primary": "#002d72", "secondary": "#ff5910", "tertiary": "#ffffff" },
  "NYY": { "name": "New York Yankees", "nick": "Yankees", "loc": "New York", "primary": "#0c2340", "secondary": "#c4ced4", "tertiary": "#ffffff" },
  "OAK": { "name": "Oakland Athletics", "nick": "Athletics", "loc": "Oakland", "primary": "#003831", "secondary": "#efb21e", "tertiary": "#ffffff" },
  "PHI": { "name": "Philadelphia Phillies", "nick": "Phillies", "loc": "Philadelphia", "primary": "#e81828", "secondary": "#002d72", "tertiary": "#ffffff" },
  "PIT": { "name": "Pittsburgh Pirates", "nick": "Pirates", "loc": "Pittsburgh", "primary": "#27251f", "secondary": "#fdb827", "tertiary": "#ffffff" },
  "SD": { "name": "San Diego Padres", "nick": "Padres", "loc": "San Diego", "primary": "#2f241d", "secondary": "#ffc425", "tertiary": "#ffffff" },
  "SF": { "name": "San Francisco Giants", "nick": "Giants", "loc": "San Francisco", "primary": "#fd5a1e", "secondary": "#27251f", "tertiary": "#efd19f" },
  "SEA": { "name": "Seattle Mariners", "nick": "Mariners", "loc": "Seattle", "primary": "#0c2c56", "secondary": "#005c5c", "tertiary": "#c4ced4" },
  "STL": { "name": "St. Louis Cardinals", "nick": "Cardinals", "loc": "St. Louis", "primary": "#c41e3a", "secondary": "#0c2340", "tertiary": "#fedb00" },
  "TBR": { "name": "Tampa Bay Rays", "nick": "Rays", "loc": "Tampa Bay", "primary": "#092c5c", "secondary": "#8fbce6", "tertiary": "#f5d130" },
  "TEX": { "name": "Texas Rangers", "nick": "Rangers", "loc": "Texas", "primary": "#003278", "secondary": "#c0111f", "tertiary": "#ffffff" },
  "TOR": { "name": "Toronto Blue Jays", "nick": "Blue Jays", "loc": "Toronto", "primary": "#134a8e", "secondary": "#1d2d5c", "tertiary": "#e8291c" },
  "WSH": { "name": "Washington Nationals", "nick": "Nationals", "loc": "Washington", "primary": "#ab0003", "secondary": "#14225a", "tertiary": "#ffffff" }
};
