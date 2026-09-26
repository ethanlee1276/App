"""One Most Likely board: every pick the site makes, in one pool, each put
through four checks and given a tier.

Ethan, 2026-09-26: "maybe we should combine the matchup picks and most
likely picks into one big, just most likely pick area ... filter through
to see what works best with all of our data and matchup scripts ... I
don't want to lose any picks, but I want to just be more confident in what
we're selecting ... so we're not confusing the user and don't have a
million different places for a million different picks." Then, to the plan
below: "yeah do it".

THE POOL. The Most Likely board as it stands (props, scorers, game lines —
the rows the staked and paper books already journal), the matchup picks
(engine/matchpicks) and the touchdown scenarios (engine/tdscenarios), one
row per bet: the same player, market, side and line from two makers is one
row that remembers both. Nothing is dropped here.

THE FOUR CHECKS, each True (agrees), False (disagrees) or None (cannot
say):

  model    our chance clears its lane's bar (MODEL_BAR) — a touchdown is
           its own lane, since a 45% scorer is a good scorer and not a
           worse 60% prop;
  matchup  the offence-against-defence breakdown backs this side: for a
           prop, the scan's read leans the same way (engine/gamescan
           leans); for a scorer, his matchup scores TD_CASE of 8 or better
           (engine/matchpicks.td_matchup), and 1 or less says no;
  market   the sportsbooks' price is near our chance — within MARKET_AGREE
           it agrees; MARKET_FAR or more above the price, it disagrees
           (when we are that far from every book, that is usually our
           error, not free money);
  record   picks of this market, side and chance band have hit at about
           the rate we claimed in our own journal (RECORD_MIN_N settled
           first) — the check that learns.

THE TIERS. Top: our number, the matchup and the market agree and the
record is not against it. Strong: the model passes and at most one check is against it with
three for, or none against with two for. Worth a look: the rest.

Nothing here moves a probability; the tier is how many independent reads
back the number. Published as ``likely_board`` and journaled on paper per
tier (ledger category ``board``), so the record says whether Top really
hits more than Worth a look.

Standard library only.
"""
from __future__ import annotations

#: Our chance a pick needs for the model check, by lane.
MODEL_BAR = {"td": 0.40, "prop": 0.58, "game": 0.58}
#: Our chance within this of the book's: the market agrees.
MARKET_AGREE = 0.08
#: Our chance this far ABOVE the book's: the market disagrees.
MARKET_FAR = 0.15
#: A scorer's matchup (of 8) that backs him, and the most that says no.
TD_CASE = 4
TD_AGAINST = 1
#: Settled picks of a market-side-band before our record speaks.
RECORD_MIN_N = 20
#: How far under the claimed rate the record may run and still agree, and
#: how far under it says no.
RECORD_SLACK = 0.04
RECORD_MISS = 0.08
#: The journal buckets whose settled rows make the record.
RECORD_CATEGORIES = ("likely", "matchup_td", "matchup_prop", "td_scenario", "board")
#: Chance bands the record is read in (ledger.LIKELY_BANDS).
BANDS = ((0.30, 0.45), (0.45, 0.60), (0.60, 0.75), (0.75, 1.01))

TIERS = (("top", "Top pick"), ("strong", "Strong"), ("look", "Worth a look"))
TIER_LABEL = dict(TIERS)


def lane_of(r: dict) -> str:
    if r.get("kind") == "game":
        return "game"
    return "td" if r.get("market") == "anytime_td" else "prop"


def _side(r: dict) -> str:
    s = str(r.get("side") or "").lower()
    return {"yes": "over", "no": "under"}.get(s, s)


def key_of(r: dict) -> tuple:
    lane = lane_of(r)
    who = r.get("player") or r.get("matchup") or f"{r.get('away', '')}@{r.get('home', '')}"
    line = None if lane == "td" else r.get("line")
    try:
        line = None if line is None else round(float(line), 1)
    except (TypeError, ValueError):
        pass
    return (who, r.get("market"), _side(r), line)


def _band(p: float):
    for lo, hi in BANDS:
        if lo <= p < hi:
            return lo
    return None


def record_table(conn, sport: str = "nfl") -> dict:
    """{(market, side, band): {"n", "hits", "claimed"}} from the journal's
    settled picks in RECORD_CATEGORIES, one per bet across buckets."""
    marks = ",".join("?" * len(RECORD_CATEGORIES))
    rows = conn.execute(
        f"SELECT date, player, market, side, line, hit_prob, status FROM bets "
        f"WHERE sport=? AND category IN ({marks}) AND status IN ('won','lost') "
        f"AND hit_prob IS NOT NULL", (sport, *RECORD_CATEGORIES)).fetchall()
    seen, out = set(), {}
    for r in rows:
        k = (r[0], r[1], r[2], str(r[3] or "").lower(), r[4])
        if k in seen:
            continue
        seen.add(k)
        p = float(r[5])
        band = _band(p)
        if band is None:
            continue
        cell = out.setdefault((r[2], str(r[3] or "").lower(), band), {"n": 0, "hits": 0, "claimed": 0.0})
        cell["n"] += 1
        cell["hits"] += 1 if r[6] == "won" else 0
        cell["claimed"] += p
    return out


def record_check(table: dict | None, market: str, side: str, prob: float):
    """(True/False/None, a sentence) from the record table."""
    band = _band(prob)
    cell = (table or {}).get((market, side, band)) if band is not None else None
    if not cell or cell["n"] < RECORD_MIN_N:
        n = cell["n"] if cell else 0
        return None, f"our record on these is too short to say ({n} settled)"
    rate, claimed = cell["hits"] / cell["n"], cell["claimed"] / cell["n"]
    words = f"picks like this hit {rate:.0%} of {cell['n']} when we said {claimed:.0%}"
    if rate >= claimed - RECORD_SLACK:
        return True, words
    if rate < claimed - RECORD_MISS:
        return False, words
    return None, words


def market_check(r: dict):
    from .odds import american_to_prob
    p = r.get("model_prob")
    implied = r.get("implied_prob")
    if implied is None and r.get("odds"):
        try:
            implied = american_to_prob(int(r["odds"]))
        except (TypeError, ValueError):
            implied = None
    if p is None or implied is None:
        return None, "no book price to compare"
    gap = float(p) - float(implied)
    words = f"books imply {float(implied):.0%}, we say {float(p):.0%}"
    if abs(gap) <= MARKET_AGREE:
        return True, words
    if gap >= MARKET_FAR:
        return False, words + " — far above every book"
    return None, words


def matchup_check(r: dict, leans: dict, td_scores: dict):
    lane = lane_of(r)
    if lane == "td":
        s = td_scores.get(r.get("player") or "")
        if s is None:
            return None, "no matchup read for him"
        if s >= TD_CASE:
            return True, f"matchup {s} of 8 for a touchdown"
        if s <= TD_AGAINST:
            return False, f"matchup only {s} of 8 for a touchdown"
        return None, f"matchup {s} of 8 for a touchdown"
    if lane == "prop":
        lean = leans.get((r.get("player") or "", r.get("team") or "", r.get("market")))
        if not lean:
            return None, "the matchup scan has no read on this market"
        if lean["side"] == _side(r):
            return True, f"matchup read: {lean.get('label') or lean.get('read')}"
        return False, f"matchup read leans the other way ({lean.get('label') or lean.get('read')})"
    return None, ""


def tier_of(checks: dict) -> str:
    """Top: our number, the MATCHUP and the market all agree, and our record
    is not against it. The box's first board (2026-09-26) had 42 Top picks,
    most of them receiving-yards overs the matchup had no read on — the
    model, the market and the record agreeing without the one check Ethan
    built this board around. A pick with no matchup read tops out at
    Strong. Strong: the model passes and at most one check is against it
    with three for, or none against with two for."""
    vals = list(checks.values())
    pos, neg = vals.count(True), vals.count(False)
    if not checks.get("model"):
        return "look"
    if checks.get("matchup") is True and checks.get("market") is True and checks.get("record") is not False:
        return "top"
    if (neg == 0 and pos >= 2) or (neg <= 1 and pos >= 3):
        return "strong"
    return "look"


def _game_of(r: dict, games: list) -> str:
    if r.get("game"):
        return r["game"]
    teams = {r.get("team"), r.get("opponent"), r.get("home"), r.get("away")} - {None, ""}
    for g in games or []:
        if {g.get("home"), g.get("away")} <= teams or (teams and teams <= {g.get("home"), g.get("away")}):
            return f"{g.get('away')}@{g.get('home')}"
    return ""


def build(result: dict, record: dict | None = None) -> dict:
    """{"rows": [...], "tiers": {tier: n}, "lanes": {lane: n}} — the pool,
    checked and tiered, ranked Top first then by our chance."""
    from .gamescan import leans_from_reads
    from .matchpicks import td_matchup, positions_map
    games = result.get("games") or []
    reads = result.get("scan_reads") or {}
    leans = leans_from_reads(reads)
    positions = positions_map(result.get("recommendations") or [], reads)
    usage = {x.get("player"): x.get("usage") for g in reads.values() for x in (g or {}).get("players") or []}

    pool: dict = {}
    order = []

    def add(r: dict, source: str, lines=()):
        if not isinstance(r, dict) or r.get("model_prob") is None or (not r.get("player") and r.get("kind") != "game"):
            return
        k = key_of(r)
        if k not in pool:
            row = dict(r)
            row["sources"] = [source]
            row["case_lines"] = list(lines or [])
            pool[k] = row
            order.append(k)
            return
        row = pool[k]
        if source not in row["sources"]:
            row["sources"].append(source)
        # What the other maker already worked out, where this row lacks it.
        for f in ("matchup_score", "matchup_points", "label", "read", "game", "headshot", "position"):
            if row.get(f) in (None, "") and r.get(f) not in (None, ""):
                row[f] = r[f]
        for t in lines or []:
            if t not in row["case_lines"]:
                row["case_lines"].append(t)

    for r in result.get("most_likely") or []:
        add(r, "likely")
    for g in result.get("matchup_picks") or []:
        for r in (g.get("td") or []) + (g.get("props") or []):
            add(r, "matchup", r.get("matchup_lines"))
    for r in result.get("td_scenarios") or []:
        add(r, "scenario", r.get("scenario_lines"))

    # Every scorer's matchup, off his game's scan.
    by_game = {f"{g.get('away')}@{g.get('home')}": g for g in games}
    td_scores: dict = {}
    for k in order:
        r = pool[k]
        r["game"] = _game_of(r, games)
        if lane_of(r) != "td":
            continue
        if r.get("matchup_score") is not None:
            td_scores[r["player"]] = int(r["matchup_score"])
            continue
        g = by_game.get(r["game"])
        if not g or not g.get("scan"):
            continue
        scan = g["scan"]
        opp, team = r.get("opponent"), r.get("team")
        row = dict(r, position=str(r.get("position") or positions.get(r["player"]) or "").upper())
        m = td_matchup(row, (scan.get("units") or {}).get(opp), (scan.get("redzone") or {}).get(team),
                       (scan.get("redzone") or {}).get(opp), usage=usage.get(r["player"]))
        td_scores[r["player"]] = m["score"]
        for t in m["lines"]:
            if t not in r["case_lines"]:
                r["case_lines"].append(t)

    rows, tiers, lanes = [], {t: 0 for t, _ in TIERS}, {}
    for k in order:
        r = pool[k]
        lane = lane_of(r)
        prob = float(r["model_prob"])
        checks, notes = {}, {}
        checks["model"] = prob >= MODEL_BAR[lane]
        notes["model"] = f"our chance {prob:.0%} (the bar here is {MODEL_BAR[lane]:.0%})"
        checks["matchup"], notes["matchup"] = matchup_check(r, leans, td_scores)
        checks["market"], notes["market"] = market_check(r)
        checks["record"], notes["record"] = record_check(record, r.get("market"), _side(r), prob)
        tier = tier_of(checks)
        r.update({"lane": lane, "tier": tier, "tier_label": TIER_LABEL[tier],
                  "checks": checks, "check_notes": notes,
                  "matchup_score": td_scores.get(r.get("player") or "") if lane == "td" else r.get("matchup_score")})
        rows.append(r)
        tiers[tier] += 1
        lanes[lane] = lanes.get(lane, 0) + 1
    rank = {t: i for i, (t, _) in enumerate(TIERS)}
    rows.sort(key=lambda r: (rank[r["tier"]], -float(r["model_prob"])))
    return {"rows": rows, "tiers": tiers, "lanes": lanes}


def journal_rows(board: dict, tier: str) -> list:
    """The board's rows of one tier, for the paper book."""
    return [r for r in (board or {}).get("rows") or [] if r.get("tier") == tier]
