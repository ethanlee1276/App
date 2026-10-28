"""Karma: levels and badges for showing up, watching and talking.

Ethan, 2026-10-28: "diving back to the Real app there's a feature at hand
where they give you karma for viewing live games and talking and chatting
… it's like a type of a level up feature and you can get badges … look
more deeper into that. And see what other apps do like that as well then
implement features like that".

WHAT REAL DOES (its help pages, docs.realapp.link: Karma, Badges,
Leaderboards, the changelog). Karma is the app's social currency: +10 or
more for each live game's feed you open while it is on, +10 for the live
feed and +10 for a comment once a day, a fixed amount for reacting and for
the day's game pick, 10 to 100 for a pre-game poll called right, 5 to 50
for an in-game one. Badges come in amounts (10, 50, 500, 1k, 5k …) of
karma reached, live games watched, upvotes earned and polls won, plus one-
off badges (a playoff game watched, an emoji challenge done). Karma
milestones unlock things on the profile (a banner at 1,000, a flair emoji
at 5,000); a day, a week, a month and a season each have a karma
leaderboard, and placing on one leaves a trophy. A daily streak rewards
the day's poll called right.

WHAT THE OTHERS ADD. Twitch pays channel points for watching (10 every
five minutes, more for watching while chatting, a bonus for a run of
streams watched) and fills a Hype Train when a chat goes off together:
five levels, each with a five-minute clock. Duolingo has XP, a daily
streak that a missed day freezes rather than breaks, three daily quests,
and a weekly league. Reddit's karma is the upvotes your posts and
comments earn, with streak and milestone achievements; scrolling counts
for nothing there. Discord's level bots (MEE6) pay 15 to 25 XP a message
but only one message a minute, so spam levels nobody. The MLB Ballpark
app keeps a fan's journal of games attended.

WHAT THIS IS. Every account (free or member, the chat is free) earns
karma for:
  * watching — a live game's page open: +10 for each game joined while it
    is on, +2 every five minutes watched (up to 20 a game), +5 for being
    in the room when the house posts a big play (engine/housepost);
  * talking — +10 for the first message of the day in a game chat, +2 a
    message after that, one a minute (MEE6's rule), up to 20 more a day;
    +1 for each person who reacts to a message of yours (Reddit's upvote,
    Real's upvote badges), up to 50 a day; +5 the first time a day you
    react;
  * playing the free games — +5 for voting who wins a game and +10 when
    your side wins, +5 for each Call it call right (engine/callit) and +25
    for every five right in a row, +5 for each trivia answer right
    (engine/trivia), +5 per level when the room's heat (below) climbs while
    you are part of it;
  * showing up — +5 the first time a day you open the Live tab or your
    karma, three daily quests (+10 each, +20 for all three; Duolingo's),
    days in a row with milestone bonuses (3, 7, 14, 30 … 365), one missed
    day forgiven for every seven in a row (Duolingo's freeze, without a
    shop);
  * bringing people — +15 when a friend joins a watch party you started,
    +5 for joining one, +100 when a friend you invited becomes a member,
    +5 for each of your first ten teams or players followed;
  * the week — the week's top ten on the karma ladder each take a trophy
    (+100 first, +50 to third, +25 to tenth).

NEVER FOR MONEY OR BETS. Nothing here pays for a bet logged, tracked,
tailed or placed, a sportsbook opened, a parlay built, or a plan bought;
the one payment that counts is a friend's, and it pays the friend who
brought them, not the buyer. Karma buys nothing and is worth nothing
outside the page: it is a level, badges and a flair, the way Real's is.

LEVELS. Level L needs 25·(L−1)·(L+2) karma (100 for level 2, 2,700 for 10,
10,450 for 20, 40,950 for 40) — the curve Discord's level bots use, square
in the level, so the early levels come in a night and the later ones are
a season's. Every five levels is a tier with its own colour, Rookie to
Legend, worn beside a username in every game chat; level 3 unlocks a flair
emoji worn beside it too.

THE ROOM'S HEAT (Twitch's Hype Train). A game chat's last five minutes —
messages and reactions from at least three people — fill a meter of five
levels shown over the chat; everyone who took part while it climbed is
paid for each level, once an hour a room.

CAPS AND ONCE-ONLY. Every award is a row keyed (account, kind, what it is
for): the same message, game, call or day can never pay twice, and each
kind has its daily ceiling, so no tapping farms a level. A message hidden
by reports or by the founder takes back what it earned and what its
reactions earned. The site's own account earns nothing and stands on no
ladder.

THE LADDER AND YOUR NAME. The week's and the all-time ladders show
usernames, the way Call it's ladders do; "Show me on the karma ladders"
(Settings, the Karma tab) takes a name off them. Levels and badges show on
a profile and beside a username in the chats.

KEPT: the karma rows (``karma_events``: what, when, how much), the games
joined while live (``karma_watch``), the flair and the ladder choice
(``karma_prefs``) and each finished week's top ten (``karma_weeks``) —
named in the Privacy Policy, exported with the account and deleted with
it. Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import math
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "web" / "data"
_ET = ZoneInfo("America/New_York")

#: What each kind of karma pays, its ceiling a day (None: no daily
#: ceiling, the key alone keeps it once), and how the page names it.
RULES = {
    "watch_join": (10, 100, "Joined a live game"),
    "watch": (2, 60, "Watching live"),
    "witness": (5, 30, "There for a big play"),
    "chat_day": (10, None, "First message of the day"),
    "chat": (2, 20, "Chatting"),
    "liked": (1, 50, "A reaction to your message"),
    "react_day": (5, None, "Reacted"),
    "vote": (5, None, "Voted who wins"),
    "vote_won": (10, None, "Picked the winner"),
    "call_won": (5, 75, "Called it"),
    "call_streak": (25, None, "Five calls right in a row"),
    "trivia": (5, 30, "Trivia right"),
    "hype": (5, 50, "The room's heat climbed"),
    "day": (5, None, "Checked in"),
    "quest": (10, None, "Daily quest"),
    "quests_all": (20, None, "All three quests"),
    "streak_bonus": (0, None, "Days in a row"),
    "follow": (5, None, "Followed a team or player"),
    "party_host": (15, 30, "A friend joined your watch party"),
    "party_join": (5, 15, "Joined a watch party"),
    "recruit": (100, None, "A friend you invited became a member"),
    "camp": (20, None, "Getting started"),
    "camp_done": (50, None, "Getting started: all five"),
    "trophy": (0, None, "Top ten for the week"),
    "night": (0, None, "Watching after 1 a.m."),
}
#: A game pays for at most this much watching (ten five-minute stretches).
WATCH_PER_GAME = 20
#: One watching credit at a time, whatever is open: a credit every
#: WATCH_EVERY_S seconds across every tab and game.
WATCH_EVERY_S = 300
#: Messages pay one a minute (MEE6).
CHAT_EVERY_S = 60
#: Your first this-many follows pay.
FOLLOW_MAX = 10
#: A big play counts for a watcher whose page asked within this long of it.
WITNESS_S = 360
#: Days-in-a-row milestones and what each pays.
STREAK_BONUS = {3: 10, 7: 25, 14: 50, 30: 100, 50: 150, 100: 300, 200: 500, 365: 1000}
#: A missed day is forgiven after this many days in a row.
REST_AFTER = 7
#: Call it: a bonus for every CALL_RUN right in a row.
CALL_RUN = 5
#: The week's trophies: rank → karma.
TROPHY = {1: 100, 2: 50, 3: 50, **{r: 25 for r in range(4, 11)}}
TROPHY_WEEKS_BACK = 4
#: Accounts made before this (1 Jan 2027, Eastern) are founding fans.
FOUNDING_BEFORE = _dt.datetime(2027, 1, 1, tzinfo=_ET).timestamp()

#: The tiers: (first level, name, class). Every five levels until MVP.
TIERS = ((1, "Rookie", "t1"), (5, "Starter", "t2"), (10, "Pro", "t3"), (15, "All-Star", "t4"),
         (20, "MVP", "t5"), (30, "Hall of Famer", "t6"), (40, "Legend", "t7"))
#: Unlocks by level.
FLAIR_AT = 3
COLOR_AT = 10
RING_AT = 20
#: The flair a level-3 account may wear beside its name — sports and
#: noise, nothing that is a team's mark or a bet.
FLAIRS = ("🔥", "🏈", "🏀", "⚾", "🏒", "🎯", "👑", "🐐", "💯", "⚡", "🧊", "🚀", "🍿", "📣", "🧠", "🦾")

#: Badge families: (key, name, what counts, tier thresholds).
FAMILIES = (
    ("live", "Watching live", "live games watched", (1, 10, 50, 100, 250, 500)),
    ("voice", "In the chat", "game chat messages (one a minute counts)", (10, 100, 500, 1000, 5000)),
    ("crowd", "Crowd favourite", "reactions to your messages", (10, 50, 250, 1000, 5000)),
    ("caller", "Called it", "Call it calls right", (10, 50, 250, 1000, 2500)),
    ("hothand", "Hot hand", "Call it calls right in a row, best", (3, 5, 8, 12, 20)),
    ("trivia", "Trivia head", "trivia answers right", (5, 25, 100, 500)),
    ("winner", "Picked the winner", "who-wins votes right", (5, 25, 100, 250)),
    ("streak", "Every day", "days in a row, best", (3, 7, 14, 30, 100, 365)),
    ("sports", "All sports", "leagues watched live", (2, 3, 4, 5, 6)),
    ("there", "I was there", "big plays seen live", (1, 10, 50, 100)),
    ("host", "Host", "watch parties friends joined", (1, 5, 25)),
    ("recruiter", "Recruiter", "friends who became members", (1, 5, 10)),
    ("weeks", "Week's best", "weeks in the top ten", (1, 5, 10, 25)),
    ("season", "Season ticket", "live games of one league this season", (5, 10, 25, 50, 100)),
    ("karma", "Karma", "karma earned", (1000, 5000, 10000, 50000, 100000)),
)
TIER_NAMES = ("Bronze", "Silver", "Gold", "Platinum", "Diamond", "Legend")
#: One-off badges: (key, name, how).
ONE_OFF = (
    ("founding", "Founding fan", "Joined Qellys in its first season"),
    ("nightowl", "Night owl", "Watched a live game after 1 a.m. Eastern"),
)

#: The daily quests: (key, words, the count that finishes it).
QUESTS = {
    "watch": ("Watch a live game for 10 minutes", 2),
    "chat": ("Say something in a game chat", 1),
    "react": ("React to a play or a message", 1),
    "call": ("Make a Call it call", 1),
    "trivia": ("Answer a trivia question", 1),
    "vote": ("Vote who wins a game", 1),
}
#: Watching is every day's first quest; two more are drawn for the day.
QUEST_FIRST = "watch"

#: The room's heat: activity in the last HYPE_S seconds (messages and
#: reactions), from at least HYPE_PEOPLE people.
HYPE_S = 300
HYPE_PEOPLE = 3
HYPE_LEVELS = (10, 25, 50, 100, 200)

#: THE SEASON (a Season ticket badge's count): live games of one league
#: since 1 Aug 2026, Eastern — the 2026-27 season, the date Call it's
#: season ladder starts from. Move both when a new season starts.
SEASON_START = _dt.datetime(2026, 8, 1, tzinfo=_ET).timestamp()

#: GETTING STARTED (2026-10-28; the first-week checklists Duolingo and
#: Strava open with): five firsts, each worth CAMP karma once, and a bonus
#: for all five. Shown to an account for its first CAMP_DAYS, or until done.
CAMP = (("profile", "Pick a username"), ("follow", "Follow a team or a player"),
        ("watch", "Open a live game"), ("chat", "Say something in a game chat"),
        ("call", "Make a Call it call"))
CAMP_DAYS = 14

#: FRIENDS WATCHING NOW (2026-10-28; Discord's and Xbox's "playing now"): a
#: friend's live game shows while their page asked within this long, unless
#: they turned it off.
FRIEND_FRESH_S = 150

#: KARMA ALERTS (2026-10-28, Ethan: "keep user retainment"), one switch on
#: the Karma tab, sent as the account's own phone alerts (engine/pushmine,
#: topic ALERT_TOPIC): at about eight in the evening, Eastern, when the days
#: in a row would end at midnight (Duolingo's reminder); on a Monday, the
#: week's trophy; and each new tier. Nothing at night (quiet hours hold it).
ALERT_TOPIC = "karma"
STREAK_NUDGE_HOURS = (19.5, 22.5)
#: A run this long is worth a nudge.
STREAK_NUDGE_MIN = 2

LADDER_N = 25
CACHE_S = 60
_cache: dict = {}


# ─── storage ────────────────────────────────────────────────────────────────

def ensure_tables(conn) -> None:
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS karma_events (
        user_id INTEGER NOT NULL,
        kind    TEXT NOT NULL,
        ref     TEXT NOT NULL,
        pts     INTEGER NOT NULL,
        at      REAL NOT NULL,
        day     TEXT NOT NULL,
        PRIMARY KEY (user_id, kind, ref)
      );
      CREATE INDEX IF NOT EXISTS karma_events_day ON karma_events (user_id, day);
      CREATE INDEX IF NOT EXISTS karma_events_at ON karma_events (at);
      CREATE TABLE IF NOT EXISTS karma_watch (
        user_id  INTEGER NOT NULL,
        room     TEXT NOT NULL,
        league   TEXT NOT NULL,
        first_at REAL NOT NULL,
        last_at  REAL NOT NULL,
        PRIMARY KEY (user_id, room)
      );
      CREATE TABLE IF NOT EXISTS karma_prefs (
        user_id    INTEGER PRIMARY KEY,
        flair      TEXT NOT NULL DEFAULT '',
        ladder     INTEGER NOT NULL DEFAULT 1,
        seen_level INTEGER NOT NULL DEFAULT 0
      );
      -- Each finished week's top ten, worked out once.
      CREATE TABLE IF NOT EXISTS karma_weeks (
        week    TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        rank    INTEGER NOT NULL,
        pts     INTEGER NOT NULL,
        PRIMARY KEY (week, user_id)
      );
      CREATE TABLE IF NOT EXISTS karma_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
      );
    """)
    # Karma alerts (2026-10-28): whether this account wants them, and the
    # level its last "a new tier" alert was for. Added rather than declared
    # (the table shipped first), and raced like gamechat's party column.
    have = {r[1] for r in conn.execute("PRAGMA table_info(karma_prefs)")}
    # And (the same day) whether friends may see the live game it is on.
    # And the badges pinned to show first on the profile (comma-separated).
    for col, decl in (("remind", "INTEGER NOT NULL DEFAULT 0"), ("told_level", "INTEGER NOT NULL DEFAULT 0"),
                      ("share", "INTEGER NOT NULL DEFAULT 1"), ("pins", "TEXT NOT NULL DEFAULT ''")):
        if col not in have:
            from .db import column_exists_or_raise
            try:
                conn.execute(f"ALTER TABLE karma_prefs ADD COLUMN {col} {decl}")
            except sqlite3.OperationalError as exc:
                column_exists_or_raise(exc)


_ready: set = set()


def _prepare(conn) -> None:
    """The tables, and once a database everything said and played before
    karma began counted (``backfill``) — on whichever read comes first, so
    a chat's levels are right before anybody opens the Karma tab."""
    try:
        key = str(conn.execute("PRAGMA database_list").fetchone()[2] or "")
    except (sqlite3.Error, TypeError, IndexError):
        key = ""
    if key and key in _ready:
        return
    ensure_tables(conn)
    backfill(conn)
    if key:
        _ready.add(key)


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


# ─── days and weeks, Eastern ────────────────────────────────────────────────

def day_of(t: float) -> str:
    return _dt.datetime.fromtimestamp(float(t), tz=_ET).date().isoformat()


def day_start(day: str) -> float:
    d = _dt.date.fromisoformat(day)
    return _dt.datetime(d.year, d.month, d.day, tzinfo=_ET).timestamp()


def _shift(day: str, n: int) -> str:
    return (_dt.date.fromisoformat(day) + _dt.timedelta(days=n)).isoformat()


def week_of(t: float) -> str:
    """The Monday (Eastern) that starts the week ``t`` falls in."""
    d = _dt.datetime.fromtimestamp(float(t), tz=_ET).date()
    return (d - _dt.timedelta(days=d.weekday())).isoformat()


# ─── levels ─────────────────────────────────────────────────────────────────

def need(level: int) -> int:
    """Karma that level ``level`` starts at."""
    lv = max(1, int(level))
    return 25 * (lv - 1) * (lv + 2)


def level_of(points: int) -> int:
    p = max(0, int(points or 0))
    lv = max(1, int((-1 + math.sqrt(9 + 4 * p / 25)) / 2))
    while need(lv + 1) <= p:
        lv += 1
    while lv > 1 and need(lv) > p:
        lv -= 1
    return lv


def tier_of(level: int) -> tuple:
    """``(name, class)`` of a level's tier."""
    out = TIERS[0]
    for t in TIERS:
        if level >= t[0]:
            out = t
    return out[1], out[2]


def level_view(points: int) -> dict:
    lv = level_of(points)
    name, cls = tier_of(lv)
    lo, hi = need(lv), need(lv + 1)
    return {"points": int(points), "level": lv, "tier": name, "cls": cls, "from": lo, "to": hi,
            "progress": round((points - lo) / (hi - lo), 4) if hi > lo else 1.0}


# ─── awarding ───────────────────────────────────────────────────────────────

def total(conn, user_id) -> int:
    row = conn.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=?", (int(user_id),)).fetchone()
    return int(row[0] or 0)


def _day_sum(conn, user_id, kind: str, day: str) -> int:
    row = conn.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=? AND day=? AND kind=?",
                       (int(user_id), day, kind)).fetchone()
    return int(row[0] or 0)


def _house(conn) -> int | None:
    try:
        from . import housepost as HP
        return HP.house_id(conn)
    except Exception:                                        # noqa: BLE001
        return None


def award(conn, user_id, kind: str, ref, pts: int | None = None, now: float | None = None,
          commit: bool = True) -> int:
    """Pay ``kind`` for ``ref`` once, inside its daily ceiling. Returns
    what was paid (0 when it was paid before, or the day is full)."""
    if not user_id or kind not in RULES:
        return 0
    t = time.time() if now is None else float(now)
    base, cap, _ = RULES[kind]
    p = base if pts is None else int(pts)
    day = day_of(t)
    if cap is not None and p > 0:
        room = cap - _day_sum(conn, user_id, kind, day)
        if room <= 0:
            return 0
        p = min(p, room)
    cur = conn.execute("INSERT OR IGNORE INTO karma_events (user_id, kind, ref, pts, at, day) VALUES (?,?,?,?,?,?)",
                       (int(user_id), kind, str(ref)[:80], int(p), t, day))
    if commit:
        conn.commit()
    if cur.rowcount:
        _cache.pop(("card", int(user_id)), None)
        return p
    return 0


def note(conn, user_id, got: int, kind: str) -> dict | None:
    """What an action's answer carries back for the page's toast: what it
    paid, the new total, and whether a level was crossed."""
    if not got:
        return None
    t = total(conn, user_id)
    return {"got": int(got), "why": RULES.get(kind, (0, 0, ""))[2], "total": t,
            "level": level_of(t), "up": level_of(t - got) < level_of(t)}


def on_message(conn, user_id, msg_id, now: float | None = None) -> dict | None:
    """A message posted in a game chat: the day's first pays 10, the rest 2
    each, one a minute, inside the day's ceiling."""
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    day = day_of(t)
    got = award(conn, user_id, "chat_day", day, now=t)
    if got:
        return note(conn, user_id, got, "chat_day")
    last = conn.execute("SELECT MAX(at) FROM karma_events WHERE user_id=? AND kind IN ('chat','chat_day')",
                        (int(user_id),)).fetchone()[0]
    if last is not None and t - float(last) < CHAT_EVERY_S:
        return None
    return note(conn, user_id, award(conn, user_id, "chat", int(msg_id), now=t), "chat")


def on_react(conn, user_id, msg_id, kind_now: str, now: float | None = None) -> dict | None:
    """A face put on a message: its author earns 1 (never for their own,
    once per person per message); the reactor's first of the day pays 5."""
    ensure_tables(conn)
    if not kind_now:
        return None
    t = time.time() if now is None else float(now)
    row = conn.execute("SELECT user_id FROM chat_msgs WHERE id=? AND hidden=0", (int(msg_id or 0),)).fetchone()
    if row and int(row[0]) != int(user_id) and int(row[0]) != (_house(conn) or -1):
        award(conn, int(row[0]), "liked", f"{int(msg_id)}:{int(user_id)}", now=t)
    return note(conn, user_id, award(conn, user_id, "react_day", day_of(t), now=t), "react_day")


def on_play_react(conn, user_id, kind_now: str, now: float | None = None) -> dict | None:
    ensure_tables(conn)
    if not kind_now:
        return None
    t = time.time() if now is None else float(now)
    return note(conn, user_id, award(conn, user_id, "react_day", day_of(t), now=t), "react_day")


def on_vote(conn, user_id, room: str, now: float | None = None) -> dict | None:
    ensure_tables(conn)
    return note(conn, user_id, award(conn, user_id, "vote", room, now=now), "vote")


def on_trivia(conn, user_id, room: str, qkey: str, right: bool, now: float | None = None) -> dict | None:
    ensure_tables(conn)
    if not right:
        return None
    return note(conn, user_id, award(conn, user_id, "trivia", f"{room}:{qkey}", now=now), "trivia")


def on_party_join(conn, user_id, party_id, now: float | None = None) -> dict | None:
    """Joining a friend's watch party pays the joiner 5 and its host 15."""
    ensure_tables(conn)
    row = conn.execute("SELECT user_id FROM chat_parties WHERE id=?", (int(party_id or 0),)).fetchone()
    if not row or int(row[0]) == int(user_id):
        return None
    if int(row[0]):
        award(conn, int(row[0]), "party_host", int(party_id), now=now)
    return note(conn, user_id, award(conn, user_id, "party_join", int(party_id), now=now), "party_join")


def on_follow(conn, user_id, kind: str, value: str, now: float | None = None) -> dict | None:
    """A team or a player followed: the first FOLLOW_MAX pay (a price or an
    edge alert is about a bet, and pays nothing)."""
    ensure_tables(conn)
    if kind not in ("team", "player"):
        return None
    n = conn.execute("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND kind='follow'", (int(user_id),)).fetchone()[0]
    if n >= FOLLOW_MAX:
        return None
    return note(conn, user_id, award(conn, user_id, "follow", f"{kind}:{value}", now=now), "follow")


def grade_calls(conn, game: str, unit: str, now: float | None = None) -> int:
    """Pay this unit's right calls (engine/callit grade calls it). Returns
    how many were paid."""
    ensure_tables(conn)
    n = 0
    for (uid, at) in conn.execute("SELECT user_id, at FROM callit_calls WHERE game=? AND unit=? AND won=1",
                                  (game, unit)).fetchall():
        n += bool(award(conn, uid, "call_won", f"{game}:{unit}", now=now if now is not None else at, commit=False))
    conn.commit()
    return n


def revoke_message(conn, msg_id) -> None:
    """A message hidden for everyone takes back what it paid, and what the
    reactions to it paid its writer."""
    try:
        ensure_tables(conn)
        conn.execute("DELETE FROM karma_events WHERE kind='chat' AND ref=?", (str(int(msg_id)),))
        conn.execute("DELETE FROM karma_events WHERE kind='liked' AND ref LIKE ?", (f"{int(msg_id)}:%",))
        conn.commit()
        _cache.clear()
    except sqlite3.Error:
        pass


# ─── watching ───────────────────────────────────────────────────────────────

def _live_game(room: str, data_dir: Path | None = None) -> dict:
    from . import gamechat as GC
    m = GC.ROOM_RE.match(str(room or ""))
    if not m:
        return {}
    from .socialfeed import _read
    blob = _read((data_dir or DATA) / f"live_{m.group(1)}.json") or {}
    for g in blob.get("games") or []:
        if str(g.get("event_id") or g.get("game_pk") or "") == m.group(2):
            live = g.get("live") or {}
            return {"league": m.group(1), "state": str(live.get("state") or ""),
                    "home": g.get("home") or "", "away": g.get("away") or "",
                    "home_score": live.get("home_score"), "away_score": live.get("away_score")}
    return {}


def watch(conn, user_id, room: str, now: float | None = None, data_dir: Path | None = None) -> tuple[int, dict]:
    """A live game's page, open and in view, asking about once a minute.
    Joining a game on pays 10; watching pays 2 a stretch of five minutes
    (one stretch at a time across every tab and game, 20 a game at most);
    a big play the house posts in the room while you are there pays 5."""
    _prepare(conn)
    t = time.time() if now is None else float(now)
    from . import gamechat as GC
    if not GC.room_ok(room):
        return 400, {"error": "That game has no room."}
    g = _live_game(room, data_dir)
    if g.get("state") != "live":
        return 200, {"ok": True, "live": False}
    was = conn.execute("SELECT first_at FROM karma_watch WHERE user_id=? AND room=?", (int(user_id), room)).fetchone()
    conn.execute("INSERT INTO karma_watch (user_id, room, league, first_at, last_at) VALUES (?,?,?,?,?) "
                 "ON CONFLICT(user_id, room) DO UPDATE SET last_at=excluded.last_at",
                 (int(user_id), room, g["league"], t, t))
    first = float(was[0]) if was else t
    got, kind = 0, "watch_join"
    got += award(conn, user_id, "watch_join", room, now=t, commit=False)
    last = conn.execute("SELECT MAX(at) FROM karma_events WHERE user_id=? AND kind='watch'", (int(user_id),)).fetchone()[0]
    done = conn.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=? AND kind='watch' AND ref LIKE ?",
                        (int(user_id), f"{room}:%")).fetchone()[0]
    # A stretch pays once the page has been here five minutes, and five
    # minutes after the last stretch paid, in this game or another.
    if (t - first >= WATCH_EVERY_S - 15 and (last is None or t - float(last) >= WATCH_EVERY_S - 15)
            and int(done or 0) < WATCH_PER_GAME):
        p = award(conn, user_id, "watch", f"{room}:{int(t // WATCH_EVERY_S)}", now=t, commit=False)
        if p and not got:
            kind = "watch"
        got += p
    hour = _dt.datetime.fromtimestamp(t, tz=_ET).hour
    if 1 <= hour < 5:
        award(conn, user_id, "night", day_of(t), now=t, commit=False)
    # A big play the house posted in this room while this page was here.
    seen = 0
    if _has(conn, "chat_house_seen"):
        for (play,) in conn.execute("SELECT play FROM chat_house_seen WHERE game=? AND posted=1 AND at>=? AND at>=?",
                                    (room, t - WITNESS_S, first - 60)).fetchall():
            p = award(conn, user_id, "witness", f"{room}:{play}", now=t, commit=False)
            if p:
                seen += 1
                if not got:
                    kind = "witness"
                got += p
    conn.commit()
    out = {"ok": True, "live": True}
    k = note(conn, user_id, got, kind)
    if k:
        out["karma"] = k
    if seen:
        out["witness"] = seen
    return 200, out


# ─── catching up: what other tables already say ─────────────────────────────

def _award_rows(conn, user_id, kind: str, rows) -> int:
    """Pay ``[(ref, at)]`` in time order, each on its own day's ceiling."""
    n = 0
    for ref, at in sorted(rows, key=lambda r: float(r[1] or 0)):
        n += award(conn, user_id, kind, ref, now=float(at or time.time()), commit=False)
    return n


def _winner(g: dict) -> str:
    try:
        h, a = float(g.get("home_score")), float(g.get("away_score"))
    except (TypeError, ValueError):
        return ""
    return "home" if h > a else "away" if a > h else ""


_graded: set = set()


def grade_votes(conn, room: str, data_dir: Path | None = None, now: float | None = None) -> int:
    """A final game's who-wins vote: the right side's voters each earn 10.
    Asked on every poll of a final game's room, so a room graded once is
    remembered (a late vote cannot come: the vote closes at the final)."""
    if room in _graded and data_dir is None:
        return 0
    ensure_tables(conn)
    g = _live_game(room, data_dir)
    side = _winner(g) if g.get("state") == "final" else ""
    if not side or not _has(conn, "chat_votes"):
        return 0
    n = 0
    for (uid,) in conn.execute("SELECT user_id FROM chat_votes WHERE room=? AND side=?", (room, side)).fetchall():
        n += bool(award(conn, uid, "vote_won", room, now=now, commit=False))
    conn.commit()
    if data_dir is None:
        _graded.add(room)
        if len(_graded) > 5000:
            _graded.clear()
    return n


def sync_user(conn, user_id, now: float | None = None, data_dir: Path | None = None) -> None:
    """What this account did that pays and is not paid yet: calls right,
    trivia right, follows, watch parties, friends who became members, and
    who-wins votes on games now final. Once each; cheap to run again."""
    uid = int(user_id)
    if _has(conn, "callit_calls"):
        _award_rows(conn, uid, "call_won", [(f"{g}:{u}", at) for g, u, at in conn.execute(
            "SELECT game, unit, at FROM callit_calls WHERE user_id=? AND won=1 ORDER BY at DESC LIMIT 2000", (uid,))])
    if _has(conn, "trivia_answers") and _has(conn, "trivia_asked"):
        rows = []
        for room, qkey, pick, at, q in conn.execute(
                "SELECT a.room, a.qkey, a.pick, a.at, q.q FROM trivia_answers a JOIN trivia_asked q "
                "ON q.room=a.room AND q.qkey=a.qkey WHERE a.user_id=?", (uid,)):
            try:
                if int(json.loads(q).get("answer")) == int(pick):
                    rows.append((f"{room}:{qkey}", at))
            except (ValueError, TypeError, AttributeError):
                continue
        _award_rows(conn, uid, "trivia", rows)
    if _has(conn, "alert_watches"):
        have = conn.execute("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND kind='follow'", (uid,)).fetchone()[0]
        if have < FOLLOW_MAX:
            rows = conn.execute("SELECT kind, value, created_at FROM alert_watches WHERE user_id=? AND kind IN "
                                "('team','player') ORDER BY created_at LIMIT ?", (uid, FOLLOW_MAX)).fetchall()
            _award_rows(conn, uid, "follow", [(f"{k}:{v}", at) for k, v, at in rows])
    if _has(conn, "chat_parties") and _has(conn, "chat_party_members"):
        _award_rows(conn, uid, "party_host", [(pid, at) for pid, at in conn.execute(
            "SELECT p.id, MIN(m.joined_at) FROM chat_parties p JOIN chat_party_members m ON m.party_id=p.id "
            "WHERE p.user_id=? AND m.user_id<>? GROUP BY p.id", (uid, uid))])
        _award_rows(conn, uid, "party_join", [(pid, at) for pid, at in conn.execute(
            "SELECT m.party_id, m.joined_at FROM chat_party_members m JOIN chat_parties p ON p.id=m.party_id "
            "WHERE m.user_id=? AND p.user_id<>?", (uid, uid))])
    if _has(conn, "referrals"):
        _award_rows(conn, uid, "recruit", [(rid, at) for rid, at in conn.execute(
            "SELECT referred_id, paid_at FROM referrals WHERE referrer_id=? AND paid_at IS NOT NULL", (uid,))])
    if _has(conn, "chat_votes"):
        for (room,) in conn.execute("SELECT room FROM chat_votes WHERE user_id=? AND changed_at>?",
                                    (uid, (time.time() if now is None else now) - 3 * 86400)).fetchall():
            if not conn.execute("SELECT 1 FROM karma_events WHERE user_id=? AND kind='vote_won' AND ref=?",
                                (uid, room)).fetchone():
                grade_votes(conn, room, data_dir, now)
    conn.commit()


def backfill(conn, now: float | None = None) -> bool:
    """Once: everything said and played before karma began counts, by the
    same rules and ceilings — the chats' fourteen days of messages and
    their reactions, every vote, and every account's calls, trivia,
    follows, parties and friends. Returns True when it ran."""
    ensure_tables(conn)
    if conn.execute("SELECT 1 FROM karma_meta WHERE key='backfill_v1'").fetchone():
        return False
    house = _house(conn) or -1
    if _has(conn, "chat_msgs"):
        last: dict = {}
        for mid, uid, at in conn.execute("SELECT id, user_id, created_at FROM chat_msgs WHERE hidden=0 "
                                         "ORDER BY created_at").fetchall():
            if int(uid) == house:
                continue
            if award(conn, uid, "chat_day", day_of(at), now=at, commit=False):
                last[uid] = at
            elif at - last.get(uid, -1e18) >= CHAT_EVERY_S and award(conn, uid, "chat", mid, now=at, commit=False):
                last[uid] = at
        if _has(conn, "chat_reacts"):
            for mid, reactor, at, author in conn.execute(
                    "SELECT r.msg_id, r.user_id, r.changed_at, m.user_id FROM chat_reacts r JOIN chat_msgs m "
                    "ON m.id=r.msg_id WHERE r.kind<>'' AND m.hidden=0 ORDER BY r.changed_at").fetchall():
                if int(author) != int(reactor) and int(author) != house:
                    award(conn, author, "liked", f"{mid}:{reactor}", now=at, commit=False)
                award(conn, reactor, "react_day", day_of(at), now=at, commit=False)
    if _has(conn, "chat_play_reacts"):
        for uid, at in conn.execute("SELECT user_id, changed_at FROM chat_play_reacts WHERE kind<>''").fetchall():
            award(conn, uid, "react_day", day_of(at), now=at, commit=False)
    if _has(conn, "chat_votes"):
        for room, uid, at in conn.execute("SELECT room, user_id, changed_at FROM chat_votes").fetchall():
            award(conn, uid, "vote", room, now=at, commit=False)
    users = set()
    for table in ("callit_calls", "trivia_answers", "alert_watches", "chat_party_members"):
        if _has(conn, table):
            users |= {int(r[0]) for r in conn.execute(f"SELECT DISTINCT user_id FROM {table}")}
    if _has(conn, "referrals"):
        users |= {int(r[0]) for r in conn.execute("SELECT DISTINCT referrer_id FROM referrals WHERE paid_at IS NOT NULL")}
    for uid in sorted(users):
        if uid != house:
            sync_user(conn, uid, now)
    conn.execute("INSERT OR REPLACE INTO karma_meta (key, value) VALUES ('backfill_v1', ?)",
                 (str(time.time() if now is None else now),))
    conn.commit()
    return True


# ─── days in a row ──────────────────────────────────────────────────────────

def days_of(conn, user_id) -> list:
    return [r[0] for r in conn.execute("SELECT DISTINCT day FROM karma_events WHERE user_id=? ORDER BY day",
                                       (int(user_id),))]


def streak(days, today: str) -> dict:
    """Days in a row up to today, from the ``days`` (ascending) an account
    earned karma on. A single missed day is forgiven once the run has
    REST_AFTER days in it (and the count starts again towards the next);
    the forgiven day adds nothing. ``now``: the current run, alive while
    its last day is today or yesterday (or the day before, with a rest in
    hand); ``best``; ``start``: the current run's first day."""
    run = best = since_rest = 0
    start = prev = None
    for d in days:
        if prev is None:
            run, since_rest, start = 1, 1, d
        else:
            gap = (_dt.date.fromisoformat(d) - _dt.date.fromisoformat(prev)).days
            if gap == 1:
                run += 1
                since_rest += 1
            elif gap == 2 and since_rest >= REST_AFTER:
                run += 1
                since_rest = 1
            elif gap > 1:
                run, since_rest, start = 1, 1, d
        best = max(best, run)
        prev = d
    if prev is None:
        return {"now": 0, "best": 0, "start": None, "rest": False, "today": False}
    behind = (_dt.date.fromisoformat(today) - _dt.date.fromisoformat(prev)).days
    alive = behind <= 1 or (behind == 2 and since_rest >= REST_AFTER)
    return {"now": run if alive else 0, "best": best, "start": start if alive else None,
            "rest": since_rest >= REST_AFTER, "today": behind == 0}


# ─── quests ─────────────────────────────────────────────────────────────────

def quests_for(user_id, day: str) -> list:
    """The day's three: watching, and two drawn for this account and day
    (the same two all day, a different pair most days)."""
    rest = sorted((k for k in QUESTS if k != QUEST_FIRST),
                  key=lambda k: hashlib.sha256(f"{int(user_id)}:{day}:{k}".encode()).hexdigest())
    return [QUEST_FIRST] + rest[:2]


def _quest_count(conn, user_id, key: str, day: str) -> int:
    uid = int(user_id)
    one = lambda sql, args: int(conn.execute(sql, args).fetchone()[0] or 0)        # noqa: E731
    if key == "watch":
        return one("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND day=? AND kind='watch'", (uid, day))
    if key == "chat":
        return one("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND day=? AND kind='chat_day'", (uid, day))
    if key == "react":
        return one("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND day=? AND kind='react_day'", (uid, day))
    if key == "vote":
        return one("SELECT COUNT(*) FROM karma_events WHERE user_id=? AND day=? AND kind='vote'", (uid, day))
    lo, hi = day_start(day), day_start(_shift(day, 1))
    if key == "call" and _has(conn, "callit_calls"):
        return one("SELECT COUNT(*) FROM callit_calls WHERE user_id=? AND at>=? AND at<?", (uid, lo, hi))
    if key == "trivia" and _has(conn, "trivia_answers"):
        return one("SELECT COUNT(*) FROM trivia_answers WHERE user_id=? AND at>=? AND at<?", (uid, lo, hi))
    return 0


def quests(conn, user_id, day: str, now: float | None = None) -> list:
    """The day's quests with how far along each is, paying any just done."""
    out = []
    for key in quests_for(user_id, day):
        words, goal = QUESTS[key]
        n = _quest_count(conn, user_id, key, day)
        done = n >= goal
        if done:
            award(conn, user_id, "quest", f"{day}:{key}", now=now, commit=False)
        out.append({"key": key, "text": words, "n": min(n, goal), "goal": goal, "done": done})
    if out and all(q["done"] for q in out):
        award(conn, user_id, "quests_all", day, now=now, commit=False)
    return out


# ─── badges ─────────────────────────────────────────────────────────────────

def _count(conn, user_id, *kinds) -> int:
    q = ",".join("?" * len(kinds))
    return int(conn.execute(f"SELECT COUNT(*) FROM karma_events WHERE user_id=? AND kind IN ({q})",
                            (int(user_id), *kinds)).fetchone()[0] or 0)


def badge_counts(conn, user_id, points: int | None = None, best_days: int | None = None) -> dict:
    uid = int(user_id)
    best_call = 0
    if _has(conn, "callit_calls"):
        from . import callit as CI
        best_call = CI.streaks(conn, uid)[1]
    if best_days is None:
        best_days = streak(days_of(conn, uid), day_of(time.time()))["best"]
    return {
        "live": int(conn.execute("SELECT COUNT(*) FROM karma_watch WHERE user_id=?", (uid,)).fetchone()[0] or 0),
        "voice": _count(conn, uid, "chat", "chat_day"),
        "crowd": _count(conn, uid, "liked"),
        "caller": _count(conn, uid, "call_won"),
        "hothand": int(best_call),
        "trivia": _count(conn, uid, "trivia"),
        "winner": _count(conn, uid, "vote_won"),
        "streak": int(best_days),
        "sports": int(conn.execute("SELECT COUNT(DISTINCT league) FROM karma_watch WHERE user_id=?",
                                   (uid,)).fetchone()[0] or 0),
        "there": _count(conn, uid, "witness"),
        "host": _count(conn, uid, "party_host"),
        "recruiter": _count(conn, uid, "recruit"),
        "weeks": _count(conn, uid, "trophy"),
        "season": season_best(conn, uid)[1],
        "karma": total(conn, uid) if points is None else int(points),
    }


def badges(conn, user_id, points: int | None = None, best_days: int | None = None) -> list:
    """Every badge, earned or not: its tier (0 for none yet), the next
    tier's mark and the count so far."""
    counts = badge_counts(conn, user_id, points, best_days)
    out = []
    for key, name, what, marks in FAMILIES:
        n = counts.get(key, 0)
        tier = sum(1 for m in marks if n >= m)
        out.append({"key": key, "name": name, "what": what, "n": n, "tier": tier,
                    "tier_name": TIER_NAMES[tier - 1] if tier else "", "of": len(marks),
                    "next": marks[tier] if tier < len(marks) else None})
    u = conn.execute("SELECT created_at FROM users WHERE id=?", (int(user_id),)).fetchone() if _has(conn, "users") else None
    founding = bool(u) and float(u[0] or 0) < FOUNDING_BEFORE
    night = _count(conn, user_id, "night") > 0
    for key, name, how in ONE_OFF:
        got = founding if key == "founding" else night
        out.append({"key": key, "name": name, "what": how, "n": int(got), "tier": int(got),
                    "tier_name": "", "of": 1, "next": None if got else 1, "one": True})
    return out


#: A profile shows its owner's pinned badges first (Steam's and Xbox's
#: showcase): up to this many.
PINS_MAX = 3


def top_badges(rows: list, n: int = 6, pins=()) -> list:
    """The ones to show on a profile: the pinned (earned) first, then
    earned, highest tier first."""
    got = [b for b in rows if b["tier"]]
    pinned = [k for k in pins if k in {b["key"] for b in got}]
    got.sort(key=lambda b: (b["key"] not in pinned, pinned.index(b["key"]) if b["key"] in pinned else 0,
                            -b["tier"] / max(1, b["of"]), -b["tier"], b["key"]))
    return [{"key": b["key"], "name": b["name"], "tier": b["tier"], "tier_name": b["tier_name"],
             "one": bool(b.get("one"))} for b in got[:n]]


# ─── ladders ────────────────────────────────────────────────────────────────

def _ladder_sql(conn) -> tuple:
    prof = _has(conn, "feed_profiles")
    handle = "p.handle" if prof else "NULL"
    join = "JOIN feed_profiles p ON p.user_id=e.user_id " if prof else ""
    return handle, join


def friend_ids(conn, user_id) -> set:
    """The account's friends, both sides of the friendship (engine/social)."""
    if not user_id or not _has(conn, "friendships"):
        return set()
    return {int(r[0]) for r in conn.execute(
        "SELECT f.friend_id FROM friendships f JOIN friendships b ON b.user_id=f.friend_id AND b.friend_id=f.user_id "
        "WHERE f.user_id=?", (int(user_id),))}


def friends_ladder(conn, viewer, now: float | None = None) -> dict:
    """This week's karma among the viewer and their friends (Duolingo's
    friends league): the viewer always, a friend with a username unless
    they took themselves off the ladders."""
    _prepare(conn)
    t = time.time() if now is None else float(now)
    since = day_start(week_of(t))
    pals = friend_ids(conn, viewer)
    off = {int(r[0]) for r in conn.execute("SELECT user_id FROM karma_prefs WHERE ladder=0")}
    ids = sorted((pals - off) | {int(viewer)})
    q = ",".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT p.user_id, p.handle, COALESCE((SELECT SUM(e.pts) FROM karma_events e WHERE e.user_id=p.user_id "
        f"AND e.at>=? AND e.kind<>'trophy'), 0) AS s FROM feed_profiles p WHERE p.user_id IN ({q}) "
        "ORDER BY s DESC, p.handle", (since, *ids)).fetchall() if _has(conn, "feed_profiles") else []
    out = {"scope": "friends", "since": since, "friends": len(pals),
           "rows": [{"rank": i + 1, "handle": h, "points": int(sm), "level": level_of(total(conn, u)),
                     "me": int(u) == int(viewer)} for i, (u, h, sm) in enumerate(rows)]}
    mine = next((r for r in out["rows"] if r["me"]), None)
    out["mine"] = {"rank": mine["rank"], "points": mine["points"]} if mine else {"rank": None, "points": 0}
    return out


def ladder(conn, scope: str = "week", viewer=None, now: float | None = None, n: int = LADDER_N) -> dict:
    """The week's (from Monday, Eastern) or the all-time karma ladder: its
    top ``n`` by username, and the viewer's own place on it."""
    _prepare(conn)
    t = time.time() if now is None else float(now)
    if scope == "friends":
        return friends_ladder(conn, viewer, t) if viewer else {"scope": "friends", "rows": [], "mine": {}}
    since = day_start(week_of(t)) if scope == "week" else 0.0
    # A week's trophies pay on the Monday after: they count all time,
    # never towards the next week's ladder.
    wk = " AND e.kind<>'trophy'" if scope == "week" else ""
    key = ("ladder", scope, since, n)
    hit = _cache.get(key)
    if hit and t - hit[0] < CACHE_S:
        rows = hit[1]
    else:
        handle, join = _ladder_sql(conn)
        if not join:
            rows = []
        else:
            house = _house(conn) or -1
            rows = conn.execute(
                f"SELECT e.user_id, SUM(e.pts) AS s, {handle} FROM karma_events e {join}"
                f"LEFT JOIN karma_prefs k ON k.user_id=e.user_id WHERE e.at>=?{wk} "
                "AND COALESCE(k.ladder, 1)=1 AND e.user_id<>? GROUP BY e.user_id HAVING s>0 "
                "ORDER BY s DESC, MIN(e.at) ASC LIMIT ?", (since, house, int(n))).fetchall()
            rows = [(int(r[0]), int(r[1]), r[2]) for r in rows]
        _cache[key] = (t, rows)
    out = {"scope": scope, "since": since,
           "rows": [{"rank": i + 1, "handle": h or "a fan", "points": s, "level": level_of(total(conn, u)),
                     "me": bool(viewer) and u == int(viewer)} for i, (u, s, h) in enumerate(rows)]}
    if viewer:
        mine = int(conn.execute(f"SELECT COALESCE(SUM(e.pts), 0) FROM karma_events e WHERE e.user_id=? AND e.at>=?{wk}",
                                (int(viewer), since)).fetchone()[0] or 0)
        on = conn.execute("SELECT ladder FROM karma_prefs WHERE user_id=?", (int(viewer),)).fetchone()
        shown = on is None or int(on[0]) == 1
        if shown and mine > 0 and join_ok(conn):
            ahead = conn.execute(
                "SELECT COUNT(*) FROM (SELECT e.user_id, SUM(e.pts) AS s FROM karma_events e "
                "JOIN feed_profiles p ON p.user_id=e.user_id LEFT JOIN karma_prefs k ON k.user_id=e.user_id "
                f"WHERE e.at>=?{wk} AND COALESCE(k.ladder, 1)=1 AND e.user_id<>? "
                "GROUP BY e.user_id HAVING s>?)", (since, _house(conn) or -1, mine)).fetchone()[0]
            out["mine"] = {"rank": int(ahead) + 1, "points": mine}
        else:
            out["mine"] = {"rank": None, "points": mine, "hidden": not shown}
    return out


def join_ok(conn) -> bool:
    return _has(conn, "feed_profiles")


def _week_results(conn, week: str) -> list:
    """A finished week's top ten, worked out once and kept."""
    done = conn.execute("SELECT 1 FROM karma_meta WHERE key=?", (f"week:{week}",)).fetchone()
    if not done:
        lo = day_start(week)
        hi = day_start(_shift(week, 7))
        rows = []
        if join_ok(conn):
            rows = conn.execute(
                "SELECT e.user_id, SUM(e.pts) AS s FROM karma_events e JOIN feed_profiles p ON p.user_id=e.user_id "
                "LEFT JOIN karma_prefs k ON k.user_id=e.user_id WHERE e.at>=? AND e.at<? AND e.kind<>'trophy' "
                "AND COALESCE(k.ladder, 1)=1 AND e.user_id<>? GROUP BY e.user_id HAVING s>0 "
                "ORDER BY s DESC, MIN(e.at) ASC LIMIT 10", (lo, hi, _house(conn) or -1)).fetchall()
        for i, (uid, s) in enumerate(rows):
            conn.execute("INSERT OR REPLACE INTO karma_weeks (week, user_id, rank, pts) VALUES (?,?,?,?)",
                         (week, int(uid), i + 1, int(s)))
        conn.execute("INSERT OR REPLACE INTO karma_meta (key, value) VALUES (?, ?)", (f"week:{week}", str(len(rows))))
    return [(int(u), int(r)) for u, r in conn.execute("SELECT user_id, rank FROM karma_weeks WHERE week=?", (week,))]


def trophies(conn, user_id, now: float | None = None) -> None:
    """Pay this account's top-ten finishes in the last few finished weeks."""
    t = time.time() if now is None else float(now)
    this = week_of(t)
    for k in range(1, TROPHY_WEEKS_BACK + 1):
        week = _shift(this, -7 * k)
        for uid, rank in _week_results(conn, week):
            if uid == int(user_id) and rank in TROPHY:
                award(conn, user_id, "trophy", week, pts=TROPHY[rank], now=day_start(_shift(week, 7)) + 1,
                      commit=False)


# ─── the room's heat ────────────────────────────────────────────────────────

def hype(conn, room: str, viewer=None, now: float | None = None) -> dict:
    """The room's last five minutes as a meter: ``level`` 0-5 and how far
    to the next. A viewer who took part while it is lit earns 5 a level,
    each level once an hour in a room."""
    t = time.time() if now is None else float(now)
    key = ("hype", room)
    hit = _cache.get(key)
    if hit and t - hit[0] < 5:
        n, people, mine = hit[1]
    else:
        since = t - HYPE_S
        rows = conn.execute(
            "SELECT user_id FROM chat_msgs WHERE room=? AND created_at>=? AND hidden=0 "
            "UNION ALL SELECT user_id FROM chat_reacts WHERE room=? AND changed_at>=? AND kind<>'' "
            "UNION ALL SELECT user_id FROM chat_play_reacts WHERE room=? AND changed_at>=? AND kind<>''",
            (room, since, room, since, room, since)).fetchall()
        house = _house(conn) or -1
        ids = [int(r[0]) for r in rows if int(r[0]) != house]
        n, people, mine = len(ids), len(set(ids)), set(ids)
        _cache[key] = (t, (n, people, mine))
    level = sum(1 for m in HYPE_LEVELS if n >= m) if people >= HYPE_PEOPLE else 0
    nxt = HYPE_LEVELS[level] if level < len(HYPE_LEVELS) else None
    lo = HYPE_LEVELS[level - 1] if level else 0
    out = {"level": level, "n": n, "next": nxt,
           "progress": 1.0 if nxt is None else round(max(0.0, (n - lo) / (nxt - lo)), 3) if people >= HYPE_PEOPLE else 0.0}
    if viewer and level and int(viewer) in mine:
        ensure_tables(conn)
        got = 0
        hour = int(t // 3600)
        for lv in range(1, level + 1):
            got += award(conn, viewer, "hype", f"{room}:{hour}:{lv}", now=t, commit=False)
        conn.commit()
        k = note(conn, viewer, got, "hype")
        if k:
            out["karma"] = k
    return out


# ─── the season, getting started, friends watching ──────────────────────────

def season_best(conn, user_id) -> tuple:
    """``(league, games)``: the league this account watched most this
    season, live, and how many of its games."""
    row = conn.execute("SELECT league, COUNT(*) AS n FROM karma_watch WHERE user_id=? AND first_at>=? "
                       "GROUP BY league ORDER BY n DESC, league LIMIT 1", (int(user_id), SEASON_START)).fetchone()
    return (row[0], int(row[1])) if row else ("", 0)


def _camp_done(conn, uid: int, key: str) -> bool:
    one = lambda sql, args=(): conn.execute(sql, (uid, *args)).fetchone() is not None    # noqa: E731
    if key == "profile":
        return _has(conn, "feed_profiles") and one("SELECT 1 FROM feed_profiles WHERE user_id=?")
    if key == "follow":
        return (_has(conn, "alert_watches")
                and one("SELECT 1 FROM alert_watches WHERE user_id=? AND kind IN ('team','player') LIMIT 1"))
    if key == "watch":
        return one("SELECT 1 FROM karma_watch WHERE user_id=? LIMIT 1")
    if key == "chat":
        return one("SELECT 1 FROM karma_events WHERE user_id=? AND kind IN ('chat_day','chat') LIMIT 1")
    if key == "call":
        return _has(conn, "callit_calls") and one("SELECT 1 FROM callit_calls WHERE user_id=? LIMIT 1")
    return False


def camp(conn, user_id, now: float | None = None) -> dict | None:
    """The getting-started list while it is worth showing (an account's first
    CAMP_DAYS, until all five are done), paying each first once."""
    uid = int(user_id)
    t = time.time() if now is None else float(now)
    steps = [{"key": k, "text": w, "done": bool(_camp_done(conn, uid, k))} for k, w in CAMP]
    for x in steps:
        if x["done"]:
            award(conn, uid, "camp", x["key"], now=t, commit=False)
    finished = all(x["done"] for x in steps)
    if finished:
        award(conn, uid, "camp_done", "camp", now=t, commit=False)
    conn.commit()
    made = conn.execute("SELECT created_at FROM users WHERE id=?", (uid,)).fetchone() if _has(conn, "users") else None
    young = bool(made) and t - float(made[0] or 0) < CAMP_DAYS * 86400
    if finished or not young:
        return None
    return {"steps": steps, "done": sum(x["done"] for x in steps), "of": len(steps),
            "pts": RULES["camp"][0], "bonus": RULES["camp_done"][0]}


def friends_watching(conn, user_id, now: float | None = None, room: str = "") -> list:
    """Friends whose page is on a live game now (``room``: that game only),
    newest first, unless they turned it off. Friends only: both sides of a
    friendship (engine/social), never followers or strangers."""
    if not _has(conn, "friendships"):
        return []
    t = time.time() if now is None else float(now)
    where = " AND w.room=?" if room else ""
    rows = conn.execute(
        "SELECT w.user_id, w.room, w.league, p.handle, p.display_name, p.color FROM karma_watch w "
        "JOIN friendships f ON f.friend_id=w.user_id AND f.user_id=? "
        "JOIN friendships b ON b.user_id=w.user_id AND b.friend_id=? "
        "LEFT JOIN feed_profiles p ON p.user_id=w.user_id "
        "LEFT JOIN karma_prefs k ON k.user_id=w.user_id "
        f"WHERE w.last_at>=? AND COALESCE(k.share, 1)=1{where} ORDER BY w.last_at DESC LIMIT 40",
        (int(user_id), int(user_id), t - FRIEND_FRESH_S, *((room,) if room else ()))).fetchall() \
        if _has(conn, "feed_profiles") else []
    seen, out = set(), []
    for uid, rm, lg, handle, name, color in rows:
        if uid in seen or not handle:
            continue
        seen.add(uid)
        # A game the scoreboard calls over drops off; one it no longer
        # carries is taken on the page's word.
        g = _live_game(rm)
        if (g.get("state") or "") not in ("live", ""):
            continue
        out.append({"handle": handle, "name": name or "", "color": int(color or 0), "room": rm, "league": lg,
                    "away": g.get("away", ""), "home": g.get("home", "")})
    return out


# ─── karma alerts ───────────────────────────────────────────────────────────

def _next_mark(n: int):
    return next((m for m in sorted(STREAK_BONUS) if m > n), None)


def alerts_pass(conn, now: float | None = None) -> int:
    """Queue each opted-in account's karma alerts (engine/pushmine sends
    them): the evening nudge before the days in a row would end, the
    Monday trophy, a new tier. Each once (its id), only to phones that
    carry the topic. Returns how many were queued."""
    from . import pushalerts as PA
    from . import pushmine as PM
    ensure_tables(conn)
    t = time.time() if now is None else float(now)
    et = _dt.datetime.fromtimestamp(t, tz=_ET)
    hour = et.hour + et.minute / 60
    today = et.date().isoformat()
    quiet = PA.quiet_now(et)
    told = 0
    for uid, told_level in conn.execute("SELECT user_id, told_level FROM karma_prefs WHERE remind=1").fetchall():
        uid = int(uid)
        if not PM.asked(conn, uid, ALERT_TOPIC):
            continue
        # The evening nudge: a run that would end at midnight, nothing yet today.
        if STREAK_NUDGE_HOURS[0] <= hour < STREAK_NUDGE_HOURS[1]:
            st = streak(days_of(conn, uid), today)
            if st["now"] >= STREAK_NUDGE_MIN and not st["today"] and not st["rest"]:
                mark = _next_mark(st["now"])
                close = f" {mark - st['now']} more for the {mark}-day bonus." if mark and mark - st["now"] <= 2 else ""
                told += PM.tell(conn, uid, f"karma:streak:{today}", ALERT_TOPIC,
                                f"Your {st['now']}-day streak ends at midnight",
                                "Open Live or a game for a minute to keep it going." + close, "/#live",
                                ttl="karma", now=t)
        if quiet:
            continue
        # Monday: last week's trophy (paid here if the Karma tab has not been opened).
        if et.weekday() == 0 and 9 <= et.hour < 21:
            week = _shift(week_of(t), -7)
            trophies(conn, uid, t)
            rank = next((r for who, r in _week_results(conn, week) if who == uid), None)
            if rank:
                told += PM.tell(conn, uid, f"karma:trophy:{week}", ALERT_TOPIC,
                                f"#{rank} on last week's karma ladder",
                                f"+{TROPHY.get(rank, 0)} karma and a trophy on your profile.", "/#account",
                                ttl="karma_week", now=t)
            else:
                # Everyone else: their week in a line (Duolingo's and
                # Strava's Monday recap), when there was one.
                lo, hi = day_start(week), day_start(_shift(week, 7))
                got = int(conn.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=? AND at>=? "
                                       "AND at<? AND kind<>'trophy'", (uid, lo, hi)).fetchone()[0] or 0)
                if got > 0:
                    days = conn.execute("SELECT COUNT(DISTINCT day) FROM karma_events WHERE user_id=? AND at>=? "
                                        "AND at<?", (uid, lo, hi)).fetchone()[0]
                    told += PM.tell(conn, uid, f"karma:week:{week}", ALERT_TOPIC,
                                    f"Your week: +{got:,} karma",
                                    f"{days} day{'s' if days != 1 else ''} on Qellys, level {level_of(total(conn, uid))} "
                                    "now. A new week's ladder starts today.", "/#account", ttl="karma_week", now=t)
        # A new tier since the last one told.
        lv = level_of(total(conn, uid))
        tier_at = max(at for at, _, _ in TIERS if at <= lv)
        if tier_at > int(told_level or 0) and tier_at > 1:
            name = tier_of(lv)[0]
            told += PM.tell(conn, uid, f"karma:tier:{tier_at}", ALERT_TOPIC, f"Level {lv}: you're {name} now",
                            f"Everyone in the chats sees {name} beside your name.", "/#account", ttl="karma", now=t)
            conn.execute("UPDATE karma_prefs SET told_level=? WHERE user_id=?", (lv, uid))
    conn.commit()
    return told


# ─── what the pages read ────────────────────────────────────────────────────

def _prefs(conn, user_id) -> dict:
    row = conn.execute("SELECT flair, ladder, seen_level, remind, share, pins FROM karma_prefs WHERE user_id=?",
                       (int(user_id),)).fetchone()
    return {"flair": row[0] if row else "", "ladder": bool(row[1]) if row else True,
            "seen_level": int(row[2]) if row else 0, "remind": bool(row[3]) if row else False,
            "share": bool(row[4]) if row else True,
            "pins": [x for x in str(row[5] or "").split(",") if x] if row else []}


def reminds(conn, user_id) -> bool:
    """Does this account want karma alerts? (engine/pushalerts.subscribe
    asks, so a phone signed in to it carries the topic.)"""
    try:
        row = conn.execute("SELECT remind FROM karma_prefs WHERE user_id=?", (int(user_id),)).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])


def phones(conn, user_id) -> int:
    """How many phones signed in to this account take alerts at all."""
    if not _has(conn, "push_subs"):
        return 0
    return int(conn.execute("SELECT COUNT(*) FROM push_subs WHERE user_id=?", (int(user_id),)).fetchone()[0] or 0)


def _relink(conn, user_id, on: bool) -> None:
    """Put the karma topic on (or take it off) every phone signed in to the
    account, the way a subscribe from the Alerts page would."""
    if not _has(conn, "push_subs"):
        return
    for endpoint, topics in conn.execute("SELECT endpoint, topics FROM push_subs WHERE user_id=?",
                                         (int(user_id),)).fetchall():
        have = [t for t in str(topics or "").split(",") if t and t != ALERT_TOPIC]
        conn.execute("UPDATE push_subs SET topics=? WHERE endpoint=?",
                     (",".join(have + ([ALERT_TOPIC] if on else [])), endpoint))


def set_prefs(conn, user_id, flair=None, ladder=None, remind=None, share=None, pins=None) -> tuple[int, dict]:
    ensure_tables(conn)
    conn.execute("INSERT OR IGNORE INTO karma_prefs (user_id) VALUES (?)", (int(user_id),))
    if pins is not None:
        known = {f[0] for f in FAMILIES} | {o[0] for o in ONE_OFF}
        keep = list(dict.fromkeys(str(k) for k in pins if str(k) in known))
        if len(keep) > PINS_MAX:
            return 400, {"error": f"Pin up to {PINS_MAX} badges."}
        earned = {b["key"] for b in badges(conn, user_id) if b["tier"]}
        if any(k not in earned for k in keep):
            return 400, {"error": "Pin a badge you have earned."}
        conn.execute("UPDATE karma_prefs SET pins=? WHERE user_id=?", (",".join(keep), int(user_id)))
    if share is not None:
        conn.execute("UPDATE karma_prefs SET share=? WHERE user_id=?", (1 if share else 0, int(user_id)))
    if remind is not None:
        # From now on: the tiers already reached are not news.
        conn.execute("UPDATE karma_prefs SET remind=?, told_level=? WHERE user_id=?",
                     (1 if remind else 0, level_of(total(conn, user_id)), int(user_id)))
        _relink(conn, user_id, bool(remind))
    if flair is not None:
        flair = str(flair)
        if flair and flair not in FLAIRS:
            return 400, {"error": "Pick one of the flairs shown."}
        if flair and level_of(total(conn, user_id)) < FLAIR_AT:
            return 403, {"error": f"Flair opens at level {FLAIR_AT}."}
        conn.execute("UPDATE karma_prefs SET flair=? WHERE user_id=?", (flair, int(user_id)))
    if ladder is not None:
        conn.execute("UPDATE karma_prefs SET ladder=? WHERE user_id=?", (1 if ladder else 0, int(user_id)))
    conn.commit()
    _cache.clear()
    return 200, {"ok": True, **{k: v for k, v in _prefs(conn, user_id).items() if k != "seen_level"},
                 "phones": phones(conn, user_id)}


def cards(conn, user_ids, now: float | None = None) -> dict:
    """``{user_id: {"lv", "cls", "flair"}}`` for the names in a chat, each
    read at most once a minute. The site's own account has none."""
    t = time.time() if now is None else float(now)
    out = {}
    try:
        _prepare(conn)
        house = _house(conn)
        for uid in {int(u) for u in user_ids or []}:
            if uid == house:
                continue
            hit = _cache.get(("card", uid))
            if hit and t - hit[0] < CACHE_S:
                card = hit[1]
            else:
                lv = level_of(total(conn, uid))
                flair = _prefs(conn, uid)["flair"] if lv >= FLAIR_AT else ""
                card = {"lv": lv, "cls": tier_of(lv)[1], **({"flair": flair} if flair else {})}
                _cache[("card", uid)] = (t, card)
            out[uid] = card
    except sqlite3.Error:
        return {}
    if len(_cache) > 5000:
        _cache.clear()
    return out


def public(conn, user_id) -> dict:
    """A profile's karma, as anybody may see it: the level, its tier, the
    total, the best badges and the days in a row."""
    _prepare(conn)
    pts = total(conn, user_id)
    st = streak(days_of(conn, user_id), day_of(time.time()))
    lv = level_view(pts)
    prefs = _prefs(conn, user_id)
    flair = prefs["flair"] if lv["level"] >= FLAIR_AT else ""
    return {**lv, "flair": flair, "streak": st["now"],
            "badges": top_badges(badges(conn, user_id, pts, st["best"]), pins=prefs["pins"])}


def me(conn, user_id, now: float | None = None, data_dir: Path | None = None, checkin: bool = True) -> dict:
    """The Karma tab and the Live tab's strip: the level and the way to the
    next, the days in a row, the day's quests, every badge, the week's
    place, the flair and what the last few karma were for. Opening it is
    the day's check-in, pays what is owed and says once when a level was
    crossed since the last look."""
    _prepare(conn)
    t = time.time() if now is None else float(now)
    uid = int(user_id)
    today = day_of(t)
    if checkin:
        award(conn, uid, "day", today, now=t, commit=False)
    sync_user(conn, uid, t, data_dir)
    q = quests(conn, uid, today, t)
    st = streak(days_of(conn, uid), today)
    if st["now"] and st["start"]:
        for mark, pts in STREAK_BONUS.items():
            if st["now"] >= mark:
                award(conn, uid, "streak_bonus", f"{st['start']}:{mark}", pts=pts, now=t, commit=False)
    if _has(conn, "callit_calls"):
        run, first = 0, None
        for (right, at) in conn.execute("SELECT won, at FROM callit_calls WHERE user_id=? AND won IS NOT NULL "
                                        "ORDER BY at DESC LIMIT 200", (uid,)):
            if not right:
                break
            run, first = run + 1, at
        for k in range(CALL_RUN, run + 1, CALL_RUN):
            award(conn, uid, "call_streak", f"{int(first or 0)}:{k}", now=t, commit=False)
    trophies(conn, uid, t)
    conn.commit()
    pts = total(conn, uid)
    prefs = _prefs(conn, uid)
    lv = level_view(pts)
    out = {**lv, "streak": st, "quests": q, "badges": badges(conn, uid, pts, st["best"]),
           "flair": prefs["flair"] if lv["level"] >= FLAIR_AT else "", "flairs": list(FLAIRS),
           "ladder_on": prefs["ladder"], "remind": prefs["remind"], "phones": phones(conn, uid),
           "share": prefs["share"], "pins": prefs["pins"], "pins_max": PINS_MAX,
           "camp": camp(conn, uid, t), "friends": friends_watching(conn, uid, t),
           "season": dict(zip(("league", "games"), season_best(conn, uid))),
           "unlocks": {"flair": FLAIR_AT, "color": COLOR_AT, "ring": RING_AT},
           "week": ladder(conn, "week", uid, t, n=10),
           "today": int(conn.execute("SELECT COALESCE(SUM(pts), 0) FROM karma_events WHERE user_id=? AND day=?",
                                     (uid, today)).fetchone()[0] or 0),
           "recent": [{"kind": k, "why": RULES.get(k, (0, 0, k))[2], "pts": int(p), "at": float(a)}
                      for k, p, a in conn.execute("SELECT kind, pts, at FROM karma_events WHERE user_id=? AND pts>0 "
                                                  "ORDER BY at DESC LIMIT 12", (uid,))],
           "rules": [{"kind": k, "pts": v[0], "cap": v[1], "why": v[2]} for k, v in RULES.items() if v[0] > 0]}
    if prefs["seen_level"] and lv["level"] > prefs["seen_level"]:
        out["up_from"] = prefs["seen_level"]
    if lv["level"] != prefs["seen_level"]:
        conn.execute("INSERT INTO karma_prefs (user_id, seen_level) VALUES (?, ?) "
                     "ON CONFLICT(user_id) DO UPDATE SET seen_level=excluded.seen_level", (uid, lv["level"]))
        conn.commit()
    return out


def export_user(conn, user_id) -> dict:
    out = {}
    if _has(conn, "karma_events"):
        rows = [{"kind": k, "for": r, "karma": p, "at": a} for k, r, p, a in conn.execute(
            "SELECT kind, ref, pts, at FROM karma_events WHERE user_id=? ORDER BY at", (int(user_id),))]
        if rows:
            out["karma"] = rows
    if _has(conn, "karma_watch"):
        rows = [{"game": r, "league": lg, "first": f, "last": la} for r, lg, f, la in conn.execute(
            "SELECT room, league, first_at, last_at FROM karma_watch WHERE user_id=? ORDER BY first_at", (int(user_id),))]
        if rows:
            out["live_games_watched"] = rows
    if _has(conn, "karma_prefs"):
        row = conn.execute("SELECT flair, ladder FROM karma_prefs WHERE user_id=?", (int(user_id),)).fetchone()
        if row:
            out["karma_settings"] = {"flair": row[0], "on_ladders": bool(row[1])}
    if _has(conn, "karma_weeks"):
        rows = [{"week": w, "rank": r, "karma": p} for w, r, p in conn.execute(
            "SELECT week, rank, pts FROM karma_weeks WHERE user_id=? ORDER BY week", (int(user_id),))]
        if rows:
            out["karma_weeks_top_ten"] = rows
    return out


def report(conn) -> list:
    """Read-only: how much karma there is and who leads (the runbook's check)."""
    if not _has(conn, "karma_events"):
        return ["karma: no rows yet (the tables are made by the first page that asks)"]
    n, people, pts = conn.execute("SELECT COUNT(*), COUNT(DISTINCT user_id), COALESCE(SUM(pts), 0) "
                                  "FROM karma_events").fetchone()
    back = conn.execute("SELECT value FROM karma_meta WHERE key='backfill_v1'").fetchone() if _has(conn, "karma_meta") else None
    out = [f"karma: {n} rows, {people} accounts, {pts} karma in all; "
           f"history counted: {'yes' if back else 'not yet (the first page to show karma does it)'}"]
    for kind, c, s in conn.execute("SELECT kind, COUNT(*), SUM(pts) FROM karma_events GROUP BY kind ORDER BY SUM(pts) DESC"):
        out.append(f"   {kind:<13} {c:>7} rows {int(s or 0):>9} karma")
    if _has(conn, "feed_profiles"):
        top = conn.execute("SELECT p.handle, SUM(e.pts) AS s FROM karma_events e JOIN feed_profiles p ON p.user_id=e.user_id "
                           "GROUP BY e.user_id ORDER BY s DESC LIMIT 5").fetchall()
        if top:
            out.append("   most karma: " + ", ".join(f"@{h} {int(s):,} (level {level_of(s)})" for h, s in top))
    return out


def main(argv=None) -> int:
    """``python3 -m engine.karma``: the report above, off the accounts
    database opened read-only."""
    from . import accounts as A
    conn = sqlite3.connect(f"file:{A.DB_PATH}?mode=ro", uri=True)
    try:
        for line in report(conn):
            print(line)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
