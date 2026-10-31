"""Juice Reel → Zeno's Record, without Ethan lifting a finger.

Ethan, 2026-09-21: *"can we make a way to sync my juice reel to the site
so all my bets will automatically sync."*

Juice Reel's API docs say every bets endpoint takes *"Owner only: Client
ID + secret"*, so for the account that owns the app the two keys are the
whole credential — no browser flow. `engine/juicereel.py` reads
`/oauth2/bets/changed` the way the docs describe reconciliation, and
every test here runs against the SAMPLE BET THOSE DOCS PUBLISH, verbatim,
so the mapping is tested against their shape and not my memory of it.

Run directly:
`python3 tests/test_juice_reel_syncs_zenos_record.py`
"""

import copy
import json
import os
import re
import sys
import tempfile
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QB_FEEDSTATE_DIR", tempfile.mkdtemp())
os.environ.setdefault("QB_MODELS_DIR", tempfile.mkdtemp())

from engine import juicereel as jr                            # noqa: E402
from engine import zeno                                       # noqa: E402

#: The docs' own sample, verbatim (juicereel.com/api-docs, "List settled
#: bets", 200 response). A NoVig moneyline on the Mets, lost.
SAMPLE = json.loads("""
{"id": 9531, "userId": 4, "oddsAmerican": 114, "amountRisked": 0.5886,
 "toWin": 0.6714, "netResult": -0.5886, "result": "Lost",
 "datePlaced": "2026-08-11T13:32:26.434Z", "dateClosed": "2026-08-11T23:15:00.000Z",
 "isAdjustedOdds": false, "isAdjustedLine": false, "adjustedRisk": null,
 "clvPct": null, "createdAt": "2026-08-26T20:35:17.972Z",
 "updatedAt": "2026-08-26T20:35:17.972Z", "currencyCode": "USD",
 "BetType": {"id": 1, "typeName": "Straight"},
 "BetStatus": {"id": 2, "statusName": "Closed"},
 "Site": {"id": 1589, "name": "NoVig"},
 "Subbets": [{"id": 13345, "userId": 4, "subbetType": "Moneyline",
   "position": "New York Mets", "value": 0, "oddsAmerican": 114,
   "duration": null, "startDate": "2026-08-11T23:15:00.000Z", "wasLiveBet": false,
   "description": "Atlanta Braves vs New York Mets - NYM",
   "scrapeDescription": "MLB | Atlanta Braves vs New York Mets | MONEY | NYM",
   "metric": null,
   "TruthTeam": {"id": 1020, "name": "New York Mets", "displayName": "New York Mets"},
   "OppTruthTeam": {"id": 1003, "name": "Atlanta Braves", "displayName": "Atlanta Braves"},
   "Player": null, "OppPlayer": null,
   "Event": {"id": 428, "name": null, "startDate": "2026-08-11T23:15:00.000Z",
     "type": "Game", "homeTeamId": 1003, "awayTeamId": 1020, "status": "Scheduled",
     "sportId": 1, "leagueId": 2,
     "HomeTeam": {"id": 1003, "name": "Atlanta Braves", "displayName": "Atlanta Braves"},
     "AwayTeam": {"id": 1020, "name": "New York Mets", "displayName": "New York Mets"},
     "Sport": {"id": 1, "name": "Baseball"}, "League": {"id": 2, "name": "MLB"}},
   "BetResult": {"id": 2, "name": "Lost"},
   "Sport": {"id": 1, "name": "Baseball"}, "League": {"id": 2, "name": "MLB"}}]}
""")


def _bet(**kw):
    b = copy.deepcopy(SAMPLE)
    b.update(kw)
    return b


def _store():
    return zeno.connect(Path(tempfile.mkdtemp()) / "z.db")


def _keys(on=True):
    if on:
        os.environ[jr.CLIENT_ID_ENV] = "cid-test"
        os.environ[jr.CLIENT_SECRET_ENV] = "sec-test"
    else:
        os.environ.pop(jr.CLIENT_ID_ENV, None)
        os.environ.pop(jr.CLIENT_SECRET_ENV, None)


# --- their sample bet, in our store's shape ------------------------------
def test_the_docs_sample_bet_maps_to_one_settled_ticket():
    r = jr.to_row(SAMPLE)
    assert r["external_id"] == "9531"
    assert r["book"] == "NoVig"
    assert r["result"] == "lost" and r["odds"] == 114
    assert r["stake"] == 0.59, r["stake"]              # 0.5886, to cents
    # netResult is signed PROFIT; a loss returns nothing.
    assert r["payout"] == 0.0, r["payout"]
    assert r["sport"] == "mlb" and r["market"] == "moneyline"
    assert r["event"] == "New York Mets @ Atlanta Braves", r["event"]
    assert "New York Mets" in r["selection"], r["selection"]
    assert r["legs"] is None and r["line"] is None
    assert r["placed_at"] == "2026-08-11T13:32:26.434Z"
    assert r["settled_at"] == "2026-08-11T23:15:00.000Z"
    assert r["event_at"] == "2026-08-11T23:15:00.000Z"


def test_a_win_pays_the_stake_back_plus_the_profit():
    r = jr.to_row(_bet(result="Won", netResult=0.6714,
                       BetResult={"id": 1, "name": "Won"}))
    assert r["result"] == "won"
    assert r["payout"] == 1.26, r["payout"]            # 0.5886 + 0.6714


def test_an_open_bet_is_open_with_no_payout():
    r = jr.to_row(_bet(result=None, netResult=None, dateClosed=None,
                       BetStatus={"id": 1, "statusName": "Open"}))
    assert r["result"] == "open" and r["payout"] is None
    assert r["settled_at"] is None


def test_a_cancelled_bet_is_void_whatever_the_result_word_says():
    r = jr.to_row(_bet(BetStatus={"id": 3, "statusName": "Cancelled"}))
    assert r["result"] == "void"


def test_a_closed_bet_with_an_unknown_word_is_read_off_the_money():
    r = jr.to_row(_bet(result="Weird", netResult=0.4,
                       BetResult={"id": 9, "name": "Weird"}))
    assert r["result"] == "won"
    r = jr.to_row(_bet(result="Weird", netResult=0.0,
                       BetResult={"id": 9, "name": "Weird"}))
    assert r["result"] == "push"


def test_the_adjusted_risk_is_the_real_stake_when_juice_reel_says_so():
    r = jr.to_row(_bet(adjustedRisk=0.0))
    assert r["stake"] == 0.0


def test_a_parlay_is_one_ticket_with_its_legs():
    leg2 = copy.deepcopy(SAMPLE["Subbets"][0])
    leg2.update({"id": 13346, "subbetType": "Spread", "position": "Atlanta Braves",
                 "value": -1.5, "description": "Atlanta Braves -1.5"})
    b = _bet(BetType={"id": 2, "typeName": "Parlay"}, oddsAmerican=350,
             Subbets=[SAMPLE["Subbets"][0], leg2])
    r = jr.to_row(b)
    assert r["market"] == "parlay" and r["odds"] == 350
    assert r["legs"] and len(r["legs"]) == 2, r["legs"]
    assert r["selection"].startswith("2-leg parlay: "), r["selection"]
    assert "Atlanta Braves -1.5" in r["legs"][1], r["legs"]
    assert r["line"] is None, "a parlay has no single line"


def test_a_spread_leg_reads_like_a_person_would_say_it():
    sb = copy.deepcopy(SAMPLE["Subbets"][0])
    sb.update({"subbetType": "Spread", "position": "Atlanta Braves",
               "value": -1.5, "description": "x"})
    assert jr._leg_text(sb) == "Atlanta Braves -1.5"
    sb.update({"value": 1.5})
    assert jr._leg_text(sb) == "Atlanta Braves +1.5"
    r = jr.to_row(_bet(Subbets=[sb]))
    assert r["line"] == 1.5 and r["market"] == "spread"


# --- the feed, followed the way the docs describe -------------------------
class _Feed:
    """A fake Juice Reel: pages of bets, newest first, and a log of every
    request so the checkpoint and the cursor can be checked."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        q = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(url).query))
        i = int(q.get("cursor") or 0)
        bets = self.pages[i] if i < len(self.pages) else []
        more = i + 1 < len(self.pages)
        return {"bets": bets, "hasMore": more,
                "nextCursor": str(i + 1) if more else None}


import urllib.parse                                            # noqa: E402


def test_a_first_sync_walks_every_page_and_keeps_the_newest_stamp():
    _keys()
    b1 = _bet(id=1, updatedAt="2026-09-20T10:00:00.000Z")
    b2 = _bet(id=2, updatedAt="2026-09-19T10:00:00.000Z")
    b3 = _bet(id=3, updatedAt="2026-09-18T10:00:00.000Z")
    feed = _Feed([[b1, b2], [b3]])
    conn = _store()
    st = Path(tempfile.mkdtemp()) / "s.json"
    got = jr.sync(conn, opener=feed, state_path=st)
    assert got["ok"] and got["fetched"] == 3 and got["added"] == 3, got
    assert len(feed.calls) == 2, [c[0] for c in feed.calls]
    assert jr.load_checkpoint(st)["updated_at"] == "2026-09-20T10:00:00.000Z"
    # And the keys travelled the way the docs say: Basic auth AND the
    # X-OAuth-Client-Id header, on every request.
    for _url, h in feed.calls:
        assert h["Authorization"].startswith("Basic ") and h["X-OAuth-Client-Id"] == "cid-test"


def test_the_next_sync_asks_only_for_what_changed_and_stops_at_the_checkpoint():
    _keys()
    conn = _store()
    st = Path(tempfile.mkdtemp()) / "s.json"
    jr.save_checkpoint({"updated_at": "2026-09-19T10:00:00.000Z"}, st)
    new = _bet(id=7, updatedAt="2026-09-21T10:00:00.000Z")
    same = _bet(id=2, updatedAt="2026-09-19T10:00:00.000Z")    # at the stamp: kept
    old = _bet(id=3, updatedAt="2026-09-18T10:00:00.000Z")     # older: stop here
    feed = _Feed([[new, same, old], [_bet(id=99)]])
    got = jr.sync(conn, opener=feed, state_path=st)
    assert got["fetched"] == 2, got
    assert len(feed.calls) == 1, "it paged past the checkpoint"
    assert "updatedAtAfter=2026-09-19T10%3A00%3A00.000Z" in feed.calls[0][0]
    assert jr.load_checkpoint(st)["updated_at"] == "2026-09-21T10:00:00.000Z"


def test_syncing_twice_updates_a_settled_bet_rather_than_duplicating_it():
    _keys()
    conn = _store()
    st = Path(tempfile.mkdtemp()) / "s.json"
    open_bet = _bet(id=5, result=None, netResult=None, dateClosed=None,
                    updatedAt="2026-09-20T10:00:00.000Z",
                    BetStatus={"id": 1, "statusName": "Open"})
    jr.sync(conn, opener=_Feed([[open_bet]]), state_path=st)
    settled = _bet(id=5, result="Won", netResult=0.6714,
                   updatedAt="2026-09-21T10:00:00.000Z",
                   BetResult={"id": 1, "name": "Won"})
    got = jr.sync(conn, opener=_Feed([[settled]]), state_path=st)
    assert got["updated"] == 1 and got["added"] == 0, got
    assert conn.execute("SELECT COUNT(*) FROM zeno_bets").fetchone()[0] == 1
    o = zeno.block(conn)["overall"]
    assert o["wins"] == 1 and o["open"] == 0, o


# --- it never takes the build down -----------------------------------------
def test_without_keys_it_says_so_and_does_nothing():
    _keys(on=False)
    conn = _store()
    got = jr.sync(conn, opener=_Feed([[SAMPLE]]))
    assert got["ok"] is False and jr.CLIENT_ID_ENV in got["why"], got
    assert conn.execute("SELECT COUNT(*) FROM zeno_bets").fetchone()[0] == 0
    assert "skipped" in jr.line(got)


def test_a_wrong_key_is_named_and_a_dead_network_is_survived():
    _keys()
    conn = _store()

    def denied(url, headers):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)
    got = jr.sync(conn, opener=denied, state_path=Path(tempfile.mkdtemp()) / "s")
    assert not got["ok"] and "401" in got["why"] and "secret" in got["why"], got
    # AND THE OTHER MEANING. Juice Reel issues keys at once and keeps them
    # inactive until review; that 401 is indistinguishable from a typo, and
    # Ethan's first check returned it seconds after submitting the form.
    assert "review" in got["why"], got["why"]

    def dead(url, headers):
        raise OSError("connection refused")
    got = jr.sync(conn, opener=dead, state_path=Path(tempfile.mkdtemp()) / "s")
    assert not got["ok"] and "could not reach" in got["why"], got


def test_finding_nothing_and_failing_do_not_print_alike():
    quiet = jr.line({"ok": True, "fetched": 0, "added": 0, "updated": 0,
                     "unchanged": 0, "skipped": 0})
    broke = jr.line({"ok": False, "why": "x"})
    assert "0 changed" in quiet and "skipped" not in quiet
    assert "skipped" in broke


def test_the_settle_pass_syncs_before_it_exports_the_record():
    src = (ROOT / "launch.py").read_text(encoding="utf-8")
    src = re.sub(r"(?m)^\s*#.*$", "", src)
    i = src.index("_jr.sync(_zc)")
    j = src.index("_ss.refresh(lconn)")
    assert i < j, "the sync runs after the breaker, not before the export"


def test_the_keys_never_appear_in_a_url():
    _keys()
    feed = _Feed([[]])
    jr.sync(_store(), opener=feed, state_path=Path(tempfile.mkdtemp()) / "s")
    for url, _h in feed.calls:
        assert "sec-test" not in url and "cid-test" not in url, url


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            ran += 1
            try:
                fn()
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{fails} failed" if fails else f"\n{ran} tests passed.")
    sys.exit(1 if fails else 0)
