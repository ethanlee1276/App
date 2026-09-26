"""Matchup picks: every game, broken down offence against defence, into the
touchdowns and the yards-and-catches bets the matchup makes a case for.

Ethan, 2026-09-26: "me and the AI went through each offense and defense of
every team and figured out where the breakout candidates were, and who had
a good matchup and who had a bad matchup ... and what we came back with"
— Stevenson under 47.5 rushing, Walker and Rice to score, Adams 5 catches,
Kyren Williams 60 and 60, Gibbs, St. Brown and Olave against New Orleans,
LaPorta, Knox, Kincaid, Allen and Cook in Lions–Bills. The journal had
none of them, on any board, in any market (probed on the box the same
day): the site's shelves are built to show few touchdowns — Most Likely
floors at 55% and seats the five likeliest scorers of the SLATE, the
scenarios shelf takes eight, never a quarterback, and demands a soft
defence; the value board wants an edge he said he does not care about.

So this goes game by game, the way that conversation did:

TOUCHDOWNS. Every priced scorer in the game who is not on the injury report
or pulled by the books, scored on the matchup — his team's expected points
(offence), the opponent's defence at his position (the pass defence for a
receiver or tight end, the run defence for a back or a quarterback), his
expected red-zone chances, and red-zone trips (his offence getting in, the
opponent letting teams in; engine/redzone) — each 0–2, out of 8. A scorer
is a pick when our chance clears TD_MIN_PROB and the matchup makes a case
(TD_MATCHUP_MIN), or when our chance alone is TD_STRONG_PROB — the goal-
line back or the running quarterback everybody expects to score. Ranked by
our chance, TD_PER_GAME a game, TD_PER_TEAM a side. Quarterbacks count.

YARDS AND CATCHES. The matchup scan already reads every key player — could
shine (breakout / good matchup) or could struggle (tough / avoid) — and the
markets that read points at. A pick is that market on the read's side
(shine → over, struggle → under) at the posted line, where OUR number
agrees at PROP_MIN_PROB or better. PROP_PER_GAME a game, PROP_PER_PLAYER a
player.

No edge requirement, no 55% floor, no slate-wide cap: these are the
matchup's picks, and the chance shown is the model's. Journaled on paper
(ledger categories matchup_td / matchup_prop), so the record — not an
argument — says how they do against the other methods.

Standard library only.
"""
from __future__ import annotations

from .tdscenarios import OFFENSE_POINTS, DEFENSE_RANK, RED_ZONE_CHANCES, TRIPS_REL, _pts, _ord

#: A scorer below this chance is not a pick, whatever the matchup.
TD_MIN_PROB = 0.28
#: At this chance he is a pick on the chance alone.
TD_STRONG_PROB = 0.45
#: Matchup points (of 8) that make the case for a scorer under TD_STRONG_PROB.
TD_MATCHUP_MIN = 4
TD_PER_GAME = 4
TD_PER_TEAM = 3

#: The markets a read can turn into a yards-or-catches pick.
PROP_MARKETS = ("receptions", "rec_yds", "rush_yds", "pass_yds")
#: Our chance on the read's side at the posted line.
PROP_MIN_PROB = 0.55
#: The longest price a yards-or-catches pick is taken at. The box, 2026-09-26:
#: "Terrance Ferguson UNDER 49.5 -380 ProphetX" was an exchange rung, not a
#: market; a -380 under says nothing a reader can use.
PROP_MAX_JUICE = -250
#: A real role before a read's line means anything — targets a game for the
#: receiving markets, carries a game for rushing. The same box run picked
#: Brady Russell under 5 rushing yards and Dyami Brown under 1.5 catches.
PROP_MIN_TARGETS = 3.0
PROP_MIN_CARRIES = 6.0
PROP_PER_GAME = 4
PROP_PER_PLAYER = 2

LEAN_SIDE = {"breakout": "over", "good": "over", "tough": "under", "avoid": "under"}
_TD_GROUP = {"WR": "passing", "TE": "passing", "RB": "rushing", "FB": "rushing", "QB": "rushing"}
_UNIT_WORD = {"passing": "pass", "rushing": "run"}


def td_matchup(row: dict, opp_units: dict | None, rz_own: dict | None, rz_opp: dict | None,
               n_teams: int = 32, usage: dict | None = None) -> dict:
    """{"points": {...}, "score": 0-8, "lines": [...]} for one scorer row."""
    pos = str(row.get("position") or "").upper()
    unit = _TD_GROUP.get(pos, "passing")
    implied = row.get("implied_total")
    rank = (((opp_units or {}).get("def") or {}).get(unit) or {}).get("rank")
    rz = row.get("rz_chances")
    off_rel, def_rel = (rz_own or {}).get("off_rel"), (rz_opp or {}).get("def_rel")
    trips = [v for v in (off_rel, def_rel) if v is not None]
    trips_rel = sum(trips) / len(trips) if trips else None
    pts = {"offense": _pts(implied, OFFENSE_POINTS), "defense": _pts(rank, DEFENSE_RANK),
           "red_zone": _pts(rz, RED_ZONE_CHANCES), "trips": _pts(trips_rel, TRIPS_REL)}
    team, opp = row.get("team") or "", row.get("opponent") or ""
    lines = []
    if implied is not None:
        lines.append(f"{team} expected to score {float(implied):.1f} by the lines")
    if rank is not None:
        lines.append(f"{opp}’s {_UNIT_WORD[unit]} defence ranks {_ord(rank)} of {n_teams}"
                     + (" (he scores on the ground)" if pos == "QB" else ""))
    u = usage or {}
    share = u.get("carry_share") if unit == "rushing" and pos != "QB" else u.get("tgt_share")
    if share is not None and pos != "QB":
        lines.append(f"{float(share):.0%} of the {'carries' if unit == 'rushing' else 'targets'}")
    if rz is not None:
        lines.append(f"{float(rz):.1f} expected red-zone chances")
    if trips:
        bits = []
        if off_rel is not None:
            bits.append(f"{team} gets {float(rz_own.get('off')):.1f} red-zone plays a game "
                        f"({off_rel * 100:+.0f}% vs the league)")
        if def_rel is not None:
            bits.append(f"{opp} allows {float(rz_opp.get('def')):.1f} ({def_rel * 100:+.0f}%)")
        lines.append(" · ".join(bits))
    return {"points": pts, "score": sum(pts.values()), "lines": lines}


def _label(score: int) -> str:
    return "Strong matchup" if score >= 6 else "Good matchup" if score >= TD_MATCHUP_MIN else "Likely scorer"


def td_picks(game: dict, watch: list, reads: list, pulled=(), positions: dict | None = None) -> list:
    """This game's touchdown picks from every priced scorer in it. A scorer
    row carries no position; ``positions`` ({player: pos}, from the prop
    rows and the reads) supplies it, so a quarterback reads as one."""
    home, away = game.get("home"), game.get("away")
    scan = game.get("scan") or {}
    units, rz = scan.get("units") or {}, scan.get("redzone") or {}
    n_teams = int(scan.get("n_teams") or 32)
    usage = {(x.get("player") or ""): x.get("usage") for x in reads or []}
    out_players = {(x.get("player") or "") for x in reads or [] if x.get("own_status")}
    pulled = set(pulled or ()) | set(scan.get("pulled") or ())
    rows = []
    for r in watch or []:
        team, opp = r.get("team"), r.get("opponent")
        if {team, opp} != {home, away} or r.get("model_prob") is None or not r.get("odds"):
            continue
        name = r.get("player") or ""
        if str(r.get("injury_status") or "").strip() or name in out_players or name in pulled:
            continue
        prob = float(r["model_prob"])
        if prob < TD_MIN_PROB:
            continue
        pos = str(r.get("position") or (positions or {}).get(name) or "").upper()
        r = dict(r, position=pos)
        m = td_matchup(r, units.get(opp), rz.get(team), rz.get(opp), n_teams, usage.get(name))
        if m["score"] < TD_MATCHUP_MIN and prob < TD_STRONG_PROB:
            continue
        rows.append({
            "kind": "td", "matchup_pick": True, "player": name, "team": team, "opponent": opp,
            "position": str(r.get("position") or "").upper(), "headshot": r.get("headshot") or "",
            "market": "anytime_td", "market_label": "Anytime TD", "side": "YES", "line": 0.5,
            "odds": r.get("odds"), "book": r.get("book") or "", "model_prob": round(prob, 4),
            "kickoff": r.get("kickoff") or game.get("kickoff") or "",
            "game_date": r.get("game_date") or game.get("date") or "",
            "matchup_score": m["score"], "matchup_points": m["points"], "matchup_lines": m["lines"],
            "label": _label(m["score"]),
        })
    rows.sort(key=lambda x: (-x["model_prob"], -x["matchup_score"]))
    picked, per_team = [], {}
    for x in rows:
        if per_team.get(x["team"], 0) >= TD_PER_TEAM:
            continue
        picked.append(x)
        per_team[x["team"]] = per_team.get(x["team"], 0) + 1
        if len(picked) >= TD_PER_GAME:
            break
    return picked


def _side_price(row: dict, side: str):
    """(odds, book) for ``side`` at the row's own line: the row's price when
    it is on that side, else the best bettable quote at that line — an
    exchange only when a sportsbook is close (odds.prefer_sportsbook)."""
    from types import SimpleNamespace as NS
    from .odds import bettable_lines, prefer_sportsbook
    from .odds import is_exchange
    key = "over_odds" if side == "over" else "under_odds"
    # A REAL SPORTSBOOK QUOTE AT THIS LINE, OR NO PICK. A "proxy" row is a
    # line the model hung itself (eight of eighteen picks on the box's first
    # run, 2026-09-26); an exchange alone at a line is a rung of its ladder.
    lines = [NS(book=ln.get("book") or "", line=ln.get("line"), over_odds=ln.get(key))
             for ln in row.get("all_lines") or []
             if ln.get("line") == row.get("line") and ln.get(key)
             and (ln.get("book") or "").lower() != "proxy"]
    lines = bettable_lines(lines) if lines else []
    if not any(not is_exchange(ln.book) for ln in lines):
        return None, ""
    best = prefer_sportsbook(lines)
    return (best.over_odds, best.book) if best else (None, "")


def prop_picks(game: dict, reads: list, props: list) -> list:
    """This game's yards-and-catches picks: each read's markets on its side,
    where our number agrees."""
    home, away = game.get("home"), game.get("away")
    by_key: dict = {}
    for r in props or []:
        if r.get("market") in PROP_MARKETS and r.get("line") is not None and r.get("hit_prob") is not None:
            by_key.setdefault((r.get("player") or "", r.get("market")), r)
    rows = []
    for x in reads or []:
        side = LEAN_SIDE.get(x.get("read"))
        if not side or x.get("own_status") or {x.get("team"), x.get("opp")} != {home, away}:
            continue
        for mk in x.get("lean") or []:
            r = by_key.get((x.get("player") or "", mk))
            if not r or str(r.get("injury_status") or "").strip():
                continue
            u = x.get("usage") or {}
            role = u.get("carries_pg") if mk == "rush_yds" else u.get("targets_pg") if mk != "pass_yds" else 99
            if role is None or float(role) < (PROP_MIN_CARRIES if mk == "rush_yds" else PROP_MIN_TARGETS):
                continue
            hp = float(r["hit_prob"])
            prob = hp if str(r.get("side") or "").lower() == side else 1.0 - hp
            if prob < PROP_MIN_PROB:
                continue
            odds, book = _side_price(r, side)
            if not odds or int(odds) < PROP_MAX_JUICE:
                continue
            rows.append({
                "kind": "prop", "matchup_pick": True, "player": r.get("player"), "team": r.get("team"),
                "opponent": r.get("opponent"), "position": r.get("position") or x.get("pos") or "",
                "headshot": r.get("headshot") or x.get("headshot") or "",
                "market": mk, "market_label": r.get("market_label") or mk,
                "side": side.upper(), "line": r.get("line"), "odds": odds, "book": book,
                "model_prob": round(prob, 4), "projection": r.get("projection"),
                "kickoff": r.get("kickoff") or game.get("kickoff") or "",
                "game_date": r.get("game_date") or game.get("date") or "",
                "read": x.get("read"), "label": x.get("label"),
                "matchup_lines": list(x.get("pro") or [])[:3] if side == "over" else list(x.get("con") or [])[:3],
            })
    rows.sort(key=lambda x: -x["model_prob"])
    picked, per_player = [], {}
    for x in rows:
        if per_player.get(x["player"], 0) >= PROP_PER_PLAYER:
            continue
        picked.append(x)
        per_player[x["player"]] = per_player.get(x["player"], 0) + 1
        if len(picked) >= PROP_PER_GAME:
            break
    return picked


def positions_map(props: list, scan_reads: dict) -> dict:
    """{player: position} from the prop rows, then the reads — a scorer row
    carries none."""
    positions = {r.get("player"): r.get("position") for r in props or [] if r.get("position")}
    for game in (scan_reads or {}).values():
        for x in (game or {}).get("players") or []:
            if x.get("pos"):
                positions.setdefault(x.get("player"), x.get("pos"))
    return positions


def build(games: list, scan_reads: dict, watch: list, props: list) -> list:
    """[{"game", "home", "away", "kickoff", "td": [...], "props": [...]}] for
    every game with a scan, in the board's game order."""
    positions = positions_map(props, scan_reads)
    out = []
    for g in games or []:
        home, away = g.get("home"), g.get("away")
        key = f"{away}@{home}"
        reads = ((scan_reads or {}).get(key) or {}).get("players") or []
        if not g.get("scan") and not reads:
            continue
        td = td_picks(g, watch, reads, g.get("pulled_players") or (), positions)
        pp = prop_picks(g, reads, props)
        for r in td + pp:
            r["game"] = key
        if td or pp:
            out.append({"game": key, "home": home, "away": away,
                        "kickoff": g.get("kickoff") or "", "td": td, "props": pp})
    return out


def journal_rows(board: list, kind: str) -> list:
    """The board's picks of one kind ("td" or "prop"), flat, for the ledger."""
    return [r for g in board or [] for r in g.get("td" if kind == "td" else "props") or []]
