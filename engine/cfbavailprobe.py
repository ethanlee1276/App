"""Where the conferences publish their football availability reports, found from the box (decision 20).

    python3 -m engine.cfbavailprobe            # look now, print what was found, write the file

Ethan, 23 November 2026, on decision 20: "decision 20 is a yes if it helps and get us more up to date info for
the users". ESPN's college injury board listed one college football injury that Monday against the NFL's 797:
schools owe ESPN nothing. The conferences publish availability reports for their games (the Big Ten four a week
for 2026, and the SEC, the ACC and the Big 12 their own; the College Football Playoff its teams'), each on its
own site in its own format, and the sandbox this site is built in cannot reach any of them. The box can.
The NBA's own injury report (a PDF the league posts through every game day) is mapped the same way.

So the box looks, every EVERY_S, and writes what it found to web/data/cfb_availability_probe.json: for each
conference, the pages it read (address, answer, kind, size, title, headings), the links on them that speak of
availability or injuries, each table's heading row and first rows as text, the PDF links, any data address a
page's own scripts name, and a few lines of text around the word "availability". It follows such links from the
conference's front and football pages two steps deep, at most FOLLOW pages a step. Nothing on the site reads
the file and no pick moves: it is the map the reader that follows is written from, and it is switched off
(QB_CFB_AVAIL_PROBE=off) once that reader is built.

Standard library only. Each read is a plain GET with urllib's own User-Agent (as engine/sources/fetch's
DEFAULT_AGENT reads ESPN): no account, no form, nothing posted.
"""
from __future__ import annotations

import datetime as _dt
import gzip
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "data" / "cfb_availability_probe.json"
ENV = "QB_CFB_AVAIL_PROBE"
#: How often the box looks again (the reports post Wednesday to Saturday, several a week).
EVERY_S = 3 * 3600
#: The thread's sleep between checks of whether a look is due.
IDLE_S = 600
TIMEOUT_S = 20
#: Pages followed from each step, per conference.
FOLLOW = 8
DEPTH = 2
#: The most of a page read (a conference front page can be large; the reports are small).
MAX_BYTES = 3_000_000
#: Where each conference's look starts. The first look (23 November) read the front and football pages: those
#: are built in the reader's browser by scripts (the Big Ten's football page held 22 words of text), and three
#: front pages answered 404 to a plain request, so no link to a report showed. Each conference's own page on its
#: reporting rules (ACC, Big 12) and its reports page as the press names it (SEC, Big Ten: "FBReports") are where
#: the reports are said to be posted, so the look starts there, with the football pages behind them.
SOURCES = {
    "big_ten": ("https://bigten.org/fbreports", "https://bigten.org/fb/article/60284/",
                "https://bigten.org/sports/football"),
    "sec": ("https://www.secsports.com/FBreports", "https://www.secsports.com/fbreports",
            "https://www.secsports.com/sport/football"),
    "acc": ("https://theacc.com/sports/2025/8/28/availability-reporting.aspx", "https://theacc.com/fbreports",
            "https://theacc.com/sports/football"),
    "big_12": ("https://big12sports.com/sports/2025/8/21/availability-reporting.aspx",
               "https://big12sports.com/fbreports", "https://big12sports.com/sports/football"),
    "cfp": ("https://collegefootballplayoff.com/",),
    # THE NBA'S OWN INJURY REPORT: the league posts it as a PDF through every game day, ahead of ESPN's board
    # (which the NBA build reads, with its blurbs' words, step ABU). Mapped the same way, for the same reader.
    "nba_official": ("https://official.nba.com/nba-injury-report-2026-27-season/",),
}
#: THE NBA'S REPORT ITSELF. Its index page turned the first look away (403), and each report is a PDF at an
#: address made of its own time, posted every quarter hour on game days ("Injury-Report_2026-04-06_08_15AM.pdf",
#: Eastern time): the look asks for the newest quarter hour, then each before it, back NBA_BACK_SLOTS slots.
NBA_PDF = "https://ak-static.cms.nba.com/referee/injury/Injury-Report_{day}_{hhmm}.pdf"
NBA_BACK_SLOTS = 16
#: A link worth following: its address or its words speak of availability or injuries.
LINK_WORDS = re.compile(r"availab|injur|fbreport", re.I)
#: The strongest of them, followed first.
STRONG_WORDS = re.compile(r"availability[-_ ]?report|fbreport|availability", re.I)
#: A data address a page's scripts name (a JSON feed the page fills itself from).
API_RE = re.compile(r"""["'](https?://[^"'\s]{6,300}?(?:api|json|feed)[^"'\s]{0,200})["']""", re.I)
#: Any quoted text in a page (its scripts included) that names the reports: where a page built by scripts
#: fetches them from.
HINT_RE = re.compile(r"""["']([^"'<>\s]{0,240}(?:availab|fbreport)[^"'<>\s]{0,240})["']""", re.I)
#: The output's own ceiling, so a strange page can never fill the box's disk or the site.
MAX_OUT = 600_000


def on() -> bool:
    return str(os.environ.get(ENV, "on")).strip().lower() not in ("off", "0", "false", "no")


def _iso(t: float) -> str:
    return _dt.datetime.fromtimestamp(float(t), _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Page(HTMLParser):
    """The parts of a page the reader needs: its title, headings, links, tables and text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.headings, self.links, self.tables, self.text = "", [], [], [], []
        self._in_title = False
        self._heading = None
        self._link = None
        self._table_stack: list = []
        self._cell = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("h1", "h2", "h3", "h4"):
            self._heading = []
        elif tag == "a" and a.get("href"):
            self._link = {"href": a.get("href"), "text": []}
        elif tag == "table":
            self._table_stack.append({"rows": [], "cls": a.get("class") or "", "id": a.get("id") or ""})
        elif tag == "tr" and self._table_stack:
            self._table_stack[-1]["rows"].append([])
        elif tag in ("td", "th") and self._table_stack:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4") and self._heading is not None:
            t = " ".join(" ".join(self._heading).split())
            if t:
                self.headings.append(f"{tag}: {t}")
            self._heading = None
        elif tag == "a" and self._link is not None:
            self._link["text"] = " ".join(" ".join(self._link["text"]).split())
            self.links.append(self._link)
            self._link = None
        elif tag in ("td", "th") and self._cell is not None and self._table_stack:
            rows = self._table_stack[-1]["rows"]
            if not rows:
                rows.append([])
            rows[-1].append(" ".join(" ".join(self._cell).split()))
            self._cell = None
        elif tag == "table" and self._table_stack:
            self.tables.append(self._table_stack.pop())

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._heading is not None:
            self._heading.append(data)
        if self._link is not None:
            self._link["text"].append(data)
        if self._cell is not None:
            self._cell.append(data)
        s = data.strip()
        if s:
            self.text.append(s)


def _get(url: str):
    """(status, content type, body bytes): one plain GET, no User-Agent of ours, packed bodies unpacked."""
    try:
        req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            ctype = resp.headers.get("Content-Type") or ""
            final = resp.geturl()
            raw = resp.read(MAX_BYTES)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        # A page that answered from somewhere else says where (a short address that redirects to the reports).
        return "ok", (ctype + (f"; landed={final}" if final and final != url else "")), raw
    except urllib.error.HTTPError as exc:
        return f"HTTP {exc.code}", "", b""
    except Exception as exc:                                   # noqa: BLE001
        return type(exc).__name__, "", b""


def _snippets(text: list, limit: int = 4, width: int = 600) -> list:
    """A few runs of the page's words that begin at "availability" (or "injur" when none does)."""
    whole = " ".join(text)
    out = []
    for word in ("availab", "injur"):
        for m in re.finditer(word, whole, re.I):
            start = max(0, m.start() - 80)
            piece = whole[start:start + width]
            if not any(piece[:120] in o for o in out):
                out.append(piece)
            if len(out) >= limit:
                return out
        if out:
            break
    return out


def pdf_text(raw: bytes, limit: int = 4000) -> str:
    """The text a simple PDF draws (its packed streams' Tj and TJ strings), at most ``limit`` characters: enough
    to see a report's layout. A PDF whose fonts draw by glyph number gives little or nothing, which says so too."""
    out, size = [], 0
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
        data = m.group(1)
        try:
            data = zlib.decompress(data)
        except Exception:                                      # noqa: BLE001 — an image, or an unpacked stream
            pass
        for t in re.finditer(rb"\(((?:\\.|[^\\)])*)\)\s*Tj|\[(.*?)\]\s*TJ", data, re.S):
            piece = t.group(1) if t.group(1) is not None else b"".join(
                re.findall(rb"\(((?:\\.|[^\\)])*)\)", t.group(2) or b"", re.S))
            if piece:
                out.append(piece)
                size += len(piece)
        if size > limit:
            break
    return " ".join(x.decode("latin-1", errors="replace") for x in out)[:limit]


def _next_data(body: str, limit: int = 3) -> list:
    """Runs of a Next.js page's own data (its __NEXT_DATA__ script) around "availab": a page that fills itself."""
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', body, re.S)
    if not m:
        return []
    data = m.group(1)
    out = [data[max(0, x.start() - 300):x.start() + 900] for x in re.finditer(r"availab", data, re.I)][:limit]
    return out or [data[:600]]


def look_page(url: str, get=_get) -> tuple[dict, list]:
    """(what one page says, the links on it worth following)."""
    status, ctype, raw = get(url)
    rec = {"url": url, "status": status, "type": ctype.split(";")[0].strip(), "bytes": len(raw)}
    landed = re.search(r"landed=(\S+)", ctype)
    if landed:
        rec["landed"] = landed.group(1)
    if status != "ok":
        return rec, []
    if "pdf" in ctype.lower() or raw[:5] == b"%PDF-":
        rec["pdf"] = True
        rec["pdf_text"] = pdf_text(raw)
        return rec, []
    body = raw.decode("utf-8", errors="replace")
    if "json" in ctype.lower() or body.lstrip()[:1] in ("{", "["):
        rec["json_head"] = body[:3000]
        return rec, []
    p = _Page()
    try:
        p.feed(body)
    except Exception:                                          # noqa: BLE001 — a malformed page is still read so far
        pass
    rec["title"] = " ".join(p.title.split())[:200]
    rec["headings"] = p.headings[:20]
    worth, pdfs = [], []
    for ln in p.links:
        href = urllib.parse.urljoin(url, ln["href"].strip())
        if not href.startswith("http"):
            continue
        text = ln["text"] if isinstance(ln["text"], str) else ""
        if href.lower().split("?")[0].endswith(".pdf"):
            pdfs.append({"text": text[:120], "href": href})
        if LINK_WORDS.search(href) or LINK_WORDS.search(text):
            worth.append({"text": text[:120], "href": href})
    seen = set()
    rec["links"] = [x for x in worth if not (x["href"] in seen or seen.add(x["href"]))][:40]
    rec["pdfs"] = pdfs[:30]
    rec["tables"] = [{"class": t["cls"][:80], "id": t["id"][:60], "rows": len(t["rows"]),
                      "first": [r[:12] for r in t["rows"][:10]]} for t in p.tables if t["rows"]][:8]
    rec["apis"] = sorted({m.group(1)[:300] for m in API_RE.finditer(body)
                          if LINK_WORDS.search(m.group(1)) or "football" in m.group(1).lower()})[:20]
    rec["snippets"] = _snippets(p.text)
    rec["words"] = len(p.text)
    hints = list(dict.fromkeys(m.group(1) for m in HINT_RE.finditer(body)))
    if hints:
        rec["hints"] = hints[:25]
    nd = _next_data(body)
    if nd:
        rec["next_data"] = nd
    follow = sorted(rec["links"], key=lambda x: (not STRONG_WORDS.search(x["href"] + " " + x["text"]),))
    return rec, [x["href"] for x in follow]


def nba_pdf_urls(now: float, back: int = NBA_BACK_SLOTS) -> list:
    """The NBA report's addresses for the newest ``back`` quarter hours, newest first (Eastern time)."""
    from zoneinfo import ZoneInfo
    t = _dt.datetime.fromtimestamp(float(now), ZoneInfo("America/New_York"))
    t = t.replace(minute=t.minute - t.minute % 15, second=0, microsecond=0)
    out = []
    for i in range(back):
        x = t - _dt.timedelta(minutes=15 * i)
        out.append(NBA_PDF.format(day=x.strftime("%Y-%m-%d"), hhmm=x.strftime("%I_%M%p")))
    return out


def look_nba_pdf(now: float, get=_get) -> dict:
    """The newest NBA report found (its address, size and the text a simple PDF draws), and every address asked."""
    asked = []
    for url in nba_pdf_urls(now):
        rec, _links = look_page(url, get)
        asked.append(f"{rec['status']} {url.rsplit('/', 1)[-1]}")
        if rec["status"] == "ok":
            rec["asked"] = asked
            return rec
    return {"url": "", "status": "none found", "asked": asked}


def _home(url: str) -> str:
    """A site's own name, without its "www.": bigten.org."""
    host = urllib.parse.urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def mine(href: str, homes: set) -> bool:
    """A link the look may follow: on the conference's own site (or one under it), or a PDF wherever it is kept
    (a report is often a file on a storage site). Never another site's pages."""
    h = _home(href)
    return any(h == x or h.endswith("." + x) for x in homes) or href.lower().split("?")[0].endswith(".pdf")


def look(sources=None, get=_get, follow: int = FOLLOW, depth: int = DEPTH) -> dict:
    """{conference: {"pages": [...]}} — each conference's start pages, then the links worth following on its own
    site (`mine`), two steps deep, at most ``follow`` pages a step, never the same page twice."""
    out = {}
    for name, starts in (sources or SOURCES).items():
        pages, seen = [], set()
        homes = {_home(u) for u in starts}
        step = list(starts)
        for level in range(depth + 1):
            nxt = []
            for url in step:
                if url in seen:
                    continue
                seen.add(url)
                rec, links = look_page(url, get)
                rec["step"] = level
                pages.append(rec)
                nxt += [u for u in links if u not in seen and mine(u, homes)]
            step = list(dict.fromkeys(nxt))[:follow]
            if not step:
                break
        out[name] = {"pages": pages}
    return out


def write(found: dict, now: float, out=None) -> Path:
    p = Path(out or OUT)
    doc = {"generated_at": _iso(now), "every_s": EVERY_S, "sources": found}
    text = json.dumps(doc, separators=(",", ":"))
    if len(text) > MAX_OUT:                                    # the snippets and tables go first, then pages
        for v in found.values():
            for pg in v.get("pages") or []:
                pg.pop("snippets", None)
                for t in pg.get("tables") or []:
                    t["first"] = t["first"][:4]
        text = json.dumps(doc, separators=(",", ":"))[:MAX_OUT]
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, p)
    return p


_LAST = {"at": 0.0}


def watch_once(now=None, get=_get, out=None) -> float:
    """Look when EVERY_S has passed since the last look; the seconds until the next check."""
    now = time.time() if now is None else float(now)
    if now - _LAST["at"] < EVERY_S:
        return min(IDLE_S, EVERY_S - (now - _LAST["at"]))
    _LAST["at"] = now
    found = look(get=get)
    found["nba_report_pdf"] = {"pages": [look_nba_pdf(now, get)]}
    write(found, now, out)
    return IDLE_S


def main(argv=None) -> int:
    found = look()
    found["nba_report_pdf"] = {"pages": [look_nba_pdf(time.time())]}
    p = write(found, time.time())
    for name, v in found.items():
        print(f"\n=== {name}")
        for pg in v["pages"]:
            print(f"  [{pg.get('step')}] {pg['status']:12} {pg.get('type', ''):24} {pg['bytes']:8}  {pg['url']}")
            for ln in (pg.get("links") or [])[:6]:
                print(f"        link: {ln['text'][:60]!r} -> {ln['href']}")
            for t in (pg.get("tables") or [])[:2]:
                print(f"        table ({t['rows']} rows): {t['first'][:2]}")
    print(f"\nwritten: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
