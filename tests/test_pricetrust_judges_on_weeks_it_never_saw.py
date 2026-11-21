"""pricetrust.py: would pulling our chance toward the price have been closer — on weeks it never saw.

Step 109 (runbook H): on the one board, the picks whose chance ran furthest
above the price were the furthest wrong (claimed 65%, hit 53%, 367 NFL
picks). The check tries one rule — give back part of the gap above the
market's de-vigged chance — choosing it on earlier weeks and scoring it on
the next, against a bar written before any run. These tests plant the
pattern and check it is found, check honest claims are left alone, check
the market's chance is never taken from after the pick, and check nothing
is written.

Run directly: `python3 tests/test_pricetrust_judges_on_weeks_it_never_saw.py`
"""
import datetime as dt
import json
import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pricetrust as PT                                          # noqa: E402
from engine import ledger                                        # noqa: E402
from engine.odds import devig_two_way                            # noqa: E402

#: Our chance minus the market's, cycled across each week's picks.
GAPS = (-0.04, 0.0, 0.03, 0.06, 0.09, 0.12, 0.15, 0.18)


def _picks(truth, seed, weeks=6, per=180):
    """A made-up board: the market's chance, ours above it by GAPS, and an
    outcome drawn at ``truth(ours, market)``."""
    rng = random.Random(seed)
    out = []
    for w in range(weeks):
        for i in range(per):
            m = rng.uniform(0.52, 0.72)
            ours = min(0.95, max(0.05, m + GAPS[i % len(GAPS)]))
            out.append({"id": len(out), "week": f"2026-W{w + 1:02d}", "ours": ours, "market": m,
                        "won": rng.random() < truth(ours, m)})
    return out


def _market_right(ours, m):
    return m


def _ours_right(ours, m):
    return ours


_INS = ("INSERT INTO bets (ts, sport, date, game_day, player, market, side, line, odds, hit_prob, "
        "stake_units, stake_dollars, status, category, fair_consensus) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,0.1,0,?,?,?)")


def _ledger(rows, category="board"):
    """The made-up board journaled as the box journals it: the field's fair
    for the over, so an under carries one minus its own side's chance."""
    p = Path(tempfile.mkdtemp()) / "ledger.db"
    conn = ledger.connect(p)
    for r in rows:
        wk = int(r["week"][-2:])
        side = "UNDER" if r["id"] % 2 else "OVER"
        fc = 1.0 - r["market"] if side == "UNDER" else r["market"]
        day = (dt.date(2026, 9, 13) + dt.timedelta(days=7 * (wk - 1))).isoformat()
        conn.execute(_INS, (f"{day}T15:00:00", "nfl", r["week"], day, f"P{r['id']}", "rec_yds", side, 50.5,
                            -150, round(r["ours"], 4), "won" if r["won"] else "lost", category, round(fc, 4)))
    conn.commit()
    conn.close()
    return p


def test_a_real_overclaim_is_found_on_the_weeks_that_chose_nothing():
    p = _ledger(_picks(_market_right, seed=2))
    rep = PT.study(PT.load(PT.open_ledger(p), "nfl"), snapshots=str(p.parent / "none.jsonl"))
    nfl = rep["books"]["The one board"]["nfl"]
    assert nfl["sources"] == {"journaled": 1080}, nfl["sources"]
    assert nfl["verdict"] == "PASSES", nfl["why"]
    assert nfl["rule_ll"] < nfl["base_ll"] and not nfl["worse_weeks"]
    assert nfl["latest_choice"]["w"] >= 0.5, nfl["latest_choice"]
    # Five held-out weeks: week 1 has nothing before it to choose on.
    assert [w["week"] for w in nfl["walk"]] == ["2026-W02", "2026-W03", "2026-W04", "2026-W05", "2026-W06"]


def test_the_bar_catches_a_pure_overclaim_most_runs_and_honest_chances_almost_never():
    """The rates the runbook quotes: at the NFL board's size (about 180
    picks a week, five held-out weeks), over twenty made-up seasons."""
    caught = sum(PT.verdict(PT.walk(_picks(_market_right, s)))["verdict"] == "PASSES" for s in range(1, 21))
    fooled = sum(PT.verdict(PT.walk(_picks(_ours_right, s)))["verdict"] == "PASSES" for s in range(1, 21))
    assert caught >= 12, caught
    assert fooled <= 2, fooled


def test_honest_chances_choose_no_change():
    weeks = PT.walk(_picks(_ours_right, seed=3))
    assert PT.verdict(weeks)["verdict"] != "PASSES"
    assert sum(w["w"] == 0.0 for w in weeks) >= 3, [(w["week"], w["w"]) for w in weeks]


def test_each_week_is_chosen_only_on_the_weeks_before_it():
    seen = []
    real = PT.fit

    def spy(rows):
        seen.append(max(r["week"] for r in rows))
        return real(rows)

    PT.fit = spy
    try:
        weeks = PT.walk(_picks(_market_right, seed=4))
    finally:
        PT.fit = real
    assert len(seen) == len(weeks)
    for latest_seen, w in zip(seen, weeks):
        assert latest_seen < w["week"], (latest_seen, w["week"])


def test_the_rule_only_gives_back_the_gap_above_the_market():
    assert PT.shown(0.70, 0.60, 1.0, 0.0) == 0.60
    assert abs(PT.shown(0.70, 0.60, 0.5, 0.0) - 0.65) < 1e-12
    # T: only the part of the gap beyond it is given back.
    assert abs(PT.shown(0.68, 0.60, 0.5, 0.05) - 0.665) < 1e-12
    # At or under the market, or inside T: untouched. Never raised.
    assert PT.shown(0.55, 0.60, 1.0, 0.0) == 0.55
    assert PT.shown(0.63, 0.60, 1.0, 0.05) == 0.63
    for ours in (0.3, 0.5, 0.7, 0.9):
        for m in (0.4, 0.6, 0.8):
            for w in PT.GRID_W:
                for t in PT.GRID_T:
                    assert PT.shown(ours, m, w, t) <= ours


def test_a_tie_goes_to_no_change():
    rows = [{"ours": 0.55, "market": 0.60, "won": i % 2 == 0, "week": "2026-W01"} for i in range(80)]
    assert PT.fit(rows) == (0.0, 0.0)


def test_a_thin_book_refuses_to_judge():
    weeks = PT.walk(_picks(_market_right, seed=5, weeks=3, per=40))
    v = PT.verdict(weeks)
    assert v["verdict"] == "NOT YET" and "the bar needs 3 weeks and 100 picks" in v["why"], v


def test_a_week_is_the_sports_own_week():
    assert PT.week({"date": "2026-W3"}) == "2026-W03"
    assert PT.week({"date": "2026-10-15", "game_day": "2026-10-15"}) == "week of 2026-10-12"
    assert PT.week({"date": "", "game_day": "", "ts": "2026-10-18T17:00:00"}) == "week of 2026-10-12"
    assert PT.week({"date": "", "game_day": None, "ts": None}) == ""


def _snap(path, rows):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _bet(i, side="OVER", line=64.5, player="Amon-Ra St. Brown", fc=None):
    return {"id": i, "sport": "nfl", "date": "2026-W06", "game_day": "2026-10-12", "ts": "2026-10-12T16:00:00",
            "player": player, "market": "rec_yds", "side": side, "line": line, "hit_prob": 0.66,
            "status": "won", "category": "board", "fair_consensus": fc}


def test_the_market_at_pick_time_is_rebuilt_from_quotes_before_the_pick_and_never_after():
    pick = dt.datetime(2026, 10, 12, 16, 0, tzinfo=dt.timezone.utc).timestamp()
    hour = 3600.0
    snaps = Path(tempfile.mkdtemp()) / "line_history.jsonl"

    def row(book, at, over, under, line=64.5, **kw):
        return {"ts": at, "player": "Amon Ra St Brown", "market": "rec_yds", "book": book, "line": line,
                "over_odds": over, "under_odds": under, **kw}

    _snap(snaps, [
        row("draftkings", pick - 3 * hour, -140, 110),     # superseded by its later quote
        row("draftkings", pick - hour, -120, 100),
        row("fanduel", pick - 2 * hour, -115, -105),
        row("betmgm", pick - 0.5 * hour, -125, 105),
        row("caesars", pick + 600, -300, 240),             # after the pick: never
        row("espnbet", pick - 7 * hour, -300, 240),        # older than six hours
        row("bovada", pick - hour, -300, None),            # one side only: a vig would be guessed
        row("pointsbet", pick - hour, -300, 240, line=65.5),   # another line
        row("hardrock", pick - 0.2 * hour, -300, 240, start_ts=pick - 0.4 * hour),   # in play
    ])
    fairs = sorted(devig_two_way(o, u)[0] for o, u in ((-120, 100), (-115, -105), (-125, 105)))
    bets = [_bet(1), _bet(2, side="UNDER"), _bet(3, player="Somebody Else")]
    counts = PT.attach_market(bets, str(snaps))
    assert abs(bets[0]["market_p"] - fairs[1]) < 1e-9, (bets[0]["market_p"], fairs)
    assert abs(bets[1]["market_p"] - (1.0 - fairs[1])) < 1e-9
    assert bets[0]["market_src"] == bets[1]["market_src"] == "snapshots"
    assert bets[2]["market_p"] is None and counts == {"snapshots": 2, "none": 1}, counts


def test_an_accented_name_written_escaped_still_finds_its_quotes():
    """json.dumps writes "Acuña" as "Acu\\u00f1a"; the fast read off the
    text cannot compare that, so the line is parsed instead of skipped."""
    pick = dt.datetime(2026, 10, 12, 16, 0, tzinfo=dt.timezone.utc).timestamp()
    snaps = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    _snap(snaps, [{"ts": pick - 60, "player": "Ronald Acuña Jr.", "market": "hits", "book": b,
                   "line": 0.5, "over_odds": -200, "under_odds": 160}
                  for b in ("draftkings", "fanduel", "betmgm")])
    assert "\\u00f1" in snaps.read_text()
    bet = dict(_bet(1, line=0.5, player="Ronald Acuna"), market="hits", sport="mlb")
    PT.attach_market([bet], str(snaps))
    assert abs(bet["market_p"] - devig_two_way(-200, 160)[0]) < 1e-9, bet["market_p"]


def test_two_books_are_not_a_field():
    pick = dt.datetime(2026, 10, 12, 16, 0, tzinfo=dt.timezone.utc).timestamp()
    snaps = Path(tempfile.mkdtemp()) / "line_history.jsonl"
    _snap(snaps, [{"ts": pick - 60, "player": "Amon-Ra St. Brown", "market": "rec_yds", "book": b,
                   "line": 64.5, "over_odds": -120, "under_odds": 100} for b in ("draftkings", "fanduel")])
    bets = [_bet(1)]
    PT.attach_market(bets, str(snaps))
    assert bets[0]["market_p"] is None


def test_the_journaled_field_comes_first_and_an_under_is_its_other_side():
    snaps = Path(tempfile.mkdtemp()) / "none.jsonl"
    bets = [_bet(1, fc=0.58), _bet(2, side="UNDER", fc=0.58), _bet(3, fc=None)]
    counts = PT.attach_market(bets, str(snaps))
    assert bets[0]["market_p"] == 0.58 and abs(bets[1]["market_p"] - 0.42) < 1e-12
    assert counts == {"journaled": 2, "none": 1}, counts


def test_the_bands_describe_how_far_our_chance_ran_above():
    rows = [{"ours": 0.80, "market": 0.60, "won": i < 6} for i in range(10)] + \
           [{"ours": 0.62, "market": 0.60, "won": i < 6} for i in range(10)] + \
           [{"ours": 0.55, "market": 0.60, "won": i < 6} for i in range(10)]
    b = {r["band"]: r for r in PT.bands(rows)}
    assert set(b) == {"15+ points above", "0-5 above", "at or under the market"}
    assert b["15+ points above"]["hit"] == 0.6 and b["15+ points above"]["z_ours"] < 0


def test_the_ledger_and_the_snapshots_are_never_written():
    p = _ledger(_picks(_market_right, seed=2, weeks=4, per=60))
    snaps = p.parent / "line_history.jsonl"
    _snap(snaps, [{"ts": 1.0, "player": "P1", "market": "rec_yds", "book": "fanduel", "line": 50.5,
                   "over_odds": -110, "under_odds": -110}])
    before = (p.read_bytes(), snaps.read_bytes())
    out = p.parent / "report.json"
    assert PT.main(["--db", str(p), "--snapshots", str(snaps), "--json", str(out)]) == 0
    assert (p.read_bytes(), snaps.read_bytes()) == before
    rep = json.loads(out.read_text())
    assert rep["books"]["The one board"]["nfl"]["verdict"] in ("PASSES", "FAILS", "NOT YET")


def test_the_report_says_the_verdict_and_where_the_market_came_from():
    p = _ledger(_picks(_market_right, seed=2))
    text = PT.render(PT.study(PT.load(PT.open_ledger(p)), snapshots=str(p.parent / "none.jsonl")))
    assert "=== The one board · NFL  — 1080 settled, 1080 with a market chance (journaled 1080)" in text
    assert "VERDICT: PASSES — every held-out week no worse, and the pooled log loss better" in text
    assert "2026-W06" in text and "by how far our chance ran above the market" in text


def test_the_bar_is_written_down_before_the_run():
    src = " ".join((ROOT / "pricetrust.py").read_text().split())
    assert "THE BAR, WRITTEN BEFORE ANY RUN" in src
    assert "every held-out week's log loss with the rule is no worse than without it" in src
    assert "AND the pooled held-out log loss is better" in src
    assert "never after it and never after the game's start" in src
    assert PT.GRID_W == (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
    assert PT.GRID_T == (0.0, 0.05, 0.10, 0.15)
    assert (PT.MIN_TRAIN, PT.MIN_WEEKS, PT.MIN_HELD, PT.SNAPSHOT_HOURS) == (60, 3, 100, 6.0)


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
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
