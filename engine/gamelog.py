"""A player's game log, one line a game, in every league (2026-11-16).

Ethan, with ESPN's game log for Joe Burrow: "we should have game logs for
every player too that you can look up and see for each player."

The history file already keeps one row per player, stat and game in every
league (`player_game_logs`). `season_log` turns one player's season into a
line a game: the day (and the week, in football), the opponent and where,
the result and the score off the `games` table, and the league's own columns
grouped the way a box score groups them (passing, rushing and receiving; the
basketball box; a skater's or a goalie's line; a hitter's or a pitcher's).
The season's totals and its per-game averages close it. A group is shown
only where the player has a number in it, a column only where the file keeps
it, so a receiver's log is no wall of empty passing columns.

Facts, not picks: served free (server.py /api/players/gamelog) on the same
footing as the logs behind the player page, and drawn by js/gamelog.js.
"""
from __future__ import annotations

import datetime as _dt
import os
import re

from . import db as _db

# How a column is worked out from one game's stats (and from the season's):
#   ("sum", m, ...)   the first of the markets the file keeps
#   ("pct", made, tried)  made over tried, as a percentage
#   ("avg", num, den)     num over den
#   ("made", made, tried) "made-tried"
#   ("max", m)            the most in one game (a kicker's long): a season's
#                         is its best game's, never a sum (PEAK)
#   ("rating",)           the passer rating (the NFL's; college's efficiency)
#   ("toi", m)            time on ice in minutes, an average over the season
#   ("ip", outs)          innings pitched from outs ("6.1")
#   ("bavg", num, den)    a batting rate as baseball prints it (".312")
#   ("obp", h, bb, hbp, ab, sf)      on-base percentage (".385")
#   ("ops", h, bb, hbp, ab, sf, tb)  on-base plus slugging (".912")
#   ("era", er, outs)     earned runs a nine innings ("3.45")
#   ("whip", h, bb, outs) walks and hits an inning ("1.12")
#   ("dec", w, l, sv)     a pitcher's decision ("W"); a season's, the record ("10-5")
FOOTBALL = (
    ("passing", "Passing", ("pass_att",), (
        ("cmp", "CMP", "Completions", ("sum", "pass_cmp")),
        ("att", "ATT", "Passing attempts", ("sum", "pass_att")),
        ("yds", "YDS", "Passing yards", ("sum", "pass_yds")),
        ("pct", "CMP%", "Completion percentage", ("pct", "pass_cmp", "pass_att")),
        ("avg", "AVG", "Yards per pass attempt", ("avg", "pass_yds", "pass_att")),
        ("td", "TD", "Passing touchdowns", ("sum", "pass_td")),
        ("int", "INT", "Interceptions thrown", ("sum", "pass_int")),
        ("rtg", "RTG", "Passer rating", ("rating",)))),
    ("rushing", "Rushing", ("carries", "rush_att"), (
        ("car", "CAR", "Rushing attempts", ("sum", "carries", "rush_att")),
        ("yds", "YDS", "Rushing yards", ("sum", "rush_yds")),
        ("avg", "AVG", "Yards per rush", ("avg", "rush_yds", "carries")),
        ("td", "TD", "Rushing touchdowns", ("sum", "rush_td")))),
    ("receiving", "Receiving", ("receptions", "targets"), (
        ("rec", "REC", "Receptions", ("sum", "receptions")),
        ("tgt", "TGT", "Targets", ("sum", "targets")),
        ("yds", "YDS", "Receiving yards", ("sum", "rec_yds")),
        ("avg", "AVG", "Yards per catch", ("avg", "rec_yds", "receptions")),
        ("td", "TD", "Receiving touchdowns", ("sum", "rec_td")))),
    # A KICKER'S AND A DEFENDER'S LINES (2026-11-17; Ethan, with Cameron
    # Dicker's page: "the player page is missing a bunch of data"), from
    # engine/ingest's NFL_KICKING_MARKETS and NFL_DEFENSE_MARKETS.
    ("kicking", "Kicking", ("kick_pts", "fg_att", "xp_att"), (
        ("fg", "FG", "Field goals made-attempted", ("made", "fg_made", "fg_att")),
        ("pct", "FG%", "Field goal percentage", ("pct", "fg_made", "fg_att")),
        ("lng", "LNG", "Longest field goal made", ("max", "fg_long")),
        ("fg50", "50+", "Field goals made from 50 yards or more", ("sum", "fg_50")),
        ("xp", "XP", "Extra points made-attempted", ("made", "xp_made", "xp_att")),
        ("pts", "PTS", "Kicking points", ("sum", "kick_pts")))),
    ("defense", "Defense", ("tackles_ast", "tackles_solo"), (
        ("tot", "TOT", "Total tackles", ("sum", "tackles_ast")),
        ("solo", "SOLO", "Solo tackles", ("sum", "tackles_solo")),
        ("sack", "SACK", "Sacks", ("sum", "def_sacks")),
        ("tfl", "TFL", "Tackles for loss", ("sum", "def_tfl")),
        ("qbh", "QBH", "Quarterback hits", ("sum", "def_qb_hits")),
        ("int", "INT", "Interceptions", ("sum", "def_int")),
        ("pd", "PD", "Passes defended", ("sum", "def_pd")),
        ("ff", "FF", "Forced fumbles", ("sum", "def_ff")),
        ("td", "TD", "Defensive touchdowns", ("sum", "def_td")))),
)
HOOPS = (
    ("box", "", ("min", "pts"), (
        ("min", "MIN", "Minutes", ("sum", "min")),
        ("pts", "PTS", "Points", ("sum", "pts")),
        ("reb", "REB", "Rebounds", ("sum", "reb")),
        ("ast", "AST", "Assists", ("sum", "ast")),
        ("stl", "STL", "Steals", ("sum", "stl")),
        ("blk", "BLK", "Blocks", ("sum", "blk")),
        ("tov", "TO", "Turnovers", ("sum", "tov")),
        ("fg", "FG", "Field goals made-attempted", ("made", "fgm", "fga")),
        ("fgp", "FG%", "Field goal percentage", ("pct", "fgm", "fga")),
        ("fg3", "3PT", "Three-pointers made-attempted", ("made", "fg3m", "fg3a")),
        # The two percentages a box score prints beside its makes
        # (2026-11-17), off the makes and tries already stored.
        ("fg3p", "3P%", "Three-point percentage", ("pct", "fg3m", "fg3a")),
        ("ft", "FT", "Free throws made-attempted", ("made", "ftm", "fta")),
        ("ftp", "FT%", "Free throw percentage", ("pct", "ftm", "fta")),
        ("oreb", "OREB", "Offensive rebounds", ("sum", "oreb")))),
)
HOCKEY = (
    # hits and blocks too: a grinder with neither a point nor a shot played
    ("skater", "", ("goals", "assists", "sog", "points", "hits", "blocks"), (
        ("g", "G", "Goals", ("sum", "goals")),
        ("a", "A", "Assists", ("sum", "assists")),
        ("pts", "PTS", "Points", ("sum", "points")),
        # A skater's plus-minus and penalty minutes (2026-11-17), stored from
        # the box score since then (engine/sources/nhldata LATER_MARKETS).
        ("pm", "+/-", "Plus-minus", ("sum", "plus_minus")),
        ("pim", "PIM", "Penalty minutes", ("sum", "pim")),
        ("sog", "SOG", "Shots on goal", ("sum", "sog")),
        ("blk", "BLK", "Blocked shots", ("sum", "blocks")),
        ("hit", "HIT", "Hits", ("sum", "hits")),
        ("ppg", "PPG", "Power-play goals", ("sum", "ppg")),
        ("toi", "TOI", "Time on ice", ("toi", "toi")))),
    ("goalie", "Goalie", ("shots_against", "saves"), (
        ("sa", "SA", "Shots against", ("sum", "shots_against")),
        ("sv", "SV", "Saves", ("sum", "saves")),
        ("ga", "GA", "Goals against", ("sum", "goals_against")),
        ("svp", "SV%", "Save percentage", ("pct", "saves", "shots_against")),
        ("toi", "TOI", "Time on ice", ("toi", "toi")))),
)
BASEBALL = (
    # THE LINE A BOX SCORE PRINTS (2026-11-17; Ethan: "yes build it all").
    # The file kept the four numbers the props grade (plate appearances, hits,
    # total bases, home runs; a pitcher's outs and strikeouts); each final
    # game's box score now adds every player's whole line (engine/mlb/
    # fulllines). A season read before its box scores were filled shows the
    # props' numbers alone: a column shows only where the file keeps it.
    ("batting", "Batting", ("pa", "hits", "total_bases"), (
        ("pa", "PA", "Plate appearances", ("sum", "pa")),
        ("ab", "AB", "At bats", ("sum", "at_bats")),
        ("r", "R", "Runs", ("sum", "runs")),
        ("h", "H", "Hits", ("sum", "hits")),
        ("2b", "2B", "Doubles", ("sum", "doubles")),
        ("3b", "3B", "Triples", ("sum", "triples")),
        ("hr", "HR", "Home runs", ("sum", "home_runs")),
        ("rbi", "RBI", "Runs batted in", ("sum", "rbis")),
        ("bb", "BB", "Walks", ("sum", "walks")),
        ("so", "SO", "Strikeouts", ("sum", "batter_strikeouts")),
        ("sb", "SB", "Stolen bases", ("sum", "stolen_bases")),
        ("tb", "TB", "Total bases", ("sum", "total_bases")),
        ("avg", "AVG", "Batting average", ("bavg", "hits", "at_bats")),
        ("obp", "OBP", "On-base percentage", ("obp", "hits", "walks", "hbp", "at_bats", "sac_flies")),
        ("slg", "SLG", "Slugging percentage", ("bavg", "total_bases", "at_bats")),
        ("ops", "OPS", "On-base plus slugging",
         ("ops", "hits", "walks", "hbp", "at_bats", "sac_flies", "total_bases")))),
    ("pitching", "Pitching", ("outs",), (
        ("ip", "IP", "Innings pitched", ("ip", "outs")),
        ("h", "H", "Hits allowed", ("sum", "hits_allowed")),
        ("r", "R", "Runs allowed", ("sum", "runs_allowed")),
        ("er", "ER", "Earned runs", ("sum", "earned_runs")),
        ("bb", "BB", "Walks", ("sum", "walks_allowed")),
        ("k", "K", "Strikeouts", ("sum", "strikeouts")),
        ("hr", "HR", "Home runs allowed", ("sum", "home_runs_allowed")),
        ("pc", "PC", "Pitches", ("sum", "pitches")),
        ("dec", "DEC", "Decision: win, loss or save", ("dec", "wins", "losses", "saves")),
        ("era", "ERA", "Earned run average", ("era", "earned_runs", "outs")),
        ("whip", "WHIP", "Walks and hits an inning", ("whip", "hits_allowed", "walks_allowed", "outs")))),
)
LAYOUTS = {"nfl": FOOTBALL, "cfb": FOOTBALL, "nba": HOOPS, "wnba": HOOPS, "cbb": HOOPS, "nhl": HOCKEY,
           "mlb": BASEBALL}
#: A league whose `period` is a week number, not a day.
WEEKLY = ("nfl", "cfb")
#: The stats a season holds at their best game, not their sum (the "max" rule).
PEAK = frozenset({"fg_long"})
#: A RATE READS ONLY THE GAMES WITH THEIR WHOLE LINE (2026-11-17). The file
#: keeps a hitter's hits and total bases (the props' numbers) for games whose
#: box score it may not hold: hits over no at-bats would lift an average. A
#: game carrying its box score's line (at-bats for a hitter, earned runs for a
#: pitcher) also adds that line's numbers under "<market>|whole", and a rate
#: (WHOLE_RATES) reads those wherever a season has them.
WHOLE = {"at_bats": ("at_bats", "hits", "total_bases", "walks", "hbp", "sac_flies"),
         "earned_runs": ("earned_runs", "outs", "hits_allowed", "walks_allowed")}
WHOLE_RATES = frozenset({"bavg", "obp", "ops", "era", "whip"})
#: A game log prints these as the season's through each game, as a box score's
#: and ESPN's game logs do: one game's batting average is noise.
RUNNING = WHOLE_RATES


def _pairs() -> frozenset:
    """Every two markets a column reads together (a percentage, an average, made-tried), in every layout."""
    out = set()
    for layout in LAYOUTS.values():
        for group in layout:
            for c in group[-1]:
                how = c[3]
                if how[0] in ("pct", "avg", "made") and len(how) == 3:
                    out.add((how[1], how[2]))
    return frozenset(out)


#: EACH NUMBER OVER THE GAMES THAT CARRY IT (step ACV, 23 November 2026). A season can hold games whose box score
#: was read before a column was kept: the WNBA's older games carry made threes (the old "3PT" column) but no
#: attempts, steals, blocks or turnovers until the nightly re-read reaches them (step ABO), and A'ja Wilson's 2026
#: line read 3PT "0.9-0.8" and 3P% 113.2, every column divided by all 48 games. A season now counts the games each
#: market is in ("<market>|n"), and a pair a column reads together (PAIRS) is summed over the games carrying both
#: ("<a>|<b>|a", "<a>|<b>|b", "<a>|<b>|n"): an average divides by the games that carry it, a percentage and a
#: made-tried read only the games with both.
PAIRS = _pairs()


def add_up(into: dict, stats: dict) -> dict:
    """One game's stats into a running season: summed, except a PEAK stat,
    which keeps its most; a game with its whole line adds it again (WHOLE);
    each market's games counted and each PAIR summed where both are there."""
    for m, v in stats.items():
        if m in PEAK:
            into[m] = max(into.get(m, v), v)
        else:
            into[m] = into.get(m, 0.0) + v
        into[f"{m}|n"] = into.get(f"{m}|n", 0) + 1
    for key, marks in WHOLE.items():
        if stats.get(key) is not None:
            for m in marks:
                into[f"{m}|whole"] = into.get(f"{m}|whole", 0.0) + (stats.get(m) or 0.0)
    for a, b in PAIRS:
        va, vb = stats.get(a), stats.get(b)
        if va is not None and vb is not None:
            into[f"{a}|{b}|a"] = into.get(f"{a}|{b}|a", 0.0) + va
            into[f"{a}|{b}|b"] = into.get(f"{a}|{b}|b", 0.0) + vb
            into[f"{a}|{b}|n"] = into.get(f"{a}|{b}|n", 0) + 1
    return into


def paired(s: dict, a: str, b: str) -> tuple:
    """(a, b, games): a season's two markets over the games carrying both (add_up, step ACV), where the stats
    are a season's; else the two as kept, and no count (one game's line)."""
    n = s.get(f"{a}|{b}|n")
    if n:
        return s.get(f"{a}|{b}|a"), s.get(f"{a}|{b}|b"), n
    return s.get(a), s.get(b), None


def games_with(s: dict, market: str, played: int) -> int:
    """How many of a season's games carry ``market`` (add_up, step ACV); ``played`` where it was not counted."""
    return int(s.get(f"{market}|n") or played or 0)
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _first(stats: dict, markets) -> float | None:
    for m in markets:
        if stats.get(m) is not None:
            return float(stats[m])
    return None


def shows(games, marks) -> bool:
    """Does a group belong on a player's page: a number other than zero in
    any of its marks, in any game. A receiver's carries of 0 every week are
    no rushing line, so a group of zeros stays off. But every mark counts,
    not only the first one stored (2026-11-17): read that way, a skater with
    no goal yet had no skater group at all, so a defenseman with assists
    and shots all season had an empty page and game log."""
    return any(g["stats"].get(m) for g in games for m in marks)


def _rating(sport: str, s: dict) -> float | None:
    att = s.get("pass_att") or 0.0
    if att <= 0:
        return None
    cmp_, yds = s.get("pass_cmp") or 0.0, s.get("pass_yds") or 0.0
    td, ints = s.get("pass_td") or 0.0, s.get("pass_int") or 0.0
    if sport == "cfb":
        # College's passer efficiency, the number ESPN's college logs print.
        return round((8.4 * yds + 330 * td + 100 * cmp_ - 200 * ints) / att, 1)
    clip = lambda x: max(0.0, min(2.375, x))                     # noqa: E731
    a, b = clip((cmp_ / att - 0.3) * 5), clip((yds / att - 3) * 0.25)
    c, d = clip(td / att * 20), clip(2.375 - ints / att * 25)
    return round((a + b + c + d) / 6 * 100, 1)


def _whole(s: dict, m: str):
    """A rate's number: the games with their whole line, where the stats are a
    season's that has them (WHOLE); else the number as kept."""
    w = s.get(f"{m}|whole")
    return w if w is not None else s.get(m)


def rate3(x: float) -> str:
    """A batting rate as baseball prints it: .312, and 1.000."""
    out = f"{x:.3f}"
    return out[1:] if out.startswith("0.") else out


def _obp(s: dict, h: str, bb: str, hbp: str, ab: str, sf: str) -> float | None:
    hits, at_bats = _whole(s, h), _whole(s, ab)
    if hits is None or at_bats is None:
        return None
    walks, hit_by, sac = (_whole(s, m) or 0.0 for m in (bb, hbp, sf))
    den = at_bats + walks + hit_by + sac
    return (hits + walks + hit_by) / den if den else None


def _baseball(kind: str, how: tuple, s: dict, games: int):
    """The baseball rates and a pitcher's decision (the kinds above)."""
    if kind == "bavg":
        num, den = _whole(s, how[1]), _whole(s, how[2])
        return None if num is None or not den else rate3(num / den)
    if kind == "obp":
        v = _obp(s, *how[1:6])
        return None if v is None else rate3(v)
    if kind == "ops":
        v, ab, tb = _obp(s, *how[1:6]), _whole(s, how[4]), _whole(s, how[6])
        return None if v is None or tb is None else rate3(v + (tb / ab if ab else 0.0))
    if kind == "era":
        er, outs = _whole(s, how[1]), _whole(s, how[2])
        return None if er is None or not outs else f"{er * 27.0 / outs:.2f}"
    if kind == "whip":
        h, bb, outs = _whole(s, how[1]), _whole(s, how[2]), _whole(s, how[3])
        return None if h is None or bb is None or not outs else f"{(h + bb) * 3.0 / outs:.2f}"
    if kind == "dec":
        w, lo, sv = (int(s.get(m) or 0) for m in how[1:4])
        if not (w or lo or sv):
            return None
        if games <= 1 and w + lo + sv == 1:
            return "W" if w else "L" if lo else "SV"
        return f"{w}-{lo}" + (f", {sv} SV" if sv else "")
    return None


def value(sport: str, how: tuple, s: dict, games: int = 1):
    """One column's value from a game's stats, or from the season's summed
    stats (``games`` played, for the averages a sum cannot carry)."""
    kind = how[0]
    if kind in ("bavg", "obp", "ops", "era", "whip", "dec"):
        return _baseball(kind, how, s, games)
    if kind in ("sum", "max"):
        return _first(s, how[1:])
    if kind in ("pct", "avg"):
        num, den, _n = paired(s, how[1], how[2])
        if num is None or not den:
            return None
        return round(100.0 * num / den, 1) if kind == "pct" else round(num / den, 1)
    if kind == "made":
        made, tried, _n = paired(s, how[1], how[2])
        return None if made is None or tried is None else f"{int(made)}-{int(tried)}"
    if kind == "rating":
        return _rating(sport, s)
    if kind == "toi":
        t = s.get(how[1])
        return None if t is None else round(t / max(1, games_with(s, how[1], games)), 2)
    if kind == "ip":
        outs = s.get(how[1])
        return None if outs is None else f"{int(outs) // 3}.{int(outs) % 3}"
    return None


def _played(sport: str, s: dict) -> bool:
    """A basketball line of no minutes is a game he did not play."""
    return not (sport in ("nba", "wnba", "cbb") and s.get("min") is not None and float(s["min"]) <= 0)


#: Leagues where one player's rows a day or less apart are one game. Football is
#: played once a week, and college's history holds copies of one game from more
#: than one writer (seen live 2026-11-16, after engine/cfbdedupe's pass of the
#: 14th): the play file's row, whose completions went to nobody when its passer
#: split missed (Arch Manning, 0 of 9 for 0 yards at Oklahoma), beside the box
#: score's (19 of 31 for 260); a copy a day off; a copy keyed by ESPN's team
#: number ("espn:194" for Ohio State). Read as one game, each box-score group
#: from whichever copy carries the fuller line.
ONE_A_WEEK = ("cfb",)


def _group_markets(sport: str) -> list:
    out = []
    for _, _, marks, cols in LAYOUTS.get(sport, ()):
        ms = set(marks)
        for c in cols:
            if c[3][0] in ("sum", "max", "pct", "avg", "made", "toi", "ip", "bavg", "obp", "ops", "era", "whip",
                           "dec"):
                ms.update(c[3][1:])
            elif c[3][0] == "rating":
                ms.update(("pass_att", "pass_cmp", "pass_yds", "pass_td", "pass_int"))
        out.append(ms)
    return out


def _day(period) -> "_dt.date | None":
    try:
        return _dt.date.fromisoformat(str(period)[:10])
    except (TypeError, ValueError):
        return None


def _espn(team) -> bool:
    return str(team or "").startswith("espn:")


def _sides(sport: str, out: list) -> None:
    """A game held twice WITH THE SIDES SWAPPED (2026-11-16, live: Ohio State's
    14 November game against NU is in Jeremiah Smith's rows as OSU against NU
    and as NU against OSU, and the copy read first led the merged game, so his
    page's header said "NU"). Which side was his is the side his nearest other
    games were on: a trade happens between games, never inside one, so this
    holds for a man traded to the club he once played against."""
    for i, g in enumerate(out):
        alt = g.pop("_alt", None)
        if not alt:
            continue
        near = ""
        for j in sorted((j for j in range(len(out)) if j != i), key=lambda j: abs(j - i)):
            if out[j].get("team") and not _espn(out[j]["team"]):
                near = out[j]["team"]
                break
        if near and g.get("team") != near and alt[0] == near:
            g["team"], g["opponent"], g["home"] = alt


def collapse(sport: str, games: list) -> list:
    """One player's game dicts (period, game_id, team, opponent, stats), copies
    of one game merged where the league plays once a week (ONE_A_WEEK); each
    merged game says how many rows it was made of (``copies``)."""
    if sport not in ONE_A_WEEK or len(games) < 2:
        return games
    groups = _group_markets(sport)
    grouped = set().union(*groups) if groups else set()
    out: list = []
    for g in sorted(games, key=lambda g: str(g["period"])):
        d = _day(g["period"])
        head = out[-1] if out else None
        if head is not None and d and head["_day"] and (d - head["_day"]).days <= 1:
            if (head.get("team") and g.get("team") and head["team"] != g["team"]
                    and head.get("team") == g.get("opponent") and head.get("opponent") == g.get("team")):
                head.setdefault("_alt", (g["team"], g.get("opponent"), g.get("home")))
            for key in ("team", "opponent"):
                other = "opponent" if key == "team" else "team"
                # ESPN's number gives way to a club's code only from a copy
                # whose other side agrees: a copy with the sides swapped would
                # hand the head the other club.
                if (_espn(head.get(key)) and g.get(key) and not _espn(g[key])
                        and (_espn(head.get(other)) or not head.get(other) or g.get(other) == head.get(other))):
                    head[key] = g[key]
            mine, theirs = head["stats"], g["stats"]
            for ms in groups:
                if sum(theirs.get(m) or 0 for m in ms) > sum(mine.get(m) or 0 for m in ms):
                    for m in ms:
                        mine.pop(m, None)
                        if theirs.get(m) is not None:
                            mine[m] = theirs[m]
            for m, v in theirs.items():
                if m not in grouped and v is not None and (mine.get(m) is None or v > mine[m]):
                    mine[m] = v
            head["copies"] += 1
            continue
        out.append(dict(g, stats=dict(g["stats"]), copies=1, _day=d))
    for g in out:
        g.pop("_day", None)
    _sides(sport, out)
    return out


#: HOW LONG A ROW WITH NO LINE WAITS FOR ITS BOX SCORE (2026-11-17). Joe
#: Burrow's Sunday row (a touchdown flag) carried no passing line until the
#: week's box scores landed (`has_line`); but a row that never gets a line,
#: a player who recorded nothing, waited for ever: Jake Tonges' Week 1 of
#: 2026 read "box score not in yet" two months on. The weekly leagues' box
#: scores are in within the week, the daily leagues' by the next night.
LINE_WAIT_DAYS = {"nfl": 4, "cfb": 4}
LINE_WAIT_DEFAULT = 2


def awaiting_line(sport: str, date, today: _dt.date | None = None) -> bool:
    """Is a row with no line still waiting for its box score? A game with no
    known date waits; one older than the league's wait has none coming."""
    try:
        day = _dt.date.fromisoformat(str(date or "")[:10])
    except ValueError:
        return True
    return ((today or _dt.date.today()) - day).days <= LINE_WAIT_DAYS.get(sport, LINE_WAIT_DEFAULT)


def has_line(sport: str, s: dict) -> bool:
    """Does a game's row carry a box-score line in the league's layout? Seen on
    the live file 2026-11-16: Joe Burrow's Sunday game had a row the night of
    the game (a touchdown flag) and no passing line until the week's box
    scores land, and it was counted as a game played, so his averages fell by
    a ninth. A row with no line is a game whose numbers are still to come."""
    return any(_first(s, marks) is not None for _, _, marks, _ in LAYOUTS.get(sport, ()))


def _results(conn, sport: str, season: int) -> tuple[dict, dict]:
    """The season's games, by game id and by (period, the two clubs)."""
    by_id, by_pair = {}, {}
    for r in conn.execute("SELECT period, game_id, home, away, home_score, away_score, date FROM games "
                          "WHERE sport=? AND season=?", (sport, season)):
        g = {"period": str(r[0]), "home": r[2], "away": r[3], "hs": r[4], "as": r[5], "date": r[6],
             "game_id": str(r[1]), "season": season}
        by_id[str(r[1])] = g
        by_pair[(str(r[0]), frozenset((r[2], r[3])))] = g
    return by_id, by_pair


def seasons_of(conn, sport: str, player: str) -> list[int]:
    return [int(r[0]) for r in conn.execute(
        "SELECT DISTINCT season FROM player_game_logs WHERE sport=? AND player=? ORDER BY season DESC",
        (sport, player)) if r[0] is not None]


def season_log(sport: str, player: str, season: int | None = None, db_path=None) -> dict:
    """``{player, sport, season, seasons, team, position, groups, games, totals,
    per_game}`` for one player's season, the newest game first; ``{}`` where
    the league has no layout, the file is missing or he has no games."""
    layout = LAYOUTS.get(sport)
    path = str(db_path or _db.DEFAULT_DB)
    if not layout or not player or not os.path.exists(path):
        return {}
    conn = _db.connect(path)
    try:
        seasons = seasons_of(conn, sport, player)
        if not seasons:
            from .statlogs import resolve_player
            found = resolve_player(conn, sport, player)
            if found and found != player:
                player = found
                seasons = seasons_of(conn, sport, player)
        if not seasons:
            return {}
        season = int(season) if season and int(season) in seasons else seasons[0]
        rows = conn.execute(
            "SELECT period, game_id, team, opponent, position, home, market, value FROM player_game_logs "
            "WHERE sport=? AND player=? AND season=?", (sport, player, season)).fetchall()
        by_id, by_pair = _results(conn, sport, season)
    finally:
        conn.close()
    games: dict = {}
    for period, gid, team, opp, pos, home, market, val in rows:
        g = games.setdefault((str(period), str(gid)), {"period": str(period), "game_id": str(gid), "team": team,
                                                       "opponent": opp, "position": pos, "home": home, "stats": {}})
        if pos and not g["position"]:
            g["position"] = pos                    # a box score's pinch hitter has none (engine/mlb/fulllines)
        if val is not None:
            g["stats"][market] = float(val)
    games = {(g["period"], g["game_id"]): g for g in collapse(sport, list(games.values()))}
    # The groups this player has a number in, and the columns the file keeps.
    groups = []
    for key, title, marks, cols in layout:
        if not shows(games.values(), marks):
            continue
        kept = [c for c in cols if any(value(sport, c[3], g["stats"]) is not None for g in games.values())]
        if kept:
            groups.append((key, title, kept))
    if not groups:
        return {}
    out_games, played, summed = [], 0, {}
    # In the order played, so a RUNNING column reads the season through each game.
    for g in sorted(games.values(), key=lambda g: (g["period"], g["game_id"])):
        s = g["stats"]
        counted = False
        res = by_id.get(g["game_id"]) or by_pair.get((g["period"], frozenset((g["team"], g["opponent"]))))
        home = (res["home"] == g["team"]) if res else bool(g["home"])
        line = {"opponent": g["opponent"], "home": home, "team": g["team"]}
        if sport in WEEKLY and not _ISO.match(g["period"]):
            try:
                line["week"] = int(g["period"])
            except ValueError:
                pass
            line["date"] = str((res or {}).get("date") or "")[:10]
        else:
            line["date"] = g["period"][:10]
        if res and res["hs"] is not None and res["as"] is not None:
            mine, theirs = (res["hs"], res["as"]) if home else (res["as"], res["hs"])
            line["result"] = "W" if mine > theirs else "L" if mine < theirs else "T"
            line["score"] = f"{int(mine)}-{int(theirs)}"
        if not _played(sport, s):
            line["dnp"] = True
        elif not has_line(sport, s):
            # Out of the games played either way: waiting for its line, or past
            # the wait with none (a game the player recorded nothing in).
            line["pending" if awaiting_line(sport, line.get("date")) else "no_line"] = True
        else:
            played += 1
            add_up(summed, s)
            counted = True
        line["values"] = {f"{k}.{c[0]}": cell(sport, c[3], s, summed, played, counted)
                          for k, _, cols in groups for c in cols}
        out_games.append(line)
    out_games.sort(key=lambda x: (x.get("date") or "", x.get("week") or 0), reverse=True)
    totals = {f"{k}.{c[0]}": value(sport, c[3], summed, played) for k, _, cols in groups for c in cols}
    per_game = {f"{k}.{c[0]}": (round(summed[_first_key(summed, c[3][1:])]
                                      / games_with(summed, _first_key(summed, c[3][1:]), played), 1)
                                if c[3][0] == "sum" and played and _first_key(summed, c[3][1:]) else None)
                for k, _, cols in groups for c in cols}
    last = max(games.values(), key=lambda g: g["period"])
    return {"sport": sport, "player": player, "season": season, "seasons": seasons,
            "team": last["team"] or "", "position": last["position"] or "",
            "groups": [{"key": k, "title": t, "cols": [{"key": c[0], "label": c[1],
                                                         "title": c[2] + (", the season's through each game"
                                                                          if c[3][0] in RUNNING else "")}
                                                        for c in cols]}
                       for k, t, cols in groups],
            "games": out_games, "played": played, "totals": totals, "per_game": per_game}


def cell(sport: str, how: tuple, s: dict, summed: dict, played: int, counted: bool):
    """A game's cell in the log: its own number, or for a RUNNING column the
    season's through it (none for a game not counted)."""
    if how[0] in RUNNING:
        return value(sport, how, summed, played) if counted else None
    return value(sport, how, s)


def _first_key(s: dict, markets) -> str | None:
    for m in markets:
        if m in s:
            return m
    return None
