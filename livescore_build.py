#!/usr/bin/env python3
"""Live NFL, CFB, NBA and WNBA scores → web/data/live_{league}.json.

    python3 livescore_build.py
    python3 livescore_build.py --league cfb

THE GAP THIS CLOSES, named by `live_build.py`'s own docstring on the day
it shipped: "MLB, NFL, NBA, WNBA and CFB never got the same treatment."

That file exists because live MLB scores were read out of
`data/mlb_recommendations.json` — 8MB, 923 props, seven minutes thirty-nine
seconds to build — so a score that changes every pitch waited on the whole
model and the site showed games 8-15 minutes behind. Nothing was broken; it
was wired to the wrong file.

MLB got its own fast clock. The other four did not, and `app.js`'s
LIVE_FEEDS still points them at the model boards: NFL at
`data/recommendations.json`, CFB at `data/cfb.json`, NBA and WNBA at
theirs. Same bug, four leagues, still live. NFL is the worse of the two
footballs because it at least CALLS `livescores.attach_live` — inside
nfl_build, behind the whole board. College never called it at all, so its
live scores are whatever the last slate build happened to record.

WHAT THIS COSTS. One request per league per poll, cached 30 seconds by
`fetch_text`, and ZERO odds credits — ESPN's scoreboard is keyless. Four
requests where the alternative is four model builds.

WHAT THIS DELIBERATELY DOES NOT CARRY, copied from live_build.py because
the reasoning is the same: no props, no prices, no edges. Scores and game
state only. That keeps it cheap and keeps it out of the paywall's way — a
score is a public fact and `engine/gate.py` has no reason to redact one.
The odds grid and the live win-probability track still come from the model
board, where they belong and where their latency does not matter; the
front end MERGES the two rather than replacing one with the other.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import time as _time
from pathlib import Path

from engine.sources.fetch import DataUnavailable
from engine.sources.livescores import ESPN_SCOREBOARD, fetch_rows

#: Cached for the launcher's fast cadence. Shorter than this buys nothing
#: — `LIVE_FAST_S` is 12 seconds and the scoreboard does not move faster
#: than the clock on the screen.
TTL = 20

#: Plays on a card: about one drive's worth.
PLAYS_PER_GAME = 6

#: The most football games one pass will fetch a summary for. A college
#: Saturday can have thirty in progress at once, a summary is a few
#: hundred kilobytes, and this box OOM-killed seven test children on
#: 2026-09-04 with nothing else unusual running. Eight summaries every
#: thirty seconds is affordable; thirty is not. Past the cap a game keeps
#: its score and loses only its plays, and the note SAYS SO — an empty
#: strip because the budget ran out and one because the game has not
#: kicked off are different facts. Scoreboard order, which is kickoff
#: order: the earliest games are the ones deepest into their drives.
PLAYS_MAX_GAMES = 8

OUT = Path("web/data")

#: Where one game's WHOLE play-by-play lives: `web/data/pbp/{league}_
#: {event}.json`, one file per live game, written on the same pass that
#: puts the last six plays on the card. Ethan, 2026-09-05: "You should be
#: able to click on each live game and see a deeper play by play." The
#: card's strip stays six plays because the fast file is polled every
#: twelve seconds by every open tab; a game's full list — 392 plays on a
#: finished WNBA game — is fetched only by a reader who opened that game.
#: Free files, like the scoreboards: scores and plays are public facts,
#: nothing priced (engine/gate.FREE_DIRS).
PBP_DIR = OUT / "pbp"

#: A deep file outlives its game by this much and is then pruned. Long
#: enough that a final can still be read the morning after; short enough
#: that a season of games does not accumulate under web/.
PBP_MAX_AGE_S = 36 * 3600


#: THE STAMP THE BROWSER DOES ARITHMETIC ON, in UTC and saying so.
#:
#: Ethan, 2026-09-06, screenshot of a live game: the park card read
#: "updated 240 min ago" while the rail beside it showed pitches from a
#: minute earlier and the topbar said "Updated 1m ago". The file was
#: fine. The label was lying.
#:
#: 240 minutes is not a coincidence — it is the America/New_York offset
#: in September, to the minute. These two lines wrote
#: `datetime.now().isoformat()`: LOCAL time on a box whose service runs
#: in Eastern, with nothing to say so. The page's `pbpAgo` appends "Z"
#: and reads it as UTC, so 18:42 Eastern was read as 18:42 UTC — four
#: hours in the past, on every live game, for as long as the card has
#: existed.
#:
#: It survived because almost every other reader SLICES this string to
#: show a clock time (`.slice(11, 16)`) rather than doing date maths on
#: it, and a sliced local stamp shows the right local time. Exactly one
#: reader subtracts it from `Date.now()`, and that is the one that broke.
#:
#: UTC with an explicit Z, so no reader has to guess. The clock-slicing
#: readers now show UTC rather than Eastern, which is why `pbpAgo` was
#: taught to handle both.
#:
#: PUBLIC AND SHARED, 2026-09-06, because the first version of this note
#: claimed this was "the only writer changed here" — and it was wrong.
#: `live_build.py` writes the deep play-by-play file the game centre
#: actually reads, with its own naive clock, so the page kept reporting
#: four hours after this was "fixed". One helper, imported, rather than
#: two builders each deciding what a timestamp is.
def utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _win_prob(league: str, st, home: str, away: str) -> dict | None:
    """The live win-probability block for one game, or None to show none.

    NO PREGAME LINE IS PASSED, deliberately. This builder polls every few
    seconds and holds no board; reaching for one here would put a
    paywalled file read on the fast clock for a number that matters most
    in the first quarter and barely at all after. The front end merges
    this row with the board card that already carries `game_spread`, and
    that is where the prior belongs — until then this is the score and
    the clock, which is what `basis` says it is.

    Returns None rather than a neutral 50% whenever the clock cannot be
    read: overtime, a pre-game card, a shape the feed did not give. An
    absent panel is honest; a confident coin flip on a game that has not
    kicked off is not.
    """
    from engine import livewp
    left = livewp.seconds_left(league, getattr(st, "period", None),
                               getattr(st, "clock", None))
    if left is None:
        return None
    try:
        margin = float(st.home_score) - float(st.away_score)
    except (TypeError, ValueError):
        return None
    try:
        return livewp.reading(league, home, away, margin, left)
    except Exception:                                      # noqa: BLE001
        # A sport with no measured margin SD refuses here — see
        # `gamebets._sd`. That is the right answer and it must not take
        # the scoreboard down with it: the page still wants the score.
        return None


def _row(r: dict, league: str = "") -> dict:
    """One game in the shape `app.js`'s fetchAllLive merge expects.

    `home` and `away` are the LEAGUE BOARD'S abbreviations, resolved by
    `livescores._side_key` — see its docstring for why that is the fussy
    part. The merge key is `away@home`, and a key that does not match
    does not error, it silently drops the card's lines and its chart.
    """
    st = r["live"]
    live = {
        "state": st.state,
        "home_score": st.home_score,
        "away_score": st.away_score,
        "period": st.period,
        "clock": st.clock,
        "detail": st.detail,
        "start_time": st.start_time,
    }
    # FOOTBALL ONLY, AND ONLY WHEN IT PARSED. `yard_line` and
    # `possession` are what the card art draws the ball with; basketball
    # payloads carry no situation block at all, and a football spot that
    # would not parse leaves them None. Writing the keys anyway would
    # hand the front end `null` to tell apart from "this sport has no
    # such thing", which are different facts.
    # ONLY WHEN THE CLOCK IS STOPPED FOR A REASON. Absent means play is
    # live; a key that was always there would make "" and "no delay" the
    # same fact the page has to tell apart.
    if getattr(st, "hold", ""):
        live["hold"] = st.hold
    if st.yard_line is not None:
        live["yard_line"] = st.yard_line
    if st.possession:
        live["possession"] = st.possession
    # WIN PROBABILITY, and only when the clock could actually be read.
    # Written as a nested block rather than loose keys so a card can tell
    # "this game has no reading" from "this field happened to be zero" —
    # the same reason `yard_line` is absent rather than null above.
    if st.state == "live":
        _wp = _win_prob(str(league or "").lower(), st,
                        r.get("home") or "", r.get("away") or "")
        if _wp:
            live["win_prob"] = _wp
    out = {"event_id": r["event_id"], "home": r["home"], "away": r["away"],
           "home_name": r["home_name"], "away_name": r["away_name"],
           "live": live}
    # ESPN's own team ids, when the scoreboard gave them. A basketball
    # play names its team by id and nothing else, and these are how
    # `attach_plays` turns that id into the card's own `home`/`away` —
    # the verified route, since the summary's team dicts have not been
    # probed. Written only when present, for the reason `yard_line` is.
    if r.get("home_id"):
        out["home_id"] = r["home_id"]
    if r.get("away_id"):
        out["away_id"] = r["away_id"]
    # Where to watch it, when the scoreboard named a carrier (the Watch
    # button, Ethan 2026-10-07). Absent otherwise, for the same reason.
    if getattr(st, "tv", None) or getattr(st, "tv_local", None):
        out["tv"] = list(st.tv or [])
        out["tv_local"] = list(st.tv_local or [])
    return out


def build(league: str, pbp_dir: Path | None = None,
          prev: dict | None = None) -> dict:
    """`{"games": [...], "generated_at": ...}` — or an honest empty board.

    A feed that cannot be reached returns NO GAMES rather than raising,
    exactly as `live_build.build` does. This runs every few seconds beside
    a live site; one unreachable poll must not take the page down, and an
    empty scoreboard is a true statement about what we know right now.

    THE NOTE IS NOT DECORATION. An empty list with no note and an empty
    list because ESPN refused the request look identical to every reader
    downstream, and this repo has been bitten by that shape enough times
    to spell it out — see engine/census.py and the college board that
    "showed nothing on opening Saturday and both logs lied about it".
    """
    now = utc_stamp()
    try:
        rows = fetch_rows(league, ttl=TTL)
    except DataUnavailable as exc:
        return {"generated_at": now, "league": league, "games": [],
                "note": f"{league.upper()} scoreboard unreachable — {exc}"}
    except Exception as exc:                                 # noqa: BLE001
        return {"generated_at": now, "league": league, "games": [],
                "note": f"{league.upper()} scoreboard unreadable — "
                        f"{type(exc).__name__}: {exc}"}
    games = [_row(r, league) for r in rows]
    games.sort(key=lambda g: (g["live"]["start_time"] or "", g["event_id"]))
    out = {"generated_at": now, "league": league, "games": games}
    out["plays_note"] = attach_plays(games, league, pbp_dir=pbp_dir,
                                     prev=prev)
    return out


def _round_robin(live: list[dict], league: str,
                 pbp_dir: Path | None) -> list[dict]:
    """Live games, LEAST RECENTLY SERVED FIRST.

    THE CAP WAS A RANKING, AND IT NEVER MOVED. `PLAYS_MAX_GAMES` was
    chosen against a measured constraint — a summary is a few hundred
    kilobytes and this box OOM-killed seven test children on 2026-09-04
    — so raising it is not the fix. The bug was that the same eight
    games won the cap on every pass: the order was the scoreboard's,
    which is kickoff order, and kickoff order does not change during a
    game. On a September Saturday the early window held the budget for
    three hours and every other college game had no plays on its card
    and NO DEEP FILE AT ALL, so opening it showed nothing. Ethan,
    2026-09-19: "none of the live play by play is working for CFB
    games."

    The deep file's own mtime is the cursor — a game that has never been
    served has no file and sorts first, and one served a moment ago
    sorts last. Nothing is stored between passes and nothing has to be:
    the answer is already on disk. Thirty live games against a cap of
    eight now means every game is refreshed about every four passes,
    which on a twelve-second clock is under a minute, rather than
    twenty-two games never being fetched at all.

    Same ceiling, same requests per pass, all of the slate.
    """
    if pbp_dir is None:
        return list(live)

    def served_at(g: dict) -> float:
        try:
            return (Path(pbp_dir) /
                    f"{league}_{g['event_id']}.json").stat().st_mtime
        except OSError:
            return 0.0                 # never served: it goes first

    return sorted(live, key=served_at)


def _carry_forward(waiting: list[dict], league: str,
                   prev: dict | None) -> int:
    """Give a game past the cap the plays it had LAST pass. Returns how
    many were carried.

    Without this the round robin trades one failure for another: a card
    would show six plays on the pass it was fetched and an empty strip
    on the next three, so the strip would blink rather than lag. A play
    list a few passes old is the honest thing to show while the budget
    is elsewhere, and `plays_state` says which it is so the page can
    word it.

    ``prev`` is the fast file already on disk — ONE small read for the
    whole league, not one per game. Re-reading each deep file here would
    put the cost back exactly where the cap took it out.
    """
    if not waiting or not prev:
        return 0
    was = {str(g.get("event_id") or ""): g
           for g in (prev.get("games") or []) if isinstance(g, dict)}
    n = 0
    for g in waiting:
        old = was.get(str(g.get("event_id") or "")) or {}
        plays = old.get("plays")
        if not plays:
            continue
        g["plays"] = plays
        if old.get("drive"):
            g["drive"] = old["drive"]
        if old.get("players"):
            g.setdefault("players", old["players"])
        g["plays_state"] = "carried"
        n += 1
    return n


def attach_plays(games: list[dict], league: str,
                 pbp_dir: Path | None = None,
                 prev: dict | None = None) -> str:
    """Put the last few plays — and, for football, the current drive —
    on every game IN PROGRESS. Returns a note for the log and the file.

    ONLY LIVE GAMES. Football reads the `drives` block the droplet probe
    saw on a live college game; basketball reads the `plays` list it saw
    on a finished WNBA game (`engine/sources/espnplays` carries both
    shapes and what each was seen on). A scheduled game has neither and
    a final is not what anybody is watching. A league in neither tuple
    is left alone and the note says so.

    THE SIDES OF A BASKETBALL PLAY COME FROM THE SCOREBOARD. A hoops
    play carries `team{id}` and nothing else; this game's `home_id` and
    `away_id` were read off the same scoreboard payload as its score, so
    the play's `team` is the card's own key by the same route rather
    than by a second reading of ESPN's abbreviations.

    A GAME THAT FAILS KEEPS ITS SCORE. Each summary is guarded on its own
    and the failures are counted rather than raised — one unreachable
    play feed must not cost the scoreboard the card, which is the more
    important product of this process.

    ``pbp_dir`` set: the same payload also becomes the game's deep file
    (`write_pbp`) — every play, football's grouped by drive — so the
    page a reader opens from the card costs no second fetch. A deep file
    that fails to write costs nothing but itself.
    """
    from engine.sources import espnplays
    if league in espnplays.FOOTBALL:
        noun = "drives"
    elif league in espnplays.HOOPS or league in espnplays.HOCKEY:
        noun = "plays"
    else:
        for g in games:
            g["plays_state"] = "no_source"
        return f"{league}: no play-by-play source yet"
    # WHY THIS LIST IS THE SIZE IT IS, ON EVERY GAME. Ethan's standing
    # complaint about the site is failures that read as ordinary empty
    # results, and the play rail was the cleanest example left: the page
    # drew "No plays yet." whether the game had not kicked off, the feed
    # was unreachable, or the game was past the fetch cap. Three
    # different situations, one sentence, and only one of them is the
    # reader's own patience.
    #
    # THE NOTE THIS FUNCTION RETURNS IS NOT THAT ANSWER. It is one line
    # for the whole board in operator language ("plays: 3 of 4 live
    # game(s), 1 feed(s) unreachable, 2 deep file(s)") — the right thing
    # for a build log and the wrong thing to put in front of somebody
    # deciding whether to bet a game. This is per GAME, and it is a state
    # rather than a sentence so the page owns the wording.
    for g in games:
        g["plays_state"] = "idle"
    live = [g for g in games if g["live"]["state"] == "live"]
    if not live:
        return f"no games in progress — no {noun} fetched"
    live = _round_robin(live, league, pbp_dir)
    served, waiting = live[:PLAYS_MAX_GAMES], live[PLAYS_MAX_GAMES:]
    for g in waiting:
        g["plays_state"] = "capped"
    got = failed = deep = boxes = nofeed = 0
    for g in served:
        try:
            payload = espnplays.fetch_summary(league, g["event_id"])
            sides = {str(g.get("home_id") or ""): g["home"],
                     str(g.get("away_id") or ""): g["away"]}
            sides.pop("", None)
            if noun == "drives":
                g["plays"] = espnplays.football_plays(
                    payload, league, PLAYS_PER_GAME,
                    home=g["home"], away=g["away"])
                drive = espnplays.current_drive(payload, league)
                if drive:
                    g["drive"] = drive
            elif not isinstance((payload or {}).get("plays"), list):
                # The summary came back without a play list: say so,
                # rather than "No plays yet." on a game in its second
                # period (hockey's first live games from this box).
                g["plays_state"] = "no_feed"
                nofeed += 1
                continue
            else:
                g["plays"] = espnplays.hoops_plays(payload, league,
                                                   PLAYS_PER_GAME, sides=sides)
            g["plays_state"] = "ok"
            got += 1
        except Exception:                                    # noqa: BLE001
            g["plays_state"] = "unreachable"
            failed += 1                # the card keeps its score
            continue
        # THE BOX SCORE, ONTO THE CARD'S OWN ROW, from the payload already
        # in hand. Ethan, 2026-09-14, 11:01pm, every Broncos-Chiefs bet on
        # the Live tab reading "in play" and nothing else: "why are we not
        # ... tracking the live stats like how sports books do it". The
        # tracker's number came from `livepicks.espn_progress` at BOARD
        # build time — every forty-five minutes or so on the football
        # boards — and the page had nothing fresher to read. This file is
        # written every twelve seconds while a game is on, and the summary
        # it already fetches for the plays carries the box; the parser the
        # deep file's Player stats room trusts (`pbp_players`) reads it
        # here, so the bet under a game card counts on the game card's
        # clock. A parser that cannot read this payload costs the row its
        # box and nothing else: the plays stay, and the page keeps the
        # build's number.
        try:
            g["players"] = pbp_players(league, payload, g)
            boxes += 1
        except Exception:                                    # noqa: BLE001
            pass
        if pbp_dir is not None:
            try:
                write_pbp(league, g, payload, pbp_dir, sides=sides)
                deep += 1
            except Exception:                                # noqa: BLE001
                pass                       # the card keeps its plays
    carried = _carry_forward(waiting, league, prev)
    skipped = max(0, len(live) - PLAYS_MAX_GAMES)
    note = f"{noun}: {got} of {len(live)} live game(s)"
    if failed:
        note += f", {failed} feed(s) unreachable"
    if nofeed:
        note += f", {nofeed} summary(ies) with no play list"
    if skipped:
        note += (f", {skipped} past the {PLAYS_MAX_GAMES}-game cap "
                 f"({carried} carried forward, "
                 f"{skipped - carried} scores only)")
    if pbp_dir is not None and got:
        note += f", {deep} deep file(s)"
    if boxes:
        note += f", {boxes} box score(s)"
    return note


def pbp_players(league: str, payload: dict, g: dict) -> list[dict]:
    """``[{player, team, position, stats}]`` from the summary already in
    hand — the box score behind the play-by-play page's Player stats
    tab (Ethan, 2026-09-05: "the play by plays other rooms").

    THE SAME PARSERS THE TRACKER TRUSTS FOR ITS FINALS, and nothing
    parsed a second way: `nflpreseason.parse_boxscore` (labels, not
    positions) for the NFL, `cfbdata.parse_summary` for college,
    `espnhoops.parse_summary` for the hoops leagues. A football row is
    one market per line, so those are folded into one row per player.
    A parser that raises — a shape it does not recognise — costs the
    tab and nothing else: the caller leaves `players` out and the page
    says there is no box score on file.
    """
    if league == "nfl":
        from engine.sources.nflpreseason import parse_boxscore
        by: dict = {}
        for r in parse_boxscore(payload, {"home": g.get("home"), "away": g.get("away")}):
            key = (r.get("player"), r.get("team"))
            row = by.setdefault(key, {"player": r.get("player"), "team": r.get("team"),
                                      "position": "", "stats": {}})
            try:
                row["stats"][r["market"]] = float(r["value"])
            except (KeyError, TypeError, ValueError):
                continue
        return list(by.values())
    if league == "cfb":
        from engine.sources.cfbdata import parse_summary
    else:
        from engine.sources.espnhoops import parse_summary
    out = []
    for r in parse_summary(payload):
        stats = {}
        for k, v in (r.get("stats") or {}).items():
            try:
                stats[k] = float(v)
            except (TypeError, ValueError):
                continue
        out.append({"player": r.get("player"), "team": r.get("team", ""),
                    "position": r.get("position", ""), "stats": stats})
    return out


def pbp_doc(league: str, g: dict, payload: dict,
            sides: dict | None = None) -> dict:
    """One game's whole play-by-play as the page reads it.

    The card's own header fields ride along — sides in the board's
    vocabulary, names, the live state — so the page needs no second
    lookup to say whose game it is. Football carries `drives`, each with
    its plays, and the same plays flattened as `plays`; basketball has
    no drive and carries `plays` alone. Newest LAST throughout, as a
    play-by-play reads; the page decides what to show first.
    """
    from engine.sources import espnplays
    doc = {
        "league": league,
        "event_id": str(g.get("event_id") or ""),
        "generated_at": utc_stamp(),
        "home": g.get("home"), "away": g.get("away"),
        "home_name": g.get("home_name", ""), "away_name": g.get("away_name", ""),
        "live": g.get("live") or {},
    }
    if g.get("tv") or g.get("tv_local"):
        doc["tv"], doc["tv_local"] = list(g.get("tv") or []), list(g.get("tv_local") or [])
    if league in espnplays.FOOTBALL:
        drives = espnplays.football_drives(
            payload, league, home=doc["home"] or "", away=doc["away"] or "")
        doc["drives"] = drives
        doc["plays"] = [r for d in drives for r in d["plays"]]
    else:
        doc["plays"] = espnplays.hoops_plays(payload, league, 0, sides=sides)
    # The box score, for the Player stats tab. A parser that cannot read
    # this payload leaves the key out; the page says so. The card's row
    # already carries it when `attach_plays` parsed it a moment ago, and
    # one parse per pass is enough.
    try:
        doc["players"] = (g["players"] if isinstance(g.get("players"), list)
                          else pbp_players(league, payload, g))
    except Exception:                                        # noqa: BLE001
        pass
    # THE GAMECAST'S ROOMS (2026-10-09, Ethan's ESPN screenshots): the
    # whole box score, each side's game totals, the two records, and the
    # drive in progress — all off the summary in hand, each guarded on
    # its own so a shape this box has not seen costs that key alone.
    for key, read in (("box", lambda: espnplays.summary_box(payload, league)),
                      ("team_stats", lambda: espnplays.summary_team_stats(payload, league)),
                      ("records", lambda: espnplays.team_records(payload, league))):
        try:
            got = read()
        except Exception:                                    # noqa: BLE001
            continue
        if got:
            doc[key] = got
    if league in espnplays.FOOTBALL:
        try:
            drive = espnplays.current_drive(payload, league)
        except Exception:                                    # noqa: BLE001
            drive = None
        if drive:
            doc["drive"] = drive
    # THE BASKETBALL PAGE'S HEADER (2026-10-15, Ethan's NBA render): the
    # quarter-by-quarter line, the building, and the scorer's table —
    # timeouts, team fouls, the bonus, the ball — where ESPN carries it.
    # Each guarded on its own, each absent rather than empty.
    if league in espnplays.HOOPS:
        for key, read in (("linescores", lambda: espnplays.hoops_linescores(payload, league)),
                          ("venue", lambda: espnplays.hoops_venue(payload)),
                          ("situation", lambda: espnplays.hoops_situation(payload, league))):
            try:
                got = read()
            except Exception:                                # noqa: BLE001
                continue
            if got:
                doc[key] = got
    return doc


def write_pbp(league: str, g: dict, payload: dict, pbp_dir: Path,
              sides: dict | None = None) -> Path:
    """Write the deep file atomically; returns its path."""
    pbp_dir = Path(pbp_dir)
    pbp_dir.mkdir(parents=True, exist_ok=True)
    out = pbp_dir / f"{league}_{g['event_id']}.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pbp_doc(league, g, payload, sides=sides)))
    os.replace(tmp, out)
    return out


def prune_pbp(pbp_dir: Path, max_age_s: int = PBP_MAX_AGE_S,
              now: float | None = None) -> int:
    """Remove deep files older than ``max_age_s``; returns how many.

    Runs on the fast clock, so it must be cheap — one directory scan,
    no parsing — and must never raise into the scoreboard write.
    """
    pbp_dir = Path(pbp_dir)
    if not pbp_dir.is_dir():
        return 0
    now = _time.time() if now is None else now
    gone = 0
    for path in pbp_dir.glob("*.json"):
        try:
            if now - path.stat().st_mtime > max_age_s:
                path.unlink()
                gone += 1
        except OSError:
            continue
    return gone


def _previous(out_dir: Path, league: str) -> dict | None:
    """Last pass's fast file, for the plays a capped game keeps.

    Unreadable or absent is None and costs only the carry-forward — the
    scoreboard this function serves is the more important product, and a
    first run has no previous pass by definition.
    """
    try:
        with open(Path(out_dir) / f"live_{league}.json",
                  encoding="utf-8") as fh:
            got = json.load(fh)
        return got if isinstance(got, dict) else None
    except Exception:                                        # noqa: BLE001
        return None


def write(league: str, out_dir: Path = OUT) -> dict:
    pbp_dir = Path(out_dir) / "pbp"
    payload = build(league, pbp_dir=pbp_dir,
                    prev=_previous(out_dir, league))
    try:
        prune_pbp(pbp_dir)
    except Exception:                                        # noqa: BLE001
        pass                          # the scoreboard write comes first
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"live_{league}.json"
    # Atomic replace — this runs on the launcher's fast clock while the
    # Live tab polls the same file; see memes_build for the lesson.
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=1))
    os.replace(tmp, out)
    if league == "nhl":
        # The skaters' lines for the parlay checker (nhl_box_pass). After
        # the scoreboard, and its own try: a box that will not load costs
        # the live props their numbers and nothing else.
        try:
            note = nhl_box_pass(payload.get("games") or [], Path(out_dir))
            if note:
                payload["box_note"] = note
        except Exception:                                    # noqa: BLE001
            pass
        # The league's own events onto each game's deep file, for the live
        # rink page (nhl_rink_pass). Its own try again: a play-by-play that
        # will not load leaves the page on ESPN's plays, as before.
        try:
            note = nhl_rink_pass(payload.get("games") or [], Path(out_dir))
            if note:
                payload["rink_note"] = note
        except Exception:                                    # noqa: BLE001
            pass
    return payload


#: HOCKEY'S SKATER LINES, for the parlay checker's live props
#: (engine/sliplive). ESPN's hockey box score has never been verified from
#: this box (engine/sources/espnplays says so), so the lines come from the
#: league's own box score through the parser settlement already trusts,
#: `nhldata.parse_boxscore` — fetched under their OWN cache names, because
#: the settlement ingest reads `nhl_box_{id}` for a month and a mid-game
#: snapshot written under that name would be graded as the final.
NHL_BOX_FILE = "live_nhl_box.json"
#: A game in progress is re-read at most this often; a final, this often.
NHL_BOX_TTL = 30
NHL_FINAL_TTL = 600
#: The most games one pass reads a box for — in progress first. A full
#: hockey night is sixteen; they start over three hours.
NHL_BOX_MAX_GAMES = 8


def _et_today() -> _dt.date:
    try:
        from zoneinfo import ZoneInfo
        return _dt.datetime.now(ZoneInfo("America/New_York")).date()
    except Exception:                                        # noqa: BLE001
        return _dt.date.today()


def _nhl_names(path: Path | None = None) -> dict:
    """{player id: full name} off the nightly roster file (H5) — the box
    score names a skater "C. McDavid", the board "Connor McDavid"."""
    p = Path(path) if path else Path(__file__).resolve().parent / "data" / "nhl_rosters.json"
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError):
        return {}
    return {str(pl.get("pid")): str(pl.get("name") or "")
            for players in (doc.get("teams") or {}).values() for pl in players or []
            if isinstance(pl, dict) and pl.get("pid") and pl.get("name")}


def nhl_box_pass(games: list[dict], out_dir: Path, fetch_day=None,
                 fetch_box=None, names: dict | None = None,
                 today: _dt.date | None = None) -> str:
    """Write `live_nhl_box.json`: every hockey game on the scoreboard that
    is in progress or over, with each skater's and goalie's line. Returns
    a line for the log, or "" when no game is on.

    The scoreboard's pairs are already the league's own codes
    (`livescores._side_key`), which are the score feed's, so a game joins
    on AWAY@HOME. The score feed is read for today and yesterday on the
    Eastern clock — a late game runs past midnight."""
    on = [g for g in games or [] if (g.get("live") or {}).get("state") in ("live", "final")]
    if not on:
        return ""
    from engine.sources import nhldata
    from engine.sources.fetch import fetch_json
    if fetch_day is None:
        def fetch_day(d):
            return fetch_json(f"{nhldata.API}/score/{d}", f"nhl_live_score_{d}.json", ttl=NHL_BOX_TTL)
    if fetch_box is None:
        def fetch_box(gid, final=False):
            return fetch_json(f"{nhldata.API}/gamecenter/{gid}/boxscore",
                              f"nhl_live_box_{gid}.json",
                              ttl=NHL_FINAL_TTL if final else NHL_BOX_TTL)
    names = _nhl_names() if names is None else names
    day = today or _et_today()
    feed: dict = {}
    for d in (day, day - _dt.timedelta(days=1)):
        try:
            rows = nhldata.parse_score_day(fetch_day(d.isoformat()))
        except Exception:                                    # noqa: BLE001
            continue
        for r in rows:
            feed.setdefault((r.get("away"), r.get("home")), r)
    on.sort(key=lambda g: 0 if (g.get("live") or {}).get("state") == "live" else 1)
    out_games, failed, missing = [], 0, 0
    for g in on[:NHL_BOX_MAX_GAMES]:
        r = feed.get((g.get("away"), g.get("home")))
        if not r or not r.get("game_id"):
            missing += 1
            continue
        final = bool(r.get("final"))
        try:
            rows = nhldata.parse_boxscore(fetch_box(r["game_id"], final=final))
        except Exception:                                    # noqa: BLE001
            failed += 1
            continue
        players = []
        for p in rows:
            keys = nhldata.GOALIE_MARKETS if p.get("goalie") else nhldata.SKATER_MARKETS
            players.append({"player": names.get(str(p.get("pid"))) or p.get("short") or "",
                            "team": p.get("team") or "", "position": p.get("position") or "",
                            "stats": {k: p[k] for k in keys if isinstance(p.get(k), (int, float))}})
        out_games.append({"away": g.get("away"), "home": g.get("home"), "nhl_id": r["game_id"],
                          "state": "final" if final else "live", "players": players})
    doc = {"generated_at": utc_stamp(), "games": out_games}
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / NHL_BOX_FILE
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, out)
    note = f"nhl box: {len(out_games)} of {len(on)} game(s)"
    if failed:
        note += f", {failed} unreachable"
    if missing:
        note += f", {missing} not on the league's score feed"
    return note


#: THE LIVE RINK (2026-10-15, Ethan's NHL renders: "figure out what data we
#: can use for the live play by play screen for nhl like live posetions and
#: puck tracking"). The league's play-by-play places every event on the ice —
#: faceoffs, hits, takeaways, giveaways, shots, blocks, goals, penalties —
#: with who was in it and how many skaters each side had; ESPN's hockey
#: plays carry none of that. `engine/sources/nhlrink` turns it into the
#: deep file's `rink` block, with the league's box score (ice time) and our
#: expected goals on each attempt when the model is on the box. Fetched
#: under its own cache name, like the box: the shot ingest reads
#: `nhl_pbp_{id}` for a month, and a mid-game snapshot under that name
#: would be read as the final's.
NHL_PBP_TTL = 15


def _nhl_feed(fetch_day, today: _dt.date | None = None) -> dict:
    """{(away, home): score-feed row} for today and yesterday on the
    Eastern clock — a late game runs past midnight."""
    from engine.sources import nhldata
    day = today or _et_today()
    feed: dict = {}
    for d in (day, day - _dt.timedelta(days=1)):
        try:
            rows = nhldata.parse_score_day(fetch_day(d.isoformat()))
        except Exception:                                    # noqa: BLE001
            continue
        for r in rows:
            feed.setdefault((r.get("away"), r.get("home")), r)
    return feed


_XG_CACHE: dict = {}


def _nhl_xg():
    """The expected-goals scorer for one shot row, or None when the model
    file is not on this box. Re-read when the nightly refit rewrites it."""
    from engine.nhl import xg
    path = xg._models_dir() / xg.MODEL_FILE
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    if _XG_CACHE.get("stamp") != stamp:
        model = xg.load(path)
        _XG_CACHE.clear()
        _XG_CACHE.update(stamp=stamp, model=model)
    model = _XG_CACHE.get("model")
    return (lambda shot: xg.xg(model, shot)) if model else None


def _merge_rink(g: dict, rink: dict, pbp_dir: Path) -> None:
    """Put the rink block on the game's deep file, atomically. A file ESPN
    already wrote keeps its modified time — that time is the round robin's
    cursor (`_round_robin`) and the league's events are not ESPN serving
    the game; a game ESPN has not served yet gets a file of its own."""
    pbp_dir = Path(pbp_dir)
    pbp_dir.mkdir(parents=True, exist_ok=True)
    out = pbp_dir / f"nhl_{g['event_id']}.json"
    stamp = None
    try:
        doc = json.loads(out.read_text())
        stamp = out.stat().st_mtime
    except (OSError, ValueError):
        doc = None
    if not isinstance(doc, dict):
        doc = {"league": "nhl", "event_id": str(g.get("event_id") or ""), "generated_at": utc_stamp(),
               "home": g.get("home"), "away": g.get("away"),
               "home_name": g.get("home_name", ""), "away_name": g.get("away_name", ""), "plays": []}
    if g.get("live"):
        doc["live"] = g["live"]          # this pass's scoreboard, the freshest
    doc["rink"] = rink
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, out)
    if stamp is not None:
        os.utime(out, (stamp, stamp))


def nhl_rink_pass(games: list[dict], out_dir: Path, fetch_day=None, fetch_box=None,
                  fetch_pbp=None, xg_fn=..., today: _dt.date | None = None) -> str:
    """The `rink` block onto the deep file of every hockey game in progress
    or over (up to the box pass's cap, in progress first). Returns a line
    for the log, or "" when no game is on."""
    on = [g for g in games or [] if (g.get("live") or {}).get("state") in ("live", "final")]
    if not on:
        return ""
    from engine.sources import nhldata, nhlrink
    from engine.sources.fetch import fetch_json
    if fetch_day is None:
        def fetch_day(d):
            return fetch_json(f"{nhldata.API}/score/{d}", f"nhl_live_score_{d}.json", ttl=NHL_BOX_TTL)
    if fetch_box is None:
        def fetch_box(gid, final=False):
            return fetch_json(f"{nhldata.API}/gamecenter/{gid}/boxscore", f"nhl_live_box_{gid}.json",
                              ttl=NHL_FINAL_TTL if final else NHL_BOX_TTL)
    if fetch_pbp is None:
        def fetch_pbp(gid, final=False):
            return fetch_json(f"{nhldata.API}/gamecenter/{gid}/play-by-play", f"nhl_live_pbp_{gid}.json",
                              ttl=NHL_FINAL_TTL if final else NHL_PBP_TTL)
    if xg_fn is ...:
        xg_fn = _nhl_xg()
    feed = _nhl_feed(fetch_day, today)
    on.sort(key=lambda g: 0 if (g.get("live") or {}).get("state") == "live" else 1)
    done = failed = missing = 0
    for g in on[:NHL_BOX_MAX_GAMES]:
        r = feed.get((g.get("away"), g.get("home")))
        if not r or not r.get("game_id"):
            missing += 1
            continue
        final = bool(r.get("final"))
        try:
            pbp = fetch_pbp(r["game_id"], final=final)
        except Exception:                                    # noqa: BLE001
            failed += 1
            continue
        try:
            box = fetch_box(r["game_id"], final=final)
        except Exception:                                    # noqa: BLE001
            box = None                 # the events stand without ice time
        try:
            rink = nhlrink.rink_doc(pbp, box, xg_fn)
            rink["at"] = utc_stamp()
            _merge_rink(g, rink, Path(out_dir) / "pbp")
            done += 1
        except Exception:                                    # noqa: BLE001
            failed += 1
    note = f"nhl rink: {done} of {len(on)} game(s)"
    if failed:
        note += f", {failed} unreachable"
    if missing:
        note += f", {missing} not on the league's score feed"
    return note


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", default="",
                    help="one of " + ", ".join(ESPN_SCOREBOARD))
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    leagues = [args.league] if args.league else list(ESPN_SCOREBOARD)
    out_dir = Path(args.out_dir)
    total = live = 0
    for lg in leagues:
        # ONE LEAGUE'S FAILURE IS NOT FOUR. `build` already refuses to
        # raise on a bad feed; this catches the write itself, so a full
        # disk or a permission fault on one file still leaves the other
        # three boards refreshed.
        try:
            payload = write(lg, out_dir)
        except Exception as exc:                             # noqa: BLE001
            print(f"  ⚠️  {lg}: {type(exc).__name__}: {exc}")
            continue
        n = len(payload["games"])
        on = sum(1 for g in payload["games"]
                 if g["live"]["state"] == "live")
        total += n
        live += on
        note = payload.get("note")
        print(f"  {lg}: {n} game(s), {on} in progress"
              + (f" — {note}" if note else ""))
        if on and payload.get("plays_note"):
            print(f"      {payload['plays_note']}")
        # Hockey's two league passes say what they did (nhl_box_pass,
        # nhl_rink_pass): a game the league's feed did not answer for shows
        # here, not only as a page without its rink.
        for key in ("box_note", "rink_note"):
            if payload.get(key):
                print(f"      {payload[key]}")
    print(f"live scores: {total} game(s) across {len(leagues)} league(s), "
          f"{live} in progress → {out_dir}/live_*.json")


if __name__ == "__main__":
    main()
