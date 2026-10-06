"""The community feed: the site talking to its Discord, by itself.

Ethan, 2026-10-06: "link my Discord server to the website so every single
night when bets settle, it'll automatically post that day's record … and
link other shit to where the site feels more alive and linked to a
community."

Two webhooks, two channels (each a line in /etc/qellys/env; either alone
works):

    QB_DISCORD_RECORD_WEBHOOK   a public #record channel
        · last night's record, once every pick of the night has graded —
          each published book's W-L, units, hit rate against what we said,
          the best hit and the toughest miss (engine/recap, one day)
        · the week, on Tuesdays once Monday night has settled
    QB_DISCORD_PICKS_WEBHOOK    a members' #picks channel
        · the Pick of the Day, the first cycle it is locked
        · "today's board is up" — how many Most Likely picks by tier and
          how many Edge picks, the first cycle a game day's board exists
        · a long shot that cashed (+300 or longer), the cycle it settles
    QB_DISCORD_PICKS_DETAIL=0   post counts only, never the pick itself
                                (for a channel that is not members-only)

Runs from the seal step of every cycle (launch._seal_forecasts) and
remembers what it posted in data/discord_feed.json, so each thing goes
out once: one record per night, one Pick of the Day per sport per day,
one post per long shot. A webhook that is down costs the post, which is
retried next cycle; it never costs the cycle.

Every number is the journal's own, through engine/recap — nothing here
is new arithmetic the Record page does not already trust. The chain
heads and the Bitcoin anchors go to their own channel (QB_HEADS_WEBHOOK,
engine/witness); this feed is for people, that one is for proof.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "discord_feed.json"
SITE = "https://qellysbook.com"
BOARD_FILE = {"nfl": "recommendations.json", "cfb": "cfb.json", "mlb": "mlb_recommendations.json",
              "nba": "nba.json", "wnba": "wnba.json", "nhl": "nhl.json"}
SPORT_LABEL = {"nfl": "NFL", "cfb": "College football", "mlb": "MLB", "nba": "NBA", "wnba": "WNBA", "nhl": "NHL"}
MARKET_WORDS = {"pass_yds": "passing yards", "rush_yds": "rushing yards", "rec_yds": "receiving yards",
                "receptions": "receptions", "anytime_td": "anytime TD", "pass_td": "passing TDs",
                "pass_att": "pass attempts", "pass_cmp": "completions", "rush_att": "carries",
                "pass_int": "interceptions", "moneyline": "moneyline", "spread": "spread", "total": "total"}
LONGSHOT_ODDS = 300
#: Post a night's record even with picks still open once it is this late
#: in the morning (Eastern) — a west-coast game stuck ungraded should not
#: hold the whole night's record hostage.
LATE_MORNING_ET = 11
TIMEOUT_S = 10


# ─── configuration and state ───────────────────────────────────────────────

def config(env: dict | None = None) -> dict:
    if env is None:
        try:
            from .secrets import load_local_secrets
            load_local_secrets()
        except Exception:                                    # noqa: BLE001
            pass
        env = os.environ
    sports = tuple(s.strip().lower() for s in str(env.get("QB_DISCORD_SPORTS") or "").split(",") if s.strip()) \
        or tuple(BOARD_FILE)
    return {"record": str(env.get("QB_DISCORD_RECORD_WEBHOOK") or "").strip(),
            "picks": str(env.get("QB_DISCORD_PICKS_WEBHOOK") or "").strip(),
            "detail": str(env.get("QB_DISCORD_PICKS_DETAIL", "1")).strip() not in ("0", "false", "no", "off"),
            "sports": tuple(s for s in sports if s in BOARD_FILE)}


def load_state(path: Path = STATE) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict, path: Path = STATE) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(path).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    os.replace(tmp, path)


def post(url: str, content: str) -> bool:
    """One Discord webhook message. True when Discord took it."""
    body = json.dumps({"content": content[:1990]}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "qellys-feed/1"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
        return 200 <= r.status < 300


# ─── words ─────────────────────────────────────────────────────────────────

def _et(now: _dt.datetime) -> _dt.datetime:
    try:
        from zoneinfo import ZoneInfo
        return now.astimezone(ZoneInfo("America/New_York"))
    except Exception:                                        # noqa: BLE001
        return now - _dt.timedelta(hours=4)


def odds_text(o) -> str:
    try:
        o = int(round(float(o)))
    except (TypeError, ValueError):
        return ""
    return f"+{o}" if o > 0 else f"−{abs(o)}"


def pick_text(p: dict) -> str:
    """"Josh Allen over 249.5 passing yards (−110)" / "BUF −6.5 (−110)"."""
    market = str(p.get("market") or "")
    side = str(p.get("side") or "").lower()
    line = p.get("line")
    try:
        line_s = "" if line in (None, "") else f"{float(line):g}"
    except (TypeError, ValueError):
        line_s = str(line)
    if p.get("kind") == "game" or market in ("moneyline", "spread", "total"):
        head = str(p.get("pick_label") or p.get("player") or "").strip()
    else:
        words = MARKET_WORDS.get(market, market.replace("_", " "))
        side_w = "" if market == "anytime_td" else side
        head = " ".join(x for x in (str(p.get("player") or ""), side_w, line_s if market != "anytime_td" else "",
                                    words) if x)
    o = odds_text(p.get("odds"))
    return f"{head} ({o})" if o else head


def _day_words(day: str) -> str:
    try:
        return _dt.date.fromisoformat(day).strftime("%a %b %-d")
    except ValueError:
        return day


def record_text(rec: dict, day: str, still_open: int = 0) -> str | None:
    books = [b for b in (rec.get("books") or []) if (b.get("w") or 0) + (b.get("l") or 0) + (b.get("p") or 0)]
    if not books:
        return None
    lines = [f"**{_day_words(day)} — the record**" + (f" ({still_open} still grading)" if still_open else "")]
    best = worst = None
    for b in books:
        wl = f"{b['w']}-{b['l']}" + (f"-{b['p']}" if b.get("p") else "")
        u = float(b.get("units") or 0)
        bits = [f"{u:+.1f}u"]
        if b.get("hit") is not None:
            bits.append(f"hit {b['hit']:.0%}" + (f", we said {b['claimed']:.0%}" if b.get("claimed") is not None else ""))
        lines.append(f"{b['book']}: **{wl}** ({' · '.join(bits)})")
        if b.get("best") and (best is None or float(b["best"].get("odds") or 0) > float(best.get("odds") or 0)):
            best = b["best"]
        if b.get("worst") and (worst is None or float(b["worst"].get("claim") or 0) > float(worst.get("claim") or 0)):
            worst = b["worst"]
    if best:
        lines.append(f"Best hit: {pick_text(best)}")
    if worst:
        c = worst.get("claim")
        lines.append(f"Toughest miss: {pick_text(worst)}" + (f" — we said {c:.0%}" if c is not None else ""))
    lines.append(f"Every pick, graded: {SITE}/#record")
    return "\n".join(lines)


def weekly_text(rec: dict) -> str | None:
    books = [b for b in (rec.get("books") or []) if (b.get("w") or 0) + (b.get("l") or 0)]
    if not books:
        return None
    lines = [f"**The week — {_day_words(rec.get('from', ''))} to {_day_words(rec.get('to', ''))}**"]
    for b in books:
        lines.append(f"{b['book']}: **{b['w']}-{b['l']}" + (f"-{b['p']}" if b.get("p") else "") +
                     f"** ({float(b.get('units') or 0):+.1f}u" +
                     (f", hit {b['hit']:.0%}" if b.get("hit") is not None else "") + ")")
        bs = b.get("by_sport") or {}
        if len(bs) > 1:
            lines.append("  " + " · ".join(f"{SPORT_LABEL.get(s, s.upper())} {v['w']}-{v['l']}" for s, v in bs.items()))
    lines.append(f"The recap, with the best and worst: {SITE}/#record")
    return "\n".join(lines)


def potd_text(card: dict, sport: str, detail: bool = True) -> str | None:
    pick = card.get("pick") or {}
    if not pick:
        return None
    label = SPORT_LABEL.get(sport, sport.upper())
    if not detail:
        return f"**Pick of the Day ({label})** is locked — members see it at {SITE}/#recommended"
    p = pick.get("hit_prob") or pick.get("model_prob")
    try:
        chance = f" — we say {float(p):.0%}" if p is not None else ""
    except (TypeError, ValueError):
        chance = ""
    book = f" at {pick['book']}" if pick.get("book") else ""
    say = str((card.get("verdict") or {}).get("say") or "").strip()
    out = f"**Pick of the Day ({label})**: {pick_text(pick)}{book}{chance}"
    if say:
        out += f"\n{say[:400]}"
    return out + f"\n{SITE}/#recommended"


def board_text(board: dict, sport: str, today: str, detail: bool = True) -> str | None:
    rows = ((board.get("likely_board") or {}).get("rows")) or []
    recs = [r for r in board.get("recommendations") or [] if r.get("recommended")]
    recs += [r for r in board.get("game_bets") or [] if r.get("recommended")]
    games = [g for g in board.get("games") or [] if str(g.get("date") or "")[:10] == today]
    if not games or not (rows or recs):
        return None
    tiers = {}
    for r in rows:
        tiers[r.get("tier")] = tiers.get(r.get("tier"), 0) + 1
    label = SPORT_LABEL.get(sport, sport.upper())
    parts = []
    if rows:
        t = ", ".join(f"{tiers[k]} {w}" for k, w in (("top", "Top"), ("strong", "Strong"), ("look", "Worth a look"))
                      if tiers.get(k))
        parts.append(f"{len(rows)} Most Likely pick{'s' if len(rows) != 1 else ''}" + (f" ({t})" if t else ""))
    if recs:
        parts.append(f"{len(recs)} Edge pick{'s' if len(recs) != 1 else ''}")
    out = f"**{label} board is up** — {len(games)} game{'s' if len(games) != 1 else ''} today: {' · '.join(parts)}."
    if detail and rows:
        tops = [r for r in rows if r.get("tier") == "top"][:3]
        if tops:
            out += "\nTop: " + " · ".join(pick_text(r) for r in tops)
    return out + f"\n{SITE}/#likely"


def longshot_text(row: dict) -> str:
    label = SPORT_LABEL.get(str(row.get("sport") or ""), str(row.get("sport") or "").upper())
    return f"🎯 **Long shot cashed** ({label}): {pick_text(row)}\n{SITE}/#record"


# ─── what has settled ──────────────────────────────────────────────────────

def _books_cats() -> tuple:
    from .recap import BOOKS
    return tuple(c for _, cats in BOOKS for c in cats)


def day_counts(conn, day: str) -> tuple[int, int]:
    """(open, settled) picks of the published books whose game day is `day`."""
    cats = _books_cats()
    marks = ",".join("?" * len(cats))
    try:
        o = conn.execute(f"SELECT COUNT(*) FROM bets WHERE COALESCE(game_day, date)=? AND category IN ({marks}) "
                         f"AND status='open'", (day, *cats)).fetchone()[0]
        s = conn.execute(f"SELECT COUNT(*) FROM bets WHERE COALESCE(game_day, date)=? AND category IN ({marks}) "
                         f"AND status IN ('won','lost','push')", (day, *cats)).fetchone()[0]
    except sqlite3.Error:
        return 0, 0
    return int(o or 0), int(s or 0)


def recent_longshots(conn, since: str) -> list[dict]:
    try:
        rows = conn.execute(
            "SELECT id, sport, player, market, side, line, odds, hit_prob, category FROM bets WHERE status='won' "
            "AND odds >= ? AND COALESCE(game_day, date) >= ? AND category NOT LIKE 'parlay%' ORDER BY id",
            (LONGSHOT_ODDS, since)).fetchall()
    except sqlite3.Error:
        return []
    return [dict(zip(("id", "sport", "player", "market", "side", "line", "odds", "hit_prob", "category"), r))
            for r in rows]


def _load_board(sport: str) -> dict | None:
    from . import gate
    try:
        path = Path(gate.board_source(ROOT / "web" / "data" / BOARD_FILE[sport]))
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError, KeyError):
        return None


# ─── one pass ──────────────────────────────────────────────────────────────

def run(conn, now: _dt.datetime | None = None, env: dict | None = None, boards: dict | None = None,
        post_fn=post, state_path: Path = STATE) -> dict:
    """Everything due this cycle, once each. Returns {"posted": [...], "failed": [...]}."""
    from .recap import recap
    cfg = config(env)
    out = {"posted": [], "failed": []}
    if not cfg["record"] and not cfg["picks"]:
        out["note"] = "no Discord webhook set"
        return out
    now = now or _dt.datetime.now(_dt.timezone.utc)
    et = _et(now)
    today = et.date()
    state = load_state(state_path)
    posted = state.setdefault("posted", {})

    def send(key: str, url: str, text: str | None) -> None:
        if not text or key in posted or not url:
            return
        try:
            ok = post_fn(url, text)
        except Exception as exc:                             # noqa: BLE001
            out["failed"].append(f"{key}: {exc}")
            return
        if ok:
            posted[key] = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            out["posted"].append(key)

    # Last night, and the night before if it was still grading yesterday.
    if cfg["record"]:
        for back in (1, 2):
            day = (today - _dt.timedelta(days=back)).isoformat()
            key = f"record:{day}"
            if key in posted:
                continue
            open_n, settled_n = day_counts(conn, day)
            if not settled_n or (open_n and et.hour < LATE_MORNING_ET):
                continue
            rec = recap(conn, now=_dt.datetime.fromisoformat(day) + _dt.timedelta(hours=16), days=1)
            send(key, cfg["record"], record_text(rec, day, still_open=open_n))
        if today.weekday() == 1:                             # Tuesday: the week through Monday night
            iso = today.isocalendar()
            send(f"weekly:{iso[0]}-W{iso[1]:02d}", cfg["record"], weekly_text(recap(conn, now=now, days=7)))

    if cfg["picks"]:
        t = today.isoformat()
        for sport in cfg["sports"]:
            board = (boards or {}).get(sport) if boards is not None else _load_board(sport)
            if not board:
                continue
            send(f"board:{sport}:{t}", cfg["picks"], board_text(board, sport, t, cfg["detail"]))
            card = board.get("pick_of_the_day") or {}
            if card.get("pick") and (card.get("verdict") or {}).get("bet") is not False \
                    and str(card.get("date") or t)[:10] == t:
                send(f"potd:{sport}:{t}", cfg["picks"], potd_text(card, sport, cfg["detail"]))
        since = (today - _dt.timedelta(days=2)).isoformat()
        for row in recent_longshots(conn, since):
            send(f"longshot:{row['id']}", cfg["picks"], longshot_text(row) if cfg["detail"] else
                 f"🎯 A long shot cashed ({odds_text(row.get('odds'))}) — {SITE}/#record")

    # Keep the state small: anything older than 60 days has nothing left to dedupe.
    cutoff = (now - _dt.timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for k in [k for k, v in posted.items() if str(v) < cutoff]:
        posted.pop(k, None)
    if out["posted"]:
        save_state(state, state_path)
    return out
