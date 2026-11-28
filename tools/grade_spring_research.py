#!/usr/bin/env python3
"""Grade the spring 2026 MLB and NBA research chats' picks — run on the box.

    cd /srv/qellys && sudo -u qellys python3 tools/grade_spring_research.py

Ethan, 2026-11-15 ("Yes to mlb and nba"): grade the spring chats the way
the NFL chats were graded (engine/researchrecord), on the box's own box
scores, which the workspace that read the chats does not have. The picks are
docs/research/spring_2026_picks.json, every leg the chats' cards named.

WHAT IT READS, read-only: MLB's plate appearances (`mlb_pa`: each hitter's
hits, total bases, home runs and runs driven in, each pitcher's strikeouts,
and the first inning's runs driven in for a no-run-first-inning pick), the
NBA's finals (`games`) and its box scores (`player_game_logs`). A pick the
history has no game for is said, never guessed.

One caveat, said beside each such pick: a first inning is read as scoreless
when no batter drove in a run in it; a run that scored on an error or a wild
pitch is not in the plate appearances' RBI.

Prints each pick with its number and result, the record by kind, and one
line to paste back (SPRING_GRADES {...}). Standard library only. Writes
nothing.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "history.db"
DEFAULT_PICKS = ROOT / "docs" / "research" / "spring_2026_picks.json"

#: One club, every spelling a feed gives it.
ALIASES = [
    {"ATH", "OAK", "SAC"}, {"CWS", "CHW"}, {"WSH", "WSN", "WAS"}, {"TB", "TBR", "TBA"}, {"SD", "SDP"},
    {"SF", "SFG"}, {"KC", "KCR"}, {"AZ", "ARI"}, {"LAA", "ANA"}, {"NYK", "NY"}, {"GSW", "GS"},
    {"NOP", "NO", "NOR"}, {"SAS", "SA"}, {"UTA", "UTAH"}, {"PHX", "PHO"}, {"BKN", "BRK"}, {"CHA", "CHO"},
]
HITS = {"single", "double", "triple", "home_run"}
BASES = {"single": 1, "double": 2, "triple": 3, "home_run": 4}
MARKET_WORDS = {"strikeouts": "strikeouts", "hits": "hits", "total_bases": "total bases",
                "home_runs": "home runs", "rbi": "runs driven in", "pts": "points", "ast": "assists",
                "reb": "rebounds", "fg3m": "threes", "spread": "spread", "total": "total",
                "nrfi": "no run in the first inning"}


def club(code) -> str:
    c = str(code or "").strip().upper()
    for group in ALIASES:
        if c in group:
            return sorted(group)[0]
    return c


def name_key(name) -> str:
    """A name as two feeds both spell it: no accents, no dots, no suffix."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    s = "".join(ch if ch.isalnum() or ch == " " else " " for ch in s)
    words = [w for w in s.split() if w not in ("jr", "sr", "ii", "iii", "iv")]
    return " ".join(words)


def teams_of(game) -> set:
    parts = str(game or "").split("@")
    return {club(p) for p in parts if p}


def settle(value, line, side) -> str:
    if value is None:
        return "missing"
    v, ln = float(value), float(line)
    if v == ln:
        return "push"
    over = v > ln
    return "won" if (over if side == "over" else not over) else "lost"


def mlb_day(conn, date: str) -> list:
    return conn.execute(
        "SELECT game_pk, batter, pitcher, team, opponent, inning, event_type, rbi FROM mlb_pa "
        "WHERE date LIKE ? ORDER BY game_pk, at_bat", (f"{date}%",)).fetchall()


def mlb_value(rows: list, pick: dict):
    """(value, note) for an MLB player pick on its day's plate appearances."""
    who, market = name_key(pick["who"]), pick["market"]
    want = teams_of(pick.get("game"))
    games: dict = defaultdict(lambda: {"v": 0, "teams": set()})
    for game_pk, batter, pitcher, team, opp, _inn, etype, rbi in rows:
        mine = name_key(pitcher) == who if market == "strikeouts" else name_key(batter) == who
        if not mine:
            continue
        g = games[game_pk]
        g["teams"] |= {club(team), club(opp)}
        et = str(etype or "")
        if market == "strikeouts":
            g["v"] += 1 if et.startswith("strikeout") else 0
        elif market == "hits":
            g["v"] += 1 if et in HITS else 0
        elif market == "total_bases":
            g["v"] += BASES.get(et, 0)
        elif market == "home_runs":
            g["v"] += 1 if et == "home_run" else 0
        elif market == "rbi":
            g["v"] += int(rbi or 0)
    if not games:
        return None, "no plate appearance of his that day in the history"
    pick_g = next((g for g in games.values() if want and want <= g["teams"]), None) or next(iter(games.values()))
    note = "first game of a doubleheader" if len(games) > 1 and not (want and want <= pick_g["teams"]) else ""
    return pick_g["v"], note


def nrfi(rows: list, pick: dict):
    want = teams_of(pick.get("game"))
    found, runs = False, 0
    for _pk, _b, _p, team, opp, inning, _et, rbi in rows:
        if {club(team), club(opp)} != want:
            continue
        found = True
        if inning == 1:
            runs += int(rbi or 0)
    if not found:
        return None, "the game is not in the history"
    return runs, "read from runs driven in (an error or a wild pitch is not counted)"


def nba_game(conn, date: str, pick: dict):
    want = teams_of(pick.get("game"))
    for home, away, hs, as_ in conn.execute(
            "SELECT home, away, home_score, away_score FROM games WHERE sport='nba' AND (period=? OR date=?)",
            (date, date)).fetchall():
        if {club(home), club(away)} == want and hs is not None and as_ is not None:
            return club(home), club(away), float(hs), float(as_)
    return None


def nba_prop(conn, date: str, pick: dict):
    who = name_key(pick["who"])
    for player, value in conn.execute(
            "SELECT player, value FROM player_game_logs WHERE sport='nba' AND period=? AND market=?",
            (date, pick["market"])).fetchall():
        if name_key(player) == who:
            return float(value), ""
    return None, "no box score of his that day in the history"


def grade(conn, picks: list) -> list:
    out, days = [], {}
    for p in picks:
        date, market, side = p["date"], p["market"], p.get("side") or ""
        value, note, result = None, "", "missing"
        if p["sport"] == "mlb":
            if date not in days:
                days[date] = mlb_day(conn, date)
            if market == "nrfi":
                value, note = nrfi(days[date], p)
                result = "missing" if value is None else ("won" if value == 0 else "lost")
            else:
                value, note = mlb_value(days[date], p)
                result = settle(value, p["line"], side)
        elif market in ("spread", "total"):
            g = nba_game(conn, date, p)
            if g is None:
                note = "the final is not in the history"
            else:
                home, away, hs, as_ = g
                if market == "total":
                    value = hs + as_
                    result = settle(value, p["line"], side)
                else:
                    me = club(p["who"])
                    margin = (hs - as_) if me == home else (as_ - hs)
                    value = margin
                    cover = margin + float(p["line"])
                    result = "push" if cover == 0 else ("won" if cover > 0 else "lost")
                note = f"final {away} {as_:g}, {home} {hs:g}"
        else:
            value, note = nba_prop(conn, date, p)
            result = settle(value, p["line"], side)
        out.append({**p, "value": value, "result": result, "note": note})
    return out


def kind_of(p: dict) -> str:
    if p["market"] in ("spread", "nrfi"):
        return f"{p['sport']} {p['market']}"
    return f"{p['sport']} {p['market']} {p.get('side') or ''}".strip()


def said(p: dict) -> str:
    m = MARKET_WORDS.get(p["market"], p["market"])
    if p["market"] == "spread":
        return f"{p['who']} {float(p['line']):+g} ({p['game']})"
    if p["market"] == "nrfi":
        return f"{p['game']}: {m}"
    if p["market"] == "total":
        return f"{p['game']} {p['side']} {p['line']:g} points"
    return f"{p['who']} {p['side']} {p['line']:g} {m}"


def report(rows: list) -> dict:
    by_kind: dict = defaultdict(lambda: [0, 0, 0, 0])      # won, lost, push, missing
    by_role: dict = defaultdict(lambda: [0, 0, 0, 0])
    idx = {"won": 0, "lost": 1, "push": 2, "missing": 3}
    for r in rows:
        num = "—" if r["value"] is None else f"{r['value']:g}"
        print(f"{r['date']} {r['sport'].upper():4} {said(r):<52} {num:>6}  {r['result'].upper():8}"
              f"{'  (' + r['role'] + ')' if r['role'] != 'pick' else ''}{'  ' + r['note'] if r['note'] else ''}")
        by_kind[kind_of(r)][idx[r["result"]]] += 1
        by_role[f"{r['sport']} {r['role']}"][idx[r["result"]]] += 1
    print("\nBy kind (won-lost, pushes, not in the history):")
    for k in sorted(by_kind):
        w, l, pu, m = by_kind[k]
        print(f"  {k:<28} {w}-{l}" + (f", {pu} push" if pu else "") + (f", {m} not found" if m else ""))
    print("By sport and role:")
    for k in sorted(by_role):
        w, l, pu, m = by_role[k]
        print(f"  {k:<28} {w}-{l}" + (f", {pu} push" if pu else "") + (f", {m} not found" if m else ""))
    summary = {"by_kind": {k: v for k, v in sorted(by_kind.items())},
               "picks": [{"date": r["date"], "who": r["who"], "market": r["market"], "result": r["result"],
                          "value": r["value"]} for r in rows]}
    print("\nSPRING_GRADES " + json.dumps(summary, separators=(",", ":")))
    return summary


def main(argv=None) -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--db", default=str(DEFAULT_DB))
    a.add_argument("--picks", default=str(DEFAULT_PICKS))
    args = a.parse_args(argv)
    picks = json.loads(Path(args.picks).read_text(encoding="utf-8"))["picks"]
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        report(grade(conn, picks))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
