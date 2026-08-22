"""What changes when the door is open to everyone.

Ethan, 2026-08-15: *"a dedicated server for anyone and everyone to use."*

A LAN server and a public one are different programs wearing the same
code. Most of this repo's assumptions were fine for one person on their
own Wi-Fi and stop being fine the moment a stranger can reach the port.
Two were found by audit rather than by reading — measured against a
running server, which is the only way this class of thing shows up:

  * **`/api/profile/<name>` created accounts with no credential.** Three
    were made from curl in a second. On a LAN that was the feature; public
    it is free disk for whoever finds the path.
  * **No security headers at all.** Not one.

Both are fixed and pinned here. The plan they came out of is
docs/LAUNCH.md, and the thing worth keeping from it is the order: the
questions that can invalidate the work go before the work.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _shell_blocks(md):
    """The fenced code in a markdown file — the parts that are commands.

    Prose has to stay free to name a command as the WRONG one to run. A
    guard that searches the whole file cannot tell the instruction from
    the warning about it, and fires on the paragraph explaining itself.
    """
    return re.findall(r"^```(?:bash|sh)?\n(.*?)^```", md, re.M | re.S)


SERVER = _read("server.py")
APP = _read("web", "js", "app.js")
PLAN = _read("docs", "LAUNCH.md")


# --- the open write endpoint -------------------------------------------------
def test_a_stranger_cannot_create_a_profile():
    """The one an audit found. Anyone could POST a name that did not
    exist and get a 1MB store, with no credential of any kind."""
    i = SERVER.index('if not parsed.path.startswith("/api/profile/")')
    body = SERVER[i:i + 2000]
    assert "_load_profile(_name) is None" in body
    assert "_local_only()" in body and "_via_tailnet()" in body
    assert "_PROFILE_LOCAL_ONLY" in body


def test_syncing_an_existing_profile_still_works_from_anywhere():
    """The fix must not break the phone that already has one. Creation is
    the privileged act; syncing is not, and gating both would have broken
    the feature to secure it."""
    i = SERVER.index('if not parsed.path.startswith("/api/profile/")')
    body = SERVER[i:i + 2000]
    guard = body[body.index("_load_profile(_name) is None"):]
    guard = guard[:guard.index("code, out = profile_sync")]
    # The refusal is conditional on the profile being ABSENT.
    assert "is None" in guard
    assert "403" in guard


def test_the_refusal_points_at_the_thing_that_replaced_it():
    """A closed door with no sign on it is a bug report."""
    i = SERVER.index("_PROFILE_LOCAL_ONLY = (")
    msg = SERVER[i:i + 500]
    assert "email and password" in msg


# --- security headers --------------------------------------------------------
def test_every_response_carries_the_basic_headers():
    assert "SECURITY_HEADERS = (" in SERVER
    i = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[i:SERVER.index("\n)", i)]
    for name in ("X-Content-Type-Options", "Referrer-Policy",
                 "X-Frame-Options", "Content-Security-Policy"):
        assert name in block, name
    assert "nosniff" in block
    # …and they are sent from the one place every response goes through.
    j = SERVER.index("def _send(")
    send = SERVER[j:j + 1400]
    assert "for name, value in SECURITY_HEADERS" in send


def test_hsts_is_sent_only_over_https():
    """On a plain-HTTP LAN address it does nothing at best; announced from
    a name that later has to serve HTTP it is a self-inflicted outage
    browsers remember for months."""
    j = SERVER.index("def _send(")
    send = SERVER[j:j + 1400]
    i = send.index("Strict-Transport-Security")
    assert "self._is_https()" in send[:i], "HSTS is sent unconditionally"
    # And it is NOT in the always-sent tuple, which is the other way the
    # same mistake gets made.
    k = SERVER.index("SECURITY_HEADERS = (")
    always = SERVER[k:SERVER.index("\n)", k)]
    assert "Strict-Transport-Security" not in always


def test_connect_src_is_self_and_that_is_a_real_restriction():
    """Not decoration. The page makes NO browser-side request to any
    external host — Sleeper, ESPN, Yahoo and Stripe are all reached by the
    server — so an injected script has nowhere to send what it steals.
    Checked against the page rather than asserted."""
    k = SERVER.index("SECURITY_HEADERS = (")
    csp = SERVER[k:SERVER.index("\n)", k)]
    assert "connect-src 'self'" in csp
    external = re.findall(r'fetch\(\s*[`"\']https?://', APP)
    assert not external, f"the page now fetches externally: {external[:3]}"


def test_the_inline_script_weakness_is_written_down_not_hidden():
    """`script-src` still needs 'unsafe-inline' because the page carries
    inline onclick handlers. That is a real weakness in the policy, and an
    exception nobody wrote down gets mistaken for a considered choice."""
    k = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[max(0, k - 1400):SERVER.index("\n)", k)]
    assert "unsafe-inline" in block
    assert "onclick" in block, "the reason for the weakness is not recorded"
    assert APP.count('onclick="') > 0, \
        "the handlers are gone — tighten script-src and update this test"


def test_frame_src_names_every_host_the_page_actually_embeds():
    """The CSP must not silently switch off a feature.

    `default-src 'self'` covers frames when `frame-src` is absent, so the
    first version of these headers refused BOTH pool-chart embeds on
    Rocket Radar — the chart panel that is the entire point of that page
    came up empty. Nothing failed: the page renders perfectly and it is
    the browser that declines the frame, with the refusal only in the
    console. 4,400 tests could not see it; a headless sweep reading the
    console found it in one pass.

    So the rule is derived from the page rather than typed by hand: every
    host app.js builds an iframe src from must appear in `frame-src`, and
    `frame-src` must not be a wildcard — `https:` would let any injected
    iframe load anything, which is most of what frame protection is for.
    """
    # Read the assembled header, not the source text. Grepping the source
    # broke the moment the directive was split across two Python string
    # literals for line length: the regex captured the first literal only
    # and the test failed on a host that was in fact allowed. What the
    # browser sees is the concatenated value, so that is what to check.
    import server as _srv
    csp = dict(_srv.SECURITY_HEADERS)["Content-Security-Policy"]
    assert "frame-src" in csp, \
        "no frame-src, so default-src 'self' silently blocks the charts"
    frame_src = next(d for d in csp.split(";") if d.strip().startswith("frame-src"))
    frame_src = frame_src.strip()[len("frame-src"):].strip()
    assert "*" not in frame_src and frame_src.split() != ["https:"], \
        f"frame-src is a wildcard: {frame_src!r}"

    # Every embed URL in the page, not a window around one call site: a
    # windowed search silently found nothing when the URLs sat twenty
    # lines above the <iframe>, and a test that finds nothing passes.
    assert "<iframe" in APP, "no iframe left — drop frame-src and this test"
    embedded = set(re.findall(r'https://([a-z0-9.-]+)/[^`"\']*embed=1', APP))
    assert embedded, "could not find the embed URLs — this test has gone stale"
    for host in sorted(embedded):
        assert host in frame_src, \
            f"the page frames {host} but frame-src does not allow it"


def test_clickjacking_is_refused_twice():
    """`X-Frame-Options` for old browsers, `frame-ancestors` for the rest.
    A betting page framed inside somebody else's site is a phishing page
    wearing our numbers."""
    k = SERVER.index("SECURITY_HEADERS = (")
    block = SERVER[k:SERVER.index("\n)", k)]
    assert "DENY" in block and "frame-ancestors 'none'" in block


# --- the plan ----------------------------------------------------------------
def test_the_plan_puts_the_killable_questions_first():
    """Standing up a server before checking whether Stripe will process
    this business, or whether the feeds permit commercial use, is how
    three weeks get spent on something that has to be rebuilt."""
    assert "Phase 0" in PLAN
    assert PLAN.index("Phase 0") < PLAN.index("Phase 2 — the server")
    for must in ("restricted-business", "commercial use", "not a lawyer"):
        assert must in PLAN, must


def test_the_plan_is_honest_about_what_it_cannot_answer():
    assert "**I am not a lawyer.**" in PLAN
    assert "Only you can" in PLAN


def test_the_plan_names_the_audit_findings_rather_than_generalities():
    assert "no credential" in PLAN
    assert "No security headers" in PLAN
    # …and the things that were ALREADY right are recorded as such, so
    # nobody re-does them.
    assert "already correct" in PLAN


# --- the proxy, which quietly breaks everything above ------------------------
def test_the_real_caller_is_read_from_the_proxy_header():
    """FOUND WHILE WRITING THE DEPLOY CONFIG, before any of it shipped.

    Behind Caddy, `client_address` is Caddy. Every request would arrive
    from 127.0.0.1, `_local_only()` would be true for the entire internet,
    and both guards built on it — cleartext-password refusal and
    local-only profile creation — would be open doors that still looked
    shut."""
    i = SERVER.index("def _client_ip(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "X-Forwarded-For" in body
    # THE LAST HOP, not the first: a client can start the list with
    # anything it likes; the last entry is the one our proxy wrote.
    assert "hops[-1]" in body
    # …and trusted only from loopback, or anyone could claim to be local.
    assert "127.0.0.1" in body
    # The guards must go through it rather than reading the peer.
    for fn in ("def _local_only(", "def _via_tailnet("):
        j = SERVER.index(fn)
        guard = SERVER[j:SERVER.index("\n    def ", j + 1)]
        assert "_client_ip()" in guard, fn
        assert "self.client_address" not in guard, \
            f"{fn} reads the raw peer, which is the proxy behind a proxy"


def test_the_caddyfile_forwards_the_headers_the_guards_depend_on():
    caddy = _read("deploy", "Caddyfile")
    assert "X-Forwarded-For" in caddy and "X-Forwarded-Proto" in caddy
    # Bound to loopback, or the proxy in front is optional for an attacker.
    unit = _read("deploy", "qellys.service")
    assert "--bind 127.0.0.1" in unit


def test_the_production_unit_runs_the_process_that_refreshes_the_data():
    """A public site has to keep being true, not just keep answering.

    The unit ran `server.py`, which serves the built JSON and rebuilds
    none of it — nothing in production would have called `refresh_all`,
    the nightly ingest or the auto-settle, so `web/data/*.json` would have
    frozen at whatever the deploy wrote. The board would have kept saying
    "live" over a slate that was weeks old, which is worse than being
    down: down is obvious.

    launch.py is where the loop lives, and it serves the same handler
    (`from server import Handler`), so this costs nothing but the flag it
    needed to bind to loopback.
    """
    unit = _read("deploy", "qellys.service")
    exec_line = [l for l in unit.splitlines() if l.startswith("ExecStart=")]
    assert len(exec_line) == 1, exec_line
    assert exec_line[0].endswith("launch.py --bind 127.0.0.1 8000"), exec_line[0]

    # And the flag it needs is real, applied to the site's own bind —
    # not just accepted and ignored.
    launch = _read("launch.py")
    i = launch.index('if "--bind" in argv:')
    block = launch[i:i + 400]
    assert "bind = argv[i + 1]" in block
    # The class was renamed when the server was given a request
    # ceiling (BoundedHTTPServer). The claim here is that launch.py
    # binds the socket itself, not what the class is called.
    assert re.search(r"HTTPServer\(\(bind, port\), Handler\)", launch)
    assert 'ThreadingHTTPServer(("0.0.0.0"' not in launch, \
        "the site still hard-codes every interface somewhere"


def test_the_deploy_check_waits_longer_than_a_cold_start_takes():
    """The smoke check has to outlast the build that precedes the bind.

    launch.py runs a full `refresh_all()` — every board, every sport —
    BEFORE it binds the port, so a cold start is tens of seconds. The
    check was five tries two seconds apart: about twelve, which a healthy
    deploy loses every time. It would have declared success a failure and
    recommended rolling back a release that was working, which is the
    expensive direction to be wrong in.

    Pinned as a budget rather than as literal numbers, so the loop can be
    retuned without a test that only knows how to say "you changed it".
    """
    sh = _read("deploy", "deploy.sh")
    i = sh.index("prove it is actually up")
    block = sh[i:]
    tries = int(re.search(r"seq 1 (\d+)", block).group(1))
    gap = int(re.search(r"sleep (\d+)\n", block).group(1))
    assert tries * gap >= 120, f"only {tries * gap}s to answer a cold start"

    # A process that has EXITED is down, not slow — waiting the full
    # window on a corpse turns a clear failure into a slow one.
    assert "is-active" in block


# --- rate limiting -----------------------------------------------------------
def test_reads_and_auth_have_separate_budgets():
    """The first cut shared one counter per IP, so ordinary page polling
    ate the strict auth budget — measured: 19 of 25 signups got through
    instead of 20, and the missing one was a GET. A couple of minutes of
    browsing would have locked the same person out of signing in."""
    i = SERVER.index("def _rate_limited(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert 'bucket: str = "read"' in body
    assert 'f"{bucket}:{self._client_ip()}"' in body
    post = SERVER[SERVER.index("def do_POST("):]
    post = post[:post.index("\n    def ", 1)]
    assert '"auth" if auth else "read"' in post


def test_the_limits_are_generous_enough_for_normal_use():
    """A limit that trips on real browsing gets raised to infinity by the
    first person it annoys. The board polls every 30s and the meme page
    every 15s, so two tabs is already dozens a minute."""
    import re as _re
    read = int(_re.search(r"RATE_READ_PER_MIN = (\d+)", SERVER).group(1))
    auth = int(_re.search(r"RATE_AUTH_PER_MIN = (\d+)", SERVER).group(1))
    assert read >= 120, "too tight for a page that polls"
    assert auth <= 60 and auth >= 10, "auth limit is either useless or hostile"
    assert auth < read


def test_the_limiter_does_not_scan_the_whole_table_per_request():
    """MEASURED 2026-08-22, and it is the reason this test exists.

    The sweep ran on EVERY request once the table passed 8192 keys, and
    built `list(_RATE.items())` — a copy of the whole table — to do it,
    under the global lock every API request takes:

           1,000 keys   0.002 ms per request
          16,000 keys   3.587 ms
          64,000 keys  21.982 ms

    At 64k distinct callers that is ~45 requests per second for the whole
    site on any hardware, and it is a spiral rather than a plateau: the
    slower it gets, the more requests are in flight, the more addresses
    arrive. Which is exactly the traffic an Instagram post delivers.

    It would never have crashed. It would have gone treacle-slow at the
    one moment it mattered and recovered by itself afterwards.
    """
    import time
    import server as S
    now = time.time()
    S._RATE.clear()
    S._RATE_SWEPT_AT = now                      # just swept; none due
    for i in range(40_000):
        S._RATE[f"read:k{i}"] = [now]
    t0 = time.perf_counter()
    for j in range(200):
        S.rate_ok(f"read:new{j}", S.RATE_READ_PER_MIN, now)
    per = (time.perf_counter() - t0) / 200
    S._RATE.clear()
    assert per < 0.001, (
        f"{per * 1000:.3f} ms per request with 40k callers tracked — the "
        f"per-request table scan is back, and every API request queues "
        f"behind it")


def test_the_sweep_still_collects_what_it_is_for():
    """Cheap and useless is not the goal. Anything older than the window
    is dead weight — nothing reads it — so a sweep must take all of it."""
    import time
    import server as S
    now = time.time()
    S._RATE.clear()
    S._RATE_SWEPT_AT = 0.0                      # overdue, so it runs
    for i in range(3_000):
        S._RATE[f"read:old{i}"] = [now - 300]
    for i in range(50):
        S._RATE[f"read:live{i}"] = [now]
    S.rate_ok("read:trigger", S.RATE_READ_PER_MIN, now)
    left = len(S._RATE)
    S._RATE.clear()
    assert left <= 52, f"{left} entries survived a sweep of 3,000 expired ones"


def test_the_table_cannot_grow_without_a_ceiling():
    """It is memory on a 1 GB box, and the traffic that fills it is the
    traffic the box is least able to spare it for."""
    import time
    import server as S
    now = time.time()
    S._RATE.clear()
    S._RATE_SWEPT_AT = 0.0
    for i in range(S._RATE_MAX_KEYS * 2):       # all fresh, none evictable
        S._RATE[f"read:f{i}"] = [now]
    S.rate_ok("read:trigger", S.RATE_READ_PER_MIN, now)
    kept = len(S._RATE)
    S._RATE.clear()
    assert kept <= S._RATE_MAX_KEYS, f"{kept:,} kept over a {S._RATE_MAX_KEYS:,} cap"
    # Trimmed BELOW the cap, not exactly to it: landing on the cap means
    # the next arrival sweeps again, which is the per-request O(n) back.
    assert kept < S._RATE_MAX_KEYS, "no headroom — the next caller re-sweeps"


def test_the_limit_itself_is_still_exact():
    """All of the above is worthless if it stopped counting correctly."""
    import time
    import server as S
    now = time.time()
    S._RATE.clear()
    S._RATE_SWEPT_AT = now
    allowed = sum(1 for _ in range(320)
                  if S.rate_ok("read:one", 300, now))
    S._RATE.clear()
    assert allowed == 300, f"{allowed} got through a limit of 300"


def test_a_refused_request_does_not_extend_the_block():
    """A caller hammering while limited must not keep pushing their own
    window forward — that turns a one-minute cool-off into a permanent
    lockout for anyone who retries."""
    import server as S
    S._RATE.clear()
    S._RATE_SWEPT_AT = 1000.0
    for _ in range(300):
        S.rate_ok("read:x", 300, 1000.0)        # fills the budget at t=1000
    for _ in range(50):
        S.rate_ok("read:x", 300, 1030.0)        # refused, mid-window
    ok = S.rate_ok("read:x", 300, 1061.0)       # window has passed
    S._RATE.clear()
    assert ok, "the refused hits extended the window — this is a lockout"


def test_the_stripe_webhook_is_not_rate_limited():
    """It is authenticated by signature already, and a retry burst during
    an incident is exactly when dropping payment events costs most."""
    post = SERVER[SERVER.index("def do_POST("):]
    post = post[:post.index("\n    def ", 1)]
    i = post.index("_rate_limited")
    assert 'not parsed.path.startswith("/api/billing/webhook")' in post[:i]


def test_the_limiter_bounds_its_own_memory():
    """Otherwise it is the denial of service it was added to prevent."""
    i = SERVER.index("def rate_ok(")
    body = SERVER[i:SERVER.index("\n\n\n", i)]
    assert "len(_RATE) >" in body


# --- deployment --------------------------------------------------------------
def test_the_deploy_script_gates_on_the_suite():
    sh = _read("deploy", "deploy.sh")
    assert "run_tests.py" in sh
    i = sh.index("run_tests.py")
    assert "systemctl restart" not in sh[:i], \
        "it restarts before the tests have had their say"
    assert "TESTS FAILED" in sh
    # …and it proves the site answers rather than trusting the restart.
    assert "curl" in sh[sh.index("systemctl restart"):]


def test_the_deploy_script_backs_up_before_it_changes_anything():
    sh = _read("deploy", "deploy.sh")
    assert sh.index("backup.sh") < sh.index("git pull")


def test_the_backup_covers_what_cannot_be_rebuilt_and_skips_what_can():
    sh = _read("deploy", "backup.sh")
    assert "accounts.db" in sh and "ledger.db" in sh
    assert "history.db" in sh and "rebuilds from" in sh


def test_the_backup_does_not_need_a_package_that_is_not_installed():
    """Found by running it: the `sqlite3` CLI is a separate package and is
    not present by default. Python already is, and a backup that depends
    on something missing is missing on the day it is needed."""
    sh = _read("deploy", "backup.sh")
    assert "python3 -" in sh
    assert ".backup" in sh or "s.backup(d)" in sh
    for line in sh.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert not stripped.startswith("sqlite3 "), \
            f"shells out to the sqlite3 CLI: {stripped}"


def test_there_is_a_restore_drill_and_it_notices_staleness():
    """A backup nobody has restored is a hope."""
    sh = _read("deploy", "backup.sh")
    assert "--check" in sh
    assert "integrity_check" in sh
    assert "STALE" in sh


# --- the crash a static suite cannot see -------------------------------------
def test_the_prediction_desk_cache_is_declared_before_it_is_read():
    """WEATHER AND ALERTS BOTH CRASHED ON LOAD, and 4,414 passing tests
    said nothing.

    `let _railDeskCache` sat 5,000 lines BELOW the two renderers that read
    it. `let` is hoisted but stays in the temporal dead zone until its
    declaration line actually RUNS, so both pages threw "cannot access
    before initialization" and came up blank below the fold. The file
    parses perfectly; the fault only exists at runtime, in one execution
    order, on two pages nothing was opening.

    Pinned narrowly rather than as a general rule: a dozen other
    top-level bindings are referenced above their declaration and are
    perfectly fine, because the code that reads them runs later. A test
    that flagged all of them would be noise, and noise gets ignored."""
    app = _read("web", "js", "app.js")
    decl = app.index("let _railDeskCache")
    first_use = app.index("_railDeskCache ||")
    assert decl < first_use, \
        "the cache is declared after a reader again — Weather and Alerts crash"


def test_every_page_with_a_nav_entry_is_in_the_browser_sweep():
    """The reason that crash survived: Weather and Alerts were not in the
    launcher's sweep list, so nothing ever opened them. A page absent from
    that list is a page nobody looks at until a user does."""
    src = _read("launch.py")
    block = src[src.index('("MLB Recommended"'):src.index("]\n\n_SWEEP_JS")]
    for page in ("Weather", "Alerts", "Standings", "Rosters", "Live",
                 "About", "Terms", "Privacy"):
        assert f'("{page}"' in block, f"{page} is not swept"


def test_caddy_sends_the_same_csp_the_app_does():
    """In production Caddy serves index.html off disk, so the app's own
    headers never touch the one response that executes scripts.

    The Caddyfile's security block had every header EXCEPT the CSP, which
    meant the policy applied to `/api/*` JSON — where it does almost
    nothing — and not to the document. The page would have shipped with
    no CSP at all and nothing would have looked wrong.

    Duplicated headers drift, so this compares them character for
    character rather than checking that both merely exist.
    """
    import server as _srv
    caddy = _read("deploy", "Caddyfile")
    m = re.search(r'Content-Security-Policy\s+"([^"]+)"', caddy)
    assert m, "the Caddyfile serves the document with no CSP"
    assert m.group(1) == dict(_srv.SECURITY_HEADERS)["Content-Security-Policy"], \
        "the proxy's CSP and the app's have drifted apart"


def test_the_service_worker_is_not_cached_by_the_proxy():
    """The one file that can make every other file stale. A worker cached
    for a year keeps serving its own old shell, and the fix — shipping a
    new worker — is exactly what the cache stops from arriving."""
    caddy = _read("deploy", "Caddyfile")
    i = caddy.index("path /sw.js")
    assert "no-cache" in caddy[i:i + 200]


def test_the_shell_is_never_heuristically_cached():
    """index.html, app.js and styles.css carried NO Cache-Control, which
    hands the decision to browser heuristics — and iOS used them. After
    the 2026-08-17 navigation deploy, Ethan's phone kept its old app.js
    (heuristically "fresh") under the freshly-fetched index.html: the
    Library group ships folded in the markup and only the new JS can
    unfold it, so the button was dead and six pages were unreachable —
    "the library button doesnt work so we lost all of that information".

    no-cache = store but REVALIDATE: one conditional request, a 304 when
    nothing changed, a deploy live on the next open. The document is
    matched at / and /index.html — the app routes with the hash
    fragment, which never reaches the server, so / IS the document for
    every view."""
    caddy = _read("deploy", "Caddyfile")
    i = caddy.index("@shell")
    matcher = caddy[i:caddy.index("\n", i)]
    for path in ("/ ", "/index.html", "/js/*", "/css/*"):
        assert path in matcher + " ", f"{path.strip()} left the shell matcher"
    assert "no-cache" in caddy[i:i + 260], "the shell lost its revalidation rule"
    # And the worker version moved with the shell — its own header says
    # "Bump VERSION on any shell change", which two deploys skipped.
    assert 'const VERSION = "qb-v1"' not in _read("web", "sw.js"), \
        "the redesign shipped without a service-worker version bump"


def test_the_manifest_goes_out_as_a_manifest():
    """Caddy's MIME table does not know .webmanifest. Served as
    text/plain the install prompt never appears — no error, no console
    message, just no prompt, which is the hardest kind of bug to chase."""
    caddy = _read("deploy", "Caddyfile")
    assert "manifest.webmanifest" in caddy
    i = caddy.index("path /manifest.webmanifest")
    assert "application/manifest+json" in caddy[i:i + 200]


def test_the_sweep_judges_our_page_not_the_charts_we_embed():
    """A red nobody can fix is one people learn to ignore.

    Playwright reports console messages from EVERY frame, and Rocket
    Radar embeds a DexScreener chart that runs their code on their
    origin. Their analytics beacon fails CORS against their own API, and
    that arrived as "Rocket Radar ❌" on a page that was working — a
    permanent failure we have no way to fix, sitting next to the real
    ones and teaching you to skim past both.

    Filtered by the message's ORIGIN, and only for console messages.
    `pageerror` is never filtered: a thrown exception is ours by
    definition, and that is the channel the team-form crash came down.

    Verified by running the real _SWEEP_JS against a page with a
    deliberate console.error AND a deliberate throw, both from our own
    origin — both still reported. Silencing a check is worse than the
    noise it removes, so that direction is the one to test.
    """
    src = _read("launch.py")
    js = src[src.index("_SWEEP_JS = r\"\"\""):src.index("\ndef _browser_sweep")]
    assert "m.location()" in js, "console errors are not attributed to a frame"
    assert "127.0.0.1:${PORT}" in js, "the origin test does not name our own"
    # pageerror must stay unconditional.
    pe = js[js.index("p.on('pageerror'"):]
    pe = pe[:pe.index("\n")]
    assert "location" not in pe and "includes" not in pe, \
        "a thrown exception is being filtered by origin — it is always ours"


def test_the_server_does_not_announce_its_python_version():
    """The default `BaseHTTP/0.6 Python/3.11.15` hands an attacker the
    exact stack and patch level to look up CVEs against, for nothing in
    return."""
    assert "server_version = " in SERVER
    assert "sys_version = \"\"" in SERVER
    i = SERVER.index("server_version = ")
    assert "BaseHTTP" not in SERVER[i:i + 80]


def test_the_undocumented_feed_risk_is_called_out():
    """The finding most likely to be missed, because nothing breaks when
    you get it wrong — it just becomes somebody else's decision later."""
    assert "Undocumented endpoints" in PLAN
    assert "ESPN" in PLAN


def test_one_canonical_hostname_and_www_redirects_to_it():
    """Two hostnames serving the same site is a session bug, not a
    cosmetic one: a cookie set on www is not sent to the bare name, so
    signing in at one and then visiting the other looks like being
    silently signed out. It also hands search engines two copies of every
    page. Caddy issues certificates for both and then serves only one.

    308 rather than 302 — permanent, and it preserves the method, so a
    POST that lands on www is not quietly turned into a GET. `redir …
    permanent` is Caddy's spelling of 308.
    """
    caddy = _read("deploy", "Caddyfile")
    assert "\nqellysbook.com {" in caddy, "the canonical host is not served"
    assert "www.qellysbook.com {" in caddy, "www is not claimed at all"
    i = caddy.index("www.qellysbook.com {")
    block = caddy[i:i + 200]
    assert "redir" in block and "permanent" in block, \
        "www serves content instead of redirecting — sessions will split"
    assert "https://qellysbook.com" in block

    # The page must agree with the proxy about which name is canonical.
    html = _read("web", "index.html")
    assert 'rel="canonical" href="https://qellysbook.com/"' in html
    assert 'property="og:url" content="https://qellysbook.com/"' in html



def test_the_crash_loop_limits_are_in_the_section_systemd_reads():
    """A misplaced systemd key is ignored with a log line, not an error.

    `StartLimitBurst` and `StartLimitIntervalSec` belong to [Unit].  They
    sat in [Service], where systemd logs "Unknown key name … ignoring"
    once at load and carries on — so the file read as protected and was
    not.  Found on the first real deploy, in the journal, at the exact
    moment it mattered: the droplet's OOM killer took the process during
    its first cold build, and with the limit ignored `Restart=always`
    would have looped for ever instead of stopping at a visible failure.
    """
    unit = _read("deploy", "qellys.service")
    # Section headers only — anchored to line starts. Searching for the
    # bare text found "[Service]" inside the comment that explains this
    # very fix, which sits ABOVE the real header, so the [Unit] block came
    # out too short and the assertion failed on a correct file.
    u = re.search(r"^\[Unit\]$", unit, re.M).start()
    svc = re.search(r"^\[Service\]$", unit, re.M).start()
    assert u < svc
    unit_block, svc_block = unit[u:svc], unit[svc:]
    for key in ("StartLimitBurst", "StartLimitIntervalSec"):
        assert key in unit_block, f"{key} is not in [Unit] — systemd ignores it"
        assert key not in svc_block, f"{key} is in [Service], where it does nothing"


def test_the_service_names_itself_as_the_memory_victim():
    """Without a limit the kernel chooses what to kill when the box runs
    out, and it may not choose us. Naming ourselves means the app dies,
    systemd restarts it, and the journal says which unit — rather than
    something unrelated dying and the cause being a mystery."""
    unit = _read("deploy", "qellys.service")
    assert "MemoryMax=" in unit
    assert "MemoryAccounting=true" in unit


def test_the_deploy_notes_add_caddys_repository_before_installing_it():
    """`apt install caddy` alone fails on Ubuntu.

    Caddy is not in Ubuntu's archive, so the bare command answers "Unable
    to locate package caddy" — which reads like a typo and sends you
    looking for one. The install page's four lines (keyring, key, source
    list, update) have to come first, and the step is only correct if
    they come BEFORE the install in the file someone reads top to bottom.
    """
    readme = _read("deploy", "README.md")
    key = readme.index("caddy-stable-archive-keyring.gpg")
    src = readme.index("/etc/apt/sources.list.d/caddy-stable.list")
    install = readme.index("apt install -y caddy")
    assert key < install and src < install, \
        "the repository is added after the install that needs it"
    # And no earlier line may tell you to install it the way that fails.
    assert "apt install caddy\n" not in readme, \
        "a bare `apt install caddy` is still in the instructions"


def test_every_log_directory_the_caddyfile_writes_to_is_created_first():
    """Caddy cannot make its own log directory.

    The Caddyfile names `/var/log/caddy/qellys.log`. The package does not
    create that directory and the service runs as the unprivileged
    `caddy` user, so the reload dies with "permission denied" on the log
    file — which reads as a Caddy fault and is a mkdir. `caddy validate`
    does not catch it: it checks that the file parses, and it runs as
    root, where opening that path succeeds.

    Derived from the Caddyfile rather than hardcoded, so moving the log
    somewhere else fails here instead of on the box.
    """
    caddy = _read("deploy", "Caddyfile")
    readme = _read("deploy", "README.md")
    paths = re.findall(r"^\s*output file (\S+)", caddy, re.M)
    assert paths, "the Caddyfile logs nowhere — did the log block move?"
    for path in paths:
        d = path.rsplit("/", 1)[0]
        assert f"mkdir -p {d}" in readme, f"{d} is never created"
        # -R, because anything that ran as root already left a root-owned
        # LOG FILE in there, and appending to that fails with the same
        # error after a chown that looked like it had worked.
        assert f"chown -R caddy:caddy {d}" in readme, \
            f"{d} is chowned shallowly — a root-owned log file survives it"
        # And before the reload that needs it, not after.
        assert readme.index(f"mkdir -p {d}") < readme.index("systemctl reload caddy")


def test_validate_is_not_run_as_root():
    """`caddy validate` provisions the config, it does not merely parse
    it — and provisioning a log block OPENS the log file. Run under sudo
    that creates it owned by root, which is precisely the permission
    failure the mkdir/chown step exists to prevent: the check causes the
    fault it is too blind to report. As the caddy user it both tests the
    right identity and leaves the right owner behind."""
    readme = _read("deploy", "README.md")
    assert "sudo -u caddy caddy validate" in readme
    # COMMANDS ONLY. Searching the whole file found the string inside the
    # paragraph explaining this very fix — the third time a guard in this
    # repo has matched its own prose. The prose has to be free to name
    # the wrong command; only the fenced blocks are instructions.
    for block in _shell_blocks(readme):
        assert not re.search(r"^\s*sudo caddy validate", block, re.M), \
            "validate under sudo creates a root-owned log file"


def test_the_forwarded_header_overrides_survive_caddys_own_warning():
    """Caddy calls these unnecessary on every reload. They are not.

    `header_up X-Forwarded-For {remote_host}` REPLACES the header;
    Caddy's default appends to it, leaving whatever the client claimed in
    front of the real peer. Deleting these because the log says to would
    be a silent security regression, so the reason is pinned in both the
    file and the notes.
    """
    caddy = _read("deploy", "Caddyfile")
    assert "header_up X-Forwarded-For {remote_host}" in caddy, \
        "the override is gone — the app now trusts a client-supplied list"
    assert "Unnecessary header_up" in caddy, \
        "nothing in the file explains why Caddy's warning is wrong here"
    # And _client_ip must still be reading the end of the list.
    i = SERVER.index("def _client_ip(")
    body = SERVER[i:SERVER.index("\n    def ", i + 1)]
    assert "[-1]" in body, "_client_ip no longer takes the last entry"


def test_the_nightly_backup_writes_somewhere_the_app_user_can_write():
    """backup.sh defaults to ./backups, and on the server that is inside
    /srv/qellys — which the app user deliberately does not own (step 1,
    so a bug that writes a path cannot rewrite the code being executed).
    The nightly job would die at `mkdir`, as an unprivileged user, at
    4am, with the output going nowhere. Every failure mode of this step
    is silent, which is why it is pinned rather than trusted.
    """
    readme = _read("deploy", "README.md")
    sh = _read("deploy", "backup.sh")
    assert 'DEST="${QB_BACKUP_DIR:-$ROOT/backups}"' in sh, \
        "backup.sh no longer takes an override — the deploy step needs one"
    cron = [ln for b in _shell_blocks(readme) for ln in b.splitlines()
            if "backup.sh" in ln and "* * *" in ln]
    assert cron, "no nightly cron line for backup.sh"
    for ln in cron:
        assert "QB_BACKUP_DIR=" in ln, \
            "the cron line does not redirect the backup out of the checkout"
        assert "/srv/qellys/backups" not in ln, "still writing inside the repo"
        # Cron gets almost no environment; an export in the deploy shell
        # does not survive into it, so the variable must be on the line.
        assert ">>" in ln and "2>&1" in ln, \
            "cron mails the output instead, and this box has no mail server"


def test_a_backup_is_taken_before_the_restore_drill_checks_for_one():
    """--check restores the NEWEST backup and verifies it. Run first, it
    correctly reports "MISSING: no backup of accounts" — which reads as a
    broken script on the one night you are paying attention."""
    readme = _read("deploy", "README.md")
    body = "\n".join(_shell_blocks(readme))
    plain = re.search(r"^.*backup\.sh$", body, re.M)
    assert plain, "the drill is documented but a first backup is never taken"
    check = body.index("backup.sh --check")
    assert plain.start() < check, "--check runs before anything is backed up"


def test_swap_is_set_up_before_the_app_is_started():
    """Order is the whole content of this step.

    The first real deploy ran the cold build on a 1GB droplet with no
    swap: seven minutes of CPU, then the OOM killer, having never reached
    the bind. Swap after `systemctl enable --now` documents the fix in
    the wrong place — by then the failure has already happened and reads
    as the app being broken.
    """
    readme = _read("deploy", "README.md")
    swapon = readme.index("swapon /swapfile")
    start = readme.index("systemctl enable --now qellys")
    assert swapon < start, "swap is documented after the start it protects"
    assert "/etc/fstab" in readme, "swap would not survive a reboot"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
