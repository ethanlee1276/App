"""The box maps where the conferences publish their availability reports (decision 20, step ADA).

Ethan, 23 November: "decision 20 is a yes if it helps and get us more up to date info for the users". The
conferences post their football availability reports on their own sites, which the sandbox this site is built
in cannot reach. The box can: every few hours it reads each conference's front and football pages, follows the
links that speak of availability or injuries on that conference's own site two steps deep, and writes what it
found (tables, PDF text, data addresses, the words around "availability") to
web/data/cfb_availability_probe.json, the map the college reader is written from. Nothing reads it; no pick
moves. One rule each here.

Run directly: `python3 tests/test_the_box_maps_the_college_availability_reports.py`
"""
import json
import os
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import cfbavailprobe as P                  # noqa: E402

SITE = {
    "https://conf.test/": ("ok", "text/html", b"<title>Conf</title><a href='/fb/availability-report'>Availability "
                           b"Report</a><a href='https://news.other.test/injury-roundup'>Injury roundup</a>"
                           b"<a href='/tickets'>Tickets</a>"),
    "https://conf.test/fb/availability-report": (
        "ok", "text/html; charset=utf-8",
        b"<h2>Week 13 Availability Report</h2><a href='https://cdn.store.test/osu-mich.pdf'>OSU at MICH availability"
        b" (PDF)</a><a href='/fb/availability/osu-mich'>OSU at MICH</a><table class='avail'><tr><th>Player</th>"
        b"<th>Pos</th><th>Status</th></tr><tr><td>John Smith</td><td>WR</td><td>Out</td></tr></table><script>var u="
        b"'https://api.conf.test/football/availability.json'</script><p>Availability reports are released Wednesday."
        b"</p>"),
    "https://conf.test/fb/availability/osu-mich": ("ok", "text/html", b"<table><tr><th>Name</th><th>Status</th></tr>"
                                                   b"<tr><td>Al Back</td><td>Questionable</td></tr></table>"),
}


def _pdf(text: bytes) -> bytes:
    return (b"%PDF-1.4\n1 0 obj << /Filter /FlateDecode >> stream\n" + zlib.compress(text)
            + b"\nendstream endobj\n%%EOF")


def _get(extra=None):
    pages = dict(SITE, **(extra or {}))
    return lambda u: pages.get(u, ("HTTP 404", "", b""))


def test_it_follows_the_availability_links_two_steps_and_keeps_what_a_reader_needs():
    pdf = _pdf(b"BT (Ohio State Availability Report) Tj ET BT [(John )-20(Smith)] TJ ET")
    found = P.look({"conf": ("https://conf.test/",)}, get=_get({"https://cdn.store.test/osu-mich.pdf":
                                                              ("ok", "application/pdf", pdf)}))
    pages = {pg["url"]: pg for pg in found["conf"]["pages"]}
    assert set(pages) == {"https://conf.test/", "https://conf.test/fb/availability-report",
                          "https://cdn.store.test/osu-mich.pdf", "https://conf.test/fb/availability/osu-mich"}, pages
    rep = pages["https://conf.test/fb/availability-report"]
    assert rep["step"] == 1 and rep["tables"][0]["first"] == [["Player", "Pos", "Status"], ["John Smith", "WR", "Out"]]
    assert rep["apis"] == ["https://api.conf.test/football/availability.json"]
    assert rep["pdfs"][0]["href"] == "https://cdn.store.test/osu-mich.pdf"
    assert any("released Wednesday" in x for x in rep["snippets"])
    got = pages["https://cdn.store.test/osu-mich.pdf"]
    assert got["pdf"] and got["pdf_text"] == "Ohio State Availability Report John Smith", got
    assert "https://news.other.test/injury-roundup" not in pages, "never another site's pages"


def test_a_page_that_fails_is_said_and_the_look_goes_on():
    found = P.look({"conf": ("https://conf.test/missing", "https://conf.test/")}, get=_get())
    first = found["conf"]["pages"][0]
    assert first["status"] == "HTTP 404" and first["bytes"] == 0
    assert any(pg["url"] == "https://conf.test/fb/availability-report" for pg in found["conf"]["pages"])


def test_a_page_that_fills_itself_says_where_its_data_is():
    body = (b'<html><script id="__NEXT_DATA__" type="application/json">{"props":{"availability":[{"player":"A",'
            b'"status":"Out"}]}}</script></html>')
    rec, _links = P.look_page("https://conf.test/x", get=lambda u: ("ok", "text/html", body))
    assert rec["next_data"] and '"availability"' in rec["next_data"][0]


def test_a_page_built_by_scripts_says_where_it_fetches_the_reports_and_where_it_landed():
    body = (b"<script>cfg={reports:'/api/v2/fbreports?week=13',x:\"https://cdn.x.test/availability/w13.json\"}"
            b"</script><a href='/fbreports/2026/11/22/osu-mich'>OSU at MICH</a>")
    rec, links = P.look_page("https://conf.test/fbreports",
                             get=lambda u: ("ok", "text/html; landed=https://conf.test/fb/reports", body))
    assert rec["landed"] == "https://conf.test/fb/reports"
    assert rec["hints"] == ["/api/v2/fbreports?week=13", "https://cdn.x.test/availability/w13.json",
                            "/fbreports/2026/11/22/osu-mich"]
    assert links == ["https://conf.test/fbreports/2026/11/22/osu-mich"], "a reports page's own links are followed"
    assert all(any("fbreport" in u.lower() or "availab" in u.lower() for u in starts)
               for name, starts in P.SOURCES.items() if name not in ("cfp", "nba_official")), \
        "each conference's look starts where its reports are posted"


def test_the_nbas_own_report_is_asked_for_by_its_time_newest_first():
    import datetime as dt
    from zoneinfo import ZoneInfo
    now = dt.datetime(2026, 11, 23, 17, 52, tzinfo=ZoneInfo("America/New_York")).timestamp()
    urls = P.nba_pdf_urls(now, back=3)
    assert [u.rsplit("/", 1)[-1] for u in urls] == ["Injury-Report_2026-11-23_05_45PM.pdf",
                                                   "Injury-Report_2026-11-23_05_30PM.pdf",
                                                   "Injury-Report_2026-11-23_05_15PM.pdf"]
    pdf = _pdf(b"BT (Injury Report: 11/23/26 05:30 PM) Tj ET")
    rec = P.look_nba_pdf(now, get=lambda u: ("ok", "application/pdf", pdf) if u == urls[1] else ("HTTP 404", "", b""))
    assert rec["url"] == urls[1] and rec["pdf_text"] == "Injury Report: 11/23/26 05:30 PM"
    assert rec["asked"] == ["HTTP 404 Injury-Report_2026-11-23_05_45PM.pdf", "ok Injury-Report_2026-11-23_05_30PM.pdf"]
    assert P.look_nba_pdf(now, get=lambda u: ("HTTP 404", "", b""))["status"] == "none found"


def test_the_file_is_written_whole_and_small_and_the_clock_holds_it_to_every_three_hours():
    out = Path(tempfile.mkdtemp()) / "probe.json"
    P._LAST["at"] = 0.0
    wait = P.watch_once(now=1_000_000.0, get=_get(), out=out)
    doc = json.loads(out.read_text())
    assert doc["generated_at"].startswith("1970-01-12") and doc["every_s"] == P.EVERY_S == 3 * 3600
    assert set(doc["sources"]) == set(P.SOURCES) | {"nba_report_pdf"}, "every source looked at (404s here)"
    assert wait == P.IDLE_S
    mtime = out.stat().st_mtime
    assert P.watch_once(now=1_000_000.0 + 3600, get=_get(), out=out) <= P.IDLE_S
    assert out.stat().st_mtime == mtime, "not again inside three hours"
    assert len(out.read_text()) <= P.MAX_OUT


def test_it_starts_on_the_box_and_a_switch_holds_it():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    assert 'threading.Thread(target=_cfb_avail_probe, daemon=True, name="cfbavailprobe").start()' in src
    assert "if _cp.on():" in src
    os.environ[P.ENV] = "off"
    try:
        assert not P.on()
    finally:
        os.environ.pop(P.ENV, None)
    assert P.on()


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
