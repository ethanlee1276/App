"""Every way somebody could read a paid board without paying, closed.

Ethan, 2026-08-20: *"we also have to make sure there is no way to bypass
this pay wall."*

THE ONE IDEA THIS RESTS ON. A paywall enforced by a check is only as good
as the number of places that remember to check. This one is not a check:
the file on the public path **is** the free version. `publish()` writes
the redacted copy to `web/data/` and the full copy to `data/built/`,
which is outside the web root and which the web server has no route to.
There is no full copy in the served tree to leak, so most of the bypasses
below cannot exist rather than being defended against.

The rest of this file walks the surface anyway, because "cannot exist" is
a claim and claims get stale. Each test names the attack.

    python3 tests/test_paywall_bypass.py
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


def _env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    def restore():
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return restore


BOARD = {
    "generated_at": "2026-08-20T12:00:00",
    "games": [{"id": "g1"}, {"id": "g2"}],
    "recommendations": [{"pick": "A"}, {"pick": "B"}, {"pick": "C"}],
    "game_bets": [{"pick": "D"}],
    "long_shots": [{"pick": "E"}],
}


# --- the attack that made this design ------------------------------------------
def test_curling_the_public_file_returns_no_picks():
    """`curl https://qellysbook.com/data/recommendations.json` is the first
    thing anybody tries, and the app never sees that request — the web
    server answers it off disk. So the answer has to already be free."""
    from engine import gate
    restore = _env(QB_PAYWALL="1")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pub = os.path.join(tmp, "recommendations.json")
            gate.publish(dict(BOARD), pub, "recommendations.json")
            on_disk = json.loads(open(pub).read())
        # THE KEY SURVIVES, THE ROWS DO NOT — and that is the design, not
        # a leak. `redact` empties a paid list rather than deleting it so
        # the page still parses and can render its own locked state; a
        # missing key would be a JSON shape the front end has never seen.
        # What matters is that no pick is readable.
        for paid in ("recommendations", "game_bets", "long_shots"):
            assert not on_disk.get(paid), \
                f"{paid} is readable on the public path: {on_disk.get(paid)!r}"
        blob = json.dumps(on_disk)
        for secret in ("\"A\"", "\"B\"", "\"C\"", "\"D\"", "\"E\""):
            assert secret not in blob, \
                f"a pick survived somewhere in the public payload: {secret}"
        # …and the free half is still there, or the gate broke the site.
        assert on_disk.get("games"), "tonight's slate went behind the paywall too"
        assert on_disk.get("locked"), "nothing tells the reader what was withheld"
    finally:
        restore()


def test_the_full_board_is_written_outside_the_web_root():
    """If FULL_DIR ever moved under web/, every protection here would be
    decoration and the file server would hand out the paid copy."""
    from engine import gate
    from pathlib import Path
    web = (Path(ROOT) / "web").resolve()
    assert not gate.FULL_DIR.resolve().is_relative_to(web), \
        f"the full board is inside the served tree: {gate.FULL_DIR}"


def test_the_full_copy_is_written_before_the_public_one():
    """A crash between the two writes must not leave the FULL board on the
    public path — the exact failure this module exists to prevent,
    arriving through the back door."""
    src = _read("engine", "gate.py")
    body = src[src.index("def publish("):]
    body = body[:body.index("\ndef ")]
    assert body.index("FULL_DIR.mkdir") < body.index("is public"), \
        "the public path may be written first"


# --- reaching for the private copy directly ------------------------------------
def test_the_board_api_refuses_a_path_that_climbs_out():
    """`/api/board/<name>` takes its name from the URL. A name that can
    walk up turns an entitlement check into an arbitrary file read."""
    from engine import gate
    for bad in ("../secrets.json", "..%2Fsecrets.json", "/etc/passwd",
                "sub/dir.json", ".hidden.json", "recommendations.json/../x.json",
                "", "recommendations.txt", "recommendations"):
        assert gate.full_board(bad) is None, f"accepted {bad!r}"


def test_the_static_server_cannot_be_walked_out_of_the_web_root():
    src = _read("server.py")
    body = src[src.index("def _static("):]
    body = body[:body.index("\n    def ")]
    assert "is_relative_to" in body and ".resolve()" in body, \
        "path traversal is not guarded on the static handler"


def test_the_board_api_checks_entitlement_before_it_answers():
    src = _read("server.py")
    body = src[src.index("def _api_board("):]
    body = body[:body.index("\n    def ")]
    assert body.index("_entitled(") < body.index("return self._send(200"), \
        "the payload is sent before anybody checks who is asking"
    assert "402" in body and "401" in body


# --- the client is not the thing deciding --------------------------------------
def test_the_wall_is_not_what_protects_anything():
    """The paywall VIEW is a shop. If it were the protection, editing one
    variable in a console would open the site. The comment saying so is
    load-bearing documentation and is checked, because the next person to
    touch this needs to know which half is the lock."""
    app = _read("web", "js", "app.js")
    i = app.index("THE PRICING WALL")
    head = app[i:i + 1800]
    assert "curl" in head and "gate.py" in head, \
        "nothing in the wall's own source says where the real protection is"


def test_the_client_asks_the_server_whether_it_is_walled():
    app = _read("web", "js", "app.js")
    fn = app[app.index("async function paywallCheck("):]
    fn = fn[:fn.index("\n}")]
    assert "/api/billing/status" in fn, \
        "the client decides for itself whether the wall is up"


def test_the_service_worker_never_caches_a_board():
    """An installed app holding yesterday's FULL board in a cache would be
    a copy of the paid product living on disk past the subscription."""
    sw = _read("web", "sw.js")
    fetch = sw[sw.index('addEventListener("fetch"'):]
    assert '"/data/"' in fetch and '"/api/"' in fetch
    assert fetch.index('"/data/"') < fetch.index("respondWith")


# --- the entitlement itself ----------------------------------------------------
def test_an_unknown_board_is_gated_not_published():
    """The failure directions are not symmetric: wrongly gating a free
    board is a visible annoyance, wrongly publishing a paid one gives the
    product away silently. A board nobody classified must land on the
    safe side."""
    from engine import gate
    assert not gate.is_free("something_nobody_listed.json")


def test_turning_the_flag_off_restores_the_old_site_exactly():
    """The switch has to be reversible in one step. If redaction leaked
    into the off path, a rollback would not be a rollback."""
    from engine import gate
    restore = _env(QB_PAYWALL=None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            pub = os.path.join(tmp, "recommendations.json")
            gate.publish(dict(BOARD), pub, "recommendations.json")
            on_disk = json.loads(open(pub).read())
        assert on_disk == BOARD, "the paywall being off is not a no-op"
    finally:
        restore()


def test_the_record_stays_free_on_purpose():
    """It is the evidence the subscription is sold on, and a proof nobody
    can read persuades nobody. This is a decision, not an oversight, so it
    is pinned as one."""
    from engine import gate
    assert gate.is_free("record.json")
    restore = _env(QB_PAYWALL="1")
    try:
        out = gate.redact({"overall": {"settled": 9}}, "record.json")
        assert out.get("overall"), "the record was redacted"
    finally:
        restore()


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
