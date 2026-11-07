"""Who starts tonight, read before the tip — the starting five's news (measured 2026-11-04).

The board reads a man's minutes from his last twenty games whatever he did
in them, and his role from his newest one: started, or came off the bench.
About one game in eleven he does the other thing tonight (the lab's two
seasons: 4.6-4.9% of priced games each way), and those games carry a sixth
of the board's squared minutes error. Measured on the board's own number,
the vacancy and a regular's return included: a bench man who starts plays
3.6 minutes over it, a starter sent to the bench 3.8-4.2 under.

KNOWING TONIGHT'S FIVE OUTRIGHT would take 5.5-6.0% off the minutes error
over every priced game and 0.9-1.2% off points (each season held out). The
five is only confirmed half an hour before the tip, after most of the
board's prices are posted, so this reads what is known before then:

  * the injury report on his club's LAST STARTING FIVE — a bench man starts
    27% of the time when one of them is ruled out, 3% when all five play;
  * a RETURNING REGULAR who started before he sat (`nba_build.returning`):
    the man who started in his place goes back to the bench 19-20% of the
    time, against 6-7%;
  * HIS OWN STARTS over his last ten — a man back on the bench after
    filling in still carries the starter's minutes in his base, and plays
    under it (-2.6 to -4.0 minutes when he started half or more of them);
    a new starter's base still carries his bench games, and he plays over it.

THE RULE, six terms (`hoops.LeagueTuning.starter_news`, the NBA's fitted on
the lab's two seasons beside a level the calibration owns): for a man who
came off the bench in his newest game, ``bench_after_starts`` x the share
of his last ten he started, plus ``bench_one_out`` when one of the five is
ruled out and ``bench_two_out`` more when two or more are; for a man who
started it, ``start_after_bench`` x the share of his last ten he did NOT
start, plus ``start_one_back`` when a starter returns and
``fill_in_one_back`` x that same share on top. The minutes ride the
vacancy's slot (`minutes.project_minutes`), its caps included.

THE BAR, written before the run: each season held out in turn, the six
fitted on the other beside a level, and every season's squared error of
minutes AND points over every priced game lower with the rule than with the
level alone, through the board's own projection. HELD: minutes 1.72% /
1.28%, points 0.34% / 0.35% (in the 46% of games it moves, 3.4% / 2.3%
and 1.0% / 0.8%); points Brier at the fitters' half-point line 0.2434 ->
0.2428 and 0.2428 -> 0.2421. Refitted on both seasons for the board, beside
the second game back's haircut refitted with it (`hoops.NBA`).

On the box, nbarules.py replays it on the box's own stored seasons every
week (the weekly refit's ``nba_rules`` piece) and files its own verdict
(engine/nba/switches ``starters``): a season where it stops taking error
off the games it touches turns it off. ``QB_NBA_STARTERS=0`` turns it off
outright. The WNBA has no values (not measured there).

Standard library only.
"""
from __future__ import annotations

#: His starts are read over this many of his newest games.
WINDOW = 10
#: The six terms, in the order the docs give them.
TERMS = ("bench_after_starts", "bench_one_out", "bench_two_out",
         "start_after_bench", "start_one_back", "fill_in_one_back")
#: A shift this small moves nothing worth a line on the card.
NOTE_MIN = 0.5


def on() -> bool:
    """The board's switch: the environment, else the box's own verdict."""
    from .switches import is_on
    return is_on("starters")


def share(starts, n: int = WINDOW):
    """The share of his newest ``n`` games he started, or None unread."""
    v = [bool(s) for s in list(starts or [])[:n]]
    return sum(v) / len(v) if v else None


def read(starts, five_out: int = 0, five_back: int = 0) -> dict:
    """``{term: value}`` for one man — every term 0.0 with his starts
    unknown. ``starts`` newest first, aligned with his minutes;
    ``five_out`` how many of his club's last starting five are ruled out
    tonight; ``five_back`` how many returning regulars started before they
    sat (himself never counted)."""
    out = dict.fromkeys(TERMS, 0.0)
    x = share(starts)
    if x is None:
        return out
    try:
        o, k = int(five_out or 0), int(five_back or 0)
    except (TypeError, ValueError):
        o, k = 0, 0
    if bool(list(starts)[0]):
        out["start_after_bench"] = 1.0 - x
        if k >= 1:
            out["start_one_back"] = 1.0
            out["fill_in_one_back"] = 1.0 - x
    else:
        out["bench_after_starts"] = x
        out["bench_one_out"] = 1.0 if o >= 1 else 0.0
        out["bench_two_out"] = 1.0 if o >= 2 else 0.0
    return out


def minutes(starts, five_out: int = 0, five_back: int = 0, tune=None) -> float:
    """Tonight's minutes from the starting five's news: 0.0 with no values
    for the league, the switch off, or his starts unknown."""
    coef = dict(getattr(tune, "starter_news", None) or {})
    if not coef or not on():
        return 0.0
    terms = read(starts, five_out, five_back)
    return round(sum(float(coef.get(k, 0.0) or 0.0) * v for k, v in terms.items()), 2)


def note(starts, five_out: int, five_back: int, shift: float) -> str:
    """The card's line where the news moved him ``NOTE_MIN`` or more."""
    if abs(float(shift or 0.0)) < NOTE_MIN:
        return ""
    x = share(starts)
    if x is None:
        return ""
    k10 = round(x * min(WINDOW, len(list(starts))))
    n10 = min(WINDOW, len(list(starts)))
    sign = f"{shift:+.1f} minutes"
    if bool(list(starts)[0]):
        if int(five_back or 0) >= 1:
            return (f"A starter is back tonight and he started {k10} of his last {n10} — "
                    f"{sign} (measured: the fill-in is the one who goes back to the bench)")
        return (f"Starting lately after coming off the bench ({k10} of his last {n10}) — {sign} "
                f"(measured: a new starter plays over a base made partly of bench games)")
    if int(five_out or 0) >= 1:
        one = int(five_out) == 1
        who = "one of his club's last starting five is" if one else \
              f"{int(five_out)} of his club's last starting five are"
        return (f"Off the bench, and {who} ruled out tonight — {sign} "
                f"(measured: a bench man starts {'about a quarter' if one else 'nearly half'} "
                f"of the time then)")
    return (f"Back on the bench after starting {k10} of his last {n10} — {sign} "
            f"(measured: his base still carries the starter's minutes)")


def club_news(team: str, hist: dict, days: list, gone: dict, back: dict) -> tuple[list, list]:
    """``(his club's last starting five ruled out tonight, the returning
    regulars who started before they sat)`` from what the build already
    read: ``hist`` (`nba_build.player_history`, each man's ``starts`` and
    ``dates`` newest first), ``days`` the club's game dates before tonight
    newest first (`nba_build.club_days`), ``gone`` tonight's ruled-out men
    (`nba_build.absences`), ``back`` tonight's returning regulars
    (`nba_build.returning`)."""
    if not days:
        return [], []
    last = str(days[0])
    five = []
    for name, h in (hist or {}).items():
        if h.get("team") != team:
            continue
        dates, starts = list(h.get("dates") or []), list(h.get("starts") or [])
        if dates and starts and str(dates[0]) == last and bool(starts[0]):
            five.append(name)
    out_names = {n for n, _m in (gone or {}).get(team, [])}
    five_out = sorted(n for n in five if n in out_names)
    returning = []
    for name, _m in (back or {}).get(team, []):
        starts = list((hist.get(name) or {}).get("starts") or [])
        if starts and bool(starts[0]):
            returning.append(name)
    return five_out, sorted(returning)
