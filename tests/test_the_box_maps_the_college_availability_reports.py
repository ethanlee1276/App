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
                          "https://cdn.store.test/osu-mich.pdf", "https://conf.test/fb/availability/osu-mich",
                          # the data address its script names, on the conference's own site
                          "https://api.conf.test/football/availability.json"}, pages
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
    assert links == ["https://conf.test/fbreports/2026/11/22/osu-mich", "https://conf.test/api/v2/fbreports?week=13",
                     "https://cdn.x.test/availability/w13.json"], "its links, then the addresses its scripts name"
    assert rec["scripts"] == [] and rec["words"] < 200
    found = P.look({"conf": ("https://conf.test/fbreports",)},
                   get=lambda u: ("ok", "text/html", body) if u == "https://conf.test/fbreports" else ("HTTP 404", "", b""))
    assert "https://cdn.x.test/availability/w13.json" not in [pg["url"] for pg in found["conf"]["pages"]], \
        "another site's address is never read"
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


def test_a_page_that_turns_the_plain_request_away_is_asked_once_more_under_a_plain_reader_name():
    calls = []

    def fake(url, agent):
        calls.append(agent)
        return ("HTTP 404", "", b"") if agent is None else ("ok", "text/html", b"<title>ACC</title>")
    real = P._get_as
    P._get_as = fake
    try:
        status, ctype, raw = P._get("https://theacc.com/x")
    finally:
        P._get_as = real
    assert status == "ok" and ctype.endswith("; agent=plain") and calls == [None, P.PLAIN_AGENT]
    assert "qellys" not in P.PLAIN_AGENT.lower(), "nothing that names this site goes out in a header"
    rec, _ = P.look_page("https://theacc.com/x", get=lambda u: ("ok", "text/html; agent=plain", b"<p>x</p>"))
    assert rec["agent"] == "plain"


def test_a_feature_page_is_read_through_its_own_script_and_each_page_once():
    page = (b"<link href='https://static.conf.test/feature-pages/availability-reporting/availability_reporting.css'>"
            b"<script>var cfg = {dataUrl: 'https://static.conf.test/feature-pages/availability-reporting/fb.json'};"
            b"</script><a href='https://conf.test/fb-availability-archive.aspx#top'>Archive</a>")
    js = b"fetch('https://static.conf.test/feature-pages/availability-reporting/fb.json'); var u='/services/avail.ashx';"
    site = {"https://conf.test/fb-availability.aspx": ("ok", "text/html", page),
            "https://static.conf.test/feature-pages/availability-reporting/availability_reporting.js":
                ("ok", "application/javascript", js),
            "https://static.conf.test/feature-pages/availability-reporting/fb.json":
                ("ok", "application/json", b'{"games": [{"player": "A", "status": "Out"}]}')}
    found = P.look({"conf": ("https://conf.test/fb-availability.aspx", "http://conf.test/fb-availability.aspx#x")},
                   get=lambda u: site.get(u, ("HTTP 404", "", b"")))
    pages = {pg["url"]: pg for pg in found["conf"]["pages"]}
    assert list(pages).count("https://conf.test/fb-availability.aspx") == 1, "one page, one address"
    first = pages["https://conf.test/fb-availability.aspx"]
    assert first["inline"] == ["var cfg = {dataUrl: 'https://static.conf.test/feature-pages/availability-reporting/fb.json'};"]
    script = pages["https://static.conf.test/feature-pages/availability-reporting/availability_reporting.js"]
    assert script["js_urls"] == ["https://static.conf.test/feature-pages/availability-reporting/fb.json",
                                 "/services/avail.ashx"]
    assert pages["https://static.conf.test/feature-pages/availability-reporting/fb.json"]["json_head"].startswith(
        '{"games"'), "the data itself, read"
    assert P.canon("http://bigten.org/x.aspx#events") == "https://bigten.org/x.aspx"


def test_every_inline_script_is_counted_and_the_report_bearing_ones_kept_and_an_app_bundle_read():
    body = ('<script>var component = {"type":"main-navigation","data":[]};</script>'
            '<script>var component = {"type":"story-content","data":{"html":"<td>John Smith</td><td>Questionable</td>"}};'
            '</script><script src="/dist/assets/app-CRAW0Srj.js"></script>').encode()
    rec, links = P.look_page("https://www.secsports.com/fbreports", get=lambda u: ("ok", "text/html", body))
    assert rec["inline_count"] == 2 and [x["types"] for x in rec["inline_inventory"]] == [["main-navigation"],
                                                                                           ["story-content"]]
    assert rec["inline_inventory"][1]["status_words"] and len(rec["inline"]) == 1 and "John Smith" in rec["inline"][0]
    assert links == ["https://www.secsports.com/dist/assets/app-CRAW0Srj.js"], "the site's own app bundle is read"
    js = b"fetch('/api/availability-reports?sport=football');var y='https://cdn.x.test/a.png';"
    got, _ = P.look_page(links[0], get=lambda u: ("ok", "application/javascript", js))
    assert got["js_urls"] == ["/api/availability-reports?sport=football", "https://cdn.x.test/a.png"]
    assert got["js_bits"] and "availability-reports" in got["js_bits"][0]


def test_a_frame_the_report_page_embeds_is_read_wherever_it_lives():
    page = b"<p>Availability</p><iframe src='https://docs.google.com/spreadsheets/d/e/2PACX/pubhtml?widget=true'></iframe>"
    sheet = b"<table><tr><td>Team</td><td>Player</td><td>Status</td></tr><tr><td>Clemson</td><td>A Back</td><td>Out</td></tr></table>"
    site = {"https://conf.test/fb.aspx": ("ok", "text/html", page),
            "https://docs.google.com/spreadsheets/d/e/2PACX/pubhtml?widget=true": ("ok", "text/html", sheet)}
    found = P.look({"conf": ("https://conf.test/fb.aspx",)}, get=lambda u: site.get(u, ("HTTP 404", "", b"")))
    pages = {pg["url"]: pg for pg in found["conf"]["pages"]}
    assert pages["https://conf.test/fb.aspx"]["frames"] == ["https://docs.google.com/spreadsheets/d/e/2PACX/pubhtml?widget=true"]
    sheet_pg = pages["https://docs.google.com/spreadsheets/d/e/2PACX/pubhtml?widget=true"]
    assert sheet_pg["tables"][0]["first"][1] == ["Clemson", "A Back", "Out"], "the embedded sheet's rows, read"
    assert all("_frames" not in pg for pg in found["conf"]["pages"])


def test_a_file_too_big_loses_fields_never_its_ending():
    import tempfile as _t
    big = {"x": {"pages": [{"url": str(i), "inline": ["a" * 5000] * 4, "pdf_text": "b" * 4000} for i in range(60)]}}
    out = Path(_t.mkdtemp()) / "p.json"
    P.write(big, 0, out)
    text = out.read_text()
    doc = json.loads(text)                                     # whole JSON, always
    assert len(text) <= P.MAX_OUT and len(doc["sources"]["x"]["pages"]) == 60, "fields went, not pages"
    assert "inline" not in doc["sources"]["x"]["pages"][0]


def test_an_app_page_gives_its_own_data_from_its_data_page_attribute():
    import html as _h
    data = {"component": "Reports/Show", "props": {"report": {"teams": [{"name": "Alabama", "players": [
        {"name": "A Back", "status": "Questionable"}]}]}, "menus": []}, "version": "abc"}
    body = f'<div id="app" data-page="{_h.escape(json.dumps(data))}"></div>'.encode()
    rec, _links = P.look_page("https://www.secsports.com/fbreports", get=lambda u: ("ok", "text/html", body))
    app = rec["app"]
    assert app["component"] == "Reports/Show" and app["props_keys"] == ["menus", "report"]
    assert any("Questionable" in b for b in app["bits"]) and json.loads(app["whole"]) == data


def test_the_file_is_written_whole_and_small_and_the_clock_holds_it_to_every_three_hours():
    out = Path(tempfile.mkdtemp()) / "probe.json"
    P._LAST["at"] = 0.0
    wait = P.watch_once(now=1_000_000.0, get=_get(), out=out)
    doc = json.loads(out.read_text())
    assert doc["generated_at"].startswith("1970-01-12") and doc["every_s"] == P.EVERY_S == 3 * 3600
    assert set(doc["sources"]) == set(P.SOURCES), "every source looked at (each page a 404 here)"
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
