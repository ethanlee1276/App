"""Fantasy draft kit — turn last season's usage into a draft board.

The same doctrine as the rest of the fantasy engine (volume is predictive,
efficiency is noise), pointed at the one decision the season starts with.
Three ideas, each of which most draft content gets wrong:

* **Value over replacement, not points.** The 4th QB scores more than the
  20th WR, and drafting him early is still usually wrong: the QB you can
  get ten rounds later scores nearly as much, and the WR you passed on has
  no such substitute. Every player is valued against the best freely
  available body at his own position (the "replacement"), which is what
  actually decides a start/sit — and a draft pick.
* **Tiers, not ranks.** The difference between WR7 and WR9 is noise; the
  cliff between tier 2 and tier 3 is real. Tier breaks are placed where
  the projected-points gap between consecutive players is large, so the
  board says "these six are interchangeable, then it drops" instead of
  pretending rank 12 beats rank 13.
* **Projection = volume first, production second.** Where play-by-play
  xFP exists it leads the blend; actual PPR confirms. A player who scored
  above his opportunity is regression risk and the board says so.

Honesty constraints, stated because they matter at the table: everything
here is LAST season run forward. The board knows nothing about rookies
(they simply aren't on it), coaching changes, free-agency moves, or camp
news. The tiers structure the draft; picking within a tier is where your
own news-reading beats any model built on stale volume.
"""

from __future__ import annotations

from .fantasy import _weekly, _pbp_weekly, _short_key, league_rates, USAGE_MIN_WEEKS

# 12-team, 1QB / 2RB / 2WR / 1TE / 1FLEX. The flex is mostly RB/WR in
# practice, so replacement rank = starters*teams plus a flex share.
DEFAULT_TEAMS = 12
REPLACEMENT_RANK = {"QB": 12, "RB": 26, "WR": 26, "TE": 12}
# A new tier starts when the projected-PPG gap to the player above is at
# least this. Within a position, ~1.2 PPG over a season is a real cliff.
TIER_GAP = 1.2
MIN_GAMES = 6            # below this a per-game average is mostly noise
BOARD_POSITIONS = ("QB", "RB", "WR", "TE")
# xFP leads the blend where it exists (it values every opportunity by where
# it happened); actual production confirms. For QBs there is no volume
# model — attempts are shown as context and production carries the load.
XFP_WEIGHT = 0.6
SLEEPER_GAP = 1.5        # xFP above actual by this much = usage says buy


def _players(conn, season: int) -> list[dict]:
    data = _weekly(conn, season)
    rates = league_rates(conn, season)
    pbp = _pbp_weekly(conn, season)
    out = []
    for player, p in data["players"].items():
        pos = (p["position"] or "").upper()
        if pos not in BOARD_POSITIONS:
            continue
        weeks = sorted(p["weeks"])
        n = len(weeks)
        if n < USAGE_MIN_WEEKS:
            continue
        ppg = sum(m.get("fp_ppr", 0.0) for m in p["weeks"].values()) / n
        tgt = sum(m.get("targets", 0.0) for m in p["weeks"].values()) / n
        car = sum(m.get("carries", 0.0) for m in p["weeks"].values()) / n
        # RECEPTIONS, carried so a PPR variant is arithmetic rather than a
        # guess. The alternative was estimating them from targets times an
        # assumed catch rate, which invents the one number the format
        # turns on. They are already in the weekly pull; only the board
        # dropped them.
        rec = sum(m.get("receptions", 0.0) for m in p["weeks"].values()) / n
        att = sum(m.get("pass_att", 0.0) for m in p["weeks"].values()) / n

        xfp_vals = [m["xfp"] for m in pbp.get(_short_key(player, p["team"]),
                                              {}).values() if "xfp" in m]
        rate = rates.get(pos)
        # QBs never take the volume paths. xFP values targets and carries —
        # for a quarterback that is his SCRAMBLES and nothing else, so the
        # blend rated Josh Allen (24 PPG in the DB) at a 12.6 projection
        # while a thin-sample rookie with no xFP rows "led" the position.
        # Passing production has no volume model here; for QBs the honest
        # projection is their scoring itself, labeled as such.
        if pos != "QB" and len(xfp_vals) >= USAGE_MIN_WEEKS:
            xppg = sum(xfp_vals) / len(xfp_vals)
            basis = "xfp"
        elif pos != "QB" and rate and (tgt + car) > 0:
            xppg = rate[0] * tgt + rate[1] * car
            basis = "volume"
        else:
            xppg = ppg
            basis = "points"
        proj = XFP_WEIGHT * xppg + (1.0 - XFP_WEIGHT) * ppg
        out.append({
            "player": player, "team": p["team"], "position": pos,
            "games": n, "ppg": round(ppg, 1), "xppg": round(xppg, 1),
            "proj": round(proj, 1), "basis": basis,
            "targets_pg": round(tgt, 1), "carries_pg": round(car, 1),
            "rec_pg": round(rec, 2),
            "pass_att_pg": round(att, 1),
            "small_sample": n < MIN_GAMES,
        })
    return out


def _assign_tiers(rows: list[dict], gap: float = TIER_GAP) -> None:
    """Tier breaks at real cliffs in projected PPG (rows already sorted
    descending). Mutates in place: adds ``tier`` (1-based)."""
    tier = 1
    for i, r in enumerate(rows):
        if i and rows[i - 1]["proj"] - r["proj"] >= gap:
            tier += 1
        r["tier"] = tier


def build_draft_kit(conn, season: int, teams: int = DEFAULT_TEAMS,
                    sleeper: dict | None = None) -> dict:
    """The full kit: per-position tiers, a VORP-ordered overall board,
    replacement baselines, and the usage-says-buy sleepers list.

    `sleeper` is the players blob. Handed in rather than fetched, and
    optional: without it the board is exactly what it was before — last
    season's usage and nobody else. With it, players the market drafts
    that this board cannot see are placed at the market's own rank (see
    engine/draftmarket.py), which matters most for the mock simulator,
    whose draft pool IS this board.
    """
    players = _players(conn, season)

    # OUT OF THE LEAGUE MEANS OFF THE BOARD. Ethan, 2026-08-24: "the
    # fantasy draft is using old retired players. it used tom brady and
    # kenneth gainwell." The board is built from the newest INGESTED
    # season, and when that lags the calendar it faithfully projects
    # players who have since retired — and the mock simulator drafts
    # straight from this board, so a simulated room was spending real
    # picks on men who no longer play.
    #
    # The roster layer already knew: apply_current_rosters stamps
    # `roster_flag: "inactive"` on exactly these rows. A flag is the
    # right treatment for a free agent (an active player somebody may
    # yet sign) and the wrong one for a retirement — nobody can draft
    # Tom Brady, so he does not belong on a draft board at any rank.
    # Dropped BEFORE tiers and replacement, so the baselines are
    # computed over a pool of people who exist.
    #
    # Only players Sleeper POSITIVELY marks inactive go: a usage row
    # with no Sleeper match at all is kept, because a name-join failure
    # must never erase a real player. Active-but-teamless stays too —
    # that is the free-agent case the flag handles.
    dropped: list[str] = []
    if sleeper:
        from .offseason import _lookup, index_players
        idx = index_players(sleeper)
        kept = []
        for r in players:
            cur = _lookup(idx, r["player"], r["position"])
            if cur is not None and not cur["active"]:
                dropped.append(r["player"])
            else:
                kept.append(r)
        players = kept

    # BEFORE tiers, VORP and replacement, deliberately. Placing them
    # afterwards would rank them against a replacement level computed as
    # though they did not exist — and the whole reason a missing rookie
    # class distorts the board is that it moves who is actually free.
    from .draftmarket import place_missing, summary as _market_summary
    placed = place_missing(players, sleeper)
    players = players + placed
    market = _market_summary(placed)

    by_pos: dict[str, list[dict]] = {}
    for r in players:
        by_pos.setdefault(r["position"], []).append(r)

    scale = teams / DEFAULT_TEAMS
    baselines: dict[str, float] = {}
    for pos, rows in by_pos.items():
        rows.sort(key=lambda r: r["proj"], reverse=True)
        _assign_tiers(rows)
        rank = max(2, round(REPLACEMENT_RANK.get(pos, 12) * scale))
        # Replacement = the best player your league-mates can grab for free.
        # If the position is shallower than the replacement rank, the last
        # man on the list is the baseline.
        baseline = rows[min(rank, len(rows)) - 1]["proj"] if rows else 0.0
        baselines[pos] = round(baseline, 1)
        for i, r in enumerate(rows):
            r["pos_rank"] = i + 1
            r["vorp"] = round(r["proj"] - baseline, 1)

    board = sorted(players, key=lambda r: r["vorp"], reverse=True)

    # THE ONE FACT ON THE BOARD. Everything else here is a projection and
    # can be argued with; the schedule is published. A bye decides whether
    # the roster somebody just drafted has three starters missing in week
    # eleven, and the kit had no idea the concept existed.
    from .byes import bye_weeks, attach as _attach_byes
    _attach_byes(board, bye_weeks(conn, season))

    # Usage says buy: expected clearly above actual — the draft-day version
    # of buy-low. (Sell-highs matter less at the table: the market already
    # prices last year's points; the board's lower proj handles it.)
    # A market-placed player can never be a sleeper: "usage says buy"
    # compares expected against actual, and he has neither. The zeroes he
    # carries would fail the gap test anyway — excluded explicitly so a
    # later change to those defaults cannot quietly let him in.
    sleepers = sorted(
        (r for r in players
         if r["basis"] not in ("points", "market")
         and r["xppg"] - r["ppg"] >= SLEEPER_GAP),
        key=lambda r: r["xppg"] - r["ppg"], reverse=True)[:10]

    return {
        "season": season, "teams": teams,
        # Who was removed and why, so a vanished name is checkable
        # rather than mysterious. Count plus a capped sample — a long
        # retirement class should not bloat the payload.
        "dropped_inactive": {"n": len(dropped), "players": dropped[:20]},
        "replacement": baselines,
        "market": market,
        "board": board[:150],
        "tiers": {pos: rows[:40] for pos, rows in by_pos.items()},
        "sleepers": sleepers,
        "notes": [
            "Projections are last season's volume run forward. Players "
            "with no last-season usage \u2014 rookies, and anyone who "
            "missed the year \u2014 are placed at the market\u2019s own "
            "draft rank instead, marked \u201cmarket\u201d, because we "
            "have no independent read on a player we have never seen "
            "play. The board still knows nothing about coaching changes "
            "or scheme.",
            "Draft by tier, not rank: inside a tier the differences are "
            "noise, and your read on camp news beats the model's.",
            "VORP is points over the best freely-available player at the "
            "same position — it is why the 4th-best QB is worth less than "
            "the 15th-best WR.",
            "Bye weeks come off the published schedule, not a table — a "
            "hard-coded one is silently wrong the year the league moves a "
            "week, and it moves most years.",
        ],
    }
