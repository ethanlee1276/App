"""Where the credits went, and what stops it happening again.

Ethan's 20,000-credit plan emptied and the only evidence was a cumulative
counter that says how much is gone and nothing about what took it. "What
burned my quota" should be a receipt, not an archaeology exercise.

The hole was `harvest_odds.py --budget`, which defaulted to 0 — no cap — on a
command whose own dry-run text warns that one full-market historical call has
measured at 35-40 credits. Thirty days of a fifteen-game sport is roughly
sixteen thousand credits from a single command, with one y/N prompt between
it and the meter.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import oddsbudget as B
from engine.sources import oddsapi as O

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- what a call actually costs ---------------------------------------------
def test_a_call_is_priced_from_the_request_it_actually_sent():
    """The API bills per market per region. Pricing a build by "one call per
    game" is what made an eight-credit request look like one credit — the
    invisible overspend the pacer was blind to for a month."""
    live = ("https://api.the-odds-api.com/v4/sports/baseball_mlb/events/e1/odds"
            "?markets=a,b,c,d,e,f,g,h&regions=us")
    kind, sport, credits, _ = O._classify(live, "odds_event_e1.json")
    assert kind == "live_event"
    assert credits == 8, "an eight-market request was not priced at eight"

    two = live.replace("markets=a,b,c,d,e,f,g,h", "markets=a,b")
    assert O._classify(two, "odds_event_e1.json")[2] == 2


def test_a_historical_call_is_priced_far_above_a_live_one():
    """This is the whole story of the burn. The same request against the
    historical endpoint is billed at a large multiple, and nothing in the
    system used to say so out loud."""
    q = "?markets=a,b,c,d,e,f,g,h&regions=us"
    live = O._classify(
        f"https://api.the-odds-api.com/v4/sports/baseball_mlb/events/e/odds{q}",
        "odds_event_e.json")[2]
    hist = O._classify(
        f"https://api.the-odds-api.com/v4/historical/sports/baseball_mlb/events/e/odds{q}",
        "odds_hist_event_mlb_2026.json")[2]
    assert hist > live * 3, (hist, live)


def test_the_sport_is_attributed_so_spend_can_be_blamed():
    kind, sport, _, _ = O._classify(
        "https://x/v4/sports/baseball_mlb/events?regions=us",
        "odds_events_mlb.json")
    assert sport == "mlb" and kind == "live_events"


# --- the ledger -------------------------------------------------------------
def test_every_paid_call_lands_in_the_ledger_with_a_day_and_a_price():
    p = os.path.join(tempfile.mkdtemp(), "spend.jsonl")
    B.log_spend("hist_event", "mlb", 38, "2026-07-01", path=p)
    B.log_spend("hist_event", "mlb", 38, "2026-07-02", path=p)
    B.log_spend("live_event", "mlb", 8, path=p)
    by_day = B.spend_by_day(path=p)
    day = next(iter(by_day))
    assert by_day[day]["hist_event"] == [2, 76]
    assert by_day[day]["live_event"] == [1, 8]


def test_the_ledger_never_breaks_a_fetch():
    """Accounting that can take down a build is worse than no accounting.

    An unwritable path here is a REGULAR FILE standing where a directory
    would have to be — log_spend creates missing directories on purpose, so
    a merely-absent path is not the failure case."""
    d = tempfile.mkdtemp()
    blocker = os.path.join(d, "blocker")
    open(blocker, "w").close()
    bad = os.path.join(blocker, "nested", "spend.jsonl")
    B.log_spend("live_event", "mlb", path=bad)      # must not raise
    assert B.read_spend(path=bad) == []


def test_a_corrupt_ledger_line_is_skipped_not_fatal():
    p = os.path.join(tempfile.mkdtemp(), "spend.jsonl")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"iso": "2026-08-02", "kind": "live_event",
                             "credits": 8}) + "\n")
        fh.write("{ not json\n")
    assert len(B.read_spend(path=p)) == 1


# --- the hole that let it happen --------------------------------------------
def test_the_harvester_defaults_to_a_spend_cap():
    """It defaulted to 0 — unlimited — and 0 is still available, but you have
    to ask for it now."""
    import harvest_odds
    assert harvest_odds.DEFAULT_BUDGET > 0
    src = open(os.path.join(_ROOT, "harvest_odds.py"), encoding="utf-8").read()
    assert "default=DEFAULT_BUDGET" in src, "the cap is not wired to the flag"
    assert "default=0" not in src.split("--budget")[1][:200], (
        "the budget flag still defaults to unlimited")


def test_one_plan_cannot_be_emptied_by_the_default_harvest():
    """The ceiling has to be small against a plan, or it is decoration. One
    plan is 20,000 credits."""
    import harvest_odds
    assert harvest_odds.DEFAULT_BUDGET < 20000 / 10


def test_the_confirmation_prints_a_number_not_a_warning():
    """"This spends API credits" is not information. A figure you can compare
    against your balance is."""
    src = open(os.path.join(_ROOT, "harvest_odds.py"), encoding="utf-8").read()
    block = src[src.index("if not args.yes:"):src.index("conn = _db.connect")]
    assert "Estimated cost" in block
    assert "Your pool right now" in block
    assert "NO SPEND CAP" in block, (
        "running uncapped has to announce itself")


def test_the_audit_command_is_wired_up():
    src = open(os.path.join(_ROOT, "launch.py"), encoding="utf-8").read()
    assert '"--odds-audit" in argv' in src
    assert "def odds_audit(" in src


if __name__ == "__main__":
    import re as _re
    declared = _re.findall(r"^def (test_\w+)",
                           open(__file__, encoding="utf-8").read(), _re.M)
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    assert not set(declared) - {f.__name__ for f in fns}
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
