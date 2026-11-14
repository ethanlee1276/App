"""What changed: every game report's record of what moved since it was first written.

Ethan, 2026-10-20 ("I want you too do all of it besides D"), the "what
changed" log of that list: a report written on Tuesday is read on Sunday,
and by then the line has moved, a man has been ruled out and the forecast
has turned. The report is rewritten every build, so it is always current
— and so a reader cannot see what changed. This keeps that.

ONE SNAPSHOT A GAME, ONE FILE A LEAGUE. Each build takes a small snapshot
of every game's facts (the spread and total, kickoff, the simulator, the
injury report, pulled props, the forecast, the key players' reads, how
the listed players practised, a quarterback change) and compares it with
the one kept. What moved is written as sentences under the build's time.
The file sits beside the build's full board in the private directory
(engine/gate._full_dir_for), never in the public tree: the reads are
paid, and so is a log of them.

ONLY WHAT A READER WOULD CALL A CHANGE. A spread or total is a change
when it has moved half a point; the simulator when its home chance has
moved five points; the forecast when the temperature has moved 5°F, the
wind 5 mph or the chance of rain 20 points, or rain or snow comes or
goes. A number that has not moved that far keeps its old value in the
snapshot, so a line that creeps a quarter point a build is written when
the creep reaches half a point, not lost a quarter at a time.

A FACT THE BUILD COULD NOT READ IS NOT A CHANGE. A build whose scan, reads
or forecast failed leaves that fact out of its snapshot, and the kept
value stands: a feed that blinks does not write "came off the injury
report" for every name on it and "was listed" for every name the build
after.

Standard library only. Never raises out of ``update``.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

#: The bars a number must move by before it is a change.
LINE_STEP = 0.5
SIM_STEP = 0.05
TEMP_STEP = 5.0
WIND_STEP = 5.0
PRECIP_STEP = 0.20

#: How many dated entries a game keeps, and how many days past its date a
#: game stays in the file.
MAX_ENTRIES = 12
KEEP_DAYS = 10

#: The injury report's statuses (engine/gamescan.OUT_STATUSES and
#: QUESTIONABLE), in words.
STATUS_WORDS = {"out": "out", "ir": "on injured reserve", "doubtful": "doubtful",
                "pup": "on the PUP list", "suspended": "suspended", "inactive": "inactive",
                "questionable": "questionable"}

#: The statuses that keep a player off the field (engine/gamescan.OUT_STATUSES).
OUT = {"out", "ir", "doubtful", "pup", "suspended", "inactive"}

#: The scan's reads (engine/gamescan.READS), in words.
READ_WORDS = {"breakout": "favorable, a breakout candidate", "good": "favorable",
              "neutral": "neutral", "tough": "unfavorable", "avoid": "unfavorable, one to avoid"}

#: How a listed player practised (engine/practice.PRACTICE), in words.
PRACTICE_WORDS = {"DNP": "did not practice", "Limited": "was limited in practice",
                  "Full": "practiced fully"}


def path_for(sport: str, where) -> Path:
    return Path(where) / f"reportlog_{sport}.json"


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def game_key(g: dict) -> str:
    return f"{g.get('away')}@{g.get('home')}|{str(g.get('date') or '')[:10]}"


# --- the snapshot -------------------------------------------------------------------------
def facts(g: dict, result: dict | None, extra: dict | None = None, is_key=None,
          more: dict | None = None) -> dict:
    """One game's snapshot. A fact the build did not read is left out.
    ``more`` is what a league knows that its board's rows do not carry in
    the football shape (engine/leaguereport): "starters" {team: name} with
    "starter_word", "injuries" {player: status}, "weather", "who"."""
    result = result or {}
    out: dict = {}
    who: dict = {}
    for k in ("spread", "total"):
        v = _f(g.get(k))
        if v is not None:
            out[k] = v
    if g.get("kickoff"):
        out["kickoff"] = str(g["kickoff"])
    sim = _f((g.get("sim") or {}).get("p_home_win"))
    if sim is not None:
        out["sim_home"] = round(sim, 3)
    w = g.get("weather") or {}
    if w.get("forecast") and not w.get("dome") and not g.get("indoor"):
        out["weather"] = {k: w.get(k) for k in ("temp_f", "wind_mph", "precip_chance", "rain", "snow")
                          if w.get(k) is not None}
    scan = g.get("scan")
    if isinstance(scan, dict):
        inj = {}
        for r in scan.get("injuries") or []:
            if isinstance(r, dict) and r.get("player"):
                inj[str(r["player"])] = str(r.get("status") or "").lower()
                who[str(r["player"])] = " ".join(str(x) for x in (r.get("team"), r.get("position")) if x)
        out["injuries"] = inj
        out["pulled"] = sorted(str(p) for p in scan.get("pulled") or [] if p)
    reads = (result.get("scan_reads") or {}).get(f"{g.get('away')}@{g.get('home')}") or {}
    rows = [r for r in reads.get("players") or [] if isinstance(r, dict) and r.get("player")]
    if rows:
        out["reads"] = {}
        for r in rows:
            who.setdefault(str(r["player"]), " ".join(str(x) for x in (r.get("team"), r.get("pos")) if x))
            if r.get("read") and (is_key is None or is_key(r)):
                out["reads"][str(r["player"])] = str(r["read"])
    if "qb_changes" in result:
        out["qb"] = sorted(str(q.get("headline")) for q in result.get("qb_changes") or []
                           if isinstance(q, dict) and q.get("headline")
                           and q.get("team") in (g.get("home"), g.get("away")))
    prac = (extra or {}).get("practice")
    if isinstance(prac, dict):
        out["practice"] = {}
        for x in prac.get("rows") or []:
            if isinstance(x, dict) and x.get("player") and x.get("practice") in PRACTICE_WORDS:
                out["practice"][str(x["player"])] = str(x["practice"])
                who.setdefault(str(x["player"]), str(x.get("team") or ""))
    for k, v in (more or {}).items():
        if k == "who":
            who.update(v or {})
        elif v is not None:
            out[k] = v
    out["who"] = {p: t for p, t in who.items() if t}
    return out


# --- what moved -----------------------------------------------------------------------------
def _spread_words(sp: float, home: str, away: str) -> str:
    if sp == 0:
        return "a pick'em"
    fav = home if sp < 0 else away
    return f"{fav} −{abs(sp):g}"


def _clock(hhmm: str) -> str:
    try:
        hh, mm = (int(x) for x in str(hhmm).split(":")[:2])
    except ValueError:
        return str(hhmm)
    return f"{(hh % 12) or 12}:{mm:02d} {'PM' if hh >= 12 else 'AM'}"


def _weather_words(w: dict) -> str:
    bits = []
    if _f(w.get("temp_f")) is not None:
        bits.append(f"{round(float(w['temp_f']))}°F")
    if _f(w.get("wind_mph")) is not None:
        bits.append(f"wind {round(float(w['wind_mph']))} mph"
                    + (f" blowing {w['wind_dir']}" if w.get("wind_dir") in ("in", "out") else ""))
    if _f(w.get("precip_chance")) is not None and float(w["precip_chance"]) > 0:
        bits.append(f"a {round(float(w['precip_chance']) * 100)}% chance of rain")
    if w.get("snow"):
        bits.append("snow")
    elif w.get("rain"):
        bits.append("rain")
    return ", ".join(bits) or "no forecast"


def _weather_moved(a: dict, b: dict) -> bool:
    def step(k, bar):
        x, y = _f(a.get(k)), _f(b.get(k))
        return x is not None and y is not None and abs(x - y) >= bar
    turned = a.get("wind_dir") in ("in", "out") and b.get("wind_dir") in ("in", "out") \
        and a["wind_dir"] != b["wind_dir"]
    return (step("temp_f", TEMP_STEP) or step("wind_mph", WIND_STEP) or step("precip_chance", PRECIP_STEP)
            or bool(a.get("rain")) != bool(b.get("rain")) or bool(a.get("snow")) != bool(b.get("snow"))
            or turned)


def _moved(old: dict, new: dict, k: str, bar: float):
    a, b = _f(old.get(k)), _f(new.get(k))
    return (a, b) if a is not None and b is not None and abs(a - b) >= bar else None


def diff(old: dict, new: dict, home: str, away: str) -> list:
    """The sentences for what moved from ``old`` to ``new``; [] for nothing.
    A fact either snapshot lacks is not compared."""
    out = []
    who = {**(old.get("who") or {}), **(new.get("who") or {})}

    def name(p):
        return f"{p} ({who[p]})" if who.get(p) else p

    m = _moved(old, new, "spread", LINE_STEP)
    if m:
        out.append(f"The spread moved from {_spread_words(m[0], home, away)} to {_spread_words(m[1], home, away)}")
    m = _moved(old, new, "total", LINE_STEP)
    if m:
        out.append(f"The total moved from {m[0]:g} to {m[1]:g}")
    if old.get("kickoff") and new.get("kickoff") and old["kickoff"] != new["kickoff"]:
        out.append(f"Kickoff moved from {_clock(old['kickoff'])} to {_clock(new['kickoff'])} ET")
    m = _moved(old, new, "sim_home", SIM_STEP)
    if m:
        out.append(f"Our simulator moved {home} from {round(m[0] * 100)}% to {round(m[1] * 100)}% to win")
    if "injuries" in old and "injuries" in new:
        oi, ni = old["injuries"], new["injuries"]
        for p in sorted(set(oi) | set(ni)):
            if p not in oi:
                out.append(f"{name(p)} was listed {STATUS_WORDS.get(ni[p], ni[p])}")
            elif p not in ni:
                out.append(f"{name(p)} came off the injury report; he was {STATUS_WORDS.get(oi[p], oi[p])}")
            elif oi[p] != ni[p]:
                out.append(f"{name(p)} is now {STATUS_WORDS.get(ni[p], ni[p])}; he was "
                           f"{STATUS_WORDS.get(oi[p], oi[p])}")
    if "pulled" in old and "pulled" in new:
        op, np_ = set(old["pulled"]), set(new["pulled"])
        for p in sorted(np_ - op):
            out.append(f"Every book took {name(p)}'s props down")
        # NOT "BACK UP" FOR A MAN STILL LISTED OUT. Kyle Monangai,
        # 2026-10-22, ruled out a third straight game: "Kyle Monangai's
        # props are back up" sat under a report that said he was out. The
        # pull memory now keeps him down until a pull prices him
        # (engine/pricedplayers); a book that lists an out player's name
        # again is still not news a reader can use.
        listed = {p for p, st in (new.get("injuries") or {}).items() if st in OUT}
        for p in sorted(op - np_ - listed):
            out.append(f"{name(p)}'s props are back up")
    ow, nw = old.get("weather"), new.get("weather")
    if ow and nw and _weather_moved(ow, nw):
        out.append(f"The forecast moved from {_weather_words(ow)} to {_weather_words(nw)}")
    elif nw and not ow:
        out.append(f"The first forecast is in: {_weather_words(nw)}")
    if "reads" in old and "reads" in new:
        orr, nr = old["reads"], new["reads"]
        for p in sorted(set(orr) & set(nr)):
            if orr[p] != nr[p]:
                out.append(f"The read on {name(p)} went from {READ_WORDS.get(orr[p], orr[p])} to "
                           f"{READ_WORDS.get(nr[p], nr[p])}")
    if "qb" in old and "qb" in new:
        out += sorted(set(new["qb"]) - set(old["qb"]))
    os_, ns = old.get("starters") or {}, new.get("starters") or {}
    word = new.get("starter_word") or old.get("starter_word") or "starter"
    for t in sorted(set(os_) & set(ns)):
        if os_[t] and ns[t] and os_[t] != ns[t]:
            out.append(f"{t}'s {word} is now {ns[t]}, not {os_[t]}")
    for t in sorted(set(ns) - set(os_)):
        if "starters" in old and ns[t]:
            out.append(f"{t} named its {word}: {ns[t]}")
    oc, nc = old.get("confirmed") or {}, new.get("confirmed") or {}
    for t in sorted(set(oc) & set(nc)):
        if not oc[t] and nc[t] and ns.get(t):
            out.append(f"{t}'s {word} is confirmed: {ns[t]}")
    if old.get("lineups") is False and new.get("lineups") is True:
        out.append("Both lineups are out")
    if "practice" in old and "practice" in new:
        opr, npr = old["practice"], new["practice"]
        for p in sorted(set(opr) & set(npr)):
            if opr[p] != npr[p]:
                out.append(f"{name(p)} {PRACTICE_WORDS[npr[p]]}, after he {PRACTICE_WORDS[opr[p]]}")
    return out


def drop_false_returns(entries: list, last: dict) -> list:
    """The kept entries without a "props are back up" for a player the
    latest snapshot still lists out — the line the old pull memory wrote
    and never should have (Kyle Monangai, 2026-10-22). An entry left with
    nothing goes."""
    who = last.get("who") or {}
    out = {p for p, st in (last.get("injuries") or {}).items() if st in OUT}
    if not out:
        return entries
    bad = {f"{p}'s props are back up" for p in out} | \
          {f"{p} ({who[p]})'s props are back up" for p in out if who.get(p)}
    keep = []
    for e in entries:
        changes = [x for x in e.get("changes") or [] if x not in bad]
        if changes:
            keep.append({**e, "changes": changes})
    return keep


def carry(old: dict, new: dict) -> dict:
    """The snapshot to keep: ``new``, except that a number that has not
    moved past its bar keeps its old value (so slow drift still adds up)
    and a fact this build could not read keeps the old one."""
    keep = {**old, **new}
    for k, bar in (("spread", LINE_STEP), ("total", LINE_STEP), ("sim_home", SIM_STEP)):
        if _f(old.get(k)) is not None and _f(new.get(k)) is not None and not _moved(old, new, k, bar):
            keep[k] = old[k]
    ow, nw = old.get("weather"), new.get("weather")
    if ow and nw and not _weather_moved(ow, nw):
        keep["weather"] = ow
    keep["who"] = {**(old.get("who") or {}), **(new.get("who") or {})}
    # A starter not named this build (still "to be announced") keeps the
    # last one named: an announcement that blinks is not a change.
    if isinstance(old.get("starters"), dict) and isinstance(new.get("starters"), dict):
        keep["starters"] = {**old["starters"], **{t: n for t, n in new["starters"].items() if n}}
    return keep


# --- the file -------------------------------------------------------------------------------
def read(path) -> dict:
    try:
        with open(path) as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(path, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(tmp, "w") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, p)


def update(path, snapshots: dict, at: str, today: _dt.date | None = None) -> dict:
    """Fold this build's ``snapshots`` ({game_key: (facts, home, away)}) into
    the file at ``path``; → {game_key: {"first", "at", "entries" (oldest
    first)}} for this build's games. Never raises: a file that cannot be
    read or written leaves every report without the section and prints
    "what changed not kept (<error>)" — the empty answer a quiet slate
    gives too must not pass for one."""
    try:
        data = read(path)
        games = data.get("games") if isinstance(data.get("games"), dict) else {}
        out = {}
        for key, (snap, home, away) in snapshots.items():
            rec = games.get(key)
            if not isinstance(rec, dict) or not isinstance(rec.get("last"), dict):
                rec = {"first": at, "last": snap, "entries": []}
            else:
                moved = diff(rec["last"], snap, home, away)
                if moved:
                    rec["entries"] = (list(rec.get("entries") or []) + [{"at": at, "changes": moved}])[-MAX_ENTRIES:]
                rec["last"] = carry(rec["last"], snap)
                rec["entries"] = drop_false_returns(rec.get("entries") or [], rec["last"])
            games[key] = rec
            out[key] = {"first": rec["first"], "at": at, "entries": list(rec.get("entries") or [])}
        if today is None:
            # The build's own day (its stamp), so the window moves with the
            # builds and not with whatever clock reads the file.
            try:
                today = _dt.date.fromisoformat(str(at)[:10])
            except ValueError:
                today = _dt.date.today()
        for key in list(games):
            try:
                day = _dt.date.fromisoformat(key.rsplit("|", 1)[-1])
            except ValueError:
                games.pop(key)
                continue
            if (today - day).days > KEEP_DAYS:
                games.pop(key)
        _write(path, {"games": games})
        return out
    except Exception as exc:                                 # noqa: BLE001
        # {} is also a slate with no games, so the failure says itself.
        print(f"⚠️  what changed not kept ({type(exc).__name__}: {exc})")
        return {}


def now_et() -> str:
    """This moment on the Eastern clock the site's kickoffs are given in."""
    try:
        from zoneinfo import ZoneInfo
        t = _dt.datetime.now(ZoneInfo("America/New_York"))
    except Exception:                                        # noqa: BLE001
        t = _dt.datetime.now()
    return t.replace(tzinfo=None).isoformat(timespec="seconds")


def when_words(at: str) -> str:
    """"Wed 2:10 PM" from a stamp of now_et()."""
    try:
        t = _dt.datetime.fromisoformat(str(at))
    except ValueError:
        return str(at)
    return f"{t.strftime('%a')} {(t.hour % 12) or 12}:{t.minute:02d} {'PM' if t.hour >= 12 else 'AM'}"
