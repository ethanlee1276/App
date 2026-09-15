"""When a player is out, where does his usage actually go?

NFL_MODEL §7's injury ripple, and the half that was never built:

    | §7 Injury ripple | 🟡 | … full redistribution model 📋 |

What exists today is `engine/injuries.py`, and it is worth being exact
about what that is: a table of INVENTED multipliers. Opponent's CB1 out
multiplies a receiving projection by 1.09. Interior DT out, 1.06. Own left
tackle out, 0.95. Nobody measured those numbers — they are plausible, they
are round, and they are the same for every team and every player.

A redistribution model is the opposite claim: not "receivers do about 9%
better", but "when THIS player misses, THESE teammates absorb his targets,
by this much, over this many games." That is answerable from the weekly
stats already on disk. It is a comparison of the same teammates in the
games he played against the games he missed.

TWO THINGS MAKE THIS HONEST AND BOTH ARE EASY TO SKIP.

**Share, not volume.** A teammate's raw targets rise in a game the team
threw 45 times and fall in one it threw 22, and neither has anything to do
with who was absent. The measure is share of the team's targets, so game
script cancels.

**The absence sample is tiny and must say so.** A player who missed three
games gives a three-game sample; the difference between 18% and 24% target
share over three games is nothing at all. Every row carries `n_out`, and
`MIN_OUT_GAMES` is the floor below which the answer is "not enough games",
which is the true answer for most players in most seasons.

NOTHING HERE PRICES ANYTHING. It measures. Replacing `injuries.py`'s 1.09
with a measured share is a PRICING change, and `docs/THE_INFORMATION_TEST.md`
is why it waits — the claimed edge measures AUC 0.479, so a new input into
the grade is the exact move that finding rules out until something moves
that number. What this closes is that we had never looked.
"""

from __future__ import annotations

#: Below this many missed games the honest answer is "cannot say". Three
#: is not a power calculation — it is the point below which a difference
#: in share is a rounding artefact of one busy afternoon.
MIN_OUT_GAMES = 3
#: A teammate needs this many games in BOTH states to be compared at all.
MIN_BOTH = 2

#: Which weekly-stats column carries each usage kind, with the fallbacks
#: nflverse's schema has used over the years.
USAGE = {
    "targets": ("targets", "tgt"),
    "carries": ("carries", "rushing_attempts", "rush_att"),
}


def _f(row, keys) -> float:
    for k in keys:
        v = row.get(k)
        if v not in (None, "", "NA"):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return 0.0


def _name(row) -> str:
    for k in ("player_display_name", "player_name", "player"):
        v = row.get(k)
        if v:
            return str(v)
    return ""


def _week(row):
    try:
        return int(float(row.get("week")))
    except (TypeError, ValueError):
        return None


def _season(row) -> int:
    try:
        return int(float(row.get("season")))
    except (TypeError, ValueError):
        return 0


def team_weeks(rows, team: str) -> dict:
    """`{(season, week): [row, ...]}` for one team's players, regular
    season only.

    THE SEASON IS IN THE KEY. Keyed by week alone, last season's week 3
    and this season's week 3 were one week, and a card that reads two
    seasons of stats to find a teammate's absences — which is the only
    way an early-season card has a sample at all — pooled the two games
    into one share. Rows without a season (the single-season callers and
    the tests that feed them) key on season 0 and behave as before.
    """
    out: dict = {}
    for r in rows:
        if str(r.get("recent_team") or r.get("team") or "").upper() != team:
            continue
        if str(r.get("season_type") or "REG").upper() not in ("REG", ""):
            continue
        w = _week(r)
        if w is None:
            continue
        out.setdefault((_season(r), w), []).append(r)
    return out


def shares(week_rows, kind: str) -> dict:
    """`{player: share of the team's targets/carries}` for one week."""
    keys = USAGE[kind]
    tot = sum(_f(r, keys) for r in week_rows)
    if tot <= 0:
        return {}
    return {_name(r): _f(r, keys) / tot for r in week_rows if _name(r)}


def redistribution(rows, team: str, player: str, kind: str = "targets"
                   ) -> dict:
    """How teammates' usage share changed in the weeks `player` was absent.

    Absence is read from the stats themselves — a week where the team
    played and this player has no row, or a row with no usage at all. That
    is deliberately not an injury report: a report says who was listed,
    the stats say who actually did not play, and only the second is what a
    redistribution is about.
    """
    weeks = team_weeks(rows, team)
    played, missed = [], []
    for w, wk in sorted(weeks.items()):
        s = shares(wk, kind)
        if not s:
            continue
        (played if s.get(player, 0.0) > 0 else missed).append(s)

    who = {}
    for name in {n for s in played + missed for n in s}:
        if name == player:
            continue
        a = [s[name] for s in played if name in s]
        b = [s[name] for s in missed if name in s]
        if len(a) < MIN_BOTH or len(b) < MIN_BOTH:
            continue
        with_, without = sum(a) / len(a), sum(b) / len(b)
        who[name] = {
            "with": round(with_, 4),
            "without": round(without, 4),
            "delta": round(without - with_, 4),
            "n_with": len(a), "n_without": len(b),
        }
    return {
        "team": team, "player": player, "kind": kind,
        "n_played": len(played), "n_out": len(missed),
        # THE GUARD, not a decoration. Below the floor every delta below is
        # noise, and a caller that reads the deltas without reading this
        # is reading a three-game accident as a role change.
        "enough": len(missed) >= MIN_OUT_GAMES,
        "beneficiaries": dict(sorted(who.items(),
                                     key=lambda kv: -kv[1]["delta"])),
    }


def report(res: dict, limit: int = 6) -> str:
    lines = ["", "=" * 70,
             f"  WHERE {res['player'].upper()}'S {res['kind'].upper()} GO "
             f"WHEN HE IS OUT", "=" * 70,
             f"  {res['team']} · {res['n_played']} game(s) with him, "
             f"{res['n_out']} without"]
    if not res["enough"]:
        lines += [
            "",
            f"  NOT ENOUGH GAMES — {res['n_out']} missed, and the floor is "
            f"{MIN_OUT_GAMES}.",
            "  The numbers below are printed so you can see the shape, and",
            "  they are not evidence of anything: a six-point move in share",
            "  over two games is one busy afternoon.",
        ]
    if not res["beneficiaries"]:
        lines += ["", "  No teammate appears in enough games on both sides "
                      "to compare.", ""]
        return "\n".join(lines)
    lines += ["", f"  {'teammate':<24} {'with':>7} {'without':>8} "
                  f"{'delta':>7}   games"]
    for name, v in list(res["beneficiaries"].items())[:limit]:
        lines.append(f"  {name[:24]:<24} {v['with']:>6.1%} {v['without']:>8.1%}"
                     f" {v['delta']:>+7.1%}   {v['n_with']}/{v['n_without']}")
    lines += [
        "",
        "  Share of the team's total, not raw volume: a teammate's targets",
        "  rise when the team throws 45 times and fall when it throws 22,",
        "  and neither has anything to do with who was absent.",
        "",
        "  Measurement only. engine/injuries.py still prices injuries with",
        "  invented multipliers (1.09 for a CB1, 1.06 for a DT); replacing",
        "  those with measured shares is a PRICING change — see",
        "  docs/THE_INFORMATION_TEST.md.",
        ""]
    return "\n".join(lines)


# --- the note on the beneficiary's card ----------------------------------------
#: Whose absence moves which usage. A quarterback out is a different
#: question (the backup's own passing line) and is not a ripple.
KIND_OF_POSITION = {"RB": "carries", "FB": "carries",
                    "WR": "targets", "TE": "targets"}
#: The teammates who can absorb it — the same position group as the man
#: out, which is what Ethan asked for and what the share measures.
GROUP = {"carries": frozenset({"RB", "FB"}), "targets": frozenset({"WR", "TE"})}
#: The markets on the beneficiary's card that the usage feeds.
MARKETS_OF = {"carries": frozenset({"rush_yds"}),
              "targets": frozenset({"rec_yds", "receptions"})}
#: Below this the share "did not move": two points is one target over a
#: 40-throw afternoon.
MOVED = 0.02
#: How many ripples one card carries at most.
PER_CARD = 2


def _key(name: str) -> str:
    return "".join(ch for ch in str(name or "").lower() if ch.isalnum())


def _first_week(rows, player_key: str, kind: str):
    """The first week the player had any usage in these rows, or None."""
    keys = USAGE[kind]
    weeks = [_week(r) for r in rows
             if _key(_name(r)) == player_key and _f(r, keys) > 0]
    weeks = [w for w in weeks if w is not None]
    return min(weeks) if weeks else None


def absence_rows(stats, prior_stats, team: str, player: str, kind: str,
                 season: int, week: int) -> list:
    """The rows a redistribution may read for this absence.

    FROM THE WEEK HE FIRST APPEARED, per season. `redistribution` reads
    absence off the stats — a team week with no usage from him — and
    that is right for a man who was on the roster and did not play, and
    wrong for every week before he arrived: a mid-season signing, a
    rookie, a player who changed teams would show "missed" every week
    of the season before his first, and his teammates' ordinary shares
    would be read as what they absorbed. This season runs to the week
    before the one being built (that week's stats do not exist yet, or
    exist for Thursday only); last season runs to its end.
    """
    pk = _key(player)
    out: list = []
    for rows, upto in ((prior_stats or [], None), (stats or [], week - 1)):
        mine = [r for r in rows
                if str(r.get("recent_team") or r.get("team") or "").upper() == team]
        start = _first_week(mine, pk, kind)
        if start is None:
            continue
        for r in mine:
            w = _week(r)
            if w is None or w < start or (upto is not None and w > upto):
                continue
            out.append(r)
    return out


def note_text(out_player: str, status: str, kind: str, res: dict,
              beneficiary: str) -> dict:
    """One ripple, as the card says it. The number is measured or the
    note says it could not be — never a round guess dressed as one."""
    b = (res.get("beneficiaries") or {}).get(beneficiary)
    n_out = int(res.get("n_out") or 0)
    word = "carries" if kind == "carries" else "targets"
    games = f"{n_out} missed game{'' if n_out == 1 else 's'}"
    who = out_player.split()[-1] if out_player else "teammate"
    st = (status or "out").lower()
    if res.get("enough") and b:
        d = float(b["delta"])
        if d >= MOVED:
            text = (f"{out_player} {st} — over his {games}, "
                    f"{beneficiary.split()[-1]} absorbed {d:+.0%} of the {word}")
        else:
            text = (f"{out_player} {st} — over his {games}, "
                    f"{beneficiary.split()[-1]}'s share of the {word} did not "
                    f"move ({d:+.1%})")
        return {"out": out_player, "status": status, "kind": kind,
                "n_out": n_out, "delta": round(d, 4), "measured": True,
                "with": b["with"], "without": b["without"],
                "n_without": b["n_without"], "text": text}
    why = (f"{games} since last season" if n_out
           else "he has not missed a game in the sample")
    return {"out": out_player, "status": status, "kind": kind,
            "n_out": n_out, "delta": None, "measured": False,
            "text": f"{out_player} {st} — usage likely up; not enough games "
                    f"to measure ({why})"}


def ripples_for_props(props, injuries, stats, prior_stats,
                      season: int, week: int) -> dict:
    """``{(player, market): [ripple, ...]}`` for every prop whose teammate
    at the same position is ruled out this week.

    Ethan, 2026-09-14: "RB2 Isiah Pacheco is now out till October 11th so
    RB1 ... should be seeing a lot more usage ... I wanna make sure we
    are adjusting if needed and reading this data". This is the safe
    half: the card SAYS what the stats measured about the beneficiary
    when this teammate sat, and the projection does not move. Moving it
    is a pricing change and waits on the information test
    (engine.ripplefit).
    """
    from .injuries import RULED_OUT
    out_by_team: dict = {}
    for inj in injuries or []:
        pos = str(getattr(inj, "position", "") or "").upper()
        kind = KIND_OF_POSITION.get(pos)
        if kind and str(getattr(inj, "status", "")).upper() in RULED_OUT:
            out_by_team.setdefault((str(inj.team).upper(), kind), []).append(inj)
    if not out_by_team:
        return {}
    cache: dict = {}
    result: dict = {}
    for prop in props:
        pos = str(getattr(prop, "position", "") or "").upper()
        team = str(getattr(prop, "team", "") or "").upper()
        market = getattr(prop, "market", "")
        notes = []
        for kind, group in GROUP.items():
            if pos not in group or market not in MARKETS_OF[kind]:
                continue
            for inj in out_by_team.get((team, kind), []):
                if _key(inj.player) == _key(prop.player):
                    continue                       # his own hold, not a ripple
                ck = (team, _key(inj.player), kind)
                if ck not in cache:
                    rows = absence_rows(stats, prior_stats, team, inj.player,
                                        kind, season, week)
                    cache[ck] = (redistribution(rows, team, inj.player, kind)
                                 if rows else None)
                res = cache[ck]
                if res is None:
                    continue                       # never played here: nothing to absorb
                # The beneficiary is looked up by the stats' spelling.
                name = next((n for n in res["beneficiaries"]
                             if _key(n) == _key(prop.player)), prop.player)
                notes.append(note_text(inj.player, inj.status, kind, res, name))
        if notes:
            notes.sort(key=lambda n: (-(n["delta"] if n["measured"] else -1.0),
                                      -n["n_out"]))
            result[(prop.player, market)] = notes[:PER_CARD]
    return result
