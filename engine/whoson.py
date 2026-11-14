"""Who is on the site right now, and which page: the owner's view.

Ethan, 2026-11-01: "add a feature ONLY AVALIBLE for my Qellys Book account
on the site that lets me see all active users. It shows me all users and
what page they are on."

WHAT IS HELD, IN MEMORY ONLY. Each open tab of the site says, when its page
changes and once a minute while it is in front of somebody, which of our
pages it shows (the page's own view name, "likely", "pbp" ..., and the
league, or for a game its room, "nfl_401873033") and a random number the
tab made up for itself and forgets when it closes. The server keeps the
latest of each for HERE_S seconds and then forgets it. It is never written
to a disk or a database and does not outlive a restart; a tab that closes
says so and is dropped at once. Nothing else: no address, no device, no
clicks, nothing typed.

WHO SEES IT. The site's own account, the verified handle Qellys_Book that
only the owner's claim on the box can hand out (engine/socialfeed.claim),
and the box's owner token. To anybody else the endpoint answers as if it
did not exist.

BY NAME ONLY AFTER THE NOTICE (the Privacy Policy's §2.13 and §13). Until
1 November the policy said the site's page counts "cannot say what any one
person did", so a signed-in member is named only when engine/policynotice
says the change of 2026-11-01 may count them (an account made after it,
one emailed a week ago or more, or a phone sign-in a week after it was
posted) and they have not turned off "Show me in Who's on now" (Settings →
Your data, the `whoson` setting). Every other member, and every visitor,
is a number on the page they have open.

Standard library only.
"""
from __future__ import annotations

import re
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
#: The Privacy Policy's section on it; until it is there nothing is kept.
POLICY = ROOT / "web" / "privacy.html"
POLICY_ID = "who-is-on"
#: The site's own account (engine/socialfeed.claim's handle).
SITE_HANDLE = "Qellys_Book"
#: A tab that has not said anything for this long has left.
HERE_S = 150
#: Tabs held at most: past it the stalest go first (a scraper, not a crowd).
MAX_TABS = 5000
#: What a tab may say: our own page names, a league or a game's room.
VIEW = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
DETAIL = re.compile(r"^(?:[a-z]{2,8}|(?:nfl|cfb|nba|wnba|nhl|mlb|cbb)_[0-9]{1,14})$")
TAB = re.compile(r"^[a-f0-9]{16}$")

_LOCK = threading.Lock()
_TABS: dict = {}           # tab -> {"uid", "view", "detail", "first", "since", "at"}


def policy_ready(path: Path | None = None) -> bool:
    try:
        return f'id="{POLICY_ID}"' in (path or POLICY).read_text(encoding="utf-8")
    except OSError:
        return False


def shown(settings) -> bool:
    """Is this member willing to be named? Yes unless they said no."""
    return not (isinstance(settings, dict) and settings.get("whoson") == "off")


def changed(old_settings, new_settings) -> str | None:
    """The consent log's words when a member's choice moved, else None."""
    a, b = shown(old_settings), shown(new_settings)
    return None if a == b else ("shown by name in Who's on now" if b else "not shown by name in Who's on now")


def beat(tab, uid, view, detail="", now: float | None = None) -> bool:
    """A tab's page, now. False (and nothing kept) for anything malformed."""
    tab, view, detail = str(tab or ""), str(view or ""), str(detail or "")
    if not TAB.match(tab) or not VIEW.match(view) or (detail and not DETAIL.match(detail)):
        return False
    t = time.time() if now is None else float(now)
    uid = int(uid) if uid else None
    with _LOCK:
        was = _TABS.get(tab)
        same_tab = bool(was) and was["uid"] == uid and t - was["at"] <= HERE_S
        first = was["first"] if same_tab else t
        since = was["since"] if same_tab and (was["view"], was["detail"]) == (view, detail) else t
        _TABS[tab] = {"uid": uid, "view": view, "detail": detail, "first": first, "since": since, "at": t}
        if len(_TABS) > MAX_TABS:
            for k in sorted(_TABS, key=lambda k: _TABS[k]["at"])[:len(_TABS) - MAX_TABS]:
                _TABS.pop(k, None)
    return True


def leave(tab) -> None:
    """The tab closed: gone now, not in HERE_S."""
    with _LOCK:
        _TABS.pop(str(tab or ""), None)


def live(now: float | None = None) -> list:
    """Every tab heard from in the last HERE_S seconds (the rest forgotten)."""
    t = time.time() if now is None else float(now)
    with _LOCK:
        for k in [k for k, v in _TABS.items() if t - v["at"] > HERE_S]:
            _TABS.pop(k, None)
        return [dict(v) for v in _TABS.values()]


def clear() -> None:
    with _LOCK:
        _TABS.clear()


def _reads_the_desk(conn, user_id) -> bool:
    from . import siteowners as SO
    return SO.is_owner(conn, user_id)


def is_site_account(conn, user_id) -> bool:
    """The verified Qellys_Book account, and no other."""
    if not user_id:
        return False
    from . import socialfeed as SF
    prof = SF.profile_of(conn, int(user_id)) or {}
    return bool(prof.get("verified")) and str(prof.get("handle") or "").lower() == SITE_HANDLE.lower()


def nameable(conn, uids, now: float | None = None) -> set:
    """Of these members, the ones the page may name: told of the change
    (engine/policynotice) and not opted out (the `whoson` setting). The
    site's own account is the one reading the page, so it is named from the
    first day: showing an account to itself tells nobody anything, and its
    own row is how the owner sees the names work before anyone else's can."""
    from . import accounts as A
    from . import policynotice as PN
    ok = PN.may_count(conn, uids, now, notice=PN.WHOSON)
    out = set()
    for uid in ok:
        try:
            settings = (A.get_sections(conn, uid).get("settings") or {}).get("data")
        except Exception:                           # noqa: BLE001 — unreadable settings: not named
            continue
        if shown(settings):
            out.add(int(uid))
    for uid in uids:
        if int(uid) not in out and _reads_the_desk(conn, uid):
            out.add(int(uid))
            break                                   # there is one
    return out


def _game(detail: str, data_dir: Path | None) -> dict:
    """A game room's two sides and state, off the league's fast scoreboard."""
    from . import gamechat as GC
    try:
        g = GC.game_of(detail, data_dir) if GC.room_ok(detail) else {}
    except Exception:                               # noqa: BLE001 — a missing file is just no label
        g = {}
    return {k: g.get(k) for k in ("away", "home", "state")} if g else {}


def snapshot(conn, now: float | None = None, data_dir: Path | None = None) -> dict:
    """The owner's page: members by name where they may be, a count of the
    rest, visitors by count, and every page with how many are on it."""
    from . import socialfeed as SF
    t = time.time() if now is None else float(now)
    tabs = live(t)
    by_uid: dict = {}
    visitors = []
    for v in tabs:
        (by_uid.setdefault(v["uid"], []) if v["uid"] else visitors).append(v)
    named = nameable(conn, list(by_uid), t) if by_uid else set()
    members, pages, games = [], {}, {}
    hidden = 0

    def page(v, who):
        key = (v["view"], v["detail"])
        p = pages.setdefault(key, {"view": v["view"], "detail": v["detail"], "members": 0, "visitors": 0})
        p[who] += 1
        if v["detail"] and "_" in v["detail"] and v["detail"] not in games:
            games[v["detail"]] = _game(v["detail"], data_dir)

    for uid, mine in by_uid.items():
        top = max(mine, key=lambda v: v["at"])
        page(top, "members")
        if uid not in named:
            hidden += 1
            continue
        prof = SF.profile_of(conn, uid) or {}
        members.append({"handle": prof.get("handle") or "", "name": prof.get("name") or "",
                        "color": int(prof.get("color") or 0), "verified": bool(prof.get("verified")),
                        "view": top["view"], "detail": top["detail"], "tabs": len(mine),
                        "on_page_s": int(t - top["since"]), "on_site_s": int(t - min(v["first"] for v in mine)),
                        "seen_s": int(t - top["at"])})
    for v in visitors:
        page(v, "visitors")
    members.sort(key=lambda m: (m["seen_s"], m["handle"].lower()))
    rows = sorted(pages.values(), key=lambda p: (-(p["members"] + p["visitors"]), p["view"], p["detail"]))
    for p in rows:
        if p["detail"] in games and games[p["detail"]]:
            p["game"] = games[p["detail"]]
    for m in members:
        if m["detail"] in games and games[m["detail"]]:
            m["game"] = games[m["detail"]]
    return {"at": t, "window_s": HERE_S, "members": members, "unnamed_members": hidden,
            "members_total": len(by_uid), "visitors": len(visitors), "pages": rows}
