"""Ask Qellys, shown as well as said: the steps, the cards, the next questions.

Ethan, 2026-10-27: "go on to looking at our Ask Kelly feature and auditing
that and making that look better visually, and then also making it function
better. Look at other apps that use AI betting ... and do it better."

What the others do (FanDuel's AceAI, Action Network's Playbook, Rithmm's
Scout, Gambly, RotoBot): the answer is a sentence and a slip. What none of
them shows is its work, and the numbers behind it as numbers. This module is
that half, three pieces, all built in code from what the lookups returned,
never from the model's words:

  STEPS   each lookup as it starts, in words ("Checking Josh Allen's passing
          yards history"), streamed to the page while the answer is written
          (server.py `_ask`, `stream`), then kept with the answer.
  CARDS   the lookups' own numbers drawn: a hit-rate card (the last five, the
          last ten, the season and every stored game against the line, and
          the last ten games as bars), a price card (every book's price, the
          best marked), a record card and a start/sit card. A card is the
          tool's output, so it can never say a number the data does not.
  NEXT    up to three questions a reader would ask next, from what this
          answer looked up and who it was about.

Standard library and engine/slipgrade's leg cleaner only; pure functions.
"""
from __future__ import annotations

from engine import slipgrade as _SG

#: At most this many cards under one answer: two numbers-heavy panels is a
#: lot on a phone.
MAX_CARDS = 2
#: At most this many suggested next questions.
MAX_FOLLOW = 3


def _s(v) -> str:
    return str(v or "").strip()


def step_label(name: str, args) -> str:
    """What a lookup is doing, said before it has answered."""
    a = args if isinstance(args, dict) else {}
    player, team = _s(a.get("player")), _s(a.get("team"))
    sport = _s(a.get("sport")).upper()
    q = _s(a.get("query"))
    if name == "prop_hit_rate":
        stat = _s(a.get("stat")) or "stat"
        return f"Checking {player}’s {stat} history against the line" if player else "Checking a hit rate"
    if name == "player_history":
        opp = _s(a.get("opponent"))
        return f"Pulling {player}’s game log" + (f" against {opp}" if opp else "") if player else "Pulling a game log"
    if name == "team_history":
        opp = _s(a.get("opponent"))
        return f"Looking up {team} against {opp}" if team and opp else f"Looking up {team}’s results" if team \
            else "Looking up a team’s results"
    if name == "tonight_board":
        return f"Reading tonight’s {sport} board" if sport else "Reading tonight’s boards"
    if name == "line_shop":
        return f"Comparing every book’s price for {q}" if q else "Comparing book prices"
    if name == "our_picks":
        return "Reading our picks for tonight"
    if name == "our_picks_live":
        return "Checking our bets in play"
    if name == "our_record":
        return "Reading our graded record"
    if name == "zeno_record":
        return "Reading Zeno’s record"
    if name == "injuries":
        return f"Checking the injury report for {player or team}" if (player or team) else "Checking the injury report"
    if name == "live_scores":
        return "Checking live scores"
    if name == "slate":
        return "Reading tonight’s slate"
    if name == "schedule":
        return f"Reading {team}’s schedule" if team else "Reading a schedule"
    if name == "standings":
        return f"Reading the {sport} standings" if sport else "Reading the standings"
    if name == "league_table":
        return "Ranking the league"
    if name == "player_leaders":
        return f"Ranking the {sport} leaders" if sport else "Ranking the leaders"
    if name == "team_trends":
        return f"Reading {team}’s betting trends" if team else "Reading betting trends"
    if name == "team_efficiency":
        return f"Reading {team}’s efficiency" if team else "Reading team efficiency"
    if name == "futures":
        return "Reading futures prices"
    if name == "news":
        return "Reading the latest news"
    if name == "roster":
        return f"Reading {team}’s roster" if team else "Reading a roster"
    if name == "prediction_markets":
        return "Reading Kalshi and Polymarket"
    if name == "market_moves":
        return "Reading the live market feed"
    if name == "odds_calc":
        return "Doing the odds arithmetic"
    if name == "book_report":
        return "Reading the books’ report card"
    if name == "fantasy":
        return "Reading the fantasy desk"
    if name == "fantasy_points":
        names = [p for p in (a.get("players") or []) if isinstance(p, str)]
        return ("Scoring " + ", ".join(names[:3]) + " in fantasy points") if names else "Scoring fantasy points"
    if name == "defense_vs_position":
        pos = _s(a.get("position")).upper()
        return f"Checking defenses against {pos}s" if pos else "Checking defenses by position"
    if name == "web_search":
        return "Searching the web"
    return "Looking it up"


# ---- the bet a card is about ------------------------------------------------------------------
#: What a card carries of tonight's bet so the page can act on it — add it to
#: the slip, track it in My Bets, watch the player. The board row's own keys,
#: so the slip's leg is the leg the board would have added.
BET_KEYS = ("market", "market_label", "team", "opponent", "matchup", "game_date", "stake_units")


def _bet(sport, player, row: dict, book=None, odds=None) -> dict | None:
    """Tonight's priced player bet, from a board row: who, which market,
    which side at which number, at which book and price. None unless all of
    those are there: a button that adds half a bet is worse than none."""
    if not isinstance(row, dict):
        return None
    side = str(row.get("side") or "").upper()
    odds = row.get("odds") if odds is None else odds
    book = row.get("book") if book is None else book
    if not (sport and player and row.get("market") and side in ("OVER", "UNDER")
            and row.get("line") is not None and isinstance(odds, (int, float)) and odds):
        return None
    bet = {"sport": str(sport).lower(), "player": player, "side": side, "line": row.get("line"),
           "odds": int(odds), "book": book or ""}
    bet.update({k: row[k] for k in BET_KEYS if row.get(k) not in (None, "")})
    # Whether the box can follow it: a leg the screenshot checker's own
    # cleaner keeps (engine/slipgrade.clean_slip), which is what the Live tab
    # and the slip watch read it through.
    bet["trackable"] = bool(_SG.clean_slip({"legs": [{"sport": bet["sport"], "player": player, "team": bet.get("team"),
                                                      "market": bet["market"], "side": side.lower(),
                                                      "line": bet["line"], "odds": bet["odds"]}]})["legs"])
    return bet


# ---- the cards ------------------------------------------------------------------------------
def _rate(t: dict, side: str):
    if not isinstance(t, dict) or not t.get("games"):
        return None
    hit = t.get("over" if side == "over" else "under") or 0
    decided = t["games"] - (t.get("push") or 0)
    return {"hit": hit, "of": decided, "rate": t.get(f"{side}_hit_rate"), "avg": t.get("average")}


def hits_card(out: dict) -> dict | None:
    """prop_hit_rate's own tallies, and its last ten games."""
    if not isinstance(out, dict) or out.get("error") or out.get("found") is False or out.get("line") is None:
        return None
    side = "under" if str(out.get("side")) == "under" else "over"
    windows = []
    for key, label in (("last_5", "Last 5"), ("last_10", "Last 10")):
        r = _rate(out.get(key), side)
        if r:
            windows.append({"label": label, **r})
    season = next((k for k in out if k.startswith("season_")), None)
    if season:
        r = _rate(out.get(season), side)
        if r:
            windows.append({"label": season.split("_", 1)[1], **r})
    r = _rate(out.get("every_stored_game"), side)
    if r:
        windows.append({"label": "All", **r})
    if out.get("against"):
        r = _rate(out["against"], side)
        if r:
            windows.append({"label": f"vs {_s(out['against'].get('opponent'))[:12]}", **r})
    if not windows:
        return None
    games = [{"vs": _s(g.get("vs"))[:4], "value": g.get("value")}
             for g in (out.get("last_10_games") or []) if isinstance(g, dict) and g.get("value") is not None]
    card = {"kind": "hits", "player": out.get("player"), "stat": out.get("stat"), "side": side,
            "line": out.get("line"), "windows": windows[:5], "games": games[:10]}
    t = out.get("tonight")
    if isinstance(t, dict):
        card["tonight"] = {k: t.get(k) for k in ("side", "line", "odds", "book", "model_prob", "tier")
                           if t.get(k) is not None}
        # The buttons act on tonight's bet only when it is the one the card
        # is about: the same side at the same number. Asked about the other
        # side, or another line, there is no price on the board to act at.
        same = str(t.get("side") or "").lower() == side and _same_line(t.get("line"), out.get("line"))
        bet = _bet(out.get("sport"), out.get("player"), t) if same else None
        if bet:
            card["bet"] = bet
    return card


def _same_line(a, b) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (TypeError, ValueError):
        return False


def prices_card(out: dict) -> dict | None:
    """line_shop's first pick: every book's price, the best on our side."""
    picks = (out or {}).get("picks") if isinstance(out, dict) else None
    if not picks:
        return None
    p = picks[0]
    books = [b for b in p.get("books") or [] if isinstance(b, dict) and b.get("book")]
    if not books:
        return None
    best = p.get("best_price_at_this_line") or {}
    card = {"kind": "prices", "pick": p.get("pick"), "books": books[:8], "best": best.get("book"),
            "best_odds": best.get("odds")}
    mv = p.get("line_move") or {}
    if mv.get("open") is not None and mv.get("current") is not None:
        card["move"] = {"open": mv["open"], "current": mv["current"]}
    # THE LINE'S PATH since it opened (docs/IDEAS.md round three), drawn as a
    # small chart under the books: the points line_shop already returns.
    tape = [{"line": t["line"], "minutes_ago": t.get("minutes_ago")} for t in p.get("line_since_open") or []
            if isinstance(t, dict) and isinstance(t.get("line"), (int, float))]
    if len(tape) > 1:
        card["tape"] = tape
    # The bet at the best price on our side, where one was found; else ours.
    bet = _bet(p.get("league"), p.get("player"), p, book=best.get("book") if best.get("odds") else p.get("our_book"),
               odds=best.get("odds") or p.get("our_price"))
    if bet:
        card["bet"] = bet
    return card


def record_card(out: dict) -> dict | None:
    """our_record's headline and its last thirty days."""
    if not isinstance(out, dict) or out.get("error"):
        return None
    head = out.get("all_bets") or {}
    if not head.get("settled"):
        return None
    card = {"kind": "record", "wins": head.get("wins"), "losses": head.get("losses"), "pushes": head.get("pushes"),
            "roi": head.get("roi"), "units": head.get("net_units"), "settled": head.get("settled"),
            "since": out.get("since")}
    last = out.get("last_30_days")
    if isinstance(last, dict):
        card["last_30"] = {k: last.get(k) for k in ("wins", "losses", "net_units")}
    return card


def startsit_card(out: dict) -> dict | None:
    """fantasy_points with two or more players: their projections and the call."""
    players = (out or {}).get("players") if isinstance(out, dict) else None
    if not players or len(players) < 2:
        return None
    rows = [{"player": p.get("player"), "team": p.get("team"), "position": p.get("position"),
             "opponent": p.get("opponent"), "points": p.get("projected_points"),
             "injury": p.get("injury")} for p in players[:4] if isinstance(p, dict)]
    card = {"kind": "startsit", "scoring": out.get("scoring"), "players": rows}
    call = (out.get("compare") or {}).get("call") if isinstance(out.get("compare"), dict) else None
    if isinstance(call, dict) and call.get("start"):
        card["call"] = {"start": call.get("start"), "text": _s(call.get("text"))[:240]}
    return card


BUILDERS = {"prop_hit_rate": hits_card, "line_shop": prices_card, "our_record": record_card,
            "fantasy_points": startsit_card}


def cards(calls) -> list[dict]:
    """The answer's cards, from its lookups in the order they were made: one
    of each kind, at most MAX_CARDS."""
    out, kinds = [], set()
    for name, _args, result in calls or []:
        build = BUILDERS.get(name)
        card = build(result) if build else None
        if card and card["kind"] not in kinds:
            kinds.add(card["kind"])
            out.append(card)
        if len(out) >= MAX_CARDS:
            break
    return out


# ---- what to ask next ------------------------------------------------------------------------
def follow_ups(question: str, calls, league: str = "") -> list[str]:
    """Up to MAX_FOLLOW next questions, from what this answer looked up and who
    it was about. Never the question just asked."""
    asked = _s(question).lower()
    used = [n for n, _a, _r in calls or []]
    player = next((_s((r or {}).get("player")) for n, _a, r in calls or []
                   if n in ("prop_hit_rate", "player_history") and isinstance(r, dict) and r.get("player")), "")
    if not player:
        player = next((_s((a or {}).get("player")) for _n, a, _r in calls or []
                       if isinstance(a, dict) and a.get("player")), "")
    team = next((_s((a or {}).get("team")) for _n, a, _r in calls or [] if isinstance(a, dict) and a.get("team")), "")
    lg = _s(league).upper()
    out = []
    if player:
        if "line_shop" not in used:
            out.append(f"What’s the best price on {player}?")
        if "injuries" not in used:
            out.append(f"Is {player} on the injury report?")
        if "player_history" not in used:
            out.append(f"How has {player} done lately?")
    elif team:
        out.append(f"How have the {team} done lately?")
        if "injuries" not in used:
            out.append(f"Who is hurt on the {team}?")
    if "fantasy_points" in used:
        out.append("Who should I pick up this week?")
    if "our_record" in used and "our_picks" not in used:
        out.append("What are our best bets tonight?")
    if "our_picks" not in used and "tonight_board" not in used:
        out.append(f"What’s the best bet on tonight’s {lg} board?".replace("tonight’s  board", "tonight’s board"))
    if "our_record" not in used:
        out.append("How has our record been lately?")
    seen, keep = set(), []
    for q in out:
        k = q.lower()
        if k in seen or k.rstrip("?") in asked:
            continue
        seen.add(k)
        keep.append(q)
        if len(keep) >= MAX_FOLLOW:
            break
    return keep
