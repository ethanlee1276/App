"""Everything kept about one member, counted — the "What we keep" screen
(Settings → Your data), with every yes and no they gave us.

Ethan's second research paper (2026-10-29): show members "their own
computed profile ... your transparency promise made visible". The Privacy
Policy names every table; this counts THIS member's rows in each, grouped
the way a person thinks of them (their account, what they track, their
alerts, what they post and play, how they use the site, their choices),
with how long each group is kept. It reads the database itself: any table
holding a person that the map below does not name is listed under "Other"
by its own name, so nothing kept can be left off the screen.

Counts only, for the signed-in member, never anyone else's rows; the rows
themselves are in Download my data (engine/accounts.export_user).
Standard library only.
"""
from __future__ import annotations

import re
import sqlite3

#: The columns that name a person, and which of them are this member's.
PERSON = ("user_id", "from_id", "to_id", "referred_id", "referrer_id", "follower_id", "followee_id")
_SAFE = re.compile(r"^[a-z_][a-z0-9_]*$")

#: (title, kept, [(table, what), ...]) in the order the screen reads.
GROUPS = (
    ("Your account", "until you delete the account; sessions until they expire", (
        ("sessions", "devices signed in"), ("passkeys", "passkeys"), ("passkey_users", "passkey handle"),
        ("passkey_challenges", "passkey sign-ins in flight"), ("password_resets", "reset links"),
        ("subscriptions", "membership"), ("code_redemptions", "codes redeemed"), ("code_attempts", "code tries"),
        ("gift_codes", "gifts bought"), ("referral_codes", "your invite code"), ("referrals", "invites"))),
    ("What you track", "until you delete it or the account; closing prices 90 days", (
        ("user_data", "synced sections (My Bets, settings, fantasy, bankroll, searches)"),
        ("bet_clv", "closing prices of your parlays' legs"), ("slip_alerts", "parlay alerts sent"),
        ("slip_alert_optin", "last-leg email choice"), ("slip_chance", "parlay chance history"),
        ("alert_watches", "watches"), ("alert_seen", "watch hits seen"),
        ("streak_picks", "streak picks"), ("streak_state", "streak"))),
    ("Your alerts", "until you turn them off; what they said, a day", (
        ("push_subs", "phones with alerts on"), ("push_mine", "your own alerts waiting"),
        ("push_watch_seen", "watch alerts sent"), ("push_lineup_leagues", "fantasy league for lineup alerts"),
        ("push_activities", "parlays on your lock screen"), ("push_game_activities", "games on your lock screen"),
        ("news_seen", "injury statuses last told you"), ("digest_optin", "email choices"),
        ("calendar_links", "calendar link"), ("widget_links", "widget link"))),
    ("What you post and play", "chats 14 days, posts 120 days, the rest until you delete them or the account", (
        ("chat_msgs", "game chat messages"), ("chat_reacts", "reactions"), ("chat_play_reacts", "play reactions"),
        ("chat_votes", "who-wins votes"), ("chat_potg", "player of the game votes"),
        ("chat_reminders", "game reminders"), ("chat_reports", "reports you made"),
        ("chat_parties", "watch parties started"), ("chat_party_members", "watch parties joined"),
        ("feed_posts", "posts"), ("feed_comments", "comments"), ("feed_likes", "likes"),
        ("feed_comment_likes", "comment likes"), ("feed_votes", "poll votes"), ("feed_tails", "tails and fades"),
        ("feed_pins", "pinned badges"), ("feed_notifs", "activity notices"), ("feed_reports", "post reports"),
        ("feed_blocks", "people blocked"), ("feed_profiles", "profile"), ("feed_follows", "follows"),
        ("dm_messages", "direct messages"), ("message_deletes", "messages deleted"),
        ("parlay_shares", "parlays shared"), ("pick_shares", "picks shared"), ("friendships", "friends"),
        ("friend_requests", "friend requests"), ("friend_invites", "friend invites"),
        ("friend_nicknames", "nicknames"), ("callit_calls", "Call it calls"), ("trivia_answers", "trivia answers"),
        ("pickem_picks", "pick'em picks"), ("pickem_prefs", "pick'em choices"),
        ("pickem_group_members", "pick'em groups you are in"), ("tf_calls", "tail or fade calls"),
        ("karma_events", "karma"), ("karma_weeks", "karma weeks"), ("karma_prefs", "karma choices"),
        ("karma_watch", "games watched for karma"))),
    ("How you use the site", "only with your yes; 120 days", (
        ("activity_days", "days of your activity"), ("activity_prefs", "your yes or no"),
        ("engagement_away", "\"while you were away\" alerts"))),
    ("Your choices", "until you delete the account", (
        ("consent_log", "yeses and noes, each with the policy's date"),
        ("policy_notices", "changes to our documents we emailed you about"))),
)


def _tables(conn) -> dict:
    """{table: [its person columns]} for every table in the database that names one."""
    out = {}
    for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
        if not _SAFE.match(str(name)):
            continue
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({name})")]
        who = [c for c in cols if c in PERSON]
        if who:
            out[name] = who
    return out


def _count(conn, table: str, cols: list, user_id: int) -> int:
    where = " OR ".join(f"{c} = ?" for c in cols)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}",
                                (int(user_id),) * len(cols)).fetchone()[0])
    except sqlite3.Error:
        return 0


def summary(conn, user_id) -> list[dict]:
    """[{"title", "kept", "n", "items": [{"what", "n"}]}] — this member's
    rows, every table that names a person, the empty ones left out."""
    have = _tables(conn)
    named = set()
    out = []
    for title, kept, items in GROUPS:
        rows = []
        for table, what in items:
            named.add(table)
            if table in have:
                n = _count(conn, table, have[table], user_id)
                if n:
                    rows.append({"what": what, "n": n})
        if title == "Your account":
            rows.insert(0, {"what": "your email or phone, the password check, when you joined", "n": 1})
        if rows:
            out.append({"title": title, "kept": kept, "n": sum(r["n"] for r in rows), "items": rows})
    other = [{"what": t, "n": n} for t in sorted(set(have) - named)
             if (n := _count(conn, t, have[t], user_id))]
    if other:
        out.append({"title": "Other", "kept": "as the Privacy Policy says for each", "n": sum(r["n"] for r in other),
                    "items": other})
    return out
