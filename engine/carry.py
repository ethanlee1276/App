"""The prior-season carry — giving weeks 1-3 a baseline without faking one.

THE HOLE THIS FILLS
-------------------
``player_game_logs`` keeps only ``0 < wk < upto_week`` — one season, no
cross-season carry anywhere — and ``build_slate`` skips any player with
fewer than three logs. Week 1 has zero prior weeks, week 2 has one, week 3
has two. Measured on the cached 2025 season:

    week 1: 0 props   week 2: 0 props   week 3: 0 props   week 4: 235 props

So the NFL prop board switched itself off for the first three weeks of
every season, which for 2026 is Sep 9 to Oct 1. The game-level board was
never affected — ``build_games`` needs only the schedule.

WHAT WAS MEASURED BEFORE ANY OF THIS WAS WRITTEN
------------------------------------------------
Fitted on 2024 → 2025 weeks 1-3, REG only: given a player's last season,
how well does it predict his first three games of the next one, and what
shrink toward the positional mean minimises the error?

The answer, sweeping ``k`` in ``w = n/(n+k)`` and scoring MAE:

    market       best k     MAE k=0    MAE k=2    MAE k=inf
    pass_yds        2        50.53      50.18       54.46
    rush_yds        0        16.64      16.64       26.82
    rec_yds         2        14.96      14.88       20.76
    receptions      2         1.10       1.09        1.64

Two things come out of that, and the first one corrected the plan:

* **A carried season should be used at close to face value.** The shrink
  that helps is tiny — at 17 games ``k=2`` pulls only 11% toward the
  positional mean, and the gain is under 1%. Shrinking all the way to the
  positional mean (``k=inf``) costs 39% on receiving yards. The original
  design assumed a stale season needed heavy regression; measured, that
  would have made the projection materially worse.

* **The shrink is nearly cosmetic and is kept for the thin cases.** Its
  real work is at low ``n``, where ``n/(n+2)`` pulls harder on its own.

``PRIOR_GAMES`` is therefore 2.0 and ``MIN_PRIOR_GAMES`` is 6, at which
floor k=2 was fractionally the best of the sweep (14.27 vs 14.33 at k=0).

THE RESET GATE, AND WHY IT WARNS RATHER THAN DELETES
-----------------------------------------------------
§5's reset rule says a trade or a coordinator change resets the sample and
the stale games should be discarded. ``engine/reset.py`` implements that
for MID-SEASON changes, where discarding leaves you the games since.

The offseason case is not the same shape, and the difference matters: an
offseason trade leaves NOTHING to project from, so "discard" means the
player drops off the board entirely — the exact failure this module
exists to fix. That is a real cost, so it needed evidence, and the
evidence does not support paying it:

* Raw MAE said movers were BETTER than stayers for receivers (12.00 vs
  14.96), which is only the level confound — movers averaged 30.1 yards
  against 36.8, and MAE is not scale-free.
* Level-matched on relative error, inside baseline-median halves, the
  comparison is inconsistent in both directions: rec_yds -46% / -0%,
  receptions -6% / +20%, rush_yds -12% / +11%, pass_yds +88% / -43%. The
  cells suggesting movers are worse are n=6, n=6 and n=18, and each is
  contradicted by a cell of similar or greater size going the other way.
* Fitting the shrink separately for movers returns the SAME k=2. If a
  changed team really made last season stale, movers would want more
  shrink than stayers. They do not.

So an offseason reset is **detected and reported, not applied**. The
player keeps his carried baseline and the card says he changed teams or
his coach did, which tells the reader the true thing without deleting 23%
of the receiver board (42 of 182) on a hypothesis this data refuses to
support.

``DISCARD_ON_RESET`` exists so that decision can be revisited rather than
rediscovered. Flipping it to True is justified when there is a per-market
sample of movers large enough to separate them from stayers on relative
error at matched baseline level — roughly 60+ movers in one market, which
is three or four seasons of accumulation, not one.

WHAT IS AND IS NOT DETECTABLE ACROSS AN OFFSEASON
--------------------------------------------------
* **Team change** — the current roster's team against the player's last
  team in the prior season's logs. Clean and complete.
* **Head-coach change** — from the schedule feed, which carries a coach on
  every row for both seasons. A PROXY for "coordinator change", the same
  under-detecting proxy ``reset.py`` already documents.
* **Role change** — NOT detectable. It needs snap share, and the current
  season has no snaps until it has games. Under-detection, never false
  detection, exactly as in ``reset.py``.

Rookies need no special case: a player with no prior-season logs simply
gets no carry and does not reach the board.

Standard library only. Reads the same cached nflverse feeds as the rest.
"""

from __future__ import annotations

from .models import GameLog

#: The k in ``w = n/(n+k)`` — how hard a carried season is pulled toward
#: the positional mean. Fitted on 2024 → 2025 weeks 1-3; see the module
#: docstring for the sweep this came from.
PRIOR_GAMES = 2.0

#: Fewest prior-season games that count as a season worth carrying. Below
#: this the player is left off rather than projected from a cameo.
MIN_PRIOR_GAMES = 6

#: Detected offseason resets warn on the card. They do not delete the
#: sample — the measurement behind that decision is in the docstring, as is
#: the evidence that would justify flipping this.
DISCARD_ON_RESET = False

#: …but they are not STAKED either. A mover keeps his baseline and stays on
#: the board; he just cannot become a recommended bet while that baseline is
#: the only thing we have.
#:
#: This is deliberately NOT a claim that movers are worse — the fit says the
#: opposite, or rather says it cannot tell, which is the point. n is 9 to 42
#: per market, and a 20% degradation would be invisible at that size. So the
#: measurement licenses keeping them on the board (there is no evidence they
#: are bad) and does not license staking them (there is no evidence they are
#: fine). Those are different questions and the honest answer differs.
#:
#: The asymmetry decides it: a bet not taken costs nothing, a bet taken on a
#: baseline describing a job the player no longer holds costs money. Weeks
#: 1-3 are also where the model is least checkable — nflguard needs 25
#: settled bets before it can say anything at all — so this is the stretch
#: where caution is cheapest.
STAKE_ON_RESET = False

#: Kinds of offseason reset, reusing reset.py's vocabulary so a reader sees
#: one set of labels across both rules.
TRADE = "team change"
COACH = "coach change"


def shrink_weight(n: int, prior_games: float = PRIOR_GAMES) -> float:
    """``n/(n+k)`` — the weight the player's own carried mean keeps.

    1.0 would be face value, 0.0 the positional mean alone. At the fitted
    k=2 a full 17-game season keeps 0.89 of itself.
    """
    if n <= 0:
        return 0.0
    return n / (n + prior_games)


def positional_means(rows: list[dict], market: str) -> dict[str, float]:
    """Mean value per position for one market — the anchor of the shrink.

    Built from the SAME season being carried, so it describes the league
    the player was actually in rather than an average from somewhere else.

    The construction is the mean of QUALIFIED PLAYERS' SEASON MEANS, not
    the mean of every player-game row, and the two are not the same
    number. Averaging rows lets every backup who threw four passes in
    garbage time vote: measured on 2025, that pulled the QB anchor to
    184.1 against 196.7 for the players who actually held a job — 38 of
    the 81 quarterbacks in the feed cleared ``MIN_PRIOR_GAMES``.

    It matters because ``PRIOR_GAMES`` was FITTED against this
    construction. Shipping the row-mean instead would leave the constant
    calibrated for an anchor the code no longer computes, which is a
    silent kind of wrong — the shrink would still look fitted and would
    be pulling somewhere else.
    """
    from .sources.nflverse import MARKET_COLUMNS, _f, _s, _regular_season

    cols = MARKET_COLUMNS[market]
    per_player: dict[tuple, list[float]] = {}
    for r in _regular_season(rows):
        pos = _s(r, "position", "position_group").upper()
        name = _s(r, "player_display_name", "player_name", "full_name")
        if not pos or not name:
            continue
        per_player.setdefault((pos, name), []).append(_f(r, *cols))

    buckets: dict[str, list[float]] = {}
    for (pos, _name), vals in per_player.items():
        if len(vals) < MIN_PRIOR_GAMES:
            continue
        buckets.setdefault(pos, []).append(sum(vals) / len(vals))
    return {p: sum(v) / len(v) for p, v in buckets.items() if v}


def carried_logs(rows: list[dict], player: str, market: str) -> list[GameLog]:
    """One player's prior-season games, tagged ``prior=True``.

    Most recent first, like ``player_game_logs``, but the weeks belong to
    the PREVIOUS season — which is why every one of them carries the flag.
    Anything comparing these weeks against a current-season week without
    checking ``prior`` is reading last September as though it were this
    one.
    """
    from .sources.nflverse import MARKET_COLUMNS, _f, _s, _regular_season

    cols = MARKET_COLUMNS[market]
    out = []
    for r in _regular_season(rows):
        name = _s(r, "player_display_name", "player_name", "full_name")
        if name != player:
            continue
        wk = int(_f(r, "week", default=0))
        if wk <= 0:
            continue
        out.append(GameLog(week=wk, opponent=_s(r, "opponent_team", "opponent"),
                           value=_f(r, *cols), home=True, prior=True))
    out.sort(key=lambda g: g.week, reverse=True)
    return out


def last_teams(rows: list[dict]) -> dict[str, str]:
    """``{player: the team he finished the prior season with}``.

    The last week wins, so a player traded mid-way through the prior season
    is compared from where he ended up rather than where he started.
    """
    from .sources.nflverse import _f, _s, _regular_season

    seen: dict[str, tuple[int, str]] = {}
    for r in _regular_season(rows):
        name = _s(r, "player_display_name", "player_name", "full_name")
        team = _s(r, "recent_team", "team")
        if not name or not team:
            continue
        wk = int(_f(r, "week", default=0))
        if name not in seen or wk >= seen[name][0]:
            seen[name] = (wk, team)
    return {p: t for p, (_w, t) in seen.items()}


def head_coaches(schedules: list[dict], season: int) -> dict[str, str]:
    """``{team: head coach}`` for a season, taking the LAST week's coach.

    The last week rather than the first because a team that changed coach
    mid-season carries the new one into the offseason, and that is the
    comparison an offseason change is asking about.
    """
    from .sources.nflverse import _s

    seen: dict[str, tuple[int, str]] = {}
    for r in schedules:
        if _s(r, "season") != str(season) or _s(r, "game_type", default="REG") != "REG":
            continue
        try:
            wk = int(_s(r, "week", default="0") or 0)
        except (TypeError, ValueError):
            continue
        for side in ("home", "away"):
            team, coach = _s(r, f"{side}_team"), _s(r, f"{side}_coach")
            if not team or not coach:
                continue
            if team not in seen or wk >= seen[team][0]:
                seen[team] = (wk, coach)
    return {t: c for t, (_w, c) in seen.items()}


def offseason_coach_changes(schedules: list[dict], season: int) -> dict[str, tuple]:
    """``{team: (old_coach, new_coach)}`` between ``season-1`` and ``season``.

    A team missing from either season is not a change — it is a gap in the
    feed, and reporting it as a reset would be a false detection.
    """
    was = head_coaches(schedules, season - 1)
    now = head_coaches(schedules, season)
    return {t: (was[t], now[t]) for t in now
            if t in was and was[t] != now[t]}


def build_index(prior_rows: list[dict], roster: dict[str, dict],
                schedules: list[dict], season: int) -> dict:
    """Everything the carry needs, resolved once for the whole slate."""
    return {
        "last_teams": last_teams(prior_rows),
        "roster": roster,
        "coach_changes": offseason_coach_changes(schedules, season),
        "season": season,
    }


def reset_for(index: dict, player: str) -> tuple | None:
    """``(kind, detail)`` if this player's prior season describes a
    different job now, else None.

    Team change beats coach change: a player who moved to a team that also
    changed coach has moved, and saying so is more use than naming the
    coach of a building he has never worked in.
    """
    was = (index.get("last_teams") or {}).get(player)
    entry = (index.get("roster") or {}).get(player) or {}
    now = entry.get("team") or ""
    if was and now and was != now:
        return (TRADE, f"joined {now} from {was}")
    changes = index.get("coach_changes") or {}
    if now and now in changes:
        old, new = changes[now]
        return (COACH, f"{now} changed head coach ({old} → {new})")
    return None


def carry_for(index: dict, prior_rows: list[dict], player: str, market: str,
              pos_means: dict[str, float]) -> dict | None:
    """The carried sample for one player and market, or None.

    Returns the logs, the weight the shrink leaves on his own mean, the
    anchor it is shrunk toward, and any reset that was detected. The
    CALLER applies the shrink to the projection rather than to the log
    values: shrinking each value toward a constant would shrink the
    variance too, and a carried season should not come out looking more
    certain than a played one.
    """
    logs = carried_logs(prior_rows, player, market)
    if len(logs) < MIN_PRIOR_GAMES:
        return None
    hit = reset_for(index, player)
    if hit and DISCARD_ON_RESET:
        return None
    entry = (index.get("roster") or {}).get(player) or {}
    pos = (entry.get("position") or "").upper()
    anchor = pos_means.get(pos)
    own = sum(g.value for g in logs) / len(logs)
    return {
        "logs": logs,
        "games": len(logs),
        "weight": shrink_weight(len(logs)),
        "own_mean": own,
        "anchor": anchor,
        "position": pos,
        "team": entry.get("team") or "",
        "reset": hit,
        "season": index.get("season", 0) - 1,
    }


def shrunk_mean(carry: dict) -> float:
    """The carried baseline after the fitted pull toward the positional mean."""
    anchor = carry.get("anchor")
    own = carry.get("own_mean", 0.0)
    if anchor is None:
        return own
    w = carry.get("weight", 1.0)
    return w * own + (1.0 - w) * anchor


def decorate(recommendations: list[dict], report: dict) -> int:
    """Say on the card that this number came from last season, and why.

    A carried projection that looks identical to a played one is the whole
    risk of this feature. Every recommendation built on carried games says
    so, and a detected reset says that too.
    """
    carried = report.get("carried") or {}
    n = 0
    for r in recommendations:
        entry = carried.get(r.get("player"))
        if not entry:
            continue
        season, games = entry.get("season"), entry.get("games")
        note = (f"Carried from {season}: no {season + 1} games yet, so this "
                f"projects from {games} game(s) last season, pulled "
                f"{(1 - entry.get('weight', 1.0)):.0%} toward the positional "
                f"mean")
        r.setdefault("warnings", []).append(note)
        r["carried"] = {k: entry.get(k) for k in
                        ("season", "games", "weight", "position")}
        hit = entry.get("reset")
        if hit:
            kind, detail = hit
            r["warnings"].append(
                f"Offseason {kind}: {detail}. Last season's games are still "
                f"in the average — there is nothing else yet — so treat this "
                f"as describing the job he had, not the one he has")
            r["carried"]["reset"] = {"kind": kind, "detail": detail}
            if not STAKE_ON_RESET and r.get("recommended"):
                # Shown, not staked. See STAKE_ON_RESET for why those are
                # different answers to different questions.
                r["recommended"] = False
                r["carried"]["held_back"] = True
                r["warnings"].append(
                    "Not staked while that is the only sample there is. It "
                    "stays on the board so the number is visible, but a bet "
                    "wants evidence about the job he holds now")
        n += 1
    return n
