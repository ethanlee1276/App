"""How engaged each member is, who is drifting away, and what the members
are worth together — read from each member's own activity (engine/activity)
and nothing else, and only while that is switched on.

    python3 -m engine.engagement report        # the owner's report, the last 28 days
    python3 -m engine.engagement report 56
    python3 -m engine.engagement fit           # fit the visit model; held out; saves nothing
    python3 -m engine.engagement fit --save    # and keep it, only if it beats the rule
    python3 -m engine.engagement demo          # the report on a made-up population

Ethan, 2026-10-29: "how apps will use data off your phone to see how much
worth you are to them, and how to get retention rate off of you ... look
at other apps' algorithms and what they do ... let's start implementing
that stuff." docs/RETENTION.md §6 has the research; this is what was built.

STAGES (`stage`), the lifecycle every engagement tool sorts people into,
with one change that matters for a sports site: "away too long" is
measured against the member's OWN rhythm. A football fan who comes every
Sunday is not drifting at day six; a daily reader is.
  new       signed up in the last 7 days
  power     on 15 or more of the last 28 days (the power-user curve's
            right-hand hump: Andrew Chen and Li Jin's L28, a16z 2018)
  regular   6 to 14 of the last 28
  casual    1 to 5 of the last 28, and not overdue
  lapsing   away longer than max(7 days, 2.5 times their usual gap
            between visits), under 30 days
  dormant   30 to 59 days away
  gone      60 days or more

WHO IS STILL AROUND (`BGBB`). Fader, Hardie and Shang's beta-geometric /
beta-binomial model ("Customer-Base Analysis in a Discrete-Time
Noncontractual Setting", Marketing Science 2010), the standard for exactly
this data: each day is a chance to come, a member who is "alive" comes
with their own probability p, and may quietly stop for good with their own
probability θ; p and θ vary across members as beta distributions. From a
member's active days it gives the chance they are still around and the
days they will come in the next four weeks. It is FITTED on this site's
own members (`fit`), and only kept if, on members it never saw, it
predicts who comes back better than the stage rule does (the `--heldout`
habit of engine/nbavacancy). Until then the report says so and the
stages stand alone.

WHAT IT IS WORTH. Monthly revenue by stage, the revenue in the lapsing and
dormant stages (the money a win-back is for), average revenue per paying
member, the measured monthly cancellation rate and the lifetime value they
imply (ARPU ÷ churn). By group only: nothing here treats a member
differently by what they pay or might pay — the sportsbooks' "VIP" models
that do exactly that are the ones under a US Senate inquiry (Blumenthal,
October 2026) and in court. docs/RETENTION.md §2.

ACTING ON IT (`away_pass`): the "while you were away" alert. See below.

Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import sqlite3
import statistics
import time
from pathlib import Path

from engine import activity as ACT

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "data" / "engagement_model.json"
STAGES = ("new", "power", "regular", "casual", "lapsing", "dormant", "gone")
#: The ET hours an alert that is not tied to a game may go (quiet hours,
#: engine/pushalerts.QUIET, are 23:00-09:00).
SEND_HOURS = range(10, 22)
#: Days of history a member's usual gap is read from.
GAP_WINDOW = 56
#: The fit's four-week look ahead.
AHEAD = 28
#: Monthly revenue a plan is worth (engine/billing.PLANS: the price over its months).
PLAN_MONTHLY = {"monthly": 25.0, "sixmonth": 125.0 / 6, "yearly": 225.0 / 12}


def _day(s: str) -> _dt.date:
    return _dt.date.fromisoformat(str(s)[:10])


# ---- one member ---------------------------------------------------------------------
def features(rows: list, signup: _dt.date, today: _dt.date, since: _dt.date | None = None) -> dict:
    """What the stages and the alerts read, from one member's activity rows
    (engine/activity.rows, oldest first). `since` is the first day the
    activity log holds for anybody: a member it has never seen is "away"
    from then, not from the day they signed up."""
    active = sorted({_day(r["day"]) for r in rows if r.get("seconds") or r.get("visits")})
    age = (today - signup).days
    # Never seen: away since the log began (or since they signed up, if
    # later). With no log at all there is nothing to say they were away.
    last = active[-1] if active else max(signup, since or today)
    recent = [d for d in active if (today - d).days < GAP_WINDOW]
    gaps = [(b - a).days for a, b in zip(recent, recent[1:])]
    usual = statistics.median(gaps) if gaps else None
    l28 = [r for r in rows if (today - _day(r["day"])).days < 28 and (r.get("seconds") or r.get("visits"))]
    hours = [0] * 24
    sports: dict = {}
    for r in l28:
        hours = [a + b for a, b in zip(hours, r.get("hours") or [0] * 24)]
        for k, v in (r.get("sports") or {}).items():
            sports[k] = sports.get(k, 0) + int(v)
    secs = sum(int(r.get("seconds") or 0) for r in l28)
    return {"age": age, "recency": (today - last).days, "seen": bool(active),
            "l7": sum(1 for d in active if (today - d).days < 7),
            "l28": sum(1 for d in active if (today - d).days < 28),
            "usual_gap": usual, "overdue_after": max(7.0, 2.5 * usual) if usual else 14.0,
            "minutes": round(secs / 60 / len(l28), 1) if l28 else 0.0,
            "visits28": sum(int(r.get("visits") or 0) for r in l28),
            "taps28": sum(int(r.get("taps") or 0) for r in l28),
            "best_hour": best_hour(hours),
            "sports": [k for k, v in sorted(sports.items(), key=lambda kv: -kv[1]) if k != "other" and v > 0][:3],
            "active_days": active}


def best_hour(hours: list, allowed=SEND_HOURS) -> int | None:
    """The Eastern hour a member spends most time in, among the hours an
    alert may go — Braze's "most engaged hour", read off their own
    seconds. None until there is something to read."""
    if not hours or not any(hours[h] for h in allowed):
        return None
    return max(allowed, key=lambda h: hours[h])


def stage(f: dict) -> str:
    if f["age"] < 7:
        return "new"
    r = f["recency"]
    if r >= 60:
        return "gone"
    if r >= 30:
        return "dormant"
    if r > f["overdue_after"]:
        return "lapsing"
    if f["l28"] >= 15:
        return "power"
    if f["l28"] >= 6:
        return "regular"
    return "casual"


# ---- the visit model (BG/BB) -----------------------------------------------------------
def _lbeta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _lse(xs: list) -> float:
    m = max(xs)
    return m + math.log(sum(math.exp(x - m) for x in xs))


def bgbb_terms(params, x: int, tx: int, n: int) -> tuple[float, float]:
    """(log of the alive-throughout term, log likelihood) for one member:
    x active days among n chances after their first, the last on day tx."""
    a, b, g, d = params
    alive = _lbeta(a + x, b + n - x) - _lbeta(a, b) + _lbeta(g, d + n) - _lbeta(g, d)
    terms = [alive]
    lt = _lbeta(a + x, b + tx - x) - _lbeta(a, b) + _lbeta(g + 1, d + tx) - _lbeta(g, d)
    for i in range(n - tx):
        terms.append(lt)
        # B(p, q+1) / B(p, q) = q / (p + q), for both betas.
        lt += math.log((b + tx - x + i) / (a + b + tx + i)) + math.log((d + tx + i) / (g + 1 + d + tx + i))
    return alive, _lse(terms)


def p_alive(params, x: int, tx: int, n: int) -> float:
    """The chance a member is still around on the day after the n-th (eq. 11)."""
    _a, _b, g, d = params
    alive, ll = bgbb_terms(params, x, tx, n)
    return math.exp(alive + _lbeta(g, d + n + 1) - _lbeta(g, d + n) - ll)


def p_back(params, x: int, tx: int, n: int, ahead: int = AHEAD) -> float:
    """The chance a member comes on at least one of the next `ahead` days.
    Dead, never; alive, one minus the chance of `ahead` quiet days, each
    risking the stop first — averaged over what their history says p and θ are."""
    a, b, g, d = params
    alive, ll = bgbb_terms(params, x, tx, n)
    w = math.exp(alive - ll)                          # alive through day n, given the history
    pa, pb, ga, gb = a + x, b + n - x, g, d + n       # the posteriors, alive
    quiet = math.exp(_lbeta(pa, pb + ahead) - _lbeta(pa, pb) + _lbeta(ga, gb + ahead) - _lbeta(ga, gb))
    for k in range(ahead):
        quiet += math.exp(_lbeta(pa, pb + k) - _lbeta(pa, pb) + _lbeta(ga + 1, gb + k) - _lbeta(ga, gb))
    return max(0.0, min(1.0, w * (1.0 - quiet)))


def expected_days(params, x: int, tx: int, n: int, ahead: int = AHEAD) -> float:
    """Active days to expect in the next `ahead` (eq. 13)."""
    a, b, g, d = params
    if abs(g - 1.0) < 1e-6:
        g += 1e-6
    _alive, ll = bgbb_terms(params, x, tx, n)
    head = _lbeta(a + x + 1, b + n - x) - _lbeta(a, b) - ll
    k = d / (g - 1) * math.exp(math.lgamma(g + d) - math.lgamma(1 + d))
    diff = (math.exp(math.lgamma(1 + d + n) - math.lgamma(g + d + n))
            - math.exp(math.lgamma(1 + d + n + ahead) - math.lgamma(g + d + n + ahead)))
    return max(0.0, math.exp(head) * k * diff)


def triple(active: list, first: _dt.date, end: _dt.date) -> tuple[int, int, int]:
    """(x, tx, n) for BG/BB: the days after the first one, up to `end`."""
    n = (end - first).days
    after = [(d - first).days for d in active if first < d <= end]
    return len(after), (max(after) if after else 0), n


def _nelder_mead(f, x0: list, step: float = 0.5, iters: int = 800, tol: float = 1e-7) -> list:
    pts = [list(x0)] + [[v + (step if i == j else 0.0) for j, v in enumerate(x0)] for i in range(len(x0))]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = sorted(range(len(pts)), key=lambda i: vals[i])
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) < tol * (1 + abs(vals[0])):
            break
        c = [sum(p[j] for p in pts[:-1]) / (len(pts) - 1) for j in range(len(x0))]
        refl = [c[j] + (c[j] - pts[-1][j]) for j in range(len(x0))]
        fr = f(refl)
        if fr < vals[0]:
            exp_ = [c[j] + 2 * (c[j] - pts[-1][j]) for j in range(len(x0))]
            fe = f(exp_)
            pts[-1], vals[-1] = (exp_, fe) if fe < fr else (refl, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = refl, fr
        else:
            con = [c[j] + 0.5 * (pts[-1][j] - c[j]) for j in range(len(x0))]
            fc = f(con)
            if fc < vals[-1]:
                pts[-1], vals[-1] = con, fc
            else:
                pts = [pts[0]] + [[pts[0][j] + 0.5 * (p[j] - pts[0][j]) for j in range(len(x0))] for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
    return pts[min(range(len(pts)), key=lambda i: vals[i])]


def fit_bgbb(data: list) -> tuple:
    """Maximum likelihood (a, b, g, d) for [(x, tx, n), ...], members with
    the same history counted together."""
    counts: dict = {}
    for t in data:
        if t[2] > 0:
            counts[t] = counts.get(t, 0) + 1
    if not counts:
        raise ValueError("nobody with a day after their first")

    def nll(logp):
        if any(abs(v) > 12 for v in logp):
            return 1e18
        p = [math.exp(v) for v in logp]
        return -sum(w * bgbb_terms(p, *t)[1] for t, w in counts.items())

    best = _nelder_mead(nll, [0.0, 0.0, 0.0, 0.0])
    return tuple(math.exp(v) for v in best)


# ---- the accounts database ---------------------------------------------------------------
def _table(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def members(conn, now: float | None = None, user_ids=None) -> dict:
    """{user_id: {signup, rows, opted_out, plan, status, alerts}} for every
    account (or the ones named)."""
    ACT.ensure_tables(conn)
    sql = "SELECT id, created_at FROM users"
    args: tuple = ()
    if user_ids is not None:
        ids = [int(u) for u in user_ids]
        if not ids:
            return {}
        sql += f" WHERE id IN ({','.join('?' * len(ids))})"
        args = tuple(ids)
    out = {int(uid): {"signup": ACT.eastern(created).date(), "rows": [], "opted_out": False,
                      "plan": "", "status": "", "alerts": False}
           for uid, created in conn.execute(sql, args)}
    if not out:
        return out
    if user_ids is not None and len(out) <= 200:
        for uid in out:
            out[uid]["rows"] = ACT.rows(conn, uid, ACT.KEEP_DAYS, now)
    else:
        for r in ACT.rows(conn, None, ACT.KEEP_DAYS, now):
            if r["user_id"] in out:
                out[r["user_id"]]["rows"].append(r)
    # Only members who said yes are read at all (engine/activity: consent first).
    yes = {u for (u,) in conn.execute("SELECT user_id FROM activity_prefs WHERE off = 0")}
    for uid in out:
        out[uid]["opted_out"] = uid not in yes
    if _table(conn, "subscriptions"):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")}
        plan = "plan" if "plan" in cols else "''"
        for uid, status, p in conn.execute(f"SELECT user_id, status, {plan} FROM subscriptions"):
            if uid in out:
                out[uid].update(status=str(status or ""), plan=str(p or ""))
    if _table(conn, "push_subs"):
        for (uid,) in conn.execute("SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL"):
            if uid in out:
                out[uid]["alerts"] = True
    return out


def monthly(m: dict) -> float:
    """What a member pays a month now (a trial pays nothing yet)."""
    return PLAN_MONTHLY.get(m.get("plan") or "monthly", 25.0) if m.get("status") == "active" else 0.0


def first_day(conn) -> _dt.date | None:
    ACT.ensure_tables(conn)
    row = conn.execute("SELECT MIN(day) FROM activity_days").fetchone()
    return _day(row[0]) if row and row[0] else None


def load_model(path: Path | None = None) -> dict | None:
    try:
        got = json.loads(Path(path or MODEL).read_text(encoding="utf-8"))
        return got if isinstance(got.get("params"), list) and len(got["params"]) == 4 else None
    except (OSError, ValueError, AttributeError):
        return None


# ---- the held-out test -------------------------------------------------------------------
def heldout(conn, now: float | None = None, ahead: int = AHEAD) -> dict:
    """Fit on three quarters of the members as they stood `ahead` days ago,
    then ask both the model and the stage rule which of the other quarter
    came back in the `ahead` days since. Brier scores, lower is better."""
    today = ACT.eastern(now).date()
    cut = today - _dt.timedelta(days=ahead)
    train, test = [], []
    for uid, m in members(conn, now).items():
        if m["opted_out"]:
            continue
        active = sorted({_day(r["day"]) for r in m["rows"] if r["seconds"] or r["visits"]})
        before = [d for d in active if d <= cut]
        if not before or (cut - before[0]).days < 1:
            continue
        came = any(cut < d <= today for d in active)
        t = triple(before, before[0], cut)
        f = features([r for r in m["rows"] if _day(r["day"]) <= cut], m["signup"], cut)
        (test if uid % 4 == 0 else train).append((t, stage(f), came))
    if len(train) < 30 or len(test) < 10:
        return {"ok": False, "why": f"too few members with history before {cut} "
                                    f"({len(train)} to fit, {len(test)} to test; 30 and 10 are the least)"}
    params = fit_bgbb([t for t, _, _ in train])
    # The rule's own probabilities: how often each stage came back, in the fitting quarter.
    rate: dict = {}
    for _, st, came in train:
        n, k = rate.get(st, (0, 0))
        rate[st] = (n + 1, k + int(came))
    base = sum(int(c) for _, _, c in train) / len(train)
    rule = lambda st: (rate[st][1] + base) / (rate[st][0] + 1) if st in rate else base   # noqa: E731
    bm = sum((p_back(params, *t, ahead=ahead) - int(c)) ** 2 for t, _, c in test) / len(test)
    br = sum((rule(st) - int(c)) ** 2 for _, st, c in test) / len(test)
    return {"ok": True, "params": [round(v, 6) for v in params], "brier_model": round(bm, 4),
            "brier_rule": round(br, 4), "holds": bm < br, "fitted": len(train), "tested": len(test),
            "as_of": cut.isoformat()}


def fit(conn, now: float | None = None, save: bool = False, path: Path | None = None) -> dict:
    """The held-out test; with save, refit on everybody up to today and keep
    it — only when the model beat the rule on the members it never saw."""
    got = heldout(conn, now)
    if not (got.get("ok") and got.get("holds")) or not save:
        return dict(got, saved=False)
    today = ACT.eastern(now).date()
    data = []
    for m in members(conn, now).values():
        active = sorted({_day(r["day"]) for r in m["rows"] if r["seconds"] or r["visits"]})
        if active and not m["opted_out"]:
            data.append(triple(active, active[0], today - _dt.timedelta(days=1)))
    params = fit_bgbb(data)
    doc = {"params": [round(v, 6) for v in params], "fitted_on": len(data), "at": today.isoformat(),
           "heldout": {k: got[k] for k in ("brier_model", "brier_rule", "fitted", "tested", "as_of")}}
    p = Path(path or MODEL)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return dict(got, saved=True, model=doc)


# ---- the owner's report ----------------------------------------------------------------
def _pct(a, b) -> str:
    return f"{100 * a / b:.0f}%" if b else "—"


def _bar(n: int, top: int, width: int = 24) -> str:
    return "█" * max(1, round(width * n / top)) if n and top else ""


# ---- the four groups (the second paper, 2026-10-29) ------------------------------------
#: (name, who, what to do) — "Sort users into four groups and treat each
#: differently", read off each account's own last-seen day and its plan, so
#: they need no activity log.
GROUPS = (
    ("Champions", "paying, here in the last 5 days",
     "ask them for referrals (Invite friends) and early feedback on what is new"),
    ("At-risk payers", "paying, not here in 5 days or more",
     "their week and the board's go by push once a week (engine/lifecycle); cancelling stays one tap"),
    ("Engaged free", "never paid, here in the last 7 days",
     "the plans page shows what members' alerts caught on their teams"),
    ("Dormant", "not paying, not here in 30 days or more",
     "one note at a season's start at most, then nothing"),
)


def four_groups(conn, now: float | None = None) -> dict:
    """{name: {"n", "monthly"}} plus "Everyone else", for every account."""
    t = time.time() if now is None else float(now)
    out = {g[0]: {"n": 0, "monthly": 0.0} for g in GROUPS}
    out["Everyone else"] = {"n": 0, "monthly": 0.0}
    subs = _table(conn, "subscriptions")
    plan = "s.plan" if subs and "plan" in {r[1] for r in conn.execute("PRAGMA table_info(subscriptions)")} else "''"
    sql = (f"SELECT u.last_seen, u.created_at, s.status, {plan} FROM users u LEFT JOIN subscriptions s "
           "ON s.user_id = u.id") if subs else "SELECT last_seen, created_at, NULL, '' FROM users"
    for last, created, status, p in conn.execute(sql):
        away = (t - float(last or created or t)) / 86400
        paying = str(status or "") in ("active", "trialing")
        m = {"status": str(status or ""), "plan": str(p or "")}
        if paying:
            name = "Champions" if away < 5 else "At-risk payers"
        elif away >= 30:
            name = "Dormant"
        elif status is None and away < 7:
            name = "Engaged free"
        else:
            name = "Everyone else"
        out[name]["n"] += 1
        out[name]["monthly"] += monthly(m)
    return out


def groups_lines(conn, now: float | None = None) -> list:
    if not _table(conn, "users"):
        return []
    got = four_groups(conn, now)
    lines = ["the four groups (each account's own last-seen day and its plan; no activity log needed):"]
    for name, who, do in GROUPS:
        g = got[name]
        money = f"${g['monthly']:.0f}/month" if g["monthly"] else ""
        lines.append(f"  {name:<16}{g['n']:>6}  {money:<12}{who} — {do}")
    lines.append(f"  {'Everyone else':<16}{got['Everyone else']['n']:>6}")
    return lines


#: The pages that are a pick, for "paying, no pick opened in 5 days".
PICK_VIEWS = ("prop", "likely", "edge", "recommended", "tonight", "props", "longshots", "scanner", "record")


def churn_flags(ms: dict, today: _dt.date, conn=None) -> dict:
    """The paper's rules, over members who said yes: no visit in 5+ days while
    their league plays; bets logged this week under half their four-week
    average; fewer alerts opened two weeks running; paying and no pick
    opened in 5 days. Counts only."""
    live = set()                                         # leagues anybody read in the last week
    for m in ms.values():
        for r in m["rows"]:
            if not m["opted_out"] and (today - _day(r["day"])).days < 7:
                live |= set(r["sports"])
    flags = {"no visit in 5+ days while their league plays": 0,
             "bets logged this week under half their 4-week average": 0,
             "fewer alerts opened two weeks running": 0,
             "paying, no pick opened in 5 days": 0}
    for uid, m in ms.items():
        if m["opted_out"] or not m["rows"]:
            continue
        rows = m["rows"]
        last = max(_day(r["day"]) for r in rows if r["seconds"] or r["visits"]) if any(
            r["seconds"] or r["visits"] for r in rows) else None
        theirs = {k for r in rows for k in r["sports"]}
        if last and (today - last).days >= 5 and theirs & live:
            flags["no visit in 5+ days while their league plays"] += 1
        weeks = [0, 0, 0]
        for r in rows:
            ago = (today - _day(r["day"])).days
            if 0 <= ago < 21:
                weeks[ago // 7] += r["taps"]
        if weeks[2] >= 2 and weeks[1] < weeks[2] and weeks[0] < weeks[1]:
            flags["fewer alerts opened two weeks running"] += 1
        if monthly(m) > 0 and not any(r["views"].get(v) for r in rows
                                      if (today - _day(r["day"])).days < 5 for v in PICK_VIEWS):
            flags["paying, no pick opened in 5 days"] += 1
        if conn is not None and _table(conn, "user_data"):
            row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'mybets'",
                               (uid,)).fetchone()
            try:
                bets = (json.loads(row[0]) or {}).get("rows") if row else None
            except (TypeError, ValueError, AttributeError):
                bets = None
            per = [0] * 5
            for b in bets if isinstance(bets, list) else []:
                try:
                    ago = (today - _dt.date.fromisoformat(str((b or {}).get("date") or "")[:10])).days
                except ValueError:
                    continue
                if 0 <= ago < 35:
                    per[ago // 7] += 1
            usual = sum(per[1:]) / 4
            if usual >= 2 and per[0] < usual / 2:
                flags["bets logged this week under half their 4-week average"] += 1
    return flags


# ---- the first paper's numbers: the North Star, the aha moment, recency by frequency ----
#: A live game's own pages, as js/activity.js names them.
LIVE_VIEWS = ("pbp", "gamecast")
#: "Logged first bet and watched it on the Sweat Board during a live game
#: within 48 hours of signup": the signup day or the next (the log keeps days).
AHA_DAYS = 2
#: Under this many members in a test, the report says so instead of a share.
AHA_MIN = 10


def _logged(conn, uid) -> list:
    """[(the bet's date, the day it was logged or None)] off a member's synced
    My Bets; the logged day is read off the entry's id (its first thirteen
    digits are the moment it was saved)."""
    if conn is None or not _table(conn, "user_data"):
        return []
    row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'mybets'", (uid,)).fetchone()
    try:
        rows = (json.loads(row[0]) or {}).get("rows") if row else None
    except (TypeError, ValueError, AttributeError):
        rows = None
    out = []
    for b in rows if isinstance(rows, list) else []:
        if not isinstance(b, dict):
            continue
        sid = str(b.get("id") or "")
        at = ACT.eastern(int(sid[:13]) / 1000).date() if len(sid) >= 13 and sid[:13].isdigit() else None
        out.append((str(b.get("date") or "")[:10], at))
    return out


def _follows(conn, uid) -> bool:
    """A team in their settings, or a player or team watch."""
    if conn is None:
        return False
    if _table(conn, "user_data"):
        row = conn.execute("SELECT payload FROM user_data WHERE user_id = ? AND section = 'settings'",
                           (uid,)).fetchone()
        try:
            if row and (json.loads(row[0]) or {}).get("teams"):
                return True
        except (TypeError, ValueError, AttributeError):
            pass
    return bool(_table(conn, "alert_watches") and conn.execute(
        "SELECT 1 FROM alert_watches WHERE user_id = ? AND kind IN ('player', 'team') LIMIT 1", (uid,)).fetchone())


def _weeks_ago(day: _dt.date, today: _dt.date) -> int:
    """0 for this Monday-to-Sunday week, 1 for the one before, and so on."""
    return ((today - _dt.timedelta(days=today.weekday())) - (day - _dt.timedelta(days=day.weekday()))).days // 7


def north_star(ms: dict, today: _dt.date, conn=None, weeks: int = 4) -> list:
    """The first paper's North Star, weekly active sweaters: members who said
    yes who opened a live game's page in the week, with a bet dated that week
    or a team or player they follow. [this week, the week before, ...]."""
    out = [0] * weeks
    for uid, m in ms.items():
        if m["opted_out"]:
            continue
        watched = {_weeks_ago(_day(r["day"]), today) for r in m["rows"]
                   if any((r.get("views") or {}).get(v) for v in LIVE_VIEWS)}
        watched = {k for k in watched if 0 <= k < weeks}
        if not watched:
            continue
        follows = _follows(conn, uid)
        bet = set()
        for d, _at in _logged(conn, uid):
            try:
                bet.add(_weeks_ago(_dt.date.fromisoformat(d), today))
            except ValueError:
                continue
        for k in watched:
            out[k] += 1 if follows or k in bet else 0
    return out


def aha(ms: dict, today: _dt.date, conn=None) -> dict:
    """The paper's aha moment as a test, not a belief: of members who said yes
    and signed up 28 to 84 days ago, those who logged a bet and watched a live
    game's page in their first AHA_DAYS, and how many of each kind were still
    here in days 22 to 28 after signing up."""
    got = {"n": 0, "aha": 0, "kept_aha": 0, "kept_rest": 0}
    for uid, m in ms.items():
        age = (today - m["signup"]).days
        if m["opted_out"] or not 28 <= age <= 84:
            continue
        first = {m["signup"] + _dt.timedelta(days=i) for i in range(AHA_DAYS)}
        watched = any(_day(r["day"]) in first and any((r.get("views") or {}).get(v) for v in LIVE_VIEWS)
                      for r in m["rows"])
        logged = any(at in first for _d, at in _logged(conn, uid))
        kept = any(22 <= (_day(r["day"]) - m["signup"]).days <= 28 and (r.get("seconds") or r.get("visits"))
                   for r in m["rows"])
        got["n"] += 1
        if watched and logged:
            got["aha"] += 1
            got["kept_aha"] += kept
        else:
            got["kept_rest"] += kept
    return got


#: Recency (days since last here) and frequency (days here of the last 28) bands.
R_BANDS = ((0, 3, "here in 3 days"), (4, 13, "4 to 13 days"), (14, 10 ** 6, "14 days or more"))
F_BANDS = ((1, 3, "1-3 days"), (4, 11, "4-11 days"), (12, 28, "12+ days"))


def rfm_lines(ms: dict, fs: dict) -> list:
    """Recency by frequency, with the paying members in each cell (the money):
    members who said yes and were here at least once in the last 28 days."""
    grid = {(r, f): [0, 0] for r in range(3) for f in range(3)}
    for uid, f in fs.items():
        if not f["l28"]:
            continue
        r = next(i for i, (lo, hi, _w) in enumerate(R_BANDS) if lo <= f["recency"] <= hi)
        q = next(i for i, (lo, hi, _w) in enumerate(F_BANDS) if lo <= f["l28"] <= hi)
        grid[(r, q)][0] += 1
        grid[(r, q)][1] += monthly(ms[uid]) > 0
    out = [f"  {'':<18}" + "".join(f"{w:>14}" for _lo, _hi, w in F_BANDS)]
    for r, (_lo, _hi, w) in enumerate(R_BANDS):
        out.append(f"  {w:<18}" + "".join(f"{f'{grid[(r, q)][0]} ({grid[(r, q)][1]})':>14}" for q in range(3)))
    return out


def report(conn, days: int = 28, now: float | None = None, model_path: Path | None = None) -> str:
    on = ACT.enabled()
    head = [f"Qellys engagement, the last {days} days (Eastern days). Activity: "
            + ("ON." if on else f"OFF — {ACT.why_off()}.")]
    groups = groups_lines(conn, now)
    if groups:
        head += [""] + groups
    kept = _table(conn, "activity_days") and conn.execute("SELECT 1 FROM activity_days LIMIT 1").fetchone()
    if not kept:
        return "\n".join(head + ["", "Nothing has been kept yet, so there is nothing to report. "
                                     "`python3 -m engine.engagement demo` shows the report on a made-up population."])
    return "\n".join(head + [""] + _body(members(conn, now), ACT.eastern(now).date(), first_day(conn),
                                         days, load_model(model_path), conn, now))


def _body(ms: dict, today: _dt.date, since, days: int, model: dict | None, conn=None,
          now: float | None = None) -> list:
    out: list = []
    fs = {uid: features(m["rows"], m["signup"], today, since) for uid, m in ms.items() if not m["opted_out"]}
    st = {uid: stage(f) for uid, f in fs.items()}
    opted = sum(1 for m in ms.values() if m["opted_out"])
    # 1. Stages, and the money in each.
    out.append(f"{'members by stage':<22}{'members':>8}{'paying':>8}{'$/month':>9}")
    for s in STAGES:
        ids = [u for u, v in st.items() if v == s]
        pay = [u for u in ids if monthly(ms[u]) > 0]
        out.append(f"  {s:<20}{len(ids):>8}{len(pay):>8}{sum(monthly(ms[u]) for u in pay):>9.0f}")
    risk = sum(monthly(ms[u]) for u, v in st.items() if v in ("lapsing", "dormant"))
    out.append(f"  revenue at risk (paying members lapsing or dormant): ${risk:.0f} a month")
    if opted:
        out.append(f"  ({opted} have not said yes to keeping their activity, or said no, and are not counted)")
    # 1b. The churn rules (the second paper: "start with rules, not models").
    out += ["", "churn flags (members who said yes; the paper's four rules):"]
    for rule, n in churn_flags(ms, today, conn).items():
        out.append(f"  {rule:<56}{n:>5}")
    # 1c. The first paper's numbers: the North Star, the aha moment, recency by frequency.
    ns = north_star(ms, today, conn)
    out += ["", "north star, weekly active sweaters (opened a live game's page with a bet that week or a team "
                "or player they follow):",
            "  this week " + " · ".join([str(ns[0])] + [f"{k} week{'s' if k > 1 else ''} ago {n}"
                                                       for k, n in enumerate(ns[1:], 1)])]
    a = aha(ms, today, conn)
    if a["n"] < AHA_MIN:
        out.append(f"aha moment (a bet logged and a live game watched in the first two days): "
                   f"{a['n']} members signed up 4 to 12 weeks ago, too few to test yet")
    else:
        rest = a["n"] - a["aha"]
        out.append(f"aha moment (a bet logged and a live game watched in the first two days): {a['aha']} of {a['n']} "
                   f"({_pct(a['aha'], a['n'])}); here in days 22-28: {_pct(a['kept_aha'], a['aha'])} of them, "
                   f"{_pct(a['kept_rest'], rest)} of the rest (who did it, not why they stayed)")
    out += ["", "recency by frequency, members here in the last 28 days (paying in brackets):"] + rfm_lines(ms, fs)
    # 2. The power-user curve (L28).
    hist = [0] * 29
    for f in fs.values():
        hist[f["l28"]] += 1
    seen = sum(hist[1:])
    out += ["", f"days active in the last 28 (the power-user curve; {seen} members active at all):"]
    top = max(hist[1:] or [0])
    for k in range(1, 29):
        if hist[k]:
            out.append(f"  {k:>2} {_bar(hist[k], top):<25}{hist[k]}")
    # 3. Stickiness, time, leagues, hours.
    daily: dict = {}
    sports: dict = {}
    hours = [0] * 24
    minutes = []
    taps = visits = 0
    for uid, m in ms.items():
        if m["opted_out"]:
            continue
        for r in m["rows"]:
            if (today - _day(r["day"])).days >= days or not (r["seconds"] or r["visits"]):
                continue
            daily[r["day"]] = daily.get(r["day"], 0) + 1
            for k, v in r["sports"].items():
                sports[k] = sports.get(k, 0) + v
            hours = [a + b for a, b in zip(hours, r["hours"])]
            taps += r["taps"]
            visits += r["visits"]
        if fs[uid]["minutes"]:
            minutes.append(fs[uid]["minutes"])
    mau = sum(1 for f in fs.values() if f["l28"])
    dau = sum(daily.values()) / days
    out += ["", f"stickiness: {dau:.1f} members a day of {mau} in the last 28 days ({_pct(dau, mau)} DAU/MAU)"]
    if minutes:
        out.append(f"time: median {statistics.median(minutes):.0f} minutes an active day")
    tot = sum(v for k, v in sports.items() if k != "other")
    if tot:
        ranked = [(k, v) for k, v in sorted(sports.items(), key=lambda kv: -kv[1]) if k != "other"][:6]
        out.append("by league: " + ", ".join(f"{k.upper()} {_pct(v, tot)}" for k, v in ranked))
    if any(hours):
        busy = sorted(range(24), key=lambda h: -hours[h])[:3]
        out.append("busiest hours (Eastern): " + ", ".join(f"{h:02d}:00" for h in busy))
    if visits:
        out.append(f"visits an alert opened: {taps} of {visits} ({_pct(taps, visits)})")
    with_a = [f["l28"] for u, f in fs.items() if ms[u]["alerts"] and f["age"] >= 28]
    without = [f["l28"] for u, f in fs.items() if not ms[u]["alerts"] and f["age"] >= 28]
    if with_a and without:
        out.append(f"members 28+ days old: with alerts on, {statistics.mean(with_a):.1f} days of 28; "
                   f"without, {statistics.mean(without):.1f} (they chose alerts, so this is who, not why)")
    # 4. New members by signup week: still here in week 1, 2 and 4.
    out += ["", "new members by signup week: on in days 1-7 · 8-14 · 22-28 after signing up"]
    weeks: dict = {}
    for uid, m in ms.items():
        if m["opted_out"] or (since and m["signup"] < since):
            continue
        wk = m["signup"] - _dt.timedelta(days=m["signup"].weekday())
        act = {(d - m["signup"]).days for d in fs[uid]["active_days"]}
        weeks.setdefault(wk, []).append(act)
    for wk in sorted(weeks)[-8:]:
        acts = weeks[wk]
        cells = []
        for lo, hi in ((1, 7), (8, 14), (22, 28)):
            if (today - wk).days < hi + 6:
                cells.append(f"{'—':>6}")
                continue
            back = sum(1 for a in acts if any(lo <= x <= hi for x in a))
            cells.append(f"{_pct(back, len(acts)):>6}")
        out.append(f"  {wk.isoformat()}  {len(acts):>4} members  " + "  ".join(cells))
    if not weeks:
        out.append("  (no member has signed up since the activity log began)")
    # 5. Who is still around: the visit model.
    out.append("")
    if model:
        p = model["params"]
        ho = model.get("heldout") or {}
        probs = []
        for f in fs.values():
            if f["seen"]:
                first = f["active_days"][0]
                probs.append(p_alive(p, *triple(f["active_days"], first, today)))
        out.append(f"visit model: BG/BB fitted {model.get('at')} on {model.get('fitted_on')} members "
                   f"(held out: Brier {ho.get('brier_model')} against the rule's {ho.get('brier_rule')})")
        if probs:
            out.append(f"  still around, on the model: {sum(probs):.0f} of {len(probs)} members seen "
                       f"({_pct(sum(probs), len(probs))})")
    else:
        out.append("visit model: not fitted yet — `python3 -m engine.engagement fit` (stages use the rule alone)")
    # 6. Subscriptions: ARPU, churn, lifetime value.
    paying = [monthly(m) for m in ms.values() if monthly(m) > 0]
    out.append("")
    if paying:
        arpu = statistics.mean(paying)
        churn = _churn(conn, now) if conn is not None else None
        line = f"paying members: {len(paying)}, ${sum(paying):.0f} a month, ${arpu:.2f} each"
        if churn:
            rate, cancels, exposure = churn
            life = min(36.0, 1 / rate) if rate > 0 else 36.0
            line += (f"; cancellations {cancels} in 90 days over {exposure:.0f} member-months "
                     f"= {100 * rate:.1f}% a month, about {life:.0f} months each, lifetime value ~${arpu * life:.0f}")
        else:
            line += "; too little history for a cancellation rate yet (10 member-months is the least)"
        out.append(line)
    else:
        out.append("paying members: none on record here")
    return out


def _churn(conn, now: float | None = None) -> tuple | None:
    """(monthly rate, cancellations, member-months) over the last 90 days, or None."""
    if conn is None or not _table(conn, "subscriptions"):
        return None
    t = time.time() if now is None else now
    cancels = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'canceled' AND updated_at >= ?",
                           (t - 90 * 86400,)).fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'").fetchone()[0]
    exposure = active * 3 + cancels * 1.5            # a cancellation was, on average, half the window in
    return (cancels / exposure, cancels, exposure) if exposure >= 10 else None


# ---- acting on it: "while you were away" ---------------------------------------------------
"""THE "WHILE YOU WERE AWAY" ALERT (topic "away", its own switch in Alerts).

A member whose stage turns lapsing or dormant, with a phone that has the
switch on, hears once — at their own usual hour (best_hour: the most
engaged hour Braze sends at; 19:00 Eastern when there is none yet) — one
line made of their own things: a followed team's game today; else the
newest thing the site shipped since they were last here (web/changelog.json,
an entry's `alert`); else today's slate in the league they read most. Never
"we miss you", never a streak's guilt, never a pick, never "bet now"
(docs/RETENTION.md §1: the alerts regulators move against are the ones
that also get alerts switched off).

At most one a week (AWAY_EVERY_S), and after AWAY_UNANSWERED of them with
no visit in between, none at all until they come back — Duolingo stops its
reminders the same way rather than shouting louder. Gone (60 days) is
gone: nothing is sent to a member past it.
"""
AWAY_TOPIC = "away"
AWAY_EVERY_S = 7 * 86400
AWAY_UNANSWERED = 3
AWAY_DEFAULT_HOUR = 19
#: A slate worth a line: at least this many games today in the member's league.
AWAY_SLATE_MIN = 3
#: The leagues with a fast scoreboard (engine/kickoffs.LEAGUES) and their names.
LEAGUE_NAME = {"nfl": "NFL", "cfb": "college football", "nba": "NBA", "wnba": "WNBA", "nhl": "NHL", "mlb": "MLB"}


def ensure_tables(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS engagement_away (
        user_id INTEGER PRIMARY KEY, sent_at REAL NOT NULL, sent_n INTEGER NOT NULL DEFAULT 0)""")
    conn.commit()


def _today_games(data_dir: Path, now: float) -> list:
    """(league, event, away, home, start) for every game today (Eastern) not yet begun."""
    from engine.gamechat import _when
    from engine.kickoffs import LEAGUES, UNDER_WAY
    from engine.socialfeed import _read
    today = ACT.eastern(now).date()
    out = []
    for lg in LEAGUES:
        for g in (_read(Path(data_dir) / f"live_{lg}.json") or {}).get("games") or []:
            live = g.get("live") or {}
            start = _when(live.get("start_time"))
            event = str(g.get("event_id") or g.get("game_pk") or "")
            if (start is None or not event or start <= now or ACT.eastern(start).date() != today
                    or str(live.get("state") or "").lower() in UNDER_WAY):
                continue
            out.append((lg, event, str(g.get("away") or "").upper(), str(g.get("home") or "").upper(), start))
    return out


def _clock(t: float) -> str:
    e = ACT.eastern(t)
    return f"{(e.hour % 12) or 12}:{e.minute:02d} {'PM' if e.hour >= 12 else 'AM'} ET"


def _whats_new(last_day: _dt.date, path: Path | None = None) -> dict | None:
    try:
        doc = json.loads(Path(path or ROOT / "web" / "changelog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    for e in doc.get("entries") or []:                 # newest first
        if e.get("kind") == "ship" and e.get("alert") and str(e.get("url") or "").startswith("/") \
                and _day(e["date"]) > last_day:
            return e
    return None


def away_hook(conn, user_id, f: dict, games: list, now: float, changelog: Path | None = None) -> tuple | None:
    """(title, body, url) built from the member's own things, or None when
    there is nothing of theirs worth a line today."""
    from engine import divisions as DV
    from engine.kickoffs import follows
    mine = follows(conn, user_id)
    for lg, event, away, home, start in sorted(games, key=lambda g: g[4]):
        if (lg, DV.canonical(lg, away)) in mine or (lg, DV.canonical(lg, home)) in mine:
            return (f"{away} @ {home} today, {_clock(start)}",
                    "Your team’s game: its page, the chat and Call it.", f"/#pbp/{lg}/{event}")
    last = f["active_days"][-1] if f["active_days"] else ACT.eastern(now).date() - _dt.timedelta(days=f["recency"])
    new = _whats_new(last, changelog)
    if new:
        return ("New since you were here", str(new["alert"])[:200], str(new["url"]))
    for lg in f["sports"]:
        n = sum(1 for g in games if g[0] == lg)
        if n >= AWAY_SLATE_MIN and lg in LEAGUE_NAME:
            return (f"{n} {LEAGUE_NAME[lg]} games today",
                    "Scores, the game chats and Call it, all in one place.", f"/?sport={lg}#live")
    return None


def away_pass(conn, data_dir: Path | None = None, now: float | None = None,
              changelog: Path | None = None) -> int:
    """Queue the "while you were away" alert for every member it is due for
    (engine/pushmine sends it). Returns how many were told."""
    from engine import pushmine as PM
    t = time.time() if now is None else float(now)
    if not ACT.enabled():
        return 0
    PM.ensure_tables(conn)
    ensure_tables(conn)
    users = [u for (u,) in conn.execute(
        "SELECT DISTINCT user_id FROM push_subs WHERE user_id IS NOT NULL AND (',' || topics || ',') LIKE ?",
        (f"%,{AWAY_TOPIC},%",))]
    if not users:
        return 0
    today = ACT.eastern(t).date()
    since = first_day(conn)
    games = None
    told = 0
    for uid, m in members(conn, t, users).items():
        if m["opted_out"]:
            continue
        f = features(m["rows"], m["signup"], today, since)
        row = conn.execute("SELECT sent_at, sent_n FROM engagement_away WHERE user_id = ?", (uid,)).fetchone()
        sent_at, sent_n = (float(row[0]), int(row[1])) if row else (0.0, 0)
        if row and f["active_days"] and f["active_days"][-1] >= ACT.eastern(sent_at).date():
            sent_n = 0                                    # they came back since the last one
            conn.execute("UPDATE engagement_away SET sent_n = 0 WHERE user_id = ?", (uid,))
        if stage(f) not in ("lapsing", "dormant") or sent_n >= AWAY_UNANSWERED or t - sent_at < AWAY_EVERY_S:
            continue
        hour = f["best_hour"] if f["best_hour"] is not None else AWAY_DEFAULT_HOUR
        if ACT.eastern(t).hour != hour:
            continue
        if games is None:
            games = _today_games(Path(data_dir) if data_dir else PM.WEB / "data", t)
        hook = away_hook(conn, uid, f, games, t, changelog)
        if not hook:
            continue
        if PM.tell(conn, uid, f"away:{today.isoformat()}", AWAY_TOPIC, *hook, now=t):
            conn.execute("INSERT INTO engagement_away (user_id, sent_at, sent_n) VALUES (?, ?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET sent_at = excluded.sent_at, sent_n = excluded.sent_n",
                         (uid, t, sent_n + 1))
            told += 1
    conn.commit()
    return told


# ---- a made-up population, to see the report before switching it on -----------------------
def demo(seed: int = 7, n: int = 400) -> str:
    """The report on `n` simulated members (BG/BB with known parameters),
    and the fit's recovery of them — nothing read, nothing kept."""
    import random
    from zoneinfo import ZoneInfo
    rnd = random.Random(seed)
    today = _dt.date(2026, 10, 29)
    true = (0.9, 2.2, 0.35, 6.0)                         # p ~ Beta(0.9, 2.2), θ ~ Beta(0.35, 6)
    ms: dict = {}
    # Their My Bets and teams, in memory only, for the lines that read them
    # (the North Star, the aha moment). Logging a bet here is independent of
    # staying, so the demo shows the test's form, never a finding.
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE user_data (user_id INTEGER, section TEXT, ts INTEGER, payload TEXT, "
                 "PRIMARY KEY (user_id, section))")
    for uid in range(1, n + 1):
        signup = today - _dt.timedelta(days=rnd.randint(0, 110))
        p, th = rnd.betavariate(*true[:2]), rnd.betavariate(*true[2:])
        rows, d, alive = [], signup, True
        lg = rnd.choice(["nfl", "nfl", "nba", "nba", "cfb", "nhl", "mlb"])
        hour = rnd.choice([12, 13, 19, 20, 20, 21, 21, 22])
        watcher, bettor = rnd.random() < 0.5, rnd.random() < 0.4
        bets = []
        while d <= today:
            if d == signup or (alive and rnd.random() < p):
                secs = int(rnd.expovariate(1 / 700)) + 30
                hrs = [0] * 24
                hrs[hour] = secs
                views = {"live": secs, **({"pbp": secs // 2} if watcher and rnd.random() < 0.6 else {})}
                rows.append({"day": d.isoformat(), "seconds": secs, "visits": 1 + (secs > 900),
                             "taps": int(rnd.random() < 0.15), "views": views, "sports": {lg: secs},
                             "hours": hrs})
                if bettor and rnd.random() < 0.4:
                    at = _dt.datetime.combine(d, _dt.time(hour), tzinfo=ZoneInfo("America/New_York")).timestamp()
                    bets.append({"id": f"{int(at * 1000)}{rnd.randint(1000, 9999)}", "date": d.isoformat()})
            d += _dt.timedelta(days=1)
            if alive and d > signup and rnd.random() < th:
                alive = False
        if bets:
            conn.execute("INSERT INTO user_data VALUES (?, 'mybets', 1, ?)", (uid, json.dumps({"rows": bets})))
        if rnd.random() < 0.6:
            conn.execute("INSERT INTO user_data VALUES (?, 'settings', 1, ?)",
                         (uid, json.dumps({"teams": [f"{lg}:DEMO"]})))
        ms[uid] = {"signup": signup, "rows": rows, "opted_out": rnd.random() < 0.03,
                   "status": "active" if rnd.random() < 0.18 else "", "plan": rnd.choice(["monthly", "yearly"]),
                   "alerts": rnd.random() < 0.45}
    data = []
    for m in ms.values():
        act = sorted({_day(r["day"]) for r in m["rows"]})
        data.append(triple(act, act[0], today - _dt.timedelta(days=1)))
    got = fit_bgbb(data)
    model = {"params": list(got), "at": today.isoformat(), "fitted_on": len(data), "heldout": {}}
    head = ["Qellys engagement — DEMO on a made-up population of "
            f"{n} (nothing here is real; nothing was read or kept).",
            f"Simulated with p ~ Beta{true[:2]}, θ ~ Beta{true[2:]}; the fit found "
            f"({', '.join(f'{v:.2f}' for v in got)}).", ""]
    return "\n".join(head + _body(ms, today, today - _dt.timedelta(days=110), 28, model, conn))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=("report", "fit", "demo"))
    ap.add_argument("days", nargs="?", type=int, default=28)
    ap.add_argument("--save", action="store_true", help="fit: keep the model if it beats the rule held out")
    a = ap.parse_args(argv)
    if a.what == "demo":
        print(demo())
        return 0
    from engine import accounts
    if not Path(accounts.DB_PATH).exists():
        print("No accounts database here.")
        return 0
    if a.what == "report" and not a.save:
        # Read-only, like every report the catch-up script runs.
        conn = sqlite3.connect(f"file:{accounts.DB_PATH}?mode=ro", uri=True)
        try:
            if not _table(conn, "activity_days"):
                print(f"Qellys engagement: activity {'ON' if ACT.enabled() else 'OFF — ' + ACT.why_off()}; "
                      "nothing has been kept yet.")
                return 0
            print(report(conn, a.days))
        finally:
            conn.close()
        return 0
    conn = accounts.connect()
    try:
        print(json.dumps(fit(conn, save=a.save), indent=1))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
