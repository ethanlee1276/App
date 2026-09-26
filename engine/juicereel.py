"""Juice Reel → Zeno's Record, automatically.

Ethan, 2026-09-21: *"instead of me having to import my juice reel record
every time i make a bet, can we make a way to sync my juice reel to the
site so all my bets will automatically sync to the site, since every
sportsbook i have is synced with juice reel."*

JUICE REEL HAS AN API, and its docs (juicereel.com/api-docs) say the
thing that makes this simple: every bets endpoint accepts *"Owner only:
Client ID + secret"*. No browser login, no consent screen, no refresh
tokens to rotate — for the account that owns the OAuth application, the
two keys ARE the credential. This module reads Ethan's own bets from
`GET /oauth2/bets/changed`, which the docs describe as the feed built
"for reconciliation": open, closed and cancelled bets together, newest
`updatedAt` first, with a cursor. Their instruction is followed to the
letter — store the newest `updatedAt` from each page as the checkpoint,
pass it back as `updatedAtAfter` next time, stop paging when a returned
bet is older than the checkpoint.

THE KEYS LIVE WHERE EVERY OTHER KEY LIVES: `/etc/qellys/env`, as
`QB_JUICEREEL_CLIENT_ID` and `QB_JUICEREEL_CLIENT_SECRET`. Never in
source, never in a URL, never printed. With either missing the sync
says so once and does nothing — the manual import stays.

A JUICE REEL BET IS ONE TICKET WITH `Subbets` — a straight has one, a
parlay has several. The store already thinks that way, so a ticket maps
to one row with the legs listed. Money is the ticket's: `amountRisked`
(or `adjustedRisk` when Juice Reel says the real risk differed, e.g. a
free play) and `netResult`, which is signed PROFIT — the payout is the
stake back plus it.

NEVER INTO THE BUILD. This runs from the settle pass beside the other
learning steps, and a Juice Reel outage or a bad key prints a warning
and leaves the record exactly as it was. One person's tickets must not
take the model's record down with them.
"""

from __future__ import annotations

import base64
import datetime as _dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://external-api.juicereel.com"
CLIENT_ID_ENV = "QB_JUICEREEL_CLIENT_ID"
CLIENT_SECRET_ENV = "QB_JUICEREEL_CLIENT_SECRET"
SOURCE = "juicereel-api"

#: Where the sync remembers how far it got. In data/ because that is the
#: directory the service may write (ReadWritePaths in the unit file).
CHECKPOINT = Path(os.environ.get("QB_JUICEREEL_STATE", "").strip()
                  or (Path(__file__).resolve().parents[1] / "data"
                      / "juicereel_sync.json"))

#: Pages per sync, as a ceiling. The first sync walks the whole history;
#: after that a page or two covers a day. Fifty pages is thousands of
#: tickets and well inside the 25,000-per-five-minutes limit.
MAX_PAGES = 50
TIMEOUT_S = 20


# --- credentials --------------------------------------------------------------
def credentials() -> tuple[str, str] | None:
    cid = os.environ.get(CLIENT_ID_ENV, "").strip()
    sec = os.environ.get(CLIENT_SECRET_ENV, "").strip()
    return (cid, sec) if cid and sec else None


def _headers(cid: str, sec: str) -> dict:
    basic = base64.b64encode(f"{cid}:{sec}".encode()).decode()
    return {"Authorization": f"Basic {basic}",
            "X-OAuth-Client-Id": cid,
            "Accept": "application/json",
            "User-Agent": "qellys-zeno-sync/1"}


def _get(path: str, params: dict, cid: str, sec: str, opener=None) -> dict:
    """One GET. `opener` is for tests; the real one is urllib."""
    url = API + path
    q = {k: v for k, v in params.items() if v}
    if q:
        url += "?" + urllib.parse.urlencode(q)
    if opener is not None:
        return opener(url, _headers(cid, sec))
    req = urllib.request.Request(url, headers=_headers(cid, sec))
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


# --- the checkpoint -----------------------------------------------------------
def load_checkpoint(path=None) -> dict:
    p = Path(path or CHECKPOINT)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_checkpoint(state: dict, path=None) -> None:
    p = Path(path or CHECKPOINT)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1), encoding="utf-8")


# --- one Juice Reel bet → one store row ----------------------------------------
def _leg_text(sb: dict) -> str:
    """"Chiefs -3.5" from a subbet, the way a person would say it."""
    kind = str(sb.get("subbetType") or "").strip()
    pos = str(sb.get("position") or "").strip()
    val = sb.get("value")
    desc = str(sb.get("description") or "").strip()
    if desc and pos and pos not in desc:
        desc = f"{pos} — {desc}"
    if kind.lower() in ("spread", "total", "totals", "over", "under") \
            and val not in (None, 0, "0"):
        try:
            v = float(val)
            sign = "+" if v > 0 and kind.lower() == "spread" else ""
            return f"{pos} {sign}{v:g}".strip() if pos else f"{kind} {sign}{v:g}"
        except (TypeError, ValueError):
            pass
    return desc or pos or kind or "bet"


def _sport(bet: dict, sb: dict | None) -> str | None:
    for src in (sb or {}, bet):
        lg = (src.get("League") or {}).get("name")
        if lg:
            return str(lg).strip().lower()
    for src in (sb or {}, bet):
        sp = (src.get("Sport") or {}).get("name")
        if sp:
            return str(sp).strip().lower()
    return None


def _event(sb: dict) -> str | None:
    ev = sb.get("Event") or {}
    away = (ev.get("AwayTeam") or {}).get("displayName") or (ev.get("AwayTeam") or {}).get("name")
    home = (ev.get("HomeTeam") or {}).get("displayName") or (ev.get("HomeTeam") or {}).get("name")
    if away and home:
        return f"{away} @ {home}"
    return ev.get("name") or ev.get("description") or None


def to_row(bet: dict) -> dict | None:
    """The store's shape for one Juice Reel ticket, or None."""
    if not isinstance(bet, dict) or bet.get("id") is None:
        return None
    subs = [s for s in (bet.get("Subbets") or []) if isinstance(s, dict)]
    status = str((bet.get("BetStatus") or {}).get("statusName") or "").lower()
    result_word = str(bet.get("result")
                      or (bet.get("BetResult") or {}).get("name") or "")
    if status == "cancelled" or status == "canceled":
        result = "void"
    elif status and status != "closed":
        result = "open"
    else:
        from .zeno import _result
        result = _result(result_word)
        if result == "open":               # closed, but the word was unknown
            net = bet.get("netResult")
            try:
                n = float(net)
                result = "won" if n > 0 else ("lost" if n < 0 else "push")
            except (TypeError, ValueError):
                result = "open"
    stake = bet.get("amountRisked")
    if bet.get("adjustedRisk") is not None:
        stake = bet.get("adjustedRisk")
    try:
        stake_f = float(stake)
    except (TypeError, ValueError):
        return None
    payout = None
    if result not in ("open",):
        try:
            payout = round(max(0.0, stake_f + float(bet.get("netResult"))), 2)
        except (TypeError, ValueError):
            payout = None
    legs = [_leg_text(s) for s in subs]
    kind = str((bet.get("BetType") or {}).get("typeName") or "").lower()
    if len(subs) > 1:
        selection = f"{len(subs)}-leg {kind or 'parlay'}: " + " / ".join(legs)
        market = kind or "parlay"
    else:
        selection = legs[0] if legs else (kind or "bet")
        market = str((subs[0].get("subbetType") if subs else "") or kind
                     or "").lower() or None
    first = subs[0] if subs else {}
    starts = [s.get("startDate") for s in subs if s.get("startDate")]
    line = None
    if len(subs) == 1:
        v = first.get("value")
        try:
            line = float(v) if v not in (None, "", 0, "0") else None
        except (TypeError, ValueError):
            line = None
    return {
        "book": (bet.get("Site") or {}).get("name") or "other",
        "external_id": str(bet["id"]),
        "placed_at": bet.get("datePlaced"),
        "event_at": min(starts) if starts else None,
        "sport": _sport(bet, first),
        "event": _event(first) if len(subs) == 1 else None,
        "market": market,
        "selection": selection[:200],
        "line": line,
        "odds": bet.get("oddsAmerican"),
        "stake": round(stake_f, 2),
        "payout": payout,
        "result": result,
        "legs": legs if len(subs) > 1 else None,
        "settled_at": bet.get("dateClosed") if result != "open" else None,
        # The store keeps this verbatim; `updatedAt` is the checkpoint.
        "updatedAt": bet.get("updatedAt"),
    }


# --- the sync ---------------------------------------------------------------
def fetch_changed(cid: str, sec: str, since: str | None, opener=None,
                  max_pages: int = MAX_PAGES) -> tuple[list[dict], str | None]:
    """Every bet updated since the checkpoint, newest first, and the
    newest `updatedAt` seen. Follows the docs: stop when a page's bets
    are older than the checkpoint, or when `hasMore` is false."""
    bets: list[dict] = []
    newest = since
    cursor = None
    for _ in range(max_pages):
        page = _get("/oauth2/bets/changed",
                    {"updatedAtAfter": since, "cursor": cursor}, cid, sec, opener)
        got = [b for b in (page.get("bets") or []) if isinstance(b, dict)]
        stop = False
        for b in got:
            u = str(b.get("updatedAt") or "")
            if since and u and u < since:
                stop = True
                break
            bets.append(b)
            if u and (newest is None or u > newest):
                newest = u
        cursor = page.get("nextCursor")
        if stop or not page.get("hasMore") or not cursor:
            break
    return bets, newest


def sync(conn, opener=None, state_path=None) -> dict:
    """Pull what changed at Juice Reel into the store. Never raises.

    ``{"ok", "fetched", "added", "updated", "unchanged", "skipped",
    "checkpoint", "why"}``
    """
    out = {"ok": False, "fetched": 0, "added": 0, "updated": 0,
           "unchanged": 0, "skipped": 0, "checkpoint": None, "why": ""}
    creds = credentials()
    if not creds:
        out["why"] = (f"not configured — set {CLIENT_ID_ENV} and "
                      f"{CLIENT_SECRET_ENV} in /etc/qellys/env")
        return out
    cid, sec = creds
    state = load_checkpoint(state_path)
    since = state.get("updated_at")
    try:
        bets, newest = fetch_changed(cid, sec, since, opener)
    except urllib.error.HTTPError as exc:
        out["why"] = (f"Juice Reel answered {exc.code}"
                      + (" — either the client id or secret is wrong, or "
                         "the application is still awaiting Juice Reel's "
                         "review (credentials are issued at once but stay "
                         "inactive until it completes)"
                         if exc.code in (401, 403) else ""))
        return out
    except Exception as exc:                                  # noqa: BLE001
        out["why"] = f"could not reach Juice Reel — {type(exc).__name__}: {exc}"
        return out
    from .zeno import import_rows
    rows = [r for r in (to_row(b) for b in bets) if r]
    out["skipped"] = len(bets) - len(rows)
    got = import_rows(conn, rows, source=SOURCE)
    out.update({k: got[k] for k in ("added", "updated", "unchanged")})
    out["skipped"] += got["skipped"]
    out["fetched"] = len(bets)
    if newest:
        save_checkpoint({"updated_at": newest,
                         "synced_at": _dt.datetime.utcnow().isoformat(
                             timespec="seconds")}, state_path)
    out["checkpoint"] = newest
    out["ok"] = True
    return out


def line(result: dict) -> str:
    """One build-log line, always printed — a sync that found nothing
    and one that could not run must not look alike."""
    if not result.get("ok"):
        return f"  ⚠️  Juice Reel sync skipped: {result.get('why')}"
    return (f"  Juice Reel sync: {result['fetched']} changed → "
            f"{result['added']} added · {result['updated']} updated "
            f"· {result['unchanged']} unchanged"
            + (f" · {result['skipped']} skipped" if result["skipped"] else ""))


# --- CLI --------------------------------------------------------------------
def _cli(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python3 -m engine.juicereel")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("check", help="prove the keys work: GET /oauth2/me")
    s = sub.add_parser("sync", help="pull changed bets into Zeno's store")
    s.add_argument("--full", action="store_true",
                   help="ignore the checkpoint and walk the whole history")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        creds = credentials()
        if not creds:
            print(f"  not configured: set {CLIENT_ID_ENV} and {CLIENT_SECRET_ENV}")
            return 2
        try:
            me = _get("/oauth2/me", {}, *creds)
        except urllib.error.HTTPError as exc:
            print(f"  Juice Reel answered {exc.code} — "
                  + ("either the client id or secret is wrong, or the "
                     "application is still awaiting Juice Reel's review. "
                     "Ethan's first check on 2026-09-21 was this exact "
                     "401, seconds after submitting the form that says "
                     "credentials stay inactive until review completes; "
                     "re-run when Juice Reel says it is approved."
                     if exc.code in (401, 403) else exc.reason))
            return 1
        print(f"  ok — connected as {me.get('displayName')!r} (id {me.get('id')})")
        return 0
    if a.cmd == "sync":
        from .zeno import _root_trap, connect
        problem = _root_trap()
        if problem:
            print(problem)
            return 2
        if a.full:
            save_checkpoint({})
        conn = connect()
        try:
            r = sync(conn)
        finally:
            conn.close()
        print(line(r))
        return 0 if r["ok"] else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
