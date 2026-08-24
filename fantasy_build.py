#!/usr/bin/env python3
"""Build the Fantasy Football page's data from the ingested NFL history.

    python3 fantasy_build.py --out web/data/fantasy.json

Stats come from the local DB (usage rows land during the normal NFL
ingest). Two cache-first, once-a-day fetches keep the page current with
the league rather than with last season: the nflverse schedule (coaching
changes, and next season's lines for game scripts) and Sleeper's public
players feed (current teams, rookies, depth charts). Both fall back to
stale caches, then to nothing — the page labels what it couldn't refresh
instead of guessing.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
from pathlib import Path


def _write_json(path: Path, doc: dict, indent: int = 2) -> None:
    """Atomic replace — the Fantasy tab polls these files while the
    refresher rebuilds them; a poll must see old or new, never half."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, indent=indent))
    os.replace(tmp, path)

from engine import fantasy, fantasy_draft, fantasy_ranks, offseason, preseason
from engine.db import connect
from engine.sources.fetch import DataUnavailable


def _write_rosters(path: Path, blob: dict | None) -> None:
    """Active NFL rosters + recent team changes, from the players blob.

    Separate from the fantasy payload on purpose: the NFL page shouldn't
    have to download draft tiers and buy-low tables to list a roster. It
    is named per-sport because every league now owns its own roster tab —
    a roster belongs to a league, and "who is on this team" is a question
    you ask while looking at that league's board.

    An unreachable feed writes a payload that SAYS the feed was
    unreachable, rather than an empty one — "no rosters" and "every team
    has nobody" look identical on a page and mean opposite things.
    """
    from engine import rosters as _r
    if not blob:
        _write_json(path, {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "teams": {}, "team_count": 0, "player_count": 0,
            "feed": "unavailable",
            "note": "The roster feed was unreachable on this build, so this "
                    "is not an empty league — it is no data. Try "
                    "`python3 launch.py --refresh-rosters`.",
        })
        print("Rosters: feed unavailable — wrote an empty payload that says so.")
        return
    today = datetime.date.today().isoformat()
    # The same photo map the usage and buy/sell boards already use, so the
    # roster page shows the face the rest of the site shows. Faces are
    # polish: an unreachable roster file is an empty map and initials, not
    # a failed build.
    try:
        from engine.sources import nflverse as _nv
        from engine.seasons import season_of as _season_of
        _faces = _nv.headshot_map(_season_of("nfl", today))
    except Exception:                                          # noqa: BLE001
        _faces = {}
    out = _r.build_rosters(blob, faces=_faces)
    # THE SECOND OPINION. Sleeper knows who is on every roster; ESPN's
    # injury report knows what is wrong with the ones who are hurt, and
    # often files first. Until now the two lived on different pages and
    # disagreed in public — a player on the ESPN board with no Sleeper
    # designation showed as Active here. `injurymerge` takes availability
    # from whichever feed is more pessimistic and detail from whichever
    # has it, and never clears anyone. Cached feed; a failure leaves the
    # roster exactly as Sleeper reported it.
    try:
        from engine import injurymerge as _im
        from engine.sources import espninjuries as _ei
        _rows = _ei.current_rows(_ei.parse_injuries(_ei.fetch_injuries("nfl")))
        out = _im.apply(out, _rows)
        _m = out.get("injury_merge") or {}
        print(f"Injury merge: {_m.get('matched', 0)} of {_m.get('espn_filings', 0)}"
              f" ESPN filings matched a rostered player"
              + (f" · {_m['newly_unavailable']} newly unavailable"
                 if _m.get("newly_unavailable") else "")
              + (f" · {_m['conflicts']} disagreement(s)"
                 if _m.get("conflicts") else "")
              + (f" · {_m['unmatched_count']} unmatched"
                 if _m.get("unmatched_count") else ""))
    except Exception as _exc:                                  # noqa: BLE001
        print(f"  ⚠️  ESPN injury merge unavailable: {_exc}")
    # Transactions come from diffing OUR OWN daily snapshots. No news feed,
    # nothing to curate, and it covers every rostered player rather than
    # the ones somebody thought to mention.
    store = _r.record_teams(blob, today)
    out["transactions"] = _r.transactions(store)
    out["generated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
    out["feed"] = "live"
    _write_json(path, out)
    tx = out["transactions"]["moves"]
    print(f"Rosters: {out['team_count']} teams, {out['player_count']:,} players"
          + (f" · {len(tx)} team change(s) in the tracked window: "
             + ", ".join(f"{m['player']} ({m['from']}→{m['to']})" for m in tx[:4])
             + ("…" if len(tx) > 4 else "") if tx else
             f" · no team changes across {out['transactions']['days']} tracked day(s)"))


def _upcoming_schedule(season: int) -> list[dict]:
    """The cached nflverse schedule → engine.fantasy.upcoming_schedule.
    An unreachable schedule file is an empty list, never a dead build."""
    try:
        from engine.sources import nflverse
        return fantasy.upcoming_schedule(nflverse.load_schedules(), season)
    except Exception:                                        # noqa: BLE001
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="web/data/fantasy.json")
    args = ap.parse_args()

    conn = connect()
    blob = None
    season = fantasy.latest_season(conn)
    if season is None:
        out = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
               "season": None, "usage": [], "buy_sell": {}, "scripts": [],
               "note": "No NFL usage data ingested yet — run "
                       "`python3 ingest.py nfl` once."}
    else:
        # THE BLOB MOVED UP. It used to load after the kit, because its
        # only job was stamping current teams onto rows that already
        # existed. The kit now needs it while it is still building: the
        # players the market drafts and our usage rows cannot see are
        # placed BEFORE tiers and replacement level, so that every other
        # player's VORP is measured against a pool that includes them.
        # Still optional — None means Sleeper was unreachable and the
        # board is exactly what it was before.
        blob = offseason.load_sleeper_players()
        kit = fantasy_draft.build_draft_kit(conn, season, sleeper=blob)
        try:
            from engine.sources.nflverse import load_schedules
            sched = load_schedules()
        except DataUnavailable:
            sched = []
        off = offseason.build_offseason(sched, blob, kit=kit)
        # Waiver-wire pulse: what every Sleeper league grabbed/dumped in
        # the last 24h. None (unreachable) simply omits the section.
        adds = offseason.load_trending("add", blob)
        drops = offseason.load_trending("drop", blob)
        trending = ({"adds": adds or [], "drops": drops or [],
                     "lookback_hours": 24}
                    if adds is not None or drops is not None else None)
        usage = fantasy.usage_board(conn, season)
        buy_sell = fantasy.buy_sell_board(conn, season)
        # Faces ride along from the roster file already on disk — the DB
        # rows these boards are built from carry stats, not photographs.
        # The UI falls back to the helmet avatar wherever the map is empty,
        # so an unavailable roster file costs nothing.
        try:
            from engine.sources import nflverse
            faces = nflverse.headshot_map(season)
        except Exception:
            faces = {}
        # EVERY row a fantasy surface draws a person from, one loop —
        # Ethan, 2026-08-18: "there is a lot of places I'm noticing we
        # are not showing the headshot." The draft kit's board, tiers
        # and sleepers were the big miss: the kit page and the mock
        # draft both pass r.headshot to the avatar, but the field never
        # existed on kit rows, so every one fell back to the drawn chip
        # even on a machine with the photos stored.
        _face_rows = [usage, buy_sell.get("buy_low") or [],
                      buy_sell.get("sell_high") or [],
                      (trending or {}).get("adds") or [],
                      (trending or {}).get("drops") or [],
                      kit.get("board") or [],
                      kit.get("sleepers") or []]
        _face_rows += list((kit.get("tiers") or {}).values())
        for rows in _face_rows:
            for r in rows:
                r["headshot"] = faces.get(r.get("player") or "", "")
        # Trades must show on EVERY board, not just the draft kit — usage
        # and buy/sell rows come out of the DB wearing last season's teams.
        # The kit was stamped inside build_offseason; these join its moves
        # list so the page's "player moves" section is complete.
        if blob is not None:
            idx = offseason.index_players(blob)
            moves = off.setdefault("moves", [])
            seen = {m["player"] for m in moves}
            for rows in (usage, buy_sell.get("buy_low") or [],
                         buy_sell.get("sell_high") or []):
                offseason.stamp_current_teams(rows, idx, moves=moves, seen=seen)
            moves.sort(key=lambda m: m["player"])
        # The launch-time roster check, visible in the terminal every cycle.
        synced = off.get("rosters_synced_at")
        mv = off.get("moves") or []
        print(f"Roster sync: Sleeper cache "
              + (f"written {synced}" if synced else "UNAVAILABLE — team "
                 "stamps may be stale")
              + f" · {len(mv)} board player(s) on new teams"
              + (": " + ", ".join(f"{m['player']} ({m['from']}→{m['to']})"
                                  for m in mv[:6])
                 + ("…" if len(mv) > 6 else "") if mv else ""))
        # Camp signals: snapshot today's depth charts, diff across the
        # preseason window. The chart is the coaching staff's own verdict
        # — tracked daily, it says who WON a job before Week 1 lines and
        # fantasy drafts have priced it.
        camp = preseason.camp_report(
            blob, datetime.date.today().isoformat())
        if camp and camp.get("days", 0) >= 2:
            ns = camp.get("new_starters") or []
            print(f"Camp watch ({camp['from']} → {camp['to']}): "
                  f"{len(ns)} new starter(s), {len(camp['risers'])} riser(s), "
                  f"{len(camp['fallers'])} faller(s)"
                  + (": " + ", ".join(
                      f"{r['player']} ({r['team']} {r['position']}1"
                      + (", rookie" if r.get("rookie") else "") + ")"
                      for r in ns[:5]) if ns else ""))
        out = {
            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "season": season,
            "camp": camp,
            "usage": usage,
            "rates": fantasy.league_rates(conn, season),
            "buy_sell": buy_sell,
            "scripts": fantasy.game_scripts(conn),
            # Calendar dates for every unplayed game — the scripts carry
            # the market's read per matchup, the schedule says WHEN, and
            # the day-by-day board joins the two in the browser. Never
            # fatal: no schedule cache means no calendar, not no page.
            "schedule": _upcoming_schedule(season),
            "draft_kit": kit,
            # Is the season we built from the season it SHOULD be? None
            # when current; {have, expected} when the ingest lags the
            # calendar — the state that put Tom Brady on a 2026 draft
            # board. The page wears it as a banner; the build log prints
            # the command that fixes it.
            "usage_stale": fantasy.usage_freshness(season),
            "offseason": off,
            "trending": trending,
            # EVERY RANKING WE CAN LEGITIMATELY READ, side by side. Ethan,
            # 2026-08-15: "add where we show every books ranking side by
            # side." Two columns are built here — our VORP board and
            # Sleeper's own `search_rank`, read out of the players blob
            # already in memory, so this costs no request. The other two
            # (your live draft's pick order, and any list you paste) are
            # filled in the browser because they only exist there.
            "ranks": fantasy_ranks.build(kit, blob or {}),
        }
        # Camp and the rankings table are assembled after the stamp loop
        # above, and their rows carry people too — same map, same rule.
        for rows in ((camp or {}).get("risers") or [],
                     (camp or {}).get("fallers") or [],
                     (camp or {}).get("new_starters") or [],
                     (out.get("ranks") or {}).get("rows") or []):
            for r in rows:
                r.setdefault("headshot", faces.get(r.get("player") or "", ""))
    conn.close()

    p = Path(args.out)
    # THROUGH THE GATE, since 2026-08-22 — `draft_kit`, `ranks`,
    # `buy_sell` and `scripts` are paid keys now, and _write_json puts
    stale = out.get("usage_stale")
    if stale:
        print(f"  WARNING: NFL usage tops out at {stale['have']} — the "
              f"board should build from {stale['expected']}. Fix: "
              f"python3 ingest.py nfl --seasons "
              f"{stale['have'] + 1}-{stale['expected']}")
    # whatever it is given on the public path. Same hole as memes_build:
    # the redaction was correct and the builder walked around it.
    # `_write_json` stays for rosters_nfl.json, which is free.
    from engine import gate
    gate.publish(out, p, p.name)

    # Active rosters ride along: the players blob is already in memory and
    # already paid for, so this is a second reading of it rather than a
    # second fetch. Written to its own file so the NFL page never has to
    # load the whole fantasy payload to answer "who is on this team".
    _write_rosters(p.parent / "rosters_nfl.json", blob)
    mk = ((out.get("draft_kit") or {}).get("market") or {})
    if mk.get("placed"):
        print(f"Draft board: {mk['placed']} player(s) placed at the market\u2019s "
              f"rank ({mk.get('rookies', 0)} rookie(s)) \u2014 "
              + ", ".join(f"{n} {pos}" for pos, n
                          in sorted((mk.get("by_position") or {}).items()))
              + f", deepest rank {mk.get('deepest')}"
              + f" \u00b7 {mk.get('anchor_pct')}% of our board joined "
                f"Sleeper by name ({mk.get('anchored')}/{mk.get('board_seen')})")
        if (mk.get("anchor_pct") or 0) < 60:
            print("  \u26a0\ufe0f  that join is thin \u2014 placements are "
                  "interpolated between OUR players at THEIR market ranks, so "
                  "a low join means the curve is drawn through very few "
                  "points. Check the name normaliser before trusting them.")
    elif blob is None:
        print("Draft board: Sleeper unreachable \u2014 no market placements, "
              "so rookies and anyone who missed last season are OFF the board "
              "(and out of the mock draft's pool).")
    bs = out.get("buy_sell") or {}
    print(f"Fantasy: season {out['season']}, {len(out['usage'])} usage rows, "
          f"{len(bs.get('buy_low', []))} buy-low / {len(bs.get('sell_high', []))} "
          f"sell-high, {len(out['scripts'])} game scripts. Wrote {args.out}")


if __name__ == "__main__":
    main()
