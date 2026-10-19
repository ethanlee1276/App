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
  facts       Kickoff, venue, records and recent results, head coaches,
              coordinator changes, rest, division
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
plays, not a read's touchdown chance or its leaning markets. The game
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
OFFICIALS = ("Officials: the referee is named late in the week. Over 7,340 games we found the "
             "referee adds nothing the closing line does not already hold, so the crew is not "
             "part of this read.")

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
)
UNIT_NOTE = ("EPA is expected points added a play. Pressure is the rate the offense allows and the "
             "defense gets home. Throws are yards a target: short under 10 air yards, mid 10–19, "
             "deep 20+. Each cell is the value and its rank, 1st the best; the edge column names the "
             "side ahead by the edge bar.")

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
)

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
    s = f"{v:.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _pct(x, nd: int = 0) -> str:
    v = _f(x)
    return "" if v is None else f"{v * 100:.{nd}f}%"


def _minus(s: str) -> str:
    """The true minus sign, the way the site prints a negative (trueMinus)."""
    return str(s).replace("-", "\u2212")


def _signed(x, nd: int = 2) -> str:
    v = _f(x)
    return "" if v is None else _minus(f"{v:+.{nd}f}")


def _fmt(x, how: str) -> str:
    """A table cell's figure: fixed decimals, so a column lines up."""
    v = _f(x)
    if v is None:
        return ""
    return {"epa": lambda: _signed(v, 2), "pct": lambda: _pct(v),
            "pct1": lambda: _pct(v, 1), "num1": lambda: f"{v:.1f}"}[how]()


def _odds(x) -> str:
    v = _f(x)
    if v is None or v == 0:
        return ""
    return _minus(f"{int(round(v)):+d}")


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
class Ctx:
    """One game and everything on the board about it."""

    def __init__(self, g: dict, result: dict, allowed: dict | None = None,
                 sched=None, staff: dict | None = None, names: dict | None = None):
        self.g = g
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
        n_teams = int((self.scan.get("method") or {}).get("teams") or 32)
        self.n_teams = n_teams
        try:
            from .gamescan import EDGE_GAP
        except Exception:                                    # noqa: BLE001
            EDGE_GAP = 10
        self.gap_bar = max(EDGE_GAP, round(n_teams * EDGE_SHARE))
        self.sched_row = self._sched_row()

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


def _role_line(r: dict) -> str:
    """"31% of the targets (10.8 a game)" — his work, in one phrase."""
    u = _usage(r)
    pos = str(r.get("pos") or "").upper()
    if pos in ("RB", "FB") and u.get("carry_share"):
        bits = [f"{_pct(u['carry_share'])} of the carries ({_num(u.get('carries_pg'))} a game)"]
        if (u.get("tgt_share") or 0) >= 0.08:
            bits.append(f"{_pct(u['tgt_share'])} of the targets")
        return ", ".join(bits)
    if pos in ("WR", "TE") and u.get("tgt_share"):
        return f"{_pct(u['tgt_share'])} of the targets ({_num(u.get('targets_pg'))} a game)"
    return ""


# --- the sections ---------------------------------------------------------------------
def _p(text):
    text = _sentence(text)
    return {"type": "p", "text": text} if text else None


def _list(items):
    items = [_sentence(i) for i in items if i]
    return {"type": "list", "items": items} if items else None


def _h(text):
    return {"type": "h", "text": text} if text else None


def _section(key: str, title: str, blocks) -> dict | None:
    blocks = [b for b in blocks if b]
    return {"key": key, "title": title, "blocks": blocks} if blocks else None


def kickoff_words(date: str, kickoff: str) -> str:
    """"Sunday, Oct. 25, 4:25 PM ET" from the board's date and ET kickoff."""
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


def line_words(c: Ctx) -> str:
    """"DET by 3 at home, total 52.5" — the favorite, the margin, the total."""
    g = c.g
    sp, tot = _f(g.get("spread")), _f(g.get("total"))
    bits = []
    if sp is not None:
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
    """{team: points the spread and total imply}, or {}."""
    sp, tot = _f(c.g.get("spread")), _f(c.g.get("total"))
    if sp is None or tot is None:
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
    items.append(f"{c.name(c.away)}{f' ({ra})' if ra else ''} at {c.name(c.home)}"
                 f"{f' ({rh})' if rh else ''}" + (" — a neutral site" if g.get("neutral_site") else ""))
    st = g.get("stadium") or {}
    venue = st.get("name") or g.get("venue") or ""
    if venue:
        roof = {"dome": "a fixed dome", "closed": "roof closed", "open": "roof open",
                "retractable": "a retractable roof", "outdoors": "outdoors"}.get(
            str(g.get("roof") or st.get("roof") or "").lower(), "")
        surface = str(g.get("surface") or st.get("surface") or "").replace("_", " ")
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
            items.append(f"{c.name(t)}' last {len(res)}: {'; '.join(res)}"
                         if c.name(t).endswith("s") else f"{c.name(t)}'s last {len(res)}: {'; '.join(res)}")
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
    return _section("facts", "Game facts", [_list(items)])


def sec_market(c: Ctx) -> dict | None:
    g = c.g
    out = []
    lw = line_words(c)
    pts = implied_points(c)
    if lw:
        s = f"The line: {lw}"
        if pts:
            s += (f". That puts {c.home} at about {_num(pts[c.home])} points and "
                  f"{c.away} at about {_num(pts[c.away])}")
        out.append(_p(s))
    ml = ml_chances(c)
    if ml:
        fav = max(ml, key=ml.get)
        dog = c.opp[fav]
        out.append(_p(f"Moneyline: {fav} {_odds(g.get('home_ml' if fav == c.home else 'away_ml'))}, "
                      f"{dog} {_odds(g.get('home_ml' if dog == c.home else 'away_ml'))} — "
                      f"{fav} wins {_pct(ml[fav])} of the time once the book's cut is taken out"))
    lo = g.get("line_open") or {}
    moves = []
    if lo:
        o_sp, mv = _f(lo.get("spread_home")), _f(lo.get("spread_move"))
        if o_sp is not None:
            opened = (f"{c.home} {_minus(_num(o_sp))}" if o_sp < 0 else f"{c.away} {_minus(_num(-o_sp))}"
                      if o_sp > 0 else "a pick'em")
            if mv:
                toward = c.home if mv < 0 else c.away
                moves.append(f"The spread opened at {opened} and has moved {_num(abs(mv))} "
                             f"point{'s' if abs(mv) != 1 else ''} toward {toward}")
            else:
                moves.append(f"The spread opened at {opened} and has not moved")
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
    out.append(_list(moves))
    cr = g.get("crowd") or {}
    crowd = []
    venues = [(v, cr.get(k)) for v, k in (("Kalshi", "kalshi"), ("Polymarket", "polymarket"))
              if _f(cr.get(k)) is not None]
    if venues:
        crowd.append("Prediction markets have " + _join(
            f"{c.home} at {_pct(p)} on {v}" for v, p in venues))
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
        split.append(f"{word}: {_pct(share)} of the money on {side}"
                     + (f" (${int(round(float(s['usd']))):,} traded)" if _f(s.get("usd")) else ""))
    if split:
        venues_w = _join(money.get("venues") or []) or "the prediction markets"
        out.append(_p(f"Where the money is going on {venues_w}: {'; '.join(split)}"))
    sim = g.get("sim") or {}
    if _f(sim.get("p_home_win")) is not None:
        ph = float(sim["p_home_win"])
        sp = _f(g.get("spread"))
        bits = [f"{c.home} won {_pct(ph)} of {int(sim.get('trials') or 0):,} simulated games"
                if sim.get("trials") else f"{c.home} won {_pct(ph)} of simulated games"]
        if _f(sim.get("cover")) is not None and sp is not None and sp != 0:
            bits.append(f"covered {'−' if sp < 0 else '+'}{_num(abs(sp))} in {_pct(sim['cover'])}"
                        + (f" (a push in {_pct(sim['cover_push'])})"
                           if (_f(sim.get('cover_push')) or 0) >= 0.02 else ""))
        if _f(sim.get("over")) is not None and _f(g.get("total")) is not None:
            bits.append(f"went over {_num(g['total'])} in {_pct(sim['over'])}")
        out.append(_p("Our drive-by-drive simulator, run from these lines and both teams' "
                      f"numbers: {_join(bits)}. A simulation of the game, not a pick"))
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
            "head": ["", f"{off} off", f"{dfn} def", "Edge"], "rows": rows}


def sec_rankings(c: Ctx) -> dict | None:
    if not c.units:
        return None
    blocks = [_table_for(c, c.away, c.home), _table_for(c, c.home, c.away)]
    if any(blocks):
        blocks.append({"type": "note", "text": UNIT_NOTE})
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
                           "head": ["", c.away, c.home], "rows": rows,
                           "note": (f"Through {played}; " if played else "")
                                   + "the rank is against the league, 1st the best."})
    u0 = c.units.get(c.home) or c.units.get(c.away) or {}
    if u0.get("blend") is not None and u0.get("games"):
        w = float(u0["blend"])
        blocks.append(_p(f"The ranks are adjusted for the opponents each team has faced. After "
                         f"{_plural(u0['games'], 'game')} a rank is {_pct(w)} this season and {_pct(1 - w)} "
                         f"last season — the mix that best predicted the rest of a season when we tested "
                         f"it. An edge is a gap of {c.gap_bar} or more ranks"))
    edges = _edges(c)
    if edges:
        said = [edge_words(c, e) for e in edges[:4]]
        blocks.append(_p("Reading it: " + "; ".join(said)))
    return _section("rankings", "How the units rank", blocks)


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
        rr = _f(((nums.get(t) or {}).get("run_rate") or {}).get("value"))
        o = ch_off.get(t) or {}
        style = []
        if rr is not None:
            style.append(f"runs on {_pct(rr)} of plays")
        for key, words in (("play_action_rate", "play action on {} of dropbacks"),
                           ("motion_rate", "motion on {} of plays"),
                           ("screen_rate", "screens on {} of plays"),
                           ("rpo_rate", "run-pass options on {}"),
                           ("no_huddle_rate", "no huddle on {}")):
            if _f(o.get(key)) is not None:
                style.append(words.format(_pct(o[key])))
        if style:
            lines.append(f"On offense {t} {_join(style)}" +
                         (f" (charted, {season_ch} weeks 1–{weeks})" if season_ch and weeks and o else ""))
        mine = c.reads_for(t)
        tree = sorted((r for r in mine if str(r.get("pos") or "").upper() in ("WR", "TE", "RB")
                       and (_usage(r).get("tgt_share") or 0) >= TREE_SHARE),
                      key=lambda r: -(_usage(r).get("tgt_share") or 0))
        if tree:
            lines.append("Who gets the ball thrown to him: " + "; ".join(
                f"{r['player']} ({r.get('pos')}) {_pct(_usage(r)['tgt_share'])} of the targets, "
                f"{_num(_usage(r).get('targets_pg'))} a game" for r in tree[:5]))
        backs = sorted((r for r in mine if str(r.get("pos") or "").upper() in ("RB", "FB", "QB")
                        and (_usage(r).get("carry_share") or 0) >= BACKFIELD_SHARE),
                       key=lambda r: -(_usage(r).get("carry_share") or 0))
        if backs:
            lines.append("Who carries it: " + "; ".join(
                f"{r['player']} ({r.get('pos')}) {_pct(_usage(r)['carry_share'])} of the carries, "
                f"{_num(_usage(r).get('carries_pg'))} a game" for r in backs[:3]))
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
        if cov:
            lines.append(f"On defense {t} {_join(cov)}" + (f" ({sch_season} charting)" if sch_season else ""))
        dd = ch_def.get(t) or {}
        now = []
        if _f(dd.get("blitz_rate")) is not None:
            now.append(f"blitzing on {_pct(dd['blitz_rate'])} of dropbacks")
        if _f(dd.get("heavy_box_rate")) is not None:
            now.append(f"8 or more in the box on {_pct(dd['heavy_box_rate'])} of runs")
        if _f(dd.get("light_box_rate")) is not None:
            now.append(f"6 or fewer on {_pct(dd['light_box_rate'])}")
        if now:
            lines.append(f"This season {t} is {_join(now)}" +
                         (f" (charted, weeks 1–{weeks})" if weeks else ""))
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
    lines = c.scan.get("line_out") or {}
    for t in c.teams:
        if lines.get(t):
            blocks.append(_p(f"{c.name(t)} starting line: {_join(lines[t])} "
                             f"{'is' if len(lines[t]) == 1 else 'are'} out"))
    pulled = [p for p in c.scan.get("pulled") or [] if p]
    if pulled:
        blocks.append(_p(f"Every sportsbook has taken down its props on {_join(pulled)} — treated as "
                         "out until they come back"))
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
            blocks.append(_p("The injury report was not read for this build — check the inactives "
                             "before kickoff"))
    return _section("injuries", "Injuries and availability", blocks)


def _corner_line(cn: dict) -> str:
    bits = [f"{cn.get('name')} ({cn.get('spot')})"]
    if cn.get("targets"):
        bits.append(f"{_num(cn.get('rating'))} passer rating allowed on {_plural(cn['targets'], 'target')}"
                    + (f", {_num(cn.get('yds_per_tgt'))} yards a target" if cn.get("yds_per_tgt") else "")
                    + (f", {_plural(cn['td'], 'touchdown')}" if cn.get("td") else ""))
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
            leaks.append(f"{group} — {_join(soft)}")
        if hard:
            holds.append(f"{group} — {_join(hard)}")
    out = []
    games = next((x.get("games") for x in r.values() if isinstance(x, dict) and x.get("games")), None)
    tail = f" (over {_plural(games, 'game')})" if games else ""
    if leaks:
        out.append(f"Where {dfn}'s defense leaks: {'; '.join(leaks)}{tail}")
    if holds:
        out.append(f"Where it holds: {'; '.join(holds)}")
    return out


def _why(r: dict) -> list:
    """A read's reasons, the pick-free ones: what it says for and against
    him, then the scheme, charting and tracking notes about him. His share
    of the work is on his line already, and the corner's numbers are in the
    coverage lines under the verdicts, so neither is said again here."""
    role = bool(_role_line(r))
    why = [str(x) for x in (r.get("pro") or []) + (r.get("con") or []) if x
           and not (role and ("of the carries" in str(x) or "of the targets" in str(x)))]
    for n in r.get("notes") or []:
        s = str(n)
        if s.startswith("Usage is ") or "passer rating on" in s:
            continue
        if "against man" in s or "against zone" in s or "box" in s \
                or s.startswith(("Tracking:", "Charted:")):
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
            sub.append(_p(f"Across {off}'s key players: " + "; ".join(said)))
        items = []
        for r, why in zip(keys, whys):
            tone, label = VERDICT.get(r.get("read"), ("neutral", "NEUTRAL"))
            pos = str(r.get("pos") or "").upper()
            against = {"QB": f"{dfn}'s pass defense", "RB": f"{dfn}'s run defense",
                       "FB": f"{dfn}'s run defense"}.get(pos, f"{dfn}'s coverage")
            items.append({"player": r.get("player"), "team": off, "pos": pos,
                          "headshot": r.get("headshot") or "", "verdict": tone, "label": label,
                          "title": f"{r.get('player')} vs {against}", "role": _role_line(r),
                          "why": [_sentence(w) for w in why if w not in common][:4]})
        if items:
            sub.append({"type": "verdicts", "items": items})
        room = cov.get(dfn) or {}
        corners = [cn for cn in room.get("corners") or [] if isinstance(cn, dict) and cn.get("name")]
        notes = []
        if room.get("weakest"):
            w = next((cn for cn in corners if cn.get("name") == room["weakest"]), None)
            if w and w.get("targets"):
                notes.append(f"The soft spot in {dfn}'s coverage: {_corner_line(w)}")
        if corners:
            notes.append(f"{dfn}'s corners: " + "; ".join(_corner_line(cn) for cn in corners))
        if room.get("missing"):
            notes.append(f"{dfn} is without {_join(room['missing'])} in the secondary")
        notes += funnel_lines(c, dfn)
        sub.append(_list(notes))
        sub = [b for b in sub if b]
        if sub:
            blocks += [_h(f"{c.name(off)} offense vs {c.name(dfn)} defense")] + sub
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
            lines.append(f"{dfn}'s rush runs through " + _join(
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
                s += f", {float(ypc_d['value']):.1f} allowed a carry"
            s += ")"
            gap = int(rd["rank"]) - int(ro["rank"])
            who = off if gap >= c.gap_bar else dfn if -gap >= c.gap_bar else None
            lines.append(s + (f" — edge {who}" if who else ""))
        if lines:
            blocks += [_h(f"{c.name(off)} up front"), _list(lines)]
    return _section("trenches", "In the trenches", blocks)


def sec_redzone(c: Ctx) -> dict | None:
    nums = c.scan.get("numbers") or {}
    rz = c.scan.get("redzone") or {}
    lines = []
    for off in c.teams:
        dfn = c.opp[off]
        o, d = (nums.get(off) or {}).get("rz_off") or {}, (nums.get(dfn) or {}).get("rz_def") or {}
        if _f(o.get("value")) is not None and _f(d.get("value")) is not None:
            of = o.get("of") or c.n_teams
            lines.append(f"{off} scores a touchdown on {_pct(o['value'])} of its red-zone trips this season"
                         + (f" ({_ord(o['rank'])} of {of})" if o.get("rank") else "")
                         + f"; {dfn} allows one on {_pct(d['value'])}"
                         + (f" ({_ord(d['rank'])} of {d.get('of') or of}, 1st the stingiest)" if d.get("rank") else ""))
        ro, rd = rz.get(off) or {}, rz.get(dfn) or {}
        if _f(ro.get("off")) is not None and _f(rd.get("def")) is not None:
            rel_o, rel_d = _f(ro.get("off_rel")), _f(rd.get("def_rel"))
            lines.append(f"{off} runs about {_num(ro['off'])} red-zone plays a game"
                         + (f" ({_pct(abs(rel_o))} {'above' if rel_o >= 0 else 'below'} the league)" if rel_o is not None else "")
                         + f"; {dfn} allows about {_num(rd['def'])}"
                         + (f" ({_pct(abs(rel_d))} {'above' if rel_d >= 0 else 'below'} the league)" if rel_d is not None else "")
                         + ", both adjusted for opponents")
        chances = sorted(((r.get("player"), _f((r.get("td") or {}).get("rz_chances")))
                          for r in c.reads_for(off)), key=lambda x: -(x[1] or 0))
        chances = [(p, v) for p, v in chances if p and v and v >= 0.3][:3]
        if chances:
            lines.append(f"{off}'s expected red-zone chances: " + "; ".join(
                f"{p} about {_num(v)} a game" for p, v in chances))
    return _section("redzone", "Red zone", [_list(lines)])


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
            lines.append(f"{t}: {n}")
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
    return _section("context", "Coaching and the schedule", [_list(lines)])


#: The simulator's six margin buckets (engine/drivesim.summary), home − away.
SIM_BUCKETS = (("home", 15, None), ("home", 8, 14), ("home", 1, 7),
               ("away", 1, 7), ("away", 8, 14), ("away", 15, None))


def sec_scripts(c: Ctx) -> dict | None:
    blocks = []
    sc = (c.plan.get("script") or {})
    step = next((s for s in c.plan.get("steps") or [] if isinstance(s, dict) and s.get("key") == "line"), {})
    if sc.get("archetype"):
        blocks.append(_p(f"The script the lines point to: {sc['archetype']}"
                         + (f" ({sc.get('confidence')} confidence)" if sc.get("confidence") else "")))
    plan_lines = [str(x) for x in step.get("lines") or [] if x][1:]
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
        bits.append(f"a one-score game (8 or fewer) {_pct(sim['one_score'])} of the time")
    if _f(sim.get("blowout")) is not None:
        bits.append(f"a 14-plus-point game either way {_pct(sim['blowout'])}")
    if bits:
        blocks.append(_p(f"In the simulator this is {_join(bits)}"))
    return _section("scripts", "How the game could go", blocks)


def sec_watch(c: Ctx) -> dict | None:
    shine = sorted((r for r in c.reads if r.get("read") in ("breakout", "good")),
                   key=lambda r: (r.get("read") != "breakout", -_volume(r)))
    struggle = sorted((r for r in c.reads if r.get("read") in ("tough", "avoid") and _is_key(r)),
                      key=lambda r: (r.get("read") != "avoid", -_volume(r)))

    def item(r, tone):
        why = [str(x) for x in (r.get("pro") if tone == "up" else r.get("con")) or [] if x][:2]
        return {"player": r.get("player"), "team": r.get("team"), "pos": r.get("pos"),
                "headshot": r.get("headshot") or "", "tone": tone,
                "label": r.get("label") or "", "role": _role_line(r),
                "text": " ".join(_sentence(w) for w in why)}
    blocks = []
    if shine:
        blocks += [_h("Could shine"), {"type": "players", "items": [item(r, "up") for r in shine[:6]]}]
    if struggle:
        blocks += [_h("Could struggle"), {"type": "players", "items": [item(r, "down") for r in struggle[:4]]}]
    if c.reads and not shine:
        blocks.append(_p("No one in this game reads as a breakout candidate or a good matchup"))
    return _section("watch", "Players to watch", blocks)


def sec_weather(c: Ctx) -> dict | None:
    g = c.g
    w = g.get("weather") or {}
    cond = g.get("conditions") or {}
    st = g.get("stadium") or {}
    lines = []
    if w.get("dome") or str(g.get("roof") or "").lower() in ("dome", "closed"):
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
    if not (w.get("dome") or str(g.get("roof") or "").lower() in ("dome", "closed")) and st.get("plays"):
        lines.append(st["plays"])
    for why in cond.get("why") or []:
        if why and why not in lines:
            lines.append(str(why))
    return _section("weather", "Weather and venue", [_list(lines)])


def sec_before(c: Ctx) -> dict | None:
    lines = []
    g = c.g
    try:
        hh, mm = (int(x) for x in str(g.get("kickoff") or "").split(":")[:2])
        t = _dt.datetime(2000, 1, 1, hh, mm) - _dt.timedelta(minutes=INACTIVES_BEFORE_MIN)
        lines.append(f"Inactives post about {_clock(t.hour, t.minute)} ET, "
                     f"{INACTIVES_BEFORE_MIN} minutes before kickoff")
    except ValueError:
        pass
    for r in c.scan.get("injuries") or []:
        if isinstance(r, dict) and str(r.get("status") or "").upper() == "QUESTIONABLE":
            lines.append(f"{r.get('player')} ({r.get('team')}) is questionable"
                         + (f" — {r['opens'][0].lower()}{r['opens'][1:]}" if r.get("opens") else ""))
    w = g.get("weather") or {}
    if w.get("forecast") and not w.get("dome"):
        lines.append("The forecast can still move; the read uses the game-time forecast, never "
                     "today's conditions")
    games = [((c.units.get(t) or {}).get("games")) for t in c.teams]
    if any(n is not None and n < 4 for n in games):
        lines.append("Small sample: " + _join(f"{t} has played {_plural(n, 'game')}"
                                               for t, n in zip(c.teams, games) if n is not None)
                     + " this season, so last season carries more of every rank")
    if g.get("price_stale"):
        lines.append("The game lines on this page are older than the build — check the price "
                     "before you trust the market section")
    behind = (c.result.get("data_freshness") or {}).get("behind") or []
    if behind:
        lines.append(f"Data behind the last week played: {_join(str(b) for b in behind)}")
    lines.append(OFFICIALS)
    return _section("before", "Before kickoff", [_list(lines)])


def sec_short(c: Ctx, built: dict) -> dict | None:
    """The short version, written last from what the sections found."""
    items = []
    lw = line_words(c)
    pts = implied_points(c)
    if lw:
        s = f"{lw}"
        if pts:
            s += f": the books expect about {c.home} {_num(pts[c.home])}, {c.away} {_num(pts[c.away])}"
        ml = ml_chances(c)
        if ml:
            fav = max(ml, key=ml.get)
            s += f"; the moneyline makes {fav} a {_pct(ml[fav])} favorite"
        items.append(s[0].upper() + s[1:])
    edges = _edges(c)
    if edges:
        items.append("Where the edges are: " + "; ".join(edge_words(c, e) for e in edges[:3]))
    cov = c.scan.get("coverage") or {}
    soft = []
    for t in c.teams:
        room = cov.get(t) or {}
        w = next((cn for cn in room.get("corners") or [] if cn.get("name") == room.get("weakest")), None)
        if w and w.get("targets") and _f(w.get("rating")) is not None:
            soft.append(f"{w['name']} ({t} {w.get('spot')}), {_num(w['rating'])} rating allowed on "
                        f"{_plural(w['targets'], 'target')}")
    if soft:
        items.append("Soft spots in coverage: " + "; ".join(soft))
    shine = [r for r in c.reads if r.get("read") in ("breakout", "good")]
    shine.sort(key=lambda r: (r.get("read") != "breakout", -_volume(r)))
    if shine:
        items.append("Could shine: " + _join(f"{r['player']} ({r.get('team')} {r.get('pos')}"
                                              f"{', breakout candidate' if r.get('read') == 'breakout' else ''})"
                                              for r in shine[:4]))
    struggle = [r for r in c.reads if r.get("read") in ("tough", "avoid") and _is_key(r)]
    if struggle:
        items.append("Could struggle: " + _join(f"{r['player']} ({r.get('team')} {r.get('pos')})"
                                                 for r in struggle[:3]))
    outs = [r for r in c.scan.get("injuries") or [] if isinstance(r, dict)
            and str(r.get("status") or "").upper() not in ("QUESTIONABLE", "")]
    if outs:
        items.append("Out: " + _join(f"{r.get('player')} ({r.get('team')} {r.get('position') or ''})".replace(" )", ")")
                                     for r in outs[:5]))
    for q in c.result.get("qb_changes") or []:
        if isinstance(q, dict) and q.get("team") in c.teams and q.get("headline"):
            items.append(q["headline"])
    fat = (c.result.get("fatigue") or {}).get("teams") or {}
    ra, rh = (fat.get(c.away) or {}).get("rest_days"), (fat.get(c.home) or {}).get("rest_days")
    if ra and rh and ra != rh:
        more = c.away if ra > rh else c.home
        items.append(f"Rest: {more} comes in on {max(ra, rh)} days to {c.opp[more]}'s {min(ra, rh)}")
    sim = c.g.get("sim") or {}
    if _f(sim.get("p_home_win")) is not None:
        ph = float(sim["p_home_win"])
        lead = c.home if ph >= 0.5 else c.away
        s = f"Our simulator has {lead} winning {_pct(max(ph, 1 - ph))}"
        if _f(sim.get("one_score")) is not None:
            s += f", a one-score game {_pct(sim['one_score'])} of the time"
        items.append(s)
    return _section("short", "The short version", [_list(items)])


SECTIONS = (sec_facts, sec_market, sec_rankings, sec_identity, sec_injuries, sec_matchups,
            sec_trenches, sec_redzone, sec_context, sec_scripts, sec_watch, sec_weather,
            sec_before)


def _words(sections) -> int:
    n = 0

    def count(x):
        nonlocal n
        if isinstance(x, str):
            n += len(x.split())
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in ("type", "headshot", "verdict", "tone", "key"):
                    count(v)
        elif isinstance(x, list):
            for v in x:
                count(v)
    count(sections)
    return n


def build(g: dict, result: dict, *, allowed: dict | None = None, sched=None,
          staff: dict | None = None, names: dict | None = None) -> dict | None:
    """One game's report, or None for a row with no teams."""
    if not isinstance(g, dict) or not g.get("away") or not g.get("home"):
        return None
    c = Ctx(g, result, allowed=allowed, sched=sched, staff=staff, names=names)
    built = {}
    for fn in SECTIONS:
        s = fn(c)
        if s:
            built[s["key"]] = s
    short = sec_short(c, built)
    sections = ([short] if short else []) + list(built.values())
    words = _words(sections)
    return {"game": f"{c.away}@{c.home}", "away": c.away, "home": c.home,
            "date": g.get("date") or "", "kickoff": g.get("kickoff") or "",
            "title": f"{c.name(c.away)} at {c.name(c.home)}",
            "built_at": result.get("built_at") or "",
            "words": words, "minutes": max(1, round(words / WORDS_A_MINUTE)),
            "sections": sections}


def attach(result: dict, *, allowed: dict | None = None, season: int | None = None) -> str:
    """``result["game_reports"]``: one report for every game on the board.
    One line for the build log; never raises."""
    try:
        sched = staff = None
        try:
            from . import spots
            sched = spots.load_schedule()
            season = season or int(str(result.get("date") or "")[:4] or 0) or None
            staff = spots.staff_for(season, (season or 1) - 1) if season else {}
        except Exception:                                    # noqa: BLE001
            sched, staff = None, {}
        names = _team_names()
        reports = []
        for g in result.get("games") or []:
            r = build(g, result, allowed=allowed, sched=sched, staff=staff, names=names)
            if r:
                reports.append(r)
        result[KEY] = reports
        if not reports:
            return "Game reports: no games on the board"
        words = sum(r["words"] for r in reports)
        return (f"Game reports: {len(reports)} game(s), {words:,} words "
                f"(about {round(words / max(1, len(reports)) / WORDS_A_MINUTE)} minutes each)")
    except Exception as exc:                                 # noqa: BLE001
        result.pop(KEY, None)
        return f"⚠️  Game reports skipped ({type(exc).__name__}: {exc})"


# --- reading one back -----------------------------------------------------------------
def to_text(report: dict) -> str:
    """The report as plain text — what the box prints and the tests read."""
    out = [f"{report.get('title')} — {report.get('game')} · {report.get('date')} "
           f"{report.get('kickoff')} ET · about {report.get('minutes')} min"]
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
                    out.append(f"  • {v['title']} = {v['label']}" + (f" — {v['role']}" if v.get("role") else ""))
                    out += [f"      - {w}" for w in v.get("why") or []]
            elif t == "players":
                for v in b["items"]:
                    out.append(f"  • {v['player']} ({v.get('team')} {v.get('pos')}) — {v.get('label')}"
                               + (f": {v['text']}" if v.get("text") else ""))
    return "\n".join(out)


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
