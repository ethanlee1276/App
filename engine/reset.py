"""The reset rule — throwing away a sample that describes a dead role.

§5 of the model spec states it plainly, and it is the sharpest recency
instruction in the document:

    A coordinator change, a new starter, or a traded player *resets the
    sample*. Weight post-change games at nearly 100% and discard the
    stale data entirely, even if the sample is small. Three games in the
    real current role beat twelve games in a role that no longer exists.

Every other recency mechanism here shades — the form windows weight the
last two games at 45%, the fitted dial leans a little further one way or
the other. Shading is right for a player whose role is stable and whose
production drifts. It is exactly wrong for a receiver who was traded in
week 13: those eleven games with his old team are not "older evidence of
the same thing", they are evidence about a different job. Averaging them
in at any weight imports a number that cannot happen again.

**What this can actually detect**, which is narrower than the spec's
wording and worth stating honestly:

* **Team change** — a player appearing with a new team mid-season. The
  cleanest trigger there is, and the most common (29 in the 2025 logs).
* **Head-coach change** — the schedule feed carries the coach on every
  row, so a mid-season firing is visible. This is a PROXY for the
  spec's "coordinator change": a coordinator swap alone is not in any
  free feed, so a coordinator fired without his head coach is missed.
  Under-detection, never false detection.
* **Role change** — a sustained snap-share promotion or demotion
  (``ROLE_JUMP`` over ``ROLE_WEEKS`` weeks either side). This is the
  spec's "new starter" seen from the only angle the data offers: the
  backup who took the job, rather than the depth-chart line that says
  he did.

One deviation from the spec, deliberate and flagged: below
``MIN_POST_RESET`` post-reset games the sample is NOT truncated. "Even
if the sample is small" is right down to about three games; at one it
stops being a small sample and becomes an outlier machine, because a
single 140-yard afternoon would become the entire projected mean with
nothing to pull it back. Below the floor the logs are left alone and
the card carries the warning instead, which tells the reader the same
thing without pretending to a number.

Standard library only; reads the history DB the ingests already fill.
"""

from __future__ import annotations

#: Kinds of reset, most specific first — the label that reaches the card.
TRADE = "team change"
COACH = "coach change"
ROLE = "role change"

#: Weeks either side of a candidate week when testing for a role shift,
#: and the change in snap share that counts as a new job rather than a
#: busy afternoon.
ROLE_WEEKS = 3
ROLE_JUMP = 0.30
#: …plus regime bounds, so "a rotational player got a few more snaps"
#: does not read as a promotion.
ROLE_FROM_BELOW = 0.35
ROLE_TO_ABOVE = 0.55

#: Below this many post-reset games the sample is kept and the card warns
#: instead. See the module docstring for why this floor exists.
MIN_POST_RESET = 2


def _wk(period) -> int | None:
    try:
        return int(str(period).lstrip("0") or 0)
    except (TypeError, ValueError):
        return None


def coach_changes(schedules: list[dict], season: int) -> dict[str, tuple]:
    """``{team: (week, old_coach, new_coach)}`` for mid-season changes.

    The LAST change of the season wins, which is what a reset needs: a
    team that changed coaches twice resets from the most recent one.
    """
    from .sources.nflverse import _s

    seen: dict[str, dict[int, str]] = {}
    for r in schedules:
        if _s(r, "season") != str(season) or _s(r, "game_type") != "REG":
            continue
        wk = _wk(_s(r, "week"))
        if wk is None:
            continue
        for side in ("home", "away"):
            team, coach = _s(r, f"{side}_team"), _s(r, f"{side}_coach")
            if team and coach:
                seen.setdefault(team, {})[wk] = coach
    out: dict[str, tuple] = {}
    for team, byweek in seen.items():
        weeks = sorted(byweek)
        for a, b in zip(weeks, weeks[1:]):
            if byweek[a] != byweek[b]:
                out[team] = (b, byweek[a], byweek[b])
    return out


def player_moves(conn, season: int, sport: str = "nfl") -> dict[str, tuple]:
    """``{player: (week, old_team, new_team)}`` — mid-season team changes.

    Read off the logs themselves rather than a transactions feed: a
    player who appears with a new team HAS moved, whatever the paperwork
    said, and that is the fact the projection cares about.
    """
    rows = conn.execute(
        "SELECT DISTINCT player, team, period FROM player_game_logs "
        "WHERE sport=? AND season=? ORDER BY player, period",
        (sport, season)).fetchall()
    seq: dict[str, list] = {}
    for r in rows:
        wk = _wk(r["period"])
        if wk is None:
            continue
        line = seq.setdefault(r["player"], [])
        if not line or line[-1][1] != r["team"]:
            line.append((wk, r["team"]))
    out: dict[str, tuple] = {}
    for player, line in seq.items():
        if len(line) > 1:
            wk, new_team = line[-1]
            out[player] = (wk, line[-2][1], new_team)
    return out


def role_shifts(conn, season: int, sport: str = "nfl") -> dict[str, tuple]:
    """``{player: (week, before_share, after_share)}`` — sustained snap
    promotions or demotions, the only view of "a new starter" the data
    offers without a depth-chart feed."""
    rows = conn.execute(
        "SELECT player, period, value FROM player_game_logs "
        "WHERE sport=? AND season=? AND market='snap_pct' "
        "ORDER BY player, period", (sport, season)).fetchall()
    seq: dict[str, list] = {}
    for r in rows:
        wk = _wk(r["period"])
        if wk is not None:
            seq.setdefault(r["player"], []).append((wk, float(r["value"] or 0)))
    out: dict[str, tuple] = {}
    for player, line in seq.items():
        if len(line) < 2 * ROLE_WEEKS:
            continue
        hits: list[tuple] = []
        for i in range(ROLE_WEEKS, len(line) - ROLE_WEEKS + 1):
            before = sum(v for _w, v in line[i - ROLE_WEEKS:i]) / ROLE_WEEKS
            after = sum(v for _w, v in line[i:i + ROLE_WEEKS]) / ROLE_WEEKS
            promoted = (after - before >= ROLE_JUMP
                        and before < ROLE_FROM_BELOW and after > ROLE_TO_ABOVE)
            demoted = (before - after >= ROLE_JUMP
                       and after < ROLE_FROM_BELOW and before > ROLE_TO_ABOVE)
            if promoted or demoted:
                hits.append((i, line[i][0], round(before, 3), round(after, 3)))
        if not hits:
            continue
        # A single change trips the window on several consecutive weeks —
        # as it slides past, the "before" average decays but can still
        # clear the bound. Those are one event, so group consecutive hits
        # into runs and take the FIRST week of the LAST run: the last run
        # because a newer regime governs, the first week of it because
        # that is when the new role started. Taking the last hit instead
        # reported a demotion a week late and would have discarded a game
        # already played in the new role.
        runs: list[list[tuple]] = [[hits[0]]]
        for h in hits[1:]:
            if h[0] == runs[-1][-1][0] + 1:
                runs[-1].append(h)
            else:
                runs.append([h])
        # The LAST run, because a newer regime governs the job he holds now.
        run = runs[-1]
        i0, _wk0, before, after = run[0]
        # Then the exact boundary. A sliding window trips for several weeks
        # around one change — straddling it backwards AND forwards — so the
        # run's edges are both off by a week in opposite directions. The
        # discontinuity itself is unambiguous: the first week whose own
        # snap share sits on the new regime's side of the midpoint. Getting
        # this wrong costs a real game in either direction — one week late
        # discards a game already played in the new role, one week early
        # keeps a stale one.
        mid = (before + after) / 2.0
        rising = after > before
        lo = max(0, i0 - 1)
        hi = min(len(line), run[-1][0] + ROLE_WEEKS)
        boundary = None
        for j in range(lo, hi):
            v = line[j][1]
            if (v >= mid) if rising else (v <= mid):
                boundary = j
                break
        j = boundary if boundary is not None else i0
        out[player] = (line[j][0], round(before, 3), round(after, 3))
    return out


def build(conn, season: int, schedules: list[dict] | None = None,
          sport: str = "nfl") -> dict:
    """Every reset this season, indexed for lookup by player and team."""
    return {
        "moves": player_moves(conn, season, sport),
        "roles": role_shifts(conn, season, sport),
        "coaches": coach_changes(schedules or [], season),
    }


def reset_for(index: dict, player: str, team: str) -> tuple | None:
    """The reset that governs this player, or None.

    The LATEST reset wins — a receiver traded in week 13 whose snaps then
    jumped in week 15 is projecting from week 15, because the newer event
    describes the job he holds now. That also collapses the double-count
    where one move shows up as both a trade and a promotion.
    """
    found = []
    mv = (index.get("moves") or {}).get(player)
    if mv:
        found.append((mv[0], TRADE, f"joined {mv[2]} from {mv[1]}"))
    rl = (index.get("roles") or {}).get(player)
    if rl:
        direction = "promoted" if rl[2] > rl[1] else "demoted"
        found.append((rl[0], ROLE,
                      f"{direction} — snap share {rl[1]:.0%} → {rl[2]:.0%}"))
    ch = (index.get("coaches") or {}).get((team or "").upper())
    if ch:
        found.append((ch[0], COACH, f"{team} changed head coach "
                                    f"({ch[1]} → {ch[2]})"))
    if not found:
        return None
    return max(found, key=lambda f: f[0])


def apply_to_slate(slate, conn, season: int,
                   schedules: list[dict] | None = None) -> dict:
    """Truncate every prop's logs to its player's post-reset games.

    Mutates the slate the way ``attach_injuries_to_slate`` does, and
    returns a report keyed by player so the board can say what it threw
    away and why. Props whose post-reset sample is under
    ``MIN_POST_RESET`` keep every log and are reported as ``held``.
    """
    index = build(conn, season, schedules)
    report: dict = {"reset": {}, "held": {}, "index": {
        k: len(v) for k, v in index.items()}}
    for prop in getattr(slate, "props", []):
        hit = reset_for(index, prop.player, getattr(prop, "team", ""))
        if not hit:
            continue
        week, kind, detail = hit
        kept = [g for g in prop.logs if (g.week or 0) >= week]
        entry = {"week": week, "kind": kind, "detail": detail,
                 "kept": len(kept), "dropped": len(prop.logs) - len(kept)}
        if len(kept) >= MIN_POST_RESET:
            prop.logs = kept
            report["reset"][prop.player] = entry
        elif len(prop.logs) > len(kept):
            report["held"][prop.player] = entry
    return report


def decorate(recommendations: list[dict], report: dict) -> int:
    """Say on the card what the sample rule did, either way."""
    reset, held = report.get("reset") or {}, report.get("held") or {}
    n = 0
    for r in recommendations:
        player = r.get("player")
        if player in reset:
            e = reset[player]
            r.setdefault("reasons", []).insert(0,
                f"Sample reset ({e['kind']}, week {e['week']}): {e['detail']}. "
                f"Projecting from the {e['kept']} game(s) since and discarding "
                f"{e['dropped']} in a role that no longer exists")
            r["sample_reset"] = e
            n += 1
        elif player in held:
            e = held[player]
            r.setdefault("warnings", []).append(
                f"Stale sample ({e['kind']}, week {e['week']}): {e['detail']}, "
                f"but only {e['kept']} game(s) since — too few to project from, "
                f"so the older games are still in the average. Treat this "
                f"number as describing a role he may no longer have")
            r["sample_reset"] = e
            n += 1
    return n
