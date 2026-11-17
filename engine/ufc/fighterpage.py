"""A fighter's own page (2026-11-17).

Ethan, asked whether UFC should have a full fighter page like every other
league's player page (engine/playerpage, js/playerpage.js): "yes full fighter
page". A fighter has no club, no season and no box score a game, so the page
is the fighter's own shape, from what is already kept:

  * bio      the record, age, division and team the dossier holds
             (data/ufc_dossiers.json, engine/ufc/fighters), and the facts
             ESPN's own athlete page publishes where its copy is cached from
             the dossier's draft (nickname, height, weight, reach, stance,
             country, the day born): read from the cache, never fetched here;
  * rates    the career rates the dossier measured (strikes landed and taken
             a minute, striking defence, knockdowns a hundred strikes,
             takedowns a fifteen minutes, their accuracy and the defence
             against them, submission attempts), each said in words;
  * history  every tracked fight newest first with how it ended and both
             fighters' numbers (engine/ufc/history.chart: the fight history
             chart's own reading), the record over them by method, by rounds
             scheduled and by the round it ended;
  * next     the bout on the coming card, if one is booked: the opponent and
             the date (the matchup is a fact; the pick on it is not, and
             stays on the UFC tab).

Facts, not picks, as the other leagues' pages are: served free
(server.py /api/players/page with sport=ufc), drawn by js/playerpage.js. Our
read of a fighter (the archetype, the red flags) stays on the paid side with
the picks (engine/ufc/fighters' own line). Standard library only.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import fighters as _fighters
from . import history as _history

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"
BOARD = ROOT / "web" / "data" / "ufc.json"

#: The dossier's measured rates, in the order a fight site lists them, each
#: with its short label and its words. `ctrl_per15` is left out: ESPN does not
#: publish control time, so the dossier holds a neutral stand-in, not a measure.
RATES = (
    ("slpm", "SLpM", "Significant strikes landed a minute", "rate"),
    ("sapm", "SApM", "Significant strikes taken a minute", "rate"),
    ("str_def", "Str. Def", "Significant strikes avoided", "pct"),
    ("kd_per100", "KD/100", "Knockdowns a hundred significant strikes", "rate"),
    ("td_per15", "TD/15", "Takedowns landed every fifteen minutes", "rate"),
    ("td_acc", "TD Acc", "Takedowns landed of those tried", "pct"),
    ("tdd", "TD Def", "Opponents' takedowns stopped", "pct"),
    ("sub_att_per15", "Sub/15", "Submission attempts every fifteen minutes", "rate"),
)
#: The four the page leads with.
HEADLINE = ("slpm", "str_def", "td_per15", "tdd")


def division_words(s) -> str:
    """A division as a fight site writes it: "light_heavyweight" is "Light
    Heavyweight", and "women's strawweight" keeps its apostrophe's s small."""
    return " ".join(w[:1].upper() + w[1:] for w in str(s or "").replace("_", " ").split())


def _fold(s) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def dossier_of(name: str, dossiers: dict) -> tuple[str, dict]:
    """The dossier's own spelling of a fighter and the dossier, or ("", {})."""
    if name in dossiers:
        return name, dossiers[name]
    want = _fold(name)
    hits = [k for k in dossiers if _fold(k) == want] if want else []
    return (hits[0], dossiers[hits[0]]) if len(hits) == 1 else ("", {})


def _rate(key: str, v) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    # A share the dossier keeps as 0-1 is shown as a percent; one kept as a percent stays one.
    kind = next((k for r, _, _, k in RATES if r == key), "rate")
    if kind == "pct":
        return round(x * 100 if x <= 1.0 else x, 1)
    return round(x, 2)


def rates(d: dict) -> list[dict]:
    """The dossier's measured rates, each with its label and words."""
    out = []
    for key, label, words, kind in RATES:
        v = _rate(key, d.get(key))
        if v is not None:
            out.append({"key": key, "label": label, "title": words, "value": v, "pct": kind == "pct",
                        "lead": key in HEADLINE})
    return out


def espn_bio(aid: str, cache_dir=None) -> dict:
    """The facts ESPN's athlete page publishes, from the copy the dossier's
    draft cached (engine/sources/espnmma); {} when there is none. Never
    fetches: the page answers from what is kept."""
    from ..sources.espnmma import bio_facts
    if not str(aid or "").isdigit():
        return {}
    p = Path(cache_dir or CACHE) / f"espn_mma_ath_{aid}.json"
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return bio_facts(raw)


def next_bout(name: str, board_path=None) -> dict | None:
    """The bout on the coming card with this fighter in it: ``{opponent, date,
    division}``, or None. Read from the full board (the matchup is a fact)."""
    try:
        from .. import gate
        path = gate.board_source(board_path or BOARD)
    except Exception:                                        # noqa: BLE001
        path = Path(board_path or BOARD)
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("status") != "card":
        return None
    want = _fold(name)
    for row in list(d.get("picks") or []) + list(d.get("pass_list") or []):
        fight = str((row or {}).get("fight") or "")
        sides = [s.strip() for s in fight.split(" vs ")]
        if len(sides) != 2:
            continue
        for i, s in enumerate(sides):
            if _fold(s) == want:
                return {"opponent": sides[1 - i], "date": str(d.get("event_date") or ""),
                        "division": division_words(row.get("division"))}
    return None


def page(fighter: str, db_path=None, dossier_path=None, cache_dir=None, board_path=None) -> dict:
    """Everything the fighter's page shows; ``{}`` for a name neither the
    dossiers nor the fight history knows."""
    if not fighter:
        return {}
    dossiers = _fighters.load(dossier_path)
    name, d = dossier_of(fighter, dossiers)
    hist: dict = {}
    read: dict = {"aid": "", "facts": {}}
    try:
        from .. import db as _db
        path = str(db_path or _db.DEFAULT_DB)
        if os.path.exists(path):
            conn = _db.connect(path)
            try:
                hist = _history.chart(conn, name or fighter) or {}
                # The id and facts the fight history's read kept (every
                # dossier fighter's, nightly): a fighter with no fight on
                # file still has a face and facts.
                read = _history.kept(conn, name or hist.get("player") or fighter)
            finally:
                conn.close()
    except Exception:                                        # noqa: BLE001
        hist = {}
    name = name or hist.get("player") or ""
    if not name:
        return {}
    games = hist.get("games") or []
    # ESPN's id and the facts its athlete page publishes, kept in the dossier
    # since 2026-11-17 (engine/sources/espnmma.fetch_dossier), so a page needs
    # no cache the nightly prunes after a month; older dossiers read the cache.
    aid = str(d.get("espn_id") or "")
    m = re.search(r"/full/(\d+)\.png", str(hist.get("face") or ""))
    if m and not aid:
        aid = m.group(1)
    aid = aid or read.get("aid") or ""
    face = hist.get("face") or (_history.FACE.format(aid=aid) if aid else "")
    if not aid:
        # Nothing read for the fighter yet (seen live 2026-11-17: Islam Makhachev's page had the record and
        # rates and no face, no height, no reach): ESPN's id from the name search the dossier's draft kept.
        from ..sources import espnmma
        aid = espnmma.cached_athlete_id(name, cache_dir or CACHE) or ""
        if aid:
            face = _history.FACE.format(aid=aid)   # the fight history chart's own
    facts = next((f for f in (d.get("facts"), read.get("facts")) if isinstance(f, dict) and f), None) \
        or espn_bio(aid, cache_dir)
    bio = {"record": d.get("record") or "", "division": division_words(d.get("division") or hist.get("position")),
           "age": d.get("age"), "team": str(d.get("gym") or "").strip(),
           "first_fight": d.get("first_fight") or (games[-1]["date"] if games else ""),
           "last_fight": d.get("last_fight") or (games[0]["date"] if games else ""),
           "ufc_fights": d.get("ufc_fights"), "career_fights": d.get("career_fights"), **facts}
    return {"player": name, "sport": "ufc", "face": face,
            "bio": {k: v for k, v in bio.items() if v not in (None, "")},
            "rates": rates(d), "tracked": len(games),
            "fights": games, "line": hist.get("season_line") or {},
            "by_method": hist.get("by_method") or [], "by_rounds": hist.get("by_rounds") or [],
            "by_finish": hist.get("by_finish") or [], "next": next_bout(name, board_path)}
