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


def hold(result: dict, reports: list, path, at: str | None = None) -> tuple[list, int]:
    """This build's reports, each started game's the one kept before it
    started, in the board's order; and how many were the kept ones. Every
    report of a game not yet started is kept, as written (its bets too).
    A file that cannot be read or written leaves the reports as built and
    says so."""
    try:
        from .reportlog import _write, game_key, read, when_words
        utc, et = stamps(at)
        data = read(path)
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
                if isinstance(rec, dict) and isinstance(rec.get("report"), dict):
                    out.append(dict(copy.deepcopy(rec["report"]),
                                    kept=f"{when_words(str(rec.get('at') or ''))} ET"))
                    n += 1
                elif r is not None:
                    out.append(r)
                continue
            if r is not None:
                games[k] = {"at": et, "report": copy.deepcopy(r)}
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
        _write(path, {"games": games})
        return out, n
    except Exception as exc:                                 # noqa: BLE001
        print(f"⚠️  reports as written before the start not kept ({type(exc).__name__}: {exc})")
        return list(reports or []), 0
