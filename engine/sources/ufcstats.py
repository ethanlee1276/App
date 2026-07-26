"""UFCStats.com → fighter dossiers, automatically drafted.

The Scalpy MMA doctrine is "no dossier, no bet" — which is only useful if
dossiers actually get built. UFCStats.com publishes every number the
dossier needs (career striking/grappling rates, record, fight-by-fight
history with methods) as plain public HTML, so this adapter turns the
hour of pre-card homework into a two-minute review:

  * :func:`search_fighter` — find a fighter's page from the name the odds
    feed uses;
  * :func:`parse_fighter` — pull the raw stats off the page (regex on
    stable label text like ``SLpM:`` — resilient to cosmetic redesigns);
  * :func:`to_dossier` — map raw stats into the spec's §3 dossier fields,
    with explicit ``review`` notes on every number that is estimated
    rather than measured (archetype, cardio decay, control time).

Auto-drafted dossiers still carry auto red flags (chin damage clusters,
long layoffs, age) — and red flags BLOCK the approval gate by design.
The human's review job is exactly that: confirm or delete them.

Stdlib only, like everything else. Requests are cached and politely
rate-limited; a card touches ~26 pages once a week.
"""

from __future__ import annotations

import datetime as _dt
import re
import time
import urllib.parse
import urllib.request
from html import unescape

from .fetch import CACHE_DIR, DataUnavailable

BASE = "http://www.ufcstats.com"
# UFCStats sits behind a CDN that rejects non-browser agents.
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
FETCH_PAUSE_S = 1.0        # politeness between live page fetches
_TTL = 3 * 24 * 3600       # career stats don't move between cards

_last_fetch = 0.0


def _get(url: str, cache_name: str, ttl: int = _TTL) -> str:
    """Browser-agent fetch with the standard cache/stale-fallback contract."""
    global _last_fetch
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / cache_name
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        wait = FETCH_PAUSE_S - (time.time() - _last_fetch)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            text = resp.read().decode("utf-8", errors="replace")
        _last_fetch = time.time()
        path.write_text(text, encoding="utf-8")
        return text
    except Exception as exc:  # noqa: BLE001 — offline → stale cache or raise
        if path.exists():
            return path.read_text(encoding="utf-8", errors="replace")
        raise DataUnavailable(f"Could not fetch {url}: {exc}") from exc


# --- parsing ----------------------------------------------------------------
_TAG = re.compile(r"<[^>]+>")


def _tokens(html: str) -> list[str]:
    """Tag-stripped, whitespace-collapsed text tokens of an HTML fragment."""
    text = _TAG.sub("\n", unescape(html))
    return [t.strip() for t in text.split("\n") if t.strip()]


def parse_search(html: str) -> list[dict]:
    """Fighter-details links from a search results page → [{name, url}].

    The results table shows first and last name as separate links to the
    same fighter page; pairing consecutive links per URL rebuilds the
    full name without depending on table markup.
    """
    out: list[dict] = []
    by_url: dict[str, list[str]] = {}
    for m in re.finditer(
            r'href="(https?://[^"]*fighter-details/[a-f0-9]+)"[^>]*>([^<]+)<',
            html):
        url, text = m.group(1), unescape(m.group(2)).strip()
        if not text:
            continue
        by_url.setdefault(url, [])
        if len(by_url[url]) < 2:            # first + last; ignore nickname
            by_url[url].append(text)
    for url, parts in by_url.items():
        out.append({"name": " ".join(parts), "url": url})
    return out


_LABELS = {
    "slpm": r"SLpM\s*:", "str_acc": r"Str\.\s*Acc\.\s*:",
    "sapm": r"SApM\s*:", "str_def": r"Str\.\s*Def\s*:?",
    "td_avg": r"TD\s*Avg\.\s*:", "td_acc": r"TD\s*Acc\.\s*:",
    "td_def": r"TD\s*Def\.\s*:", "sub_avg": r"Sub\.\s*Avg\.\s*:",
    "weight": r"Weight\s*:", "dob": r"DOB\s*:", "reach": r"Reach\s*:",
}
_RESULTS = {"win", "loss", "draw", "nc"}
_METHODS = ("KO/TKO", "U-DEC", "S-DEC", "M-DEC", "SUB", "DQ", "CNC",
            "Overturned", "Decision")
_DATE_RE = re.compile(r"^[A-Z][a-z]{2}\.?\s+\d{1,2},\s+\d{4}$")


def _labeled_value(label_re: str, text: str) -> str | None:
    m = re.search(label_re + r"\s*([^\n<]*)", text)
    if not m:
        return None
    v = m.group(1).strip()
    return v if v and v != "--" else None


def _num(v: str | None) -> float | None:
    if v is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", v)
    if not m:
        return None
    x = float(m.group(0))
    return x / 100.0 if "%" in v else x


def _parse_date(tok: str) -> _dt.date | None:
    try:
        return _dt.datetime.strptime(tok.replace(".", ""), "%b %d, %Y").date()
    except ValueError:
        return None


def _parse_history_row(row_html: str) -> dict | None:
    """One completed fight from a history-table row, or None.

    Column order is stable (result | fighters | KD | STR | TD | SUB |
    event+date | method | round | time) so we read the token stream, not
    the markup: the first 8 bare integers after the result are the four
    stat pairs, self first.
    """
    toks = _tokens(row_html)
    result = next((t.lower() for t in toks if t.lower() in _RESULTS), None)
    if result is None:
        return None                          # upcoming bout / header row
    ints = [int(t) for t in toks if re.fullmatch(r"\d{1,3}", t)][:8]
    date = next((d for t in toks if (d := _parse_date(t))), None)
    method = next((m for m in _METHODS
                   for t in toks if t.startswith(m)), None)
    return {"result": result, "date": date, "method": method,
            "kd": ints[0] if len(ints) >= 1 else 0,
            "sig_str": ints[2] if len(ints) >= 3 else 0}


def parse_fighter(html: str) -> dict:
    """Raw career stats + fight history from a fighter-details page."""
    # Label text survives redesigns better than CSS classes do.
    text = _TAG.sub("\n", unescape(html))
    text = "\n".join(t.strip() for t in text.split("\n") if t.strip())
    out: dict = {}
    m = re.search(r"Record\s*:\s*(\d+)-(\d+)-(\d+)", text)
    if m:
        out["wins"], out["losses"], out["draws"] = map(int, m.groups())
    for key, label in _LABELS.items():
        out[key] = _labeled_value(label, text)
    for key in ("slpm", "sapm", "td_avg", "sub_avg",
                "str_acc", "str_def", "td_acc", "td_def"):
        out[key] = _num(out.get(key))
    out["weight_lbs"] = _num(out.pop("weight", None))
    dob = out.pop("dob", None)
    out["dob"] = _parse_date(dob) if dob else None

    history = []
    for row in re.split(r"<tr\b", html)[1:]:
        parsed = _parse_history_row(row)
        if parsed:
            history.append(parsed)
    # Newest first on the page; keep that order.
    out["history"] = history
    return out


# --- dossier mapping --------------------------------------------------------
# Men's weights; women's 125/135 share names with review-note caveat.
_DIVISIONS = ((115, "w_strawweight"), (125, "flyweight"),
              (135, "bantamweight"), (145, "featherweight"),
              (155, "lightweight"), (170, "welterweight"),
              (185, "middleweight"), (205, "light_heavyweight"),
              (400, "heavyweight"))
LAYOFF_MONTHS = 18


def _division(weight: float | None) -> str:
    if weight is None:
        return ""
    for cap, name in _DIVISIONS:
        if weight <= cap:
            return name
    return "heavyweight"


def _archetype(d: dict) -> tuple[str, str]:
    """Best-effort style read from the stat shape, with the reasoning."""
    td, acc = d.get("td_avg") or 0.0, d.get("td_acc") or 0.0
    sub = d.get("sub_avg") or 0.0
    tdd = d.get("td_def") if d.get("td_def") is not None else 0.6
    slpm = d.get("slpm") or 0.0
    if sub >= 1.0 and sub >= td * 0.4:
        return "submission", f"{sub:.1f} sub attempts/15 — hunts finishes on the mat"
    if td >= 2.5 and acc >= 0.30:
        return "wrestler", f"{td:.1f} TD/15 at {acc:.0%} — wrestling is the base"
    if tdd <= 0.45 and td < 1.0:
        return "striker_poor_tdd", f"TDD {tdd:.0%} with little offensive wrestling"
    if tdd >= 0.72 and slpm >= 3.0:
        return "striker_elite_tdd", f"TDD {tdd:.0%} — hard to take down, strikes at range"
    if slpm >= 4.5:
        return "pressure", f"{slpm:.1f} strikes landed/min — volume pressure"
    return "counter", f"{slpm:.1f} SLpM at moderate pace — reads as a counter striker"


def to_dossier(name: str, raw: dict, today: _dt.date | None = None) -> dict:
    """Spec §3 dossier from raw UFCStats numbers, review notes included.

    Every field that is measured is filled from the page; every field
    that is a guess (archetype, r3_decay, ctrl_per15, women's division
    names) gets a ``review`` note saying so. Auto red flags block the
    approval gate until a human confirms or deletes them — that is the
    two-minute review this tool leaves behind."""
    today = today or _dt.date.today()
    review: list[str] = []
    hist = raw.get("history", [])
    fights_total = sum(raw.get(k, 0) or 0 for k in ("wins", "losses", "draws"))

    ko_losses = sum(1 for f in hist
                    if f["result"] == "loss" and f["method"] == "KO/TKO")
    ko_last3 = sum(1 for f in hist[:3]
                   if f["result"] == "loss" and f["method"] == "KO/TKO")
    times_finished = sum(1 for f in hist if f["result"] == "loss"
                         and f["method"] in ("KO/TKO", "SUB"))
    sig_total = sum(f["sig_str"] for f in hist)
    kd_total = sum(f["kd"] for f in hist)
    if sig_total >= 100:
        kd_per100 = round(100.0 * kd_total / sig_total, 2)
    else:
        kd_per100 = 1.0
        review.append("kd_per100 defaulted (too little strike data)")

    arch, arch_why = _archetype(raw)
    review.append(f"archetype '{arch}' guessed from stats ({arch_why}) — "
                  "override if you know the style better")
    review.append("r3_decay and ctrl_per15 aren't on the summary page — "
                  "left neutral; adjust for known cardio/top-control cases")

    division = _division(raw.get("weight_lbs"))
    if division in ("flyweight", "bantamweight"):
        review.append("125/135 lbs is ambiguous between men's and women's "
                      "divisions — prefix w_ if this is a women's bout")

    age = None
    if raw.get("dob"):
        d = raw["dob"]
        age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))

    red_flags: list[str] = []
    if ko_last3 >= 2:
        red_flags.append(f"{ko_last3} KO losses in last three fights — "
                         "chin damage clusters")
    last = next((f["date"] for f in hist if f["date"]), None)
    if last and (today - last).days > LAYOFF_MONTHS * 30:
        red_flags.append(f"no fight since {last.isoformat()} — "
                         f"{(today - last).days // 30}-month layoff")
    if age is not None and age >= 37:
        red_flags.append(f"age {age} — deep in the decline curve")
    if red_flags:
        review.append("auto red flags BLOCK bets until you confirm or "
                      "delete them — that's the review")

    return {
        "name": name,
        "age": age,
        "division": division,
        "archetype": arch,
        "ufc_fights": len(hist),
        "fights": fights_total or len(hist),
        "slpm": raw.get("slpm"),
        "sapm": raw.get("sapm"),
        "str_def": raw.get("str_def"),
        "kd_per100": kd_per100,
        "td_per15": raw.get("td_avg"),
        "td_acc": raw.get("td_acc"),
        "tdd": raw.get("td_def"),
        "ctrl_per15": 2.0,
        "sub_att_per15": raw.get("sub_avg"),
        "ko_losses": ko_losses,
        "ko_losses_last3": ko_last3,
        "times_finished": times_finished,
        "r3_decay": 0.15,
        "short_notice": False,
        "red_flags": red_flags,
        "source": "ufcstats-auto",
        "fetched": today.isoformat(),
        "review": review,
    }


# --- live lookup ------------------------------------------------------------
def _norm(s: str) -> str:
    from .oddsapi import normalize_name
    return normalize_name(s)


def search_fighter(name: str) -> dict | None:
    """Find the UFCStats page for an odds-feed fighter name.

    Searches by last name (their search matches substrings), then picks
    the exact normalized full-name match; falls back to the single result
    if the search returns only one fighter."""
    last = name.strip().split()[-1] if name.strip() else ""
    if not last:
        return None
    q = urllib.parse.quote(last)
    html = _get(f"{BASE}/statistics/fighters/search?query={q}",
                f"ufcstats_search_{_norm(last).replace(' ', '_')}.html")
    results = parse_search(html)
    target = _norm(name)
    exact = [r for r in results if _norm(r["name"]) == target]
    if exact:
        return exact[0]
    if len(results) == 1:
        return results[0]
    # Last resort: all name PARTS present (handles accent/middle-name drift).
    parts = set(target.split())
    loose = [r for r in results if parts <= set(_norm(r["name"]).split())]
    return loose[0] if len(loose) == 1 else None


def fetch_dossier(name: str, today: _dt.date | None = None) -> dict | None:
    """name → drafted dossier, or None when the fighter can't be found."""
    hit = search_fighter(name)
    if not hit:
        return None
    fid = hit["url"].rstrip("/").rsplit("/", 1)[-1]
    html = _get(hit["url"], f"ufcstats_fighter_{fid}.html")
    return to_dossier(name, parse_fighter(html), today)
