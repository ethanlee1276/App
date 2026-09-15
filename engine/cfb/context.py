"""The §9 grade's five context scores, each derived from something real.

The grade is 40% edge and 60% context, so the context scores decide most of
what gets bet. That makes them the easiest place in the whole system to
cheat: five numbers between 0 and 1, invisible on the page, and any value
looks plausible. So every one of them here is a restatement of a fact the
build actually has, and where the fact is missing the score says "half" and
the reason says why — rather than quietly assuming the best case.

* **attention fit** — the module's own thesis. An edge is plausible in a
  Wednesday MAC game and implausible in a game the entire market has
  stared at for a week.
* **situational** — letdown, lookahead and short weeks, computed from the
  schedule either side of this one. These are the §7 spots, and they are
  the only ones a schedule can prove.
* **matchup** — honestly, *do we have a read at all?* With ratings built
  from scores, the answer is a function of how many games each side has
  played. Calling that "scheme fit" would be a lie; scoring it as sample
  size is the truthful version of the same question.
* **environment** — a dome is a known environment, which is worth full
  marks. An outdoor game with no weather pulled is not, and a TOTAL in
  that game is the bet most exposed to it.
* **information** — participation and weather. Quarterback status is
  deliberately NOT scored here: §2.3 makes it a gate, and charging for it
  twice would mean the board never surfaces the games worth checking.
"""

from __future__ import annotations

import datetime as _dt

from .model import LOW, MARQUEE, STANDARD

# How plausible is an edge at each tier? This IS the thesis, as a number.
ATTENTION_FIT = {LOW: 1.0, STANDARD: 0.6, MARQUEE: 0.25}

FULL_SAMPLE = 8          # games per team before the ratings stop being thin


def attention_fit(tier: str) -> float:
    return ATTENTION_FIT.get(tier, 0.6)


def matchup_fit(home_games: int, away_games: int) -> float:
    """Sample size behind the two ratings, as a 0–1 score."""
    thin = min(int(home_games or 0), int(away_games or 0))
    return round(min(1.0, thin / FULL_SAMPLE), 3)


def environment_fit(game: dict, market: str = "side") -> float:
    if game.get("indoor"):
        return 1.0
    if game.get("weather_checked"):
        return 0.9
    # Outdoors with no weather read. A total lives or dies on it.
    return 0.45 if market in ("total", "team_total") else 0.6


def _days_between(a: str, b: str) -> int | None:
    try:
        return abs((_dt.date.fromisoformat(a[:10])
                    - _dt.date.fromisoformat(b[:10])).days)
    except (ValueError, TypeError):
        return None


def situational_tags(game: dict, history: dict, upcoming: dict) -> list[str]:
    """§7 spots provable from the schedule.

    ``history`` and ``upcoming`` are ``{team: game dict}`` for each side's
    previous and next game.
    """
    tags: list[str] = []
    date = game.get("date") or (game.get("kickoff") or "")[:10]
    for team in (game.get("home", ""), game.get("away", "")):
        prev, nxt = history.get(team), upcoming.get(team)
        if prev:
            opp_rank = (prev.get("home_rank") if prev.get("away") == team
                        else prev.get("away_rank"))
            if opp_rank:
                tags.append("letdown")
            gap = _days_between(date, prev.get("date") or "")
            if gap is not None and gap <= 6:
                tags.append("short_week")
        if nxt:
            opp_rank = (nxt.get("home_rank") if nxt.get("away") == team
                        else nxt.get("away_rank"))
            if opp_rank:
                tags.append("lookahead")
    if game.get("conference_game") and game.get("week") and int(game["week"]) >= 12:
        tags.append("rivalry")           # late-season conference games are
    return sorted(set(tags))             # where the rivalry dates live


def situational_fit(tags: list[str]) -> float:
    """A spot with nothing flagged is neutral, not good.

    0.6 is the honest baseline — most games have no situational story, and
    scoring those as perfect would hand out ten free grade points to every
    play on the board.
    """
    score = 0.6
    for t in tags:
        if t in ("letdown", "lookahead", "short_week"):
            score += 0.15               # these are the spots we WANT to find
        if t == "rivalry":
            score -= 0.15               # chaos cuts both ways; stake less
    return round(max(0.0, min(1.0, score)), 3)


def neighbours(games_before: list[dict], games_after: list[dict]
               ) -> tuple[dict, dict]:
    """``({team: previous game}, {team: next game})`` from the surrounding
    boards, keeping the closest game on each side."""
    prev: dict = {}
    nxt: dict = {}
    for g in sorted(games_before, key=lambda x: x.get("date") or ""):
        for t in (g.get("home"), g.get("away")):
            if t:
                prev[t] = g              # latest wins
    for g in sorted(games_after, key=lambda x: x.get("date") or "", reverse=True):
        for t in (g.get("home"), g.get("away")):
            if t:
                nxt[t] = g               # earliest wins
    return prev, nxt
