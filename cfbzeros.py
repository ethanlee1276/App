#!/usr/bin/env python3
"""College receivers thrown at who caught nothing — on the record, and what the voids were. On the box.

    cd /srv/qellys && sudo -u qellys python3 cfbzeros.py           # check: read-only
    cd /srv/qellys && sudo -u qellys python3 cfbzeros.py --fill    # re-read last season and this one

Ethan, 2026-10-13: "We worked so hard on nfl so ik CFB and mlb and nba and
ufc is missing stuff." The college play file names the receiver a pass
was thrown at on most incompletions since 2025, and the parser now writes
a receiver thrown at who caught none as a ZERO (engine/sources/cfbstats,
ZERO_WHEN; measured by cfbtargetfit.py). The nightly re-reads this
season's file by itself; last season's was read once, before the change,
so `--fill` re-reads both seasons' player files — player rows only, no
schedule and no lines.

The check prints:

* per season, how many college receiving zeros are stored (catches = 0) —
  0 for a season the new parser has not read yet;
* THE VOIDS. Since 2026-09-14 a college player with no line in a final
  box score has his prop voided: the box lists only players with a stat,
  so a scratch and a receiver who caught nothing looked the same (Ethan's
  rule: void the scratch, grade the player who played). Now the play
  file can tell some of them apart. For every voided college receiving
  bet it looks for that receiver's zero from the play file, and prints
  how many were thrown at — an over a book graded as a loss, an under it
  graded as a win — with the units either way. Nothing is regraded: the
  record stays as it was graded. The count is the evidence for your call
  in H.
"""

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

RECEIVING = ("receptions", "rec_yds", "rec_td")


def zeros_by_season(conn) -> list:
    return conn.execute(
        "SELECT season, COUNT(*) FROM player_game_logs WHERE sport='cfb' AND market='receptions' "
        "AND value=0 AND game_id NOT LIKE '%-box' GROUP BY season ORDER BY season DESC").fetchall()


def _payout(odds, stake) -> float:
    o = int(odds or 0)
    if not o or not stake:
        return 0.0
    return float(stake) * (o / 100.0 if o > 0 else 100.0 / -o)


def voids(lconn, hconn) -> dict:
    """``{"voided", "thrown_at", "over_lost", "under_won", "units_if_graded", "rows"}`` —
    every voided college receiving bet, and those whose receiver the play
    file has as thrown at and catching none that day."""
    from engine.sources.oddsapi import normalize_name
    out = {"voided": 0, "thrown_at": 0, "over_lost": 0, "under_won": 0,
           "units_if_graded": 0.0, "rows": []}
    marks = ",".join("?" * len(RECEIVING))
    for b in lconn.execute(
            f"SELECT id, date, player, market, side, line, odds, stake_units FROM bets "
            f"WHERE sport='cfb' AND status='void' AND market IN ({marks})", RECEIVING):
        out["voided"] += 1
        try:
            d0 = _dt.date.fromisoformat(str(b[1] or "")[:10])
        except ValueError:
            continue
        lo, hi = (d0 - _dt.timedelta(days=1)).isoformat(), (d0 + _dt.timedelta(days=1)).isoformat()
        want = normalize_name(b[2] or "")
        hit = [r for r in hconn.execute(
            "SELECT player, value FROM player_game_logs WHERE sport='cfb' AND market=? "
            "AND period BETWEEN ? AND ? AND game_id NOT LIKE '%-box'", (b[3], lo, hi))
               if normalize_name(r[0]) == want]
        if len(hit) != 1 or float(hit[0][1]) != 0.0:
            continue
        out["thrown_at"] += 1
        over = (b[4] or "OVER").upper() != "UNDER"
        if over:
            out["over_lost"] += 1
            out["units_if_graded"] -= float(b[7] or 0.0)
        else:
            out["under_won"] += 1
            out["units_if_graded"] += _payout(b[6], b[7])
        out["rows"].append((b[0], b[1], b[2], b[3], (b[4] or "OVER").upper(), b[5]))
    return out


def check(lconn, hconn) -> list:
    lines = []
    z = zeros_by_season(hconn)
    if not z:
        lines.append("CFB  no receiving zeros stored yet — the nightly writes this season's; "
                     "--fill writes last season's too")
    for season, n in z:
        lines.append(f"CFB  {season}: {n:,} receiver-games thrown at with no catch, on the record as 0")
    v = voids(lconn, hconn)
    lines.append(f"VOIDS  {v['voided']:,} college receiving bets voided as 'did not play'; "
                 f"{v['thrown_at']:,} of them the play file has as thrown at, no catch")
    if v["thrown_at"]:
        lines.append(f"       a book graded those {v['over_lost']} over(s) as losses and "
                     f"{v['under_won']} under(s) as wins: {v['units_if_graded']:+.2f}u "
                     f"had they been graded (nothing is regraded)")
        for bid, day, player, market, side, line in v["rows"][:12]:
            lines.append(f"       #{bid} {day} {player} {market} {side} {line}")
    return lines


def fill(hconn, today=None) -> list:
    from engine import ingest
    today = today or _dt.date.today()
    season = today.year if today.month >= 8 else today.year - 1
    res = ingest.ingest_cfb_player_history(hconn, [season - 1, season], quiet=True, fresh=season)
    out = [f"CFB {s['season']}: {s['rows']:,} player rows re-read" for s in res.get("seasons", [])]
    out += [f"  skipped: {note}" for note in res.get("skipped", [])[:5]]
    return out


def _ro(path):
    """Read-only, never created: the check writes nothing."""
    import sqlite3
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def main(argv=None) -> int:
    from engine import db, ledger
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--fill" in argv:
        conn = db.connect()
        try:
            for line in fill(conn):
                print(line)
        finally:
            conn.close()
    hconn, lconn = _ro(db.DEFAULT_DB), _ro(ledger.DEFAULT_DB)
    try:
        for line in check(lconn, hconn):
            print(line)
    finally:
        hconn.close()
        lconn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
