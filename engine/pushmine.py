"""Alerts that are yours: a watch that fired, and your ticket — on, one leg
left, settled.

    python3 -m engine.pushmine          # what is queued and who asked, sending nothing

Ethan, 2026-10-24: "build everything ... including all the ideas" — docs/
IDEAS.md 9 and 10, the two features the betting apps lead with (Action's
Line Watcher, a game-on alert for your own bet). engine/pushalerts sends
everybody the same two lines; this sends one member the lines about them.

WATCHES (topic "watches"). The Alerts page already matches a member's
player, team and edge watches against the feed (engine/alerts). A watch
that catches something new now knocks their phones too: "3 new on your
watches — on Ja'Marr Chase and any edge at or above 6%." The feed is a paid
file, so only a member the site's own gate lets read it is told; the words
are the member's own watches and a count, never the pick — the Alerts page
says what moved. A member's first look starts from now, not from the whole
feed window. Quiet hours (pushalerts.QUIET) hold these; what fired in the
night is one alert at nine.

YOUR BETS (topic "bets"). A saved slip is a My Bets entry the box already
grades every minute (engine/slipwatch), so it says:
  on        the first of its games is live
  last      it is down to the leg that decides it (the moment the hedge is
            worth opening)
  settled   the box score settled it: won, lost or pushed
Each once per slip, from slipwatch's own pass. These are the member's own
ticket, so they go at any hour: a game that ends at one in the morning is
the game they are watching. A bet logged by hand has no games to follow and
is not one of them.

BIG MOMENTS (topic "clutch"). A play rated 8.5 or more by engine/
playmoments, or any walk-off, in a game of a team the account follows or
by a player it follows: the score and who did it, a tap into the game.
Public facts, so anyone who follows gets it; quiet hours hold it and its
twenty minutes run out, so a moment from the night is never sent at nine.

FINAL SCORES (topic "finals", engine/finals). When a game of a team the
account follows, or with a player it follows in the box, goes final: the
score, the play of the game and the best line, once, and only while the
final is fresh.

WHAT TRAVELS AND WHERE IT WAITS. A message is queued here (`push_mine`,
beside the accounts) and sent by `flush`; a phone's service worker then asks
POST /api/push/latest what to say, and `pushalerts.latest_for` reads the
member's own queue with the shared one, newest first. The iPhone app's
alerts carry the words themselves (APNs). Only a phone signed in when it
subscribed carries the member's alerts — signing out on it detaches it
(server._push_post), so a shared phone stops showing the last person's
tickets.

Run from launch._slip_watcher's minute, after the slip watch, with the
server's own gate. Standard library only.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from engine import alerts as AL
from engine import pushalerts as PA
from engine import webpush

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
TOPICS = PA.PERSONAL
#: Wanted by every signed-in phone, never a switch (pushalerts.ACCOUNT: a
#: member's own membership notices, engine/lifecycle).
IMPLIED = (PA.ACCOUNT,)
#: The watches look at most this often (the feed changes on a build, minutes apart).
WATCH_EVERY_S = 120
#: The lineup alert's pass (engine/lineupalerts) looks at most this often.
LINEUP_EVERY_S = 15 * 60
#: How long each kind stays worth showing. A "your game is on" an hour late
#: is noise; a settled ticket is still news the next morning.
TTL_S = {"watches": 12 * 3600, "on": 30 * 60, "last": 3 * 3600, "settled": 12 * 3600, "clutch": 20 * 60,
         "finals": 3 * 3600, "lineup": 18 * 3600, "week": 14 * 3600,
         # Karma (engine/karma.alerts_pass): the streak nudge is only worth
         # sending before midnight; a week's trophy is still news that day.
         "karma": 3 * 3600, "karma_week": 12 * 3600,
         # A game chat's mention or reply (engine/gamechat): the game is
         # still on for a couple of hours at most.
         "mentions": 2 * 3600,
         # A game's reminder (engine/gamechat remind): worth it until the game is on.
         "reminders": 20 * 60,
         # The pick'em's push before picks lock (engine/pickem): until they do.
         "pickem": 3 * 3600,
         # The pick'em's Tuesday line on the week just over: that day.
         "pickem_recap": 12 * 3600,
         # A followed team's game about to start (engine/kickoffs): until it does.
         "kickoff": 15 * 60,
         # "While you were away" (engine/engagement): the evening it went.
         "away": 3 * 3600,
         # The research's bet-linked alerts (engine/slipwatch.moments): close
         # to hitting while it still is, a line move until the game starts,
         # a close finish for its last minutes.
         "close": 20 * 60, "lines": 3 * 3600, "closegame": 15 * 60, "news": 6 * 3600, "today": 8 * 3600,
         # A notice about the member's own membership (engine/lifecycle):
         # held overnight, still worth it the next morning.
         "account": 20 * 3600}
#: Held through quiet hours where the member is; the rest go at any hour
#: (their own bet, a game they asked to be told about, a final).
HELD = ('watches', 'clutch', 'lineup', 'karma', 'mentions', 'away', 'lines', 'closegame', 'news', 'account')
KEEP_PER_USER = 12
KEEP_S = 24 * 3600
_looked = {"watches": 0.0, "lineup": 0.0, "week": 0.0, "karma": 0.0, "pickem": 0.0, "away": 0.0, "news": 0.0,
           "today": 0.0, "lifecycle": 0.0}
#: Injury news (engine/newsalerts) looks this often; the boards change every half hour.
NEWS_EVERY_S = 5 * 60
#: Karma alerts' pass looks at most this often.
KARMA_EVERY_S = 15 * 60
#: Your week's pass looks at most this often, and only on a Monday morning.
WEEK_EVERY_S = 30 * 60


def ensure_tables(conn) -> None:
    PA.ensure_tables(conn)
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS push_mine (
        user_id INTEGER NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
        title TEXT NOT NULL, body TEXT NOT NULL, url TEXT NOT NULL,
        at REAL NOT NULL, until REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, id));
      CREATE TABLE IF NOT EXISTS push_watch_seen (
        user_id INTEGER PRIMARY KEY, ts TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS push_activities (
        user_id INTEGER NOT NULL, bet_id TEXT NOT NULL, token TEXT NOT NULL,
        last TEXT NOT NULL DEFAULT '', started REAL NOT NULL,
        PRIMARY KEY (user_id, bet_id));
      CREATE TABLE IF NOT EXISTS push_clutch_seen (
        game TEXT NOT NULL, play TEXT NOT NULL, at REAL NOT NULL,
        PRIMARY KEY (game, play));
      CREATE TABLE IF NOT EXISTS push_lineup_leagues (
        user_id INTEGER PRIMARY KEY, league_id TEXT NOT NULL, sleeper_user TEXT NOT NULL,
        at REAL NOT NULL);
    """)
    conn.commit()


def asked(conn, user_id, topic: str) -> bool:
    """Does any phone signed in as this member want this topic? Every one
    of them wants a notice about their own membership (pushalerts.ACCOUNT)."""
    ensure_tables(conn)
    for (topics,) in conn.execute("SELECT topics FROM push_subs WHERE user_id = ?", (int(user_id),)):
        if topic == PA.ACCOUNT or topic in str(topics).split(","):
            return True
    return False


def tell(conn, user_id, msg_id: str, topic: str, title: str, body: str, url: str,
         ttl: str = "", now: float | None = None) -> bool:
    """Queue one message for a member, once ever (its id). False when it was
    queued before or nobody of theirs asked for the topic."""
    if topic not in TOPICS + IMPLIED or not asked(conn, user_id, topic):
        return False
    t = time.time() if now is None else now
    cur = conn.execute("INSERT OR IGNORE INTO push_mine (user_id, id, kind, title, body, url, at, until) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (int(user_id), str(msg_id)[:120], topic, str(title)[:120], str(body)[:240],
                        url if str(url).startswith("/") else "/", t, t + TTL_S.get(ttl or topic, 3600)))
    if cur.rowcount:
        conn.execute("DELETE FROM push_mine WHERE user_id = ? AND id NOT IN (SELECT id FROM push_mine "
                     "WHERE user_id = ? ORDER BY at DESC LIMIT ?)", (int(user_id), int(user_id), KEEP_PER_USER))
    conn.commit()
    return bool(cur.rowcount)


def lineup_remember(conn, user_id, league_id: str, sleeper_user: str, now: float | None = None) -> bool:
    """Keep the Sleeper league a member's desk just opened, for the lineup
    alert (engine/lineupalerts), only while a phone of theirs has "My
    fantasy lineup" on. False (and nothing kept) otherwise."""
    if not user_id or not str(league_id).isdigit() or not str(sleeper_user).isdigit():
        return False
    if not asked(conn, user_id, "lineup"):
        return False
    conn.execute("INSERT INTO push_lineup_leagues (user_id, league_id, sleeper_user, at) VALUES (?,?,?,?) "
                 "ON CONFLICT(user_id) DO UPDATE SET league_id = excluded.league_id, "
                 "sleeper_user = excluded.sleeper_user, at = excluded.at",
                 (int(user_id), str(league_id)[:25], str(sleeper_user)[:25], time.time() if now is None else now))
    conn.commit()
    return True


def lineup_forget(conn) -> int:
    """Forget the league of every account no phone of which has "My fantasy
    lineup" on any more (switched off, signed out, or the phone gone): the
    privacy policy's "within fifteen minutes of your turning it off"."""
    cur = conn.execute("DELETE FROM push_lineup_leagues WHERE user_id NOT IN (SELECT user_id FROM push_subs "
                       "WHERE user_id IS NOT NULL AND (',' || topics || ',') LIKE '%,lineup,%')")
    conn.commit()
    return cur.rowcount


def mine(conn, user_id, now: float | None = None) -> list[dict]:
    """A member's messages still worth showing, oldest first, in
    pushalerts' shape (each with its `at`) — what latest_for reads."""
    if not user_id:
        return []
    t = time.time() if now is None else now
    try:
        rows = conn.execute("SELECT id, kind, title, body, url, at FROM push_mine WHERE user_id = ? "
                            "AND until > ? ORDER BY at", (int(user_id), t)).fetchall()
    except sqlite3.Error:
        return []
    return [{"id": r[0], "kind": r[1], "league": "", "title": r[2], "body": r[3], "url": r[4], "at": r[5]}
            for r in rows]


# --- watches -----------------------------------------------------------------
def _feed(web: Path = WEB) -> list:
    """The feed the Alerts page filters (server._alerts_feed): the paid copy
    when the wall is up. Only read for members the gate lets through."""
    from engine import gate
    path = Path(web) / "data" / "feed.json"
    if gate.enabled():
        path = gate.board_source(path)
    try:
        return (json.loads(path.read_text(encoding="utf-8")) or {}).get("events") or []
    except (OSError, ValueError):
        return []


def watch_line(hits: list) -> tuple[str, str]:
    """``(title, body)`` from the member's own watches: a count and their
    words, never the pick (the Alerts page shows what moved)."""
    why = []
    for h in hits:
        for w in h.get("why") or []:
            if w not in why:
                why.append(w)
    n = len(hits)
    title = f"{n} new on your watches" if n != 1 else "Your watch caught something"
    said = ", ".join(why[:2]) + (f" and {len(why) - 2} more" if len(why) > 2 else "")
    return title, (f"On {said}. " if said else "") + "Open Alerts to see what moved."


def teaser_line(hits: list) -> tuple[str, str]:
    """``(title, body)`` for an account without a plan: a count of the new
    picks on what it follows — no name, no market, no side."""
    n = len(hits)
    return (("Your players are on tonight’s board" if n != 1 else "One of yours is on tonight’s board"),
            f"{n} new pick{'s' if n != 1 else ''} on the teams and players you follow. Members see them.")


def watch_pass(conn, events: list, entitled=None, now: float | None = None) -> int:
    """Queue one alert per account whose watches caught something since
    its last look — a member's in its own words, anybody else's as a count
    (teaser_line). Returns how many were told."""
    from engine import gate
    ensure_tables(conn)
    newest = AL.newest_ts(events)
    told = 0
    users = conn.execute("SELECT DISTINCT s.user_id, u.email FROM push_subs s JOIN users u ON u.id = s.user_id "
                         "WHERE s.user_id IS NOT NULL AND (',' || s.topics || ',') LIKE '%,watches,%'").fetchall()
    for uid, email in users:
        # AN ACCOUNT WITHOUT A PLAN IS TOLD HOW MANY, never who or what
        # (2026-10-25, the free tier: Ethan's "notifications about your
        # favorite players' props being posted", with picks kept for
        # members). The teams and players it follows are its own words;
        # which of them have a pick, and the pick, are the product.
        member = True
        if gate.enabled():
            try:
                member = bool(entitled and entitled(conn, {"id": uid, "email": email}))
            except Exception:                                    # noqa: BLE001
                member = False
        watches = AL.list_watches(conn, uid)
        row = conn.execute("SELECT ts FROM push_watch_seen WHERE user_id = ?", (uid,)).fetchone()
        since = row[0] if row else ""
        if newest and newest > since:
            conn.execute("INSERT INTO push_watch_seen (user_id, ts) VALUES (?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET ts = excluded.ts", (uid, newest))
            conn.commit()
        if not since or not watches:
            continue                              # the first look starts from now
        hits = AL.fired(events, watches, since=since)
        if hits:
            title, body = watch_line(hits) if member else teaser_line(hits)
            told += tell(conn, uid, f"watches:{newest}", "watches", title, body,
                         "/#alerts" if member else "/#paywall", now=now)
    return told


# --- your bets (called from engine/slipwatch's pass) -------------------------
def _money(x) -> str:
    try:
        return f"${float(x or 0):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def _noun(legs) -> str:
    """A ticket of one leg is a bet, not a parlay: a straight bet tracked
    from Ask (2026-10-27) or a single read off a screenshot. A count we were
    not handed is a parlay, as every saved slip was before."""
    return "bet" if legs == 1 else "parlay"


def bet_on(conn, user_id, bet_id: str, where: str, now: float | None = None, legs: int = 0) -> bool:
    return tell(conn, user_id, f"bets:on:{bet_id}", "bets", f"Your {_noun(legs)} is on",
                (f"{where[:150]} — " if where else "") + "follow it on the Live tab.", "/#live", ttl="on", now=now)


def bet_last(conn, user_id, bet_id: str, leg: str, now: float | None = None) -> bool:
    return tell(conn, user_id, f"bets:last:{bet_id}", "bets", "Down to the last leg",
                f"{leg[:100] or 'One leg'} decides your parlay — the hedge and the cash-out check are on the Live tab.",
                "/#live", ttl="last", now=now)


# --- your week (topic "bets", docs/IDEAS.md round three) ----------------------
def week_summary(bets, start: str, end: str) -> dict | None:
    """Last week's settled bets in My Bets (dated start..end inclusive, ISO):
    the record, what it made or lost, and the best win. None when nothing
    settled that week."""
    w = l = p = 0
    net = 0.0
    best = None
    for b in bets if isinstance(bets, list) else []:
        if not isinstance(b, dict) or not (start <= str(b.get("date") or "")[:10] <= end):
            continue
        res = str(b.get("result") or "")
        try:
            stake = float(b.get("stake") or 0)
            o = float(b.get("odds"))
            dec = 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
        except (TypeError, ValueError, ZeroDivisionError):
            stake, dec = 0.0, 1.0
        if res in ("win", "won"):
            w += 1
            gain = stake * (dec - 1)
            net += gain
            if best is None or gain > best[0]:
                best = (gain, str(b.get("desc") or "")[:70])
        elif res in ("loss", "lost"):
            l += 1
            net -= stake
        elif res in ("push", "void"):
            p += 1
    if not (w or l or p):
        return None
    return {"w": w, "l": l, "p": p, "net": round(net, 2), "best": best[1] if best else ""}


def week_clv(conn, user_id, bets, start: str, end: str) -> str:
    """The research's weekly CLV report, in a line: how the week's saved
    slips' prices did against their closes on average, and the best-priced
    one (engine/betclv) — or "" when no close was seen."""
    from engine import betclv as BC
    got = []
    for b in bets if isinstance(bets, list) else []:
        if not isinstance(b, dict) or b.get("src") != "slip" or not (start <= str(b.get("date") or "")[:10] <= end):
            continue
        legs = b.get("legs") if isinstance(b.get("legs"), list) else []
        c = BC.ticket(conn, user_id, str(b.get("id")), legs=len(legs), payout=b.get("odds"))["clv"]
        if c is not None:
            got.append((c, str(b.get("desc") or "")[:60]))
    if not got:
        return ""
    avg = sum(c for c, _ in got) / len(got)
    best = max(got)
    line = f"Your prices {BC.words(avg)} on average ({len(got)} bet{'' if len(got) == 1 else 's'})."
    if best[0] > 0 and best[1] and len(got) > 1:
        line += f" Best price: {best[1]}."
    return line


def week_pass(conn, now: float | None = None) -> int:
    """Monday from nine in the morning, Eastern: each member whose phone gets
    their bets hears last week's record, what it made or lost and the best
    win, once a week (the message id is the week)."""
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    t = time.time() if now is None else now
    et = datetime.fromtimestamp(t, ZoneInfo("America/New_York"))
    if et.weekday() != 0 or not 9 <= et.hour < 21:
        return 0
    start = (et - timedelta(days=7)).date().isoformat()
    end = (et - timedelta(days=1)).date().isoformat()
    year, week, _ = (et - timedelta(days=7)).isocalendar()
    users = [r[0] for r in conn.execute(
        "SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
        "AND (',' || topics || ',') LIKE '%,bets,%'").fetchall()]
    told = 0
    for uid in users:
        row = conn.execute("SELECT payload FROM user_data WHERE user_id=? AND section='mybets'", (int(uid),)).fetchone()
        try:
            data = json.loads(row[0]) if row is not None else None
        except (ValueError, TypeError):
            data = None
        rows = (data or {}).get("rows") if isinstance(data, dict) else None
        got = week_summary(rows, start, end)
        if not got:
            continue
        rec = f"{got['w']}–{got['l']}" + (f"–{got['p']}" if got["p"] else "")
        sign = "+" if got["net"] >= 0 else "−"
        title = f"Your week: {rec}, {sign}{_money(abs(got['net']))}"
        clv = week_clv(conn, uid, rows, start, end)
        body = (f"Best win: {got['best']}. " if got["best"] else "") + (clv + " " if clv else "") + "My Bets has every one."
        told += bool(tell(conn, uid, f"bets:week:{year}-W{week:02d}", "bets", title, body, "/#mybets",
                          ttl="week", now=t))
    return told


def bet_soon(conn, user_id, bet_id: str, game: str, where: str, mins: int, now: float | None = None) -> bool:
    """A game of the member's ticket starts in about ten minutes (the
    research's "Your game starts", T-10), once a ticket and game."""
    return tell(conn, user_id, f"bets:soon:{bet_id}:{game}", "bets",
                f"Your bet’s game starts in {mins} minute{'' if mins == 1 else 's'}",
                f"{where}. Your ticket, live, on the Live tab." if where else "Your ticket, live, on the Live tab.",
                "/#live", ttl="on", now=now)


def bet_close(conn, user_id, bet_id: str, leg: str, where: str, now: float | None = None) -> bool:
    """A live leg within a unit of its number, or 85% likely (the
    research's "Prop close to hitting"), once a ticket."""
    return tell(conn, user_id, f"bets:close:{bet_id}", "bets", f"Close: {leg}"[:120],
                (where or "Live now") + ". Your ticket and the hedge are on the Live tab.", "/#live",
                ttl="close", now=now)


def bet_line(conn, user_id, bet_id: str, leg: str, took, now_odds, book: str, move: float,
             now: float | None = None) -> bool:
    """Before the start, the best price now 2%+ (implied) from the one the
    member took — either way, said which (topic "lines", their switch)."""
    def am(o):
        try:
            v = float(o)
        except (TypeError, ValueError):
            return str(o)
        return f"+{v:g}" if v > 0 else f"−{abs(v):g}"
    way = "your way" if move > 0 else "against you"
    return tell(conn, user_id, f"lines:{bet_id}", "lines", f"The line moved {way}: {leg}"[:120],
                f"You took {am(took)}; the best now is {am(now_odds)}{' at ' + book if book else ''}"
                + (" — you beat the market." if move > 0 else ". Information, not advice."),
                "/#mybets", ttl="lines", now=now)


def bet_line_points(conn, user_id, bet_id: str, leg: str, line, main, now: float | None = None) -> bool:
    return tell(conn, user_id, f"lines:{bet_id}", "lines", f"The line moved: {leg}"[:120],
                f"You have {line}; the main line is now {main}.", "/#mybets", ttl="lines", now=now)


def bet_close_game(conn, user_id, bet_id: str, game: str, where: str, now: float | None = None) -> bool:
    """A game on the member's ticket in its last minutes, within one score
    (topic "closegame"), once a game."""
    return tell(conn, user_id, f"closegame:{game}", "closegame", f"Close game: {where}"[:120],
                "Final minutes, within one score — and you have a bet on it.", "/#live", ttl="closegame", now=now)


def bet_settled(conn, user_id, bet: dict, done: dict, now: float | None = None) -> bool:
    """Won (and what it pays back), lost, or pushed — the result slipwatch
    just wrote to the member's My Bets — and, where every leg's close was
    seen, whether the price beat it (engine/betclv)."""
    res = done.get("result")
    stake = bet.get("stake")
    noun = _noun(len(bet.get("legs") or []) if isinstance(bet.get("legs"), list) else 0)
    if res == "win":
        try:
            o = float(done.get("paid_odds") or bet.get("odds"))
            dec = 1 + o / 100 if o > 0 else 1 + 100 / abs(o)
            body = f"{_money(float(stake) * dec)} back on {_money(stake)}. My Bets has it graded."
        except (TypeError, ValueError, ZeroDivisionError):
            body = "My Bets has it graded."
        title = f"Your {noun} won"
    elif res == "loss":
        title, body = f"Your {noun} lost", "Graded off the box score. My Bets has it."
    elif res == "push":
        title, body = f"Your {noun} pushed", f"Your {_money(stake)} comes back. My Bets has it."
    else:
        return False
    try:
        from engine import betclv as BC
        n = len(bet.get("legs") or []) if isinstance(bet.get("legs"), list) else None
        said = BC.words(BC.ticket(conn, user_id, str(bet.get("id")), legs=n, payout=bet.get("odds"))["clv"])
        if said:
            body = f"{body} Your price {said}."
    except Exception:                                             # noqa: BLE001 — the result goes without it
        pass
    return tell(conn, user_id, f"bets:settled:{bet.get('id')}", "bets", title, body, "/#mybets",
                ttl="settled", now=now)


# --- the lock screen (a Live Activity in the iOS app) ------------------------
#
# The iOS app's "On my lock screen" (deploy/ios/native, ParlayActivity)
# starts a Live Activity for a saved parlay and hands the box the activity's
# own push token (POST /api/push/activity). The slip watch's pass then
# updates it when the ticket's standing changes and ends it when the box
# score settles it. What it shows is the member's ticket and the public
# score — never our chance, which is the paid half.

#: Activities a member can have running at once (Apple allows a handful).
MAX_ACTIVITIES = 5
#: Apple ends an activity after eight hours; the box forgets it after twelve.
ACTIVITY_S = 12 * 3600


def activity_add(conn, user_id, bet_id: str, token: str, now: float | None = None) -> tuple[int, dict]:
    ensure_tables(conn)
    token, bet_id = str(token or "").strip(), str(bet_id or "").strip()[:40]
    if not (8 <= len(token) <= 200 and all(c in "0123456789abcdefABCDEF" for c in token)) or not bet_id:
        return 400, {"error": "that is not a lock-screen token"}
    t = time.time() if now is None else now
    conn.execute("DELETE FROM push_activities WHERE started < ?", (t - ACTIVITY_S,))
    n = conn.execute("SELECT COUNT(*) FROM push_activities WHERE user_id = ? AND bet_id != ?",
                     (int(user_id), bet_id)).fetchone()[0]
    if n >= MAX_ACTIVITIES:
        return 400, {"error": f"{MAX_ACTIVITIES} on the lock screen is the most"}
    conn.execute("INSERT INTO push_activities (user_id, bet_id, token, last, started) VALUES (?,?,?,'',?) "
                 "ON CONFLICT(user_id, bet_id) DO UPDATE SET token = excluded.token, started = excluded.started",
                 (int(user_id), bet_id, token, t))
    conn.commit()
    return 200, {"ok": True}


def activity_remove(conn, user_id, bet_id: str) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("DELETE FROM push_activities WHERE user_id = ? AND bet_id = ?", (int(user_id), str(bet_id)))
    conn.commit()
    return 200, {"ok": True}


def activity_state(card: dict) -> dict:
    """The lock screen's numbers (the iOS app's ContentState, field for
    field): legs won of legs, legs left, the leg that decides it and where
    it stands. No chance — the paid half stays on the Live tab."""
    from engine import slipwatch as SW
    legs = (card or {}).get("legs") or []
    now = (card or {}).get("now") or {}
    status = str(now.get("status") or "open")
    left = int(now.get("left") or 0) if status == "open" else 0
    leg = SW.open_leg(card or {}) if status == "open" else None
    title = {"won": "Won", "lost": "Lost"}.get(status) or (
        "One leg left" if left == 1 else f"{left} legs left" if left else "Waiting on the first game")
    return {"title": title, "status": status, "legs": len(legs), "left": left,
            "won": sum(1 for l in legs if (l.get("live") or {}).get("result") == "won"),
            "leg": SW.leg_name(card or {})[:60] if leg else "",
            "line": (SW.where(leg) if leg else "")[:90]}


def activity_update(conn, user_id, bet_id: str, card: dict, live=None, cfg=None, now: float | None = None) -> int:
    """Send the activity its new standing when it changed; the status, or 0
    when there was nothing to send (no activity, no change, no Apple key)."""
    from engine import webpush as W
    row = conn.execute("SELECT token, last FROM push_activities WHERE user_id = ? AND bet_id = ?",
                       (int(user_id), str(bet_id))).fetchone() if _has_activities(conn) else None
    if row is None:
        return 0
    state = activity_state(card)
    blob = json.dumps(state, sort_keys=True)
    if blob == row[1]:
        return 0
    cfg = W.apns_config() if cfg is None else cfg
    if not cfg:
        return 0
    alert = {"title": "Down to the last leg", "body": f"{state['leg']} decides it."} \
        if state["left"] == 1 and '"left": 1' not in row[1] else None
    code = (live or W.apns_live)(row[0], state, cfg, event="update", alert=alert, now=now)
    if code in (200, 201):
        conn.execute("UPDATE push_activities SET last = ? WHERE user_id = ? AND bet_id = ?",
                     (blob, int(user_id), str(bet_id)))
    elif code in (400, 404, 410):
        conn.execute("DELETE FROM push_activities WHERE user_id = ? AND bet_id = ?", (int(user_id), str(bet_id)))
    conn.commit()
    return code


def activity_end(conn, user_id, bet_id: str, done: dict, live=None, cfg=None, now: float | None = None) -> int:
    """The ticket settled: the activity's last word, then it is forgotten."""
    from engine import webpush as W
    row = conn.execute("SELECT token, last FROM push_activities WHERE user_id = ? AND bet_id = ?",
                       (int(user_id), str(bet_id))).fetchone() if _has_activities(conn) else None
    if row is None:
        return 0
    try:
        state = json.loads(row[1]) if row[1] else {}
    except ValueError:
        state = {}
    res = done.get("result")
    state.update({"title": {"win": "Won", "loss": "Lost", "push": "Pushed"}.get(res, "Settled"),
                  "status": {"win": "won", "loss": "lost", "push": "push"}.get(res, "open"),
                  "left": 0, "leg": "", "line": "Settled off the box score"})
    for k, v in (("legs", 0), ("won", 0)):
        state.setdefault(k, v)
    cfg = W.apns_config() if cfg is None else cfg
    code = (live or W.apns_live)(row[0], state, cfg, event="end", now=now) if cfg else 0
    conn.execute("DELETE FROM push_activities WHERE user_id = ? AND bet_id = ?", (int(user_id), str(bet_id)))
    conn.commit()
    return code


def _has_activities(conn) -> bool:
    try:
        return conn.execute("SELECT 1 FROM push_activities LIMIT 1").fetchone() is not None
    except sqlite3.Error:
        return False


# --- clutch: the big moment in a game you follow ------------------------------
# Ethan, 2026-10-25: "create things I've never even thought of." Every play
# on a live game's deep file already carries its moment (engine/playmoments:
# a 0-10 rating from the win chance it moved, and a tie, a lead or a
# walk-off). A play this big in a game of a team you follow, or by a player
# you follow, knocks your phone with the score and who did it, and the tap
# opens the game. The score is public, so this is anybody's who follows,
# member or not; it carries no pick.
#: A play rated this high is a moment (about a 35-point swing in the win
#: chance where the feed has one); a walk-off always is.
CLUTCH_MIN = 8.5
#: A deep file not written for this long is not a game in progress.
CLUTCH_FRESH_S = 15 * 60
#: The most moments one game sends one account (a wild finish is one tap
#: per swing, not a stream).
CLUTCH_PER_GAME = 4
CLUTCH_KEEP_S = 2 * 86400
SWING_WORD = {"walkoff": "Walk-off", "go_ahead": "Go-ahead", "tying": "Game-tying"}
_clutch_mtimes: dict = {}


def clutch_plays(doc: dict) -> list:
    """``[(key, play)]`` for each play on a deep file big enough to tell."""
    if doc.get("league") == "mlb":
        rows = [e for e in doc.get("events") or [] if isinstance(e, dict) and e.get("kind") == "atbat"]
        key = (lambda r: f"ab{r.get('at_bat')}")
    else:
        rows = [p for p in doc.get("plays") or [] if isinstance(p, dict)]
        key = (lambda r: str(r.get("id") or f"{r.get('period')}|{r.get('clock')}|{r.get('event')}"))
    out = []
    for r in rows:
        try:
            big = float(r.get("rating") or 0) >= CLUTCH_MIN
        except (TypeError, ValueError):
            big = False
        if big or r.get("swing") == "walkoff":
            out.append((key(r), r))
    return out


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def clutch_line(doc: dict, play: dict) -> tuple:
    """``(title, body)``: the moment, the score after it, who and when."""
    home, away = str(doc.get("home") or ""), str(doc.get("away") or "")
    a, h = play.get("away_score"), play.get("home_score")
    score = f"{away} {a}\u2013{h} {home}" if isinstance(a, int) and isinstance(h, int) else f"{away} at {home}"
    who = play.get("batter") or next(iter(play.get("players") or []), "") or ""
    if play.get("inning"):
        when = f"{'bottom' if play.get('half') == 'B' else 'top'} of the {_ordinal(int(play['inning']))}"
    elif play.get("period"):
        per = int(play["period"])
        lg = doc.get("league")
        when = (f"overtime" if (lg == "nhl" and per > 3) or (lg != "nhl" and per > 4)
                else f"period {per}" if lg == "nhl" else f"Q{per}")
        if play.get("clock"):
            when += f", {play['clock']}"
    else:
        when = ""
    what = str(play.get("event") or "Big play")
    try:
        rated = f" Rated {float(play.get('rating')):.1f}."
    except (TypeError, ValueError):
        rated = ""
    title = f"{SWING_WORD.get(play.get('swing'), 'Big moment')}: {score}"
    body = ", ".join(x for x in (f"{who} \u2014 {what}" if who else what, when) if x) + "." + rated
    return title, body


def _follows(watches: list, doc: dict, play: dict, leagues: dict | None = None) -> bool:
    sides = {str(doc.get("home") or "").upper(), str(doc.get("away") or "").upper()} - {""}
    names = [play.get("batter"), play.get("pitcher")] + list(play.get("players") or [])
    folded = {AL._fold(n) for n in names if n}
    for w in watches:
        if w.get("kind") == "team" and AL.team_hit(w.get("value"), doc.get("league"), sides, leagues):
            return True
        if w.get("kind") == "player" and AL._fold(w.get("value")) in folded:
            return True
    return False


def clutch_pass(conn, pbp_dir: Path | None = None, now: float | None = None) -> int:
    """Tell everyone following a side or a player in a new big moment.
    THE FIRST LOOK AT A GAME IS ITS BASELINE: the moments already on it
    when this pass first reads it are marked told, not sent, so a restart
    in the fourth quarter does not replay the first three. Returns how
    many were told."""
    ensure_tables(conn)
    t = time.time() if now is None else now
    users = conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL "
                         "AND (',' || topics || ',') LIKE '%,clutch,%'").fetchall()
    conn.execute("DELETE FROM push_clutch_seen WHERE at < ?", (t - CLUTCH_KEEP_S,))
    if not users:
        conn.commit()
        return 0
    watching = {uid: AL.list_watches(conn, uid) for (uid,) in users}
    watching = {u: w for u, w in watching.items() if w}
    leagues = {u: AL.team_leagues(conn, u) for u in watching}
    told = 0
    base = Path(pbp_dir) if pbp_dir else WEB / "data" / "pbp"
    for path in sorted(base.glob("*.json")) if base.is_dir() else []:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if t - mtime > CLUTCH_FRESH_S or _clutch_mtimes.get(str(path)) == mtime:
            continue
        try:
            doc = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        _clutch_mtimes[str(path)] = mtime
        game = f"{doc.get('league')}_{doc.get('event_id')}"
        first = conn.execute("SELECT 1 FROM push_clutch_seen WHERE game = ? LIMIT 1", (game,)).fetchone() is None
        plays = clutch_plays(doc)
        seen = {r[0] for r in conn.execute("SELECT play FROM push_clutch_seen WHERE game = ?", (game,))}
        # The game's own row, so a game with no moment yet still has its baseline.
        conn.execute("INSERT OR IGNORE INTO push_clutch_seen (game, play, at) VALUES (?, '', ?)", (game, t))
        for key, play in plays:
            if key in seen:
                continue
            conn.execute("INSERT OR IGNORE INTO push_clutch_seen (game, play, at) VALUES (?, ?, ?)", (game, key, t))
            if first:
                continue
            title, body = clutch_line(doc, play)
            url = f"/#pbp/{doc.get('league')}/{doc.get('event_id')}"
            for uid, watches in watching.items():
                if not _follows(watches, doc, play, leagues.get(uid)):
                    continue
                sent = conn.execute("SELECT COUNT(*) FROM push_mine WHERE user_id = ? AND id LIKE ?",
                                    (uid, f"clutch:{game}:%")).fetchone()[0]
                if sent < CLUTCH_PER_GAME:
                    told += tell(conn, uid, f"clutch:{game}:{key}", "clutch", title, body, url, now=t)
        conn.commit()
    return told


# --- sending -----------------------------------------------------------------
def flush(conn, knock=webpush.knock, apns=webpush.apns_send, vapid: dict | None = None, apns_cfg=None,
          now: float | None = None, quiet: bool | None = None) -> dict:
    """Send what is queued: each member's phones that want each message.
    Watches and big moments wait out quiet hours (a moment's twenty
    minutes run out first, so the night's are dropped, not sent at nine);
    a member's bets do not. Every message is
    tried once (a phone that misses it reads it from latest_for)."""
    ensure_tables(conn)
    t = time.time() if now is None else now
    conn.execute("UPDATE push_mine SET sent = 1 WHERE sent = 0 AND until <= ?", (t,))
    # Kept a day at most (the privacy policy, 2.7): long enough for a late
    # knock to read it, no longer.
    conn.execute("DELETE FROM push_mine WHERE at < ?", (t - KEEP_S,))
    held = " AND kind NOT IN (" + ", ".join(f"'{k}'" for k in HELD) + ")" if quiet else ""
    rows = conn.execute("SELECT user_id, id, kind, title, body, url FROM push_mine WHERE sent = 0" + held +
                        " ORDER BY at").fetchall()
    if quiet is None:
        # QUIET HOURS WHERE THE MEMBER IS (pushalerts.quiet_for: their
        # Settings' time zone, Eastern when they named none). What waits
        # stays unsent and goes when their morning comes, or runs out.
        late: dict = {}
        rows = [r for r in rows if r[2] not in HELD
                or not late.setdefault(r[0], PA.quiet_for(conn, r[0], t))]
    stats = {"messages": len(rows), "sent": 0, "gone": 0, "failed": 0, "skipped_apns": 0}
    if not rows:
        conn.commit()
        return stats
    by_user: dict = {}
    for uid, mid, kind, title, body, url in rows:
        by_user.setdefault(uid, []).append({"id": mid, "kind": kind, "league": "", "title": title,
                                            "body": body, "url": url})
    k = vapid or webpush.keys()
    cfg = webpush.apns_config() if apns_cfg is None else apns_cfg
    today, paid = PA.eastern_day(t), PA.paid_ids(conn)
    from engine import limits as LM
    limited = LM.reached(conn, t)
    for uid, msgs in by_user.items():
        # Their own weekly limit reached (engine/limits): the promotional
        # kinds are dropped, not held for Monday.
        if uid in limited:
            stats["limited"] = stats.get("limited", 0) + sum(m["kind"] in LM.PROMO for m in msgs)
            send_now = [m for m in msgs if m["kind"] not in LM.PROMO]
        else:
            send_now = msgs
        for endpoint, kind, topics, fails, until, day, day_n in conn.execute(
                "SELECT endpoint, kind, topics, fails, paused_until, day, day_n FROM push_subs WHERE user_id = ?",
                (uid,)).fetchall():
            want = [m for m in send_now if PA.wants(topics, "", m)]
            if not want:
                continue
            # Paused (Alerts → Pause), or the day's alerts all used
            # (pushalerts.DAY_CAP): this phone hears none of these.
            left = PA.room_today(day, day_n, today, uid, paid)
            if PA.paused(until, t) or left <= 0:
                stats["held"] = stats.get("held", 0) + 1
                continue
            if kind == "apns":
                if not cfg:
                    stats["skipped_apns"] += 1
                    continue
                want = want[:left]
                codes = [apns(endpoint, m, cfg) for m in want]
            else:
                codes = [knock(endpoint, k, topic=want[-1]["id"].replace(":", "-")[:32])]
            if all(c in (200, 201) for c in codes):
                stats["sent"] += 1
                PA.spend(conn, endpoint, len(want) if kind == "apns" else 1, today)
                PA.counted(want)
            elif any(c in (404, 410) for c in codes) or (kind == "apns" and 400 in codes):
                stats["gone"] += 1
                conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
            else:
                stats["failed"] += 1
                conn.execute("UPDATE push_subs SET fails = fails + 1 WHERE endpoint = ?", (endpoint,))
                if fails + 1 >= PA.MAX_FAILS:
                    conn.execute("DELETE FROM push_subs WHERE endpoint = ?", (endpoint,))
        conn.executemany("UPDATE push_mine SET sent = 1 WHERE user_id = ? AND id = ?",
                         [(uid, m["id"]) for m in msgs])
    conn.commit()
    return stats


def run_once(entitled=None, log=print, connect=None, now: float | None = None, web: Path = WEB,
             **flush_kw) -> dict:
    """The minute's pass: the watches (every WATCH_EVERY_S), then send what
    is queued — the slip watch's tickets included. Costs one small query
    when nobody has asked for either."""
    from engine import modelstate
    import os
    t = time.time() if now is None else now
    if connect is None:
        if os.environ.get(modelstate.ENV_VAR):
            return {}
        from engine import accounts
        connect = accounts.connect
    conn = connect()
    try:
        ensure_tables(conn)
        lineup_forget(conn)
        if not conn.execute("SELECT 1 FROM push_subs WHERE user_id IS NOT NULL LIMIT 1").fetchone():
            return {"messages": 0}
        told = 0
        if t - _looked["watches"] >= WATCH_EVERY_S:
            _looked["watches"] = t
            told = watch_pass(conn, _feed(web), entitled=entitled, now=t)
        if t - _looked["lineup"] >= LINEUP_EVERY_S:
            _looked["lineup"] = t
            from engine import lineupalerts as _la
            try:
                told += _la.lineup_pass(conn, now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  lineup alerts: {type(exc).__name__}: {exc}")
        if t - _looked["week"] >= WEEK_EVERY_S:
            _looked["week"] = t
            try:
                told += week_pass(conn, now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  your week: {type(exc).__name__}: {exc}")
        if t - _looked["karma"] >= KARMA_EVERY_S:
            _looked["karma"] = t
            from engine import karma as _karma
            try:
                told += _karma.alerts_pass(conn, now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  karma alerts: {type(exc).__name__}: {exc}")
        # The pick'em (engine/pickem): its grading, and the push before picks lock.
        if t - _looked["pickem"] >= KARMA_EVERY_S:
            _looked["pickem"] = t
            from engine import pickem as _pk
            try:
                told += _pk.alerts_pass(conn, now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  pick'em: {type(exc).__name__}: {exc}")
            # Each open pick's latest market price: the last before kickoff
            # is its close (the "beat the close" table).
            try:
                _pk.note_closes(conn, now=t, data_dir=Path(web) / "data")
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  pick'em closes: {type(exc).__name__}: {exc}")
        # Phone first (engine/lifecycle): renewals of the longer plans, and
        # the recaps for a paying member gone a while or a plan that ended.
        if t - _looked["lifecycle"] >= KARMA_EVERY_S:
            _looked["lifecycle"] = t
            from engine import lifecycle as _lc
            told += _lc.run(conn, now=t, web=Path(web), log=log)
        # Remind me (engine/gamechat): games starting in ten minutes.
        from engine import gamechat as _gc
        try:
            told += _gc.reminders_pass(conn, now=t)
        except Exception as exc:                                  # noqa: BLE001 — the rest of the minute still runs
            log(f"  ⚠️  reminders: {type(exc).__name__}: {exc}")
        # Kickoff (engine/kickoffs): a followed team's game starting in ten
        # minutes, after the bells so a bell rung for it speaks instead.
        from engine import kickoffs as _ko
        try:
            told += _ko.kickoff_pass(conn, Path(web) / "data", now=t)
        except Exception as exc:                                  # noqa: BLE001 — the rest of the minute still runs
            log(f"  ⚠️  kickoff: {type(exc).__name__}: {exc}")
        # While you were away (engine/engagement): at each member's own
        # hour, so looked at every quarter hour; nothing while activity is off.
        if t - _looked["away"] >= KARMA_EVERY_S:
            _looked["away"] = t
            from engine import engagement as _en
            try:
                told += _en.away_pass(conn, Path(web) / "data", now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  while you were away: {type(exc).__name__}: {exc}")
        # The research's follow alerts (2026-10-29): a followed team's close
        # finish every minute, the morning slate, injury news for the
        # member's own players (engine/kickoffs, engine/newsalerts).
        try:
            told += _ko.closegame_pass(conn, Path(web) / "data", now=t)
            if t - _looked["today"] >= KARMA_EVERY_S:
                _looked["today"] = t
                told += _ko.today_pass(conn, Path(web) / "data", now=t)
        except Exception as exc:                                  # noqa: BLE001 — the rest of the minute still runs
            log(f"  ⚠️  close games / today: {type(exc).__name__}: {exc}")
        if t - _looked["news"] >= NEWS_EVERY_S:
            _looked["news"] = t
            from engine import newsalerts as _na
            try:
                told += _na.news_pass(conn, Path(web) / "data", now=t)
            except Exception as exc:                              # noqa: BLE001 — the rest of the minute still runs
                log(f"  ⚠️  injury news: {type(exc).__name__}: {exc}")
        moments = clutch_pass(conn, Path(web) / "data" / "pbp", now=t)
        from engine import finals as _fin
        moments += _fin.finals_pass(conn, Path(web) / "data" / "pbp", now=t)
        stats = flush(conn, now=t, **flush_kw)
        if stats["messages"]:
            log(f"  push (yours): {stats['messages']} alert(s), {told} from watches, {moments} big moment(s) · "
                f"{stats['sent']} phone(s), {stats['gone']} gone, {stats['failed']} failed")
        return dict(stats, watches=told, clutch=moments)
    finally:
        conn.close()


def main(argv=None) -> int:
    """Read-only: what is queued and how many phones asked, by topic."""
    from engine import accounts
    try:
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        print(f"No accounts database to read ({exc}).")
        return 0
    try:
        try:
            subs = conn.execute("SELECT topics FROM push_subs WHERE user_id IS NOT NULL").fetchall()
        except sqlite3.Error:
            subs = []
        n = {tp: sum(1 for (s,) in subs if tp in str(s).split(",")) for tp in TOPICS}
        try:
            q = conn.execute("SELECT kind, SUM(sent = 0), COUNT(*) FROM push_mine GROUP BY kind").fetchall()
        except sqlite3.Error:
            q = []
        try:
            leagues = conn.execute("SELECT COUNT(*) FROM push_lineup_leagues").fetchone()[0]
        except sqlite3.Error:
            leagues = 0
    finally:
        conn.close()
    print(f"Signed-in phones asking: {n['watches']} for watches, {n['bets']} for their bets, "
          f"{n['clutch']} for big moments, {n['finals']} for final scores, {n['lineup']} for their "
          f"fantasy lineup ({leagues} league{'s' if leagues != 1 else ''} kept for it), {n['karma']} for "
          f"karma alerts.")
    print("Queued (unsent / kept): " + (", ".join(f"{k} {u}/{c}" for k, u, c in q) if q else "nothing yet."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
