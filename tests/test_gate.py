"""The paywall, and the bypass it exists to prevent.

Ethan, 2026-08-16: *"now we need to introduce the paywall for the site"* —
picks paid, the record free, $20 a month.

THE TEST THAT MATTERS MOST IS THE ONE ABOUT CURL. Caddy serves
`web/data/*.json` off disk, so the app never sees those requests and a
paywall written in JavaScript would be decorative: `curl
https://qellysbook.com/data/recommendations.json` would return the whole
board. The design answer is not a better check, it is that the full board
is never written to the public path at all — so the tests below are mostly
about WHERE bytes end up rather than about who is allowed to read them.

A gate that can be reasoned about beats one that has to be defended.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gate                                      # noqa: E402

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(**kw):
    """Set env vars and give back a restore callable."""
    was = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    def restore():
        for k, v in was.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


def _board() -> dict:
    """A mixed board: free schedule and paid picks in one object, which is
    the shape that ruled out gating whole files."""
    return {
        "date": "2026-08-16",
        "sport": "nfl",
        "games": [{"home": "DET", "away": "GB"}, {"home": "KC", "away": "BUF"}],
        "playoff_picture": {"DET": 0.61},
        "recommendations": [{"pick": "a"}, {"pick": "b"}, {"pick": "c"}],
        "game_bets": [{"pick": "d"}],
        "long_shots": [],
        "market_scan": [{"arb": 1}],
    }


def test_the_free_half_of_a_mixed_board_survives_redaction():
    """Gating the file would take tonight's slate down with the picks."""
    red = gate.redact(_board(), "recommendations.json")
    assert red["games"] == _board()["games"]
    assert red["playoff_picture"] == {"DET": 0.61}
    assert red["date"] == "2026-08-16"


def test_every_paid_field_is_emptied_and_none_of_its_content_survives():
    """The whole point. A field that is merely flagged rather than emptied
    is still in the JSON, and the JSON is the product."""
    red = gate.redact(_board(), "recommendations.json")
    blob = json.dumps(red)
    for leaked in ("\"a\"", "\"b\"", "\"c\"", "\"d\"", "arb"):
        assert leaked not in blob, f"{leaked} survived redaction"
    for key in ("recommendations", "game_bets", "market_scan"):
        assert red[key] == [], f"{key} still carries rows"


def test_a_locked_board_says_how_much_is_behind_it():
    """"No picks tonight" when there are three is a lie, and an empty
    board is a worse advertisement than a locked one."""
    red = gate.redact(_board(), "recommendations.json")
    assert red["locked"] == {"recommendations": 3, "game_bets": 1,
                             "market_scan": 1}
    assert red["locked_reason"] == "subscription"
    # An EMPTY paid field is not "locked" — zero picks is a true statement
    # about the slate, not a paywall, and claiming otherwise oversells.
    assert "long_shots" not in red["locked"]


def test_a_board_with_no_picks_at_all_is_not_advertised_as_locked():
    quiet = {"date": "2026-08-16", "games": [], "recommendations": []}
    red = gate.redact(quiet, "recommendations.json")
    assert "locked" not in red and "locked_reason" not in red


def test_the_record_is_never_redacted():
    """It is the evidence the subscription is sold on. A proof nobody can
    read persuades nobody."""
    rec = {"overall": {"units": 12.4}, "recommendations": [{"x": 1}],
           "curve": [1, 2, 3]}
    assert gate.redact(rec, "record.json") == rec
    assert gate.is_free("record.json")
    # …even reached by a path rather than a bare name.
    assert gate.is_free("web/data/record.json")


def test_an_unknown_board_is_gated_rather_than_published():
    """The failure directions are not symmetric. Wrongly gating a free
    board is a visible annoyance somebody reports in an hour; wrongly
    publishing a paid one gives the product away and nobody mentions it."""
    assert not gate.is_free("something_new.json")
    red = gate.redact({"recommendations": [1, 2]}, "something_new.json")
    assert red["recommendations"] == []


def test_redact_does_not_mutate_the_board_it_was_given():
    """The caller keeps the full copy to write for subscribers. A function
    that edited its argument would poison exactly that copy, and the
    symptom would be subscribers seeing the free board."""
    full = _board()
    gate.redact(full, "recommendations.json")
    assert len(full["recommendations"]) == 3, "the full board was emptied"


def test_publish_writes_the_full_board_outside_the_web_root():
    """The load-bearing fact. If the full copy is anywhere under web/,
    Caddy serves it and everything else here is decoration."""
    # WITH THE PAYWALL ON — the flag was added after this test and the
    # behaviour it describes is the switched-on one. Off, the public file
    # is deliberately the full board; that case has its own test below.
    restore = _env(QB_PAYWALL="1")
    with tempfile.TemporaryDirectory() as tmp:
        pub = Path(tmp) / "web" / "data" / "recommendations.json"
        was = gate.FULL_DIR
        gate.FULL_DIR = Path(tmp) / "data" / "built"
        try:
            public, full = gate.publish(_board(), pub, "recommendations.json")
            assert "web" not in Path(full).parts, \
                "the full board was written inside the web root"
            on_disk = json.loads(Path(public).read_text())
            assert on_disk["recommendations"] == [], \
                "the PUBLIC file has the picks in it — curl would get them"
            assert len(json.loads(Path(full).read_text())["recommendations"]) == 3
        finally:
            gate.FULL_DIR = was
            restore()


def test_no_built_board_directory_is_reachable_from_the_web_root():
    """Belt and braces against the same mistake arriving by symlink or by
    somebody moving FULL_DIR later."""
    web = (ROOT / "web").resolve()
    assert web not in gate.FULL_DIR.resolve().parents
    assert gate.FULL_DIR.resolve() != web


def test_a_board_name_from_a_url_cannot_climb_out_of_the_directory():
    """`full_board` takes its argument from a request path. A name that
    can traverse turns an entitlement check into an arbitrary file read,
    and `secrets.local` is two directories up."""
    for evil in ("../secrets.local", "../../etc/passwd", "/etc/passwd",
                 "a/b.json", "..%2Frecord.json", ".hidden.json", "",
                 "../data/accounts.db"):
        assert gate.full_board(evil) is None, f"{evil!r} was not refused"


def test_a_wholly_paid_board_still_parses_as_a_board():
    """A page that cannot parse its own data shows a crash, not a
    subscribe button."""
    red = gate.redact({"generated_at": "x", "sport": "nfl",
                       "futures": [1, 2, 3]}, "futures_nfl.json")
    assert red["locked_reason"] == "subscription"
    assert red["locked"]["whole_board"] >= 1
    assert red["sport"] == "nfl", "the shell the page needs is gone"


def test_the_paid_and_free_lists_do_not_overlap():
    """A file in both lists resolves by whichever check runs first, which
    is a coin toss decided by line order."""
    assert not (set(gate.PAID_FILES) & set(gate.FREE_FILES))


def test_every_board_the_site_can_build_has_been_classified():
    """Read from the registry, NOT from web/data/*.json.

    The glob version passed here and failed on the droplet: this container
    had never built nfl_preseason.json or predmarkets.json, so the check
    silently covered 28 boards instead of 30. A test whose coverage
    depends on which files a machine happens to have is a test that is
    strongest where it is least needed. Second time this session — the
    other was a 42-view sweep that passed because the dev board had no
    team_form to crash on.
    """
    classified = (set(gate.FREE_FILES) | set(gate.PAID_FILES)
                  | set(gate.MIXED_FILES))
    missing = sorted(set(gate.KNOWN_BOARDS) - classified)
    assert not missing, f"unclassified boards: {missing}"
    stray = sorted(classified - set(gate.KNOWN_BOARDS))
    assert not stray, f"classified but not in KNOWN_BOARDS: {stray}"


def test_a_board_this_machine_has_built_is_one_the_registry_knows():
    """The other direction: a file on disk that the registry has never
    heard of is a pipeline that grew a board without telling the gate."""
    built = sorted(p.name for p in (ROOT / "web" / "data").glob("*.json"))
    unknown = [n for n in built if n not in gate.KNOWN_BOARDS]
    assert not unknown, f"built but unregistered: {unknown}"


def test_the_preseason_fixture_list_is_free():
    """board_payload() calls itself "Facts only — no price", and refuses to
    put a number on a starter who plays a series and a half. Charging for
    a board that is structurally priceless would make that refusal read as
    a paywall."""
    assert gate.is_free("nfl_preseason.json")
    board = {"weeks": [{"week": 1, "games": [{"home": "DET"}]}], "total": 49}
    assert gate.redact(board, "nfl_preseason.json") == board


# --- the switch, and why it is off ------------------------------------------

def test_the_paywall_is_off_unless_somebody_turns_it_on():
    """Wired live in one step, this would have gone dark the moment it
    deployed — for everybody including Ethan, because there is no Paddle
    account yet and so no account that CAN be entitled. Off by default is
    what let it be built while the site is live and free."""
    restore = _env(QB_PAYWALL=None)
    try:
        assert not gate.enabled()
    finally:
        restore()


def test_with_the_paywall_off_the_public_file_is_unchanged():
    """The safety property of the flag: nothing about the live site moves
    until the day it is switched on."""
    restore = _env(QB_PAYWALL=None)
    with tempfile.TemporaryDirectory() as tmp:
        was = gate.FULL_DIR
        gate.FULL_DIR = Path(tmp) / "built"
        try:
            pub = Path(tmp) / "web" / "data" / "recommendations.json"
            public, full = gate.publish(_board(), pub, "recommendations.json")
            on_disk = json.loads(Path(public).read_text())
            assert len(on_disk["recommendations"]) == 3, \
                "the public board was redacted with the paywall off"
            # …and the subscriber copy is written anyway, so switching the
            # flag on needs no rebuild.
            assert len(json.loads(Path(full).read_text())["recommendations"]) == 3
        finally:
            gate.FULL_DIR = was
            restore()


def test_with_the_paywall_on_the_public_file_loses_the_picks():
    restore = _env(QB_PAYWALL="1")
    with tempfile.TemporaryDirectory() as tmp:
        was = gate.FULL_DIR
        gate.FULL_DIR = Path(tmp) / "built"
        try:
            pub = Path(tmp) / "web" / "data" / "recommendations.json"
            public, full = gate.publish(_board(), pub, "recommendations.json")
            assert json.loads(Path(public).read_text())["recommendations"] == []
            assert len(json.loads(Path(full).read_text())["recommendations"]) == 3
        finally:
            gate.FULL_DIR = was
            restore()


def test_a_comp_list_exists_so_the_owner_is_not_locked_out():
    """Without it the only route to an entitled account is a completed
    Paddle checkout — which means Ethan cannot see his own board, cannot
    comp a tester, and cannot honour a refund without going through the
    processor and waiting. Read from the environment, never the database,
    so nothing reachable from the web can grant it."""
    restore = _env(QB_COMP_EMAILS=" Ethan@Example.com , tester@x.io ")
    try:
        assert gate.comped("ethan@example.com"), "case-folding is required"
        assert gate.comped("  TESTER@X.IO  ")
        assert not gate.comped("stranger@x.io")
        assert not gate.comped("") and not gate.comped(None)
    finally:
        restore()
    # An unset list grants nothing at all.
    restore = _env(QB_COMP_EMAILS=None)
    try:
        assert not gate.comped("ethan@example.com")
    finally:
        restore()


def test_an_empty_comp_list_does_not_entitle_everyone():
    """`"".split(",")` is `[""]`, and a membership test against a set
    holding the empty string would match an empty email. The filter that
    prevents it is one `if e.strip()`."""
    restore = _env(QB_COMP_EMAILS=",, ,")
    try:
        assert not gate.comped("anybody@example.com")
        assert not gate.comped(" ")
    finally:
        restore()


# --- the server half --------------------------------------------------------

def _server() -> str:
    return open(os.path.join(ROOT, "server.py"), encoding="utf-8").read()


def test_the_board_endpoint_checks_entitlement_before_it_reads():
    """THE ORDER, which is what the name has always claimed and what the
    code did not do until 2026-08-22: it read and parsed the whole board
    — a megabyte — and then asked who was calling. Nothing was ever sent
    to the wrong person, but refusing a stranger was the most expensive
    request on the site.

    Asserted as positions rather than by naming the reader function: the
    read went through `gate.full_board` and now goes through the byte
    cache in server.py, and this test is about neither of those."""
    src = _server()
    assert '/api/board/' in src, "nothing routes to the subscriber boards"
    body = src[src.index("def _api_board"):]
    body = body[:body.index("\n    def ", 1)]
    assert "self._entitled(" in body, "the entitlement check is gone"
    reads = min(i for i in (body.find("board_bytes("),
                            body.find("gate.full_board(")) if i > 0)
    assert body.index("self._entitled(") < reads, \
        "the board is read from disk before the caller is identified"
    assert body.index("self._entitled(") < body.index("self._send(200"), \
        "the board is SENT before entitlement is decided"


def test_the_page_s_own_board_endpoint_serves_a_subscriber_their_picks():
    """THE BUG THIS FILE ALMOST MISSED, proved 2026-08-22 against a
    running server with a signed-in comped account.

    `gate.py` has said since it was written that "subscribers get the
    full board from /api/board/<name>". Nothing in web/js/app.js has ever
    called that endpoint — the page fetches SPORT_META.api, which is
    /api/<sport>/recommendations, and that served `web/data/<board>.json`
    to everybody. With the paywall on, that file IS the redacted copy.

    So a paying subscriber's page fetched a board with
    `recommendations: []` and drew "No qualifying plays at current
    numbers" — which reads as the model finding nothing, not as the
    paywall taking it away. `live_picks` is not a paid key, so their
    riding bets still showed underneath, which is exactly the screenshot
    that was being read as an empty slate.

    Every test here checked the paid file could not LEAK. None checked it
    still ARRIVED.
    """
    src = _server()
    body = src[src.index("def _serve_board("):]
    body = body[:body.index("\n    def ", 1)]
    assert "gate.enabled()" in body, "the flag decides nothing here"
    assert "self._entitled(" in body, "no entitlement check on the page's board"
    assert "board_bytes(" in body, "an entitled caller is not given the full copy"
    # And the unentitled path must still be the redacted public file.
    assert "file_bytes(public)" in body, \
        "the redacted copy is no longer the fallback"
    # The check must gate the FULL copy, not run after it.
    assert body.index("self._entitled(") < body.index("board_bytes("), \
        "the full board is read before the caller is identified"


def test_the_live_endpoint_is_the_one_the_page_actually_calls():
    """A fix on an endpoint nobody calls is the shape of the original
    bug. SPORT_META.api is what load() fetches; that is what has to be
    entitlement-aware."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("const tag = _boardTags[")
    assert "meta.api" in app[i:i + 400], "load() no longer fetches meta.api"
    src = _server()
    live = src[src.index("def _api(self, query"):]
    live = live[:live.index("\n    def ", 1)]
    assert "_serve_board(" in live, \
        "the endpoint the page calls went back to serving one file to all"


def test_ufcs_picks_are_gated():
    """LIVE ON 2026-08-22, with QB_PAYWALL=1 on the box.
    engine/ufc/model.py returns its board under `picks`, `pass_list` and
    `near_misses`. No entry in PAID_KEYS matched any of them, so
    `curl /data/ufc.json` handed every fighter, price and stake to
    anybody who asked — the paid product, on the open path, for as long
    as the paywall had been on.

    Nothing caught it. Every test in this file asked whether a NAMED key
    survived redaction; none asked whether an unnamed one did."""
    from engine import gate
    mark = "UFC_PICK_MARK"
    board = {"status": "card", "event_date": "2026-08-23",
             "weighins": [{"fighter": "free fact"}],
             "picks": [{"fighter": mark, "odds": -140, "stake_units": 0.6}],
             "pass_list": [{"fighter": mark}],
             "near_misses": [{"fighter": mark}]}
    out = gate.redact(board, "ufc.json")
    assert mark not in json.dumps(out), "the UFC card is public again"
    # And the free half of that board must survive — the card, the date
    # and the weigh-ins are facts, and sealing them would make the page
    # useless to the visitor it is meant to attract.
    assert out.get("event_date") == "2026-08-23"
    assert out.get("weighins"), "the free facts went with the picks"


def test_a_staked_row_under_any_key_is_reported():
    """The general form. Key-stripping only protects boards whose keys
    somebody anticipated, and the next board will name its rows something
    else again — so this asks a question that does not depend on the
    name: does the list carry a STAKE?"""
    from engine import gate
    hole = {"whatever_we_call_it_next": [{"who": "x", "stake_units": 0.5}]}
    assert gate.leaks(hole, "ufc.json") == ["whatever_we_call_it_next"]
    # A gated key is not a leak, a free file is a decision, and a list
    # with no stake on it is not a pick list.
    assert gate.leaks({"recommendations": [{"stake_units": 1}]}, "ufc.json") == []
    assert gate.leaks(hole, "record.json") == []
    assert gate.leaks({"games": [{"home": "TOR"}]}, "ufc.json") == []


def test_the_audit_is_runnable_on_the_box():
    """A guard that only runs in CI does not protect a board added on the
    server. `--paywall-audit` reads the real public path."""
    src = _read("launch.py") if "_read" in dir() else open(
        os.path.join(ROOT, "launch.py"), encoding="utf-8").read()
    body = src[src.index("def _paywall_audit_cli("):]
    body = body[:body.index("\ndef ", 1)]
    assert "gate.leaks(" in body or "_gate.leaks(" in body
    assert '"web" / "data"' in body, "it audits somewhere other than the public path"


def test_every_wholly_paid_file_has_an_entitled_path_to_it():
    """THE SWEEP THE LAST BUG EARNED. `/api/<sport>/recommendations`
    serving the redacted board to subscribers was found by asking whether
    paid content ARRIVES, not whether it leaks — and the same question
    has the same answer for every file in PAID_FILES.

    Those are sealed in their entirety on the public path: Caddy hands
    out a stub with `locked_reason` and no content. So a page fetching
    one from `data/` gives a paying subscriber the same empty shell it
    gives a stranger. That was live on the Record page's
    prediction-market section, the Lab and the Kalshi board.

    Checked against gate.PAID_FILES rather than a list here, so a file
    added to that tuple cannot quietly skip this."""
    import re
    from engine import gate
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    code = re.sub(r"/\*.*?\*/", " ", app, flags=re.S)
    offenders = []
    for name in gate.PAID_FILES:
        stem = name.split(".")[0]
        # A template literal covers futures_${sport}.json.
        for m in re.finditer(r"boardFetch\(\s*[`\"]data/([^`\"]+)", code):
            got = m.group(1)
            if stem.split("_")[0] in got:
                offenders.append(f"{name} fetched directly as data/{got}")
    assert not offenders, (
        "a paid file is fetched from the public path, where it is sealed "
        "for everyone including subscribers: " + "; ".join(offenders))


def test_the_paid_fetch_helper_tries_the_entitled_endpoint_first():
    """One helper, because there were four of these and a fifth will be
    written by somebody who did not read the comment."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    i = app.index("async function paidFetch(")
    fn = app[i:app.index("\n}", i) + 2]
    assert '"/api/board/" + name' in fn, "it does not ask the entitled endpoint"
    assert "data/${name}" in fn, "no static fallback for a signed-out reader"
    assert fn.index("/api/board/") < fn.index("data/${name}"), \
        "the sealed copy is tried first, so a subscriber never sees the real one"


def test_the_prediction_market_record_asks_the_entitled_endpoint():
    """predmarkets.json is in PAID_FILES, so the copy on the public path
    is a locked stub with no `validation` key. The Record page read that
    stub and drew nothing."""
    app = open(os.path.join(ROOT, "web", "js", "app.js"), encoding="utf-8").read()
    # The record page goes through the shared helper now — the entitled
    # endpoint and the fallback both live there, which is what
    # test_the_paid_fetch_helper_tries_the_entitled_endpoint_first pins.
    i = app.index("async function renderRecord")
    body = app[i:app.index("\nasync function ", i + 10)]
    assert 'paidFetch("predmarkets.json")' in body, \
        "the record page still reads the sealed public copy directly"


def test_the_flag_is_checked_before_the_account_is():
    """Ordering, not style. A site running without a processor must behave
    exactly as it did before any of this was written — refusing everyone
    because nobody has subscribed yet is the failure this avoids."""
    src = _server()
    body = src[src.index("def _entitled"):][:1400]
    i, j = body.index("gate.enabled()"), body.index("if not who")
    assert i < j, "the account is consulted before the switch"


def test_a_signed_in_visitor_without_a_subscription_gets_402_not_403():
    """"Pay and this works" and "you may never have this" are different
    answers, and the page renders a different thing for each."""
    src = _server()
    body = src[src.index("def _api_board"):][:1800]
    assert "402" in body and "401" in body


def test_a_broken_billing_lookup_does_not_become_a_free_read():
    """The failure everybody notices is a paying customer refused. The
    failure nobody notices is the product given away.

    ANCHORED ON THE BILLING CALL, not on the first `except` in the
    function — the redemption-code lookup was added ahead of it on
    2026-08-20 and has its own, deliberately different, handler. Anchoring
    by position made this test about whichever guard happened to be first,
    which is not the property it exists to defend.
    """
    src = _server()
    body = src[src.index("def _entitled"):][:2200]
    tail = body[body.index("BI.status_for"):]
    tail = tail[tail.index("except Exception"):][:400]
    assert "return False" in tail, "an exception falls through to entitled"


def test_a_broken_code_lookup_costs_a_code_holder_not_a_subscriber():
    """The redemption guard is deliberately NOT fail-closed, and the
    asymmetry is the point. Codes are checked before the processor; if
    that lookup throws and it returned False there, a paying subscriber
    would lose their board over a failure in a feature they never used.
    It falls through to the billing check instead, which still fails
    closed — so the composite is closed and the blast radius of a broken
    code table is code holders alone."""
    src = _server()
    body = src[src.index("def _entitled"):][:2200]
    head = body[body.index("RD.init("):body.index("BI.status_for")]
    guard = head[head.index("except Exception"):]
    assert "return True" not in guard, \
        "a broken code lookup grants access — that is fail-OPEN"
    assert "pass" in guard, \
        "it no longer falls through to the billing check"



# --- the builds actually go through it --------------------------------------

#: Every script that writes a board carrying picks. A gated module nothing
#: calls is the most reassuring kind of dead code.
GATED_BUILDS = ("nfl_build.py", "mlb_build.py", "nba_build.py",
                "cfb_build.py", "ufc_build.py", "futures_build.py",
                "generate.py", "generate_mlb.py", "pm_build.py")


def test_every_build_that_writes_picks_publishes_through_the_gate():
    """The wiring is the whole feature. redact() can be perfect while a
    build writes the full board straight to web/data/ beside it, and the
    symptom is nothing at all — the site looks right and the picks are
    public."""
    for name in GATED_BUILDS:
        src = (ROOT / name).read_text(encoding="utf-8")
        assert "gate.publish(" in src, f"{name} never calls gate.publish"


def test_no_gated_build_still_writes_its_board_the_old_way():
    """A leftover direct write is a second door. Checked as code rather
    than as text so the comments explaining this may quote it."""
    import re as _re
    for name in GATED_BUILDS:
        src = (ROOT / name).read_text(encoding="utf-8")
        code = "\n".join(ln for ln in src.splitlines()
                          if not ln.lstrip().startswith("#"))
        # The two idioms this repo used before the gate existed.
        for pattern in (r"out_path\.write_text\(json\.dumps\(result",
                        r"\bp\.write_text\(json\.dumps\(out\b",
                        r"json\.dump\(result, fh"):
            assert not _re.search(pattern, code), \
                f"{name} still writes its board directly ({pattern})"


def test_the_polymarket_board_is_gated_under_both_of_its_names():
    """pm_build's default --out is predmarkets.json; the file on disk is
    kalshi.json. Same board, two names, and only one was listed. Its picks
    live in `rows`, which no PAID_KEY matches — so the unlisted name would
    have published whole. Key-stripping only protects boards whose keys
    were anticipated; the named list is the net under that."""
    for name in ("kalshi.json", "predmarkets.json"):
        assert gate.is_wholly_paid(name), f"{name} is not gated"
        red = gate.redact({"generated_at": "x", "rows": [1, 2, 3]}, name)
        assert "rows" not in red, f"{name} still carries its picks"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
