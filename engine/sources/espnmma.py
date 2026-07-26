"""ESPN MMA → fighter dossiers, automatically drafted.

UFCStats walled itself off behind a JavaScript bot-challenge, so the
dossier pipeline reads ESPN's public sports API instead — keyless JSON,
the same family of endpoints that already feeds our NFL scores. Probed
shapes (July 2026):

  * search v2         → athlete id from the odds feed's name spelling
  * core athlete      → age / DOB / weight / gender
  * core records      → career W-L-D ("29-11-2")
  * v3 stats          → per-fight rows: sig strikes, KD, TD, sub attempts
  * core eventlog     → each fight's competition ref
  * competition       → date, opponent, WINNER flag, division, round format
  * competition status→ finish method + stoppage clock

What that buys over the old label-scrape: the rates are MEASURED here.
Fight minutes come from (rounds − 1)×5:00 + stoppage time, so SLpM is
our own sum of landed strikes over our own sum of minutes — and the
opponent's rows in the same fights give absorbed strikes, striking
defense, and takedown defense as things that actually happened.

Cost control: the per-fight loop covers the last ``WINDOW`` fights
(recent durability is signal; a 2015 KO loss says little in 2026), so
one fighter is ~50 small cached requests, a full card a few minutes the
first time and instant after. Counts derived inside the window say so
in the dossier's review notes.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import time
import urllib.parse
import urllib.request

from .fetch import CACHE_DIR, DataUnavailable

SEARCH = "https://site.web.api.espn.com/apis/search/v2?query={q}&limit=10"
V3_STATS = ("https://site.web.api.espn.com/apis/common/v3/sports/mma/"
            "athletes/{id}/stats")
CORE = "https://sports.core.api.espn.com/v2/sports/mma/leagues/ufc"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
FETCH_PAUSE_S = 0.25
_TTL = 3 * 24 * 3600
WINDOW = 15                      # fights the per-fight loop analyzes
ROUND_S = 300.0

_last_fetch = 0.0


def _get_json(url: str, cache_name: str, ttl: int = _TTL) -> dict:
    global _last_fetch
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        wait = FETCH_PAUSE_S - (time.time() - _last_fetch)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        _last_fetch = time.time()
        data = json.loads(text)
        path.write_text(text, encoding="utf-8")
        return data
    except Exception as exc:  # noqa: BLE001 — offline → stale cache or raise
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise DataUnavailable(f"Could not fetch {url}: {exc}") from exc


# Letters accent-stripping can't fix: they don't decompose under NFD
# (ł is its own letter, not l + diacritic), so map them by hand.
_STROKES = str.maketrans({"ł": "l", "Ł": "L", "ø": "o", "Ø": "O",
                          "đ": "d", "Đ": "D", "ð": "d", "þ": "th",
                          "æ": "ae", "œ": "oe", "ß": "ss", "’": "'"})


def _norm(s: str) -> str:
    from .oddsapi import normalize_name
    return normalize_name(s.translate(_STROKES))


# --- athlete lookup ---------------------------------------------------------
def _search_players(query: str) -> list[tuple[str, str]]:
    """Search hits typed 'player' → [(display name, athlete id)]."""
    data = _get_json(SEARCH.format(q=urllib.parse.quote(query)),
                     f"espn_mma_search_{_norm(query).replace(' ', '_')}.json")
    players: list[tuple[str, str]] = []
    for rt in data.get("results", []) or []:
        if rt.get("type") != "player":
            continue
        for item in rt.get("contents", []) or []:
            if item.get("description") not in (None, "", "MMA"):
                continue
            m = re.search(r"/id/(\d+)", json.dumps(item.get("link", {})))
            if m:
                players.append((item.get("displayName", ""), m.group(1)))
    return players


def _match_player(players: list[tuple[str, str]], name: str) -> str | None:
    target = _norm(name)
    for disp, pid in players:
        if _norm(disp) == target:
            return pid
    if len(players) == 1:
        return players[0][1]
    parts = set(target.split())
    loose = [pid for disp, pid in players if parts <= set(_norm(disp).split())]
    return loose[0] if len(loose) == 1 else None


def find_athlete_id(name: str) -> str | None:
    """Odds-feed name → ESPN athlete id.

    Full-name search first; when that finds nothing (apostrophes and
    local spellings trip exact search — "L'udovit" vs ESPN's "Ludovit"),
    retry on the last name alone and match loosely."""
    pid = _match_player(_search_players(name), name)
    if pid:
        return pid
    last = name.strip().split()[-1] if name.strip() else ""
    if last and last.lower() != name.strip().lower():
        return _match_player(_search_players(last), name)
    return None


# --- per-fight stat rows (own and opponents') -------------------------------
# label → our key, per category. Labels sometimes carry stray tabs.
_WANTED = {"SSL": "ssl", "SSA": "ssa", "KD": "kd",
           "TDL": "tdl", "TDA": "tda", "SM": "sm"}


def parse_stat_rows(stats_json: dict) -> dict[str, dict]:
    """{eventId: {ssl, ssa, kd, tdl, tda, sm}} from a v3-stats payload."""
    rows: dict[str, dict] = {}
    for cat in stats_json.get("categories", []) or []:
        labels = [str(l).strip() for l in cat.get("labels", [])]
        idx = {key: labels.index(lab) for lab, key in _WANTED.items()
               if lab in labels}
        for row in cat.get("statistics", []) or []:
            eid = str(row.get("eventId", ""))
            if not eid:
                continue
            vals = row.get("stats", [])
            slot = rows.setdefault(eid, {})
            for key, i in idx.items():
                try:
                    slot[key] = int(str(vals[i]).replace(",", ""))
                except (ValueError, IndexError, TypeError):
                    pass
    return rows


# --- competition / status parsing -------------------------------------------
def parse_competition(comp: dict, athlete_id: str) -> dict:
    """Date, our winner flag, opponent id, division text, round count."""
    out: dict = {"comp_id": str(comp.get("id", ""))}
    try:
        out["date"] = _dt.datetime.fromisoformat(
            (comp.get("date") or "").replace("Z", "+00:00")).date()
    except ValueError:
        out["date"] = None
    me = opp = None
    for c in comp.get("competitors", []) or []:
        if str(c.get("id")) == str(athlete_id):
            me = c
        else:
            opp = c
    out["winner"] = None
    if me is not None and opp is not None:
        if me.get("winner"):
            out["winner"] = True
        elif opp.get("winner"):
            out["winner"] = False          # both False = draw/NC/unplayed
    out["opp_id"] = str(opp.get("id")) if opp else None
    out["division_text"] = ((comp.get("type") or {}).get("text") or "")
    out["rounds"] = int(((comp.get("format") or {}).get("regulation") or {})
                        .get("periods") or 3)
    return out


def _clock_seconds(status: dict) -> float | None:
    dc = status.get("displayClock")
    if isinstance(dc, str) and re.fullmatch(r"\d{1,2}:\d{2}", dc.strip()):
        m, s = dc.strip().split(":")
        return int(m) * 60 + int(s)
    clock = status.get("clock")
    return float(clock) if isinstance(clock, (int, float)) else None


def method_from_status(status: dict | None) -> str | None:
    """Normalize the finish method out of a status payload, wherever the
    text lives — scans name/description fields rather than trusting one
    exact key path."""
    if not status:
        return None
    texts: list[str] = []

    def walk(o, depth=0):
        if depth > 3:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and k in (
                        "name", "displayName", "shortDisplayName",
                        "description", "text", "detail", "shortDetail"):
                    texts.append(v)
                elif isinstance(v, (dict, list)):
                    walk(v, depth + 1)
        elif isinstance(o, list):
            for v in o[:8]:
                walk(v, depth + 1)

    walk(status)
    joined = " ".join(texts).lower()
    if "submission" in joined or re.search(r"\bsub\b", joined):
        return "SUB"
    if ("ko/tko" in joined or "knockout" in joined
            or re.search(r"\btko\b|\bko\b", joined)):
        return "KO/TKO"
    if "decision" in joined or re.search(r"\b[usm]\s?-?\s?dec\b", joined):
        return "DEC"
    return None


def fight_duration_s(status: dict | None, method: str | None,
                     rounds: int) -> float:
    """Fight minutes: decisions go the distance; stoppages end at
    (period − 1)×5:00 + clock. Unknown → assume the distance (it only
    means per-minute rates run slightly conservative)."""
    if method == "DEC" or not status:
        return rounds * ROUND_S
    period = status.get("period")
    clock = _clock_seconds(status)
    if not isinstance(period, int) or period < 1 or clock is None:
        return rounds * ROUND_S
    return min((period - 1) * ROUND_S + min(clock, ROUND_S), rounds * ROUND_S)


# --- division / archetype ---------------------------------------------------
_DIV_ORDER = ("light heavyweight", "strawweight", "flyweight", "bantamweight",
              "featherweight", "lightweight", "welterweight", "middleweight",
              "heavyweight")
_WEIGHTS = ((120, "strawweight"), (127, "flyweight"), (137, "bantamweight"),
            (147, "featherweight"), (157, "lightweight"), (172, "welterweight"),
            (187, "middleweight"), (207, "light heavyweight"),
            (400, "heavyweight"))


def division_from_text(text: str, gender: str = "",
                       weight_lbs: float | None = None) -> str:
    t = (text or "").lower()
    base = next((d for d in _DIV_ORDER if d in t), "")
    if not base and weight_lbs:
        base = next((d for cap, d in _WEIGHTS if weight_lbs <= cap),
                    "heavyweight")
    if not base:
        return ""
    if "women" in t or gender.upper() == "FEMALE":
        return "w_" + base.replace(" ", "_")
    return base.replace(" ", "_")


def archetype_from_stats(slpm: float | None, td_per15: float | None,
                         td_acc: float | None, sub_per15: float | None,
                         tdd: float | None,
                         style_hint: str | None = None) -> tuple[str, str]:
    """Best-effort style read, optionally steered by a known fighting
    style (Octagon API's bio field) for the grappling archetypes."""
    hint = (style_hint or "").lower()
    if "wrestl" in hint:
        return "wrestler", f"listed style '{style_hint}'"
    if "jiu-jitsu" in hint or "grappl" in hint:
        return "submission", f"listed style '{style_hint}'"
    td, acc = td_per15 or 0.0, td_acc or 0.0
    sub = sub_per15 or 0.0
    tdd = tdd if tdd is not None else 0.6
    slpm = slpm or 0.0
    if sub >= 1.0 and sub >= td * 0.4:
        return "submission", f"{sub:.1f} sub attempts/15"
    if td >= 2.5 and acc >= 0.30:
        return "wrestler", f"{td:.1f} TD/15 at {acc:.0%}"
    if tdd <= 0.45 and td < 1.0:
        return "striker_poor_tdd", f"TDD {tdd:.0%}, little wrestling"
    if tdd >= 0.72 and slpm >= 3.0:
        return "striker_elite_tdd", f"TDD {tdd:.0%}, strikes at range"
    if slpm >= 4.5:
        return "pressure", f"{slpm:.1f} strikes landed/min"
    return "counter", f"{slpm:.1f} SLpM at moderate pace"


def octagon_styles() -> dict[str, str]:
    """{normalized fighter name: fighting style} for ranked fighters —
    a free single-request enrichment; empty dict when unreachable."""
    try:
        data = _get_json("https://api.octagon-api.com/fighters",
                         "octagon_fighters.json")
    except DataUnavailable:
        return {}
    out = {}
    for rec in data.values():
        if isinstance(rec, dict) and rec.get("name"):
            out[_norm(rec["name"])] = rec.get("fightingStyle") or ""
    return out


# --- assembly ---------------------------------------------------------------
LAYOFF_MONTHS = 18


def build_dossier(name: str, *, bio: dict, record: tuple[int, int, int],
                  own_rows: dict[str, dict], fights: list[dict],
                  total_ufc_fights: int, style_hint: str | None = None,
                  today: _dt.date | None = None) -> dict:
    """Pure assembly: probed pieces in, spec §3 dossier out.

    ``fights`` is newest-first, one dict per analyzed fight:
    {event_id, date, winner, method, duration_s, rounds, division_text,
    opp_row}. Every estimated field gets a review note; red flags block
    the approval gate until a human confirms or deletes them."""
    today = today or _dt.date.today()
    review: list[str] = []

    # Rates only over fights ESPN has stat rows for — regional-circuit
    # bouts appear in the eventlog with no stats, and counting their
    # minutes against zero recorded strikes once made strikers read as
    # 0.0 SLpM. Coverage is disclosed; no coverage → rates unmeasured.
    covered = [f for f in fights if own_rows.get(f["event_id"])]
    minutes = sum(f["duration_s"] for f in covered) / 60.0
    ssl_w = sum(own_rows[f["event_id"]].get("ssl", 0) for f in covered)
    tdl_w = sum(own_rows[f["event_id"]].get("tdl", 0) for f in covered)
    sm_w = sum(own_rows[f["event_id"]].get("sm", 0) for f in covered)
    slpm = round(ssl_w / minutes, 2) if minutes else None
    td_per15 = round(tdl_w / minutes * 15, 2) if minutes else None
    sub_per15 = round(sm_w / minutes * 15, 2) if minutes else None
    if not covered:
        review.append("no per-fight stats in ESPN's data (regional-circuit "
                      "career) — striking/grappling rates unmeasured, the "
                      "model falls back to neutral defaults")
    elif len(covered) < len(fights):
        review.append(f"per-fight stats exist for {len(covered)} of the last "
                      f"{len(fights)} fights — rates measured on those only")

    # Opponent rows in the SAME fights → absorbed strikes + both defenses.
    opp_ssl = opp_ssa = opp_tdl = opp_tda = 0
    opp_min = 0.0
    for f in fights:
        r = f.get("opp_row")
        if not r:
            continue
        opp_ssl += r.get("ssl", 0)
        opp_ssa += r.get("ssa", 0)
        opp_tdl += r.get("tdl", 0)
        opp_tda += r.get("tda", 0)
        opp_min += f["duration_s"] / 60.0
    sapm = round(opp_ssl / opp_min, 2) if opp_min else None
    str_def = round(1.0 - opp_ssl / opp_ssa, 3) if opp_ssa >= 50 else None
    if opp_tda >= 3:
        tdd = round(1.0 - opp_tdl / opp_tda, 3)
    else:
        tdd = None
        review.append("takedown defense unmeasured (opponents attempted "
                      f"only {opp_tda} takedowns in the window) — defaulted")
    if sapm is None or str_def is None:
        review.append("absorbed-strike data thin — sapm/str_def defaulted")

    # Career knockdown rate from the fighter's own full stat history.
    kd_all = sum(r.get("kd", 0) for r in own_rows.values())
    ssl_all = sum(r.get("ssl", 0) for r in own_rows.values())
    if ssl_all >= 100:
        kd_per100 = round(100.0 * kd_all / ssl_all, 2)
    else:
        kd_per100 = 1.0
        review.append("kd_per100 defaulted (too little strike data)")

    # Career TD accuracy from own rows (cheap and window-free).
    tdl_all = sum(r.get("tdl", 0) for r in own_rows.values())
    tda_all = sum(r.get("tda", 0) for r in own_rows.values())
    td_acc = round(tdl_all / tda_all, 3) if tda_all >= 5 else 0.35

    losses = [f for f in fights if f["winner"] is False]
    ko_losses = sum(1 for f in losses if f["method"] == "KO/TKO")
    ko_last3 = sum(1 for f in fights[:3]
                   if f["winner"] is False and f["method"] == "KO/TKO")
    times_finished = sum(1 for f in losses if f["method"] in ("KO/TKO", "SUB"))
    unknown_methods = sum(1 for f in losses if f["method"] is None)
    if unknown_methods:
        review.append(f"{unknown_methods} loss(es) had no parseable method — "
                      "counted as decisions; verify if durability matters here")
    if len(fights) < total_ufc_fights:
        review.append(f"finish counts cover the last {len(fights)} fights "
                      f"(of {total_ufc_fights}) — recent durability is the "
                      "signal, but check older KO losses if in doubt")

    div = next((division_from_text(f["division_text"], bio.get("gender", ""),
                                   bio.get("weight_lbs"))
                for f in fights if f.get("division_text")), "")
    if not div:
        div = division_from_text("", bio.get("gender", ""), bio.get("weight_lbs"))

    arch, why = archetype_from_stats(slpm, td_per15, td_acc, sub_per15, tdd,
                                     style_hint)
    review.append(f"archetype '{arch}' inferred ({why}) — override if you "
                  "know the style better")
    review.append("r3_decay and ctrl_per15 aren't in ESPN's data — left "
                  "neutral; adjust for known cardio/top-control cases")

    age = bio.get("age")
    red_flags: list[str] = []
    if ko_last3 >= 2:
        red_flags.append(f"{ko_last3} KO losses in last three fights — "
                         "chin damage clusters")
    last = next((f["date"] for f in fights if f["date"]), None)
    if last and (today - last).days > LAYOFF_MONTHS * 30:
        red_flags.append(f"no fight since {last.isoformat()} — "
                         f"{(today - last).days // 30}-month layoff")
    if age is not None and age >= 37:
        red_flags.append(f"age {age} — deep in the decline curve")
    if red_flags:
        review.append("auto red flags BLOCK bets until you confirm or "
                      "delete them — that's the review")

    w, l, d = record
    out = {
        "name": name,
        "age": age,
        "division": div,
        "archetype": arch,
        # Experience the clamp can trust = fights with recorded stats
        # (≈ UFC-level bouts). A 20-fight regional record with zero
        # covered fights is still a debutant to the model — correctly.
        "ufc_fights": len(own_rows),
        "career_fights": total_ufc_fights,
        "fights": len(fights),           # denominator for windowed counts
        "record": f"{w}-{l}-{d}",
        "slpm": slpm,
        "sapm": sapm,
        "str_def": str_def,
        "kd_per100": kd_per100,
        "td_per15": td_per15,
        "td_acc": td_acc,
        "tdd": tdd,
        "ctrl_per15": 2.0,
        "sub_att_per15": sub_per15,
        "ko_losses": ko_losses,
        "ko_losses_last3": ko_last3,
        "times_finished": times_finished,
        "r3_decay": 0.15,
        "short_notice": False,
        "red_flags": red_flags,
        "source": "espn-auto",
        "fetched": today.isoformat(),
        "review": review,
    }
    # Unmeasured fields are OMITTED, never stored as null — the model's
    # .get() defaults handle absent keys; a null would crash arithmetic.
    return {k: v for k, v in out.items() if v is not None}


def fetch_dossier(name: str, today: _dt.date | None = None,
                  window: int = WINDOW, log=None,
                  style_hint: str | None = None) -> dict | None:
    """name → drafted dossier via ESPN, or None when the fighter isn't
    findable. ~50 small cached requests per new fighter."""
    log = log or (lambda *_: None)
    today = today or _dt.date.today()
    aid = find_athlete_id(name)
    if not aid:
        return None

    bio_raw = _get_json(f"{CORE}/athletes/{aid}", f"espn_mma_ath_{aid}.json")
    dob = None
    try:
        dob = _dt.datetime.fromisoformat(
            (bio_raw.get("dateOfBirth") or "").replace("Z", "+00:00")).date()
    except ValueError:
        pass
    age = bio_raw.get("age")
    if age is None and dob:
        age = (today.year - dob.year
               - ((today.month, today.day) < (dob.month, dob.day)))
    bio = {"age": age, "weight_lbs": bio_raw.get("weight"),
           "gender": bio_raw.get("gender", "")}

    record = (0, 0, 0)
    try:
        rec_raw = _get_json(f"{CORE}/athletes/{aid}/records",
                            f"espn_mma_rec_{aid}.json")
        summary = (rec_raw.get("items") or [{}])[0].get("summary", "")
        m = re.match(r"(\d+)-(\d+)-(\d+)", summary)
        if m:
            record = tuple(int(x) for x in m.groups())
    except DataUnavailable:
        pass

    own_rows = parse_stat_rows(
        _get_json(V3_STATS.format(id=aid), f"espn_mma_stats_{aid}.json"))

    # Eventlog (paginated) → competition refs, newest first.
    comp_refs: list[str] = []
    page = 1
    while True:
        ev = _get_json(f"{CORE}/athletes/{aid}/eventlog?page={page}",
                       f"espn_mma_evlog_{aid}_p{page}.json")
        items = (ev.get("events") or {}).get("items") or []
        for it in items:
            ref = (it.get("competition") or {}).get("$ref", "")
            if ref:
                comp_refs.append(ref.replace("http://", "https://"))
        if page >= int((ev.get("events") or {}).get("pageCount") or 1):
            break
        page += 1
    total_fights = len(comp_refs)

    fights: list[dict] = []
    for i, ref in enumerate(comp_refs):
        if len(fights) >= window:
            break
        cid = ref.rstrip("/").split("/")[-1].split("?")[0]
        try:
            comp = parse_competition(
                _get_json(ref, f"espn_mma_comp_{cid}.json"), aid)
        except DataUnavailable:
            continue
        if comp["winner"] is None and comp["date"] and comp["date"] >= today:
            total_fights -= 1            # upcoming bout, not history
            continue
        status = None
        try:
            status = _get_json(f"{ref.split('?')[0]}/status",
                               f"espn_mma_stat_{cid}.json")
        except DataUnavailable:
            pass
        method = method_from_status(status)
        eid = None
        m = re.search(r"/events/(\d+)/", ref)
        if m:
            eid = m.group(1)
        opp_row = None
        if comp.get("opp_id"):
            try:
                opp_rows = parse_stat_rows(_get_json(
                    V3_STATS.format(id=comp["opp_id"]),
                    f"espn_mma_stats_{comp['opp_id']}.json"))
                opp_row = opp_rows.get(eid or "")
            except DataUnavailable:
                pass
        fights.append({
            "event_id": eid or "", "date": comp["date"],
            "winner": comp["winner"], "method": method,
            "duration_s": fight_duration_s(status, method, comp["rounds"]),
            "rounds": comp["rounds"],
            "division_text": comp["division_text"], "opp_row": opp_row,
        })
        log(f"    {name}: fight {len(fights)}/{min(window, len(comp_refs))} …")

    if not fights:
        return None
    fights.sort(key=lambda f: f["date"] or _dt.date.min, reverse=True)
    return build_dossier(name, bio=bio, record=record, own_rows=own_rows,
                         fights=fights, total_ufc_fights=total_fights,
                         style_hint=style_hint, today=today)
