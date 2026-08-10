"""Accounts — one name, every device, stored on Ethan's own machine.

Ethan, 2026-08-10: "Add an option to make an account so you can store
your fantasy info and your 'my bet' info. So you don't have to put in
that info every time."

The re-entry pain was localStorage being per-browser AND per-address:
the laptop at localhost, the phone at the LAN IP and a tailscale name
are three different origins — three empty copies — and iOS evicts a
site's storage after a week away. An account is a JSON file under
data/profiles/ on the machine already serving the site. No cloud, no
email, no third party, and STILL no sportsbook credentials anywhere.

Pinned here: the PIN is salted-hashed on disk and required once set;
sign-in with a typo'd name cannot silently create an account; the merge
can never lose a logged bet to a device race (union by signature) while
deletions still travel (tombstones) and a graded bet can never be
un-settled by a stale pending copy; last-writer-wins is STRICT so the
Sleeper error-path (which clears ff_user without re-stamping) cannot
erase the stored copy; and the browser's mbSig and the server's bet_sig
agree byte-for-byte — the tombstone contract is dead without that.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path

import server
from server import (profile_name_ok, profile_pin_ok, profile_get,
                    profile_sync, bet_sig, merge_sections)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = open(os.path.join(ROOT, "web/js/app.js"), encoding="utf-8").read()


def _tmpdir():
    d = Path(tempfile.mkdtemp())
    server.PROFILE_DIR = d
    return d


def _bet(desc="Yankees ML", stake=25, odds=-110, result="pending", **kw):
    b = {"date": "2026-08-10", "book": "DraftKings", "desc": desc,
         "stake": stake, "odds": odds, "result": result}
    b.update(kw)
    return b


def _mybets(rows, deleted=(), ts=0):
    return {"mybets": {"ts": ts, "data": {"rows": list(rows),
                                          "deleted": list(deleted)}}}


def test_names_and_pins_validate():
    assert profile_name_ok("ethan") and profile_name_ok("Ethan_12-3")
    for bad in ("", "e", "a" * 25, "no spaces", "slash/y", "../../etc", None, 7):
        assert not profile_name_ok(bad), bad
    assert profile_pin_ok("1234") and profile_pin_ok("123456789012")
    for bad in ("123", "1234567890123", "12a4", "", None):
        assert not profile_pin_ok(bad), bad


def test_create_get_roundtrip_and_wrong_pin():
    _tmpdir()
    code, out = profile_sync("Ethan", "1234",
                             {"fantasy": {"ts": 5, "data": {"user": "e"}}})
    assert code == 200 and out["has_pin"]
    assert out["name"] == "Ethan"          # display casing preserved
    code, out = profile_get("Ethan", "1234")
    assert code == 200 and out["sections"]["fantasy"]["data"]["user"] == "e"
    assert profile_get("Ethan", "9999")[0] == 403
    assert profile_get("Ethan", "")[0] == 403
    assert profile_sync("Ethan", "9999", {})[0] == 403


def test_signin_typo_cannot_create_an_account():
    """GET is the sign-in path and must be read-only: a typo'd name says
    'no account', it does not mint one and strand the real account."""
    d = _tmpdir()
    code, out = profile_get("ethann", "")
    assert code == 404 and "create" in out["error"]
    assert list(d.iterdir()) == []


def test_pin_is_salted_hashed_on_disk():
    d = _tmpdir()
    profile_sync("ethan", "4321", {})
    raw = (d / "ethan.json").read_text()
    assert "4321" not in raw
    stored = json.loads(raw)["pin"]
    assert set(stored) == {"salt", "hash"} and len(stored["hash"]) == 64


def test_lww_is_strict_so_an_error_cleared_client_cannot_erase():
    """The Sleeper catch path removes ff_user WITHOUT re-stamping, so
    that client keeps pushing an empty fantasy section under its old ts.
    Equal-stamp must lose — only a real (re-stamped) change wins."""
    stored = {"fantasy": {"ts": 100, "data": {"user": "ethan"}}}
    same_ts = merge_sections(stored, {"fantasy": {"ts": 100, "data": {"user": ""}}})
    assert same_ts["fantasy"]["data"]["user"] == "ethan"
    newer = merge_sections(stored, {"fantasy": {"ts": 101, "data": {"user": "new"}}})
    assert newer["fantasy"]["data"]["user"] == "new"


def test_mybets_union_never_loses_a_bet_to_a_device_race():
    """Laptop logs bet A, phone logs bet B; whoever syncs second must
    not clobber the first — a logged bet is the one thing a timestamp
    race may never eat. The reply's stamp is bumped past the pusher's
    own so the pusher adopts the union it is missing."""
    _tmpdir()
    profile_sync("ethan", "", _mybets([_bet("Yankees ML")], ts=50))
    code, out = profile_sync("ethan", "", _mybets([_bet("Judge Over 1.5 TB")], ts=60))
    rows = out["sections"]["mybets"]["data"]["rows"]
    assert {r["desc"] for r in rows} == {"Yankees ML", "Judge Over 1.5 TB"}
    assert out["sections"]["mybets"]["ts"] > 60    # pusher will adopt it


def test_deletions_travel_and_stay_dead():
    _tmpdir()
    bet = _bet("Fat finger parlay")
    profile_sync("ethan", "", _mybets([bet], ts=10))
    code, out = profile_sync("ethan", "",
                             _mybets([], deleted=[bet_sig(bet)], ts=20))
    assert out["sections"]["mybets"]["data"]["rows"] == []
    # A third device still holding the bet syncs it back up: still dead.
    code, out = profile_sync("ethan", "", _mybets([bet], ts=5))
    assert out["sections"]["mybets"]["data"]["rows"] == []


def test_a_graded_bet_is_never_unsettled_by_a_stale_pending_copy():
    _tmpdir()
    profile_sync("ethan", "", _mybets([_bet(result="win")], ts=10))
    code, out = profile_sync("ethan", "", _mybets([_bet(result="pending")], ts=20))
    rows = out["sections"]["mybets"]["data"]["rows"]
    assert len(rows) == 1 and rows[0]["result"] == "win"


def test_the_browser_and_server_compute_the_same_signature():
    """Tombstones are signatures the BROWSER computes and the SERVER
    matches against rows — one formatting disagreement (25 vs 25.0) and
    deletions silently stop working. Run the shipped mbSig under node
    against the server's bet_sig on awkward fixtures."""
    node = shutil.which("node")
    if not node:
        return
    fixtures = [_bet(), _bet(stake=25.5, odds=150), _bet(stake="10"),
                _bet(desc="  Padded, Comma  "), _bet(stake=0.5, odds=-105)]
    i = APP.index("function mbSig(")
    fn = APP[i:APP.index("\n}", i) + 2]
    script = fn + f"\nconsole.log(JSON.stringify({json.dumps(fixtures)}.map(mbSig)));"
    out = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [bet_sig(b) for b in fixtures]


def test_the_account_card_asks_for_no_password():
    """Same safety contract as My Bets itself: name + optional numeric
    PIN, nothing shaped like a credential to anything external."""
    i = APP.index("ACCOUNTS — one name, every device")
    block = APP[i:APP.index("Offseason panel", i)]
    assert 'type="password"' not in block.lower()
    assert 'inputmode="numeric"' in block
    assert "no sportsbook logins, ever" in block.lower()


def test_sync_talks_only_to_our_own_profile_endpoint():
    i = APP.index("ACCOUNTS — one name, every device")
    block = APP[i:APP.index("Offseason panel", i)]
    import re
    targets = re.findall(r'fetch\(\s*"([^"]+)"', block)
    assert targets and all(t == "/api/profile/" for t in targets), targets


def test_every_synced_surface_touches_the_account():
    """A section that changes without acctTouch never syncs — each
    write site is wired, so 'stored in your account' stays true."""
    assert 'acctTouch("mybets")' in APP.split("function mbSave", 1)[1][:300]
    assert APP.count('acctTouch("fantasy")') >= 4
    assert 'acctTouch("bankroll")' in APP
    # Deletions record a tombstone BEFORE the row disappears locally.
    i = APP.index("window.mbDelete")
    assert "mbSig(gone)" in APP[i:i + 700]


def test_adopting_a_server_copy_does_not_echo_back():
    """acctApplySection writes storage directly — through mbSave it
    would re-stamp and re-push, an echo loop between two open tabs."""
    i = APP.index("function acctApplySection")
    block = APP[i:APP.index("\nasync function acctSync", i)]
    assert "mbSave(" not in block
    assert "localStorage.setItem(MYBETS_KEY" in block


def test_the_heartbeat_respects_hidden_tabs():
    i = APP.index("ACCOUNTS — one name, every device")
    block = APP[i:APP.index("Offseason panel", i)]
    assert "document.hidden" in block


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
