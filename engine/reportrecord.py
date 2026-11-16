"""How our game reports have done: every finished game's fact check, in one list (2026-11-16).

Ethan, 2026-11-16: "think about what users would want to see after the game's
over ... they'd probably want to see if the data we were giving them were
correct or not, and the read we had was correct or not ... So we need to fact
check ourselves after the game's over and see if we were correct or not";
and before it, "people should be able to go back and still look at this data
and see if we were right or not."

Every finished game's report is graded on its box score and kept for good
(engine/reportgrade, engine/reportfacts, engine/reportarchive). This module
reads that archive back as the reports' own record: one row a game, newest
first, and the totals over them, by league (the Report Picks page's "How our
reports did"; not My Bets' report card, engine/reportcard, which is yours):

  * the call on who wins, right or wrong; our team ratings' own pick and the
    simulation's, each right or wrong;
  * the reads, right of graded, in all and by kind (matchups, breakout
    candidates, fades, starters, angles, offense against defense, how the game
    would go);
  * the lines against the final (who covered, which side of the total);
  * the injury report, right and wrong, and the regulars it missed;
  * the touchdown chances: how many scored, against how many our chances said.

Counts and names only — never a read's words, a pick or a price, which stay
in the archived report a member opens (/api/report_archive). So the record is
free (/api/report_record): our record on our own reports, for anyone to check.

The rows are kept in an index beside the archive (`report_archive/<league>/
index.json`), rebuilt for a file only when the file changed; the build writes
it after each archive save, the server only reads it. Standard library only;
nothing here raises past `refresh`, which a build calls.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
from pathlib import Path

INDEX = "index.json"
#: Bumped when a row's shape changes, so every row is read again once.
ROW_VERSION = 1
#: The rows the record sends: the newest this many.
CARD_ROWS = 400
#: The recent window the record totals beside the whole archive.
RECENT_DAYS = 30


def _f(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _pair(right, n) -> list:
    return [int(right or 0), int(n or 0)]


def row_of(doc: dict) -> dict | None:
    """One archived game as a row: counts and names, nothing paid."""
    if not isinstance(doc, dict) or not isinstance(doc.get("report"), dict):
        return None
    rep = doc["report"]
    gr = rep.get("graded") or {}
    if gr.get("status") != "graded":
        return None
    away, home = doc.get("away") or rep.get("away"), doc.get("home") or rep.get("home")
    if not away or not home:
        return None
    names = {away: away, home: home}
    for s in rep.get("sections") or []:
        for b in s.get("blocks") or [] if s.get("key") == "verdict" else []:
            if isinstance(b, dict) and b.get("type") == "winner":
                if b.get("team") and b.get("name"):
                    names[b["team"]] = b["name"]
                if b.get("other") and b.get("other_name"):
                    names[b["other"]] = b["other_name"]
    fin = doc.get("final") or {}
    row: dict = {"v": ROW_VERSION, "date": str(doc.get("date") or rep.get("date") or "")[:10],
                 "game": f"{away}@{home}", "away": away, "home": home, "names": names,
                 "final": {"away": _f(fin.get("away")), "home": _f(fin.get("home"))},
                 "reads": _pair(gr.get("right"), gr.get("graded")),
                 "groups": {g["key"]: _pair(g.get("right"), g.get("graded")) for g in gr.get("groups") or []
                            if isinstance(g, dict) and g.get("key") and g.get("graded")}}
    call = gr.get("call")
    if isinstance(call, dict) and call.get("team"):
        row["call"] = {"team": call["team"], "right": bool(call.get("right"))}
    for k in ("ratings", "sim"):
        x = gr.get(k)
        if isinstance(x, dict) and x.get("status") in ("right", "wrong"):
            row[k] = x["status"]
    if isinstance(gr.get("sim"), dict) and gr["sim"].get("script"):
        row["script"] = gr["sim"]["script"]
    sc = gr.get("score")
    if isinstance(sc, dict):
        row["lines"] = {k: sc[k] for k in ("cover", "side") if k in sc}
    inj = gr.get("injuries")
    if isinstance(inj, dict):
        row["injuries"] = _pair(inj.get("right"), int(inj.get("right") or 0) + int(inj.get("wrong") or 0))
        row["missed"] = len(inj.get("missed_names") or [])
    td = gr.get("tds")
    if isinstance(td, dict) and td.get("n"):
        row["tds"] = [int(td.get("scored") or 0), int(td["n"]), round(_f(td.get("expected")) or 0.0, 2)]
    return row


def totals(rows: list) -> dict:
    """The totals over ``rows``."""
    out = {"games": 0, "call": [0, 0], "reads": [0, 0], "groups": {}, "ratings": [0, 0], "sim": [0, 0],
           "injuries": [0, 0], "missed": 0, "tds": [0, 0, 0.0], "since": "", "through": ""}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        out["games"] += 1
        d = str(r.get("date") or "")
        if d:
            out["since"] = min(out["since"] or d, d)
            out["through"] = max(out["through"], d)
        if r.get("call"):
            out["call"][0] += bool(r["call"].get("right"))
            out["call"][1] += 1
        for k in ("ratings", "sim"):
            if r.get(k) in ("right", "wrong"):
                out[k][0] += r[k] == "right"
                out[k][1] += 1
        for k, (a, n) in (("reads", r.get("reads") or (0, 0)), ("injuries", r.get("injuries") or (0, 0))):
            out[k][0] += int(a)
            out[k][1] += int(n)
        for k, (a, n) in (r.get("groups") or {}).items():
            g = out["groups"].setdefault(k, [0, 0])
            g[0] += int(a)
            g[1] += int(n)
        out["missed"] += int(r.get("missed") or 0)
        if r.get("tds"):
            out["tds"][0] += int(r["tds"][0])
            out["tds"][1] += int(r["tds"][1])
            out["tds"][2] = round(out["tds"][2] + float(r["tds"][2]), 2)
    return out


# --- the index beside the archive ------------------------------------------------------------
def _dir(where, sport: str) -> Path:
    from .reportarchive import DIR
    return Path(where) / DIR / str(sport)


def _read_index(path: Path) -> dict:
    try:
        x = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return x.get("files") or {} if isinstance(x, dict) and x.get("v") == ROW_VERSION else {}


def rows(where, sport: str, write: bool = True) -> list:
    """Every archived game of the league as a row, newest first. A file's
    row is read again only when the file changed; ``write`` keeps the index
    (a build), else it is only read (the server)."""
    base = _dir(where, sport)
    if not base.is_dir():
        return []
    path = base / INDEX
    old = _read_index(path)
    new: dict = {}
    changed = False
    for f in sorted(base.glob("*/*.json.gz")):
        rel = f"{f.parent.name}/{f.name}"
        try:
            st = f.stat()
        except OSError:
            continue
        stamp = [st.st_size, st.st_mtime_ns]
        hit = old.get(rel)
        if isinstance(hit, dict) and hit.get("stamp") == stamp:
            new[rel] = hit
            continue
        try:
            doc = json.loads(gzip.decompress(f.read_bytes()))
        except (OSError, ValueError, EOFError, gzip.BadGzipFile):
            continue
        new[rel] = {"stamp": stamp, "row": row_of(doc)}
        changed = True
    if set(new) != set(old):
        changed = True
    if write and changed:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps({"v": ROW_VERSION, "files": new}, separators=(",", ":")), encoding="utf-8")
        tmp.replace(path)
    out = [x["row"] for x in new.values() if isinstance(x, dict) and isinstance(x.get("row"), dict)]
    out.sort(key=lambda r: (r.get("date") or "", r.get("game") or ""), reverse=True)
    return out


def refresh(where, sport: str) -> int:
    """The league's index brought up to date (a build, after its archive
    save). Returns the games on the record; never raises."""
    try:
        return len(rows(where, sport, write=True))
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ the reports' record not refreshed ({type(exc).__name__}: {exc})")
        return 0


def record(where, sport: str, today: str | None = None) -> dict:
    """The league's record on its reports: totals over every graded game and
    over the last RECENT_DAYS, and the newest CARD_ROWS games."""
    every = rows(where, sport, write=False)
    try:
        day = _dt.date.fromisoformat(str(today or "")[:10])
    except ValueError:
        day = _dt.date.today()
    since = (day - _dt.timedelta(days=RECENT_DAYS)).isoformat()
    recent = [r for r in every if str(r.get("date") or "") >= since]
    return {"sport": sport, "totals": totals(every), "recent": totals(recent), "recent_days": RECENT_DAYS,
            "games": every[:CARD_ROWS], "more": max(0, len(every) - CARD_ROWS)}
