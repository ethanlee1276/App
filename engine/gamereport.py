"""The game report: every NFL game written out top to bottom, the way a reader reads it.

Ethan, 2026-10-19, of the outside research reports he had been pasting in
all season (Bucs @ Cowboys, Bills @ Rams and the rest): "I want our board
too kinda look like that when you click on a game. I want a full layed out
detailed explanation for every nfl game just like how the report is. Obv
keep out the prop picks but everything else it valuable information too
have typed out so the user can just read it."

WHAT IT IS. One report per game, built at the end of the NFL build from
what the board already holds, in the outside reports' order:

  short       The short version: the line, where the edges are, the soft
              spots, who could shine, who is out, the schedule, the sim
  changes     What changed since the report was first written: the line,
              the injury report, the forecast, the reads (engine/reportlog)
  facts       Kickoff, venue, records and recent results, head coaches,
              coordinator changes, rest, division
  meetings    When they last met: the scores, and the lines they were
              played at
  market      The spread, total and moneyline, what they imply, where they
              opened, the prediction markets and their money, our sim
  rankings    Both offenses against the other defense, rank by rank, and
              this season's scoreboard numbers
  identity    How each team plays: run rate, play action, motion, the
              target tree and the backfield; the coverage, the blitz, the box
  injuries    Who is out or questionable and what it opens; pulled props,
              a starting line down, a quarterback change, a traded player
  matchups    Who's guarding who: a verdict on every key player, the soft
              corner, and where each defense leaks and where it holds
  trenches    Pass rush against protection; the run game against the front
  redzone     Touchdown rates both ways, trips, and who gets the chances
  context     Coaching and the schedule: rest, travel, body clock, prime
              time, division rematch, surface, altitude, the standings
  scripts     How the game could go: the script and the simulator's spread
              of outcomes
  watch       Players to watch: who could shine and who could struggle
  weather     Weather and venue
  before      Before kickoff: what to confirm and what would change this

WHAT IT IS NOT. No prop picks, as asked: no line, no price and no
probability on any player — not the scan's microscope, not the game plan's
plays, not a read's leaning markets. Three exceptions, each Ethan's own ask:
each game's parlays (`sec_parlays`, 2026-11-14), each read's own pick on its
side beside the read (`read_pick`, 2026-11-14: "it would not make any sense
to make players favoitable and breakout canidates and not give them
props"), and each team's touchdown chances ranked with their prices
(`td_chance_lines`, 2026-11-15: build his NFL Bet checking reports' way into
these — his reports rank who can score, with the chance and the price, next
to what the defense allows the position). The game
lines and the drive simulator's shares are the game's, and the report
says the simulator is a simulation, not a pick.

EVERY NUMBER IS THE BOARD'S. Nothing here is fetched or estimated: a
section whose inputs are missing is left out, and a sentence whose number
is missing is not written. The scan's units, corners, scheme, charting,
rush, red zone and season numbers (engine/gamescan); the reads and their
usage (`scan_reads`, paid); the game plan's script (`game_plans`); the
drive simulator (`g["sim"]`, engine/drivesim); the crowd and the money
(`g["crowd"]`, `g["money"]`); the opener (`g["line_open"]`); rest and
travel (`fatigue`); the standings (`playoff_picture`); recent results
(`team_recent`); quarterback changes (`qb_changes`); the defense-vs-
position ratings the props were priced against (the slate's
`defense.ratings`, passed in as ``allowed``); and the head coaches and
division from nflverse's cached schedule (engine/spots).

AND WHAT THE BOARD DOES NOT CARRY (Ethan, 2026-10-20: "I want you too
do all of it besides D"), read once per build by engine/reportdata and
this build's ideas file (engine/ideas): every key player's season and
last three games with his red-zone work (the game logs); the teams' last
meetings with the lines they were played at (the schedule file); the
practice report and how often a questionable man plays
(engine/practice); the role changes the detector sees (engine/
rolechange); the kicking air (engine/kickphysics); and the tempo,
turnovers and coaching calls off play-by-play (gamescan.season_numbers).

IT IS PAID. The reads are the paid half of the scan, so the reports ride
under their own top-level key, `game_reports`, on engine/gate.PAID_KEYS —
the paywall's strip does not descend into the rows of `games`.

Standard library only. Never raises out of `attach`.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

#: The board key the reports ride under (engine/gate.PAID_KEYS).
KEY = "game_reports"

#: Reading speed for the "about N minutes" line.
WORDS_A_MINUTE = 230

#: A rank gap this wide or wider is an edge — engine/gamescan's own bar
#: (max(EDGE_GAP, 30% of the league)), so the report and the scan agree.
EDGE_SHARE = 0.3

#: Who counts as a key player for the verdicts: the starting quarterback,
#: a back with this share of the carries, a receiver with this share of
#: the targets (engine/gamescan.key_players' floors).
KEY_CARRY_SHARE, KEY_TARGET_SHARE = 0.25, 0.12

#: A target tree lists receivers with this share or more; a backfield,
#: backs with this share of the carries or more.
TREE_SHARE, BACKFIELD_SHARE = 0.10, 0.10

#: WHO GETS THE BALL, IN COLOUR (Ethan, 2026-11-15, circling DET's "who gets
#: the ball thrown to him" line: "when we talk about player that get the
#: ball, we can make the letters of there name green or red depending on in
#: they are a breakout or favorite candidate or a unfavorable matchup"). A
#: named player's tone and words, from his matchup read in this game
#: (engine/gamescan.READS); js/report.js colours the name and opens his page.
NAME_TONE = {"breakout": ("up", "Breakout candidate"), "good": ("up", "Favorable matchup"),
             "neutral": ("", "Neutral matchup"), "tough": ("down", "Unfavorable matchup"),
             "avoid": ("down", "Unfavorable matchup — avoid")}

#: Where a defense leaks or holds against a position: a rank this close
#: to either end of the league (rank 1 gives up the most).
FUNNEL_RANKS = 6

#: The verdict words, from the scan's read (engine/gamescan.READS).
VERDICT = {"breakout": ("favorable", "FAVORABLE — breakout candidate"),
           "good": ("favorable", "FAVORABLE"),
           "neutral": ("neutral", "NEUTRAL"),
           "tough": ("unfavorable", "UNFAVORABLE"),
           "avoid": ("unfavorable", "UNFAVORABLE — avoid")}

#: Inactives post this long before kickoff.
INACTIVES_BEFORE_MIN = 90

#: The officials line, once: what refcheck.py measured (2026-10-17).
OFFICIALS = ("Officials: the referee is named late in the week. We tested 7,340 games, and the referee "
             "told us nothing the closing line didn't already, so the crew isn't part of this report.")

#: The rankings tables' rows: (unit, label, how the value prints). Short
#: labels — four columns have to fit a phone — with the long meanings in
#: the table's note (UNIT_NOTE).
UNIT_ROWS = (
    ("overall", "EPA a play", "epa"),
    ("passing", "Pass EPA", "epa"),
    ("rushing", "Rush EPA", "epa"),
    ("success", "Success rate", "pct"),
    ("explosive", "Big-play rate", "pct1"),
    ("pressure", "Pressure", "pct"),
    ("ypc", "Yards a carry", "num1"),
    ("third_down", "3rd-down rate", "pct"),
    ("redzone", "Red-zone TD%", "pct"),
    ("short", "Short throws", "num1"),
    ("mid", "Mid throws", "num1"),
    ("deep", "Deep throws", "num1"),
    # College's own (engine/gamescan.CFB_UNITS; the NFL has none of them).
    ("havoc", "Havoc rate", "pct1"),
    ("line", "Line yards", "num1"),
    ("stuff", "Stuff rate", "pct"),
)
CFB_UNIT_NOTE = ("EPA is expected points added a play (CFBD's PPA). Havoc is the share of plays that end in "
                 "a tackle for a loss, a sack, a takeaway or a pass defended; line yards credit the blockers "
                 "for a run's first yards; the stuff rate is runs stopped at or behind the line. Each cell shows "
                 "the number and its rank (1st is best). The Edge column names the side with a clear advantage.")
UNIT_NOTE = ("EPA is expected points added a play. Pressure is the rate the offense allows and the "
             "defense gets home. Throws are yards a target: short under 10 air yards, mid 10–19, "
             "deep 20+. Each cell shows the number and its rank (1st is best). The Edge column names the "
             "side with a clear advantage.")

#: This season's counting numbers (gamescan.season_numbers): (key, label,
#: how it prints).
NUMBER_ROWS = (
    ("pts_for", "Points a game", "num1"),
    ("pts_against", "Points allowed", "num1"),
    ("third_off", "3rd-down rate", "pct"),
    ("third_def", "3rd-down rate allowed", "pct"),
    ("rz_off", "Red-zone TD%", "pct"),
    ("rz_def", "Red-zone TD% allowed", "pct"),
    ("rush_allowed", "Rush yards allowed", "num1"),
    ("ypc_allowed", "Yards a carry allowed", "num1"),
    ("sacks", "Sacks a game", "num1"),
    ("run_rate", "Run rate", "pct"),
    ("giveaways", "Giveaways a game", "num1"),
    ("takeaways", "Takeaways a game", "num1"),
    ("to_margin", "Turnover margin", "signed0"),
)

#: Who a player's form line counts as (his position on the read).
FORM_GROUPS = {"QB": "qb", "RB": "rb", "FB": "rb", "WR": "rec", "TE": "rec"}

#: A form line says a player is running hot or cold when his last three
#: games' main number sits this far from the rest of his season (a share
#: of it, and at least the yards beside it), with two or more other games.
FORM_TREND_SHARE = 0.25
FORM_TREND_YDS = {"qb": 40.0, "rb": 15.0, "rec": 15.0}

#: The ideas file's sections the report reads (engine/ideas).
IDEAS = ("practice", "role", "kicks")

#: The defense-vs-position stats a funnel reads (engine/defensevs.STATS),
#: grouped by who they are about.
FUNNEL_GROUPS = (
    ("wide receivers", ("wr_rec_yds", "wr_rec", "wr_td")),
    ("tight ends", ("te_rec_yds", "te_rec", "te_td")),
    ("running backs on the ground", ("rb_rush_yds", "rb_td")),
    ("running backs as receivers", ("rb_rec_yds", "rb_rec")),
    ("quarterbacks passing", ("qb_pass_yds", "qb_pass_td")),
    ("quarterbacks running", ("qb_rush_yds",)),
)
FUNNEL_WORDS = {"wr_rec_yds": "receiving yards", "wr_rec": "catches", "wr_td": "touchdowns",
                "te_rec_yds": "receiving yards", "te_rec": "catches", "te_td": "touchdowns",
                "rb_rush_yds": "rushing yards", "rb_td": "touchdowns",
                "rb_rec_yds": "receiving yards", "rb_rec": "catches",
                "qb_pass_yds": "passing yards", "qb_pass_td": "passing touchdowns",
                "qb_rush_yds": "rushing yards"}

#: Who a funnel's yards go to, said after "gives up the most … to".
FUNNEL_TO = {"running backs on the ground": "running backs on the ground",
             "running backs as receivers": "running backs as receivers",
             "quarterbacks passing": "quarterbacks", "quarterbacks running": "quarterbacks on the run"}

SHELL_WORDS = {"COVER_0": "Cover 0", "COVER_1": "Cover 1", "COVER_2": "Cover 2",
               "COVER_3": "Cover 3", "COVER_4": "Cover 4 (quarters)", "COVER_6": "Cover 6",
               "2_MAN": "two-man", "COVER_9": "Cover 9", "PREVENT": "prevent"}


# --- small words ----------------------------------------------------------------------
def _ord(n) -> str:
    n = int(n)
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _num(x, nd: int = 1) -> str:
    """12.0 → "12", 3.40 → "3.4": a figure as a person writes it."""
    v = _f(x)
    if v is None:
        return ""
    s = f"{v + 0.0 if round(v, nd) else 0.0:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _pct(x, nd: int = 0) -> str:
    v = _f(x)
    if v is None:
        return ""
    return f"{v * 100 if round(v * 100, nd) else 0.0:.{nd}f}%"


def a_pct(x, nd: int = 0) -> str:
    """"a 60%", "an 85%" — the article a percentage is read with (eight,
    eleven, eighteen and the eighties take "an")."""
    s = _pct(x, nd)
    return f"{'an' if s.startswith('8') or s.split('%')[0] in ('11', '18') else 'a'} {s}"


def _minus(s: str) -> str:
    """The true minus sign, the way the site prints a negative (trueMinus)."""
    return str(s).replace("-", "\u2212")


def _signed(x, nd: int = 2) -> str:
    """+0.19 / −0.18, and 0.00 for a figure that rounds to nothing: a sign
    on zero ("−0.00", "+0.00") reads as a fault."""
    v = _f(x)
    if v is None:
        return ""
    s = f"{v:+.{nd}f}"
    return s[1:] if float(s) == 0 else _minus(s)


def _fmt(x, how: str) -> str:
    """A table cell's figure: fixed decimals, so a column lines up."""
    v = _f(x)
    if v is None:
        return ""
    return {"epa": lambda: _signed(v, 2), "pct": lambda: _pct(v),
            "pct1": lambda: _pct(v, 1), "num1": lambda: f"{v:.1f}",
            "signed0": lambda: _signed(v, 0)}[how]()


def _odds(x) -> str:
    v = _f(x)
    if v is None or v == 0:
        return ""
    return _minus(f"{int(round(v)):+d}")


#: The heaviest price a pick is ever worth taking at (the board's cap;
#: Ethan's method: "Never recommend a leg worse than -250").
TAKE_CAP = -250


def take_at(prob) -> str:
    """The price a pick is worth taking at — "−163 or better" — from our
    chance (its fair price), never heavier than TAKE_CAP: the method's
    "maximum playable price" on every pick (Ethan's NFL Bet checking
    project, rule 21). "" without a chance."""
    p = _f(prob)
    if p is None or not 0.0 < p < 1.0:
        return ""
    fair = -100.0 * p / (1.0 - p) if p >= 0.5 else 100.0 * (1.0 - p) / p
    return f"{_odds(max(fair, TAKE_CAP))} or better"


def _implied(x):
    """American odds → the chance they imply, vig included."""
    v = _f(x)
    if v is None or v == 0:
        return None
    return (-v) / (-v + 100.0) if v < 0 else 100.0 / (v + 100.0)


def _join(items, last: str = "and") -> str:
    items = [str(i) for i in items if i]
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} {last} {items[-1]}"


def _plural(n, one: str, many: str | None = None) -> str:
    return f"{_num(n, 1)} {one if float(n) == 1 else (many or one + 's')}"


def _sentence(text: str) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    return text if text[-1] in ".!?" else text + "."


def _team_names() -> dict:
    """{abbr: nickname} off the Odds API's full names ("Detroit Lions" →
    "Lions"); {} when that table cannot be read — the abbreviation stands."""
    try:
        from .sources.oddsapi import TEAM_ABBR
    except Exception:                                        # noqa: BLE001
        return {}
    return {abbr: full.rsplit(" ", 1)[-1] for full, abbr in TEAM_ABBR.items()}


# --- the context every section reads --------------------------------------------------
def _season_of(result: dict, g: dict | None = None) -> int:
    """The NFL season a board is for: its date ("2026-W7"), else the game's
    (a January game belongs to the season before)."""
    for d in (str((result or {}).get("date") or ""), str((g or {}).get("date") or "")):
        try:
            y = int(d[:4])
        except ValueError:
            continue
        return y - 1 if "-W" not in d and d[5:7] in ("01", "02") else y
    return _dt.date.today().year


def _week_of(result: dict) -> int | None:
    """The NFL week a board is for, off its date ("2026-W07"); None when
    the date is a day (a mid-week rebuild reads every week played)."""
    d = str((result or {}).get("date") or "")
    try:
        return int(d.split("-W", 1)[1]) if "-W" in d else None
    except ValueError:
        return None


class Ctx:
    """One game and everything on the board about it."""

    def __init__(self, g: dict, result: dict, allowed: dict | None = None,
                 sched=None, staff: dict | None = None, names: dict | None = None,
                 form: dict | None = None, meetings: list | None = None, ideas: dict | None = None,
                 sport: str = "nfl", meta: dict | None = None, changes: dict | None = None,
                 grades: dict | None = None, angles: dict | None = None):
        self.g = g
        # This season's leak tables (engine/angles.nfl_tables), the NFL's.
        self.angle_tables = angles or {}
        # Our grades (engine/grades), the NFL's: {kind: {(team, name): grade}}.
        self.grades = grades or {}
        self.sport = sport
        # What a game is scored in: "point(s)", "run(s)", "goal(s)".
        self.score_word = {"mlb": "run", "nhl": "goal"}.get(sport, "point")
        self.score_words = self.score_word + "s"
        # What moved since the report was first written (engine/reportlog).
        self.changes = changes
        # What the build knows about the game and the board leaves off
        # (college: neutral site, conference game, week).
        self.meta = meta or {}
        self.form = form or {}
        self.meetings = meetings or []
        self.ideas = ideas or {}
        self.season = _season_of(result, g)
        self.result = result or {}
        self.away, self.home = str(g.get("away") or ""), str(g.get("home") or "")
        self.teams = (self.away, self.home)
        self.opp = {self.away: self.home, self.home: self.away}
        self.scan = g.get("scan") or {}
        self.units = self.scan.get("units") or {}
        reads = (self.result.get("scan_reads") or {}).get(f"{self.away}@{self.home}") or {}
        self.reads = [r for r in reads.get("players") or [] if isinstance(r, dict)]
        self.plan = next((p for p in self.result.get("game_plans") or []
                          if isinstance(p, dict) and p.get("away") == self.away
                          and p.get("home") == self.home), None) or {}
        self.allowed = allowed or {}
        self.sched = sched
        self.staff = staff or {}
        self.names = names if names is not None else _team_names()
        n_teams = int((self.scan.get("method") or {}).get("teams") or self.scan.get("n_teams") or 32)
        self.n_teams = n_teams
        try:
            from .gamescan import EDGE_GAP
        except Exception:                                    # noqa: BLE001
            EDGE_GAP = 10
        self.gap_bar = max(EDGE_GAP, round(n_teams * EDGE_SHARE))
        self.sched_row = self._sched_row()
        # WHO MAY NOT PLAY (engine/availability, 2026-11-14; Ethan: an injured
        # player was still "could have a big day", in every sport). A man
        # ruled out or doubtful has no read on the page; a questionable one,
        # or one with no line in his team's last game, keeps his read,
        # marked, and stays out of the short version.
        try:
            from .availability import annotate
            self.reads = annotate(self)
        except Exception:                                    # noqa: BLE001
            pass

    def name(self, team: str) -> str:
        return self.names.get(team, team)

    def poss(self, team: str) -> str:
        """The team's possessive: most nicknames are plural ("Lions'")."""
        n = self.name(team)
        return f"{n}'" if n.endswith("s") else f"{n}'s"

    def unit(self, team: str, side: str, unit: str) -> dict:
        return ((self.units.get(team) or {}).get(side) or {}).get(unit) or {}

    def rank(self, team: str, side: str, unit: str):
        return self.unit(team, side, unit).get("rank")

    def reads_for(self, team: str) -> list:
        return [r for r in self.reads if r.get("team") == team]

    def _sched_row(self):
        if self.sched is None:
            return None
        try:
            return self.sched.game(home=self.home, away=self.away, day=self.g.get("date"))
        except Exception:                                    # noqa: BLE001
            return None


def _usage(r: dict) -> dict:
    return r.get("usage") or {}


def _is_key(r: dict) -> bool:
    pos = str(r.get("pos") or "").upper()
    u = _usage(r)
    if pos == "QB":
        return (u.get("snap_pct") or 0) >= 0.5
    if pos in ("RB", "FB"):
        return (u.get("carry_share") or 0) >= KEY_CARRY_SHARE
    if pos in ("WR", "TE"):
        return (u.get("tgt_share") or 0) >= KEY_TARGET_SHARE
    return False


def _volume(r: dict) -> float:
    u = _usage(r)
    return max(float(u.get("tgt_share") or 0), float(u.get("carry_share") or 0),
               1.0 if str(r.get("pos") or "").upper() == "QB" else 0.0)


def _caught(u: dict) -> tuple:
    """("targets", per game) — or ("catches", per game) where the share is
    of the catches (college logs no targets: engine/gamescan.cfb_usage)."""
    if u.get("share_of") == "catches":
        return "catches", u.get("rec_pg")
    return "targets", u.get("targets_pg")


def _role_line(r: dict) -> str:
    """"31% of the targets (10.8 a game)" — his work, in one phrase."""
    u = _usage(r)
    pos = str(r.get("pos") or "").upper()
    word, per = _caught(u)
    if pos in ("RB", "FB") and u.get("carry_share"):
        bits = [f"{_pct(u['carry_share'])} of the carries ({_num(u.get('carries_pg'))} a game)"]
        if (u.get("tgt_share") or 0) >= 0.08:
            bits.append(f"{_pct(u['tgt_share'])} of the {word}")
        return ", ".join(bits)
    if pos in ("WR", "TE") and u.get("tgt_share"):
        return f"{_pct(u['tgt_share'])} of the {word} ({_num(per)} a game)"
    if pos == "QB":
        # A QUARTERBACK'S WORK, his legs with it when he runs (Ethan,
        # 2026-11-12: "we should have QB rushing yards in the matchup report
        # as well"; engine/gamescan.QB_RUNS_CARRIES).
        from .gamescan import QB_RUNS_CARRIES, QB_RUNS_YDS
        bits = [f"{_num(u['attempts_pg'])} pass attempts a game"] if u.get("attempts_pg") else []
        cpg, ypg = float(u.get("carries_pg") or 0), float(u.get("rush_yds_pg") or 0)
        if cpg >= QB_RUNS_CARRIES or ypg >= QB_RUNS_YDS:
            bits.append(f"{_num(cpg)} carries for {_num(ypg, 0)} rushing yards a game")
        return ", ".join(bits)
    return ""


# --- a player's form (engine/reportdata.player_form) ---------------------------------
#: nflverse's week numbers past the regular season, by its length.
PLAYOFF_WEEKS = {19: "wild-card round", 20: "divisional round", 21: "conference title game",
                 22: "Super Bowl"}


def _n(x) -> int:
    return int(round(float(x or 0)))


def _count(n, one: str, many: str | None = None) -> str:
    n = _n(n)
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def day_label(day: str, season: int, current: int) -> str:
    """College's games go by their date: "Oct. 18", or "Jan. 20, 2026"
    for a game of another season (a bowl in January belongs to the one
    before it)."""
    try:
        d = _dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return str(day)
    return f"{d.strftime('%b')}. {d.day}" + ("" if int(season) == int(current) else f", {d.year}")


def week_label(season: int, week: int, current: int) -> str:
    """"Wk 5" this season; "2025 wk 13" or "2025 wild-card round" before."""
    reg = 18 if int(season) >= 2021 else 17
    if int(week) > reg:
        name = PLAYOFF_WEEKS.get(int(week) + (1 if reg == 17 else 0), "playoffs")
        return f"{season} {name}"
    return f"Wk {week}" if int(season) == int(current) else f"{season} wk {week}"


def form_game(group: str, g: dict) -> str:
    """One game's line, in a box score's words."""
    s = g.get("s") or {}
    bits = []
    if group == "qb":
        if s.get("pass_att") and "pass_cmp" in s:
            bits.append(f"{_n(s.get('pass_cmp'))} of {_n(s['pass_att'])}, {_count(s.get('pass_yds'), 'yd')}")
        else:
            bits.append(f"{_count(s.get('pass_att'), 'attempt')}, {_count(s.get('pass_yds'), 'yd')}"
                        if s.get("pass_att") else _count(s.get("pass_yds"), "yd"))
        bits.append(f"{_n(s.get('pass_td'))} TD" + (f", {_n(s.get('pass_int'))} INT" if "pass_int" in s else ""))
        if (s.get("rush_yds") or 0) >= 15 or s.get("rush_td"):
            car = s.get("rush_att") if s.get("rush_att") is not None else s.get("carries")
            bits.append((f"{_count(car, 'carry', 'carries')} for " if car else "")
                        + f"{_count(s.get('rush_yds'), 'rush yd')}"
                        + (f", {_n(s['rush_td'])} rush TD" if s.get("rush_td") else ""))
        return ", ".join(bits)
    if group == "rb":
        run = f"{_count(s.get('rush_att'), 'carry', 'carries')}, {_count(s.get('rush_yds'), 'yd')}"
        if s.get("rush_td"):
            run += f", {_n(s['rush_td'])} TD"
        out = run
        if s.get("receptions") or s.get("targets"):
            out += (f"; {_count(s.get('receptions'), 'catch', 'catches')}, {_count(s.get('rec_yds'), 'yd')}"
                    + (f", {_n(s['rec_td'])} TD" if s.get("rec_td") else ""))
        return out
    out = (f"{_count(s.get('receptions'), 'catch', 'catches')}"
           + (f" on {_count(s.get('targets'), 'target')}" if "targets" in s else "")
           + f", {_count(s.get('rec_yds'), 'yd')}")
    if s.get("rec_td"):
        out += f", {_n(s['rec_td'])} TD"
    return out


def form_season(group: str, t: dict) -> str:
    """A season's totals: "5 games: 98 carries, 512 yds (5.2 a carry) ..."."""
    s, n = t.get("s") or {}, int(t.get("games") or 0)
    if not n:
        return ""
    head = f"{_count(n, 'game')}: "
    if group == "qb":
        bits = [f"{_count(s.get('pass_yds'), 'yd')} ({_num((s.get('pass_yds') or 0) / n, 0)} a game)"]
        if s.get("pass_att") and "pass_cmp" in s:
            bits.append(f"{_pct((s.get('pass_cmp') or 0) / s['pass_att'])} completed")
        bits.append(f"{_n(s.get('pass_td'))} TD" + (f", {_n(s.get('pass_int'))} INT" if "pass_int" in s else ""))
        if (s.get("rush_yds") or 0) >= 50 or (s.get("rush_td") or 0) >= 2:
            car = s.get("rush_att") if s.get("rush_att") is not None else s.get("carries")
            bits.append((f"{_count(car, 'carry', 'carries')} for " if car else "")
                        + f"{_count(s.get('rush_yds'), 'rushing yd')}"
                        + (f" ({_num(s['rush_yds'] / n, 0)} a game)" if n else "")
                        + (f", {_n(s['rush_td'])} rushing TD" if s.get("rush_td") else ""))
        return head + ", ".join(bits)
    if group == "rb":
        out = f"{_count(s.get('rush_att'), 'carry', 'carries')}, {_count(s.get('rush_yds'), 'yd')}"
        if s.get("rush_att"):
            out += f" ({_num(s['rush_yds'] / s['rush_att'], 1)} a carry)"
        if s.get("rush_td"):
            out += f", {_n(s['rush_td'])} TD"
        if s.get("receptions"):
            out += (f"; {_count(s['receptions'], 'catch', 'catches')}, {_count(s.get('rec_yds'), 'yd')}"
                    + (f", {_n(s['rec_td'])} TD" if s.get("rec_td") else ""))
        return head + out
    out = (f"{_count(s.get('receptions'), 'catch', 'catches')}"
           + (f" on {_count(s.get('targets'), 'target')}" if "targets" in s else "")
           + f", {_count(s.get('rec_yds'), 'yd')} ({_num((s.get('rec_yds') or 0) / n, 0)} a game)")
    if s.get("rec_td"):
        out += f", {_n(s['rec_td'])} TD"
    return head + out


def _main_yds(group: str, s: dict) -> float:
    if group == "qb":
        return float(s.get("pass_yds") or 0)
    if group == "rb":
        return float(s.get("rush_yds") or 0) + float(s.get("rec_yds") or 0)
    return float(s.get("rec_yds") or 0)


MAIN_WORDS = {"qb": "passing yards", "rb": "yards from scrimmage", "rec": "receiving yards"}

#: A quarterback's red-zone carries are said from this many: two sneaks
#: are not a role.
QB_RZ_CARRIES = 4


def form_trend(group: str, f: dict, season: int) -> str:
    """"112 receiving yards a game over his last 3, up from 64 in his other
    3" — only when the gap clears FORM_TREND_SHARE and the yards."""
    t = f.get("season") or {}
    last = [g for g in f.get("games") or [] if g.get("season") == season]
    n_all = int(t.get("games") or 0)
    if len(last) < 3 or n_all - len(last) < 2:
        return ""
    recent = sum(_main_yds(group, g.get("s") or {}) for g in last) / len(last)
    total = _main_yds(group, t.get("s") or {})
    rest = (total - recent * len(last)) / (n_all - len(last))
    gap = recent - rest
    if abs(gap) < FORM_TREND_YDS[group] or abs(gap) < FORM_TREND_SHARE * max(rest, 1.0):
        return ""
    return (f"{_num(recent, 0)} {MAIN_WORDS[group]} a game over his last {len(last)}, "
            f"{'up' if gap > 0 else 'down'} from {_num(rest, 0)} in his other {n_all - len(last)}")


def form_rz(group: str, rz: dict) -> str:
    """His work inside the 20 this season, and his share of his team's."""
    if not rz:
        return ""
    team = rz.get("team") or ""
    bits = []
    car, tgt = _n(rz.get("rz_car")), _n(rz.get("rz_tgt"))
    if car >= {"rb": 1, "qb": QB_RZ_CARRIES}.get(group, 2):
        share = car / rz["team_rz_car"] if rz.get("team_rz_car") else None
        bits.append(f"{_count(car, 'carry', 'carries')} inside the 20 ({_n(rz.get('i5_car'))} inside the 5)"
                    + (f" — {_pct(share)} of {team}'s" if share else ""))
    if tgt and group != "qb":
        share = tgt / rz["team_rz_tgt"] if rz.get("team_rz_tgt") else None
        bits.append(f"{_count(tgt, 'target')} inside the 20 ({_n(rz.get('i10_tgt'))} inside the 10)"
                    + (f" — {_pct(share)} of {team}'s" if share else ""))
    rec = _n(rz.get("rz_rec"))
    if rec and group != "qb":
        share = rec / rz["team_rz_rec"] if rz.get("team_rz_rec") else None
        bits.append(f"{_count(rec, 'catch', 'catches')} inside the 20"
                    + (f" — {_pct(share)} of {team}'s" if share else ""))
    if not bits:
        caught = "catches" if "rz_rec" in rz else "targets"
        return f"No carries or {caught} inside the 20 this season" if group in ("rb", "rec") else ""
    return "; ".join(bits)


#: A board market and the logged numbers it settles on (a touchdown is
#: either kind).
HIT_MARKETS = {"receptions": ("receptions",), "rec_yds": ("rec_yds",), "rush_yds": ("rush_yds",),
               "rush_att": ("rush_att",), "pass_yds": ("pass_yds",), "pass_cmp": ("pass_cmp",),
               "pass_att": ("pass_att",), "pass_td": ("pass_td",), "anytime_td": ("rec_td", "rush_td"),
               "rush_rec_yds": ("rush_yds", "rec_yds"), "pass_rush_yds": ("pass_yds", "rush_yds")}
HIT_WORDS = {"receptions": "catches", "rec_yds": "receiving yards", "rush_yds": "rushing yards",
             "rush_att": "carries", "pass_yds": "passing yards", "pass_cmp": "completions",
             "pass_att": "pass attempts", "pass_td": "passing touchdowns", "anytime_td": "a touchdown",
             "rush_rec_yds": "rushing and receiving yards", "pass_rush_yds": "passing and rushing yards"}
#: His last games a hit line counts beside the season.
HIT_RECENT = 5


def _board_lines(c: "Ctx", player: str) -> list:
    """(market, side, line) for each number the board posts on him: its Most
    Likely picks and its Edge picks, once each."""
    out, seen = [], set()
    for k in ("most_likely", "recommendations"):
        for row in c.result.get(k) or []:
            if not isinstance(row, dict) or row.get("player") != player:
                continue
            if k == "recommendations" and not row.get("recommended"):
                continue
            mk, line = row.get("market"), row.get("line")
            side = str(row.get("side") or "").upper()
            side = "OVER" if side in ("YES", "Y") else side
            if mk not in HIT_MARKETS or line is None or side not in ("OVER", "UNDER"):
                continue
            key = (mk, side, float(line))
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out


def hit_lines(c: "Ctx", r: dict) -> list:
    """"Over 46.5 receiving yards: 5 of 8 games this season, 4 of his last
    5" — for each number the board posts on him, how often his own games
    cleared it (Ethan's reports: "SBR has him over 46.5 in 62% of games")."""
    log = (c.form.get(r.get("player")) or {}).get("log") or []
    if len(log) < 3:
        return []
    out = []
    for mk, side, line in _board_lines(c, r.get("player")):
        vals = [sum(float((g.get("s") or {}).get(m) or 0.0) for m in HIT_MARKETS[mk]) for g in log]
        hit = [(v > line) if side == "OVER" else (v < line) for v in vals]
        recent = hit[:HIT_RECENT]
        what = ("Scored" if mk == "anytime_td" and side == "OVER" else
                f"{'Over' if side == 'OVER' else 'Under'} {line:g} {HIT_WORDS[mk]}")
        out.append(f"{what}: {sum(hit)} of {len(hit)} games this season"
                   + (f", {sum(recent)} of his last {len(recent)}" if len(hit) > len(recent) else ""))
    return out


def season_log(group: str, log: list) -> str:
    """His season game by game, newest first: "Wk 9 PHI 5-43 (8) · Wk 7 HOU
    7-111" — catches-yards (targets) for a receiver, carries-yards for a
    back, completions/attempts-yards for a quarterback."""
    bits = []
    for g in log[:10]:
        s, wk = g.get("s") or {}, g.get("wk")
        head = (f"Wk {wk}" if isinstance(wk, int) else str(wk or "")[5:]) + (f" {g['opp']}" if g.get("opp") else "")
        if group == "qb":
            line = f"{_n(s.get('pass_cmp'))}/{_n(s.get('pass_att'))}-{_n(s.get('pass_yds'))}"
            if (s.get("rush_yds") or 0) >= 15:
                line += f", {_n(s.get('rush_yds'))} rush"
        elif group == "rb":
            line = f"{_n(s.get('rush_att'))}-{_n(s.get('rush_yds'))}"
            if s.get("receptions"):
                line += f", {_n(s.get('receptions'))}-{_n(s.get('rec_yds'))} rec"
        else:
            line = f"{_n(s.get('receptions'))}-{_n(s.get('rec_yds'))}" + (
                f" ({_n(s.get('targets'))})" if s.get("targets") is not None else "")
        td = _n(s.get("rec_td")) + _n(s.get("rush_td")) + (_n(s.get("pass_td")) if group == "qb" else 0)
        bits.append(f"{head} {line}" + (f", {td} TD" if td else ""))
    return " · ".join(bits)


def form_lines(c: "Ctx", r: dict) -> list:
    """[[label, [lines]]] for the player's card: this season (or last,
    when he has not played in this one), his last three games, a trend
    when there is one, and his red-zone work. [] without his logs."""
    f = c.form.get(r.get("player")) or {}
    group = FORM_GROUPS.get(str(r.get("pos") or "").upper())
    if not f or not group:
        return []
    out = []
    if f.get("season"):
        line = form_season(group, f["season"])
        if line:
            out.append(["This season", [line]])
    elif f.get("last_season"):
        line = form_season(group, f["last_season"])
        if line:
            out.append(["Last season", [line + " — none yet this season"]])
    games = []
    for g in f.get("games") or []:
        opp = g.get("opp") or ""
        when = (week_label(g["season"], g["week"], c.season) if g.get("week") is not None
                else day_label(g.get("day"), g["season"], c.season))
        # College's school codes read poorly; its opponents go by name.
        opp = c.name(opp) if opp and c.sport != "nfl" else opp
        games.append(f"{when} {'at' if g.get('where') == 'away' else 'vs'} {opp}: "
                     f"{form_game(group, g)}".replace(" vs :", ":"))
    if games:
        out.append([f"Last {len(games)}", games])
    trend = form_trend(group, f, c.season)
    if trend:
        out.append(["Lately", [trend]])
    # OUR GRADE (engine/grades): his season against his position's, from
    # free numbers — where the research docs quoted PFF's.
    from .grades import of as _grade_of, words as _grade_words
    graded = _grade_words(_grade_of(c.grades, r.get("team"), r.get("player"), r.get("pos")))
    if graded:
        out.append(["Our grade", [graded]])
    if (f.get("season") or {}).get("games", 0) >= 2:
        rz = form_rz(group, f.get("rz") or {})
        if rz:
            out.append(["Red zone", [rz]])
    # HIS SEASON GAME BY GAME, and how often it clears the board's numbers.
    log = f.get("log") or []
    if len(log) > len(f.get("games") or []):
        line = season_log(group, log)
        if line:
            out.append(["Game log", [line]])
    hits = hit_lines(c, r)
    if hits:
        out.append(["At the board's numbers", hits])
    return out


# --- the sections ---------------------------------------------------------------------
def _p(text):
    text = _sentence(text)
    return {"type": "p", "text": text} if text else None


def _list(items):
    items = [_sentence(i) for i in items if i]
    return {"type": "list", "items": items} if items else None


def name_tones(c: "Ctx", team: str, players) -> dict:
    """{name: {"tone": "up" | "down" | "", "label": words}} for each of
    ``players`` (names, or rows with a "player") who has a read for
    ``team`` in this game (NAME_TONE). A player ruled out or doubtful has
    no read on the page (engine/availability), so his name stays plain."""
    from .availability import _key
    reads = {_key(r.get("player")): r for r in c.reads_for(team) if r.get("player")}
    out = {}
    for p in players or []:
        name = str((p.get("player") if isinstance(p, dict) else p) or "")
        r = reads.get(_key(name)) if name else None
        tone, label = NAME_TONE.get(str((r or {}).get("read") or ""), ("", ""))
        if label:
            out[name] = {"tone": tone, "label": label}
    return out


def _h(text):
    return {"type": "h", "text": text} if text else None


def _section(key: str, title: str, blocks) -> dict | None:
    blocks = [b for b in blocks if b]
    return {"key": key, "title": title, "blocks": blocks} if blocks else None


def kickoff_words(date: str, kickoff: str) -> str:
    """"Sunday, Oct. 25, 4:25 PM ET" from the board's date and ET kickoff —
    or from a UTC stamp, which is how college's feed writes a kickoff."""
    if "T" in str(kickoff or ""):
        try:
            from .sources.cfbdata import to_eastern
            et = to_eastern(str(kickoff))
        except Exception:                                    # noqa: BLE001
            et = None
        if et is None:
            kickoff = ""
        else:
            date, kickoff = et.date().isoformat(), f"{et.hour:02d}:{et.minute:02d}"
    try:
        d = _dt.date.fromisoformat(str(date)[:10])
    except ValueError:
        return ""
    day = f"{d.strftime('%A')}, {d.strftime('%b')}. {d.day}"
    try:
        hh, mm = (int(x) for x in str(kickoff).split(":")[:2])
    except ValueError:
        return day
    return f"{day}, {_clock(hh, mm)} ET"


def _clock(hh: int, mm: int) -> str:
    return f"{(hh % 12) or 12}:{mm:02d} {'PM' if hh >= 12 else 'AM'}"


#: Baseball's and hockey's spread is a fixed line a run or a goal and a
#: half wide, not the expected margin: said by its name, and no team
#: totals are read off it.
FIXED_LINES = {"mlb": "run line", "nhl": "puck line"}


def line_words(c: Ctx) -> str:
    """"DET by 3 at home, total 52.5" — the favorite, the margin, the total;
    "PHI −1.5 on the run line, total 9.5" where the spread is a fixed line."""
    g = c.g
    sp, tot = _f(g.get("spread")), _f(g.get("total"))
    bits = []
    fixed = FIXED_LINES.get(c.sport)
    if sp is not None and fixed:
        if sp:
            fav = c.home if sp < 0 else c.away
            bits.append(f"{fav} −{_num(abs(sp))} on the {fixed}")
    elif sp is not None:
        if sp == 0:
            bits.append("a pick'em")
        else:
            fav = c.home if sp < 0 else c.away
            where = (" (neutral site)" if g.get("neutral_site") else
                     " at home" if fav == c.home else " on the road")
            bits.append(f"{fav} by {_num(abs(sp))}{where}")
    if tot is not None:
        bits.append(f"total {_num(tot)}")
    return ", ".join(bits)


def implied_points(c: Ctx) -> dict:
    """{team: points the spread and total imply}, or {} — and {} where the
    spread is a fixed line (FIXED_LINES), which implies no margin."""
    sp, tot = _f(c.g.get("spread")), _f(c.g.get("total"))
    if sp is None or tot is None or c.sport in FIXED_LINES:
        return {}
    return {c.home: (tot - sp) / 2.0, c.away: (tot + sp) / 2.0}


def ml_chances(c: Ctx) -> dict:
    """{team: the moneyline's chance with the vig taken out}, or {}."""
    ph, pa = _implied(c.g.get("home_ml")), _implied(c.g.get("away_ml"))
    if ph is None or pa is None or ph + pa <= 0:
        return {}
    return {c.home: ph / (ph + pa), c.away: pa / (ph + pa)}


def _edges(c: Ctx) -> list:
    return [e for e in c.scan.get("edges") or [] if isinstance(e, dict)]


def edge_words(c: Ctx, e: dict) -> str:
    """"GB's passing game (4th) against DET's pass defense (22nd) — edge GB"."""
    unit = e.get("unit")
    off_w, def_w = {
        "passing": ("passing game", "pass defense"), "rushing": ("run game", "run defense"),
        "explosive": ("big-play offense", "big-play defense"),
        "pressure": ("pass protection", "pass rush"), "overall": ("offense", "defense"),
    }.get(unit, (e.get("label") or unit or "offense", "defense"))
    off, dfn = e.get("off"), e.get("def")
    gap = e.get("gap") or 0
    who = off if gap > 0 else dfn
    return (f"{off}'s {off_w} ({_ord(e['off_rank'])}) against {dfn}'s {def_w} "
            f"({_ord(e['def_rank'])}) — edge {who}")


def sec_facts(c: Ctx) -> dict | None:
    g = c.g
    items = []
    when = kickoff_words(g.get("date"), g.get("kickoff"))
    if when:
        items.append(f"Kickoff: {when}")
    rec = ((c.result.get("playoff_picture") or {}).get("teams") or {})

    def record(t):
        r = rec.get(t) or {}
        if r.get("wins") is None or r.get("losses") is None:
            return ""
        s = f"{int(r['wins'])}-{int(r['losses'])}"
        return s + (f"-{int(r['ties'])}" if r.get("ties") else "")
    ra, rh = record(c.away), record(c.home)
    neutral = g.get("neutral_site") or c.meta.get("neutral_site")

    def ranked(t, side):
        rank = g.get(f"{side}_rank")
        return f"No. {int(rank)} {c.name(t)}" if isinstance(rank, (int, float)) and 0 < rank <= 25 else c.name(t)
    items.append(f"{ranked(c.away, 'away')}{f' ({ra})' if ra else ''} at {ranked(c.home, 'home')}"
                 f"{f' ({rh})' if rh else ''}" + (" — a neutral site" if neutral else ""))
    st = g.get("stadium") or {}
    venue = st.get("name") or g.get("venue") or ""
    if venue and c.sport == "cfb":
        items.append(f"Venue: {venue}" + (" — indoors" if g.get("indoor") else ""))
        venue = ""
    if venue:
        roof = {"dome": "a fixed dome", "closed": "roof closed", "open": "roof open",
                "retractable": "a retractable roof", "outdoors": "outdoors"}.get(
            str(g.get("roof") or st.get("roof") or "").lower(), "")
        # Abroad the schedule carries the home team's own surface, not the
        # ground's (nflverse), so the report says nothing rather than that.
        surface = "" if st.get("abroad") else str(g.get("surface") or st.get("surface") or "").replace("_", " ")
        alt = _f(st.get("altitude_ft"))
        bits = [b for b in (roof, surface and f"{surface} surface",
                            alt and alt >= 1000 and f"{int(alt):,} feet up") if b]
        items.append(f"Venue: {venue}" + (f" — {', '.join(bits)}" if bits else ""))
    recent = c.result.get("team_recent") or {}
    for t in c.teams:
        games = [x for x in recent.get(t) or [] if isinstance(x, dict)][:3]
        res = [f"{'W' if x.get('won') else 'L' if x.get('won') is False else 'T'} "
               f"{_num(x.get('scored'), 0)}-{_num(x.get('allowed'), 0)} "
               f"{'vs' if x.get('home') else 'at'} {x.get('opponent')}"
               for x in games if x.get("scored") is not None and x.get("allowed") is not None]
        if res:
            span = "last game" if len(res) == 1 else f"last {len(res)} games"
            items.append(f"{c.name(t)}' {span}: {'; '.join(res)}"
                         if c.name(t).endswith("s") else f"{c.name(t)}'s {span}: {'; '.join(res)}")
    coaches = []
    if c.sched_row is not None:
        try:
            from .spots import head_coach
            coaches = [(t, head_coach(c.sched, c.sched_row, t, c.staff)) for t in c.teams]
        except Exception:                                    # noqa: BLE001
            coaches = []
    named = [f"{c.name(t)}: {who}" for t, who in coaches if who]
    if named:
        items.append(f"Head coaches — {'; '.join(named)}")
    for t in c.teams:
        ch = (c.units.get(t) or {}).get("changed") or {}
        said = [w for side in ("off", "def") for w in ch.get(side) or []]
        if said:
            items.append(f"{c.name(t)}: {_join(sorted(set(said)))}")
    if c.sched_row is not None and c.sched_row.get("div"):
        items.append("A division game")
    hc, ac = str(g.get("home_conference") or ""), str(g.get("away_conference") or "")
    if c.meta.get("conference_game"):
        items.append(f"A {hc} game" if hc and hc == ac else "A conference game")
    elif hc and ac and hc != ac:
        items.append(f"Non-conference: {c.name(c.away)} ({ac}) against {c.name(c.home)} ({hc})")
    return _section("facts", "Game facts", [_list(items)])


def _rank_word(cell: dict, most: str, least: str) -> str:
    """"the most" for 1st, "3rd-most" in the top half, "4th-fewest" in the
    bottom half — a rank read from the near end."""
    try:
        r, of = int(cell.get("rank")), int(cell.get("of") or 0)
    except (TypeError, ValueError):
        return ""
    if of and r > (of + 1) // 2:
        r = of - r + 1
        return f"the {least}" if r == 1 else f"{_ord(r)}-{least}"
    return f"the {most}" if r == 1 else f"{_ord(r)}-{most}"


def meeting_line(m: dict) -> str:
    """"2025 week 13 at DET: GB won 31-24 · DET −2.5, GB covered · total 48.5, over"."""
    if m.get("round"):
        when = f"{m['season']} {m['round']}"
    elif m.get("week") is None and m.get("day"):
        try:
            d = _dt.date.fromisoformat(str(m["day"])[:10])
            when = f"{d.strftime('%b')}. {d.day}, {d.year}"
        except ValueError:
            when = str(m["day"])
    else:
        when = f"{m['season']} week {m['week']}"
    where = " (neutral site)" if m.get("neutral") else f" at {m['home']}"
    hs, as_ = _n(m.get("hs")), _n(m.get("as"))
    w = m.get("winner")
    if w:
        ws, ls = (hs, as_) if w == m["home"] else (as_, hs)
        score = f"{w} won {ws}-{ls}"
    else:
        score = f"tied {hs}-{as_}"
    bits = [f"{when}{where}: {score}"]
    sp = _f(m.get("spread_home"))
    if sp is not None:
        line = "a pick'em" if sp == 0 else f"{m['home'] if sp < 0 else m['away']} {_minus('-' + _num(abs(sp)))}"
        cov = m.get("covered")
        bits.append(line + (", a push" if cov == "push" else f", {cov} covered" if cov else ""))
    if _f(m.get("total")) is not None and m.get("ou"):
        bits.append(f"total {_num(m['total'])}, {'a push' if m['ou'] == 'push' else m['ou']}")
    return " · ".join(bits)


def sec_meetings(c: Ctx) -> dict | None:
    """When they last met (engine/reportdata.meetings): who won, who
    covered and whether it went over, at the lines it closed at."""
    ms = c.meetings
    if not ms:
        return None
    n = len(ms)
    wins = {t: sum(1 for m in ms if m.get("winner") == t) for t in c.teams}
    lead = max(c.teams, key=lambda t: wins[t])
    other = c.opp[lead]
    if wins[lead] == wins[other]:
        head = f"The last {_plural(n, 'meeting')} are split {wins[lead]}-{wins[other]}"
    else:
        head = f"{lead} has won {wins[lead]} of the last {_plural(n, 'meeting')}"
    lined = [m for m in ms if m.get("covered")]
    if lined:
        cov = {t: sum(1 for m in lined if m["covered"] == t) for t in c.teams}
        push = sum(1 for m in lined if m["covered"] == "push")
        best = max(c.teams, key=lambda t: cov[t])
        head += (f"; against the spread {best} is {cov[best]}-{cov[c.opp[best]]}"
                 + (f"-{push}" if push else ""))
    totals = [m for m in ms if m.get("ou")]
    if totals:
        ov = sum(1 for m in totals if m["ou"] == "over")
        un = sum(1 for m in totals if m["ou"] == "under")
        head += f"; {ov} went over the total and {un} under"
    blocks = [_p(head), _list(meeting_line(m) for m in ms)]
    blocks += rematch_blocks(c, ms[0])
    # College's meetings are the history database's games (reportdata
    # .meetings_db), never nflverse's file — the note says whose they are.
    src = "nflverse's schedule file" if c.sport == "nfl" else "the games in our history database"
    blocks.append({"type": "note", "text": "Each line is the closing spread and total the game was played at "
                                           f"({src}); the newest meeting first."})
    return _section("meetings", "When they last met", blocks)


#: A rematch's box: this many of the board's key players a side.
REMATCH_N = 4


def rematch_blocks(c: Ctx, m: dict) -> list:
    """A same-season rematch (Ethan's Commanders–Giants report: "Week 5: 27-27
    OT tie. Winston threw 33/54 for 326 ... Nabers went 11-121-1 on 20
    targets ... What changed: McCarthy replaces Winston ... WAS lost McLaurin,
    Brown and Croskey-Merritt to IR ... The game moves to MetLife"): what the
    board's own players did in it, off their logs, and what has changed
    since — a quarterback who is not the one who played it, the men now on
    a reserve list, the other team's field."""
    if not m or c.sport != "nfl" or m.get("week") is None or int(m.get("season") or 0) != int(c.season or 0):
        return []
    wk = int(m["week"])
    lines, played_qb = [], {}
    for t in c.teams:
        mine = []
        for r in c.reads:
            if r.get("team") != t:
                continue
            log = (c.form.get(r.get("player")) or {}).get("log") or []
            g = next((x for x in log if x.get("wk") == wk), None)
            if not g:
                continue
            group = FORM_GROUPS.get(str(r.get("pos") or "").upper())
            if not group:
                continue
            mine.append((_volume(r), f"{r.get('player')} {form_game(group, {'s': g.get('s') or {}})}"))
        mine.sort(key=lambda x: -x[0])
        if mine:
            lines.append(f"{c.name(t)}: " + "; ".join(x[1] for x in mine[:REMATCH_N]))
    for r in c.reads:
        if str(r.get("pos") or "").upper() != "QB":
            continue
        log = (c.form.get(r.get("player")) or {}).get("log") or []
        played_qb[r.get("team")] = any(x.get("wk") == wk and (x.get("s") or {}).get("pass_att") for x in log)
    out = []
    if lines:
        out += [_h(f"When they met in week {wk}"), _list(lines)]
    changed = []
    for t in c.teams:
        qb = next((r.get("player") for r in c.reads if r.get("team") == t
                   and str(r.get("pos") or "").upper() == "QB"), None)
        if qb and played_qb.get(t) is False:
            changed.append(f"{qb} starts for {c.name(t)} and did not throw a pass in that game")
        res = [x.get("player") for x in (c.scan.get("reserve") or {}).get(t) or [] if x.get("player")]
        if res:
            changed.append(f"{c.name(t)} is without {_join(res)}, on a reserve list now — check whether "
                           f"{'he' if len(res) == 1 else 'they'} played in the first meeting")
    if m.get("home") and m["home"] != c.home and not m.get("neutral"):
        changed.append(f"The game moves to {c.name(c.home)}'s field — the first was at {c.name(m['home'])}'s")
    if changed:
        out += [_h("What has changed since"), _list(changed)]
    return out


def sec_market(c: Ctx) -> dict | None:
    g = c.g
    out = []
    lw = line_words(c)
    pts = implied_points(c)
    if lw:
        s = f"The line: {lw}"
        if pts:
            s += (f". That puts {c.home} at about {_num(pts[c.home])} {c.score_words} and "
                  f"{c.away} at about {_num(pts[c.away])}")
        out.append(_p(s))
    ml = ml_chances(c)
    if ml:
        fav = max(ml, key=ml.get)
        dog = c.opp[fav]
        out.append(_p(f"Moneyline: {fav} {_odds(g.get('home_ml' if fav == c.home else 'away_ml'))}, "
                      f"{dog} {_odds(g.get('home_ml' if dog == c.home else 'away_ml'))} — "
                      f"take out the book's cut and that gives {fav} {a_pct(ml[fav])} chance to win"))
    lo = g.get("line_open") or {}
    moves = []
    if lo:
        o_sp, mv = _f(lo.get("spread_home")), _f(lo.get("spread_move"))
        if o_sp is not None:
            opened = (f"{c.home} {_minus(_num(o_sp))}" if o_sp < 0 else f"{c.away} {_minus(_num(-o_sp))}"
                      if o_sp > 0 else "a pick'em")
            what = FIXED_LINES.get(c.sport, "spread")
            if mv:
                toward = c.home if mv < 0 else c.away
                moves.append(f"The {what} opened at {opened} and has moved {_num(abs(mv))} "
                             f"{c.score_word if abs(mv) == 1 else c.score_words} toward {toward}")
            else:
                moves.append(f"The {what} opened at {opened} and has not moved")
        o_tot, tmv = _f(lo.get("total")), _f(lo.get("total_move"))
        if o_tot is not None:
            moves.append(f"The total opened at {_num(o_tot)}" +
                         (f" and is {'up' if tmv > 0 else 'down'} {_num(abs(tmv))}" if tmv else
                          " and has not moved"))
        am = lo.get("against_money")
        if isinstance(am, dict) and am.get("toward") and am.get("money_on"):
            to = c.home if am["toward"] == "home" else c.away
            on = c.home if am["money_on"] == "home" else c.away
            moves.append(f"The line moved toward {to} while {_pct(am.get('money_share'))} of the "
                         f"prediction-market money sat on {on} — a move against the money")
        # THE TOTAL AGAINST THE MONEY (engine/lineopen.total_against_money):
        # Ethan's Commanders–Giants read, 43.5 to 40.5 with 70% on the over.
        ta = lo.get("total_against_money")
        if isinstance(ta, dict) and ta.get("toward") and ta.get("money_on"):
            moves.append(f"The total moved {_num(abs(_f(ta.get('delta')) or 0))} toward the {ta['toward']} while "
                         f"{_pct(ta.get('money_share'))} of the prediction-market money sat on the "
                         f"{ta['money_on']} — a move against the money, which often means the bigger bettors "
                         f"are on the {ta['toward']}")
    out.append(_list(moves))
    cr = g.get("crowd") or {}
    crowd = []
    venues = [(v, cr.get(k)) for v, k in (("Kalshi", "kalshi"), ("Polymarket", "polymarket"))
              if _f(cr.get(k)) is not None]
    if venues:
        crowd.append(f"Prediction markets give {c.home} " + _join(
            f"{a_pct(p)} chance on {v}" for v, p in venues))
    if _f(cr.get("books")) is not None and _f(cr.get("gap_pts")) is not None:
        gap = float(cr["gap_pts"])
        if abs(gap) >= 1:
            crowd.append(f"That is {_num(abs(gap))} points {'higher' if gap > 0 else 'lower'} on "
                         f"{c.home} than the sportsbooks ({_pct(cr['books'])})")
        else:
            crowd.append(f"The sportsbooks agree ({c.home} {_pct(cr['books'])})")
    for venue, key, what in (("Kalshi", "kalshi_home_cover", "covering"),
                             ("Polymarket", "poly_home_cover", "covering")):
        if _f(cr.get(key)) is not None:
            crowd.append(f"{venue} has {c.home} {what} at {_pct(cr[key])}")
    for venue, key in (("Kalshi", "kalshi_over"), ("Polymarket", "poly_over")):
        if _f(cr.get(key)) is not None:
            crowd.append(f"{venue} has the over at {_pct(cr[key])}")
    out.append(_list(crowd))
    money = g.get("money") or {}
    split = []
    for mk, word in (("ml", "moneyline"), ("spread", "spread"), ("total", "total")):
        s = money.get(mk)
        if not isinstance(s, dict):
            continue
        if mk == "total":
            a, b, an, bn = s.get("over"), s.get("under"), "the over", "the under"
        else:
            a, b, an, bn = s.get("home"), s.get("away"), c.home, c.away
        if _f(a) is None or _f(b) is None:
            continue
        side, share = (an, a) if float(a) >= float(b) else (bn, b)
        split.append(f"{_pct(share)} of the {word} money is on {side}"
                     + (f" (${int(round(float(s['usd']))):,} traded)" if _f(s.get("usd")) else ""))
    if split:
        venues_w = _join(money.get("venues") or []) or "the prediction markets"
        out.append(_p(f"On {venues_w}, {_join(split)}"))
    # THE SPORTSBOOK'S PUBLIC SPLITS (engine/splits; Ethan's D, 2026-10-24).
    from .splits import words as _split_words
    public = _split_words(((c.result.get("betting_splits") or {}).get(f"{c.away}@{c.home}")) or {},
                          c.home, c.away)
    if public:
        out.append(_p(public))
    sim = g.get("sim") or {}
    if _f(sim.get("p_home_win")) is not None:
        ph = float(sim["p_home_win"])
        sp = _f(g.get("spread"))
        bits = [f"{c.home} won {_pct(ph)}"]
        if _f(sim.get("cover")) is not None and sp is not None and sp != 0:
            bits.append(f"covered {'−' if sp < 0 else '+'}{_num(abs(sp))} in {_pct(sim['cover'])}"
                        + (f" (a push in {_pct(sim['cover_push'])})"
                           if (_f(sim.get('cover_push')) or 0) >= 0.02 else ""))
        if _f(sim.get("over")) is not None and _f(g.get("total")) is not None:
            bits.append(f"the game went over {_num(g['total'])} in {_pct(sim['over'])}")
        times = f" {int(sim['trials']):,} times" if sim.get("trials") else ""
        out.append(_p(f"We simulated this game{times}, drive by drive, from these lines and both teams' "
                      f"numbers: {_join(bits)}. That's a simulation, not a pick"))
    if lw and not ml and not lo and not cr and not money:
        out.append(_p("No sportsbook moneyline was on the board for this game when it was built"))
    return _section("market", "The market", out)


def _rank_cell(u: dict, how: str) -> str:
    if not u or u.get("rank") is None:
        return "—"
    v = _fmt(u.get("value"), how)
    return f"{v} · {_ord(u['rank'])}" if v else _ord(u["rank"])


def _table_for(c: Ctx, off: str, dfn: str) -> dict | None:
    rows = []
    for unit, label, how in UNIT_ROWS:
        o, d = c.unit(off, "off", unit), c.unit(dfn, "def", unit)
        if o.get("rank") is None and d.get("rank") is None:
            continue
        edge = "—"
        if o.get("rank") is not None and d.get("rank") is not None:
            gap = int(d["rank"]) - int(o["rank"])
            edge = off if gap >= c.gap_bar else dfn if -gap >= c.gap_bar else "—"
        rows.append([label, _rank_cell(o, how), _rank_cell(d, how), edge])
    if not rows:
        return None
    return {"type": "table", "title": f"{c.name(off)} offense vs {c.name(dfn)} defense",
            "head": ["", f"{off} off", f"{dfn} def", "Edge"], "rows": rows, "rank_of": c.n_teams}


def sec_rankings(c: Ctx) -> dict | None:
    # The season's own numbers stand without the unit ranks.
    blocks = [_table_for(c, c.away, c.home), _table_for(c, c.home, c.away)] if c.units else []
    if any(blocks):
        blocks.append({"type": "note", "text": CFB_UNIT_NOTE if c.sport == "cfb" else UNIT_NOTE})
    nums = c.scan.get("numbers") or {}
    if all(nums.get(t) for t in c.teams):
        rows = []
        for key, label, how in NUMBER_ROWS:
            a, h = (nums[c.away].get(key) or {}), (nums[c.home].get(key) or {})
            if _f(a.get("value")) is None and _f(h.get("value")) is None:
                continue
            cell = (lambda x: "—" if _f(x.get("value")) is None else
                    _fmt(x["value"], how) + (f" · {_ord(x['rank'])}" if x.get("rank") else ""))
            rows.append([label, cell(a), cell(h)])
        if rows:
            played = _join(f"{_plural(nums[t]['games'], 'game')} for {t}" for t in c.teams
                           if nums[t].get("games"))
            blocks.append({"type": "table", "title": "This season's numbers",
                           "head": ["", c.away, c.home], "rows": rows, "rank_of": c.n_teams,
                           "note": (f"Through {played}. " if played else "")
                                   + "Each rank is against the whole league; 1st is best."})
    u0 = c.units.get(c.home) or c.units.get(c.away) or {}
    if u0.get("blend") is not None and u0.get("games"):
        w = float(u0["blend"])
        adjusted = (c.scan.get("method") or {}).get("opponent_adjusted", c.sport != "cfb")
        blocks.append(_p(("The ranks are adjusted for the opponents each team has faced. " if adjusted else
                          f"The ranks are against all {c.n_teams} teams, not adjusted for opponents. ")
                         + f"After {_plural(u0['games'], 'game')}, each rank mixes {_pct(w)} this season with "
                         f"{_pct(1 - w)} last season, the blend that predicted best when we tested it. An edge "
                         f"means the two sides are {c.gap_bar} or more ranks apart"))
    edges = _edges(c)
    if edges:
        said = [edge_words(c, e) for e in edges[:4]]
        blocks.append(_p("The biggest gaps: " + "; ".join(said)))
    return _section("rankings", "How the units rank", blocks)


def tempo_line(c: Ctx, t: str) -> str:
    """Plays a game, seconds a snap and pass rate over expected, ranked
    (engine/gamescan.season_numbers off team_weeks)."""
    n = (c.scan.get("numbers") or {}).get(t) or {}
    bits = []
    pg, pc, pr = n.get("plays_pg") or {}, n.get("pace") or {}, n.get("proe") or {}
    if _f(pg.get("value")) is not None:
        bits.append(f"runs {_num(pg['value'])} plays a game"
                    + (f" ({_rank_word(pg, 'most', 'fewest')})" if pg.get("rank") else ""))
    if _f(pc.get("value")) is not None:
        bits.append(f"snaps it every {_num(pc['value'])} seconds with the game in the balance"
                    + (f" ({_rank_word(pc, 'quickest', 'slowest')})" if pc.get("rank") else ""))
    if _f(pr.get("value")) is not None:
        v = float(pr["value"])
        bits.append(f"throws on {_pct(abs(v), 1)} {'more' if v >= 0 else 'fewer'} of its plays than the "
                    f"down, distance and score call for"
                    + (f" ({_rank_word(pr, 'most', 'fewest')} in the league)" if pr.get("rank") else ""))
    return f"Tempo: {t} {_join(bits)}" if bits else ""


def sec_identity(c: Ctx) -> dict | None:
    blocks = []
    nums = c.scan.get("numbers") or {}
    ch = c.scan.get("charting") or {}
    ch_off, ch_def = ch.get("offense") or {}, ch.get("defense") or {}
    scheme = c.scan.get("scheme") or {}
    season_ch, weeks = ch.get("season"), ch.get("weeks")
    sch_season = c.scan.get("scheme_season")
    for t in c.teams:
        lines = []
        tempo = tempo_line(c, t)
        if tempo:
            lines.append(tempo)
        rr = _f(((nums.get(t) or {}).get("run_rate") or {}).get("value"))
        o = ch_off.get(t) or {}
        style = []
        if rr is not None:
            style.append(f"runs the ball on {_pct(rr)} of plays")
        uses = []
        for key, words in (("play_action_rate", "play action on {} of dropbacks"),
                           ("motion_rate", "pre-snap motion on {} of plays"),
                           ("screen_rate", "screens on {} of plays"),
                           ("rpo_rate", "run-pass options on {} of plays"),
                           ("no_huddle_rate", "no huddle on {} of plays")):
            if _f(o.get(key)) is not None:
                uses.append(words.format(_pct(o[key])))
        if uses:
            uses[0] = "uses " + uses[0]
        style += uses
        if style:
            lines.append(f"On offense {t} {_join(style)}" +
                         (f" (charted, weeks 1–{weeks} of {season_ch})" if season_ch and weeks and o else ""))
        mine = c.reads_for(t)
        tree = sorted((r for r in mine if str(r.get("pos") or "").upper() in ("WR", "TE", "RB")
                       and (_usage(r).get("tgt_share") or 0) >= TREE_SHARE),
                      key=lambda r: -(_usage(r).get("tgt_share") or 0))
        if tree:
            word = _caught(_usage(tree[0]))[0]
            lines.append(("Who catches it: " if word == "catches" else "Who gets the targets: ")
                         + "; ".join(f"{r['player']} ({r.get('pos')}) {_pct(_usage(r)['tgt_share'])} of the "
                                     f"{word}" + (f", {_num(_caught(_usage(r))[1])} a game"
                                                  if _f(_caught(_usage(r))[1]) is not None else "")
                                     for r in tree[:5]))
        backs = sorted((r for r in mine if str(r.get("pos") or "").upper() in ("RB", "FB", "QB")
                        and (_usage(r).get("carry_share") or 0) >= BACKFIELD_SHARE),
                       key=lambda r: -(_usage(r).get("carry_share") or 0))
        if backs:
            lines.append("Who carries it: " + "; ".join(
                f"{r['player']} ({r.get('pos')}) {_pct(_usage(r)['carry_share'])} of the carries"
                + (f", {_num(_usage(r).get('carries_pg'))} a game" if _f(_usage(r).get("carries_pg")) is not None
                   else "") for r in backs[:3]))
        d = scheme.get(t) or {}
        cov = []
        if _f(d.get("zone")) is not None and _f(d.get("man")) is not None:
            cov.append(f"plays zone {_pct(d['zone'])} of the time and man {_pct(d['man'])}")
        shells = sorted(((k, v) for k, v in (d.get("shells") or {}).items() if _f(v)),
                        key=lambda kv: -kv[1])[:3]
        if shells:
            cov.append("most often in " + _join(f"{SHELL_WORDS.get(k, k.replace('_', ' ').title())} "
                                                f"({_pct(v)})" for k, v in shells))
        if _f(d.get("mofo")) is not None:
            cov.append(f"shows two deep safeties on {_pct(d['mofo'])} of snaps")
        if _f(d.get("blitz")) is not None:
            cov.append(f"blitzes {_pct(d['blitz'])}")
        if _f(d.get("pressure")) is not None:
            cov.append(f"gets pressure on {_pct(d['pressure'])} of dropbacks")
        # THIS SEASON FIRST (2026-11-14). The coverage table is the newest
        # season the participation data has (2025 on 14 November), and it
        # was said first and plain: "NYG blitzes 30%" beside this season's
        # charting of 40%. Ethan: "I feel like we're not pulling the most
        # recent data". This season's charting leads; last season's shells
        # say they are last season's.
        dd = ch_def.get(t) or {}
        now, box = [], []
        if _f(dd.get("blitz_rate")) is not None:
            now.append(f"blitzes on {_pct(dd['blitz_rate'])} of dropbacks")
        if _f(dd.get("heavy_box_rate")) is not None:
            box.append(f"8 or more defenders near the line on {_pct(dd['heavy_box_rate'])} of runs")
        if _f(dd.get("light_box_rate")) is not None:
            box.append(f"6 or fewer on {_pct(dd['light_box_rate'])}")
        if box:
            now.append(("against the run it puts " if now else "puts ") + _join(box))
        if now:
            lines.append(f"This season {t} " + "; ".join(now) +
                         (f" (charted, weeks 1–{weeks})" if weeks else ""))
        if cov:
            old = bool(sch_season and c.season and int(sch_season) < int(c.season))
            if old and _f(dd.get("blitz_rate")) is not None:
                cov = [x for x in cov if not x.startswith("blitzes ")]
            lines.append((f"Last season ({sch_season}) {t} " + _join(cov).replace("plays zone", "played zone")
                          .replace("shows two deep", "showed two deep").replace("gets pressure", "got pressure")
                          .replace("blitzes", "blitzed")
                          + " — this season's coverage numbers come out after the season")
                         if old else
                         f"On defense {t} {_join(cov)}" + (f" ({sch_season} charting)" if sch_season else ""))
        if lines:
            blocks += [_h(c.name(t)), _list(lines)]
    return _section("identity", "How each team plays", blocks)


def sec_injuries(c: Ctx) -> dict | None:
    blocks = []
    rows = [r for r in c.scan.get("injuries") or [] if isinstance(r, dict)]
    status = c.result.get("injury_status") or {}
    for t in c.teams:
        mine = [r for r in rows if r.get("team") == t]
        if mine:
            blocks += [_h(c.name(t)), _list(
                f"{r.get('player')} ({r.get('position') or '—'}) — {str(r.get('status') or '').lower()}"
                + (f". {r['opens'][0].upper()}{r['opens'][1:]}" if r.get("opens") else "")
                for r in mine)]
    # ON A RESERVE LIST (the roster's own status, engine/gamescan
    # .reserve_rows): the men the weekly report never lists, with what they
    # took with them — Ethan's reports open on them ("Terry McLaurin, IR —
    # removes the WR1").
    for t in c.teams:
        res = [r for r in (c.scan.get("reserve") or {}).get(t) or [] if isinstance(r, dict)]
        if res:
            blocks.append(_p(f"{c.name(t)} without, for the season or a while: " + "; ".join(
                f"{r['player']}" + (f" ({r['position']})" if r.get("position") else "")
                + f" — {r['status']}; he had {r['what']} this season" for r in res)))
    lines = c.scan.get("line_out") or {}
    for t in c.teams:
        if lines.get(t):
            own = c.name(t) + ("'" if c.name(t).endswith("s") else "'s")
            blocks.append(_p(f"{own} offensive line: {_join(lines[t])} "
                             f"{'is' if len(lines[t]) == 1 else 'are'} out"))
    blocks += practice_blocks(c)
    pulled = [p for p in c.scan.get("pulled") or [] if p]
    if pulled:
        blocks.append(_p(f"Every sportsbook has pulled its props on {_join(pulled)}, so we treat "
                         f"{'him' if len(pulled) == 1 else 'them'} as out until the props come back"))
    for q in c.result.get("qb_changes") or []:
        if isinstance(q, dict) and q.get("team") in c.teams and q.get("headline"):
            text = q["headline"]
            if q.get("detail"):
                text += f". {q['detail']}"
            if q.get("volume"):
                text += f". {q['volume']}"
            blocks.append(_p(text))
    resets = (c.result.get("sample_resets") or {})
    for bucket in ("reset", "held"):
        for who, r in (resets.get(bucket) or {}).items():
            det = str((r or {}).get("detail") or "")
            if any(f"joined {t} " in det + " " for t in c.teams):
                blocks.append(_p(f"{who} {det} (week {r.get('week')}) — his games before the move "
                                 f"count for less"))
    if not blocks:
        if status.get("applied") or status.get("asked") or status.get("total"):
            blocks.append(_p("Neither team lists a starter or a featured player as out or "
                             "questionable"))
        else:
            blocks.append(_p("The injury report was not read for this build — check "
                             + ("the inactives" if c.sport == "nfl" else "the injury news") + " before kickoff"))
    return _section("injuries", "Injuries and availability", blocks)


#: How a listed player practised, in words (engine/practice.PRACTICE).
PRACTICE_WORDS = {"DNP": ("did not practice", "who did not practice"),
                  "Limited": ("was limited in practice", "who were limited in practice"),
                  "Full": ("practiced fully", "who practiced fully")}


def practice_line(x: dict, held: bool) -> str:
    """One listed player: his designation, how he practised, how often men
    listed the same way have played, and — once it has beaten the league's
    number on held-out seasons — his club's own record."""
    head = (f"{x.get('player')} ({x.get('team')}"
            + (f", {str(x['injury']).lower()}" if x.get("injury") else "")
            + f") — {str(x.get('designation') or '').lower()}")
    pw = PRACTICE_WORDS.get(x.get("practice"))
    if pw:
        head += f"; he {pw[0]} at his last practice of the week"
    out = [head]
    lg = _f(x.get("league"))
    if lg is not None:
        who = f"Players listed {str(x.get('designation') or '').lower()}" + (f" {pw[1]}" if pw else "")
        s = f"{who} have played {_pct(lg)} of the time"
        if x.get("n"):
            s += f" ({_n(x['n']):,} listings)"
        if _f(x.get("ratio")) is not None:
            s += f", taking {_pct(x['ratio'])} of their usual snaps when they did"
        out.append(s)
    if held and _f(x.get("club")) is not None:
        out.append(f"With {x.get('team')}'s own record of who it lists and who plays folded in: {_pct(x['club'])}")
    return ". ".join(out)


def practice_blocks(c: Ctx) -> list:
    """The week's practice report for the players this report names
    (engine/practice, by way of the ideas file); everyone else listed
    questionable or doubtful is named in one line."""
    v = c.ideas.get("practice") or {}
    rows = [x for x in v.get("rows") or [] if isinstance(x, dict) and x.get("player")]
    if not rows:
        return []
    named = {r.get("player") for r in c.reads} | {
        r.get("player") for r in c.scan.get("injuries") or [] if isinstance(r, dict)}
    held = bool((v.get("held_out") or {}).get("holds"))
    lines = [practice_line(x, held) for x in rows if x["player"] in named]
    rest = [f"{x['player']} ({x.get('team')}, {str(x.get('designation') or '').lower()})"
            for x in rows if x["player"] not in named]
    if rest:
        lines.append("Also listed: " + (_join(rest) if len(rest) <= 12 else
                                        f"{', '.join(rest[:12])} and {len(rest) - 12} more"))
    return [_h("The practice report"), _list(lines)] if lines else []


def _corner_line(cn: dict, grade: dict | None = None) -> str:
    bits = [f"{cn.get('name')} ({cn.get('spot')})"]
    if cn.get("targets"):
        bits.append(f"{_num(cn.get('rating'))} passer rating allowed on {_plural(cn['targets'], 'target')}"
                    + (f", {_num(cn.get('yds_per_tgt'))} yards a target" if cn.get("yds_per_tgt") else "")
                    + (f", {_plural(cn['td'], 'touchdown')}" if cn.get("td") else ""))
    if grade:
        bits.append(f"our coverage grade {grade['grade']} of 100 ({grade['n']} defenders ranked)")
    if cn.get("status"):
        bits.append(str(cn["status"]).lower())
    if cn.get("next_man_up"):
        bits.append("next man up")
    return " — ".join(bits)


def funnel_lines(c: Ctx, dfn: str) -> list:
    """Where ``dfn`` leaks and where it holds, by position, off the
    defense-vs-position ratings the props were priced against."""
    r = c.allowed.get(dfn) or {}
    if not r:
        return []
    leaks, holds = [], []
    for group, stats in FUNNEL_GROUPS:
        soft, hard = [], []
        for s in stats:
            x = r.get(s) or {}
            rank, of, pg = x.get("rank"), x.get("of"), _f(x.get("pg"))
            if rank is None or not of or pg is None:
                continue
            per = _num(pg, 2 if s.endswith("_td") else 1)
            if int(rank) <= FUNNEL_RANKS:
                soft.append(f"the {_ord(rank)}-most {FUNNEL_WORDS[s]} ({per} a game)")
            elif int(rank) > int(of) - FUNNEL_RANKS:
                hard.append(f"the {_ord(int(of) - int(rank) + 1)}-fewest {FUNNEL_WORDS[s]} ({per} a game)")
        if soft:
            leaks.append(f"{_join(soft)} to {FUNNEL_TO.get(group, group)}")
        if hard:
            holds.append(f"{_join(hard)} to {FUNNEL_TO.get(group, group)}")
    # IN A SENTENCE (Ethan, 2026-11-15): "Where DET's defense leaks: tight
    # ends — the 1st-most receiving yards (109 a game) (over 5 games)" is
    # "DET's defense is weakest against … it gives up the most receiving
    # yards to tight ends (109 a game)".
    out = []
    games = next((x.get("games") for x in r.values() if isinstance(x, dict) and x.get("games")), None)
    over = f", over {_plural(games, 'game')}" if games else ""
    if leaks:
        out.append(f"Where {dfn}'s defense is weakest{over}: it gives up {'; '.join(leaks)}")
    if holds:
        out.append(f"Where it's strongest: it gives up {'; '.join(holds)}")
    return out


def _why(r: dict) -> list:
    """A read's reasons, the pick-free ones: what it says for and against
    him, then the scheme, charting and tracking notes about him. His share
    of the work is on his line already, and the corner's numbers are in the
    coverage lines under the verdicts, so neither is said again here."""
    role = bool(_role_line(r))
    why = [str(x) for x in (r.get("pro") or []) + (r.get("con") or []) if x
           and not (role and any(w in str(x) for w in ("of the carries", "of the targets", "of the catches")))]
    for n in r.get("notes") or []:
        s = str(n)
        if s.startswith("Usage is ") or "passer rating on" in s:
            continue
        # The charting and tracking notes (engine/gamescan.charting_notes),
        # by their plain heads since 2026-11-15 and their old ones.
        if "against man" in s or "against zone" in s or "box" in s or "near the line" in s \
                or s.startswith(("Player tracking:", "Charting:", "Tracking:", "Charted:", "On the ground:")):
            why.append(s)
    seen, out = set(), []
    for w in why:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out


def _shared(whys: list) -> set:
    """Reasons two or more of one offense's players carry — said once for
    the group instead of under every name."""
    seen: dict = {}
    for why in whys:
        for w in set(why):
            seen[w] = seen.get(w, 0) + 1
    return {w for w, n in seen.items() if n >= 2}


def sec_matchups(c: Ctx) -> dict | None:
    blocks = []
    cov = c.scan.get("coverage") or {}
    for off in c.teams:
        dfn = c.opp[off]
        sub = []
        keys = sorted((r for r in c.reads_for(off) if _is_key(r)), key=lambda r: -_volume(r))
        whys = [_why(r) for r in keys]
        common = _shared(whys)
        if common:
            order = [w for why in whys for w in why]
            said = sorted(common, key=order.index)
            text = "; ".join(said)
            if text.split(" ")[0] in ("The", "Only", "A", "An", "His", "He", "Takes"):
                text = text[:1].lower() + text[1:]
            sub.append(_p(f"True for every {off} player below: {text}"))
        items = []
        for r, why in zip(keys, whys):
            tone, label = VERDICT.get(r.get("read"), ("neutral", "NEUTRAL"))
            scorer = scorer_words(c, r) if _go_to(r) else ""
            if scorer and tone == "unfavorable":
                # Duke's back at Miami (engine/readlogic rule 3): the yards
                # are tough, the touchdowns still go through him — said as
                # the card says it, never as UNFAVORABLE first.
                tone, label = "neutral", "TOUGH FOR YARDS — STILL THE GO-TO SCORER"
            pos = str(r.get("pos") or "").upper()
            against = {"QB": f"{dfn}'s pass defense", "RB": f"{dfn}'s run defense",
                       "FB": f"{dfn}'s run defense"}.get(pos, f"{dfn}'s coverage")
            items.append({"player": r.get("player"), "team": off, "pos": pos,
                          "headshot": r.get("headshot") or "", "verdict": tone, "label": label,
                          "title": f"{r.get('player')} vs {against}", "role": _role_line(r),
                          "why": ([_sentence(cap(scorer))] if scorer else [])
                          + [_sentence(w) for w in why if w not in common][:4],
                          "form": form_lines(c, r),
                          # His pick on the read's side (`read_pick`).
                          **({"pick": read_pick(r)} if read_pick(r) else {})})
        if items:
            sub.append({"type": "verdicts", "items": items})
        room = cov.get(dfn) or {}
        corners = [cn for cn in room.get("corners") or [] if isinstance(cn, dict) and cn.get("name")]
        notes = []
        from .grades import coverage_of as _cov_grade

        def _cg(cn, team=dfn):
            return _cov_grade(c.grades, team, cn.get("name") or "")
        w = None
        if room.get("weakest"):
            w = next((cn for cn in corners if cn.get("name") == room["weakest"]), None)
            if w and w.get("targets"):
                notes.append(f"The soft spot in {dfn}'s coverage: {_corner_line(w, _cg(w))}")
            else:
                w = None
        # The soft spot is said once (2026-11-15): the corners' line names
        # the others.
        rest = [cn for cn in corners if cn is not w]
        if rest:
            notes.append(f"{dfn}'s {'other ' if w else ''}corners: "
                         + "; ".join(_corner_line(cn, _cg(cn)) for cn in rest))
        if room.get("missing"):
            notes.append(f"{dfn} is without {_join(room['missing'])} in the secondary")
        notes += funnel_lines(c, dfn)
        sub.append(_list(notes))
        sub = [b for b in sub if b]
        if sub:
            blocks += [_h(f"{c.name(off)} offense vs {c.name(dfn)} defense")] + sub
    if c.grades and blocks:
        from .grades import NOTE as _grade_note
        blocks.append(_p(_grade_note))
    return _section("matchups", "Who's guarding who", blocks)


def sec_trenches(c: Ctx) -> dict | None:
    blocks = []
    rush = c.scan.get("rush") or {}
    nums = c.scan.get("numbers") or {}
    lines_out = c.scan.get("line_out") or {}
    for off in c.teams:
        dfn = c.opp[off]
        lines = []
        po, pd = c.rank(off, "off", "pressure"), c.rank(dfn, "def", "pressure")
        if po is not None and pd is not None:
            gap = int(pd) - int(po)
            who = off if gap >= c.gap_bar else dfn if -gap >= c.gap_bar else None
            lines.append(f"{off}'s pass protection ranks {_ord(po)} against {dfn}'s pass rush "
                         f"({_ord(pd)})" + (f" — edge {who}" if who else " — close to even"))
        rushers = [x for x in rush.get(dfn) or [] if isinstance(x, dict) and x.get("name")]
        if rushers:
            lines.append(f"{dfn}'s pass rush is led by " + _join(
                f"{x['name']} ({_plural(x.get('pressures') or 0, 'pressure')}, "
                f"{_plural(x.get('sacks') or 0, 'sack')}{', ' + str(x['status']).lower() if x.get('status') else ''})"
                for x in rushers))
        sk = (nums.get(dfn) or {}).get("sacks") or {}
        if _f(sk.get("value")) is not None:
            lines.append(f"{dfn} averages {_num(sk['value'])} sacks a game"
                         + (f" ({_ord(sk['rank'])})" if sk.get("rank") else ""))
        if lines_out.get(off):
            lines.append(f"{off} is without {_join(lines_out[off])} up front")
        ro, rd = c.unit(off, "off", "rushing"), c.unit(dfn, "def", "rushing")
        if ro.get("rank") is not None and rd.get("rank") is not None:
            ypc_o, ypc_d = c.unit(off, "off", "ypc"), c.unit(dfn, "def", "ypc")
            s = f"{off}'s run game ranks {_ord(ro['rank'])}"
            if _f(ypc_o.get("value")) is not None:
                s += f" ({float(ypc_o['value']):.1f} yards a carry)"
            s += f" against {dfn}'s run defense ({_ord(rd['rank'])}"
            if _f(ypc_d.get("value")) is not None:
                s += f", allowing {float(ypc_d['value']):.1f} a carry"
            s += ")"
            gap = int(rd["rank"]) - int(ro["rank"])
            who = off if gap >= c.gap_bar else dfn if -gap >= c.gap_bar else None
            lines.append(s + (f" — edge {who}" if who else ""))
        lines += _college_front(c, off, dfn)
        if lines:
            blocks += [_h(f"{c.name(off)} up front"), _list(lines)]
    return _section("trenches", "In the trenches", blocks)


def _college_front(c: Ctx, off: str, dfn: str) -> list:
    """College's line play (engine/gamescan.CFB_UNITS): havoc, line yards
    and the stuff rate, each side's rank against the other's."""
    # IN PLAIN WORDS (2026-11-15): "MIA's runs stuffed at the line rank
    # 70th against IU's stuff rate (7th)" is "MIA ranks 70th at keeping its
    # runs from being stuffed at the line; IU's defense ranks 7th at
    # stuffing them".
    out = []
    for unit, said_off, said_def in (
            ("line", "{off} ranks {o} in line yards (how much its blockers give each run)",
             "{dfn}'s run front ranks {d}"),
            ("stuff", "{off} ranks {o} at keeping its runs from being stuffed at or behind the line",
             "{dfn}'s defense ranks {d} at stuffing them"),
            ("havoc", "{off} ranks {o} at avoiding havoc plays (tackles for a loss, sacks, takeaways and "
                      "passes defended)", "{dfn}'s defense ranks {d} at making them")):
        o, d = c.unit(off, "off", unit), c.unit(dfn, "def", unit)
        if o.get("rank") is None or d.get("rank") is None:
            continue
        gap = int(d["rank"]) - int(o["rank"])
        who = off if gap >= c.gap_bar else dfn if -gap >= c.gap_bar else None
        out.append(said_off.format(off=off, o=_ord(o["rank"])) + "; "
                   + said_def.format(dfn=dfn, d=_ord(d["rank"])) + (f" — edge {who}" if who else ""))
    return out


def _place(rank, of, good: str = "best", bad: str = "worst") -> str:
    """"the best", "the 8th-best", "the 10th-worst" — a rank of ``of`` read
    from its near end, 1st the best. Ethan, 2026-11-14, circling "(23rd of 32,
    1st the stingiest)" on the red-zone lines: "the wording in these reports
    are confusing and doesn't make sense or is hard to read"."""
    try:
        r, n = int(rank), int(of)
    except (TypeError, ValueError):
        return ""
    if n and r > (n + 1) // 2:
        r = n - r + 1
        return f"the {bad}" if r == 1 else f"the {_ord(r)}-{bad}"
    return f"the {good}" if r == 1 else f"the {_ord(r)}-{good}"


#: Within this of the league, a number is "about average" — never "0% below".
AVERAGE_BAND = 0.05


def _than_average(rel, more: str = "more", fewer: str = "fewer", who: str = "team") -> str:
    """"20% fewer than an average team", "about average"."""
    if rel is None:
        return ""
    if abs(rel) < AVERAGE_BAND:
        return "about average"
    return f"{_pct(abs(rel))} {more if rel > 0 else fewer} than an average {who}"


def _than_marks(marks: dict, offense: str, rel_o, defense: str, rel_d) -> None:
    """The red zone's "than average" in its colour (2026-11-15, Ethan: "if
    it's good, then green, if it's bad, then red"): more for an offense is
    green, more allowed by a defense red; "about average" stays plain."""
    for words, rel, up in ((offense, rel_o, True), (defense, rel_d, False)):
        if words and words != "about average" and rel is not None:
            marks[words] = "up" if (rel > 0) == up else "down"


#: WHO CAN SCORE, RANKED (Ethan's NFL Bet checking chats: "line up in order
#: who has the best touchdown chances on each team", and "I want to know that
#: next to the Dolphins tight end on the chart … like where each defense
#: lacks in red zone defense"). A scorer's usage backs him at this share of
#: his team's red-zone chances; the matchup backs him when the defense gives
#: up touchdowns to his position at TD_FUNNEL_RANK or worse.
TD_USAGE_SHARE = 0.30
TD_FUNNEL_RANK = 10
TD_LIST = 4
_TD_STAT = {"RB": "rb_td", "FB": "rb_td", "WR": "wr_td", "TE": "te_td"}
_TD_WORD = {"RB": "running backs", "FB": "running backs", "WR": "receivers", "TE": "tight ends"}


def td_chance_lines(c: Ctx, off: str) -> list:
    """``off``'s scorers by our touchdown chance: the price (and whether it is
    past the −250 limit), his share of the red-zone chances, what the defense
    gives up to his position, whether usage and matchup both back him, and
    the touchdown rule (likelyboard.td_rule)."""
    dfn = c.opp[off]
    ro = (c.scan.get("redzone") or {}).get(off) or {}
    team_rz = _f(ro.get("off"))
    allowed = c.allowed.get(dfn) or {}
    rows = []
    for r in c.reads_for(off):
        td = r.get("td") or {}
        p = _f(td.get("model_prob"))
        if p is None or p <= 0:
            continue
        pos = str(r.get("pos") or "").upper()
        odds = _f(td.get("odds"))
        bits = [f"{_pct(p)} to score" + (f", at {_odds(odds)}" + (" (past the −250 limit)" if odds < TAKE_CAP else "")
                                         if odds is not None else "")]
        share = None
        if _f(td.get("rz_chances")) and team_rz:
            share = min(1.0, float(td["rz_chances"]) / team_rz)
            bits.append(f"{_pct(share)} of {off}'s red-zone chances")
        x = allowed.get(_TD_STAT.get(pos, "")) or {}
        funnel = None
        if x.get("rank") and x.get("of"):
            rank, of = int(x["rank"]), int(x["of"])
            funnel = rank <= TD_FUNNEL_RANK
            bits.append(f"{dfn} allows {_place(rank, of, 'most', 'fewest')} touchdowns to {_TD_WORD.get(pos, 'his position')}")
        usage = share is not None and share >= TD_USAGE_SHARE
        # THE TOUCHDOWN MATCHUP, SAID AS ONE (2026-11-15): his name wears
        # his whole matchup read's colour, which can differ from what this
        # defense gives up in touchdowns to his position.
        if usage and funnel:
            bits.append("his red-zone share and the touchdown matchup both back him")
        elif usage:
            bits.append("his red-zone share backs him")
        elif funnel:
            bits.append("the touchdown matchup backs him")
        meets = p >= 0.45 or (p >= 0.40 and usage)
        if meets:
            bits.append("meets our touchdown rule")
        rows.append((p, f"{r.get('player')} ({pos or '—'}): " + "; ".join(bits)))
    rows.sort(key=lambda x: -x[0])
    return [t for _p, t in rows[:TD_LIST]]


def sec_redzone(c: Ctx) -> dict | None:
    """THE RED ZONE, IN PLAIN WORDS (2026-11-14). Ethan circled two of these
    lines — "(23rd of 32, 1st the stingiest)" and "(0% below the league)" — and
    wrote that the reports' wording "doesn't make sense or is hard to read". A
    rank is said from its near end ("the 10th-worst rate"), a number near the
    league is "about average", and the red zone is "inside the 20"."""
    nums = c.scan.get("numbers") or {}
    rz = c.scan.get("redzone") or {}
    lines, marks = [], {}
    for off in c.teams:
        dfn = c.opp[off]
        o, d = (nums.get(off) or {}).get("rz_off") or {}, (nums.get(dfn) or {}).get("rz_def") or {}
        if _f(o.get("value")) is not None and _f(d.get("value")) is not None:
            of = o.get("of") or c.n_teams
            po = _place(o.get("rank"), of) if o.get("rank") else ""
            pd = _place(d.get("rank"), d.get("of") or of) if d.get("rank") else ""
            lines.append(f"{off} scores a touchdown on {_pct(o['value'])} of its trips inside the 20"
                         + (f" ({po} rate in the league)" if po else "")
                         + f". {dfn}'s defense gives up a touchdown on {_pct(d['value'])} of them"
                         + (f" ({pd})" if pd else "") + ".")
        ro, rd = rz.get(off) or {}, rz.get(dfn) or {}
        if ro.get("what") and _f(ro.get("off")) is not None and _f(rd.get("def")) is not None:
            # College's: drives that reach the opponent's 40, raw.
            rel_o, rel_d = _f(ro.get("off_rel")), _f(rd.get("def_rel"))
            vo, vd = _than_average(rel_o), _than_average(rel_d, who="defense")
            _than_marks(marks, vo, rel_o, vd, rel_d)
            lines.append(f"{off} gets about {_num(ro['off'])} drives a game to the opponent's 40"
                         + (f" ({vo})" if vo else "")
                         + f"; {dfn}'s defense allows about {_num(rd['def'])}" + (f" ({vd})" if vd else "") + ".")
        elif _f(ro.get("off")) is not None and _f(rd.get("def")) is not None:
            rel_o, rel_d = _f(ro.get("off_rel")), _f(rd.get("def_rel"))
            vo, vd = _than_average(rel_o), _than_average(rel_d, who="defense")
            _than_marks(marks, vo, rel_o, vd, rel_d)
            lines.append(f"{off} runs about {_num(ro['off'])} plays a game inside the opponent's 20"
                         + (f" ({vo})" if vo else "")
                         + f"; {dfn}'s defense allows about {_num(rd['def'])}" + (f" ({vd})" if vd else "")
                         + ". Both are adjusted for the teams they've played.")
        chances = sorted(((r.get("player"), _f((r.get("td") or {}).get("rz_chances")))
                          for r in c.reads_for(off)), key=lambda x: -(x[1] or 0))
        chances = [(p, v) for p, v in chances if p and v and v >= 0.3][:3]
        if chances:
            # NAMES FIRST (2026-11-15, "make the game report less confusing"):
            # the measure after them, once.
            lines.append(f"Who gets {off}'s chances inside the 20: "
                         + ", ".join(f"{p} (about {_num(v)})" for p, v in chances)
                         + " — carries and targets a game there, by our numbers.")
    blocks = [_list(lines)] if lines else []
    if blocks and marks:
        blocks[0]["marks"] = marks
    for off in c.teams:
        scorers = td_chance_lines(c, off)
        if scorers:
            blocks += [_h(f"Who can score for {c.name(off)}"), _list(scorers)]
    if not blocks:
        return None
    return _section("redzone", "Red zone", blocks)


#: The schedule notes' own heads (engine/fatigue.state_for), as the team's
#: sentence: "DET: Off a bye: 14 days…" read as two labels in a row.
REST_HEADS = (("Off a bye: ", "{t} comes off a bye: "), ("Short week: ", "{t} is on a short week: "),
              ("Rest edge: ", "{t} has the rest edge: "), ("Rest deficit: ", "{t} is short on rest: "),
              ("Body clock: ", "{t}'s body clock: "), ("Neutral site: ", "Neutral site: "))


def rest_words(t: str, opp, note: str) -> str:
    """"Off a bye: 14 days of rest and two weeks to prepare" for DET →
    "DET comes off a bye: 14 days of rest and two weeks to prepare";
    "the opponent's 7" names the opponent. A note with no known head is
    "DET: …" as before."""
    n = str(note or "")
    if opp:
        n = n.replace("the opponent's", f"{opp}'s")
    for head, said in REST_HEADS:
        if n.startswith(head):
            return said.format(t=t) + n[len(head):]
    return f"{t}: {n}"


def sec_context(c: Ctx) -> dict | None:
    lines = []
    fat = (c.result.get("fatigue") or {}).get("teams") or {}
    for t in c.teams:
        f = fat.get(t) or {}
        # The side with less rest says "Rest deficit", the other "Rest
        # edge" — the same fact twice; the edge is kept.
        notes = [str(n) for n in f.get("notes") or [] if n and not str(n).startswith("Rest deficit")]
        if f.get("rest_days") and f.get("rest_band") not in (None, "", "normal week") \
                and not any("days" in n for n in notes):
            notes.insert(0, f"{f['rest_days']} days of rest ({f['rest_band']})")
        for n in notes:
            line = rest_words(t, c.opp.get(t), n)
            if line not in lines:
                lines.append(line)
    spots = {}
    if c.sched_row is not None:
        try:
            from .spots import game_spots
            spots = {t: game_spots(c.sched, c.sched_row, t, c.staff) for t in c.teams}
        except Exception:                                    # noqa: BLE001
            spots = {}
    said_prime = said_rematch = False
    for t in c.teams:
        s = spots.get(t) or {}
        if s.get("primetime") and not said_prime:
            lines.append(f"Prime time: {s['primetime']}")
            said_prime = True
        if s.get("div_rematch") and not said_rematch:
            lines.append("A division rematch — the second meeting this season")
            said_rematch = True
        if s.get("long_trip") and not c.g.get("neutral_site"):
            lines.append(f"{t} travels {s['long_trip']}")
        if s.get("new_coach"):
            lines.append(f"{t} plays {s['new_coach']}")
        if s.get("altitude"):
            lines.append(f"{t} plays {s['altitude']}")
        if s.get("surface_switch"):
            lines.append(f"{t} plays on {s['surface_switch']}")
        if s.get("late_season"):
            lines.append(_sentence(s["late_season"]))
    pp = ((c.result.get("playoff_picture") or {}).get("teams") or {})
    for t in c.teams:
        r = pp.get(t) or {}
        if r.get("note"):
            lines.append(f"{t}: {r['note']}")
        elif r.get("status") and r.get("status") != "in the hunt":
            lines.append(f"{t}: {r['status']}")
    calls = tendency_lines(c)
    blocks = [_list(lines)]
    if calls:
        blocks += [_h("How the coaches call it"), _list(calls),
                   {"type": "note", "text": "Fourth downs count at 2 yards or fewer to go, past the team's own "
                                            "30, with its win chance between 10% and 90%; pass rates leave out "
                                            "the last two minutes of each half. From this season's "
                                            "play-by-play."}]
    return _section("context", "Coaching and the schedule", blocks)


def tendency_lines(c: Ctx) -> list:
    """Each team's calls this season (engine/gamescan.season_numbers'
    counts): fourth-and-short, two-point tries, and how often it passes
    two scores up and two scores down."""
    out = []
    for t in c.teams:
        n = (c.scan.get("numbers") or {}).get(t) or {}
        k = n.get("counts") or {}
        if not k.get("weeks"):
            continue
        bits = []
        if k.get("go4_opps"):
            r = n.get("go4_rate") or {}
            bits.append(f"went for it on {k.get('go4_att', 0)} of {_count(k['go4_opps'], 'fourth-and-short')}"
                        + (f" ({_rank_word(r, 'most', 'least')} often)" if r.get("rank") else "")
                        + (f" and converted {k.get('go4_conv', 0)}" if k.get("go4_att") else ""))
        else:
            bits.append("has not faced a fourth-and-short in the balance")
        tries = int(k.get("two_pt_att") or 0)
        bits.append(f"tried {_count(tries, 'two-point conversion')} ({k.get('two_pt_conv', 0)} good)"
                    if tries else "has not tried a two-point conversion")
        lp, tp = n.get("lead_pass") or {}, n.get("trail_pass") or {}
        if _f(lp.get("value")) is not None:
            bits.append(f"passes on {_pct(lp['value'])} of plays up by 8 or more")
        if _f(tp.get("value")) is not None:
            bits.append(f"on {_pct(tp['value'])} down by 8 or more")
        out.append(f"{t} {_join(bits)}")
    return out


#: The simulator's six margin buckets (engine/drivesim.summary), home − away.
SIM_BUCKETS = (("home", 15, None), ("home", 8, 14), ("home", 1, 7),
               ("away", 1, 7), ("away", 8, 14), ("away", 15, None))


#: The game plan's script names (engine/gamescript.ARCHETYPES) in a
#: reader's words — the names stay in gamescript, where the fantasy page
#: shows them and gameplan.script_sign reads its leans.
SCRIPT_WORDS = {"everyone eats": "a high-scoring, close game, good for both offenses",
                "favorite runs, dog throws": "a high-scoring game with a clear favorite: the favorite "
                                             "runs the ball, the underdog throws",
                "floor, no ceiling": "a low-scoring game with a clear favorite",
                "nobody's good": "a low-scoring, close game"}

#: What one side's script says (gamescript.for_team's lean), plainly.
SCRIPT_LEANS = {"favored in a shootout — everyone eats": "favored in a high-scoring game that's good "
                                                         "for both offenses",
                "leads late and runs the clock — run volume up, pass volume a little down":
                    "expected to lead late and run out the clock: more runs, a few fewer passes",
                "expected to trail and throw — pass volume up, the run shelved":
                    "expected to trail and throw: more passes, fewer runs",
                "close game, both offenses stay in it": "in a close game where both offenses stay in it",
                "no favorite — the number says nothing about who leads":
                    "in a game with no favorite, so the line doesn't say who leads"}


def script_words(name) -> str:
    """"Everyone eats" → "a high-scoring, close game, good for both offenses";
    a name with no plain version is said as it is, lower-cased."""
    n = str(name or "").strip()
    return SCRIPT_WORDS.get(n.lower(), n[:1].lower() + n[1:])


def script_lean_words(line: str) -> str:
    """A game-plan line with its script lean said plainly: "DET favored in
    a shootout — everyone eats." → "DET favored in a high-scoring game
    that's good for both offenses."."""
    out = str(line or "")
    for old, new in SCRIPT_LEANS.items():
        out = out.replace(old, new)
    return out


def confidence_words(conf) -> str:
    """" (moderate confidence)"; the high band's own sentence ("high —
    favorites this size win ~79%") read "(high — favorites this size win
    ~79% confidence)" — it is " (high confidence: favorites this size win
    about 79% of the time)"; the coin flip says not to lean on it."""
    s = str(conf or "").strip()
    if not s:
        return ""
    if s.startswith("high"):
        import re
        m = re.search(r"(\d+)%", s)
        return (f" (high confidence: favorites this size win about {m.group(1)}% of the time)" if m
                else " (high confidence)")
    if s.startswith("coin flip"):
        return " (a coin flip, so don't lean on it)"
    return f" ({s} confidence)"


#: ETHAN'S FOUR SCRIPTS (his NFL Bet checking method, rule 6: "Build several
#: realistic scripts before choosing props … Then determine whether the prop
#: survives multiple realistic scripts. Prefer props that can hit under
#: multiple scripts"), each a share of the simulator's games: A the favorite
#: by 8–14, B the underdog wins, C the favorite by 1–7, D the favorite by 15+.
SCRIPT_KEYS = ("A", "B", "C", "D")
_RUSH = ("rush_yds", "rush_att")
_AIR = ("pass_yds", "pass_att", "pass_cmp", "receptions", "rec_yds", "rush_rec_yds")
#: Which scripts an over holds in, by who he plays for and what he does: a
#: favorite's back runs out a lead (A, C, D); an underdog's runs only while
#: it is close or ahead (B, C); a favorite throws when it trails or it is
#: close, and its starters sit in a blowout (A, B, C); an underdog throws
#: from behind and in garbage time (A, C, D). An under holds where the over
#: does not.
SCRIPT_FIT = {("fav", "run"): "ACD", ("dog", "run"): "BC", ("fav", "air"): "ABC", ("dog", "air"): "ACD"}


def script_shares(c: Ctx) -> tuple | None:
    """(favorite, underdog, {A: share, …}) off the simulator, or None."""
    hist = (c.g.get("sim") or {}).get("margin_hist") or []
    if len(hist) != len(SIM_BUCKETS):
        return None
    try:
        by = {(side, lo): float(p) for (side, lo, _hi), p in zip(SIM_BUCKETS, hist)}
    except (TypeError, ValueError):
        return None
    home_win = by[("home", 15)] + by[("home", 8)] + by[("home", 1)]
    fav, dog = (c.home, c.away) if home_win >= 0.5 else (c.away, c.home)
    f = "home" if fav == c.home else "away"
    d = "away" if f == "home" else "home"
    return fav, dog, {"A": by[(f, 8)], "B": by[(d, 1)] + by[(d, 8)] + by[(d, 15)], "C": by[(f, 1)],
                      "D": by[(f, 15)]}


def script_fit(market, side, team, fav) -> str:
    """The scripts (of "ABCD") a pick holds in, or "" when the method's
    scripts say nothing about its market."""
    m = str(market or "")
    kind = "run" if m in _RUSH else "air" if m in _AIR else ""
    if not kind:
        return ""
    over = SCRIPT_FIT[("fav" if team == fav else "dog", kind)]
    s = str(side or "").lower()
    if s in ("over", "yes"):
        return over
    if s == "under":
        return "".join(k for k in SCRIPT_KEYS if k not in over)
    return ""


def script_blocks(c: Ctx) -> list:
    """The four scripts with their shares and who each one feeds, then the
    game's picks by how many scripts they hold in."""
    got = script_shares(c)
    if not got:
        return []
    fav, dog, share = got
    mine = {t: c.reads_for(t) for t in c.teams}

    def lead_back(t):
        backs = [r for r in mine[t] if str(r.get("pos") or "").upper() in ("RB", "FB")
                 and (_usage(r).get("carry_share") or 0) > 0]
        return max(backs, key=lambda r: _usage(r).get("carry_share") or 0).get("player") if backs else ""

    def targets(t, n=2):
        rec = sorted((r for r in mine[t] if (_usage(r).get("tgt_share") or 0) > 0),
                     key=lambda r: -(_usage(r).get("tgt_share") or 0))
        return [r.get("player") for r in rec[:n]]

    def qb(t):
        q = [r for r in mine[t] if str(r.get("pos") or "").upper() == "QB"]
        return q[0].get("player") if q else ""
    fb, ft, fq = lead_back(fav), targets(fav), qb(fav)
    db, dt, dq = lead_back(dog), targets(dog), qb(dog)
    who = {
        "A": (f"{fav} controls it", _join([x for x in (
            f"{fb}'s carries" if fb else "", f"{ft[0]}'s short targets" if ft else "") if x]
            or [f"{fav}'s run game"]) + (f" carry the volume, and {dq} throws late" if dq else " carry the volume")),
        "B": (f"{dog} leads", _join([x for x in (
            f"{dq}'s attempts" if dq else "", _join(f"{p}'s targets" for p in dt) if dt else "") if x]
            or [f"{dog}'s passing game"]) + " go up" + (f", and {fav} has to throw ({fq})" if fq else "")),
        "C": ("a close game", "steady volume for " + _join([p for p in (ft[:1] + dt[:1] + [fb, db]) if p]
                                                          or ["both offenses"])),
        "D": ("a blowout", f"{fav}'s starters can sit in the fourth"
              + (f", so {_join([p for p in (fb, ft[0] if ft else '') if p])} are at risk on overs"
                 if fb or ft else "")
              + (f", and {dog}'s garbage-time targets go to {dt[0]}" if dt else "")),
    }
    lines = [f"Script {k}, {who[k][0]} ({_pct(share[k])} of the simulated games): {who[k][1]}"
             for k in SCRIPT_KEYS]
    blocks = [_h("Four scripts"), _list(lines)]
    picks = []
    for r in c.reads:
        pk = r.get("pick") or (r.get("matchup_pick") if not (r.get("matchup_pick") or {}).get("held_note") else None)
        if not isinstance(pk, dict) or not pk:
            continue
        fit = script_fit(pk.get("market"), pk.get("side"), r.get("team"), fav)
        if not fit:
            continue
        w = sum(share[k] for k in fit)
        picks.append((len(fit), w, f"{r.get('player')}: {_pick_words(pk)} — holds in {_join(list(fit))} "
                                   f"({_pct(w)} of the simulated games)"))
    if picks:
        picks.sort(key=lambda x: (-x[0], -x[1]))
        blocks += [_h("Which picks hold up in the most scripts"), _list(p[2] for p in picks)]
    return blocks


def sec_scripts(c: Ctx) -> dict | None:
    blocks = []
    sc = (c.plan.get("script") or {})
    step = next((s for s in c.plan.get("steps") or [] if isinstance(s, dict) and s.get("key") == "line"), {})
    if sc.get("archetype"):
        blocks.append(_p(f"How the lines say this game is likeliest to go: {script_words(sc['archetype'])}"
                         + confidence_words(sc.get("confidence"))))
    plan_lines = [script_lean_words(str(x)) for x in step.get("lines") or [] if x][1:]
    if plan_lines:
        blocks.append(_list(plan_lines))
    sim = c.g.get("sim") or {}
    hist = sim.get("margin_hist") or []
    if len(hist) == len(SIM_BUCKETS):
        rows = []
        for (side, lo, hi), p in zip(SIM_BUCKETS, hist):
            team = c.home if side == "home" else c.away
            span = f"{lo}+" if hi is None else f"{lo}–{hi}"
            rows.append([f"{team} by {span}", _pct(p)])
        blocks.append({"type": "table", "title": "How the simulated games ended",
                       "head": ["Result", "Share"], "rows": rows,
                       "note": (f"{int(sim.get('trials') or 0):,} games played drive by drive from the "
                                "lines and both teams' numbers. A simulation, not a pick."
                                if sim.get("trials") else "A simulation, not a pick.")})
    bits = []
    if _f(sim.get("one_score")) is not None:
        bits.append(f"{_pct(sim['one_score'])} are decided by 8 points or fewer")
    if _f(sim.get("blowout")) is not None:
        bits.append(f"{_pct(sim['blowout'])} by 14 or more")
    if bits:
        blocks.append(_p(f"Of the simulated games, {_join(bits)}"))
    # ETHAN'S FOUR SCRIPTS AND THE PICKS THAT SURVIVE THEM (`script_blocks`).
    blocks += script_blocks(c)
    return _section("scripts", "How the game could go", blocks)


def _pick_words(p: dict) -> str:
    """"Over 4.5 receptions (−110, 62%)" — one board row as a read's card says it."""
    side = str(p.get("side") or "").strip().lower()
    side = "Over" if side in ("over", "yes") else "Under" if side in ("under", "no") else side.capitalize()
    line = _f(p.get("line"))
    what = str(p.get("market_label") or p.get("market") or "").replace("_", " ").lower()
    bits = [b for b in (_odds(p.get("odds")), _pct(p.get("model_prob"))) if b]
    return " ".join(x for x in (side, f"{line:g}" if line is not None else "", what) if x) + (
        f" ({', '.join(bits)})" if bits else "")


def read_pick(r: dict) -> str:
    """WHAT THE BOARD DID WITH THIS READ, in one line (Ethan, 2026-11-14: "it
    would not make any sense to make players favoitable and breakout
    canidates and not give them props and some for players we thinnk will do
    bad, it doesnt make sense to not take the unders"): his Most Likely pick
    on the read's side (engine/gamescan.stamp_picks), else his matchup pick
    there (engine/matchpicks.stamp_reads — every read the data backs has
    one) with the one board's word on it, else the list's pick the other
    way, else why the data does not back a bet on the read — never a forced
    pick (Ethan: "we wanna make sure we are not forcing picks and bets").
    "" when none of his props is priced."""
    if not isinstance(r, dict):
        return ""
    if r.get("pick"):
        take = take_at(r["pick"].get("model_prob"))
        return f"Most Likely pick: {_pick_words(r['pick'])}" + (f" — take it at {take}" if take else "")
    mp = r.get("matchup_pick")
    if isinstance(mp, dict) and mp:
        # Held back by the one board (the NFL's 60%: Ethan, "hold them
        # back"), and said so (engine/likelyboard._read_picks_follow_the_board).
        if mp.get("held_note"):
            why = str(mp["held_note"])
            why = why[len("held back:"):].strip() if why.lower().startswith("held back:") else why
            return f"Matchup pick, held back: {_pick_words(mp)} — {why}"
        tier = f" ({mp['tier_label']})" if mp.get("tier_label") else ""
        take = take_at(mp.get("model_prob"))
        return f"Matchup pick{tier}: {_pick_words(mp)}" + (f" — take it at {take}" if take else "")
    if r.get("pick_other_side"):
        return (f"Our Most Likely pick on him goes the other way: {_pick_words(r['pick_other_side'])} — "
                f"our number disagrees with this read")
    # NO FORCED PICK (engine/matchpicks.not_backed): why the data does not
    # back a bet on the read.
    if (r.get("read_no_pick") or {}).get("why"):
        return f"No pick: {r['read_no_pick']['why']}"
    best = ((r.get("no_pick") or {}).get("best")) or {}
    p = _f(best.get("model_prob"))
    if p is not None and p < 0.5:
        return (f"No pick: our number disagrees with this read — his likeliest "
                f"{'over' if str(best.get('side')).lower() == 'over' else 'under'} is {_pick_words(best)}")
    return ""


def sec_watch(c: Ctx) -> dict | None:
    shine = sorted((r for r in c.reads if r.get("read") in ("breakout", "good")),
                   key=lambda r: (r.get("read") != "breakout", -_volume(r)))
    struggle = sorted((r for r in c.reads if r.get("read") in ("tough", "avoid") and _is_key(r)
                       and not _go_to(r)),
                      key=lambda r: (r.get("read") != "avoid", -_volume(r)))

    def item(r, tone):
        why = [str(x) for x in (r.get("pro") if tone == "up" else r.get("con")) or [] if x][:2]
        out = {"player": r.get("player"), "team": r.get("team"), "pos": r.get("pos"),
               "headshot": r.get("headshot") or "", "tone": tone,
               "label": r.get("label") or "", "role": _role_line(r),
               "text": " ".join(_sentence(w) for w in why)}
        # HIS PICK ON THE READ'S SIDE (`read_pick`).
        pick = read_pick(r)
        if pick:
            out["pick"] = pick
        # MAY SIT (engine/availability): the mark beside his read, and why,
        # before anything the read says.
        if r.get("availability"):
            from .availability import LABELS
            out["status"] = LABELS.get(r["availability"], "")
            out["text"] = (_sentence(r.get("availability_note") or "") + " " + out["text"]).strip()
        # A key player's season is on his card under "Who's guarding
        # who" already; the rest carry theirs here.
        if not _is_key(r):
            out["form"] = form_lines(c, r)
        return out
    blocks = []
    if shine:
        blocks += [_h("Could shine"), {"type": "players", "items": [item(r, "up") for r in shine[:6]]}]
    if struggle:
        blocks += [_h("Could struggle"), {"type": "players", "items": [item(r, "down") for r in struggle[:4]]}]
    if c.reads and not shine:
        blocks.append(_p("No one in this game reads as a breakout candidate or a good matchup"))
    blocks += no_play_blocks(c)
    blocks += role_blocks(c)
    return _section("watch", "Players to watch", blocks)


#: How many of the closest candidates a game with no qualifying play names.
CLOSEST_N = 3


def no_play_blocks(c: Ctx) -> list:
    """NEVER FORCE A BET (Ethan's NFL Bet checking method, rule 26: "If
    nothing clears the thresholds: No qualifying plays at current lines.
    Then list: closest candidates, current line, required line movement").
    A game whose reads carry no posted pick says so, then names the closest
    — each read's likeliest number on its side — with the price it would
    need. Nothing when a pick stands or no read was priced."""
    posted = [r for r in c.reads if r.get("pick") or ((r.get("matchup_pick") or {}) and
                                                     not (r.get("matchup_pick") or {}).get("held_note"))]
    if posted or not c.reads:
        return []
    near = []
    for r in c.reads:
        best = (r.get("no_pick") or {}).get("best") or {}
        p = _f(best.get("model_prob"))
        if p is None or not best.get("market"):
            continue
        take = take_at(p)
        near.append((p, f"{r.get('player')}: {_pick_words(best)}"
                        + (f" — worth it at {take}" if take and p >= 0.5 else " — our number is under even")))
    if not near:
        return []
    near.sort(key=lambda x: -x[0])
    return [_h("No qualifying plays at current lines"),
            _p("No pick in this game clears the bar at today's prices. Below are the closest, with the "
               "price each would need"),
            _list(t for _p, t in near[:CLOSEST_N])]


def role_blocks(c: Ctx) -> list:
    """The role changes the detector sees in this game (engine/rolechange,
    by way of the ideas file): his share before the change and since."""
    rows = ((c.ideas.get("role") or {}).get("rows")) or []
    lines = []
    for x in rows[:6]:
        before, after = _f(x.get("before")), _f(x.get("after"))
        n = int(x.get("games_ago") or 0)
        if before is None or after is None or not n:
            continue
        word = "up" if after > before else "down"
        lines.append(f"{x.get('player')} ({x.get('team')}): {str(x.get('label') or '').lower()} {word} to "
                     f"{_pct(after)} over his last {_plural(n, 'game')}, from {_pct(before)} before — the "
                     f"detector is {_pct(x.get('changed'))} sure the change is real")
    if not lines:
        return []
    held = any(x.get("holds") for x in rows)
    note = ("The detector reads each player's weekly share for a break in it. "
            + ("It beat the four-week average on held-out seasons, so the board reads it."
               if held else "It has not yet beaten the four-week average on held-out seasons, so "
                            "this is a reading — nothing on the board moves on it."))
    return [_h("Roles on the move"), _list(lines), {"type": "note", "text": note}]


def sec_weather(c: Ctx) -> dict | None:
    g = c.g
    w = g.get("weather") or {}
    cond = g.get("conditions") or {}
    st = g.get("stadium") or {}
    lines = []
    indoors = w.get("dome") or g.get("indoor") or str(g.get("roof") or "").lower() in ("dome", "closed")
    if indoors:
        lines.append(st.get("plays") or "Indoors — no weather")
    elif w.get("forecast"):
        # A forecast only: the build's placeholder (measured False) and
        # today's conditions are never the game's (engine/weather, #92).
        bits = []
        if _f(w.get("temp_f")) is not None:
            bits.append(f"{_num(w['temp_f'], 0)}°F")
        if _f(w.get("wind_mph")) is not None:
            bits.append(f"wind {_num(w['wind_mph'], 0)} mph" + (f" from the {w['wind_dir']}" if w.get("wind_dir") else ""))
        if _f(w.get("precip_chance")) is not None and w["precip_chance"] > 0:
            bits.append(f"{_pct(w['precip_chance'])} chance of rain")
        if w.get("snow"):
            bits.append("snow")
        elif w.get("rain"):
            bits.append("rain")
        if bits:
            lines.append("Forecast for kickoff: " + ", ".join(bits))
    if not indoors and st.get("plays"):
        lines.append(st["plays"])
    for why in cond.get("why") or []:
        # Indoors is said once (the venue's own line), never twice.
        if why and why not in lines and not (indoors and ("dome" in str(why).lower() or "indoor" in str(why).lower())):
            lines.append(str(why))
    lines += kick_lines(c)
    return _section("weather", "Weather and venue", [_list(lines)])


def kick_lines(c: Ctx) -> list:
    """The kicking air (engine/kickphysics.conditions): said for an outdoor
    game with a real forecast, or for any game a thousand feet up — an
    indoor game at sea level kicks in the air every other one does."""
    k = c.ideas.get("kicks") or {}
    dev = _f(k.get("density_dev"))
    if dev is None:
        return []
    w = c.g.get("weather") or {}
    alt = _f(k.get("altitude_ft")) or 0.0
    if not ((not k.get("dome") and w.get("forecast")) or alt >= 1000):
        return []
    where = ["indoors"] if k.get("dome") else (
        [f"{_num(k['temp_f'], 0)}°F"] if _f(k.get("temp_f")) is not None else [])
    if alt >= 1000:
        where.append(f"{int(alt):,} feet up")
    if abs(dev) < 0.02:
        feel = "close to sea-level air, so kicks fly about as they do anywhere"
    elif dev < 0:
        feel = (f"{_pct(abs(dev))} thinner than air at sea level, so kicks carry "
                f"{'noticeably ' if dev <= -0.08 else ''}farther")
    else:
        feel = (f"{_pct(dev)} denser than air at sea level, so kicks die "
                f"{'noticeably ' if dev >= 0.08 else ''}sooner")
    out = [f"Kicking air ({', '.join(where)}): {feel}" if where else f"Kicking air: {feel}"]
    if _f(k.get("plays_like_50")) is not None:
        out.append(f"A 50-yard try here plays like a {_num(k['plays_like_50'])}-yarder at sea level")
    wp = k.get("wind_parts") or {}
    if _f(wp.get("along")) is not None and _f(wp.get("across")) is not None:
        out.append(f"The wind runs about {_num(abs(wp['along']), 0)} mph along the field and "
                   f"{_num(abs(wp['across']), 0)} mph across it")
    return out


def sec_before(c: Ctx) -> dict | None:
    lines = []
    g = c.g
    try:
        if c.sport != "nfl":
            raise ValueError("no inactives list")
        hh, mm = (int(x) for x in str(g.get("kickoff") or "").split(":")[:2])
        t = _dt.datetime(2000, 1, 1, hh, mm) - _dt.timedelta(minutes=INACTIVES_BEFORE_MIN)
        lines.append(f"The inactive list comes out about {_clock(t.hour, t.minute)} ET, "
                     f"{INACTIVES_BEFORE_MIN} minutes before kickoff")
    except ValueError:
        pass
    for r in c.scan.get("injuries") or []:
        if isinstance(r, dict) and str(r.get("status") or "").upper() == "QUESTIONABLE":
            lines.append(f"{r.get('player')} ({r.get('team')}) is questionable"
                         + (f". {r['opens'][0].upper()}{r['opens'][1:]}" if r.get("opens") else ""))
    w = g.get("weather") or {}
    if w.get("forecast") and not w.get("dome"):
        lines.append("The forecast can still change; we use the forecast for kickoff, not today's weather")
    games = [((c.units.get(t) or {}).get("games")) for t in c.teams]
    if any(n is not None and n < 4 for n in games):
        lines.append("Small sample: " + _join(f"{t} has played {_plural(n, 'game')}"
                                               for t, n in zip(c.teams, games) if n is not None)
                     + " this season, so last season counts for more in every rank")
    if g.get("price_stale"):
        lines.append("The game lines on this page are older than the build — check the price "
                     "before you trust the market section")
    behind = (c.result.get("data_freshness") or {}).get("behind") or []
    if behind:
        lines.append(f"Not yet updated for the last week played: {_join(str(b) for b in behind)}")
    if c.sport == "nfl":
        # THE REFEREE ONCE HE IS NAMED (engine/nflrefs; Ethan's D, 2026-10-24),
        # with his games beside the league's and the measured caveat.
        from .nflrefs import words as _ref_words
        lines.append(_ref_words(g.get("officials") or {}) or OFFICIALS)
    return _section("before", "Before kickoff", [_list(lines)])


def sec_changes(c: Ctx) -> dict | None:
    """What changed since the report was first written, newest first
    (engine/reportlog). Nothing on the report's first build; one line when
    it has been rewritten and nothing a reader would call a change moved."""
    ch = c.changes or {}
    if not ch.get("first"):
        return None
    from .reportlog import when_words
    first = when_words(ch["first"])
    entries = [e for e in ch.get("entries") or [] if isinstance(e, dict) and e.get("changes")]
    if not entries:
        if ch.get("at") in (None, ch["first"]):
            return None
        return _section("changes", "What changed", [_p(
            f"Nothing has moved since we first wrote this report ({first} ET): the line, the injury "
            "report, the forecast and the reads are where they were")])
    blocks = [_p(f"What has moved since we first wrote this report ({first} ET), newest first")]
    for e in reversed(entries):
        blocks += [_h(f"{when_words(e.get('at'))} ET"), _list(e["changes"])]
    return _section("changes", "What changed", blocks)


# --- the short version, said in sentences ---------------------------------------------
# Ethan, 2026-10-22, at the Patriots–Bears short version on his phone: "we
# need to be more descriptive in the wording. It's very blunt." It read like
# a wire slip — "CHI by 3 at home, total 50.5", "Out: T.J. Edwards (CHI
# LB)", "Last meeting: 2024 week 10 at CHI: NE won 19-3 · CHI −6.5, NE
# covered". Each line is a sentence now: the teams by name, a position in
# words, and what the number means. The facts are the same facts, from the
# same places; nothing is said that the sections below do not hold, and a
# player still never carries a line, a price or a chance.

#: A position in words, per league.
_GRIDIRON_POS = {
    "QB": "quarterback", "RB": "running back", "HB": "running back", "FB": "fullback",
    "WR": "wide receiver", "TE": "tight end", "T": "tackle", "OT": "tackle", "LT": "left tackle",
    "RT": "right tackle", "G": "guard", "OG": "guard", "LG": "left guard", "RG": "right guard",
    "C": "center", "OL": "offensive lineman", "DE": "defensive end", "DT": "defensive tackle",
    "NT": "nose tackle", "DL": "defensive lineman", "EDGE": "edge rusher", "LB": "linebacker",
    "ILB": "inside linebacker", "OLB": "outside linebacker", "MLB": "middle linebacker",
    "CB": "cornerback", "LCB": "left cornerback", "RCB": "right cornerback", "NB": "nickel back",
    "NCB": "nickel back", "SCB": "slot cornerback", "DB": "defensive back", "S": "safety",
    "FS": "free safety", "SS": "strong safety", "K": "kicker", "P": "punter", "LS": "long snapper"}
POS_WORDS = {
    "nfl": _GRIDIRON_POS, "cfb": _GRIDIRON_POS,
    "nba": {"G": "guard", "F": "forward", "C": "center", "PG": "point guard", "SG": "shooting guard",
            "SF": "small forward", "PF": "power forward", "G-F": "guard", "F-G": "forward",
            "F-C": "forward", "C-F": "center"},
    "nhl": {"C": "center", "LW": "left wing", "RW": "right wing", "W": "wing", "F": "forward",
            "D": "defenseman", "G": "goalie"},
    "mlb": {"SP": "starting pitcher", "RP": "reliever", "P": "pitcher", "C": "catcher",
            "1B": "first baseman", "2B": "second baseman", "3B": "third baseman", "SS": "shortstop",
            "LF": "left fielder", "CF": "center fielder", "RF": "right fielder", "OF": "outfielder",
            "DH": "designated hitter", "IF": "infielder", "UT": "utility man"},
}
POS_WORDS["wnba"] = POS_WORDS["nba"]
POS_WORDS["cbb"] = POS_WORDS["nba"]

#: The verbs a scan's reason puts right after a team's code, and the form
#: a club's plural nickname takes: "GB gives up" → "the Packers give up".
#: A word not listed is left as written, so a noun is never bent.
_CLUB_VERBS = {"is": "are", "has": "have", "was": "were", "does": "do", "allows": "allow",
               "gives": "give", "shoots": "shoot", "concedes": "concede", "blitzes": "blitz",
               "stuffs": "stuff", "strikes": "strike", "starts": "start", "stacks": "stack",
               "ranks": "rank", "misses": "miss", "leans": "lean", "hits": "hit", "scores": "score",
               "plays": "play", "runs": "run", "throws": "throw", "takes": "take", "holds": "hold",
               "leads": "lead", "faces": "face", "averages": "average", "comes": "come",
               "turns": "turn", "wins": "win", "loses": "lose", "passes": "pass", "rushes": "rush",
               "sits": "sit", "gets": "get", "sees": "see", "uses": "use", "lets": "let",
               "leaks": "leak", "keeps": "keep", "needs": "need", "travels": "travel", "goes": "go"}


#: Ranks a reader says in words (AP style: first through ninth).
_ORDINAL_WORDS = {2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth", 7: "seventh",
                  8: "eighth", 9: "ninth"}


def pos_word(c: Ctx, pos, n: int = 1) -> str:
    """"running back", or "running backs" for two; "" for a code the
    league's table does not hold."""
    w = POS_WORDS.get(c.sport, _GRIDIRON_POS).get(str(pos or "").upper().strip(), "")
    if not w or n == 1:
        return w
    if w.endswith("man"):
        return w[:-3] + "men"
    return w[:-1] + "ies" if w.endswith("y") and w[-2] not in "aeiou" else w + "s"


#: Club names that are places, said without "the" (the NHL's Utah side
#: before it took a nickname: leaguereport.team_names).
PLACE_NAMES = {"Utah"}
#: Nicknames plural in use though not in spelling.
PLURAL_NAMES = {"Red Sox", "White Sox"}


def _the(c: Ctx, t: str) -> bool:
    """A club goes by its nickname with "the" ("the Lions", "the Heat"); a
    college by its school ("Indiana", and in basketball "Duke has", never
    "the Duke have"); a code with no name stands alone."""
    return c.sport not in ("cfb", "cbb") and c.name(t) != t and c.name(t) not in PLACE_NAMES


def _many(c: Ctx, t: str) -> bool:
    """Whether the team takes a plural verb: "the Lions are", but "the Heat
    is" and "Indiana is" — a nickname that is not plural in form is said
    the way it is spelled."""
    n = c.name(t)
    return _the(c, t) and (n.endswith("s") or n in PLURAL_NAMES)


def team_np(c: Ctx, t: str) -> str:
    """"the Lions", "the Heat", "Indiana", or the code where no name is known."""
    return f"the {c.name(t)}" if _the(c, t) else c.name(t)


def team_owner(c: Ctx, t: str) -> str:
    """"the Lions'", "the Heat's", "Indiana's"."""
    return f"the {c.poss(t)}" if _the(c, t) else c.poss(t)


def team_be(c: Ctx, t: str, plural: str = "are", singular: str = "is") -> str:
    return plural if _many(c, t) else singular


def cap(text: str) -> str:
    text = str(text or "")
    return text[:1].upper() + text[1:]


def _an(word: str) -> str:
    """"a 126.5" / "an 80.4" / "an 11": the article a number is read with."""
    w = str(word)
    return f"{'an' if w.startswith('8') or w.split('.')[0] in ('11', '18') else 'a'} {w}"


def named(c: Ctx, text: str) -> str:
    """A scan sentence with each team's code said as the team: "GB gives up
    the 2nd-most" → "the Packers give up the second-most"; "DET's defense"
    → "the Lions' defense"; "MIA's defense" → "the Heat's defense"; a
    college's code becomes its school. A verb after the code turns plural
    only for a plural nickname; a word not in `_CLUB_VERBS` is never bent."""
    import re
    out = str(text or "")
    for t in c.teams:
        if not t or c.name(t) == t:
            continue
        np_, own = team_np(c, t), team_owner(c, t)
        out = re.sub(rf"\b{re.escape(t)}'s\b", own, out)
        if _many(c, t):
            def verb(m, np_=np_):
                return f"{np_} {m.group(1) or ''}{_CLUB_VERBS[m.group(2)]}"
            out = re.sub(rf"\b{re.escape(t)} ((?:[a-z]+ly )?)({'|'.join(_CLUB_VERBS)})\b", verb, out)
        out = re.sub(rf"\b{re.escape(t)}\b", np_, out)
    # "the 1st-most" is "the most" said aloud, and "the 6th-most" is "the
    # sixth-most": first to ninth in words, as a reader says them.
    out = re.sub(r"\bthe 1st-(most|fewest|best|worst|highest|lowest)\b", r"the \1", out)
    return re.sub(r"\bthe ([2-9])(?:nd|rd|th)-", lambda m: f"the {_ORDINAL_WORDS[int(m.group(1))]}-", out)


def _known_names(c: Ctx) -> set:
    """Every name this game's report can open a reason on: the players in
    the reads, the injury report, the corners, the starting pitchers and
    the goalies, and the two teams."""
    if getattr(c, "_known", None) is None:
        names = {r.get("player") for r in c.reads}
        names |= {r.get("player") for r in c.scan.get("injuries") or [] if isinstance(r, dict)}
        for room in (c.scan.get("coverage") or {}).values():
            names |= {cn.get("name") for cn in (room or {}).get("corners") or [] if isinstance(cn, dict)}
        for p in ((c.g.get("pitchers") or {}).values()):
            if isinstance(p, dict):
                names.add(p.get("name"))
        for tape in ("mlb_tape", "nhl_tape"):
            for side in ((c.g.get(tape) or {}).get("sides") or {}).values():
                st = (side or {}).get("starter")
                names.add(st.get("name") if isinstance(st, dict) else st)
        # And the teams themselves: a college's reason opens on its school.
        names |= {c.name(t) for t in c.teams}
        c._known = {str(n) for n in names if n}
    return c._known


def _clause(text: str, names=()) -> str:
    """A reason as the end of a sentence: no full stop, and its first
    letter small — "Takes 69% of the carries" → "takes 69% …", "A soft
    corner" → "a soft corner", "Faces Jeremy Swayman" → "faces …" — unless
    it opens on a code ("CHC strikes out") or on a player the report names
    ("Zack Wheeler holds righties …")."""
    t = str(text or "").strip().rstrip(".")
    words = t.split()
    if not words or not t[0].isupper() or (words[0].isupper() and len(words[0]) > 1):
        return t
    if any(t.startswith(n) for n in names or ()):
        return t
    return t[0].lower() + t[1:]


def _slate_spot(c: Ctx) -> str:
    """Where this game's total sits among the board's: "the highest total
    on the board", "the third-lowest total on the board" — only at either
    end of a board of six games or more, where it says something."""
    tot = _f(c.g.get("total"))
    totals = [v for v in (_f((x or {}).get("total")) for x in c.result.get("games") or []
                          if isinstance(x, dict)) if v is not None]
    if tot is None or len(totals) < 6:
        return ""
    for n, end in ((sum(1 for v in totals if v > tot), "highest"), (sum(1 for v in totals if v < tot), "lowest")):
        if n <= 2:
            return f"the {('', 'second-', 'third-')[n]}{end} total on the board"
    return ""


def market_sentence(c: Ctx) -> str:
    """The line as a reader says it: who is favored and by how much, the
    total and the score it points to, and the moneyline's chance with the
    book's cut taken out. Baseball and hockey lead with the moneyline —
    their spread is a fixed line a run or a goal and a half wide."""
    g = c.g
    sp, tot = _f(g.get("spread")), _f(g.get("total"))
    ml = ml_chances(c)
    unit = c.score_words
    fixed = FIXED_LINES.get(c.sport)
    spot = _slate_spot(c)
    total = (f"the total is {_num(tot)}" + (f" {unit}" if fixed else "")
             + (f", {spot}" if spot else "")) if tot is not None else ""
    if fixed:
        out, fav = [], None
        if ml:
            fav = max(ml, key=ml.get)
            out.append(_sentence(f"{cap(team_np(c, fav))} {team_be(c, fav)} the moneyline favorite"
                                 f"{'s' if _many(c, fav) else ''}, with {_an(_pct(ml[fav]))} chance to win "
                                 "once the book's cut is taken out"))
        rest = []
        if sp:
            rl = c.home if sp < 0 else c.away
            who = ("they" if _many(c, rl) else "it") if rl == fav else team_np(c, rl)
            rest.append(f"{who} {team_be(c, rl)} −{_num(abs(sp))} on the {fixed}")
        if total:
            rest.append(total)
        if rest:
            out.append(_sentence(cap(", and ".join(rest))))
        return " ".join(out)
    first = ""
    if sp is not None and sp == 0:
        first = "The books have this one as a pick'em"
    elif sp is not None:
        fav = c.home if sp < 0 else c.away
        where = (" at a neutral site" if g.get("neutral_site") or c.meta.get("neutral_site") else
                 " at home" if fav == c.home else " on the road")
        size = f"{_num(abs(sp))}-point favorite"
        first = (f"{cap(team_np(c, fav))} {team_be(c, fav)} "
                 f"{size + 's' if _many(c, fav) else _an(size)}{where}")
    parts = [x for x in (first, total) if x]
    if not parts:
        return ""
    s = (", and ".join(parts) if first else cap(total))
    pts = implied_points(c)
    if pts:
        hi = max(c.teams, key=lambda t: pts[t])
        lo = c.opp[hi]
        s += (f", which works out to about {c.name(hi)} {_n(pts[hi])}, {c.name(lo)} {_n(pts[lo])}"
              if _n(pts[hi]) != _n(pts[lo]) else f", about {_n(pts[hi])} {unit} each")
    s = _sentence(s)
    if ml:
        fav = max(ml, key=ml.get)
        s += (f" Take out the book's cut and the moneyline gives {team_np(c, fav)} "
              f"{_an(_pct(ml[fav]))} chance to win.")
    return s


def edge_sentence(c: Ctx, e: dict, first: bool = True) -> str:
    """One edge from the scan, said with what it means on the field. The
    first one says what the ranks are out of; the rest do not repeat it.

    THIS SEASON ALONE, where it sits far from the rank the edge stands on
    (engine/gamescan.now_said): "the Giants' run defense (30th; 13th this
    season alone)". The blend still decides the edge, as measured."""
    from .gamescan import now_said
    off, dfn = str(e.get("off") or ""), str(e.get("def") or "")
    try:
        ranks = {"off": int(e["off_rank"]), "def": int(e["def_rank"])}
    except (KeyError, TypeError, ValueError):
        return named(c, edge_words(c, e))

    def now_of(side):
        return now_said(ranks[side], e.get(f"{side}_now"), c.n_teams)

    def inner(side, w=""):
        """For inside the parentheses: "30th in the league; 13th this season alone"."""
        now = now_of(side)
        return f"{_ord(ranks[side])}{w}" + (f"; {_ord(now)} this season alone" if now else "")

    def bare(side):
        """For running text: "30th (13th this season alone)"."""
        now = now_of(side)
        return _ord(ranks[side]) + (f" ({_ord(now)} this season alone)" if now else "")

    where = (" in the country" if c.sport == "cfb" else " in the league") if first else ""
    ro_w, rd_w, ro, rd = inner("off", where), inner("def", where), inner("off"), inner("def")
    O, D, On, Dn = team_owner(c, off), team_owner(c, dfn), team_np(c, off), team_np(c, dfn)
    ahead = (e.get("gap") or 0) > 0
    unit = e.get("unit")
    if unit == "passing":
        return (f"{O} passing game ({ro_w}) faces {D} pass defense ({rd}), an edge for {On} through "
                "the air" if ahead else
                f"{D} pass defense ({rd_w}) should slow down {O} passing game ({ro})")
    if unit == "rushing":
        return (f"{O} run game ({ro_w}) faces {D} run defense ({rd}), so there is room to run for {On}"
                if ahead else
                f"{D} run defense ({rd_w}) should hold {O} run game ({ro}) in check")
    if unit == "explosive":
        return (f"{O} big plays ({ro_w}) meet a {c.name(dfn) if _the(c, dfn) else dfn} defense that gives "
                f"them up ({rd}), so {On} should find some chunk plays" if ahead else
                f"{D} defense limits big plays ({rd_w}) and {O} offense ranks {bare('off')} at making them, so "
                f"expect few chunk plays from {On}")
    if unit == "pressure":
        return (f"{O} pass protection ({ro_w}) faces {D} pass rush ({rd}), so {O} quarterback should "
                "have time to throw" if ahead else
                f"{D} pass rush ({rd_w}) faces {O} pass protection ({ro}), so expect pressure on {O} "
                "quarterback")
    if unit == "overall":
        return (f"{O} offense ({ro_w}) faces {D} defense ({rd}), an edge for {On}" if ahead else
                f"{D} defense ({rd_w}) faces {O} offense ({ro}), an edge for {Dn}")
    return named(c, edge_words(c, e))


def edge_though(c: Ctx, e: dict):
    """(clause, [players]) when a card on the edge's offence reads against
    it (engine/gamescan.crossing_reads), else None: the counted reason of
    the most-used such card, said after the edge — "so there is room to run
    for the Chiefs, though the Falcons give up the 6th-fewest rushing yards
    to running backs (68 a game)". Ethan, 12 November 2026, on the
    Commanders at the Giants: "room to run" over an UNFAVORABLE back, with
    nothing saying why, "doesn't make any sense". A card crossing the edge
    is said beside it, never left to contradict it."""
    from .gamescan import crossing_reads
    up = (e.get("gap") or 0) > 0
    against = sorted(crossing_reads(e, c.reads), key=lambda r: -_volume(r))
    for r in against:
        why = _best_reason(c, r, "down" if up else "up")
        if why:
            return _with_name(r.get("player"), why), [r.get("player") for r in against]
    return None


def _with_name(player, why: str) -> str:
    """A player's reason that says "his" without saying who — "though only 4
    catches in his last 2 games" (the edge's caveat, 2026-11-14) — names him:
    "though Matthew Golden has only 4 catches in his last 2 games"."""
    import re
    if not player or not why or str(player).split()[-1] in why or not re.search(r"\b(his|he|him)\b", why, re.I):
        return why
    w = why[0].lower() + why[1:]
    if w.startswith("only "):
        return f"{player} has {w}"
    return f"for {player}, {w}"


def _best_reason(c: Ctx, r: dict, tone: str) -> str:
    """The one reason a short line gives for a player: a matchup over his
    workload, and either over the game's line, which every player in the
    game shares."""
    pool = [str(x) for x in (r.get("pro") if tone == "up" else r.get("con")) or [] if x]
    if not pool:
        return ""

    def rank(x):
        low = x.lower()
        return (0 if any(w in low for w in ("most", "fewest", "allow", "give", "concede", "faces", "against"))
                else 2 if low.startswith("the lines expect") else 1)
    return _clause(named(c, short_reason(sorted(pool, key=rank)[0])), _known_names(c))


def short_reason(text: str) -> str:
    """A scan reason as the short version says it: the fact without the
    model's footnotes. "Kyle Monangai (RB) is out — 36% of the carries
    (12.7 a game) to go around; not enough games without him to measure
    who takes them · our projection counts it: +10% rushing yards" (the
    Patriots–Bears short version, 2026-10-22) → "with Kyle Monangai out,
    36% of the carries (12.7 a game) are up for grabs". The footnotes stay
    on the player's card below."""
    import re
    s = str(text or "").split(" · ")[0].split("; not enough games")[0].strip()
    m = re.match(r"^(.+?) \([A-Z]+\) is out — (.+) to go around$", s)
    return f"with {m.group(1)} out, {m.group(2)} are up for grabs" if m else s


def player_clause(c: Ctx, r: dict, tone: str, tag: bool = True) -> str:
    """"Jahmyr Gibbs, the Lions' running back and a breakout candidate —
    the Packers give up the second-most touchdowns to running backs"."""
    t = str(r.get("team") or "")
    pw = pos_word(c, r.get("pos"))
    who = f"{r.get('player')}" + (f", {team_owner(c, t)} {pw}" if pw and t else
                                   f" of {team_np(c, t)}" if t else "")
    if tag and r.get("read") == "breakout":
        who += " and a breakout candidate" if pw and t else ", a breakout candidate"
    why = _best_reason(c, r, tone)
    return f"{who} — {why}" if why else who


def _go_to(r: dict) -> bool:
    """His team's go-to scorer (engine/readlogic.mark_scorers)."""
    return bool(((r or {}).get("scoring") or {}).get("go_to"))


def season_tds(c: Ctx, r: dict) -> tuple:
    """(touchdowns, rushing, receiving, games) this season, off his logs —
    (None, None, None, None) without them."""
    t = ((c.form.get(r.get("player")) or {}).get("season")) or {}
    st, n = t.get("s") or {}, int(t.get("games") or 0)
    if not n:
        return None, None, None, None
    rush, rec = _n(st.get("rush_td")), _n(st.get("rec_td"))
    return rush + rec, rush, rec, n


def scorer_words(c: Ctx, r: dict) -> str:
    """"17 touchdowns in 9 games this season (13 rushing, 4 receiving);
    Duke's likeliest scorer by our touchdown numbers (48%), with Duke
    expected to score about 21" — a go-to scorer's line. Ethan,
    2026-11-14, of Duke's back at Miami: "he's probably their go-to guy to
    score ... the total's high in that game and it's expecting both teams
    to score"."""
    from .readlogic import scoring_words
    said = scoring_words(r, team_words=c.name(str(r.get("team") or "")))
    if not said:
        return ""
    tds, rush, rec, n = season_tds(c, r)
    if tds:
        split = ([f"{rush} rushing"] if rush else []) + ([f"{rec} receiving"] if rec else [])
        lead = (f"{_count(tds, 'touchdown')} in {_count(n, 'game')} this season"
                + (f" ({', '.join(split)})" if len(split) == 2 else ""))
        # The sentence opens on the team's name, which keeps its capital.
        return f"{lead}; {said}"
    return said


def scorer_sentence(c: Ctx) -> str:
    """The short version's touchdown read: each side's go-to scorer, with
    why. "" when neither side has one."""
    bits = []
    for t in c.teams:
        r = next((x for x in c.reads if x.get("team") == t and _go_to(x)), None)
        if not r:
            continue
        pw = pos_word(c, r.get("pos"))
        words = scorer_words(c, r)
        bits.append(f"{r.get('player')}" + (f", {team_owner(c, t)} {pw}" if pw else "")
                    + (f" — {words}" if words else ""))
    if not bits:
        return ""
    return _sentence("Likeliest to score: " + ". ".join([bits[0]] + [cap(b) for b in bits[1:]]))


def shine_lines(c: Ctx, reads: list, shine_n: int = 3, struggle_n: int = 2, key_only: bool = False) -> list:
    """Who could have a big day and who could have a hard one, each with
    the reason that says why."""
    out = []
    # A man who may sit is never the game's headline (engine/availability):
    # his card says why, in Players to watch.
    reads = [r for r in reads if not r.get("availability")]
    shine = [r for r in reads if r.get("read") in ("breakout", "good")]
    shine.sort(key=lambda r: (r.get("read") != "breakout", -_volume(r), -len(r.get("pro") or [])))
    if shine:
        out.append("Who could have a big day: " + ". ".join(player_clause(c, r, "up") for r in shine[:shine_n]))
    # A go-to scorer is not a man to have a hard day (engine/readlogic rule
    # 3): his card says the yards are tough and the touchdowns still his.
    struggle = [r for r in reads if r.get("read") in ("tough", "avoid") and (not key_only or _is_key(r))
                and not _go_to(r)]
    struggle.sort(key=lambda r: (r.get("read") != "avoid", -_volume(r), -len(r.get("con") or [])))
    if struggle:
        out.append("Who could have a hard day: " + ". ".join(player_clause(c, r, "down")
                                                             for r in struggle[:struggle_n]))
    return out


def absent_sentence(c: Ctx, rows: list, per_team: int = 5) -> str:
    """Who is out, team by team, in positions a reader says: "The Bears are
    without linebacker T.J. Edwards and defensive ends Dayo Odeyingbo and
    Montez Sweat; the Patriots are missing cornerback Carlton Davis III."
    A doubtful player is said as doubtful, never as out."""
    parts = []
    for t in c.teams:
        mine = [r for r in rows if r.get("team") == t][:per_team]
        if not mine:
            continue
        gone = [r for r in mine if "DOUBT" not in str(r.get("status") or "").upper()]
        maybe = [r for r in mine if "DOUBT" in str(r.get("status") or "").upper()]

        def grouped(rs):
            order, by = [], {}
            for r in rs:
                k = str(r.get("position") or "").upper()
                if k not in by:
                    order.append(k)
                by.setdefault(k, []).append(str(r.get("player") or ""))
            out = []
            for k in order:
                names = by[k]
                w = pos_word(c, k, len(names))
                out.append(f"{w} {_join(names)}" if w else _join(names))
            return _join(out)
        bits = []
        if gone:
            verb = "without" if not parts else "missing"
            bits.append(f"{team_np(c, t)} {team_be(c, t)} {verb} {grouped(gone)}")
        if maybe:
            n = len(maybe)
            bits.append(f"{grouped(maybe)} {'is' if n == 1 else 'are'} doubtful"
                        + ("" if gone else f" for {team_np(c, t)}"))
        parts.append(", and ".join(bits))
    return _sentence(cap("; ".join(parts))) if parts else ""


#: Small counts as a reader says them.
_COUNT_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


def line_sentence(c: Ctx) -> str:
    """"Two of the Patriots' starting offensive linemen are out (Alijah
    Vera-Tucker and Ben Brown), and they face the Bears' pass rush, which
    ranks 6th."

    Said when two or more of a team's starting linemen are out (the scan's
    `line_out`: the depth chart's starters and the ones the snap counts
    say started lately). The unit ranks above are season-long and cannot
    see a line that lost two starters this week, and that was the matchup
    all four of Ethan's Patriots–Bears research docs led with, 2026-10-22.
    Nothing is said about what it will do: measured over 2022-2025
    (oloutfit.py), a line missing starters held no effect in every season,
    and its quarterbacks were sacked less, not more."""
    lines = c.scan.get("line_out") or {}
    status = {str(r.get("player") or ""): str(r.get("status") or "").upper()
              for r in c.scan.get("injuries") or [] if isinstance(r, dict)}
    said = []
    for t in c.teams:
        names = [str(x).rsplit(" (", 1)[0] for x in lines.get(t) or [] if x]
        if len(names) < 2:
            continue
        maybe = any(status.get(n) == "DOUBTFUL" for n in names)
        s = (f"{cap(_COUNT_WORDS.get(len(names), str(len(names))))} of {team_owner(c, t)} starting offensive "
             f"linemen are {'out or doubtful' if maybe else 'out'} ({_join(names)})")
        rush = c.rank(c.opp[t], "def", "pressure")
        if rush:
            s += (f", and {'they face' if _many(c, t) else 'it faces'} {team_owner(c, c.opp[t])} pass rush, "
                  f"which ranks {_ord(rush)}")
        said.append(_sentence(s))
    return " ".join(said)


#: How a rest band reads for the rested side (engine/fatigue.rest_band).
REST_WORDS = {"off a bye": "come in off their bye", "extra days": "come in with extra rest"}


def rest_sentence(c: Ctx) -> str:
    """"The Lions come in off their bye: 14 days since their last game to
    the Packers' 7" — the side with more rest, how, and the gap."""
    fat = (c.result.get("fatigue") or {}).get("teams") or {}
    ra, rh = (fat.get(c.away) or {}).get("rest_days"), (fat.get(c.home) or {}).get("rest_days")
    if not ra or not rh or ra == rh:
        return ""
    more = c.away if ra > rh else c.home
    less = c.opp[more]
    band = (fat.get(more) or {}).get("rest_band")
    club = _many(c, more)
    lead = {"off a bye": "come in off their bye" if club else "comes in off its bye",
            "extra days": "come in with extra rest" if club else "comes in with extra rest"}.get(
        band, "come in better rested" if club else "comes in better rested")
    s = (f"{cap(team_np(c, more))} {lead}: {max(ra, rh)} days since {'their' if club else 'its'} last game "
         f"to {team_owner(c, less)} {min(ra, rh)}")
    if (fat.get(less) or {}).get("rest_band") == "short week":
        s += f", and {team_np(c, less)} {team_be(c, less)} on a short week"
    return _sentence(s)


def meeting_sentence(c: Ctx, m: dict) -> str:
    """The last meeting, told: who won, where, as favorite or underdog,
    whether it covered, and how the total went."""
    if m.get("round"):
        when = f"the {m['season']} {m['round']}"
    elif m.get("week") is None and m.get("day"):
        try:
            d = _dt.date.fromisoformat(str(m["day"])[:10])
            when = f"{d.strftime('%b')}. {d.day}, {d.year}"
        except ValueError:
            when = str(m["day"])
    else:
        when = f"week {m['week']} of {m['season']}"
    hs, as_ = _n(m.get("hs")), _n(m.get("as"))
    w = m.get("winner")
    if not w:
        s = f"The last time they met ({when}), they tied {hs}-{as_}"
    else:
        ws, ls = (hs, as_) if w == m.get("home") else (as_, hs)
        where = (" at a neutral site" if m.get("neutral") else
                 " at home" if w == m.get("home") else " on the road")
        s = f"The last time they met ({when}), {team_np(c, w)} won {ws}-{ls}{where}"
        sp = _f(m.get("spread_home"))
        if sp:
            fav = m.get("home") if sp < 0 else m.get("away")
            size = f"{_num(abs(sp))}-point"
            role = "favorite" if w == fav else "underdog"
            s += f" as {size} {role}s" if _many(c, w) else f" as {_an(size)} {role}"
            cov = m.get("covered")
            if w == fav and cov == "push":
                s += ", winning by exactly the spread"
            elif w == fav and cov and cov != w:
                s += ", but did not cover"
    tot, ou = _f(m.get("total")), m.get("ou")
    if tot is not None and ou:
        both = hs + as_
        s += ("; the " + _plural(both, "point") + (f" landed right on the {_num(tot)} total" if ou == "push" else
                                                   f" went {ou} the {_num(tot)} total"))
    return _sentence(s)


def turnover_sentence(c: Ctx) -> str:
    """Each side's turnover margin and rank, and where that sits in the
    league when it is near either end."""
    nums = c.scan.get("numbers") or {}
    rows = [(t, (nums.get(t) or {}).get("to_margin") or {}) for t in c.teams]
    if not all(_f(m.get("value")) is not None for _t, m in rows):
        return ""
    where = "the country" if c.sport == "cfb" else "the league"

    def end(m):
        try:
            r = int(m.get("rank"))
        except (TypeError, ValueError):
            return ""
        return "near the top" if r <= 5 else "near the bottom" if r > c.n_teams - 5 else ""
    (ta, ma), (tb, mb) = rows
    va, vb = _signed(ma["value"], 0), _signed(mb["value"], 0)
    rk = lambda m: f" ({_ord(m['rank'])})" if m.get("rank") else ""         # noqa: E731
    ea, eb = end(ma), end(mb)
    if va == vb and rk(ma) == rk(mb):
        s = (f"In turnover margin this season, {team_np(c, ta)} and {team_np(c, tb)} are both {va}{rk(ma)}"
             + (f", {ea} of {where}" if ea else ""))
    elif ea and ea == eb:
        s = (f"In turnover margin this season, {team_np(c, ta)} {team_be(c, ta)} {va}{rk(ma)} and "
             f"{team_np(c, tb)} {vb}{rk(mb)}, both {ea} of {where}")
    else:
        def one(t, v, m, e, verb=True):
            r = f" ({_ord(m['rank'])}{', ' + e + ' of ' + where if e else ''})" if m.get("rank") else ""
            return f"{team_np(c, t)}{' ' + team_be(c, t) if verb else ''} {v}{r}"
        s = f"In turnover margin this season, {one(ta, va, ma, ea)} and {one(tb, vb, mb, eb, verb=False)}"
    return _sentence(s)


def sim_sentence(c: Ctx) -> str:
    sim = c.g.get("sim") or {}
    if _f(sim.get("p_home_win")) is None:
        return ""
    ph = float(sim["p_home_win"])
    lead = c.home if ph >= 0.5 else c.away
    runs = f" {int(sim['trials']):,} times" if _f(sim.get("trials")) else ""
    s = (f"Our simulator, which plays the game out drive by drive{runs}, has {team_np(c, lead)} winning "
         f"{_pct(max(ph, 1 - ph))} of the time")
    bits = []
    if _f(sim.get("one_score")) is not None:
        bits.append(f"{_pct(sim['one_score'])} of the games are decided by 8 points or fewer")
    if _f(sim.get("blowout")) is not None:
        bits.append(f"{_pct(sim['blowout'])} by 14 or more")
    if bits:
        s += "; " + ", and ".join(bits)
    return _sentence(s)


def sec_short(c: Ctx, built: dict) -> dict | None:
    """The short version, written last from what the sections found — in
    sentences (see the note above `POS_WORDS`)."""
    items = []
    s = market_sentence(c)
    if s:
        items.append(s)
    edges = _edges(c)
    crossed = []
    if edges:
        said = []
        for i, e in enumerate(edges[:3]):
            s = edge_sentence(c, e, first=(i == 0))
            why = edge_though(c, e)
            if why:
                s += f", though {why[0]}"
                crossed.append({"unit": e.get("unit"), "off": e.get("off"), "players": why[1]})
            said.append(s)
        items.append("Where the matchup tilts: " + ". ".join([said[0]] + [cap(x) for x in said[1:]]))
    cov = c.scan.get("coverage") or {}
    soft, n_soft = [], 0
    from .gamescan import MIN_TARGETS, SOFT_RATING
    for t in c.teams:
        room = cov.get(t) or {}
        # EVERY STARTER PAST THE BAR, the worst first (the scan's `weakest`
        # is the first), and one who may sit says so. Ethan's Patriots–Bears
        # research, 2026-10-22, went at Jaylon Johnson (22 of 28 for 412
        # yards, a 131 rating) while this named only Tyrique Stevenson (139
        # on 17) and never said Stevenson was questionable.
        bad = sorted((cn for cn in room.get("corners") or []
                      if (cn.get("targets") or 0) >= MIN_TARGETS and _f(cn.get("rating")) is not None
                      and float(cn["rating"]) >= SOFT_RATING), key=lambda cn: -float(cn["rating"]))[:2]
        for i, w in enumerate(bad):
            spot = pos_word(c, w.get("spot")) or "corner"
            maybe = " (questionable)" if str(w.get("status") or "").upper() == "QUESTIONABLE" else ""
            if i == 0:
                soft.append(f"{team_owner(c, t)} {spot} {w['name']}{maybe} has allowed "
                            f"{_an(_num(w['rating']))} passer rating on {_plural(w['targets'], 'target')}")
            else:
                soft[-1] += f", and {spot} {w['name']}{maybe} {_an(_num(w['rating']))} on {_num(w['targets'])}"
            n_soft += 1
    if soft:
        items.append(_sentence(cap(f"The softest spot{'s' if n_soft > 1 else ''} in coverage: "
                                   + "; ".join(soft)))
                     + " A perfect passer rating is 158.3, so the receivers who line up across from "
                     + ("them have" if n_soft > 1 else "him have") + " the easier matchup.")
    items += shine_lines(c, c.reads, key_only=True)
    scorers = scorer_sentence(c)
    if scorers:
        items.append(scorers)
    par = parlay_sentence(c)
    if par:
        items.append(par)
    outs = [r for r in c.scan.get("injuries") or [] if isinstance(r, dict)
            and str(r.get("status") or "").upper() not in ("QUESTIONABLE", "")]
    gone = absent_sentence(c, outs)
    if gone:
        items.append(gone)
    line = line_sentence(c)
    if line:
        items.append(line)
    for q in c.result.get("qb_changes") or []:
        if isinstance(q, dict) and q.get("team") in c.teams and q.get("headline"):
            items.append(_sentence(cap(named(c, q["headline"]))))
    rest = rest_sentence(c)
    if rest:
        items.append(rest)
    if c.meetings:
        items.append(meeting_sentence(c, c.meetings[0]))
    to = turnover_sentence(c)
    if to:
        items.append(to)
    sim = sim_sentence(c)
    if sim:
        items.append(sim)
    sec = _section("short", "The short version", [_list(items)])
    if sec and crossed:
        # What engine/boardtruth reads before it counts a crossing (CROSSED):
        # each edge whose crossing cards the sentence answered.
        sec["crossed"] = crossed
    return sec


def sec_angles(c: Ctx) -> dict | None:
    """THE ANGLES (engine/angles; Ethan, 2026-11-14: "it looks at the
    player's defense and offense and tries to find good matchups ... it's
    very hard to find that information if we are giving it"). Where each
    defence leaks to the players this offence has — the top receiver, the
    tight end, the quarterback's legs against the blitz, the red-zone
    scorer — each with its number, its rank and the market it points at,
    first after the short version."""
    from .angles import for_game
    rows = for_game(c, c.angle_tables)
    if not rows:
        return None
    up = [r for r in rows if r.get("tone") == "up"]
    down = [r for r in rows if r.get("tone") == "down"]
    blocks = []
    if up:
        blocks += [_h("Where to look"), _list(f"{_sentence(r['text'])[:-1]} → {r['points_to']}" for r in up)]
    if down:
        blocks += [_h("Where to be careful"), _list(f"{_sentence(r['text'])[:-1]} → {r['points_to']}" for r in down)]
    blocks.append({"type": "note", "text": ("This season's games, from the box scores and the charting. Shown, not "
                                            "counted: the board's numbers price each defence against each position "
                                            "on their own measured scale.")})
    return _section("angles", "The angles", blocks)


def _game_parlays(c: Ctx) -> dict | None:
    from .gameparlays import for_game
    return for_game(c.result, c.home, c.away)


def sec_parlays(c: Ctx) -> dict | None:
    """THE PARLAYS FOR THIS GAME (engine/gameparlays; Ethan, 2026-11-14:
    "for each game ... make 4 3-leg parlays ... and 3 2-leg touchdown
    parlays ... do the same shit that the report's doing"). Four three-leg
    tickets and three scorer pairs off the board's own picks, each with
    its price to take it, the script it needs, its backups and caveats —
    and the record's word on same-game parlays."""
    from .gameparlays import card
    gp = _game_parlays(c)
    if not gp:
        return None
    blocks = []
    threes = [card(t, i, "three", c.sport) for i, t in enumerate(gp.get("threes") or [], 1)]
    if threes:
        blocks += [_h("Three-leg parlays"), {"type": "parlays", "kind": "three", "items": threes}]
    elif gp.get("threes_note"):
        blocks.append(_p(f"No three-leg parlay: {gp['threes_note']}"))
    pairs = [card(t, i, "scorers", c.sport) for i, t in enumerate(gp.get("scorers") or [], 1)]
    if pairs:
        blocks += [_h("Touchdown pairs" if c.sport in ("nfl", "cfb") else "Scorer pairs"),
                   {"type": "parlays", "kind": "scorers", "items": pairs}]
    elif gp.get("scorers_note"):
        blocks.append(_p(gp["scorers_note"]))
    if not blocks:
        return None
    note = ((c.result.get("game_parlays") or {}).get("note") or "")
    if note:
        blocks.append({"type": "note", "text": note})
    return _section("parlays", "Parlays for this game", blocks)


def parlay_sentence(c: Ctx) -> str:
    """The short version's parlay lines: the likeliest three-leg ticket and
    the likeliest scorer pair, each with its price to take it."""
    from .gameparlays import pick_words
    gp = _game_parlays(c)
    if not gp:
        return ""
    bits = []
    for key, word in (("threes", "Best three-leg parlay"),
                      ("scorers", "Best touchdown pair" if c.sport in ("nfl", "cfb") else "Best scorer pair")):
        t = next(iter(gp.get(key) or []), None)
        if t:
            bits.append(f"{word}: {' + '.join(pick_words(l) for l in t['legs'])} — {float(t['joint']):.0%} by our "
                        f"numbers, take it at {t['take_words']} or better")
    return _sentence(". ".join(bits)) if bits else ""


SECTIONS = (sec_angles, sec_facts, sec_meetings, sec_market, sec_rankings, sec_identity, sec_injuries,
            sec_matchups, sec_trenches, sec_redzone, sec_context, sec_scripts, sec_watch,
            sec_parlays, sec_weather, sec_before)


def _words(sections) -> int:
    n = 0

    def count(x):
        nonlocal n
        if isinstance(x, str):
            n += len(x.split())
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in ("type", "headshot", "verdict", "tone", "key", "names", "marks", "rank_of", "rank_skip"):
                    count(v)
        elif isinstance(x, list):
            for v in x:
                count(v)
    count(sections)
    return n


def build(g: dict, result: dict, *, allowed: dict | None = None, sched=None,
          staff: dict | None = None, names: dict | None = None, form: dict | None = None,
          meetings: list | None = None, ideas: dict | None = None, sport: str = "nfl",
          meta: dict | None = None, changes: dict | None = None,
          grades: dict | None = None, angles: dict | None = None) -> dict | None:
    """One game's report, or None for a row with no teams."""
    if not isinstance(g, dict) or not g.get("away") or not g.get("home"):
        return None
    c = Ctx(g, result, allowed=allowed, sched=sched, staff=staff, names=names,
            form=form, meetings=meetings, ideas=ideas, sport=sport, meta=meta, changes=changes,
            grades=grades, angles=angles)
    return finish(c, SECTIONS, sec_short)


#: The keys whose strings are names, codes or flags — never a sentence, so
#: `plain` leaves them as they are.
PLAIN_SKIP = frozenset(("type", "kind", "key", "player", "team", "headshot", "pos", "verdict", "tone",
                        "status", "href", "url", "id", "logo", "color", "side", "market", "game", "slug",
                        "names", "marks", "rank_of", "rank_skip"))


def plain(text: str) -> str:
    """ONE REPORT, PLAIN WORDS (Ethan, 2026-11-15: "the wording in these
    reports are confusing and doesn't make sense or is hard to read").
    Whatever a section or a league's report wrote, the reader gets:

      * "the 1st-most" as "the most", and "the 6th-most" as "the
        sixth-most" — first to ninth in words, as a reader says them;
      * "(0% above the league)" as "(about average)";
      * "(109 a game) (over 5 games)" as "(109 a game, over 5 games)";
      * no ", a game" left behind by a missing number, and no double
        spaces."""
    import re
    s = str(text)
    s = re.sub(r"\bthe 1st-(most|fewest|best|worst|highest|lowest|stingiest)\b", r"the \1", s)
    s = re.sub(r"\bthe ([2-9])(?:nd|rd|th)-", lambda m: f"the {_ORDINAL_WORDS[int(m.group(1))]}-", s)
    s = re.sub(r"\(0(?:\.0)?% (?:above|below|more than|fewer than|less than)[^()]*\)", "(about average)", s)
    s = re.sub(r"\(([^()]*\ba game)\) \((over [^()]*\bgames?)\)", r"(\1, \2)", s)
    s = re.sub(r",\s{2,}a game\b", "", s)
    return re.sub(r"(?<=\S) {2,}(?=\S)", " ", s)


def plain_all(x, key: str = ""):
    """`plain` over every sentence in a report's sections — not over the
    keys that hold names and codes (PLAIN_SKIP)."""
    if isinstance(x, str):
        return x if key in PLAIN_SKIP else plain(x)
    if isinstance(x, list):
        return [plain_all(v, key) for v in x]
    if isinstance(x, dict):
        return {k: (v if k in PLAIN_SKIP else plain_all(v, k)) for k, v in x.items()}
    return x


#: Keys that hold codes, flags or the passes' own marks, never words a reader
#: sees with a name in them.
_NOT_TEXT = frozenset(("type", "kind", "key", "headshot", "verdict", "tone", "status", "names", "marks",
                       "href", "url", "id", "logo", "color", "side", "market", "game", "slug", "rank_of",
                       "rank_skip"))


def _texts(x, key: str = "") -> list:
    """Every string a block shows (its items, cells, titles, card words,
    a card's player), for the passes below."""
    if isinstance(x, str):
        return [] if key in _NOT_TEXT else [x]
    if isinstance(x, list):
        return [t for v in x for t in _texts(v, key)]
    if isinstance(x, dict):
        return [t for k, v in x.items() if k not in _NOT_TEXT for t in _texts(v, k)]
    return []


def color_names(c: Ctx, sections: list) -> list:
    """WHO'S WHO, IN COLOUR, THE WHOLE WAY DOWN (Ethan, 2026-11-15: "Make the
    game report less confusing too I liked the names colored it made it
    easier to read"). The colours began on the lines that say who gets the
    ball; now every block that names a player with a read in this game
    carries his tone (NAME_TONE, `names`), so js/report.js colours him the
    same wherever the report says him: green for a breakout candidate or a
    favorable matchup, red for an unfavorable one, plain for a neutral one.
    A player ruled out or doubtful has no read on the page
    (engine/availability), so he is never coloured. Every league's report."""
    tones: dict = {}
    for t in c.teams:
        for name, v in name_tones(c, t, c.reads_for(t)).items():
            tones.setdefault(name, v)
    for sec in sections:
        for b in sec.get("blocks") or []:
            if not isinstance(b, dict):
                continue
            texts = _texts(b)
            said = {n: v for n, v in tones.items() if any(n in x for x in texts)}
            if said:
                b["names"] = said
    return sections


#: How many teams a rank in a report's sentences is out of, where the board
#: carries no scan of its own (the football boards' is ``Ctx.n_teams``): the
#: page colours a rank by its third of the league (js/report.js).
TEXT_RANK_OF = {"mlb": 30, "nba": 30, "wnba": 15, "cbb": 365, "nhl": 32}

#: The injury words, coloured where the injury list says them (`marks`):
#: out and doubtful in red, questionable in amber.
STATUS_TONE = {"out": "down", "doubtful": "down", "questionable": "warn"}


def mark_statuses(sections: list) -> list:
    """The status word on each injury line in its colour (2026-11-15) —
    the lists of the injuries section only, where every "out" is one."""
    import re
    for sec in sections:
        if sec.get("key") != "injuries":
            continue
        for b in sec.get("blocks") or []:
            if not isinstance(b, dict) or b.get("type") != "list":
                continue
            texts = _texts(b)
            marks = {w: t for w, t in STATUS_TONE.items() if any(re.search(rf"\b{w}\b", x) for x in texts)}
            if marks:
                b["marks"] = marks
    return sections


def finish(c: Ctx, sections_fns, short_fn) -> dict:
    """The report: every section that has something to say, the short
    version written last from what they found and put first, what changed
    under it. Shared by every league's report (engine/leaguereport)."""
    built = {}
    for fn in sections_fns:
        s = fn(c)
        if s:
            built[s["key"]] = s
    short = short_fn(c, built)
    moved = sec_changes(c)
    sections = plain_all([x for x in (short, moved) if x] + list(built.values()))
    words = _words(sections)
    color_names(c, sections)
    mark_statuses(sections)
    g = c.g
    return {"game": f"{c.away}@{c.home}", "away": c.away, "home": c.home, "sport": c.sport,
            "date": g.get("date") or "", "kickoff": g.get("kickoff") or "",
            "title": f"{c.name(c.away)} at {c.name(c.home)}",
            # What Share says beside the link: the kickoff and the line —
            # public facts only (js/report.js teaser).
            "when": kickoff_words(g.get("date") or "", g.get("kickoff") or ""),
            "line": line_words(c),
            "built_at": c.result.get("built_at") or "",
            "words": words, "minutes": max(1, round(words / WORDS_A_MINUTE)),
            # The league's size, for the page to colour a rank in a sentence
            # ("the Patriots' big plays (3rd in the league)") by its third.
            "rank_of": TEXT_RANK_OF.get(c.sport) or c.n_teams,
            "sections": sections}


def ideas_for(data: dict | None, home: str, away: str) -> dict:
    """The ideas file's per-game views the report reads (IDEAS), each
    role row marked with whether its detector has held out."""
    out: dict = {}
    secs = (data or {}).get("sections") or {}
    try:
        from .ideas import _section_fns
    except Exception:                                        # noqa: BLE001
        return out
    for name in IDEAS:
        sec = secs.get(name)
        if not sec:
            continue
        try:
            fn = _section_fns(name)[2]
            v = fn(sec, home, away) if fn else None
        except Exception:                                    # noqa: BLE001
            v = None
        if v:
            out[name] = v
    for x in (out.get("role") or {}).get("rows") or []:
        rd = (((secs.get("role") or {}).get("players") or {}).get(x.get("player")) or {}).get("reads") or {}
        x["holds"] = bool(((rd.get(x.get("share")) or {}).get("verdict") or {}).get("holds"))
    return out


def report_players(result: dict) -> dict:
    """{player: team} for every read on the board — whose form is read."""
    out: dict = {}
    for rd in (result.get("scan_reads") or {}).values():
        for r in (rd or {}).get("players") or []:
            if isinstance(r, dict) and r.get("player") and r.get("team"):
                out.setdefault(r["player"], r["team"])
    return out


def college_names(result: dict) -> dict:
    """{key: the school's short name} off the college board's own team
    table (cfb_build's ``teams``: ESPN's shortDisplayName as ``nick``)."""
    out = {}
    for abbr, meta in ((result or {}).get("teams") or {}).items():
        if isinstance(meta, dict):
            out[abbr] = meta.get("nick") or meta.get("name") or abbr
    return out


def attach(result: dict, *, allowed: dict | None = None, season: int | None = None,
           conn=None, ideas: dict | None = None, sport: str = "nfl", meta: dict | None = None,
           out=None, at: str | None = None) -> str:
    """``result["game_reports"]``: one report for every game on the board.
    ``conn`` reads the game logs and, for college, the meetings (the
    history database when none is given); ``ideas`` is this build's ideas
    file (engine/ideas.LAST when none is given; the NFL's only); ``meta``
    is {"AWAY@HOME": what the build knows of a game and the board leaves
    off} (college's neutral site and conference game). ``out`` is the
    board's public path: what changed is kept beside its private copy
    (engine/reportlog), stamped ``at`` (now, Eastern, when none is given);
    with no ``out`` nothing is kept and no report has the section. One
    line for the build log; never raises.

    ITS PARTS ON THE STAGE CLOCK (2026-11-10), as the "game reports" stage:
    3.0 seconds of the NFL build at 01:19 on 10 November and 11.1 at 02:00,
    one number either way, while the stages beside it held still."""
    import time as _time
    from . import stageclock as _clock
    _t = _time.monotonic()
    own = False
    try:
        sched = staff = None
        season = season or _season_of(result)
        if sport == "nfl":
            try:
                from . import spots
                sched = spots.load_schedule()
                staff = spots.staff_for(season, (season or 1) - 1) if season else {}
            except Exception:                                # noqa: BLE001
                sched, staff = None, {}
        names = _team_names() if sport == "nfl" else college_names(result)
        _t = _clock.lap("game reports", "schedule + staff", _t)
        try:
            if conn is None:
                from .db import connect
                conn, own = connect(), True
        except Exception:                                    # noqa: BLE001
            conn = None
        form = {}
        try:
            from . import reportdata
            form = reportdata.player_form(conn, season, report_players(result), sport=sport)
        except Exception:                                    # noqa: BLE001
            form = {}
        _t = _clock.lap("game reports", "player form", _t)
        # OUR GRADES (engine/grades; Ethan's D, 2026-10-24), the NFL's, over
        # the weeks before this board's — never a reason a report fails.
        grades = {}
        if sport == "nfl" and season:
            try:
                from . import grades as _grades
                grades = _grades.table(season, before_week=_week_of(result))
            except Exception:                                # noqa: BLE001
                grades = {}
        _t = _clock.lap("game reports", "grades", _t)
        # THE ANGLES' TABLES (engine/angles): this season's leaks by
        # defence, read once off the game logs.
        angle_tables = {}
        if sport == "nfl" and season and conn is not None:
            try:
                from . import angles as _angles
                angle_tables = _angles.nfl_tables(conn, season, before_week=_week_of(result))
            except Exception as exc:                         # noqa: BLE001
                # {} is also a season with no games logged yet, so the
                # failure says so; the reports still build without them.
                print(f"  ⚠️ the angles' tables not read ({exc})")
                angle_tables = {}
        _t = _clock.lap("game reports", "angles", _t)
        if ideas is None and sport == "nfl":
            try:
                from . import ideas as _ideas
                ideas = _ideas.LAST.get("nfl") or {}
            except Exception:                                # noqa: BLE001
                ideas = {}
        _kp = None
        if sport == "nfl":
            # College's stadium altitudes are not kept (kickphysics reads the
            # NFL's table, whose codes some schools share), so its kicking
            # air is not written.
            try:
                from . import kickphysics as _kp
                kfit, kbears = _kp.load("nfl"), _kp.bearings()
            except Exception:                                # noqa: BLE001
                _kp = None
        _t = _clock.lap("game reports", "ideas + kicking fit", _t)
        prepared = []
        for g in result.get("games") or []:
            if not isinstance(g, dict):
                continue
            home, away = str(g.get("home") or ""), str(g.get("away") or "")
            extra = ideas_for(ideas, home, away) if sport == "nfl" else {}
            if _kp is not None:
                try:
                    k = _kp.conditions(g, kfit, kbears)
                    if k:
                        extra["kicks"] = k
                except Exception:                            # noqa: BLE001
                    pass
            try:
                from . import reportdata as _rd
                met = (_rd.meetings(home, away, before=g.get("date") or "") if sport == "nfl" else
                       _rd.meetings_db(conn, sport, home, away, before=g.get("date") or ""))
            except Exception:                                # noqa: BLE001
                met = []
            prepared.append((g, extra, met))
        _t = _clock.lap("game reports", "meetings + kicking air", _t)
        logged = log_changes(result, [(g, extra, None) for g, extra, _met in prepared], sport, out, at)
        _t = _clock.lap("game reports", "what changed", _t)
        reports = []
        for g, extra, met in prepared:
            home, away = str(g.get("home") or ""), str(g.get("away") or "")
            r = build(g, result, allowed=allowed, sched=sched, staff=staff, names=names,
                      form=form, meetings=met, ideas=extra, sport=sport,
                      meta=(meta or {}).get(f"{away}@{home}"),
                      changes=logged.get(f"{away}@{home}|{str(g.get('date') or '')[:10]}"),
                      grades=grades, angles=angle_tables)
            if r:
                reports.append(r)
        _t = _clock.lap("game reports", "reports", _t)
        result[KEY] = reports
        if not reports:
            return "Game reports: no games on the board"
        return summary(reports, logged, out) + f"; form for {len(form)} player(s)"
    except Exception as exc:                                 # noqa: BLE001
        result.pop(KEY, None)
        return f"⚠️  Game reports skipped ({type(exc).__name__}: {exc})"
    finally:
        if own and conn is not None:
            try:
                conn.close()
            except Exception:                                # noqa: BLE001
                pass


def log_changes(result: dict, prepared: list, sport: str, out, at: str | None) -> dict:
    """WHAT CHANGED (engine/reportlog): this build's snapshot of every game
    (``prepared``: [(game, extra, more)] — ``more`` the league's own facts,
    a starter or an injury list the board does not carry), against the one
    kept beside the private board. {} with no ``out``; never raises."""
    if not out:
        return {}
    try:
        from . import reportlog as _log
        from .gate import _full_dir_for
        snaps = {_log.game_key(g): (_log.facts(g, result, extra, is_key=_is_key, more=more),
                                    str(g.get("home") or ""), str(g.get("away") or ""))
                 for g, extra, more in prepared if g.get("home") and g.get("away")}
        return _log.update(_log.path_for(sport, _full_dir_for(out)), snaps, at or _log.now_et())
    except Exception:                                        # noqa: BLE001
        return {}


def summary(reports: list, logged: dict, out) -> str:
    """The build log's line for a league's reports."""
    words = sum(r["words"] for r in reports)
    moved = sum(1 for v in logged.values()
                if v.get("entries") and v["entries"][-1].get("at") == v.get("at"))
    each = max(1, round(words / max(1, len(reports)) / WORDS_A_MINUTE))
    return (f"Game reports: {len(reports)} game(s), {words:,} words "
            f"(about {each} minute{'s' if each != 1 else ''} each)"
            + (f"; what changed: {moved} game(s) moved since the last build, "
               f"{len(logged)} tracked" if out else ""))


# --- reading one back -----------------------------------------------------------------
def to_text(report: dict) -> str:
    """The report as plain text — what the box prints and the tests read."""
    when = report.get("when") or f"{report.get('date')} {report.get('kickoff')} ET"
    out = [f"{report.get('title')} — {report.get('game')} · {when} · about {report.get('minutes')} min"]
    for s in report.get("sections") or []:
        out += ["", s["title"].upper()]
        for b in s.get("blocks") or []:
            t = b.get("type")
            if t in ("p", "note"):
                out.append(b["text"])
            elif t == "h":
                out.append(f"— {b['text']} —")
            elif t == "list":
                out += [f"  • {i}" for i in b["items"]]
            elif t == "table":
                out.append(f"  [{b.get('title') or ''}]")
                widths = [max(len(str(r[i])) for r in [b["head"]] + b["rows"]) for i in range(len(b["head"]))]
                for r in [b["head"]] + b["rows"]:
                    out.append("  " + "  ".join(str(x).ljust(w) for x, w in zip(r, widths)))
                if b.get("note"):
                    out.append(f"  ({b['note']})")
            elif t == "verdicts":
                for v in b["items"]:
                    out.append(f"  • {v['title']} = {v['label']}"
                               + (f" [{v['status']}]" if v.get("status") else "")
                               + (f" — {v['role']}" if v.get("role") else ""))
                    out += [f"      - {w}" for w in v.get("why") or []]
                    if v.get("pick"):
                        out.append(f"      {v['pick']}")
                    out += _form_text(v)
            elif t == "players":
                for v in b["items"]:
                    who = " ".join(str(x) for x in (v.get("team"), v.get("pos")) if x)
                    out.append(f"  • {v['player']}" + (f" ({who})" if who else "")
                               + (f" — {v['label']}" if v.get("label") else "")
                               + (f" [{v['status']}]" if v.get("status") else "")
                               + (f": {v['text']}" if v.get("text") else ""))
                    if v.get("pick"):
                        out.append(f"      {v['pick']}")
                    out += _form_text(v)
            elif t == "parlays":
                for v in b["items"]:
                    out.append(f"  • {v['title']}: {v.get('price_line') or ''}")
                    for leg in v.get("legs") or []:
                        out.append(f"      - {leg['pick']}" + (f" ({leg['price']})" if leg.get("price") else "")
                                   + (f", {float(leg['chance']):.0%}" if leg.get("chance") else "")
                                   + (f", our research score {leg['research']} of {leg.get('research_of')}"
                                      if leg.get("research") is not None else ""))
                        out += [f"          · {w}" for w in leg.get("why") or []]
                    if v.get("script"):
                        out.append(f"      {v['script']}")
                    if v.get("rule_note"):
                        out.append(f"      {v['rule_note']}")
                    out += [f"      Backup: {x}" for x in v.get("backups") or []]
                    out += [f"      Caveat: {x}" for x in v.get("caveats") or []]
    return "\n".join(out)


def _form_text(v: dict) -> list:
    out = []
    for label, lines in v.get("form") or []:
        out.append(f"      · {label}: {' | '.join(lines)}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Print the game reports from the NFL board.")
    ap.add_argument("--board", default="web/data/recommendations.json",
                    help="the board's public path; the full copy beside it is read")
    ap.add_argument("--game", default="", help="a team on the game (e.g. DET); default: a list")
    args = ap.parse_args(argv)
    try:
        from .gate import board_source
        path = board_source(args.board)
    except Exception:                                        # noqa: BLE001
        path = Path(args.board)
    try:
        board = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        print(f"Could not read {path}: {exc}")
        return 1
    reports = board.get(KEY) or []
    if not reports:
        print(f"No game reports on {path} — the board predates them or the build skipped them.")
        return 1
    team = args.game.upper()
    if not team:
        for r in reports:
            print(f"{r['game']:10} {r['date']} {r['kickoff']}  {len(r['sections'])} sections, "
                  f"{r['words']:,} words")
        return 0
    hit = [r for r in reports if team in (r.get("away"), r.get("home"))]
    if not hit:
        print(f"No report for {team} on this board.")
        return 1
    for r in hit:
        print(to_text(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
