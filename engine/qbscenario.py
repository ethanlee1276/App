"""If the starting quarterback plays, and if he sits (step ABS, 22 November 2026).

Ethan, the Sunday morning: "we can start making game reports, at least for NFL and college football at first,
for like if a significant player is out. As in, example, today for the Lions game, it's not confirmed if Baker
Mayfield is playing or not yet. So we should have a game report ready for if Baker Mayfield is in and one if he's
not in, because obviously that can change. It has like a big effect on the game, and users are going to want to see
that and know that before the game starts."

WHAT THE BOARD DID. A starter listed out (or doubtful: engine/injuries.RULED_OUT) is a quarterback change
(engine/qbchange): his backup starts, and the receivers' numbers move by the measured effect. A starter listed
questionable, or a game-time decision, moved nothing: the board priced the game as if he plays, held his own props,
and said one warning line. Whether he played was the biggest question about the game, and the report answered only
one side of it.

WHAT THIS ADDS. For every team whose starting quarterback is questionable or a game-time decision, the team's props
are priced twice through the board's own pricing (`price`, engine/pipeline.price_props with the build's arguments):
once as the board prices them (he plays) and once with the change qbchange would make if he were ruled out (his
backup starts, the measured effect on the receivers). Each prop's chance of going over, both ways, rides on the
board (`result["qb_scenarios"]`), and the game's report says both (engine/gamereport.sec_swing): who starts if he
sits, what it does, and how each of the team's numbers moves. The picks still post once, after the inactives
(engine/gamereport.picks_timeline), from whichever version holds then.

Nothing here changes a number the board posts: it is the second version, said beside the first.
"""
from __future__ import annotations

#: Statuses that leave a starter's game open: the engine already prices out and doubtful as out (RULED_OUT).
UNSURE = ("QUESTIONABLE", "GTD")


def _norm(name) -> str:
    return " ".join(str(name or "").lower().replace(".", " ").replace("'", "").split())


def unsure_starters(starters: dict, injuries: list) -> dict:
    """{team: {"starter", "status"}} for each team whose starting quarterback (``starters``: {team: name}) is listed
    questionable or a game-time decision. Never raises."""
    out: dict = {}
    try:
        listed = {}
        for i in injuries or []:
            st = str(getattr(i, "status", "") or "").upper()
            if st in UNSURE:
                listed[(getattr(i, "team", ""), _norm(getattr(i, "player", "")))] = st
        for team, starter in sorted((starters or {}).items()):
            st = listed.get((team, _norm(starter))) if starter else None
            if st:
                out[team] = {"starter": starter, "status": st}
    except Exception:                                        # noqa: BLE001
        return {}
    return out


def nfl_starters(qb: dict) -> dict:
    """{team: starter} off the NFL's carry report (engine/qbchange: the team's leading passer)."""
    return {t: (slot or {}).get("starter") for t, slot in ((qb or {}).get("teams") or {}).items()
            if (slot or {}).get("starter")}


def cfb_starters(passers: dict) -> dict:
    """{team: starter} off college's passers (engine/cfb/qbchange.passers: the team's usual quarterback)."""
    return {t: (q or {}).get("usual") for t, q in (passers or {}).items() if (q or {}).get("usual")}


def _p_over(row: dict):
    """A priced row's chance of going over its line, whichever side it was evaluated on; None when unpriced."""
    try:
        p = float(row.get("hit_prob"))
    except (TypeError, ValueError):
        return None
    side = str(row.get("side") or "").upper()
    return p if side in ("OVER", "YES") else 1.0 - p if side in ("UNDER", "NO") else None


def _priced(slate, team: str, change, price) -> dict:
    """{(player, market, line): P(over)} for ``team``'s props, priced with ``change`` as the team's quarterback
    change (None: as the board has it). The slate and its game are restored however pricing ends."""
    import dataclasses
    game = next((g for g in slate.games if team in (g.home, g.away)), None)
    if game is None:
        return {}
    saved = getattr(game, "qb_changes", None)
    try:
        chs = dict(saved or {})
        if change is not None:
            chs[team] = change
        game.qb_changes = chs
        sub = dataclasses.replace(slate, props=[p for p in slate.props if getattr(p, "team", "") == team])
        rows = price(sub) or []
    finally:
        game.qb_changes = saved
    out = {}
    for r in rows:
        p = _p_over(r) if isinstance(r, dict) else None
        if p is not None and r.get("line") is not None:
            out[(str(r.get("player") or ""), str(r.get("market") or ""), float(r["line"]))] = \
                (p, str(r.get("position") or ""))
    return out


def build(slate, starters: dict, injuries: list, changes_fn, price, sport: str = "nfl") -> list:
    """Each unsure starter's two versions: [{team, starter, status, replacement, tier, headline, rows}], rows each
    {player, position, market, line, plays, sits} (P(over) both ways), the props that move most first.
    ``starters`` is {team: starter}; ``changes_fn(injuries)`` is the league's own quarterback change
    (engine/qbchange.changes, engine/cfb/qbchange.changes) on a list of injuries; ``price(slate)`` prices a slate
    as the board does. [] when no starter is unsure; never raises (a team that fails is left out, said in the log)."""
    from . import qbchange as _qbc
    from .models import Injury
    out = []
    for team, who in unsure_starters(starters, injuries).items():
        try:
            pretend = [i for i in injuries or [] if not (getattr(i, "team", "") == team
                                                       and _norm(getattr(i, "player", "")) == _norm(who["starter"]))]
            pretend.append(Injury(player=who["starter"], team=team, position="QB", role="qb", status="OUT"))
            ch = (changes_fn(pretend) or {}).get(team)
            if not ch or not ch.get("replacement"):
                continue
            if sport == "cfb":
                ch = dict(ch, league="cfb")
            plays = _priced(slate, team, None, price)
            sits = _priced(slate, team, ch, price)
            rows = []
            for key, (p0, pos) in plays.items():
                if key not in sits or _norm(key[0]) == _norm(who["starter"]):
                    continue
                p1 = sits[key][0]
                rows.append({"player": key[0], "position": pos, "market": key[1], "line": key[2],
                             "plays": round(p0, 4), "sits": round(p1, 4)})
            rows.sort(key=lambda r: (-abs(r["sits"] - r["plays"]), r["player"]))
            out.append({"team": team, "starter": who["starter"], "status": who["status"],
                        "replacement": ch.get("replacement"), "tier": ch.get("tier"),
                        "headline": _qbc.headline(dict(ch, status=who["status"])), "rows": rows})
        except Exception as exc:                             # noqa: BLE001
            print(f"  ⚠️ {team}'s if-he-sits version not built ({type(exc).__name__}: {exc})")
    return out


#: How old the injury board's newest word on a starter may be and still be said: a blurb from before the
#: week's last report is about another game.
NEWS_MAX_AGE_S = 3 * 86400


def attach_news(scenarios: list, league: str, rows=None, team_key=None, now: float | None = None) -> list:
    """Each scenario's newest word on its starter off ESPN's injury board (``rows``: espninjuries.parse_injuries
    rows; read through the board's own ten-minute cache when None): ``news`` = {"text", "posted"}, the blurb ESPN
    files with his designation ("Mayfield (foot/right thumb) is slated to play in Sunday's game against the Lions,
    Ian Rapoport of NFL Network reports") and when it was posted. ``team_key`` maps ESPN's club name to the
    board's key (the NFL's abbreviations by default; college passes its school resolver). A starter with no
    blurb, or only an old one, carries none. Never raises; returns ``scenarios``."""
    try:
        import time as _time
        from .sources.espninjuries import _parse_iso_ts, current_rows
        if not scenarios:
            return scenarios
        if rows is None:
            from .sources.espninjuries import fetch_injuries, parse_injuries
            rows = parse_injuries(fetch_injuries(league))
        if team_key is None:
            from .sources.oddsapi import TEAM_ABBR
            team_key = TEAM_ABBR.get
        now = _time.time() if now is None else now
        newest = {}
        for r in current_rows(rows or []):
            try:
                team = team_key(r.get("team") or "")
            except Exception:                                # noqa: BLE001
                team = None
            if team:
                newest[(team, _norm(r.get("player")))] = r
        for sc in scenarios:
            r = newest.get((sc.get("team"), _norm(sc.get("starter"))))
            text = " ".join(str((r or {}).get("comment") or "").split())
            posted = _parse_iso_ts((r or {}).get("date"))
            if text and posted is not None and 0 <= now - posted <= NEWS_MAX_AGE_S:
                sc["news"] = {"text": text[:400], "posted": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime(posted))}
    except Exception as exc:                                 # noqa: BLE001
        print(f"  ⚠️ the starters' newest injury word not read ({type(exc).__name__}: {exc})")
    return scenarios


def for_game(result: dict, teams) -> list:
    """The board's scenarios for this game's teams."""
    return [s for s in (result or {}).get("qb_scenarios") or []
            if isinstance(s, dict) and s.get("team") in set(teams or ())]
