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


def test_every_board_the_site_actually_builds_has_been_classified():
    """The list is only as good as its coverage. A new board added to the
    pipeline and forgotten here is gated by default — safe, but it should
    be a deliberate entry rather than an accident, and this is where that
    gets noticed."""
    built = sorted(p.name for p in (ROOT / "web" / "data").glob("*.json"))
    if not built:                      # a fresh checkout has none
        return
    known = set(gate.FREE_FILES) | set(gate.PAID_FILES)
    unclassified = [n for n in built if n not in known]
    # These are the mixed sport boards — free schedule, paid picks — and
    # they are handled by key rather than by name, so they belong to
    # neither list. Named here so a genuinely NEW file still shows up.
    mixed = {"recommendations.json", "mlb_recommendations.json", "nba.json",
             "wnba.json", "cfb.json", "ufc.json"}
    surprise = [n for n in unclassified if n not in mixed]
    assert not surprise, f"unclassified boards: {surprise}"


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
    src = _server()
    assert '/api/board/' in src, "nothing routes to the subscriber boards"
    body = src[src.index("def _api_board"):][:1800]
    assert "self._entitled(" in body
    assert "gate.full_board(" in body


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
    failure nobody notices is the product given away."""
    src = _server()
    body = src[src.index("def _entitled"):][:1400]
    tail = body[body.index("except Exception"):][:400]
    assert "return False" in tail, "an exception falls through to entitled"



if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
