"""Security P3s from the audit (roadmap #52, E-10 … E-20).

Each one is small and each one is easy to undo by accident, so each is
pinned here by behaviour where it can be run and by text where it cannot.
"""

import hashlib
import json
import os
import re
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QB_UNSUB_KEY", "test-only-unsub-key-0123456789")
SERVER = (ROOT / "server.py").read_text()
CADDY = (ROOT / "deploy" / "Caddyfile").read_text()
UNIT = (ROOT / "deploy" / "qellys.service").read_text()

from engine import billing, digest as D, routes  # noqa: E402
import server as srv  # noqa: E402


def test_e10_the_route_hint_is_a_meta_the_csp_allows():
    doc = routes.document(routes.resolve("/record"), (ROOT / "web" / "index.html").read_text())
    assert '<meta name="qb-route" content="' in doc and "<script>window.__QB_ROUTE__" not in doc
    assert "document.querySelector('meta[name=\"qb-route\"]')" in (ROOT / "web" / "js" / "app.js").read_text()


def test_e11_only_a_whole_session_id_reaches_stripe():
    ok = "cs_test_" + "a1B2c3D4e5F6g7H8"
    assert billing._SESSION_ID.fullmatch(ok)
    assert billing._SESSION_ID.fullmatch("cs_test_a1b2c3")
    for bad in ("cs_x/../../v1/customers", "cs_test_", "cs_live_abcdefghij?x=1",
                "cs_test_abcdefghij/../x", "xcs_test_abcdefghijk", ""):
        assert not billing._SESSION_ID.fullmatch(bad), bad


def _db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)")
    c.execute("INSERT INTO users VALUES (7, 'x@y.co')")
    D.ensure_tables(c)
    return c


def test_e12_no_usable_token_at_rest_and_links_carry_it_in_the_path():
    c = _db()
    tok = D.optin_set(c, 7, True, True)["token"]
    stored = c.execute("SELECT token, salt FROM digest_optin").fetchone()
    assert stored["token"] == "" and stored["salt"], "nothing a DB copy could replay"
    assert re.fullmatch(r"7\.[A-Za-z0-9_-]{24,64}", tok)
    assert D.unsubscribe(c, "7." + "A" * 32) is False, "a forged mac is refused"
    assert D.unsubscribe(c, tok) is True
    msg = D._wrap("s", "t", "<p>h</p>", tok)
    assert f"/unsubscribe/{tok}" in msg["text"] and "unsubscribe?t=" not in msg["text"]


def test_e12_a_clear_token_already_delivered_works_until_its_window_closes():
    c = _db()
    c.execute("INSERT INTO digest_optin (user_id, morning, nightly, token, created_at) "
              "VALUES (7, 1, 1, 'legacy-clear-token-0123456789', 0)")
    c.commit()
    assert D.recipients(c, "morning")[0]["token"].startswith("7."), "new sends are derived"
    assert D.unsubscribe(c, "legacy-clear-token-0123456789") is True
    c.execute("UPDATE digest_optin SET morning=1, legacy_until=?", (int(time.time()) - 1,))
    c.commit()
    D.recipients(c, "morning")                       # the sweep blanks it
    assert c.execute("SELECT token FROM digest_optin").fetchone()[0] == ""
    assert D.unsubscribe(c, "legacy-clear-token-0123456789") is False


def test_e12_the_journal_never_logs_the_token():
    assert srv._UNSUB_IN_LOG.sub(r"\1…", '"GET /unsubscribe/7.abcDEF123 HTTP/1.1" 200') == \
        '"GET /unsubscribe/… HTTP/1.1" 200'
    assert "abc" not in srv._UNSUB_IN_LOG.sub(r"\1…", "GET /unsubscribe?t=abcdefghijklmnop&x=1")


def test_e13_an_unsealable_board_leaves_the_public_path():
    with tempfile.TemporaryDirectory() as tmp:
        web = Path(tmp) / "web"; (web / "data").mkdir(parents=True)
        (web / "data" / "recommendations.json").write_text("{}")
        old = (srv.WEB, srv.UNSEALED_DIR, srv.UNSEALED_FLAG)
        srv.WEB, srv.UNSEALED_DIR, srv.UNSEALED_FLAG = web, Path(tmp) / "unsealed", Path(tmp) / "UNSEALED.json"
        try:
            srv._fail_closed([{"board": "recommendations.json", "rows": 3}], "test")
            assert not (web / "data" / "recommendations.json").exists()
            assert (Path(tmp) / "unsealed" / "recommendations.json").exists()
            flag = json.loads((Path(tmp) / "UNSEALED.json").read_text())
            assert flag["moved"] == ["recommendations.json"] and flag["rows"] == 3
            srv._clear_unsealed_flag()
            assert not (Path(tmp) / "UNSEALED.json").exists()
        finally:
            srv.WEB, srv.UNSEALED_DIR, srv.UNSEALED_FLAG = old
    assert "data/unsealed/" in (ROOT / ".gitignore").read_text()


def test_e14_no_exception_text_reaches_a_client():
    assert '{"error": f"{type(exc).__name__}: {exc}"}' not in SERVER
    assert '"detail": str(exc)' not in SERVER
    for where in ("sleeper proxy", "sleeper league desk", "espn league", "yahoo league", "zeno", "run slate"):
        assert f'exc, "{where}")' in SERVER, where


def test_e15_permissions_policy_hide_list_and_unit_filters():
    pp = dict(srv.SECURITY_HEADERS)["Permissions-Policy"]
    assert "camera=()" in pp and "geolocation=()" in pp
    assert f'Permissions-Policy "{pp}"' in CADDY, "Caddy and the app send the same policy"
    assert re.search(r"file_server \{\s*hide [^\n]*\.env", CADDY) and "hide .well-known" not in CADDY
    assert "CapabilityBoundingSet=\n" in UNIT and "SystemCallFilter=@system-service" in UNIT
    assert "~@resources" not in UNIT, "os.nice is a @resources call"


def test_e17_the_cloudflare_list_refreshes_weekly():
    timer = (ROOT / "deploy" / "qellys-cfips.timer").read_text()
    svc = (ROOT / "deploy" / "qellys-cfips.service").read_text()
    assert "OnCalendar=weekly" in timer and "Persistent=true" in timer
    assert "ExecStart=/srv/qellys/deploy/cfips.sh" in svc


def test_e18_the_sleeper_cache_is_capped():
    with tempfile.TemporaryDirectory() as d:
        for i in range(5):
            f = Path(d) / f"sleeper_league_{i}.json"
            f.write_text("{}"); os.utime(f, (i, i))
        (Path(d) / "sleeper_players_nfl.json").write_text("{}")
        name = srv.sleeper_cache_name("league/99", cache_dir=d, cap=5)
        assert name == "sleeper_league_99.json"
        left = sorted(p.name for p in Path(d).iterdir())
        assert "sleeper_league_0.json" not in left, "the oldest goes"
        assert "sleeper_players_nfl.json" in left, "the shared players file is never pruned"
    assert SERVER.count("cache = sleeper_cache_name(path)") == 3


def test_e16_e19_docs_and_comments():
    run = (ROOT / "docs" / "WHEN_YOU_ARE_HOME.md").read_text()
    assert "secrets.token_urlsafe(32)" in run and "read -rs QB_OWNER_TOKEN" in run
    assert "export QB_OWNER_TOKEN='paste" not in run
    assert "The Paddle webhook is EXEMPT" not in SERVER


def test_e20_vendored_libraries_match_their_recorded_hash():
    rows = [l.split() for l in (ROOT / "web" / "vendor" / "VERSIONS.txt").read_text().splitlines()
            if l.strip() and not l.startswith("#")]
    names = {r[0] for r in rows}
    on_disk = {p.name for p in (ROOT / "web" / "vendor").iterdir() if p.name != "VERSIONS.txt"}
    assert names == on_disk, (names, on_disk)
    for name, _version, sha in rows:
        assert hashlib.sha256((ROOT / "web" / "vendor" / name).read_bytes()).hexdigest() == sha, name


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); ran += 1; print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1; print(f"  FAIL {name}: {exc}")
            except Exception as exc:  # noqa: BLE001
                fails += 1; print(f"  ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
