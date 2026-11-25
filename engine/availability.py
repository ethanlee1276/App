"""Who may not play, for the game reports (2026-11-14).

Ethan, 2026-11-14, a screenshot of Miami vs Duke: "our player reports ...
doesn't recognize when a player is injured, so it still tells you that an
injured player could have a good matchup or they could do good that game,
even if they're ruled out ... we also need to be careful when a player is
actually ruled out and ruled questionable, and we need to mark that as well,
because we don't want to judge a game off of a player that may or may not be
playing." And: "that issue ... affects all sports, not just cfb".

The report named Malachi Toney under "Who could have a big day" and "Could
shine". The football scan already drops a man the injury report rules out;
the report had nothing behind it when the report is silent, and college's
is silent on most players (ESPN posts few college injuries; its college
basketball report was empty on 14 November). Toney had not played since 31
October: Miami's game at Notre Dame on 7 November has no line of his.

Every report reads its players through `annotate` now, one rule for every
league:

  * OUT, DOUBTFUL, suspended, on an injured list or reserve, or every book
    took his props down: no read. A man who will not play is not a player
    to watch, and a doubtful one almost never plays.
  * QUESTIONABLE, a game-time decision, day-to-day: kept, marked, and left
    out of the short version's "big day / hard day" lines, so the game is
    never summed up through a man who may sit.
  * NOT IN HIS TEAM'S LAST GAME and on no report (`missed`): the same mark,
    with the game he missed, and the same care in the short version.

The reads are copies: the board's own `scan_reads` are not touched.
"""
from __future__ import annotations

import datetime as _dt

OUT, DOUBTFUL, QUESTIONABLE, MISSED = "out", "doubtful", "questionable", "missed_last"

#: The marks a reader sees on a card, by availability.
LABELS = {QUESTIONABLE: "Questionable", MISSED: "Missed last game"}


def word(raw) -> str:
    """An injury designation as one of OUT, DOUBTFUL, QUESTIONABLE, or ""
    (probable, active, or nothing said). Every league's words: the NFL's
    and college's, the NBA's, the NHL's day-to-day, MLB's injured lists."""
    s = " ".join(str(raw or "").lower().replace("-", " ").replace("_", " ").split())
    if not s:
        return ""
    if "doubtful" in s:
        return DOUBTFUL
    if "questionable" in s or "game time" in s or s in ("gtd", "q", "day to day", "dtd"):
        return QUESTIONABLE
    if "probable" in s or s in ("active", "available", "healthy"):
        return ""
    if (s in ("o", "out", "ir", "il", "inactive", "suspended", "suspension", "pup", "nfi", "ltir",
              "reserve", "not with team", "personal")
            or s.startswith("out") or "injured reserve" in s or "injured list" in s
            or s.endswith(" il") or "suspen" in s or "reserve" in s):
        return OUT
    return ""


def _key(name) -> str:
    try:
        from .sources.oddsapi import normalize_name
        return normalize_name(str(name or ""))
    except Exception:                                        # noqa: BLE001
        return " ".join(str(name or "").lower().split())


def statuses(c) -> dict:
    """``{name key: OUT | DOUBTFUL | QUESTIONABLE}`` from whatever the report
    holds: football's scan (its injury rows and the props every book took
    down), basketball's meta (the injury report), the NHL's and the NBA's
    tapes (each side's injuries and pulled props), MLB's injured list. The
    strongest word wins when two sources disagree."""
    rank = {OUT: 3, DOUBTFUL: 2, QUESTIONABLE: 1}
    out: dict = {}

    def put(name, w):
        k = _key(name)
        if k and w and rank.get(w, 0) > rank.get(out.get(k, ""), 0):
            out[k] = w
    scan = getattr(c, "scan", None) or {}
    for r in scan.get("injuries") or []:
        if isinstance(r, dict):
            put(r.get("player"), word(r.get("status")))
    for name in scan.get("pulled") or []:
        put(name, OUT)
    meta = getattr(c, "meta", None) or {}
    for r in meta.get("injuries") or []:
        if isinstance(r, dict):
            put(r.get("player"), word(r.get("status")))
    g = getattr(c, "g", None) or {}
    for tape_key in ("nhl_tape", "nba_tape", "mlb_tape"):
        tape = g.get(tape_key) or {}
        for side in (tape.get("sides") or {}).values():
            for r in (side or {}).get("injuries") or []:
                if isinstance(r, dict):
                    put(r.get("player"), word(r.get("status")))
        for name in tape.get("pulled") or []:
            put(name, OUT)
    result = getattr(c, "result", None) or {}
    for name in result.get("injured_list") or []:
        put(name.get("player") if isinstance(name, dict) else name, OUT)
    return out


def _when_key(g: dict, sport: str):
    """A game's place in time: the NFL's (season, week), else its day."""
    if g.get("week") is not None:
        try:
            return (int(g.get("season") or 0), int(g["week"]))
        except (TypeError, ValueError):
            return None
    try:
        return _dt.date.fromisoformat(str(g.get("day") or g.get("date") or "")[:10])
    except ValueError:
        return None


def _later(a, b, sport: str) -> bool:
    """Whether game ``a`` is a later game than ``b``. College's days are a
    week apart and its stored days can sit one either side of the game
    (its kickoff's Eastern day and its UTC day), so three days or more."""
    if a is None or b is None:
        return False
    if isinstance(a, tuple) and isinstance(b, tuple):
        return a > b
    if isinstance(a, _dt.date) and isinstance(b, _dt.date):
        gap = (a - b).days
        return gap >= (3 if sport in ("cfb", "nfl") else 1)
    return False


def missed(c) -> dict:
    """``{name key: {"team", "game"}}``: a player whose newest stored game
    is older than his team's newest. Football's off the report's own form
    (each player's games, newest first); basketball's off its meta (the
    build's `nba_meta` writes it from the player history). A football row
    exists only for a man who recorded a stat, so the card says "no stat
    line", never "did not play"."""
    out: dict = dict((getattr(c, "meta", None) or {}).get("missed") or {})
    form = getattr(c, "form", None) or {}
    sport = getattr(c, "sport", "")
    teams = set(getattr(c, "teams", ()) or ())
    newest: dict = {}
    for rec in form.values():
        g0 = (rec.get("games") or [None])[0] if isinstance(rec, dict) else None
        if not g0 or g0.get("team") not in teams:
            continue
        k = _when_key(g0, sport)
        cur = newest.get(g0["team"])
        if k is not None and (cur is None or _later(k, cur[0], sport) or
                              (isinstance(k, tuple) and k > cur[0])):
            newest[g0["team"]] = (k, g0)
    for name, rec in form.items():
        g0 = (rec.get("games") or [None])[0] if isinstance(rec, dict) else None
        if not g0 or g0.get("team") not in newest:
            continue
        team_k, team_g = newest[g0["team"]]
        if _later(team_k, _when_key(g0, sport), sport):
            out[_key(name)] = {"team": g0["team"], "game": team_g, "kind": "stat"}
    return out


def _game_words(g: dict, c=None) -> str:
    """"Nov. 7 at Notre Dame", "Wk 10 vs Bears", "Nov. 11": the game a man
    missed, in the report's own words."""
    from .gamereport import day_label, week_label
    current = int(getattr(c, "season", 0) or 0) if c is not None else 0
    season = int(g.get("season") or current or 0)
    if g.get("week") is not None:
        when = week_label(season, int(g["week"]), current or season)
    else:
        when = day_label(str(g.get("day") or ""), season, current or season)
    opp = g.get("opp") or ""
    if not opp:
        return when
    name = c.name(opp) if c is not None and hasattr(c, "name") else opp
    return f"{when} {'at' if g.get('where') == 'away' else 'vs'} {name}"


def note(r: dict, c=None) -> str:
    """The sentence a marked card carries."""
    a = r.get("availability")
    if a == QUESTIONABLE:
        return (f"{r.get('player')} is listed questionable — this read only holds if the player plays; "
                "check the injury report before you bet on this player")
    if a == MISSED:
        m = r.get("missed") or {}
        g = m.get("game") or {}
        team = m.get("team") or r.get("team") or ""
        name = c.name(team) if c is not None and hasattr(c, "name") else team
        where = ""
        if g:
            where = f" ({_game_words(g, c)})"
        what = "no stat line" if m.get("kind") == "stat" else "did not play"
        # "the Packers' last game", never "Packers's last game" (step AHO; Ethan's screenshot of GB @ LA): the
        # report's own possessive where it has one (gamereport.team_owner), else the name's.
        owner = f"{name}'" if str(name).endswith("s") else f"{name}'s"
        if c is not None and hasattr(c, "poss") and team:
            try:
                from .gamereport import team_owner
                owner = team_owner(c, team)
            except Exception:                                   # noqa: BLE001 - the plain possessive stands
                pass
        return (f"{r.get('player')} had {what} in {owner} last game{where} and is on no injury report "
                "— the player may be hurt or held out; check the lineup before you bet"
                if what == "no stat line" else
                f"{r.get('player')} did not play in {owner} last game{where} and is on no injury report "
                "— check the lineup before you bet")
    return ""


def annotate(c) -> list:
    """The report's reads, minus the men who will not play, each of the rest
    marked with its availability (copies; the board's rows untouched)."""
    st = statuses(c)
    gone = missed(c)
    out = []
    for r in getattr(c, "reads", None) or []:
        k = _key(r.get("player"))
        w = st.get(k) or word(r.get("own_status"))
        if w in (OUT, DOUBTFUL):
            continue
        row = dict(r)
        if w == QUESTIONABLE:
            row["availability"] = QUESTIONABLE
        elif k in gone:
            row["availability"] = MISSED
            row["missed"] = gone[k]
        if row.get("availability"):
            row["availability_note"] = note(row, c)
        out.append(row)
    return out


def sure(r: dict) -> bool:
    """A read the short version may sum the game up through: nothing says
    he may sit."""
    return not r.get("availability")
