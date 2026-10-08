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
  * "A BACKUP MEANS MORE RUNS" — Ethan's two Eagles-Bears research reports,
    2026-09-28, both betting a back's carries on it — was measured the
    same day (qbfit, 2021-2025): the team's run share behind a
    replacement ×1.026 ± .016 (four of five seasons up, short of the bar),
    the lead backs' carries ×1.014 ± .032 (seasons split). About one more
    run in forty plays, and none of it reaching a back's line. Not applied;
    the read says so.
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

#: WHAT THE WHOLE TEAM DID behind a replacement, measured (engine/qbfit
#: TEAM_VOLUME, 2021-2025, every team-game against its own average in the
#: weeks before, over the same ratio in games with the usual starter).
#: Ethan, 2026-09-28, on the Bears: "they will probably be loosing which
#: will cause more throwing … they might run more" — and then, of putting
#: the answer on the page, "you should do it for all the teams". Shown on
#: every QB-change card and read; it moves no number (the receivers' step
#: above is the part that prices).
#:   tier: (games, {market: multiplier})
TEAM_VOLUME = {
    "downgrade": (236, {"team_pass_att": 0.975, "team_completions": 0.953,
                        "team_pass_yds": 0.925, "team_carries": 1.010}),
    "similar": (193, {"team_pass_att": 1.042, "team_completions": 1.040,
                      "team_pass_yds": 1.081, "team_carries": 1.052}),
}
_VOLUME_WORDS = (("team_pass_att", "pass attempts"), ("team_completions", "completions"),
                 ("team_pass_yds", "passing yards"), ("team_carries", "carries"))


def volume_line(tier: str) -> str:
    """The team's own volume behind this kind of replacement, in words —
    "" for a tier that was not measured."""
    got = TEAM_VOLUME.get(tier or "")
    if not got:
        return ""
    n, m = got

    def pct(v):
        d = round((v - 1) * 100)
        return "about the same" if d == 0 else f"{abs(d)}% {'more' if d > 0 else 'fewer'}"
    who = ("a quarterback this far below the starter" if tier == "downgrade"
           else "a quarterback who had thrown like the starter")
    bits = ", ".join(f"{pct(m[k])} {w}" if pct(m[k]) != "about the same" else f"{w} about the same"
                     for k, w in _VOLUME_WORDS)
    return f"Teams behind {who} ({n} games, 2021–25): {bits}"


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
    # THE USUAL STARTER (Ethan, 2026-09-26, on Seattle): "Drew Lock has
    # started one game for Seattle so far in 2026 ... week two ... Darnold
    # did get injured and Lock took over." Two games of volume made Lock
    # the "starter", so Darnold back at QB1 read as a benching. A team's
    # usual starter is its leading passer LAST season, or in its FIRST game
    # this season; the depth chart naming him again is a return.
    team_att: dict = {}
    for rows, current in ((prior_stats or [], False), (stats or [], True)):
        for r in rows:
            if _s(r, "position", "position_group").upper() != "QB":
                continue
            if _s(r, "season_type", "game_type", default="REG").upper() not in ("REG", ""):
                continue
            wk = int(_f(r, "week", default=0))
            if current and wk >= upto_week:
                continue
            team = _s(r, "recent_team", "team")
            name = _s(r, "player_display_name", "player_name", "full_name")
            if team and name:
                key = (team, "last") if not current else (team, wk)
                cell = team_att.setdefault(key, {})
                cell[name] = cell.get(name, 0.0) + _f(r, "attempts")
    usual: dict = {}
    first_week = {}
    for (team, wk) in team_att:
        if wk != "last" and (team not in first_week or wk < first_week[team]):
            first_week[team] = wk
    for team in {t for t, _w in team_att}:
        names = []
        for key in ((team, "last"), (team, first_week.get(team))):
            cell = team_att.get(key) or {}
            if cell:
                lead = max(sorted(cell), key=lambda n: cell[n])
                if lead not in names:
                    names.append(lead)
        usual[team] = names
    # HOW THE OFFENCE CHANGES SHAPE UNDER HIM (2026-10-08). Four Bucs-Cowboys
    # write-ups led with it: "Tampa altered its entire offense around
    # Daniels — 31 runs vs 36 dropbacks, 4.2 air yards per target, 8
    # carries for 55". The card said who starts and his yards an attempt;
    # now also, this season: the team's pass rate in his starts (against
    # the usual starter's), his carries and rushing yards a game, and his
    # air yards an attempt. Weekly rows carry all of it.
    profile: dict = {}
    team_plays: dict = {}             # (team, week) -> [pass attempts, carries]
    for rows, current in ((prior_stats or [], False), (stats or [], True)):
        for r in rows:
            if _s(r, "season_type", "game_type", default="REG").upper() not in ("REG", ""):
                continue
            wk = int(_f(r, "week", default=0))
            if current and wk >= upto_week:
                continue
            team = _s(r, "recent_team", "team")
            is_qb = _s(r, "position", "position_group").upper() == "QB"
            if current and team:
                tp = team_plays.setdefault((team, wk), [0.0, 0.0])
                tp[1] += _f(r, "carries")
                if is_qb:
                    tp[0] += _f(r, "attempts")
            if not is_qb:
                continue
            name = _s(r, "player_display_name", "player_name", "full_name")
            a = passing.setdefault(name, [0.0, 0.0])
            a[0] += _f(r, "attempts")
            a[1] += _f(r, "passing_yards")
            if current and _f(r, "attempts") > 0:
                pr = profile.setdefault(name, {"games": 0, "attempts": 0.0, "air_yards": 0.0,
                                               "carries": 0.0, "rush_yds": 0.0, "_starts": []})
                pr["games"] += 1
                pr["attempts"] += _f(r, "attempts")
                pr["air_yards"] += _f(r, "passing_air_yards")
                pr["carries"] += _f(r, "carries")
                pr["rush_yds"] += _f(r, "rushing_yards")
                cell = team_att.get((team, wk)) or {}
                if cell and max(sorted(cell), key=lambda n: cell[n]) == name:
                    pr["_starts"].append((team, wk))
    for name, pr in profile.items():
        starts = pr.pop("_starts")
        plays = [team_plays[k] for k in starts if k in team_plays]
        att, car = sum(p[0] for p in plays), sum(p[1] for p in plays)
        pr["starts"] = len(starts)
        pr["pass_rate"] = round(att / (att + car), 3) if att + car > 0 else None
        pr["air_per_att"] = round(pr["air_yards"] / pr["attempts"], 1) if pr["air_yards"] > 0 else None
        pr["carries_pg"] = round(pr["carries"] / pr["games"], 1)
        pr["rush_yds_pg"] = round(pr["rush_yds"] / pr["games"], 1)
    return {"teams": teams, "passing": {k: tuple(v) for k, v in passing.items()},
            "usual": {t: n for t, n in usual.items() if t in teams}, "profile": profile}


def changes(qb: dict, injuries: list, depth_qb1: dict | None = None,
            news_qb: dict | None = None) -> dict:
    """{team: change} for every team whose starter is out or benched this week.

    ``injuries`` are the slate's (weekly report merged with the live board);
    ``depth_qb1`` is sources/depthcharts.qb1_map for this week, or None;
    ``news_qb`` is engine/newsqb.expected_starters — {team: {"name",
    "source", …}} — the man the beat reporters expect, read when the
    starter is out and the depth chart has not named someone else
    (2026-09-28: Keenum for the Bears, hours before any chart moved)."""
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
        replacement, reported = None, None
        news = (news_qb or {}).get(team) or {}
        for cand in (qb1, news.get("name"), slot.get("backup")):
            if cand and _norm(cand) != _norm(starter) and (team, _norm(cand)) not in ruled:
                replacement = cand
                reported = news if cand == news.get("name") and cand != qb1 else None
                break
        tier, s_ypa, r_ypa = tier_of(qb.get("passing") or {}, starter, replacement or "")
        # HIS USUAL STARTER BACK: the man the volume ranking called the
        # starter filled in; the depth chart's QB1 is the team's usual one.
        # Last season's leader comes first: a starter hurt early in week 1
        # (Darnold) can be out-thrown in that game by the man who replaced
        # him, so the first game's leader only speaks when last season's
        # leader is not in the picture.
        usual = [_norm(n) for n in ((qb.get("usual") or {}).get(team) or [])]
        rep, sta = _norm(replacement or ""), _norm(starter)
        if benched and replacement and usual and (
                (rep == usual[0] and sta != usual[0])
                or (rep in usual[1:] and sta not in usual)):
            status, tier = "RETURNS", "return"
        out[team] = {"team": team, "starter": starter, "status": status or "BENCHED",
                     "replacement": replacement, "tier": tier,
                     # Named by the news, not the chart: the card says so.
                     "reported": ({"source": reported.get("source") or "", "title": reported.get("title") or ""}
                                  if reported else None),
                     "starter_ypa": round(s_ypa, 1) if s_ypa else None,
                     "replacement_ypa": round(r_ypa, 1) if r_ypa else None,
                     "replacement_attempts": int((qb.get("passing") or {}).get(replacement or "", (0, 0))[0]),
                     # This season's shape under each of them (see `quarterbacks`).
                     "replacement_profile": (qb.get("profile") or {}).get(replacement or ""),
                     "starter_profile": (qb.get("profile") or {}).get(starter)}
    return out


def headline(ch: dict) -> str:
    """"Joe Burrow (OUT) — Jake Browning starts", or, when it is the depth
    chart and not an injury (a benching, or the usual starter back from
    one): "Brock Purdy starts over Mac Jones (this week's depth chart)"."""
    if ch["status"] == "RETURNS":
        return f"{ch['replacement']} is back at QB — {ch['starter']} started while he was out"
    if ch["status"] == "BENCHED" and ch.get("replacement"):
        return f"{ch['replacement']} starts over {ch['starter']} (this week’s depth chart)"
    if ch.get("replacement") and ch.get("reported"):
        src = (ch["reported"] or {}).get("source") or "reports"
        who = f"{ch['replacement']} expected to start (per {src})"
    else:
        who = f"{ch['replacement']} starts" if ch.get("replacement") else "his replacement is not named yet"
    return f"{ch['starter']} ({ch['status']}) — {who}"


def shape_words(ch: dict) -> str:
    """How the offence has looked under the replacement this season, from
    `quarterbacks`' profile: the team's pass rate in his starts against the
    usual starter's, his carries and rushing yards a game, his air yards an
    attempt. "" when nothing is known."""
    rp, sp = ch.get("replacement_profile") or {}, ch.get("starter_profile") or {}
    if not rp or not ch.get("replacement"):
        return ""
    bits = []
    if rp.get("pass_rate") is not None and rp.get("starts"):
        s = (f"in his {rp['starts']} start{'s' if rp['starts'] != 1 else ''} this season the team threw on "
             f"{rp['pass_rate']:.0%} of its plays")
        if sp.get("pass_rate") is not None and sp.get("starts"):
            s += f" ({ch['starter']}’s starts: {sp['pass_rate']:.0%})"
        bits.append(s)
    if rp.get("games"):
        bits.append(f"he has run {rp['carries_pg']:.1f} times a game for {rp['rush_yds_pg']:.0f} yards")
    if rp.get("air_per_att"):
        s = f"{rp['air_per_att']:.1f} air yards an attempt"
        if sp.get("air_per_att"):
            s += f" against {ch['starter']}’s {sp['air_per_att']:.1f}"
        bits.append(s)
    return "; ".join(bits)


def detail(ch: dict) -> str:
    """The replacement's sample against the starter's, in words — and how
    the offence has looked under him (`shape_words`)."""
    shape = shape_words(ch)
    if ch.get("replacement") and ch.get("replacement_ypa") and ch.get("starter_ypa"):
        out = (f"{ch['replacement']} has thrown for {ch['replacement_ypa']} yards an attempt "
               f"({ch['replacement_attempts']} attempts) against {ch['starter']}’s {ch['starter_ypa']}")
        return f"{out} — {shape}" if shape else out
    if ch.get("replacement"):
        n = ch.get("replacement_attempts") or 0
        out = f"{ch['replacement']} has {n} pass attempt{'s' if n != 1 else ''} in our data — too few to rate"
        return f"{out} — {shape}" if shape else out
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
    if own and ch.get("status") == "RETURNS":
        note = f"Back as the starter; {ch['starter']} started while he was out"
    elif own:
        note = f"Starting in place of {ch['starter']}"
    elif ch.get("status") == "RETURNS":
        note = "His usual quarterback is back — nothing to adjust"
    elif applied != 1.0:
        note = (f"Measured over four seasons: behind a quarterback this far below the starter, "
                f"receivers lost {round((1 - applied) * 100)}% — applied (×{applied:.2f})")
    else:
        note = "Shown for you. Over four seasons this change did not move this bet enough to price it"
    return {"team": ch["team"], "starter": ch["starter"], "status": ch["status"],
            "replacement": ch.get("replacement"), "tier": ch["tier"], "headline": headline(ch),
            "detail": detail(ch), "applied": round(applied, 3), "note": note,
            "reported": ch.get("reported"),
            "volume": "" if ch.get("status") == "RETURNS" else volume_line(ch.get("tier"))}


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
