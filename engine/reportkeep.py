"""A game under way keeps the report it had before it started (2026-11-16).

Ethan, 2026-11-16, with a finished game's page: "when a game is already over
and someone goes and clicks on this game page ... show ... if these props won
or lost and if the parlays won or lost and what legs won and lost and if our
game report and reads was correct ... And that needs to be done for all
sports", and the same day: "all bets and parlays made from the game reports
should be categorized as 'report' bets".

THE GAP. A board takes a game's picks down when the game starts
(engine/likely: a pick leaves for "its game starting"; engine/livepicks brings
the journal's copies back as a tracker), and every build writes every report
again. So a game under way or over had its report written without its picks
card or its reads' picks: the finished page had none of our picks to grade
(engine/gameresults, js/report.js), Report Picks lost the game
(engine/reportbets), and the reads were written again over box scores that
hold the game itself. College wrote no report at all once the night was over:
it writes the games it prices (leaguereport.attach, `board_games`), and a
board after the last final prices none.

THE REPORT AS IT STOOD. `hold` keeps every report of a game not yet started,
its bets with it (reportbets.PRIVATE), beside the private board the way
engine/reportlog keeps what changed: one file a league, never in the public
tree (the reports are paid). Once a game has started (its live state, else its
start time passed, read by likely._kicked_off, the clock the boards take
picks down on) its report is the one kept, marked `kept` with when it was last
written ("Sun 6:58 PM ET"); a started game with none kept (the first build
after a deploy, or a game first seen under way) is written as before.

THE GAME'S PARLAYS AND PICKS GO WITH IT (Ethan, 2026-11-16, with a finished
game's page: "I want the parlay tab to still be there after the game, and
people can go back and see if the parlays for the game we recommended hit or
not, and if the picks hit or not"). The board builds each game's parlays only
for a game still to play (engine/gameparlays) and takes its picks down at the
start, so beside each report the file keeps the game's tickets (its
`game_parlays` entry) and the picks the game's page drew (PICK_LISTS). A
started game's tickets go back into the board's `game_parlays`, marked
`kept` (the parlay journal never writes a kept ticket: it was journaled, or
not, before the start), and its picks under KEPT_PICKS, a paid key the game's
page reads once the board's own lists have none for the game.

A game leaves the file once it is off the board and KEEP_DAYS past its date.
Standard library only; never raises out of `hold`.
"""
from __future__ import annotations

import copy
import datetime as _dt
from pathlib import Path

#: Days past its date a game off the board stays in the file (a board that
#: blinks empty for a build must not lose its started games' reports).
KEEP_DAYS = 1

#: The live states that say a game has begun (the boards' `live.state`).
STARTED = ("live", "final")
#: The board key a started game's picks come back under (engine/gate.PAID_KEYS).
KEPT_PICKS = "kept_picks"
#: The picks the game's page draws, by the list it draws them from.
PICK_LISTS = {"likely": "the one board's rows", "shelf": "the Most Likely list, where a league has no one board",
              "edge": "the Edge picks recommended", "bets": "the game bets", "shots": "the long shots"}


def path_for(sport: str, where) -> Path:
    return Path(where) / f"reportkeep_{sport}.json"


def _eastern():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except Exception:                                        # noqa: BLE001
        return _dt.timezone(_dt.timedelta(hours=-5))


def stamps(at: str | None = None) -> tuple[str, str]:
    """(UTC, Eastern) for this build: ``at`` is an Eastern clock time when it
    has no zone (reportlog.now_et, the reports' own stamp), now when none.
    The UTC one is aware, which likely._kicked_off reads; the Eastern one is
    plain, as reportlog writes it."""
    et = _eastern()
    t = None
    if at:
        try:
            t = _dt.datetime.fromisoformat(str(at).strip().replace("Z", "+00:00"))
        except ValueError:
            t = None
    if t is None:
        t = _dt.datetime.now(_dt.timezone.utc)
    elif t.tzinfo is None:
        t = t.replace(tzinfo=et)
    return (t.astimezone(_dt.timezone.utc).isoformat(timespec="seconds"),
            t.astimezone(et).replace(tzinfo=None).isoformat(timespec="seconds"))


def started(g: dict, stamp: str) -> bool:
    """Has this board game begun by ``stamp`` (an aware time): its live
    state, else its start passed on the clock the boards take a game's picks
    down on (likely._kicked_off: an ISO start, or a bare Eastern "20:15"
    beside its date). Unreadable is not started."""
    if not isinstance(g, dict):
        return False
    if str((g.get("live") or {}).get("state") or "").lower() in STARTED:
        return True
    from .likely import _kicked_off
    return _kicked_off({"kickoff": g.get("kickoff"), "game_date": g.get("date")}, stamp)


def _key_of_report(r: dict) -> str:
    return f"{r.get('away')}@{r.get('home')}|{str(r.get('date') or '')[:10]}"


def _in_game(r: dict, g: dict) -> bool:
    """A board row on this game: by its "AWAY@HOME", its two clubs, or its club
    and opponent (gamereport._card_in_game's way)."""
    teams = {g.get("home"), g.get("away")}
    key = r.get("game")
    if isinstance(key, str) and "@" in key:
        return key == f"{g.get('away')}@{g.get('home')}"
    if r.get("home") and r.get("away"):
        return {r.get("home"), r.get("away")} == teams
    return r.get("team") in teams and (not r.get("opponent") or r.get("opponent") in teams)


def picks_for(result: dict, g: dict) -> dict:
    """The picks the game's page draws for ``g`` (PICK_LISTS), each list only
    when it has any."""
    lb = (result or {}).get("likely_board") or {}
    rows = {
        "likely": [r for r in lb.get("rows") or [] if isinstance(r, dict) and _in_game(r, g)],
        "shelf": ([] if lb.get("rows") else
                  [r for r in (result or {}).get("most_likely") or [] if isinstance(r, dict) and _in_game(r, g)]),
        "edge": [r for r in (result or {}).get("recommendations") or []
                 if isinstance(r, dict) and r.get("recommended") and _in_game(r, g)],
        "bets": [b for b in (result or {}).get("game_bets") or []
                 if isinstance(b, dict) and b.get("home") == g.get("home") and b.get("away") == g.get("away")],
        "shots": [r for r in (result or {}).get("long_shots") or [] if isinstance(r, dict) and _in_game(r, g)],
    }
    return {k: copy.deepcopy(v) for k, v in rows.items() if v}


def parlays_for(result: dict, g: dict) -> dict | None:
    """The game's own entry in the board's `game_parlays`, or None."""
    for x in ((result or {}).get("game_parlays") or {}).get("games") or []:
        if isinstance(x, dict) and x.get("home") == g.get("home") and x.get("away") == g.get("away"):
            return copy.deepcopy(x)
    return None


def _restore(result: dict, g: dict, rec: dict, words: str) -> None:
    """A started game's tickets back into the board's `game_parlays` (marked
    `kept`), when the board has none for it, and its picks under KEPT_PICKS."""
    gp = rec.get("parlays")
    if isinstance(gp, dict) and gp and parlays_for(result, g) is None:
        board = result.get("game_parlays")
        if not isinstance(board, dict):
            board = result["game_parlays"] = {"games": []}
        board.setdefault("games", []).append(dict(gp, kept=words))
    picks = rec.get("picks")
    if isinstance(picks, dict) and picks:
        result.setdefault(KEPT_PICKS, {})[f"{g.get('away')}@{g.get('home')}"] = picks


#: This build's count of started games (`hold`): kept from before the start, rebuilt from the archive, and
#: written as built for want of either. The board carries it (REPORT_KEEP_KEY), so the heartbeat can say so.
LAST: dict = {}
REPORT_KEEP_KEY = "report_keep"


def _from_archive(path, g: dict) -> dict | None:
    """A STARTED GAME'S RECORD, REBUILT FROM ITS ARCHIVED REPORT (step AEA, 24 November 2026).

    The file beside the private board is the only place a started game's report, tickets and picks as they
    stood before the start live until the game is archived (engine/reportarchive), and a build that finds a
    started game missing from it writes the game's report as built after the start: no picks card, no tickets,
    and its archived file written again without them. Live on the 24th, every NFL game of the week before but
    its Monday night read "unkept" on Report Picks. Where the game's archived file holds the report kept before
    the start, that report, its tickets and its picks are the game's record again ({"at", "report", "parlays",
    "picks", "words"}: the kept words the report carries); None where it does not."""
    try:
        from . import reportarchive
        p = Path(path)
        sport = p.stem[len("reportkeep_"):] if p.stem.startswith("reportkeep_") else ""
        doc = reportarchive.load(sport, str(g.get("date") or "")[:10], g.get("away"), g.get("home"), where=p.parent)
    except Exception:                                        # noqa: BLE001
        return None
    rep = (doc or {}).get("report")
    if not isinstance(rep, dict) or not rep.get("kept"):
        return None
    rec = {"at": "", "words": str(rep["kept"]), "report": {k: v for k, v in rep.items() if k != "kept"}}
    gp = doc.get("parlays")
    if isinstance(gp, dict) and gp.get("kept"):
        rec["parlays"] = {k: v for k, v in gp.items() if k != "kept"}
    if isinstance(doc.get("picks"), dict) and doc["picks"]:
        rec["picks"] = doc["picks"]
    return rec


def _read_kept(path) -> tuple[dict, bool]:
    """(the file's document, whether it is there and could not be read this time). A file that cannot be opened
    (a full table of open files, a disk that will not answer) is left for the next build to read again; one whose
    text is no document is set aside beside it (".unreadable", for a look) and the file starts again, since no
    later build could read it either. No file is an empty one."""
    import json
    p = Path(path)
    if not p.exists():
        return {}, False
    try:
        with open(p) as fh:
            doc = json.load(fh)
    except OSError as exc:
        print(f"⚠️  the reports kept before the start could not be read ({exc}); the file is left as it is this "
              f"build and each started game is read from its archived report")
        return {}, True
    except ValueError as exc:
        try:
            p.replace(p.with_name(p.name + ".unreadable"))
        except OSError:
            return {}, True
        print(f"⚠️  the reports kept before the start were not a document ({exc}); set aside as "
              f"{p.name}.unreadable, each started game read from its archived report")
        return {}, False
    return (doc if isinstance(doc, dict) else {}), False


def hold(result: dict, reports: list, path, at: str | None = None) -> tuple[list, int]:
    """This build's reports, each started game's the one kept before it
    started, in the board's order; and how many were the kept ones. Every
    report of a game not yet started is kept, as written (its bets too).
    A file that cannot be read or written leaves the reports as built and
    says so.

    A started game the file does not hold is rebuilt from its archived report
    where there is one (`_from_archive`), and kept in the file again. A file
    that is there and cannot be read is not written over this build: an empty
    read would lose every started game it holds (step AEA)."""
    LAST.clear()
    try:
        from .reportlog import _write, game_key, when_words
        utc, et = stamps(at)
        data, unreadable = _read_kept(path)
        games = data.get("games") if isinstance(data.get("games"), dict) else {}
        fresh: dict = {}
        for r in reports or []:
            if isinstance(r, dict):
                fresh.setdefault(_key_of_report(r), []).append(r)
        board = [g for g in (result or {}).get("games") or []
                 if isinstance(g, dict) and g.get("home") and g.get("away")]
        seen: dict = {}
        for g in board:
            seen[game_key(g)] = seen.get(game_key(g), 0) + 1
        out, n, on_board = [], 0, set(seen)
        restored = lost = 0
        for g in board:
            k = game_key(g)
            mine = fresh.get(k) or []
            r = mine.pop(0) if mine else None
            if seen[k] > 1:
                # A doubleheader's two games share a key: each as built, neither kept.
                if r is not None:
                    out.append(r)
                continue
            if started(g, utc):
                rec = games.get(k)
                if not (isinstance(rec, dict) and isinstance(rec.get("report"), dict)):
                    rec = _from_archive(path, g)
                    if rec is not None:
                        games[k] = rec
                        restored += 1
                if isinstance(rec, dict) and isinstance(rec.get("report"), dict):
                    words = str(rec.get("words") or "") or f"{when_words(str(rec.get('at') or ''))} ET"
                    out.append(dict(copy.deepcopy(rec["report"]), kept=words))
                    _restore(result, g, rec, words)
                    n += 1
                elif r is not None:
                    out.append(r)
                    lost += 1
                continue
            if r is not None:
                games[k] = {"at": et, "report": copy.deepcopy(r),
                            **({"parlays": gp} if (gp := parlays_for(result, g)) else {}),
                            **({"picks": pk} if (pk := picks_for(result, g)) else {})}
                out.append(r)
        # A report whose game the board's list does not name stays, after the rest.
        out += [r for rest in fresh.values() for r in rest]
        today = _dt.date.fromisoformat(et[:10])
        for k in list(games):
            if k in on_board:
                continue
            try:
                day = _dt.date.fromisoformat(k.rsplit("|", 1)[-1])
            except ValueError:
                games.pop(k)
                continue
            if (today - day).days > KEEP_DAYS:
                games.pop(k)
        if not unreadable:
            _write(path, {"games": games})
        LAST.update(kept=n, restored=restored, lost=lost)
        if isinstance(result, dict):
            # Counts only (no pick, no ticket): the heartbeat reads them off the board (launch._board_counts).
            result[REPORT_KEEP_KEY] = {k: v for k, v in LAST.items() if v} or {"kept": 0}
        return out, n
    except Exception as exc:                                 # noqa: BLE001
        print(f"⚠️  reports as written before the start not kept ({type(exc).__name__}: {exc})")
        return list(reports or []), 0
