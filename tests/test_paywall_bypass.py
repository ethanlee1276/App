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
import re
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
    arriving through the back door.

    PROVEN BY CRASHING IT, not by reading the source. The version this
    replaces asserted that the string "FULL_DIR.mkdir" appeared before
    the string "is public" inside publish(), and it broke on 2026-08-22
    when that local was renamed — the write order was never touched. A
    test that fails when you rename a variable is pinned to the spelling
    of the fix rather than to the thing being guaranteed.
    """
    import os as _os
    import tempfile
    from pathlib import Path
    from engine import gate as _gate

    restore = _env(QB_PAYWALL="1")
    real = _os.replace
    seen = []

    def crash(src, dst):
        seen.append(str(dst))
        if len(seen) == 2:                      # the public write
            raise RuntimeError("power cut between the two writes")
        return real(src, dst)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        public = root / "web" / "data" / "recommendations.json"
        public.parent.mkdir(parents=True)
        board = {"date": "x", "games": [1], "recommendations": [1, 2, 3]}
        _os.replace = crash
        try:
            try:
                _gate.publish(board, public, public.name)
            except RuntimeError:
                pass
            else:
                raise AssertionError("the fixture never crashed")
        finally:
            _os.replace = real
            restore()

        assert not public.exists(), (
            "the crash left a board on the PUBLIC path — and since the "
            "full copy is written first, that board is the full one")
        full = root / "data" / "built" / "recommendations.json"
        assert full.is_file(), "the private copy was not written first"
        assert len(json.loads(full.read_text())["recommendations"]) == 3


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


# --- the flag does not seal what is already written ----------------------------
# Found 2026-08-20 by running the real server with QB_PAYWALL=1 and curling
# the picks file: it returned all 293 recommendations. This is the gap
# between "the switch is on" and "the site is sealed", and it is the one
# that would have bitten on the day Ethan first turned it on.


def _boards(tmp, **files):
    import os
    os.makedirs(tmp, exist_ok=True)
    for name, doc in files.items():
        with open(os.path.join(tmp, name), "w") as fh:
            json.dump(doc, fh)
    return tmp


def test_turning_the_flag_on_does_not_touch_a_file_already_written():
    """The thing itself. `redact` runs inside `publish()`, so a board
    written while the paywall was off stays whole when it goes on. On the
    droplet a restart rebuilds most boards, which is exactly why nobody
    noticed: the site mostly seals itself by accident."""
    from engine import gate
    restore = _env(QB_PAYWALL="1")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _boards(tmp, **{"recommendations.json": dict(BOARD)})
            still = gate.unsealed(d)
            assert still and still[0]["rows"] >= 5, \
                "a board written before the flag went on reads as sealed"
    finally:
        restore()


def test_seal_strips_them_and_says_how_many():
    from engine import gate
    restore = _env(QB_PAYWALL="1")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _boards(tmp, **{"recommendations.json": dict(BOARD)})
            res = gate.seal(d, verbose=False)
            assert res["sealed"] and res["sealed"][0]["withheld"] == 5
            assert gate.unsealed(d) == []
            on_disk = json.loads(open(os.path.join(d, "recommendations.json")).read())
            for paid in ("recommendations", "game_bets", "long_shots"):
                assert not on_disk.get(paid)
            assert on_disk.get("games"), "the free half went too"
            assert on_disk.get("locked"), "nothing says what was withheld"
    finally:
        restore()


def test_sealing_twice_is_harmless():
    """It will be run by somebody who is not sure whether they ran it."""
    from engine import gate
    restore = _env(QB_PAYWALL="1")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _boards(tmp, **{"recommendations.json": dict(BOARD)})
            gate.seal(d, verbose=False)
            first = open(os.path.join(d, "recommendations.json")).read()
            again = gate.seal(d, verbose=False)
            assert again["sealed"] == [], "a sealed board was sealed again"
            assert open(os.path.join(d, "recommendations.json")).read() == first
    finally:
        restore()


def test_seal_never_overwrites_the_subscribers_full_copy():
    """THE FOOTGUN AN EARLIER CUT HAD. `publish()` writes its input to
    data/built/ as the FULL copy, so handing it an already-stripped board
    destroys the subscribers' data in the name of protecting it. Seal
    keeps an existing full copy untouched and only writes one when there
    is none."""
    from engine import gate
    src = _read("engine", "gate.py")
    body = src[src.index("def seal("):src.index("def unsealed(")]
    # BELOW THE DOCSTRING. seal's own docstring explains at length why it
    # does not call publish(), and a naive substring check fails on the
    # explanation rather than on the mistake — the fifth time that shape
    # has bitten a test today.
    code = body.split('"""')[2] if body.count('"""') >= 2 else body
    assert "if not full_path.is_file():" in code, \
        "seal overwrites data/built unconditionally"
    assert "publish(" not in code, \
        "seal republishes rather than stripping, so a stale private copy goes live"


def test_the_exposure_count_ignores_the_disclosure_block():
    """An hour lost to this on 2026-08-20. `locked` is a disclosure —
    "3 picks were withheld" — and `redact` copies it through like any
    other key, so counting a re-redaction made a correctly sealed board
    read as still leaking."""
    from engine import gate
    restore = _env(QB_PAYWALL="1")
    try:
        sealed = gate.redact(dict(BOARD), "recommendations.json")
        assert sealed.get("locked"), "fixture is not exercising the case"
        assert gate._paid_rows(sealed, "recommendations.json") == 0, \
            "a sealed board is counted as exposed because of its own locked block"
    finally:
        restore()


def test_todo_shouts_when_boards_are_still_public():
    """The switch and the seal are two steps, and the second is invisible.
    `--todo` is where Ethan looks, so it is where this has to appear."""
    src = _read("engine", "todo.py")
    assert "unsealed(" in src, "--todo cannot see an unsealed board"
    i = src.index("unsealed(")
    assert "--seal" in src[i:i + 900], "it reports the problem without the fix"


def test_seal_refuses_politely_when_the_paywall_is_off():
    from engine import gate
    restore = _env(QB_PAYWALL=None)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            d = _boards(tmp, **{"recommendations.json": dict(BOARD)})
            res = gate.seal(d, verbose=False)
            assert res.get("off") and not res["sealed"]
            on_disk = json.loads(open(os.path.join(d, "recommendations.json")).read())
            assert on_disk == BOARD, "it stripped a board on a free site"
    finally:
        restore()


# --- checkout ------------------------------------------------------------------
# Ethan sent a competitor's checkout as the render, 2026-08-20. The layout
# is his; the card fields are the part that must never be copied.


def test_no_card_field_is_ever_served_by_us():
    """THE RULE THIS PAGE EXISTS UNDER. In the render those fields look
    like part of the page and are not — the Link badge and the card box
    are the processor's iframe on the processor's origin. A card number
    typed into a field this repo serves puts us inside PCI scope, and this
    codebase's standing rule is that card details never touch this
    server. So the payment block is a SLOT."""
    app = _read("web", "js", "app.js")
    fn = app[app.index("function checkoutHTML("):]
    fn = fn[:fn.index("\nfunction renderCheckout(")]
    low = fn.lower()
    for bad in ("card number", "cardnumber", "cvc", "cvv", "expiry",
                "exp-month", "autocomplete=\"cc-", "type=\"tel\""):
        assert bad not in low, f"a card field appeared in our own markup: {bad!r}"
    # …AND THE PAGE HAS TO SAY WHOSE PAGE TAKES IT. This used to accept
    # "whoever the processor turns out to be", because there wasn't one.
    # There is now (Stripe, 2026-08-21), so the weaker wording is no
    # longer good enough: somebody about to be redirected off this site
    # to type a card should be told, on this page, where they are going.
    assert "Stripe" in fn, \
        "the payment block does not name the processor it hands off to"
    assert ("reaches this server" in fn or "never reach this server" in fn
            or "belongs to them" in fn), \
        "nothing tells the reader the card does not come here"


def test_a_code_covering_the_term_needs_no_processor_at_all():
    """The reason this page is worth having before the processor question
    is settled: a hundred percent off means there is nothing to charge.
    Verified in a browser — yearly went $225 to $0 with USFARATHANE and
    offered to open the site with no card."""
    app = _read("web", "js", "app.js")
    fn = app[app.index("function _coCovers("):]
    fn = fn[:fn.index("\n}")]
    assert "code.months >= plan.months" in fn, \
        "coverage is not compared against the term being bought"
    body = app[app.index("function checkoutHTML("):]
    body = body[:body.index("\nfunction renderCheckout(")]
    assert "Nothing to pay" in body and "coApplyFree" in body


def test_a_short_code_against_a_long_term_does_not_read_as_free():
    """A one-month code against a yearly plan does not cover it, and
    saying "free" there would be a promise the checkout cannot honour."""
    app = _read("web", "js", "app.js")
    body = app[app.index("function checkoutHTML("):]
    body = body[:body.index("\nfunction renderCheckout(")]
    assert "less than this term" in body, \
        "a partial code is presented as though it covered the whole plan"
    # The expression grew a second term when the 3-day trial landed:
    # `(covered || trial) ? 0 : pl.price`. The claim is unchanged — the
    # total is DERIVED from whether this reader owes anything today, not
    # asserted — so this checks the shape rather than one spelling of it.
    total = re.search(r"const total = ([^;]+);", body)
    assert total, "the total is no longer computed in checkoutHTML"
    assert "covered" in total.group(1), \
        "the total does not depend on whether the code actually covers it"
    assert "pl.price" in total.group(1), \
        "the total is not derived from the plan's price"
    # …and a code that does NOT cover the term must not zero it.
    assert "covered ?" in body or "covered ||" in body


def test_the_buy_button_is_the_loudest_thing_on_the_page():
    """`.btn primary` was invented — there is no such rule in the
    stylesheet — so the buy button rendered as a thin outline while
    .btn.ghost's panel fill made "back to plans" the loudest control on a
    checkout. Measured in a browser; the hierarchy was exactly inverted."""
    css = _read("web", "css", "styles.css")
    i = css.index(".pw-buy, .co-go {")
    rule = css[i:css.index("}", i)]
    assert "var(--brand-solid)" in rule, "the buy button has no fill of its own"
    j = css.index(".co-back {")
    back = css[j:css.index("}", j)]
    assert "background: none" in back, "the way out is still styled as a call to action"


def test_the_pages_open_behind_the_wall_have_a_way_back():
    """A DEAD END, found on a phone.

    `body.walled` hides the sidebar, the topbar and the tab bar. Two
    pages stay reachable behind it on purpose — Record, because it is the
    evidence the subscription is sold on, and Account, because somebody
    who has already paid has to be able to sign in. Landing on either
    left the reader with no navigation of any kind. Ethan: "there is no
    back button to get back to the paywall page, so you are just stuck
    there and have to close the app."

    Every exemption in the hash guard therefore owes the reader a way
    out. This checks the exemptions and the escape hatch against each
    other, so adding a third exempt page without one fails here.
    """
    app = _read("web", "js", "app.js")
    html = _read("web", "index.html")

    assert 'id="wall-back"' in html, "the escape hatch is gone from the page"
    assert 'href="#paywall"' in html, "it no longer points at the plans"

    # Shown by the ROUTER, which is the one place that knows the current
    # view — a page drawing its own would have to remember to.
    i = app.index('const back = document.getElementById("wall-back")')
    block = app[i:i + 420]
    assert 'classList.contains("walled")' in block, \
        "the back link is not gated on the wall being up"
    for hidden_on in ('"paywall"', '"checkout"'):
        assert hidden_on in block, \
            f"the back link shows on {hidden_on}, where it is nonsense"

    # AND THE TWO LISTS AGREE. WALL_OPEN names the pages that stay open;
    # the escape hatch has to cover all of them.
    #
    # It used to read the `want === "record"` comparisons out of the
    # hashchange guard, because that is where the exemptions lived. They
    # moved: the guard was losing a race against the router's deferred
    # view transition and let #recommended through, so the refusal is in
    # `_switchViewNow` now and the exemptions are a named list. See
    # tests/test_wall_routing.py.
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", app)
    assert m, "the wall no longer names its exemptions — this test is blind"
    exempt = set(re.findall(r'"([a-z]+)"', m.group(1)))
    # The wall itself, and the pages the back link reaches.
    #
    # "streak" added 2026-08-24: the free game is the acquisition funnel
    # (roadmap #4 — "builds your user base before the paywall flips on"),
    # so it stays open by design. The back link reaches it through the
    # same `name !== "paywall" && name !== "checkout"` branch this test
    # pins above — confirmed by rendering the page with the wall class
    # on: #wall-back is visible there like on Record.
    assert exempt <= {"paywall", "checkout", "record", "account", "discord",
                      "signup", "streak"}, (
        f"a new page is exempt from the wall: {exempt}. Confirm the back "
        "link reaches it, then add it here.")


def test_the_wall_does_not_bounce_a_reader_out_of_checkout():
    """This used to be spelled `state.view === "checkout"` inside the
    hashchange guard, and that read was the bug: `state.view` is set by
    the last COMPLETED view transition, and the router defers through
    `startViewTransition`, so during a hashchange it names the page being
    left. The exemption is a name in WALL_OPEN now, checked against the
    page being GONE TO, which is the thing the question was always about.
    """
    app = _read("web", "js", "app.js")
    m = re.search(r"const WALL_OPEN = \[([^\]]*)\]", app)
    assert m, "the wall no longer names its exemptions"
    exempt = set(re.findall(r'"([a-z]+)"', m.group(1)))
    assert "checkout" in exempt, \
        "changing the hash mid-purchase throws them back to the plans"
    assert "record" in exempt, \
        "the Record page is no longer exempt, and it is free by design"
    assert "account" in exempt, \
        "no way to sign in from the wall, which leaves it with no door"
    # And the refusal reads the DESTINATION, never the current view.
    #
    # This used to be spelled "no `state.view` appears before the
    # assignment", which is a proxy rather than the property — and on
    # 2026-08-23 it convicted an innocent read. `_switchViewNow` now
    # captures the view it is LEAVING, one line before that assignment, so
    # a detail page can hand the board back its scroll position on the way
    # out. That read is ABOUT the current view; it is the one kind that is
    # always correct. What must never happen is the WALL asking.
    body = app[app.index("function _switchViewNow("):]
    body = body[:body.index("\n}\n")]
    args = re.findall(r"wallBlocked\(([^)]*)\)", body)
    assert args, "nothing checks the wall on a view change"
    assert set(args) == {"name"}, (
        f"the wall is deciding from something other than the destination: "
        f"{sorted(set(args))}")
    # The only read of state.view before the assignment is the leaving
    # capture, and it is named so the next person does not have to guess.
    before = body[:body.index("state.view = name")]
    reads = [ln.strip() for ln in before.split("\n")
             if "state.view" in ln and not ln.strip().startswith("//")]
    assert reads == ["const leaving = state.view;"], (
        f"a new read of the current view crept in ahead of the switch: "
        f"{reads}")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
