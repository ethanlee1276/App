"""The matchup scan: every NFL game, unit by unit and player by player.

Ethan, 2026-09-24, pasting a Falcons @ Packers breakdown he wanted done
for every game: "ranking the defenses and offenses and looking at where
exactly in the defense and offense is good and bad and what players could
shine and what players could hurt". The breakdown ranked each side's
units, set them against each other, walked the injuries to what they
open, named the player-level mismatches (a receiver's profile against the
corners he will see), mapped the game scripts, and ended on the props
worth putting under the microscope.

This module is the first layer: the UNITS. Eight a side, measured from
the play-by-play (engine/sources/nflunits), ranked 1-32:

    overall   EPA per play          success   success rate
    passing   EPA per dropback      rushing   EPA per designed run
    explosive 20+ yd dropbacks and 10+ yd runs, per play
    pressure  sacks + QB hits per dropback (allowed / generated)
    ypc       rushing yards per carry

HOW A RATING IS MADE — the two things the breakdown's model did and a
raw two-game table cannot:

* OPPONENT-ADJUSTED. An offence that opened against two top-five
  defences is not the 30th offence in football. Each game's number is
  moved by how far the opponent's own season sits from the league
  average on the other side of the ball.
* BLENDED WITH LAST SEASON by how much of this one there is:
  ``weight = games / (games + PRIOR_GAMES)``. Two weeks in, a rating is a
  third this season and two thirds last; by midseason it is this season.
  A team that turned over its roster reads a little like last year's for
  a few weeks, and the card says the blend.

Standard library only; reads the ``team_units`` table and nothing else.
"""

from __future__ import annotations

#: Games of last season a rating leans on before this season's own.
PRIOR_GAMES = 4.0

#: Each unit: (numerator field(s), denominator field, better when higher
#: — from the OFFENCE's point of view; a defence's sense is the reverse).
UNITS = {
    "overall": (("epa",), "plays", True),
    "passing": (("pass_epa",), "dropbacks", True),
    "rushing": (("rush_epa",), "rushes", True),
    "success": (("success",), "plays", True),
    "explosive": (("pass_expl", "rush_expl"), "plays", True),
    "pressure": (("sacks", "hits"), "dropbacks", False),
    "ypc": (("rush_yds",), "rushes", True),
}

#: How the page names them.
UNIT_LABELS = {"overall": "Overall", "passing": "Passing", "rushing": "Rushing",
               "success": "Success rate", "explosive": "Explosive plays",
               "pressure": "Pressure", "ypc": "Yards per carry"}


def _num(row: dict, fields) -> float:
    return sum(float(row.get(f) or 0.0) for f in fields)


def _season_rates(rows: list[dict]) -> dict:
    """{(team, side): {unit: (num, den)}} summed over the rows given."""
    out: dict = {}
    for r in rows:
        key = (r["team"], r["side"])
        cell = out.setdefault(key, {u: [0.0, 0.0] for u in UNITS})
        for u, (fields, den, _) in UNITS.items():
            cell[u][0] += _num(r, fields)
            cell[u][1] += float(r.get(den) or 0.0)
    return out


def _rate(pair) -> float | None:
    n, d = pair
    return n / d if d else None


def _adjusted(rows: list[dict]) -> tuple[dict, dict]:
    """One season's opponent-adjusted rate per (team, side, unit), and the
    number of games each team played.

    A game's number is moved by how far that opponent's season, on the
    other side of the ball, sits from the league's: a pass offence that
    faced a defence allowing 0.10 EPA per dropback less than average is
    credited 0.10. Weighted by the game's own plays."""
    rates = _season_rates(rows)
    league: dict = {}
    for u in UNITS:
        n = sum(c[u][0] for (_t, s), c in rates.items() if s == "off")
        d = sum(c[u][1] for (_t, s), c in rates.items() if s == "off")
        league[u] = n / d if d else 0.0
    games: dict = {}
    acc: dict = {}
    for r in rows:
        team, side, opp = r["team"], r["side"], r.get("opp") or ""
        if side == "off":
            games[team] = games.get(team, 0) + 1
        other = "def" if side == "off" else "off"
        opp_cell = rates.get((opp, other))
        cell = acc.setdefault((team, side), {u: [0.0, 0.0] for u in UNITS})
        for u, (fields, den, _) in UNITS.items():
            d = float(r.get(den) or 0.0)
            if not d:
                continue
            raw = _num(r, fields) / d
            opp_rate = _rate(opp_cell[u]) if opp_cell else None
            shift = (opp_rate - league[u]) if opp_rate is not None else 0.0
            cell[u][0] += (raw - shift) * d
            cell[u][1] += d
    out = {k: {u: _rate(v) for u, v in c.items()} for k, c in acc.items()}
    return out, games


def ratings_from_rows(current: list[dict], prior: list[dict] | None = None) -> dict:
    """{team: {"games", "blend", "off": {unit: {"value", "rank"}}, "def": {...}}}.

    ``current`` and ``prior`` are `team_units` rows for this season (the
    weeks before the game) and last season. Ranks run 1 = best: the best
    offence gains the most, the best defence allows the least, and for
    pressure the best offensive line allows the fewest while the best
    pass rush generates the most."""
    cur, games = _adjusted(current or [])
    pri, _ = _adjusted(prior or []) if prior else ({}, {})
    teams = sorted({t for t, _ in cur} | ({t for t, _ in pri} if not cur else set()))
    blended: dict = {}
    for team in teams:
        g = games.get(team, 0)
        w = g / (g + PRIOR_GAMES) if (team, "off") in pri or (team, "def") in pri else 1.0
        blended[team] = {"games": g, "blend": round(w, 2)}
        for side in ("off", "def"):
            c, p = cur.get((team, side), {}), pri.get((team, side), {})
            vals = {}
            for u in UNITS:
                a, b = c.get(u), p.get(u)
                vals[u] = (a if b is None else b if a is None else w * a + (1 - w) * b)
            blended[team][side] = vals
    for side in ("off", "def"):
        for u, (_, _, higher) in UNITS.items():
            good_high = higher if side == "off" else not higher
            have = [(t, blended[t][side][u]) for t in teams if blended[t][side].get(u) is not None]
            have.sort(key=lambda tv: -tv[1] if good_high else tv[1])
            ranks = {t: i + 1 for i, (t, _) in enumerate(have)}
            for t in teams:
                v = blended[t][side].get(u)
                blended[t][side][u] = {"value": None if v is None else round(v, 4),
                                       "rank": ranks.get(t)}
    return blended


def unit_ratings(conn, season: int, before_week: int | None = None,
                 sport: str = "nfl") -> dict:
    """The ratings a game in ``season`` week ``before_week`` is priced
    against: this season's weeks before it, blended with last season's."""
    def rows(yr, upto=None):
        q = ("SELECT * FROM team_units WHERE sport=? AND season=?"
             + (" AND CAST(period AS INTEGER) < ?" if upto else ""))
        args = (sport, yr) + ((upto,) if upto else ())
        return [dict(r) for r in conn.execute(q, args)]
    try:
        cur = rows(int(season), before_week)
        pri = rows(int(season) - 1)
    except Exception:                                        # noqa: BLE001
        return {}
    if not cur and not pri:
        return {}
    return ratings_from_rows(cur, pri)


# ═══ THE SCAN: one game, both offences against both defences ═══════════════
#
# What the breakdown did after the units: the injuries walked to what they
# open, each defence's corners and scheme, each offence's pass protection
# against the other's rush, and a read on every player with a prop —
# "breakout candidate", "tough matchup" — with the reasons, then the props
# worth putting under the microscope. Everything below is built from data
# the build already holds; nothing here moves a projection. A reason a
# read gives is shown to the reader; a reason becomes part of the NUMBER
# only once it has been measured against past games (engine/defensevs and
# engine/teammates are the two that have).

#: A defender needs this many targets before his coverage numbers speak.
MIN_TARGETS = 6
#: A corner allowing a passer rating at or above this is the one to attack.
SOFT_RATING = 105.0
#: A unit-vs-unit gap this many ranks wide is called out as an edge.
EDGE_GAP = 10
#: Injury statuses that take a player off the field for this game.
OUT_STATUSES = {"OUT", "IR", "DOUBTFUL", "PUP", "SUSPENDED", "INACTIVE"}

_POS_GROUP = {"WR": "wr", "TE": "te", "RB": "rb", "FB": "rb", "QB": "qb"}
_OL = ("LT", "LG", "C", "RG", "RT")
_CORNERS = ("LCB", "RCB", "NB")


def _key(name: str) -> str:
    from .sources.nflscheme import name_key
    return name_key(name)


def _abbr(name: str) -> str:
    """"Drake London" → "D.London", the play-by-play's own spelling."""
    parts = [p for p in (name or "").replace(".", " ").split()
             if p.lower() not in ("jr", "sr", "ii", "iii", "iv", "v")]
    if len(parts) < 2:
        return name or ""
    return f"{parts[0][0]}.{parts[-1]}"


def _status(injuries, team: str, name: str) -> str:
    k = _key(name)
    for i in injuries or []:
        if getattr(i, "team", "") == team and _key(getattr(i, "player", "")) == k:
            return str(getattr(i, "status", "") or "").upper()
    return ""


def usage_table(weekly_rows: list[dict], snap_rows: list[dict] | None = None,
                before_week: int | None = None) -> dict:
    """{(team, name_key): per-game usage this season} from nflverse's
    weekly player stats (and snap counts, when given): targets, target
    share, carries and carry share, catches, yards, snap share."""
    team_carries: dict = {}
    out: dict = {}
    for r in weekly_rows or []:
        if (r.get("season_type") or "REG") != "REG":
            continue
        try:
            wk = int(float(r.get("week") or 0))
        except ValueError:
            continue
        if before_week and wk >= before_week:
            continue
        team = r.get("team") or r.get("recent_team") or ""
        name = r.get("player_display_name") or r.get("player_name") or ""
        if not team or not name:
            continue
        f = lambda k: float(r.get(k) or 0) if r.get(k) not in (None, "", "NA") else 0.0  # noqa: E731
        team_carries[(team, wk)] = team_carries.get((team, wk), 0.0) + f("carries")
        u = out.setdefault((team, _key(name)), {
            "name": name, "position": r.get("position") or "", "games": 0, "weeks": [],
            "targets": 0.0, "tgt_share": 0.0, "carries": 0.0, "receptions": 0.0,
            "rec_yds": 0.0, "rush_yds": 0.0, "snap_pct": None})
        u["games"] += 1
        u["weeks"].append(wk)
        u["targets"] += f("targets")
        u["tgt_share"] += f("target_share")
        u["carries"] += f("carries")
        u["receptions"] += f("receptions")
        u["rec_yds"] += f("receiving_yards")
        u["rush_yds"] += f("rushing_yards")
    snaps: dict = {}
    for r in snap_rows or []:
        if (r.get("game_type") or "REG") != "REG":
            continue
        try:
            wk = int(float(r.get("week") or 0))
        except ValueError:
            continue
        if before_week and wk >= before_week:
            continue
        s = snaps.setdefault((r.get("team") or "", _key(r.get("player") or "")), [0.0, 0])
        s[0] += float(r.get("offense_pct") or 0)
        s[1] += 1
    for (team, k), u in out.items():
        g = max(1, u["games"])
        carries_team = sum(team_carries.get((team, w), 0.0) for w in u["weeks"])
        u.update(targets_pg=round(u["targets"] / g, 1), tgt_share=round(u["tgt_share"] / g, 3),
                 carries_pg=round(u["carries"] / g, 1),
                 carry_share=round(u["carries"] / carries_team, 3) if carries_team else 0.0,
                 rec_pg=round(u["receptions"] / g, 1), rec_yds_pg=round(u["rec_yds"] / g, 1),
                 rush_yds_pg=round(u["rush_yds"] / g, 1))
        s = snaps.get((team, k))
        if s and s[1]:
            u["snap_pct"] = round(s[0] / s[1], 2)
        del u["weeks"]
    return out


def coverage_room(team: str, chart: list[dict], defenders_now: dict,
                  defenders_last: dict | None = None, injuries=None) -> dict:
    """``team``'s corners as the published depth chart lines them up
    (left, right, nickel), each with his status and what he has allowed
    this season (last season beside it), the starters who will not play
    and who steps in, and the weakest starter left — the one an offence
    goes at."""
    spots = {row["position"]: row.get("players") or [] for row in chart or []}
    corners, missing = [], []
    for spot in _CORNERS:
        names = spots.get(spot) or []
        starter = None
        for depth, name in enumerate(names[:3]):
            st = _status(injuries, team, name)
            if st in OUT_STATUSES:
                if depth == 0:
                    missing.append({"name": name, "spot": spot, "status": st})
                continue
            starter = (name, st, depth)
            break
        if not starter:
            continue
        name, st, depth = starter
        k = _key(name)
        now = defenders_now.get((team, k)) or {}
        last = next((v for (_t, kk), v in (defenders_last or {}).items() if kk == k), {})
        corners.append({"name": name, "spot": spot, "status": st,
                        "next_man_up": depth > 0,
                        "targets": int(now.get("targets") or 0),
                        "yds_per_tgt": now.get("yds_per_tgt"), "rating": now.get("rating"),
                        "td": int(now.get("td") or 0),
                        "last": ({"targets": int(last.get("targets") or 0),
                                  "yds_per_tgt": last.get("yds_per_tgt"),
                                  "rating": last.get("rating")} if last else None)})
    rated = [c for c in corners if c["targets"] >= MIN_TARGETS and c["rating"] is not None]
    weakest = max(rated, key=lambda c: c["rating"]) if rated else None
    return {"corners": corners, "missing": missing,
            "weakest": weakest["name"] if weakest and weakest["rating"] >= SOFT_RATING else None}


def _pass_rush(team: str, defenders_now: dict, injuries=None, n: int = 3) -> list[dict]:
    """The defence's leading pass rushers this season, by pressures."""
    got = [dict(v, team=team) for (t, _k), v in defenders_now.items() if t == team and v.get("pressures")]
    got.sort(key=lambda v: -v["pressures"])
    return [{"name": v["name"], "pressures": int(v["pressures"]), "sacks": v["sacks"],
             "status": _status(injuries, team, v["name"])} for v in got[:n]]


def _line_out(team: str, chart: list[dict], injuries=None) -> list[str]:
    spots = {row["position"]: row.get("players") or [] for row in chart or []}
    out = []
    for pos in _OL:
        names = spots.get(pos) or []
        if names and _status(injuries, team, names[0]) in OUT_STATUSES:
            out.append(f"{names[0]} ({pos})")
    return out


def _rank(r: dict, side: str, unit: str):
    return ((r or {}).get(side) or {}).get(unit, {}).get("rank")


def unit_edges(off_team: str, def_team: str, ratings: dict, teams: int = 32) -> list[dict]:
    """The unit-against-unit gaps for one offence against one defence,
    widest first. Rank 1 is best on both sides, so an offence ranked 5th
    against a defence ranked 28th is a 23-rank edge to the offence."""
    o, d = ratings.get(off_team) or {}, ratings.get(def_team) or {}
    pairs = (("passing", "passing", "passing game"), ("rushing", "rushing", "running game"),
             ("explosive", "explosive", "explosive plays"), ("overall", "overall", "overall"))
    out = []
    for ou, du, label in pairs:
        orank, drank = _rank(o, "off", ou), _rank(d, "def", du)
        if orank is None or drank is None:
            continue
        gap = drank - orank          # > 0: the offence is the better unit
        out.append({"unit": ou, "label": label, "off": off_team, "def": def_team,
                    "off_rank": orank, "def_rank": drank, "gap": gap})
    for unit, label in (("pressure", "pass protection vs pass rush"),
                        ("havoc", "ball security vs havoc"),
                        ("line", "run blocking vs the front")):
        a, b = _rank(o, "off", unit), _rank(d, "def", unit)
        if a is not None and b is not None:
            out.append({"unit": unit, "label": label, "off": off_team, "def": def_team,
                        "off_rank": a, "def_rank": b, "gap": b - a})
    out.sort(key=lambda e: -abs(e["gap"]))
    return out


def _weak(rank, n: int = 32) -> bool:
    """In the bottom third of the league: 21st or worse of 32."""
    return bool(rank) and rank >= round(n * 0.65)


def _strong(rank, n: int = 32) -> bool:
    """In the top quarter: 8th or better of 32."""
    return bool(rank) and rank <= max(1, round(n * 0.25))


def _ord(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


#: The reads, in order. A score is a count of the reasons for and against.
READS = (("breakout", "Breakout candidate"), ("good", "Good matchup"), ("neutral", "Neutral"),
         ("tough", "Tough matchup"), ("avoid", "Avoid"))


def _label(score: int, volume: bool) -> tuple[str, str]:
    key = ("breakout" if score >= 3 and volume else "good" if score >= 2
           else "neutral" if score >= 0 else "tough" if score == -1 else "avoid")
    return key, dict(READS)[key]


#: Implied points (from the posted spread and total) that make a
#: scoring spot, and a thin one. The league's average is about 22.5.
POINTS_HIGH, POINTS_LOW = 26.5, 18.5

#: Position words for the defence-vs-position lines.
_POS_WORDS = {"wr": "wide receivers", "te": "tight ends", "rb": "running backs", "qb": "quarterbacks"}


def _allowed_line(allowed: dict | None, stat: str, opp: str, n_default: int = 32):
    """(+1 soft / −1 stingy / 0, sentence) for what ``opp`` gives up in
    one engine/defensevs stat — rank 1 gives up the most."""
    r = (allowed or {}).get(stat) or {}
    rank, n = r.get("rank"), r.get("of") or n_default
    if not rank:
        return 0, ""
    words = D_STAT_WORDS.get(stat, stat)
    q = max(1, round(n * 0.25))
    pg = r.get("pg")
    per = f" ({pg:.1f} a game)" if isinstance(pg, (int, float)) and pg < 10 else (
        f" ({pg:.0f} a game)" if isinstance(pg, (int, float)) else "")
    if rank <= q:
        return 1, f"{opp} gives up the {_ord(rank)}-most {words}{per}"
    if rank > n - q:
        return -1, f"{opp} gives up the {_ord(n - rank + 1)}-fewest {words}{per}"
    return 0, ""


#: The words for engine/defensevs.STATS, as a sentence says them.
D_STAT_WORDS = {"qb_pass_yds": "passing yards", "qb_pass_td": "passing touchdowns",
                "wr_rec_yds": "receiving yards to wide receivers", "wr_rec": "catches to wide receivers",
                "wr_td": "touchdowns to wide receivers", "te_rec_yds": "receiving yards to tight ends",
                "te_rec": "catches to tight ends", "te_td": "touchdowns to tight ends",
                "rb_rush_yds": "rushing yards to running backs", "rb_rec_yds": "receiving yards to running backs",
                "rb_rec": "catches to running backs", "rb_td": "touchdowns to running backs"}


def player_read(name: str, team: str, opp: str, pos: str, *, usage: dict | None,
                ratings: dict, room: dict | None, scheme: dict | None,
                split: dict | None, tackling: dict | None, line_out: list | None,
                mates_out: list | None, n_teams: int = 32,
                allowed: dict | None = None, points: float | None = None,
                line_words: str = "") -> dict:
    """One player's read against this opponent: a label, the reasons for
    and against it (each a sentence a reader can check), what else the
    scan noticed, and the markets the read points at.

    THE LABEL COUNTS ONLY WHAT WAS MEASURED TO PREDICT (engine/scanfit,
    2026-09-24). Ethan's Saints @ Lions week 1 is the case that showed
    it: the first version counted Detroit's pass-defense EPA (12th — dead
    average) and read Olave, St. Brown, Gibbs and LaPorta all NEUTRAL,
    while ignoring the two things the model actually prices with — what a
    defence gives up in the stat the bet is on (engine/defensevs, at the
    rating MODEL_STAT names) and how many points the lines expect the
    team to score (Detroit: 28, from −7 and 49.5 — the touchdown model's
    own input). Four seasons found no lift in the rest — corners out,
    zone-or-man splits, pressure, missed tackles, unit EPA — so they
    are `notes`: shown, never counted. Where no defence-vs-position
    rating is given (college), the unit ranks stand in, as before.

    Counted, not weighed: every counted reason is one point either way."""
    group = _POS_GROUP.get((pos or "").upper(), "")
    u = usage or {}
    pro, con, notes = [], [], []
    o, d = ratings.get(team) or {}, ratings.get(opp) or {}
    measured = bool(allowed)
    lean: list = []
    volume = False

    def dvp(market):
        """The model's own matchup line for this market, counted."""
        from . import defensevs as _D
        stat = _D.model_stat((pos or "").upper(), market)
        if not stat or not _D.transfer((pos or "").upper(), market):
            return
        sign, text = _allowed_line(allowed, stat, opp, n_teams)
        if sign > 0:
            pro.append(text)
        elif sign < 0:
            con.append(text)

    def own_position(stats):
        """What the defence gives up to HIS position — shown, not counted:
        in the NFL only the overall rating predicted (defensevs.MODEL_STAT)."""
        for stat in stats:
            sign, text = _allowed_line(allowed, stat, opp, n_teams)
            if sign:
                notes.append(text)

    def scoring():
        if points is None:
            return
        where = f" ({line_words})" if line_words else ""
        if points >= POINTS_HIGH:
            pro.append(f"The lines expect {team} to score about {points:.0f}{where}")
        elif points <= POINTS_LOW:
            con.append(f"The lines expect {team} to score only about {points:.0f}{where}")

    def unit(side_rank, words, soft_is_pro=True):
        """A unit rank: counted where nothing measured stands in (college),
        a note where it was measured and found flat (the NFL)."""
        if _weak(side_rank, n_teams):
            (notes if measured else (pro if soft_is_pro else con)).append(f"{words} ranks {_ord(side_rank)}")
        elif _strong(side_rank, n_teams):
            (notes if measured else (con if soft_is_pro else pro)).append(f"{words} ranks {_ord(side_rank)}")

    if group in ("wr", "te"):
        lean = ["receptions", "rec_yds", "anytime_td"]
        share = u.get("tgt_share") or 0.0
        if share >= 0.22:
            volume = True
            pro.append(f"Commands {share:.0%} of the targets ({u.get('targets_pg', 0):g} a game)")
        elif u.get("games") and share < 0.12:
            con.append(f"Only {share:.0%} of the targets so far")
        elif share >= 0.18:
            volume = True
        if measured:
            dvp("rec_yds")
            own_position((f"{group}_rec_yds", f"{group}_td"))
        unit(_rank(d, "def", "passing"), f"{opp}'s pass defense")
        scoring()
        for m in (room or {}).get("missing") or []:
            notes.append(f"{m['name']}, {opp}'s starting {m['spot']}, is {m['status'].lower()}")
        soft = (room or {}).get("weakest")
        if soft:
            c = next(x for x in room["corners"] if x["name"] == soft)
            notes.append(f"{soft} ({c['spot']}) has allowed a {c['rating']:.0f} passer rating "
                         f"on {c['targets']} targets")
        sch, sp = scheme or {}, split or {}
        look = ("zone" if (sch.get("zone") or 0) >= 0.65 else
                "man" if (sch.get("man") or 0) >= 0.35 else None)
        other = {"zone": "man", "man": "zone"}.get(look or "")
        if look and sp.get(look) and sp.get(other):
            (tl, yl), (to, yo) = sp[look], sp[other]
            if tl >= 12 and to >= 8:
                a, b = yl / tl, yo / to
                if b and (a / b >= 1.2 or a / b <= 0.8):
                    notes.append(f"Averaged {a:.1f} yards a target against {look} last season "
                                 f"({b:.1f} against {other}); {opp} played {look} "
                                 f"{sch[look]:.0%} of the time")
        for m in mates_out or []:
            pro.append(f"{m} is out — his targets are open")
    elif group == "rb":
        lean = ["rush_yds", "anytime_td"]
        cs = u.get("carry_share") or 0.0
        if cs >= 0.55:
            volume = True
            pro.append(f"Takes {cs:.0%} of the carries ({u.get('carries_pg', 0):g} a game)")
        elif u.get("games") and cs < 0.30:
            con.append(f"Only {cs:.0%} of the carries so far")
        if measured:
            dvp("rush_yds")
            dvp("anytime_td")
        rr = _rank(d, "def", "rushing")
        unit(rr, f"{opp}'s run defense")
        own = _rank(o, "off", "rushing")
        if own and own >= round(n_teams * 0.78):
            (notes if measured else con).append(f"{team}'s run game ranks {_ord(own)}")
        scoring()
        # College only: how the lines meet. A front that stuffs runs at
        # the line against a line that cannot get push.
        stuff, push = _rank(d, "def", "stuff"), _rank(o, "off", "line")
        if _strong(stuff, n_teams) and _weak(push, n_teams):
            con.append(f"{opp} stuffs runs at the line ({_ord(stuff)}) and {team}'s "
                       f"run blocking ranks {_ord(push)}")
        elif _weak(stuff, n_teams) and _strong(push, n_teams):
            pro.append(f"{team}'s run blocking ranks {_ord(push)} against a front "
                       f"that stops few runs at the line ({_ord(stuff)})")
        mt = (tackling or {}).get(opp)
        if mt is not None and mt >= 0.10:
            notes.append(f"{opp} misses {mt:.0%} of its tackles")
        if (u.get("targets_pg") or 0) >= 3.5:
            lean.append("rec_yds")
            stingy = (_allowed_line(allowed, "rb_rush_yds", opp, n_teams)[0] < 0 if measured
                      else bool(rr and rr <= round(n_teams * 0.31)))
            if stingy:
                pro.append(f"{u['targets_pg']:g} targets a game — a strong run defense pushes "
                           f"the ball to him through the air")
        for m in mates_out or []:
            pro.append(f"{m} is out — his carries are open")
    elif group == "qb":
        lean = ["pass_yds", "pass_td"]
        volume = True
        if measured:
            dvp("pass_yds")
        unit(_rank(d, "def", "passing"), f"{opp}'s pass defense")
        scoring()
        havoc = _rank(d, "def", "havoc")
        if _strong(havoc, n_teams):
            con.append(f"{opp}'s defense ranks {_ord(havoc)} in havoc — sacks, tackles for loss, takeaways")
        rush, prot = _rank(d, "def", "pressure"), _rank(o, "off", "pressure")
        if _strong(rush, n_teams) and ((prot and prot >= round(n_teams * 0.62)) or line_out):
            (notes if measured else con).append(
                f"{opp}'s pass rush ranks {_ord(rush)}"
                + (f" and {team} is without {', '.join(line_out)}" if line_out
                   else f" against the {_ord(prot)} pass protection"))
    score = len(pro) - len(con)
    key, label = _label(score, volume)
    return {"player": name, "team": team, "opp": opp, "pos": (pos or "").upper(),
            "read": key, "label": label, "pro": pro, "con": con, "notes": notes, "lean": lean,
            "usage": {k: u.get(k) for k in ("tgt_share", "targets_pg", "carry_share",
                                            "carries_pg", "rec_yds_pg", "rush_yds_pg",
                                            "snap_pct", "games") if u.get(k) is not None}}


def _opens(inj, team: str, opp: str, ratings: dict, charts: dict, usage: dict) -> str:
    """What one injury opens, in a sentence — conditional for a player
    who may yet play."""
    said = _opens_if_out(inj, team, opp, ratings, charts, usage)
    st = str(getattr(inj, "status", "") or "").upper()
    return f"If he sits — {said}" if said and st not in OUT_STATUSES else said


def _opens_if_out(inj, team: str, opp: str, ratings: dict, charts: dict, usage: dict) -> str:
    pos = (getattr(inj, "position", "") or "").upper()
    who = getattr(inj, "player", "")
    if pos in ("CB", "NB", "DB", "S", "FS", "SS"):
        out = type("I", (), {"team": team, "player": who, "status": "OUT"})()
        room = coverage_room(team, (charts or {}).get(team) or [], {}, None, [out])
        up = [c["name"] for c in room["corners"] if c["next_man_up"]]
        return (f"{team}'s coverage thins" + (f" — {', '.join(up)} steps in" if up else "")
                + f"; {opp}'s receivers see the next man up")
    if pos in ("T", "G", "C", "OT", "OG", "OL", "LT", "LG", "RG", "RT"):
        rush = _rank(ratings.get(opp) or {}, "def", "pressure")
        return (f"{team}'s protection weakens" + (f" against the {_ord(rush)} pass rush" if rush else ""))
    if pos in ("DE", "DT", "NT", "EDGE", "OLB", "DL", "LB", "ILB", "MLB"):
        return f"{opp}'s blockers get relief"
    if pos in ("WR", "TE"):
        u = usage.get((team, _key(who))) or {}
        share = u.get("tgt_share")
        return (f"{share:.0%} of {team}'s targets to share out" if share else
                f"{team}'s targets shift")
    if pos in ("RB", "FB"):
        u = usage.get((team, _key(who))) or {}
        share = u.get("carry_share")
        return (f"{share:.0%} of {team}'s carries to share out" if share else
                f"{team}'s carries shift")
    if pos == "QB":
        return f"{team} starts a different quarterback"
    return ""


def scan_game(home: str, away: str, *, ratings: dict, charts: dict, defenders_now: dict,
              defenders_last: dict | None = None, tackling: dict | None = None,
              schemes: dict | None = None, splits: dict | None = None,
              usage: dict | None = None, injuries=None, props: list | None = None,
              scheme_season=None, opponent_adjusted: bool = True,
              allowed: dict | None = None, points: dict | None = None,
              line_words: dict | None = None) -> dict:
    """The whole scan for one game (see the block comment above).

    ``allowed`` is {defence: engine/defensevs ratings} — the model's own
    matchup numbers; ``points`` and ``line_words`` are {team: implied
    points} and {team: "−7 at home, total 49.5"} from the posted lines."""
    usage = usage or {}
    n_teams = max(2, len(ratings or {}))
    gap_bar = max(EDGE_GAP, round(n_teams * 0.3))
    teams = (away, home)
    opp = {away: home, home: away}
    rooms = {t: coverage_room(t, (charts or {}).get(t) or [], defenders_now,
                              defenders_last, injuries) for t in teams}
    lines = {t: _line_out(t, (charts or {}).get(t) or [], injuries) for t in teams}
    edges = unit_edges(away, home, ratings) + unit_edges(home, away, ratings)
    edges = [e for e in edges if abs(e["gap"]) >= gap_bar]
    edges.sort(key=lambda e: -abs(e["gap"]))
    # WHO IS OUT, AND WHAT IT OPENS — starters and anyone the offence leans on.
    starters = {t: {p for row in (charts or {}).get(t) or []
                    for p in (row.get("players") or [])[:3 if row.get("position") == "WR" else 1]}
                for t in teams}
    # A defender who has actually played a part this season counts too —
    # the depth chart drops a player the moment he lands on injured
    # reserve, which is exactly when his absence is the news.
    for (t, _k), v in defenders_now.items():
        if t in starters and ((v.get("targets") or 0) >= MIN_TARGETS or (v.get("pressures") or 0) >= 3):
            starters[t].add(v.get("name") or "")
    by_key = {t: {_key(n) for n in starters[t]} for t in teams}
    inj_rows = []
    for i in injuries or []:
        t, st = getattr(i, "team", ""), str(getattr(i, "status", "") or "").upper()
        if t not in teams or st not in OUT_STATUSES | {"QUESTIONABLE"}:
            continue
        who = getattr(i, "player", "")
        used = usage.get((t, _key(who))) or {}
        if _key(who) not in by_key[t] and (used.get("tgt_share") or 0) < 0.12 \
                and (used.get("carry_share") or 0) < 0.3:
            continue
        inj_rows.append({"team": t, "player": who, "position": getattr(i, "position", ""),
                         "status": st, "opens": _opens(i, t, opp[t], ratings, charts, usage)})
    # THE PLAYERS WITH PROPS IN THIS GAME, each read against his opponent.
    seen, reads = set(), []
    for r in props or []:
        name, team = r.get("player") or "", r.get("team") or ""
        if team not in teams or not name or (team, name) in seen:
            continue
        seen.add((team, name))
        u = usage.get((team, _key(name))) or {}
        pos = r.get("position") or u.get("position") or ""
        group = _POS_GROUP.get(pos.upper(), "")
        mates = []
        for i in injuries or []:
            if getattr(i, "team", "") != team or str(getattr(i, "status", "")).upper() not in OUT_STATUSES:
                continue
            ip = (getattr(i, "position", "") or "").upper()
            mu = usage.get((team, _key(getattr(i, "player", "")))) or {}
            if group in ("wr", "te") and ip in ("WR", "TE") and (mu.get("tgt_share") or 0) >= 0.12:
                mates.append(getattr(i, "player", ""))
            if group == "rb" and ip in ("RB", "FB") and (mu.get("carry_share") or 0) >= 0.3:
                mates.append(getattr(i, "player", ""))
        reads.append(player_read(
            name, team, opp[team], pos, usage=u, ratings=ratings, room=rooms[opp[team]],
            scheme=(schemes or {}).get(opp[team]),
            split=(splits or {}).get((team, _abbr(name))),
            tackling=tackling, line_out=lines[team], mates_out=mates, n_teams=n_teams,
            allowed=(allowed or {}).get(opp[team]), points=(points or {}).get(team),
            line_words=(line_words or {}).get(team, "")))
    order = {k: i for i, (k, _) in enumerate(READS)}
    reads.sort(key=lambda x: (order[x["read"]], -len(x["pro"])))
    # THE PROPS UNDER THE MICROSCOPE: the markets each good read points
    # at, as this board prices them, likeliest first; each says whether
    # it clears the Most Likely bars (65%, no heavier than -250).
    good = {(x["team"], x["player"]): x for x in reads if x["read"] in ("breakout", "good")}
    micro = []
    for r in props or []:
        x = good.get((r.get("team"), r.get("player")))
        if not x or (r.get("market") or "") not in x["lean"]:
            continue
        # Scorer rows carry the model's chance as `model_prob`.
        p = r.get("hit_prob") if r.get("hit_prob") is not None else r.get("model_prob")
        odds = r.get("odds")
        micro.append({"player": r.get("player"), "team": r.get("team"), "market": r.get("market"),
                      "market_label": r.get("market_label") or r.get("market"),
                      "side": r.get("side"), "line": r.get("line"), "odds": odds,
                      "book": r.get("book"), "prob": p, "read": x["read"],
                      "clears": bool(p is not None and p >= 0.65 and odds is not None
                                     and float(odds) >= -250),
                      "edge_pick": bool(r.get("recommended"))})
    micro.sort(key=lambda m: -(m["prob"] or 0))
    return {
        "units": {t: ratings.get(t) for t in teams if ratings.get(t)},
        "edges": edges[:8],
        "coverage": rooms,
        "scheme": {t: (schemes or {}).get(t) for t in teams if (schemes or {}).get(t)},
        "scheme_season": scheme_season,
        "rush": {t: _pass_rush(t, defenders_now, injuries) for t in teams},
        "line_out": lines,
        "injuries": inj_rows,
        "players": reads,
        "microscope": micro[:8],
        "method": {"teams": n_teams, "opponent_adjusted": opponent_adjusted},
    }


# ═══ THE BUILD HOOK ══════════════════════════════════════════════════════════

def scheme_tables(season: int) -> dict:
    """How each defence covered and how each receiver fared against each
    look, from the newest season nflverse has charted (the participation
    file runs a season behind). A finished season never changes, so it is
    worked out once and kept (engine/modelstate); the current season's is
    re-read when it appears. ``{"season", "defense", "receivers"}``."""
    import json
    import os
    from . import modelstate
    from .sources import nflscheme as N
    from .sources.nflpbp import load_pbp_rows
    for yr in (int(season), int(season) - 1):
        path = modelstate.path(f"scheme_nfl_{yr}.json")
        done = yr < int(season)
        if done and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
            except (OSError, ValueError):
                pass
        part = N.load_participation(yr)
        if not part:
            continue
        cols = ("game_id", "play_id", "receiver_player_name", "posteam", "yards_gained", "complete_pass")
        try:
            splits = N.receiver_splits(part, load_pbp_rows(yr, columns=cols))
        except Exception:                                    # noqa: BLE001
            splits = {}
        out = {"season": yr, "defense": N.scheme(part),
               "receivers": {f"{t}|{r}": v for (t, r), v in splits.items()}}
        if done:
            try:
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path + ".tmp", "w", encoding="utf-8") as fh:
                    json.dump(out, fh, separators=(",", ":"))
                os.replace(path + ".tmp", path)
            except OSError:
                pass
        return out
    return {"season": None, "defense": {}, "receivers": {}}


def implied_points(g) -> tuple[dict, dict]:
    """({team: points the lines expect}, {team: the lines in words}) from a
    slate game's POSTED spread and total — ({}, {}) when either is a
    placeholder (models.Game.total_is_posted), because a default 44 is
    not the market's opinion of anything."""
    if g is None or not (getattr(g, "total_is_posted", False) and getattr(g, "spread_is_posted", False)):
        return {}, {}
    total, spread = float(g.total), float(g.spread)          # home spread; negative = home favoured
    fmt = lambda x: "pick'em" if x == 0 else f"{x:+g}".replace("-", "−")   # noqa: E731
    return ({g.home: (total - spread) / 2, g.away: (total + spread) / 2},
            {g.home: f"{fmt(spread)} at home, total {total:g}",
             g.away: f"{fmt(-spread)} on the road, total {total:g}"})


def scan_props(result: dict) -> list[dict]:
    """Every priced row the reads can point at: the stat props, and the
    scorer rows the touchdown board carries (the watch shelf, the long
    shots and the Most Likely scorers), once each."""
    rows = list(result.get("recommendations") or [])
    rows += [r for r in (result.get("longshot_watch") or []) + (result.get("long_shots") or [])
             + [x for x in (result.get("most_likely") or []) if x.get("market") == "anytime_td"]]
    seen, out = set(), []
    for r in rows:
        k = (r.get("player"), r.get("market"), str(r.get("side") or "").lower()
             .replace("yes", "over"), r.get("line") if r.get("market") != "anytime_td" else None)
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def attach_nfl(result: dict, slate, season: int, week: int, depth_rows=None,
               conn=None) -> int:
    """Hang a ``scan`` on every game of an NFL board. Reads only what is
    cached or small (the unit table, this season's defender file, the
    weekly stats the build already fetched); a missing input leaves its
    part of the scan empty, never the board. Returns games scanned."""
    from .sources import nflscheme as N
    from .sources.nflverse import load_weekly_stats, load_snap_counts
    from .sources.depthcharts import team_charts
    if conn is None:
        from . import db
        conn = db.connect()
    ratings = unit_ratings(conn, season, before_week=week)
    charts = team_charts(depth_rows, week)["teams"] if depth_rows else {}
    now_rows = N.load_pfr_def(season)
    defenders_now = N.defenders(now_rows)
    defenders_last = N.defenders(N.load_pfr_def(season - 1))
    tackling = N.team_tackling(now_rows)
    sch = scheme_tables(season)
    splits = {tuple(k.split("|", 1)): v for k, v in (sch.get("receivers") or {}).items()}

    def _safe(fn, *a):
        try:
            return fn(*a)
        except Exception:                                    # noqa: BLE001
            return []
    usage = usage_table(_safe(load_weekly_stats, season), _safe(load_snap_counts, season),
                        before_week=week)
    props = scan_props(result)
    by_pair = {frozenset((g.home, g.away)): g for g in getattr(slate, "games", []) or []}
    # THE MODEL'S OWN MATCHUP NUMBERS, off the slate the board was priced
    # from — the defence-vs-position ratings every prop was multiplied by.
    allowed = {t: getattr(getattr(tm, "defense", None), "ratings", None) or {}
               for t, tm in (getattr(slate, "teams", None) or {}).items()}
    # THE READS AND THE PROPS ARE THE PAID HALF. The units, corners,
    # scheme and injuries are facts anyone can look up, and ride on the
    # game; who we think shines, and at what probability, rides in
    # `scan_reads` — a top-level key on engine/gate.PAID_KEYS, because the
    # paywall's strip does not descend into the rows of `games`.
    reads = result.setdefault("scan_reads", {})
    n = 0
    for gd in result.get("games") or []:
        home, away = gd.get("home"), gd.get("away")
        g = by_pair.get(frozenset((home, away)))
        gprops = [r for r in props if r.get("team") in (home, away)
                  and r.get("opponent") in (home, away)]
        pts, words = implied_points(g)
        scan = scan_game(home, away, ratings=ratings, charts=charts,
                         defenders_now=defenders_now, defenders_last=defenders_last,
                         tackling=tackling, schemes=sch.get("defense") or {},
                         splits=splits, usage=usage,
                         injuries=getattr(g, "injuries", None) or [],
                         props=gprops, scheme_season=sch.get("season"),
                         allowed=allowed, points=pts, line_words=words)
        reads[f"{away}@{home}"] = {"players": scan.pop("players"),
                                   "microscope": scan.pop("microscope")}
        gd["scan"] = scan
        n += 1
    return n


# ═══ COLLEGE ═════════════════════════════════════════════════════════════════
#
# The same scan for every FBS game, from CFBD's advanced season numbers
# (engine/sources/cfbd.parse_advanced): no defender files and no
# charting exist for college, so the scan is the units, the mismatches
# and a read on every player with a prop. NOT opponent-adjusted — CFBD's
# season table is raw, and a schedule of cupcakes flatters a unit; the
# page says so. Blended with last season by plays, like the NFL's.

#: Plays of last season a college rating leans on: about four games.
CFB_PRIOR_PLAYS = 280.0

#: Each college unit's sense, from the OFFENCE's point of view.
CFB_UNITS = {"overall": True, "passing": True, "rushing": True, "success": True,
             "explosive": True, "havoc": False, "line": True, "stuff": False}


def cfb_ratings(current: dict, prior: dict | None = None) -> dict:
    """``{team: {"games", "blend", "off": {unit: {"value","rank"}}, "def"}}``
    from `parse_advanced` shapes keyed by the board's own team keys."""
    prior = prior or {}
    teams = sorted(current or prior)
    out: dict = {}
    for t in teams:
        c, p = (current or {}).get(t) or {}, prior.get(t) or {}
        plays = float(c.get("plays") or 0.0)
        w = plays / (plays + CFB_PRIOR_PLAYS) if p else 1.0
        out[t] = {"games": round(plays / 70) if plays else 0, "blend": round(w, 2)}
        for side in ("off", "def"):
            vals = {}
            for u in CFB_UNITS:
                a, b = (c.get(side) or {}).get(u), (p.get(side) or {}).get(u)
                vals[u] = a if b is None else b if a is None else w * a + (1 - w) * b
            out[t][side] = vals
    for side in ("off", "def"):
        for u, higher in CFB_UNITS.items():
            good_high = higher if side == "off" else not higher
            have = sorted(((t, out[t][side][u]) for t in teams if out[t][side][u] is not None),
                          key=lambda tv: -tv[1] if good_high else tv[1])
            ranks = {t: i + 1 for i, (t, _) in enumerate(have)}
            for t in teams:
                v = out[t][side][u]
                out[t][side][u] = {"value": None if v is None else round(v, 4), "rank": ranks.get(t)}
    return out


def attach_cfb(out: dict, season: int, resolve, fetch=None) -> int:
    """Hang a ``scan`` on every game of a college board; the reads ride
    in ``scan_reads`` like the NFL's. ``resolve`` maps CFBD's school name
    to the board's team key (cfbdata.resolve_team). Returns games scanned;
    no key or no answer scans nothing and says so to the caller."""
    if fetch is None:
        from .sources.cfbd import fetch_advanced as fetch

    def keyed(year):
        try:
            raw = fetch(year)
        except Exception:                                    # noqa: BLE001
            return {}
        got = {}
        for school, v in (raw or {}).items():
            k = resolve(school)
            if k:
                got[k] = v
        return got
    cur, pri = keyed(int(season)), keyed(int(season) - 1)
    if not cur and not pri:
        return 0
    ratings = cfb_ratings(cur, pri)
    reads = out.setdefault("scan_reads", {})
    props = list(out.get("recommendations") or [])
    n = 0
    for gd in out.get("games") or []:
        home, away = gd.get("home"), gd.get("away")
        if home not in ratings or away not in ratings:
            continue
        gprops = [r for r in props if r.get("team") in (home, away)
                  and (r.get("opponent") in (home, away) or not r.get("opponent"))]
        scan = scan_game(home, away, ratings=ratings, charts={}, defenders_now={},
                         props=gprops, opponent_adjusted=False)
        reads[f"{away}@{home}"] = {"players": scan.pop("players"),
                                   "microscope": scan.pop("microscope")}
        gd["scan"] = scan
        n += 1
    return n


def backfill(seasons, conn=None) -> dict:
    """Fold whole seasons of play-by-play into ``team_units`` — once for
    last season (the Tuesday refresh keeps this one current). One read
    of each file; ``{season: rows}``."""
    from . import db
    from .sources.nflpbp import load_pbp_rows
    from .sources.nflunits import Units, UNIT_COLS
    conn = conn or db.connect()
    out = {}
    for yr in seasons:
        u = Units()
        for r in load_pbp_rows(int(yr), columns=UNIT_COLS):
            u.add(r)
        out[int(yr)] = db.upsert_team_units(conn, u.rows(int(yr)))
        conn.commit()
    return out


def _main(argv) -> int:
    """``python3 -m engine.gamescan backfill 2025 2026`` · ``show 2026 3 ATL GB``"""
    if len(argv) >= 2 and argv[0] == "backfill":
        for yr, n in backfill([int(a) for a in argv[1:]]).items():
            print(f"  {yr}: {n:,} team-week unit rows")
        return 0
    if len(argv) == 5 and argv[0] == "show":
        from . import db
        season, week, a, b = int(argv[1]), int(argv[2]), argv[3].upper(), argv[4].upper()
        r = unit_ratings(db.connect(), season, before_week=week)
        if not r:
            print("  no unit rows yet — run: python3 -m engine.gamescan backfill "
                  f"{season - 1} {season}")
            return 1
        for t in (a, b):
            x = r.get(t) or {}
            print(f"  {t}  games {x.get('games')}  this season {int((x.get('blend') or 0) * 100)}%")
            for side in ("off", "def"):
                print(f"    {side}: " + "  ".join(f"{u} {v['rank']}" for u, v in (x.get(side) or {}).items()))
        for e in unit_edges(a, b, r) + unit_edges(b, a, r):
            if abs(e["gap"]) >= EDGE_GAP:
                print(f"  edge: {e['off']} {e['label']} {e['off_rank']} vs {e['def']} {e['def_rank']} ({e['gap']:+d})")
        return 0
    print(_main.__doc__)
    return 2


if __name__ == "__main__":
    import sys
    raise SystemExit(_main(sys.argv[1:]))
