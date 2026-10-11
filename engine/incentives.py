"""NFL contract-incentive tracker — December money, measured from our logs.

Late in the season a player with a stats bonus in his contract stops
being an ordinary projection: "needs 62 receiving yards for $500,000" is
information his own sideline acts on, and Week 17-18 usage bends toward
it. Books are slow to price that; a board that KNOWS the number is not.

No free feed publishes contract incentives — they surface in December
beat reporting and on the cap sites (read by a person, never scraped).
So the table is hand-curated: checked into the repo at
``data/nfl_incentives.json``, and — since the box never commits — added
from the box into its own copy beside the models (Ethan, 2026-10-11: "we
need an incentive tracker for players. like if a player needs so many
catches to get paid")::

    sudo -u qellys python3 -m engine.incentives add --player "Puka Nacua" --stat receptions \
        --target 100 --bonus 500000 --source https://www.example.com/the-report
    sudo -u qellys python3 -m engine.incentives list
    sudo -u qellys python3 -m engine.incentives remove --player "Puka Nacua" --stat receptions

Every entry carries the link to the report it came from, and the card
shows it — an incentive with no source is not taken. Both files read the
same::

    {
      "season": 2026,
      "entries": [
        {"player": "Example Receiver", "team": "KC", "stat": "rec_yds",
         "threshold": 1000, "bonus_usd": 500000,
         "source": "per beat reporting, 2026-12-14"}
      ]
    }

``stat`` must be a market our ingest actually carries — a threshold we
cannot measure would render as a guess, and this module drops it with
its reason attached rather than pretending. Everything computed here
(season total, distance, pace, games left) comes from our own ingested
game logs and finals, the same rows the model already trusts.

Authority: the tracker DISPLAYS and ANNOTATES. It appends a reason to a
matching prop card so the human sees the angle; it never moves a
probability — an unmeasured usage bump is a hypothesis, and hypotheses
go through the lab, not the pricing path.
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

DATA_PATH = Path("data/nfl_incentives.json")
#: The box's own entries (``add`` below), beside the models.
BOX_STORE = "nfl_incentives.json"

#: Stats the tracker can measure — exactly the NFL markets our ingest
#: writes per game. Anything else in the table is flagged, not guessed.
TRACKABLE = {
    "pass_yds": "passing yards",
    "rush_yds": "rushing yards",
    "rec_yds": "receiving yards",
    "receptions": "receptions",
    "pass_td": "touchdown passes",
    "anytime_td": "rushing and receiving touchdowns",
}
REGULAR_SEASON_GAMES = 17


def _box_path() -> Path:
    from . import modelstate
    return Path(modelstate.path(BOX_STORE))


def _read(p: Path) -> dict:
    try:
        raw = json.loads(p.read_text()) if p.is_file() else {}
        return raw if isinstance(raw, dict) else {}
    except (ValueError, OSError):
        return {}


def load(path: Path | str | None = None) -> dict:
    """The table: one file when ``path`` is given; by default the checked-in
    table and the box's own entries together."""
    files = [Path(path)] if path is not None else [DATA_PATH, _box_path()]
    season, entries = None, []
    for p in files:
        raw = _read(p)
        season = season or raw.get("season")
        entries += [e for e in (raw.get("entries") or []) if isinstance(e, dict)]
    return {"season": season, "entries": entries}


def _team_games_played(hconn, team: str, season: int) -> int:
    """Finals the team has actually played, from our own games table."""
    r = hconn.execute(
        "SELECT COUNT(*) FROM games WHERE sport='nfl' AND season=? "
        "AND home_score IS NOT NULL AND (home=? OR away=?)",
        (season, team, team)).fetchone()
    return int(r[0] or 0)


def report(hconn, season: int | None = None,
           path: Path | str | None = None) -> dict:
    """The tracker: each entry measured against the ingested season.

    Status vocabulary, computed not vibed:
      * ``hit``          — threshold already reached
      * ``missed``       — season over, threshold not reached
      * ``on pace``      — per-game need ≤ his own season per-game pace
      * ``needs a push`` — per-game need within 1.75× his pace
      * ``long shot``    — needs more than 1.75× his pace, every week
      * ``collecting``   — no games on file yet to judge from
    """
    from .sources.oddsapi import normalize_name
    from .seasons import season_of
    tbl = load(path)
    season = int(season or tbl.get("season")
                 or season_of("nfl", _dt.date.today().isoformat()))
    rows, dropped = [], []
    for e in tbl["entries"]:
        if e.get("season") and int(e["season"]) != season:
            continue                       # last season's money, kept on file
        stat = str(e.get("stat") or "")
        if stat not in TRACKABLE:
            dropped.append({"player": e.get("player"), "stat": stat,
                            "why": "not a market our ingest carries"})
            continue
        want = normalize_name(str(e.get("player") or ""))
        logs = [r for r in hconn.execute(
            "SELECT player, value, period, team FROM player_game_logs "
            "WHERE sport='nfl' AND season=? AND market=?", (season, stat))
            if normalize_name(r["player"]) == want]
        total = round(sum(float(r["value"] or 0) for r in logs), 1)
        played = len({r["period"] for r in logs})
        team = str(e.get("team") or (logs[-1]["team"] if logs else ""))
        team_played = _team_games_played(hconn, team, season) if team else 0
        remaining = max(0, REGULAR_SEASON_GAMES - max(team_played, played))
        threshold = float(e.get("threshold") or 0)
        need = max(0.0, round(threshold - total, 1))
        pace = round(total / played, 2) if played else None
        per_game_need = round(need / remaining, 2) if remaining else None
        if need <= 0:
            status = "hit"
        elif remaining == 0:
            status = "missed"
        elif pace is None:
            status = "collecting"
        elif per_game_need <= pace:
            status = "on pace"
        elif per_game_need <= pace * 1.75:
            status = "needs a push"
        else:
            status = "long shot"
        rows.append({
            "player": e.get("player"), "team": team, "stat": stat,
            "stat_label": TRACKABLE[stat], "threshold": threshold,
            "total": total, "need": need, "games_played": played,
            "games_left": remaining, "pace": pace,
            "per_game_need": per_game_need,
            "bonus_usd": float(e.get("bonus_usd") or 0),
            "status": status, "source": e.get("source") or "",
        })
    # Money on the line first, then closest to the wire.
    rows.sort(key=lambda r: (-r["bonus_usd"], r["need"]))
    return {"season": season, "entries": rows, "dropped": dropped,
            "note": "" if rows else (
                "No incentives on file yet — they land with December "
                "reporting. Add one from the box (python3 -m "
                "engine.incentives add, with the report's link) or to "
                "data/nfl_incentives.json, and the tracker measures it "
                "against our own ingested logs on the next build.")}


def decorate(recommendations: list[dict], entries: list[dict]) -> int:
    """Append the incentive angle to matching prop cards.

    A reason, never a number: the card says what the sideline knows, and
    the human weighs it. Only LIVE chases decorate — a hit or missed
    incentive no longer bends anyone's usage."""
    from .sources.oddsapi import normalize_name
    live = {(normalize_name(str(e.get("player") or "")), e.get("stat")): e
            for e in entries
            if e.get("status") in ("on pace", "needs a push", "long shot")}
    if not live:
        return 0
    n = 0
    for r in recommendations:
        key = (normalize_name(str(r.get("player") or "")), r.get("market"))
        e = live.get(key)
        if not e:
            continue
        r.setdefault("reasons", []).append(
            f"Incentive watch: needs {e['need']:g} more {e['stat_label']} "
            f"in {e['games_left']} game(s) for a "
            f"${e['bonus_usd']:,.0f} bonus — his sideline knows it too")
        r["incentive"] = {k: e[k] for k in
                          ("need", "games_left", "bonus_usd", "status")}
        n += 1
    return n


def card_notes(rows: list[dict], entries: list[dict]) -> int:
    """The same live chases on the Most Likely board's cards: a line and
    the report's link (``incentive_note``, ``incentive_source``) on the
    matching player and market. A reason, never a number."""
    from .sources.oddsapi import normalize_name
    live = {(normalize_name(str(e.get("player") or "")), e.get("stat")): e
            for e in entries
            if e.get("status") in ("on pace", "needs a push", "long shot")}
    n = 0
    for r in rows:
        e = live.get((normalize_name(str(r.get("player") or "")), r.get("market")))
        if not e:
            r.pop("incentive_note", None)
            r.pop("incentive_source", None)
            continue
        money = f"${e['bonus_usd']:,.0f}" if e.get("bonus_usd") else "a bonus"
        r["incentive_note"] = (f"{e['total']:,g} of {e['threshold']:,g} {e['stat_label']} — needs "
                               f"{e['need']:,g} more in {e['games_left']} game"
                               f"{'' if e['games_left'] == 1 else 's'} for {money} ({e['status']})")
        r["incentive_source"] = e.get("source") or ""
        n += 1
    return n


def milestones(hconn, season: int | None = None, limit: int = 40) -> list[dict]:
    """Every player chasing a round number down the stretch (engine/spots'
    milestones: 1,000 yards, 100 catches, 4,000 passing yards, 30
    touchdown passes, 10 touchdowns), measured from our own logs — the
    automatic half of the tracker, beside the money above."""
    from . import spots as SP
    from .seasons import season_of
    season = int(season or season_of("nfl", _dt.date.today().isoformat()))
    marks = list(SP.MILESTONES)
    vals: dict = {}
    for r in hconn.execute(
            "SELECT player, team, market, value FROM player_game_logs WHERE sport='nfl' AND season=? "
            f"AND market IN ({','.join('?' * len(marks))})", (season, *marks)):
        if r["value"] is not None:
            d = vals.setdefault((r["player"], r["market"]), {"team": r["team"], "values": []})
            d["values"].append(float(r["value"]))
            d["team"] = r["team"] or d["team"]
    played: dict = {}
    out = []
    for (player, market), d in vals.items():
        team = str(d["team"] or "")
        if team not in played:
            played[team] = _team_games_played(hconn, team, season) if team else 0
        left = max(0, REGULAR_SEASON_GAMES - max(played[team], len(d["values"])))
        chase = SP.milestone(market, d["values"], left)
        if chase:
            out.append({"player": player, "team": team, "stat": market,
                        "stat_label": SP.LABELS.get(market, market), **chase})
    out.sort(key=lambda r: (r["games_left"], r["need"] / max(r["pace"] * r["games_left"], 1e-9)))
    return out[:limit]


# --- the box's own entries ------------------------------------------------------------
def _money(text) -> float:
    """"500000", "$500,000", "500K" and "1.5M" are all money."""
    t = str(text or "").strip().lower().replace("$", "").replace(",", "")
    mult = 1.0
    if t.endswith("k"):
        t, mult = t[:-1], 1e3
    elif t.endswith("m"):
        t, mult = t[:-1], 1e6
    try:
        return float(t) * mult
    except ValueError:
        raise ValueError(f"{text!r} is not an amount of money") from None


def add(player: str, stat: str, target, bonus, source: str, team: str = "",
        season: int | None = None, path: Path | str | None = None) -> dict:
    """Save one incentive in the box's table (replacing the same player's
    same stat). Refuses a stat we cannot measure and an entry with no link
    to the report it came from."""
    from .seasons import season_of
    if stat not in TRACKABLE:
        raise ValueError(f"{stat!r} is not a stat our logs carry — one of: {', '.join(TRACKABLE)}")
    if not str(source or "").startswith(("http://", "https://")):
        raise ValueError("every incentive needs the link to the report it came from (--source https://…)")
    if not str(player or "").strip():
        raise ValueError("--player is required")
    p = Path(path) if path is not None else _box_path()
    raw = _read(p)
    season = int(season or season_of("nfl", _dt.date.today().isoformat()))
    entry = {"player": player.strip(), "team": team.strip().upper(), "stat": stat,
             "threshold": float(target), "bonus_usd": _money(bonus), "source": source.strip(),
             "season": season, "added": _dt.date.today().isoformat()}
    from .sources.oddsapi import normalize_name
    keep = [e for e in raw.get("entries") or [] if isinstance(e, dict)
            and not (normalize_name(str(e.get("player") or "")) == normalize_name(entry["player"])
                     and e.get("stat") == stat)]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps({"season": season, "entries": keep + [entry]}, indent=1))
    tmp.replace(p)
    return entry


def remove(player: str, stat: str = "", path: Path | str | None = None) -> int:
    """Take a player's entries (one stat, or all of them) out of the box's
    table; returns how many went."""
    from .sources.oddsapi import normalize_name
    p = Path(path) if path is not None else _box_path()
    raw = _read(p)
    want = normalize_name(player)
    entries = [e for e in raw.get("entries") or [] if isinstance(e, dict)]
    keep = [e for e in entries if not (normalize_name(str(e.get("player") or "")) == want
                                       and (not stat or e.get("stat") == stat))]
    if len(keep) != len(entries):
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(dict(raw, entries=keep), indent=1))
        tmp.replace(p)
    return len(entries) - len(keep)


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m engine.incentives")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a_add = sub.add_parser("add", help="add a contract incentive from a published report")
    a_add.add_argument("--player", required=True)
    a_add.add_argument("--stat", required=True, help=", ".join(TRACKABLE))
    a_add.add_argument("--target", required=True, type=float, help="the number he has to reach")
    a_add.add_argument("--bonus", required=True, help="the money: 500000, 500K or 1.5M")
    a_add.add_argument("--source", required=True, help="the link to the report it came from")
    a_add.add_argument("--team", default="", help="his team (default: from our logs)")
    a_add.add_argument("--season", type=int, default=None)
    a_rm = sub.add_parser("remove", help="take an incentive out")
    a_rm.add_argument("--player", required=True)
    a_rm.add_argument("--stat", default="", help="one stat (default: all of his)")
    sub.add_parser("list", help="every incentive on file, measured against our logs")
    sub.add_parser("milestones", help="every player chasing a round number, from our logs")
    a = ap.parse_args(argv)
    if a.cmd == "add":
        try:
            e = add(a.player, a.stat, a.target, a.bonus, a.source, a.team, a.season)
        except ValueError as exc:
            print(f"not added: {exc}")
            return 2
        print(f"added: {e['player']} — {e['threshold']:,g} {TRACKABLE[e['stat']]} for ${e['bonus_usd']:,.0f} "
              f"({e['season']}); the board shows it on its next build")
        return 0
    if a.cmd == "remove":
        n = remove(a.player, a.stat)
        print(f"removed {n} entr{'y' if n == 1 else 'ies'}")
        return 0
    from .db import connect
    h = connect()
    try:
        if a.cmd == "milestones":
            rows = milestones(h)
            print(f"{len(rows)} milestone chases" + (":" if rows else " (they start with six games left)"))
            for r in rows:
                print(f"  {r['player']:24} {r['team']:4} {r['note']}" + ("  [flag]" if r["flag"] else ""))
            return 0
        rep = report(h)
    finally:
        h.close()
    print(f"{len(rep['entries'])} incentives for {rep['season']}" + (":" if rep["entries"] else ""))
    for r in rep["entries"]:
        print(f"  {r['player']:24} {r['total']:,g} of {r['threshold']:,g} {r['stat_label']} — "
              f"needs {r['need']:,g} in {r['games_left']} — ${r['bonus_usd']:,.0f} — {r['status']}\n"
              f"    {r['source'] or 'no source'}")
    for d in rep["dropped"]:
        print(f"  dropped: {d['player']} {d['stat']} — {d['why']}")
    if not rep["entries"]:
        print("  " + rep["note"])
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
