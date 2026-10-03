#!/usr/bin/env python3
"""Are the Record page's numbers right? Read-only, on the box.

    cd /srv/qellys && sudo -u qellys python3 recordcheck.py            # NFL
    sudo -u qellys python3 recordcheck.py --sport mlb

Ethan, 2026-09-28, two Record-page screenshots: the Most Likely section's
Spread row read 2/2 while Pick of the Day listed a CAR spread LOST — "make
sure all the numbers are correct". Then 2026-10-02, four more: "make sure
we are recording everything and not missing anything ... No way we have
hit 12/13 TD picks bc I've seen more then that loose." Ten checks, nothing
written:

1. EVERY GRADE, RE-DERIVED. The ledger is copied into memory and the
   settler's own repair pass (engine/ledger.resettle_mismatches) runs on
   the copy against the history database: every settled bet whose stored
   grade disagrees with the final numbers now on file is listed. The real
   ledger is opened read-only and never touched.
2. THE SAME BET, TWO GRADES. One pick journaled in two sections (Most
   Likely and Pick of the Day, say) must carry one result.
3. EVERY GAME-LINE BET, BY SECTION. Spreads, totals and moneylines listed
   with the section that counts each, so a row can be matched to the
   number above it.
4. EACH SECTION RECOUNTED. The report functions the page draws from
   (likely_report, board_report, performance) against a plain count of
   the rows; any difference is printed.
5. EVERY ANYTIME-TOUCHDOWN PICK, IN EVERY SECTION, with its side ("scores"
   or "no TD"), price, result and the touchdowns the box score credits —
   so a TD pick seen losing can be found, and the section that counts it.
6. WHERE THE BOARD'S PICKS CAME FROM: each settled board pick against the
   other books that hold the same pick (the Most Likely list, the matchup
   picks, the touchdown scenarios), with each source's W-L and units.
7. OPEN BETS WHOSE GAME IS PAST — a bet that should have graded and did
   not, by section.
8. ROWS WITH NO CALENDAR DAY, by section. They count in every total but in
   no calendar or window; `launch.py --backfill-days` places them.
9. THE HEADLINE, RECOUNTED BY HAND: the combined record (edge picks +
   Most Likely, each pick once) and its two halves, counted here row by
   row without the ledger's SQL, against what the page is given.
10. THE PUBLISHED BOARD AGAINST THE JOURNAL: every pick on the league's
   live board file has its journal row, or the reason it does not.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import ledger as L                                  # noqa: E402

SECTION = {"main": "Edge picks", "paper": "Edge picks", "likely": "Most Likely", "likely_live": "Most Likely",
           "board": "Most Likely by tier", "potd": "Pick of the Day", "matchup_td": "Matchup TD picks",
           "matchup_prop": "Matchup picks", "td_scenario": "TD scenarios", "bold": "Bolder than the books",
           "longshot": "Long shots", "plan_gap": "Market gaps", "held": "Held back by the board"}

#: Where each league's board is published (engine/boardlint's map).
BOARD_FILES = {"nfl": "recommendations.json", "cfb": "cfb.json", "mlb": "mlb_recommendations.json",
               "nba": "nba.json", "wnba": "wnba.json"}


def _ro(path) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{Path(path)}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def copy_to_memory(path) -> sqlite3.Connection:
    src = _ro(path)
    mem = sqlite3.connect(":memory:")
    src.backup(mem)
    src.close()
    mem.row_factory = sqlite3.Row
    return mem


def regrade(mem, hist) -> list:
    """What the settler's repair pass would change, run on the copy."""
    try:
        return L.resettle_mismatches(mem, hist) or []
    except Exception as exc:                                    # noqa: BLE001
        return [{"error": f"{type(exc).__name__}: {exc}"}]


def expected_status(side, line, actual) -> str | None:
    """The result a bet's own stored number implies — side-aware, a push on
    the number (spreads are stored as margin OVER the negated line)."""
    try:
        a, ln = float(actual), float(line)
    except (TypeError, ValueError):
        return None
    s = str(side or "").upper()
    if s in ("OVER", "YES"):
        return "won" if a > ln else "push" if a == ln else "lost"
    if s in ("UNDER", "NO"):
        return "won" if a < ln else "push" if a == ln else "lost"
    return None


def self_contradictions(conn, sport) -> list:
    """Settled bets whose result disagrees with their own stored number."""
    out = []
    for r in conn.execute(f"SELECT category, {L.day_expr()} AS day, player, market, side, line, actual, status "
                          "FROM bets WHERE status IN ('won','lost','push') AND actual IS NOT NULL "
                          "AND LOWER(sport)=?", (sport,)):
        want = expected_status(r["side"], r["line"], r["actual"])
        if want and want != r["status"]:
            out.append(dict(r, want=want))
    return out


def split_grades(conn, sport) -> list:
    """Settled bets journaled in more than one section with different results."""
    q = (f"SELECT category, {L.day_expr()} AS day, player, market, side, line, status FROM bets "
         "WHERE status IN ('won','lost','push') AND LOWER(sport)=?")
    groups: dict = defaultdict(list)
    for r in conn.execute(q, (sport,)):
        groups[(r["day"], r["player"], r["market"], (r["side"] or "").upper(), r["line"])].append(
            (r["category"], r["status"]))
    return [(k, v) for k, v in groups.items() if len({s for _c, s in v}) > 1]


def game_lines(conn, sport) -> list:
    marks = ",".join("?" * len(L.GAME_MARKETS))
    return [dict(r) for r in conn.execute(
        f"SELECT category, {L.day_expr()} AS day, date, player, market, side, line, odds, status, actual, stake_units "
        f"FROM bets WHERE LOWER(sport)=? AND market IN ({marks}) AND status IN ('won','lost','push','open') "
        "ORDER BY day, category", (sport, *L.GAME_MARKETS))]


def recount(conn, sport) -> list:
    """(section, what, report says, raw count says) for every disagreement."""
    out = []
    lk = L.likely_report(conn, sport=sport)
    raw = {r["market"]: (r["n"], r["w"]) for r in conn.execute(
        "SELECT market, COUNT(*) n, SUM(status='won') w FROM bets WHERE status IN ('won','lost') "
        "AND category IN ('likely','likely_live') AND LOWER(sport)=? GROUP BY market", (sport,))}
    for m, d in (lk.get("by_market") or {}).items():
        got, want = (d.get("n"), d.get("w")), raw.get(m, (0, 0))
        if tuple(got) != tuple(want):
            out.append(("Most Likely", f"by market {m} (n, won)", got, want))
    for m, (n, w) in raw.items():
        if m not in (lk.get("by_market") or {}):
            out.append(("Most Likely", f"by market {m} (n, won)", "missing", (n, w)))
    tw = conn.execute("SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category IN "
                      "('likely','likely_live') AND LOWER(sport)=?", (sport,)).fetchone()
    if (lk.get("wins"), lk.get("losses")) != (tw["w"] or 0, tw["l"] or 0):
        out.append(("Most Likely", "wins-losses", (lk.get("wins"), lk.get("losses")), (tw["w"] or 0, tw["l"] or 0)))
    br = L.board_report(conn, sport=sport)
    for t in br.get("tiers") or []:
        r = conn.execute("SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category='board' "
                         "AND grade=? AND LOWER(sport)=?", (t["tier"], sport)).fetchone()
        if (t["w"], t["l"]) != (r["w"] or 0, r["l"] or 0):
            out.append(("Most Likely by tier", t["tier"], (t["w"], t["l"]), (r["w"] or 0, r["l"] or 0)))
    for label, cats in (("Pick of the Day", (L.POTD_CATEGORY,)), ("Edge picks", L.BOOK)):
        p = L.performance(conn, sport, cats if len(cats) > 1 else cats[0])
        marks = ",".join("?" * len(cats))
        r = conn.execute(f"SELECT SUM(status='won') w, SUM(status='lost') l FROM bets WHERE category IN ({marks}) "
                         "AND stake_units > 0 AND LOWER(sport)=?", (*cats, sport)).fetchone()
        got = (p.get("wins"), p.get("losses"))
        if got != (r["w"] or 0, r["l"] or 0):
            out.append((label, "wins-losses", got, (r["w"] or 0, r["l"] or 0)))
    return out


def td_rows(conn, sport) -> list:
    """Every anytime-touchdown row, every section, settled and open.
    OVER 0.5 is "he scores", UNDER 0.5 "he does not" (log_most_likely)."""
    return [dict(r) for r in conn.execute(
        f"SELECT category, {L.day_expr()} AS day, player, side, odds, hit_prob, status, actual, grade "
        "FROM bets WHERE LOWER(sport)=? AND market='anytime_td' "
        "AND status IN ('won','lost','push','open') ORDER BY day, category, player", (sport,))]


def td_word(side) -> str:
    return "no TD" if str(side or "").upper() in ("UNDER", "NO") else "scores"


def td_summary(rows) -> dict:
    """{(section, side word): [won, lost, open]}."""
    out: dict = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        k = (SECTION.get(r["category"], r["category"]), td_word(r["side"]))
        i = {"won": 0, "lost": 1, "open": 2}.get(r["status"])
        if i is not None:
            out[k][i] += 1
    return dict(out)


#: The other books a board pick can also sit in, asked in this order.
BOARD_SOURCES = (("the Most Likely list", ("likely", "likely_live")),
                 ("the matchup picks", ("matchup_td", "matchup_prop")),
                 ("the TD scenarios", ("td_scenario",)),
                 ("bolder than the books", ("bold",)))


def board_sources(conn, sport) -> dict:
    """{source: {w, l, push, units, tiers: {tier: [w, l]}}} over the board's
    settled picks — the same pick (date, player, market, side) found in
    another book names where it came from; none is "the board only"."""
    out: dict = {}
    for b in conn.execute("SELECT * FROM bets WHERE category='board' AND status IN ('won','lost','push') "
                          "AND LOWER(sport)=?", (sport,)):
        src = "the board only"
        for label, cats in BOARD_SOURCES:
            marks = ",".join("?" * len(cats))
            if conn.execute(
                    "SELECT 1 FROM bets WHERE sport=? AND date=? AND player=? AND market=? "
                    f"AND UPPER(COALESCE(side,''))=UPPER(COALESCE(?,'')) AND category IN ({marks}) LIMIT 1",
                    (b["sport"], b["date"], b["player"], b["market"], b["side"], *cats)).fetchone():
                src = label
                break
        e = out.setdefault(src, {"w": 0, "l": 0, "push": 0, "units": 0.0, "tiers": {}})
        st = b["status"]
        e["w" if st == "won" else "l" if st == "lost" else "push"] += 1
        e["units"] += float(b["pnl_units"] or 0.0)
        t = e["tiers"].setdefault(b["grade"] or "?", [0, 0])
        if st in ("won", "lost"):
            t[0 if st == "won" else 1] += 1
    return out


def stuck_open(conn, sport, today=None, grace_days=2) -> list:
    """(section, open count, oldest day) for open bets whose calendar day
    is more than `grace_days` behind today — a game that should have
    graded. Rows with no calendar day are counted in check 8 instead."""
    today = today or _dt.date.today()
    cut = (today - _dt.timedelta(days=grace_days)).isoformat()
    return [tuple(r) for r in conn.execute(
        f"SELECT category, COUNT(*), MIN({L.day_expr()}) FROM bets WHERE status='open' AND LOWER(sport)=? "
        "AND game_day IS NOT NULL AND game_day != '' AND game_day < ? GROUP BY category ORDER BY 2 DESC",
        (sport, cut))]


def no_day(conn, sport) -> list:
    """(section, settled, open) for rows with no calendar day."""
    return [tuple(r) for r in conn.execute(
        "SELECT category, SUM(status IN ('won','lost','push')), SUM(status='open') FROM bets "
        "WHERE (game_day IS NULL OR game_day='') AND LOWER(sport)=? AND status IN ('won','lost','push','open') "
        "GROUP BY category ORDER BY 2 DESC", (sport,))]


def by_hand(conn, sport, since=None) -> dict:
    """The combined record and its halves, counted row by row in Python —
    no `books_sql`, no `performance` — for check 9. A board pick counts
    unless a staked Most Likely list row holds the same pick and side."""
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM bets WHERE status IN ('won','lost','push') AND stake_units > 0 AND LOWER(sport)=?",
        (sport,))]
    if since:
        rows = [r for r in rows if str(r["date"] or "") >= since]
    held = {(r["date"], r["player"], r["market"], str(r["side"] or "").upper())
            for r in conn.execute("SELECT date, player, market, side FROM bets WHERE LOWER(sport)=? "
                                  "AND category IN ('likely','likely_live') AND stake_units > 0", (sport,))}
    def tally(keep):
        t = {"wins": 0, "losses": 0, "pushes": 0, "net_units": 0.0}
        for r in rows:
            if not keep(r):
                continue
            st = r["status"]
            t["wins" if st == "won" else "losses" if st == "lost" else "pushes"] += 1
            t["net_units"] += float(r["pnl_units"] or 0.0)
        t["net_units"] = round(t["net_units"], 2)
        return t
    def ml_once(r):
        if r["category"] in ("likely", "likely_live"):
            return True
        return r["category"] == "board" and \
            (r["date"], r["player"], r["market"], str(r["side"] or "").upper()) not in held
    return {"edge": tally(lambda r: r["category"] in ("main", "paper")),
            "likely": tally(ml_once),
            "overall": tally(lambda r: r["category"] in ("main", "paper") or ml_once(r))}


def board_vs_journal(conn, sport, data_dir) -> tuple:
    """(rows on the published board, [(row, reason)] for those with no
    journal row). The reason is the journal's own refusal where the row
    shows one; "not journaled" where it does not, which is the finding."""
    path = Path(data_dir) / BOARD_FILES.get(sport, "")
    if sport not in BOARD_FILES or not path.exists():
        return None, []
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, []
    rows = ((d.get("likely_board") or {}).get("rows")) or []
    date = str(d.get("date") or "")
    missing = []
    for r in rows:
        market = r.get("market", "")
        player = r.get("player")
        if r.get("kind") == "game" or market in L.GAME_MARKETS:
            keys = L.game_row_keys(r, market)
            if keys:
                player, market = keys[0], keys[1]
        row_date = date if sport == "nfl" else str(r.get("game_date") or "").strip() or date
        if conn.execute("SELECT 1 FROM bets WHERE sport=? AND date=? AND player=? AND market=? "
                        "AND category='board' LIMIT 1", (sport, row_date, player, market)).fetchone():
            continue
        try:
            odds_ok = abs(int(r.get("odds") or 0)) >= 100
        except (TypeError, ValueError):
            odds_ok = False
        why = ("a reserve row (below the bar)" if r.get("reserve")
               else "its game had started" if r.get("live") or r.get("started")
               else "no price at 100 or longer" if not odds_ok
               else "no chance on it" if r.get("model_prob") is None
               else "lineup not confirmed" if r.get("lineup_confirmed") is False
               else "not journaled")
        missing.append((r, why))
    return len(rows), missing


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="nfl")
    ap.add_argument("--db", default=str(ROOT / "data" / "ledger.db"))
    ap.add_argument("--history", default=str(ROOT / "data" / "history.db"))
    ap.add_argument("--data", default=str(ROOT / "web" / "data"))
    a = ap.parse_args(argv)
    sport = a.sport.lower()
    mem = copy_to_memory(a.db)
    hist = _ro(a.history)
    print(f"RECORD CHECK — {sport.upper()} (read-only: the ledger is checked on an in-memory copy)\n")

    fixes = regrade(mem, hist)
    print(f"1. GRADES THAT DISAGREE WITH THE FINAL NUMBERS ON FILE (every sport): {len(fixes)}")
    for f in fixes[:40]:
        if "error" in f:
            print(f"    could not re-derive: {f['error']}")
            continue
        print(f"    {f.get('date')} {f.get('player')} {f.get('market')}: graded {f.get('was')}, "
              f"the final numbers say {f.get('now')} (actual {f.get('actual')})")
    mem2 = copy_to_memory(a.db)       # the untouched copy, for the rest
    selfc = self_contradictions(mem2, sport)
    print(f"\n1b. RESULTS THAT CONTRADICT THEIR OWN NUMBER: {len(selfc)}")
    for r in selfc[:40]:
        print(f"    {r['day']} {SECTION.get(r['category'], r['category'])}: {r['player']} {r['market']} "
              f"{r['side']} {r['line']} — actual {r['actual']}, recorded {r['status']}, should be {r['want']}")
    split = split_grades(mem2, sport)
    print(f"\n2. THE SAME BET GRADED DIFFERENTLY IN TWO SECTIONS: {len(split)}")
    for (day, player, market, side, line), v in split[:40]:
        print(f"    {day} {player} {market} {side} {line}: " + ", ".join(f"{SECTION.get(c, c)} {s}" for c, s in v))
    rows = game_lines(mem2, sport)
    print(f"\n3. EVERY {sport.upper()} GAME-LINE BET ({len(rows)}), with the section that counts it")
    for r in rows:
        line = r["line"]
        shown = -line if r["market"] == "spread" and line is not None else line
        print(f"    {r['day']}  {SECTION.get(r['category'], r['category']):20} {r['player']:10} {r['market']:9} "
              f"{r['side'] or '':5} {shown!s:>6} {r['odds']!s:>6}  {r['status']:5}  actual {r['actual']}")
    diffs = recount(mem2, sport)
    print(f"\n4. SECTION TOTALS THAT DISAGREE WITH A PLAIN COUNT: {len(diffs)}")
    for sec, what, got, want in diffs:
        print(f"    {sec} · {what}: page {got}, rows {want}")

    tds = td_rows(mem2, sport)
    print(f"\n5. EVERY ANYTIME-TD PICK, EVERY SECTION ({len(tds)}) — 'scores' is a yes, 'no TD' a no")
    for (sec, word), (w, l, o) in sorted(td_summary(tds).items()):
        print(f"    {sec:22} {word:7} {w}-{l}" + (f", {o} open" if o else ""))
    for r in tds:
        tdn = "" if r["actual"] is None else f"  TDs {r['actual']:g}"
        print(f"    {r['day']}  {SECTION.get(r['category'], r['category']):22} {r['player']:24} "
              f"{td_word(r['side']):7} {r['odds']!s:>6}  {r['status']:5}{tdn}")

    src = board_sources(mem2, sport)
    print("\n6. WHERE THE BOARD'S SETTLED PICKS CAME FROM (the same pick found in another book)")
    for label, e in sorted(src.items(), key=lambda kv: -(kv[1]["w"] + kv[1]["l"])):
        tiers = ", ".join(f"{t} {w}-{l}" for t, (w, l) in sorted(e["tiers"].items()))
        print(f"    {label:24} {e['w']}-{e['l']}" + (f"-{e['push']}" if e["push"] else "")
              + f"  {e['units']:+.2f}u   ({tiers})")

    stuck = stuck_open(mem2, sport)
    print(f"\n7. OPEN BETS WHOSE GAME DAY IS PAST: {sum(n for _c, n, _d in stuck)}")
    for cat, n, oldest in stuck:
        print(f"    {SECTION.get(cat, cat):22} {n} open, oldest {oldest}")

    nd = no_day(mem2, sport)
    print(f"\n8. ROWS WITH NO CALENDAR DAY: {sum((a or 0) + (b or 0) for _c, a, b in nd)}"
          + ("  (place them: sudo -u qellys python3 launch.py --backfill-days, then --apply)" if nd else ""))
    for cat, settled, opn in nd:
        print(f"    {SECTION.get(cat, cat):22} {settled or 0} settled, {opn or 0} open")

    hand = by_hand(mem2, sport, since=L.RECORD_EPOCH)
    rep = L.pooled_report(mem2, sport, since=L.RECORD_EPOCH)
    off = []
    for k, label in (("edge", "Edge picks"), ("likely", "Most Likely, every pick once"),
                     ("overall", "Combined")):
        page, mine = rep.get(k) or {}, hand[k]
        got = (page.get("wins"), page.get("losses"), page.get("pushes"), round(float(page.get("net_units") or 0), 2))
        want = (mine["wins"], mine["losses"], mine["pushes"], mine["net_units"])
        if got[:3] != want[:3] or abs(got[3] - want[3]) > 0.011:
            off.append((label, got, want))
    print(f"\n9. THE HEADLINE, RECOUNTED BY HAND: {len(off)} disagreement(s)")
    for k, label in (("edge", "Edge picks"), ("likely", "Most Likely, every pick once"), ("overall", "Combined")):
        m = hand[k]
        print(f"    {label:30} {m['wins']}-{m['losses']}" + (f"-{m['pushes']}" if m["pushes"] else "")
              + f"  {m['net_units']:+.2f}u")
    for label, got, want in off:
        print(f"    ✗ {label}: page {got}, by hand {want}")

    n_pub, missing = board_vs_journal(mem2, sport, a.data)
    if n_pub is None:
        print(f"\n10. THE PUBLISHED BOARD AGAINST THE JOURNAL: no {sport.upper()} board file in {a.data}")
    else:
        silent = [m for m in missing if m[1] == "not journaled"]
        print(f"\n10. THE PUBLISHED BOARD AGAINST THE JOURNAL: {n_pub} on the board, "
              f"{n_pub - len(missing)} journaled, {len(missing)} not ({len(silent)} with no reason)")
        for r, why in missing[:40]:
            print(f"    {r.get('player')} {r.get('market')} {r.get('side') or ''} {r.get('line')!s} "
                  f"({r.get('tier_label') or r.get('tier') or ''}): {why}")

    if not (fixes or selfc or split or diffs or stuck or off or [m for m in missing if m[1] == "not journaled"]):
        print("\nEvery check clean: every grade matches the final numbers, no bet carries two results,"
              " every section's totals match its rows, nothing is stuck open, the headline recounts by hand,"
              " and every pick on the board is journaled.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
