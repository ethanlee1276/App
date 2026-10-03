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
#: A league whose own model sets a different bar. Empty since 2026-10-03:
#: the NHL's 65% went with its Most Likely floor (see likely.SPORT_MIN_PROB)
#: and hockey's model check asks for the shared 58% like every league.
SPORT_MODEL_BAR: dict = {}
#: The main Most Likely list's bar (likely.MIN_PROB) — a touchdown under it
#: here is said as matchup-backed (see `build`).
LIKELY_BAR = 0.55
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
#: EVERY SPORT GETS THE BOARD (Ethan, 2026-09-26: "every other sport that
#: has the Qellys' top picks is getting the same remodel"). What the
#: matchup check reads differs by sport, and where a sport has no matchup
#: read the check says so and its picks top out at Strong — a Top pick is
#: one the matchup backs, in every sport:
#:   nfl, cfb   the game scan's lean on this player and market, and for a
#:              scorer his touchdown matchup of 8 (college's defence ranks
#:              read as among 32 — tdscenarios.rank32);
#:   mlb        the MLB scan's read (engine/mlb/scan — platoon split, the
#:              starter's slugging allowed by hand, expected stats, park,
#:              the opponent's strikeout rate…); where it has none, the
#:              projection's own Matchup step, when it moved the number at
#:              least MODEL_MATCHUP_STEP toward this side;
#:   nba, wnba  none yet.
MATCHUP_SOURCE = {"nfl": "scan", "cfb": "scan", "mlb": "scan+model",
                  # Hockey's read (engine/nhl/scan, 2026-10-03): the opposing
                  # starter, shots allowed, expected goals, rest, ice time.
                  "nhl": "scan"}
MODEL_MATCHUP_STEP = 0.03
#: The journal buckets whose settled rows make the record.
RECORD_CATEGORIES = ("likely", "matchup_td", "matchup_prop", "td_scenario", "board", "bold")
#: Chance bands the record is read in (ledger.LIKELY_BANDS).
BANDS = ((0.30, 0.45), (0.45, 0.60), (0.60, 0.75), (0.75, 1.01))

TIERS = (("top", "Top pick"), ("strong", "Strong"), ("look", "Worth a look"))
#: The paper bucket for picks the board held back (see `held_reason`).
HELD_CATEGORY, HELD_LABEL = "held", "Held back"


def held_reason(r: dict, checks: dict) -> str | None:
    """Why this pick comes OFF the board, or None — it stays.

    Ethan, 2026-10-04: "the point of most likely is to give picks to what
    we think is going to happen based off all data we collect ... offense
    and defense and game script and past picks wins and losses ... I don't
    wanna take picks off because they are going bad, only if they also
    don't link to what we are trying to achieve."

    So a losing record ALONE never takes a pick off; the record's
    correction lowers its chance and its tier, and it stays. It comes off
    only when TWO of our own reads say no and only the model says yes:

      * the record has PROVEN that picks like it over-claim — likelycal
        (its maker on its side) or likelyctx (a football flag) lowered
        its chance on games the fit never saw; and
      * the offence-against-defence read leans the OTHER way (the matchup
        check says no — not "cannot say", which keeps it).

    A pick already posted (``locked``) is never taken off; it keeps its
    seat until its game, as every posted pick does."""
    if r.get("locked") or checks.get("matchup") is not False:
        return None
    proven = r.get("ctx_note") or r.get("cal_note")
    if not proven:
        return None
    return f"held back: {proven}, and our matchup read leans the other way"
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


#: THE TIERS WHOSE CARDS SHOW THEIR TIER'S REAL HIT RATE instead of our
#: chance. Ethan, 2026-09-29, told "Worth a look" claims 59% and hits 48%
#: (123-132 on the one board): "show the real hit rate". Top pick and
#: Strong hit about what they claim (62% each), so they keep our number.
REAL_RATE_TIERS = ("look",)


def tier_record(conn, sport: str = "nfl") -> dict:
    """``{tier key: {"n", "hits"}}`` — the one board's settled picks by
    tier (journal book ``board``, the tier label as the grade)."""
    label_to_key = {label: key for key, label in TIERS}
    out: dict = {}
    for grade, status in conn.execute(
            "SELECT grade, status FROM bets WHERE sport=? AND category='board' "
            "AND status IN ('won','lost')", (sport,)).fetchall():
        key = label_to_key.get(str(grade or ""))
        if not key:
            continue
        cell = out.setdefault(key, {"n": 0, "hits": 0})
        cell["n"] += 1
        cell["hits"] += 1 if status == "won" else 0
    return out


def real_rate(tiers_seen: dict | None, tier: str):
    """``(rate, n)`` for a tier in REAL_RATE_TIERS with RECORD_MIN_N settled,
    else ``(None, n)``."""
    cell = (tiers_seen or {}).get(tier) or {}
    n = int(cell.get("n") or 0)
    if tier not in REAL_RATE_TIERS or n < RECORD_MIN_N:
        return None, n
    return round(cell["hits"] / n, 4), n


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


def record_seen(table: dict | None, market: str, side: str, prob: float) -> dict:
    """What the record check read, for the card to say it in numbers:
    settled picks like this one, how many it needs before it speaks, and
    (once it does) the rate they hit against the rate we claimed."""
    band = _band(prob)
    cell = (table or {}).get((market, side, band)) if band is not None else None
    n = cell["n"] if cell else 0
    out = {"n": n, "need": RECORD_MIN_N}
    if n >= RECORD_MIN_N:
        out.update(rate=round(cell["hits"] / n, 4), claimed=round(cell["claimed"] / n, 4))
    return out


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


def model_matchups(recs: list) -> dict:
    """{(player, market): (multiplier, why)} — each pick's Matchup step,
    off the projection chain the pipeline publishes (engine/chain)."""
    out = {}
    for rec in recs or []:
        for st in ((rec or {}).get("chain") or {}).get("steps") or []:
            if st.get("key") == "matchup" and st.get("mult") is not None:
                out[(rec.get("player") or "", rec.get("market"))] = (float(st["mult"]), st.get("why") or "")
                break
    return out


def _model_matchup(r: dict, steps: dict):
    got = steps.get((r.get("player") or "", r.get("market")))
    if not got:
        return None, "the model has no matchup step for this market"
    mult, why = got
    pct = f"{(mult - 1) * 100:+.0f}%"
    toward = mult - 1 if _side(r) == "over" else 1 - mult
    words = f"matchup moved our number {pct}" + (f" ({why})" if why else "")
    if toward >= MODEL_MATCHUP_STEP:
        return True, words
    if toward <= -MODEL_MATCHUP_STEP:
        return False, words + " — against this side"
    return None, words + " — not enough to call"


def matchup_check(r: dict, leans: dict, td_scores: dict, steps: dict | None = None,
                  source: str = "scan"):
    lane = lane_of(r)
    if source == "none" and lane != "game":
        return None, "no matchup read for this sport yet"
    if source == "model" and lane == "prop":
        return _model_matchup(r, steps or {})
    if source == "scan+model" and lane == "prop" \
            and not leans.get((r.get("player") or "", r.get("team") or "", r.get("market"))):
        return _model_matchup(r, steps or {})
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


#: HOW HARD THE MATCHUP BACKS A PICK, for the order inside a tier. Ethan,
#: 2026-09-26, the NFL board: Kincaid (a Good matchup) sat #1 of the Top
#: picks "with the breakout candidates below him". The tier used the
#: matchup, but the order inside it was our chance alone, so the read never
#: touched the ranking. Now a pick the matchup backs strongly — a breakout
#: or avoid read, a touchdown matchup of STRONG_TD or better — ranks ahead
#: of one it merely backs (a good or tough read, a scorer at TD_CASE, the
#: model's own matchup step), and only then by our chance. The same rule in
#: every sport; a sport with no matchup read ranks by chance as before.
STRONG_READS = ("breakout", "avoid")
STRONG_TD = 6


def matchup_strength(r: dict, leans: dict, td_scores: dict, backed) -> int:
    """2 strongly backed, 1 backed, 0 not (or no read)."""
    if backed is not True:
        return 0
    lane = lane_of(r)
    if lane == "td":
        return 2 if (td_scores.get(r.get("player") or "") or 0) >= STRONG_TD else 1
    lean = leans.get((r.get("player") or "", r.get("team") or "", r.get("market")))
    return 2 if lean and lean.get("read") in STRONG_READS else 1


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


def build(result: dict, record: dict | None = None, sport: str = "nfl",
          tiers_seen: dict | None = None, calibration: dict | None = None) -> dict:
    """{"rows": [...], "tiers": {tier: n}, "lanes": {lane: n},
    "matchup_source": ...} — the pool, checked and tiered, ranked Top
    first, then by how hard the matchup backs it (`matchup_strength`),
    then by our chance."""
    source = MATCHUP_SOURCE.get(sport, "none")
    steps = model_matchups(result.get("recommendations") or []) if source in ("model", "scan+model") else {}
    from .gamescan import leans_from_reads
    from .matchpicks import td_matchup, positions_map
    games = result.get("games") or []
    reads = result.get("scan_reads") or {}
    leans = leans_from_reads(reads)
    positions = positions_map(result.get("recommendations") or [], reads)
    usage = {x.get("player"): x.get("usage") for g in reads.values() for x in (g or {}).get("players") or []}

    pool: dict = {}
    order = []
    capped: list = []
    from .likely import HEAVIEST_PRICE

    def add(r: dict, source: str, lines=()):
        if not isinstance(r, dict) or r.get("model_prob") is None or (not r.get("player") and r.get("kind") != "game"):
            return
        # THE MAIN LIST'S -250 CAP ON EVERYTHING POOLED IN. Ethan,
        # 2026-09-27: Gibbs at -320 was a Top pick through the matchup
        # picks while the main list would never post him — "Yes cap at
        # -250". The main list's own rows are left to it: a pick it posted
        # and then held after the price moved (likely's hold) stays.
        if source != "likely" and _past(r.get("odds"), HEAVIEST_PRICE):
            capped.append({"player": r.get("player"), "market": r.get("market"),
                           "odds": r.get("odds"), "source": source})
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
        add(r, "likely", r.get("bold_why"))
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
                       (scan.get("redzone") or {}).get(opp), n_teams=int(scan.get("n_teams") or 32),
                       usage=usage.get(r["player"]))
        td_scores[r["player"]] = m["score"]
        for t in m["lines"]:
            if t not in r["case_lines"]:
                r["case_lines"].append(t)

    # THE RECORD'S CORRECTION, BEFORE A SINGLE CHECK (engine/likelycal;
    # Ethan, 2026-10-03: "make the picks better ... I don't want to really
    # get rid of any most likely bets"). Each pick's chance is pulled
    # toward its price by as much as picks from the same maker on the same
    # side have earned in the journal, so the checks, the tier and the
    # order all read the honest number. Nothing leaves the pool. No store
    # (or a correction that failed its held-out test) changes nothing.
    try:
        from .likelycal import apply as _calibrate
        _calibrate([pool[k] for k in order], sport, calibration)
    except Exception:                                        # noqa: BLE001
        pass
    # THE SCOUT'S READ (engine/likelyctx; Ethan, 2026-10-03: "think like a
    # human ... general football knowledge"). Every football row gets the
    # flags a football person would raise — an under in a projected
    # shootout, a rushing over on a team expected to trail, his first game
    # back — written on the card. A flag lowers a chance only where the
    # graded record has proven, out of sample, that picks carrying it
    # over-claim; until that store exists the flags are notes and nothing
    # moves.
    try:
        from . import likelyctx as _ctx
        if sport in _ctx.SPORTS:
            _rows = [pool[k] for k in order]
            _ctx.annotate(_rows, result)
            _ctx.apply(_rows, sport)
    except Exception:                                        # noqa: BLE001
        pass
    rows, tiers, lanes, held = [], {t: 0 for t, _ in TIERS}, {}, []
    for k in order:
        r = pool[k]
        lane = lane_of(r)
        prob = float(r["model_prob"])
        checks, notes = {}, {}
        bar = SPORT_MODEL_BAR.get(sport, MODEL_BAR)[lane]
        checks["model"] = prob >= bar
        notes["model"] = (f"our chance {prob:.0%} (the bar here is {bar:.0%})"
                          + (f" — {r['cal_note']}" if r.get("cal_note") else "")
                          + (f" — {r['ctx_note']}" if r.get("ctx_note") else ""))
        checks["matchup"], notes["matchup"] = matchup_check(r, leans, td_scores, steps, source)
        # NOT A SECOND OPINION ON ITSELF (Ethan, 2026-10-03, "yeah make the
        # tier change"). A pick only the matchup picks or the touchdown
        # scenarios made was made BY the matchup read, so that read agreeing
        # with it is the same opinion counted twice — which is how the NFL
        # matchup picks reached Top pick and went 4-14 there. Its matchup
        # check says nothing either way; the pick stays on the board, and it
        # can still be Strong on the model, the market and the record.
        if checks["matchup"] is True and not ({"likely"} & set(r.get("sources") or ())):
            checks["matchup"] = None
            notes["matchup"] = (notes["matchup"] + " — but this pick came from the matchup read itself,"
                                " so it does not count as a second opinion")
        checks["market"], notes["market"] = market_check(r)
        checks["record"], notes["record"] = record_check(record, r.get("market"), _side(r), prob)
        why_held = held_reason(r, checks)
        if why_held:
            r.update({"lane": lane, "checks": checks, "check_notes": notes, "held_note": why_held,
                      "tier": "held", "tier_label": HELD_LABEL})
            held.append(r)
            continue
        tier = tier_of(checks)
        # A TOUCHDOWN UNDER THE MAIN LIST'S BAR, BACKED BY THE MATCHUP.
        # Ethan, 2026-09-27, on Breece Hall at 42% reading "Top pick" beside
        # St. Brown at 52% reading "reserve — ranked, not recommended": he
        # chose to keep the matchup picks' tiers and say what they are. So
        # a pick the matchup picks or the scenarios put here under 55% says
        # its chance and that the matchup backs it, and is not a reserve.
        if lane == "td" and prob < LIKELY_BAR and {"matchup", "scenario"} & set(r.get("sources") or ()):
            r["backed_note"] = f"{prob:.0%} — backed by the matchup"
            r.pop("reserve", None)
            r.pop("reserve_note", None)
        r.update({"lane": lane, "tier": tier, "tier_label": TIER_LABEL[tier],
                  "checks": checks, "check_notes": notes,
                  "record_seen": record_seen(record, r.get("market"), _side(r), prob),
                  "matchup_strength": matchup_strength(r, leans, td_scores, checks["matchup"]),
                  "matchup_score": td_scores.get(r.get("player") or "") if lane == "td" else r.get("matchup_score")})
        # THE TIER'S REAL HIT RATE, on the tiers that claim more than they
        # hit (REAL_RATE_TIERS): the card shows it in place of our chance.
        rate, n_seen = real_rate(tiers_seen, tier)
        if rate is not None:
            r["tier_rate"], r["tier_n"] = rate, n_seen
        else:
            r.pop("tier_rate", None)
            r.pop("tier_n", None)
        rows.append(r)
        tiers[tier] += 1
        lanes[lane] = lanes.get(lane, 0) + 1
    rank = {t: i for i, (t, _) in enumerate(TIERS)}
    rows.sort(key=lambda r: (rank[r["tier"]], -r["matchup_strength"], -float(r["model_prob"])))
    return {"rows": rows, "tiers": tiers, "lanes": lanes, "matchup_source": source,
            "capped": capped, "held": held}


def _past(odds, cap: int) -> bool:
    """A price heavier than ``cap`` (e.g. -320 against -250)."""
    try:
        return int(odds) < cap
    except (TypeError, ValueError):
        return False


def attach(result: dict, sport: str, conn=None) -> str:
    """Build the board onto ``result["likely_board"]`` with this sport's
    record; the line for the build log. Never raises — a board that fails
    leaves the page on its older Most Likely shelves."""
    try:
        if conn is None:
            from . import ledger
            try:
                conn = ledger.connect()
            except Exception:                                # noqa: BLE001
                conn = None
        try:
            rec = record_table(conn, sport) if conn is not None else {}
        except Exception:                                    # noqa: BLE001
            rec = {}
        try:
            seen = tier_record(conn, sport) if conn is not None else {}
        except Exception:                                    # noqa: BLE001
            seen = {}
        board = build(result, record=rec, sport=sport, tiers_seen=seen)
        result["likely_board"] = board
        t = board["tiers"]
        return (f"Most Likely board: {len(board['rows'])} pick(s) — {t.get('top', 0)} top, "
                f"{t.get('strong', 0)} strong, {t.get('look', 0)} worth a look")
    except Exception as exc:                                 # noqa: BLE001
        return f"⚠️  one Most Likely board skipped: {exc}"


def journal(lconn, result: dict, sport: str, date: str = "") -> int:
    """The board's rows to the paper book, one bucket per tier (category
    ``board``, the tier as the grade) — as nfl_build does."""
    from . import ledger
    n = 0
    for tier, label in TIERS:
        n += ledger.log_most_likely(
            lconn, {"sport": sport, "date": date or result.get("date", ""), "games": result.get("games") or [],
                    "most_likely": journal_rows(result.get("likely_board"), tier)},
            depth=None, category="board", grade_label=label) or 0
    n += journal_held(lconn, result, sport, date)
    return n


def journal_held(lconn, result: dict, sport: str, date: str = "") -> int:
    """The held-back picks on paper in their own bucket, so the record — not
    the argument in `held_reason` — says whether holding them was right."""
    from . import ledger
    held = (result.get("likely_board") or {}).get("held") or []
    if not held:
        return 0
    return ledger.log_most_likely(
        lconn, {"sport": sport, "date": date or result.get("date", ""), "games": result.get("games") or [],
                "most_likely": held}, depth=None, category=HELD_CATEGORY, grade_label=HELD_LABEL) or 0


def journal_rows(board: dict, tier: str) -> list:
    """The board's rows of one tier, for the paper book."""
    return [r for r in (board or {}).get("rows") or [] if r.get("tier") == tier]
