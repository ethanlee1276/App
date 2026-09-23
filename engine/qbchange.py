"""A starting quarterback out: noticed, priced where it was measured, shown.

Ethan, 2026-09-23: "there is a lot of starting qbs out in the nfl right now
so I wanna make sure the models notice that and we show that in the
responses and shit under the card like the other shit."

WHAT THE BOARD DID BEFORE. A depth-chart watch (sources/depthcharts
.qb_dependency) put one warning line on that team's passing and receiving
props and moved nothing. The injured starter's own props were built and
then held; his REPLACEMENT had none, because the slate picks each team's
quarterback by volume and the volume is the injured man's — so a book's
line on the man actually starting was bought and dropped.

WHAT IT DOES NOW, per team, once the injury report and the depth chart are
in (nfl_build):

  * THE STARTER is the team's leading passer by volume (the same ranking
    that picks every prop player). He is OUT when the injury report or the
    live board has him ruled out (engine/injuries.RULED_OUT), or BENCHED
    when this week's depth chart puts someone else at QB1.
  * THE REPLACEMENT is the depth chart's QB1 when that is someone else and
    he is not ruled out himself, else the team's second quarterback by
    volume. The slate is built with each team's second quarterback
    (`build_slate(qb_backups=True)`); his props stay only where he starts,
    and the out starter's go.
  * HIS TIER, from passes thrown before this week (this season and last):
    "similar" at 50+ attempts and at least 90% of the starter's yards per
    attempt, else "downgrade" (including the backup with no real sample).
  * THE EFFECT is measured (engine/qbfit.py, `python3 qbfit.py`,
    2022-2025): behind a downgrade a team's receivers lost 10% of their
    receiving yards and 9% of their catches, in every season. Nothing else
    cleared the bar (two standard errors and three seasons of four), so
    nothing else moves — tight ends, backs and touchdowns are SHOWN the
    change and left alone.
  * THE CARD (`qb_card`) goes on every row of that team — props, touchdown
    rows, Most Likely rows — and the game cards say it too.
"""
from __future__ import annotations

from .injuries import RULED_OUT
from .qbfit import MIN_ATTEMPTS, tier_of

#: {(market, group, tier): multiplier}, from `python3 qbfit.py` 2026-09-23 —
#: what engine/qbfit.shipped() returns on 2022-2025. Every season:
#: rec_yds 0.888 / 0.899 / 0.920 / 0.904; receptions 0.893 / 0.906 / 0.964 / 0.908.
EFFECT = {
    ("rec_yds", "WR", "downgrade"): 0.897,      # ± .039, n 452
    ("receptions", "WR", "downgrade"): 0.912,   # ± .031, n 445
}


def _norm(name: str) -> str:
    from .sources.oddsapi import normalize_name
    return normalize_name(str(name or ""))


def quarterbacks(specs, stats: list[dict], prior_stats: list[dict], upto_week: int, team_of) -> dict:
    """{"teams": {team: {"starter", "backup"}}, "passing": {name: (attempts, yards)}} for the slate."""
    from .sources.nflverse import _f, _s
    teams: dict = {}
    for sp in specs or []:
        if getattr(sp, "position", "") != "QB":
            continue
        team = team_of(sp.player)
        if not team:
            continue
        slot = teams.setdefault(team, {"starter": None, "backup": None})
        key = "backup" if sp.usage_role == "backup" else "starter"
        slot[key] = slot[key] or sp.player
    passing: dict = {}
    for rows, current in ((prior_stats or [], False), (stats or [], True)):
        for r in rows:
            if _s(r, "position", "position_group").upper() != "QB":
                continue
            if current and int(_f(r, "week", default=0)) >= upto_week:
                continue
            if _s(r, "season_type", "game_type", default="REG").upper() not in ("REG", ""):
                continue
            name = _s(r, "player_display_name", "player_name", "full_name")
            a = passing.setdefault(name, [0.0, 0.0])
            a[0] += _f(r, "attempts")
            a[1] += _f(r, "passing_yards")
    return {"teams": teams, "passing": {k: tuple(v) for k, v in passing.items()}}


def changes(qb: dict, injuries: list, depth_qb1: dict | None = None) -> dict:
    """{team: change} for every team whose starter is out or benched this week.

    ``injuries`` are the slate's (weekly report merged with the live board);
    ``depth_qb1`` is sources/depthcharts.qb1_map for this week, or None."""
    ruled = {}
    for i in injuries or []:
        if getattr(i, "status", "") in RULED_OUT:
            ruled[(i.team, _norm(i.player))] = i.status
    out: dict = {}
    for team, slot in sorted((qb or {}).get("teams", {}).items()):
        starter = slot.get("starter")
        if not starter:
            continue
        status = ruled.get((team, _norm(starter)))
        qb1 = (depth_qb1 or {}).get(team)
        benched = bool(qb1) and _norm(qb1) != _norm(starter) and not status
        if not status and not benched:
            continue
        replacement = None
        for cand in (qb1, slot.get("backup")):
            if cand and _norm(cand) != _norm(starter) and (team, _norm(cand)) not in ruled:
                replacement = cand
                break
        tier, s_ypa, r_ypa = tier_of(qb.get("passing") or {}, starter, replacement or "")
        out[team] = {"team": team, "starter": starter, "status": status or "BENCHED",
                     "replacement": replacement, "tier": tier,
                     "starter_ypa": round(s_ypa, 1) if s_ypa else None,
                     "replacement_ypa": round(r_ypa, 1) if r_ypa else None,
                     "replacement_attempts": int((qb.get("passing") or {}).get(replacement or "", (0, 0))[0])}
    return out


def headline(ch: dict) -> str:
    """"Joe Burrow (OUT) — Jake Browning starts", or, when it is the depth
    chart and not an injury (a benching, or the usual starter back from
    one): "Brock Purdy starts over Mac Jones (this week's depth chart)"."""
    if ch["status"] == "BENCHED" and ch.get("replacement"):
        return f"{ch['replacement']} starts over {ch['starter']} (this week’s depth chart)"
    who = f"{ch['replacement']} starts" if ch.get("replacement") else "his replacement is not named yet"
    return f"{ch['starter']} ({ch['status']}) — {who}"


def detail(ch: dict) -> str:
    """The replacement's sample against the starter's, in words."""
    if ch.get("replacement") and ch.get("replacement_ypa") and ch.get("starter_ypa"):
        return (f"{ch['replacement']} has thrown for {ch['replacement_ypa']} yards an attempt "
                f"({ch['replacement_attempts']} attempts) against {ch['starter']}’s {ch['starter_ypa']}")
    if ch.get("replacement"):
        n = ch.get("replacement_attempts") or 0
        return f"{ch['replacement']} has {n} pass attempt{'s' if n != 1 else ''} in our data — too few to rate"
    return ""


def apply_to_slate(slate, chs: dict) -> dict:
    """Stamp each game with its teams' changes, keep the replacement's props,
    drop the out starter's, and drop every backup who is not starting.
    Returns {"kept": [...], "dropped": n}."""
    keep, drop = set(), set()
    for team, ch in chs.items():
        drop.add((team, _norm(ch["starter"])))
        if ch.get("replacement"):
            keep.add((team, _norm(ch["replacement"])))
    before = len(slate.props)
    kept = sorted({p.player for p in slate.props if (p.team, _norm(p.player)) in keep})
    slate.props = [p for p in slate.props
                   if (p.team, _norm(p.player)) not in drop
                   and (getattr(p, "usage_role", "") != "backup" or (p.team, _norm(p.player)) in keep)]
    for p in slate.props:
        if (p.team, _norm(p.player)) in keep and p.usage_role == "backup":
            p.usage_role = "starter"
    for g in slate.games:
        g.qb_changes = {t: chs[t] for t in (g.home, g.away) if t in chs}
    return {"kept": kept, "dropped": before - len(slate.props)}


def card(ch: dict, applied: float = 1.0, own: bool = False) -> dict:
    """What goes under a pick of that team."""
    note = ""
    if own:
        note = f"Starting in place of {ch['starter']}"
    elif applied != 1.0:
        note = (f"Measured over four seasons: behind a quarterback this far below the starter, "
                f"receivers lost {round((1 - applied) * 100)}% — applied (×{applied:.2f})")
    else:
        note = "Shown for you. Over four seasons this change did not move this bet enough to price it"
    return {"team": ch["team"], "starter": ch["starter"], "status": ch["status"],
            "replacement": ch.get("replacement"), "tier": ch["tier"], "headline": headline(ch),
            "detail": detail(ch), "applied": round(applied, 3), "note": note}


def effect(prop, game) -> tuple:
    """(multiplier, reason, card) for one prop, from its game's changes."""
    ch = (getattr(game, "qb_changes", None) or {}).get(getattr(prop, "team", ""))
    if not ch:
        return 1.0, "", None
    if getattr(prop, "position", "") == "QB":
        own = ch.get("replacement") and _norm(prop.player) == _norm(ch["replacement"])
        return 1.0, "", card(ch, 1.0, own=bool(own))
    mult = EFFECT.get((prop.market, getattr(prop, "position", ""), ch["tier"]), 1.0)
    reason = ""
    if mult != 1.0:
        reason = (f"QB change: {headline(ch)} — behind a downgrade at quarterback receivers lost "
                  f"{round((1 - mult) * 100)}% (measured) (×{mult:.2f})")
    return mult, reason, card(ch, mult)


def game_note(ch: dict) -> str:
    """The sentence for a game card."""
    return (f"QB change: {headline(ch)}. The book's price already knows; our own rating is built "
            f"from games he started.")
