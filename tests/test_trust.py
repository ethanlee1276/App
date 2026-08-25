"""Trust furniture — methodology, receipts, the changelog, status.

Ethan, 2026-08-25: *"Trust furniture — the pages real companies have.
Cheap to build, and their absence is what makes visitors bounce with 'is
this legit?'"*

The failure modes here are quiet ones. A methodology page that states a
constant goes stale the day somebody changes the constant, and it is the
page a sceptical reader checks the others against. A receipts download
that filters a bucket is the cherry-picking it exists to disprove. A
status page that times its own fetch flatters every board it describes.

Run directly: `python3 tests/test_trust.py`
"""

import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import ledger, routes                            # noqa: E402


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


APP = _read("web", "js", "app.js")
HTML = _read("web", "index.html")
SERVER = _read("server.py")
CSS = _read("web", "css", "styles.css")


# --- the receipts ------------------------------------------------------------

def _book():
    """A journal with one settled pick in every bucket that matters, one
    still open, and one settled at zero stake."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE bets (id INTEGER PRIMARY KEY, date TEXT,
        sport TEXT, category TEXT, player TEXT, market TEXT, side TEXT,
        line REAL, odds INTEGER, book TEXT, stake_units REAL, status TEXT,
        pnl_units REAL, hit_prob REAL, closing_line INTEGER, grade TEXT)""")
    rows = [
        ("2026-08-01", "mlb", "main", "A", "hits", "OVER", 1.5, -110, "DK",
         1.0, "won", 0.91, 0.55, -120, "A"),
        ("2026-08-02", "nfl", "longshot", "B", "anytime_td", "YES", 0.5, 320,
         "FD", 0.3, "lost", -0.3, 0.28, 300, "B"),
        ("2026-08-03", "mlb", "predmarket", "C", "moneyline", "HOME", 0, -140,
         "KX", 0.5, "push", 0.0, 0.6, -140, "C"),
        ("2026-08-04", "nfl", "main", "D", "rec_yds", "OVER", 60.5, -110, "DK",
         1.0, "pending", None, 0.6, None, "A"),
        ("2026-08-05", "mlb", "main", "E", "hits", "OVER", 0.5, -200, "DK",
         0.0, "won", 0.0, 0.7, -210, "A"),
    ]
    conn.executemany(
        "INSERT INTO bets (date, sport, category, player, market, side, line,"
        " odds, book, stake_units, status, pnl_units, hit_prob, closing_line,"
        " grade) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def test_the_receipts_carry_every_bucket():
    """A file that quietly dropped the long shots and the prediction
    markets would be the cherry-picking it exists to disprove. The
    category rides as a column so the buckets stay separable."""
    conn = _book()
    got = ledger.receipts(conn)
    cats = {r["category"] for r in got}
    assert cats == {"main", "longshot", "predmarket"}, cats
    assert "category" in ledger.RECEIPT_COLUMNS


def test_an_open_pick_is_not_a_receipt():
    """Including one would let a reader compute a record that counts
    bets which have not happened yet."""
    conn = _book()
    got = ledger.receipts(conn)
    assert all(r["status"] in ("won", "lost", "push") for r in got)
    assert not any(r["player"] == "D" for r in got)


def test_a_spreadsheet_reads_forwards():
    """A running total only means something oldest-first, which is the
    opposite of every list on the site."""
    conn = _book()
    dates = [r["date"] for r in ledger.receipts(conn)]
    assert dates == sorted(dates)


def test_the_column_list_is_a_decision_not_a_star():
    """A column added to `bets` for some internal purpose must not start
    appearing in a public download by itself."""
    src = _read("engine", "ledger.py")
    i = src.index("def receipts(conn")
    body = src[i:src.index("\ndef recent_settled", i)]
    assert "SELECT *" not in body
    for col in ("stake_units", "closing_line", "pnl_units"):
        assert col in ledger.RECEIPT_COLUMNS


def test_the_download_is_free_like_the_record_it_comes_from():
    """The record is the evidence the subscription is sold on, and a
    proof nobody can read persuades nobody. Every row is settled — no
    open position, no line we are currently recommending."""
    i = SERVER.index("def _receipts_csv")
    body = SERVER[i:SERVER.index("\n    def do_HEAD", i)]
    assert "_entitled" not in body and "gate." not in body
    assert "Content-Disposition" in body
    assert 'filename="qellys-receipts-' in body


def test_the_methodology_page_links_the_download():
    assert "/api/record/receipts.csv" in APP
    assert 'download>' in APP


# --- the methodology page ----------------------------------------------------

def test_it_never_prints_a_constant_it_does_not_own():
    """A page that types "we shrink 50% toward the market" still says
    50% the day somebody changes it to 0.4 — and this is the page a
    sceptical reader checks the others against. Live figures come off
    record.json; everything else names the shape and leaves the value
    where it is measured."""
    i = APP.index("async function renderMethodology()")
    body = APP[i:APP.index("\n/* The written half", i)]
    assert "loadRecordOnce()" in body
    for typed in ("0.5", "50%", "10%", "0.10", "MARKET_SHRINK"):
        assert typed not in body, f"a model constant is typed into the page: {typed}"


def test_it_names_what_is_fitted_and_what_is_not():
    """The difference is the honest part, and most sites will not say
    which is which."""
    i = APP.index("async function renderMethodology()")
    body = APP[i:APP.index("\n/* The written half", i)]
    assert "Still an assumption" in body and "Fitted against results" in body
    assert "What we do not model" in body


def test_the_page_is_registered_everywhere_a_page_has_to_be():
    assert 'id="view-methodology"' in HTML and 'id="methodology-body"' in HTML
    assert 'id="view-status"' in HTML and 'id="status-body"' in HTML
    assert '"about", "methodology", "status"' in APP, "missing from VIEW_ORDER"
    assert '"methodology", "status",' in APP, "missing from STANDALONE_MODES"
    assert 'data-sport="methodology"' in HTML and 'data-sport="status"' in HTML
    launch = _read("launch.py")
    assert '("Methodology", "?sport=mlb#methodology"' in launch
    assert '("Status", "?sport=mlb#status"' in launch
    for name in ("methodology", "status", "changelog"):
        assert name in routes.SECTIONS


def test_status_keeps_the_freshness_chip_it_is_about():
    """Reference pages hide the chip because there is no data behind
    them. Status is the page ABOUT freshness — hiding it there would be
    the one place the answer is genuinely wanted."""
    i = APP.index("const REFERENCE_VIEWS = [")
    line = APP[i:APP.index("];", i)]
    assert '"methodology"' in line and '"status"' not in line


def test_the_contact_address_is_on_the_about_page():
    """"About, contact, changelog" — the address existed only at the
    bottom of the terms, which is where nobody looks. It has to be ONE
    address in both places: two support inboxes is one that goes
    unread."""
    i = APP.index("function renderAbout()")
    body = APP[i:APP.index("async function renderWhy", i)]
    assert "mailto:support@qellysbook.com" in body
    terms = _read("web", "terms.html")
    assert "support@qellysbook.com" in terms, \
        "the About page and the terms name different addresses"


# --- the changelog -----------------------------------------------------------

def test_the_changelog_is_written_not_generated():
    """web/data/ is generated and gitignored; this is a record somebody
    wrote. A generated file would be lost on a fresh clone."""
    path = os.path.join(ROOT, "web", "changelog.json")
    assert os.path.exists(path)
    doc = json.loads(_read("web", "changelog.json"))
    assert doc["entries"], "an empty log is a claim that nothing changed"
    import subprocess
    out = subprocess.run(["git", "check-ignore", "web/changelog.json"],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode != 0, "the changelog is gitignored"


def test_every_entry_is_dated_kinded_and_says_something():
    doc = json.loads(_read("web", "changelog.json"))
    kinds = {"ship", "model", "fix", "refuse"}
    seen = []
    for e in doc["entries"]:
        assert len(str(e.get("date", ""))) == 10, e
        assert e.get("kind") in kinds, e
        assert e.get("title") and len(e.get("body", "")) > 40, e
        seen.append(e["date"])
    assert seen == sorted(seen, reverse=True), "the log is not newest-first"


def test_a_model_change_is_its_own_kind_of_entry():
    """Ethan: "A changelog entry when numbers move because the model
    changed, so users never wonder if they misremembered." Those entries
    are the ones the Record page keeps eras for."""
    doc = json.loads(_read("web", "changelog.json"))
    model = [e for e in doc["entries"] if e["kind"] == "model"]
    assert model, "no model-change entries at all"
    era_dates = {e["start"] for e in ledger.MODEL_ERAS if e["start"]}
    logged = {e["date"] for e in model}
    assert era_dates <= logged, \
        f"a model era has no changelog entry: {era_dates - logged}"


def test_a_refusal_is_logged_too():
    """A decision nobody wrote down gets re-made by somebody who has not
    seen the reasoning — the rule docs/IDEAS.md already keeps."""
    doc = json.loads(_read("web", "changelog.json"))
    assert any(e["kind"] == "refuse" for e in doc["entries"])


# --- the status page ---------------------------------------------------------

def test_freshness_is_read_from_the_file_not_from_the_fetch():
    """Timing its own fetch is how a frozen board reads as live from
    across town: the answer is always "seconds"."""
    i = APP.index("async function boardStamp(file)")
    body = APP[i:APP.index("\n}", i)]
    assert 'method: "HEAD"' in body, "a status page must not download 8MB"
    assert 'headers.get("Last-Modified")' in body


def test_the_app_answers_head_so_the_page_works_where_it_is_built():
    """In production Caddy serves /data off disk and speaks HEAD
    natively. Without this the page is blank on the one machine where it
    is being developed."""
    i = SERVER.index("def do_HEAD")
    body = SERVER[i:SERVER.index("\n    def _entity_page", i)]
    assert 'path.startswith("/api/")' in body, \
        "an API HEAD would get a half-suppressed body"
    assert "Last-Modified" in body
    assert "is_relative_to" in body, "path traversal"


def test_stale_means_late_for_this_machine():
    i = APP.index("async function renderStatus()")
    body = APP[i:APP.index("\n/* ====", i)]
    assert "staleAfterMs()" in body
    assert "heartbeat.json" in body


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
