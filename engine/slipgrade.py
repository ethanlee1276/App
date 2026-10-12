"""Grade a parlay from its screenshot — every leg priced by our own numbers.

Ethan, 2026-10-12: "add a feature in the ai ask Qellys where users can
upload a screenshot of there parlay and it will rank it based on all our
data and tools and models".

TWO HALVES, AND ONLY THE FIRST IS A LANGUAGE MODEL.

READ (`read_slip`). Claude reads the picture once — each leg's sport,
player or team, market (one of OUR market keys), side, line and the leg's
price when the book prints one; the ticket's total price and stake. The
reply is held to a JSON schema (`output_config.format`, or a forced tool
where the SDK or the model will not take it) and every field is checked again here
(`clean_slip`): a leg that does not parse is dropped and counted, never
guessed. The image goes to the API once and is kept nowhere — not on disk,
not in a log; the usage file keeps tokens, as it does for every question.

GRADE (`grade`). No model. Each leg is found on tonight's boards — every
league Ask reads — and priced the way the board prices its own numbers:

  * a leg the Most Likely board seats (same player, market, side and
    number): that row's chance, the one the site shows, every correction
    the board applies already in it;
  * any other player prop at the slip's exact number: `likely._prob_at`,
    the derivation the Most Likely ladder and legcheck.py use, then held
    to the Most Likely list's own record on that side (engine/likelycal:
    pulled toward the price as far as the list's picks have earned, and
    only ever lowered);
  * an anytime scorer: the touchdown model's whole field (`td_field`),
    the long-shot shelves, or hockey's anytime-goal prop;
  * a side or a total: the board's own game card at that number, read
    from either side — a card backs one side, and the other side is its
    complement at the other side's price;
  * anything else: "not on our board" — said, and left out of our side
    of the math (its own price stands in for it).

A slip that prints "J. Allen" finds Josh Allen only when he is the one
Allen in that market (and on the slip's team, when it names one); team
words go through the names Ask already reads ("Bills", "Buffalo"), so
"LA Chargers" is never the Rams.

Then the ticket. Legs in different games multiply; legs in one game are
joined with the correlation the parlay engine already uses
(`parlays.relate` → `joint_two` / `joint_three`), and a pair it would never
build — one player's availability carrying two legs, a leg and its own
opposite — is named. The payout is the slip's printed price when it shows
one, else its legs' prices multiplied. Each leg is ranked by how far our
chance clears what its own price needs; the weakest is named with the
board's likeliest pick in the same game beside it.

NOT ADVICE, NOT THE RECORD. Nothing here is bet, journaled, posted or
kept. The card says our number and what the price needs, and no more.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import random

#: Every market the boards price, by the key the boards use. The reader
#: must pick one of these (or "other"), so a leg can only ever be looked up
#: under a name that exists.
MARKETS = (
    # football (NFL, college)
    "pass_yds", "pass_td", "pass_att", "pass_cmp", "pass_int", "rush_yds", "rush_att",
    "rec_yds", "receptions", "rush_rec_yds", "pass_rush_yds", "anytime_td",
    "kick_pts", "fg_made", "tackles_ast",
    # basketball (NBA, WNBA)
    "pts", "reb", "ast", "pra", "fg3m",
    # baseball
    "hits", "total_bases", "home_runs", "strikeouts", "outs",
    # hockey
    "sog", "points", "goals", "assists", "blocks", "anytime_goal", "saves",
    # game lines
    "moneyline", "spread", "total",
    "other",
)
#: How a leg is said back — in the summary the conversation carries, the
#: weakest leg and the pairs named on the card.
MARKET_WORDS = {
    "pass_yds": "passing yards", "pass_td": "passing TDs", "pass_att": "pass attempts",
    "pass_cmp": "completions", "pass_int": "interceptions", "rush_yds": "rushing yards",
    "rush_att": "carries", "rec_yds": "receiving yards", "receptions": "receptions",
    "rush_rec_yds": "rush + rec yards", "pass_rush_yds": "pass + rush yards", "kick_pts": "kicking points",
    "fg_made": "field goals", "tackles_ast": "tackles + assists", "pts": "points", "reb": "rebounds",
    "ast": "assists", "pra": "pts + reb + ast", "fg3m": "threes", "hits": "hits", "total_bases": "total bases",
    "home_runs": "home runs", "strikeouts": "strikeouts", "outs": "outs", "sog": "shots on goal",
    "points": "points", "goals": "goals", "assists": "assists", "blocks": "blocks", "saves": "saves",
}
GAME_MARKETS = ("moneyline", "spread", "total")
SCORER_MARKETS = ("anytime_td", "anytime_goal")
SPORTS = ("nfl", "cfb", "nba", "wnba", "mlb", "nhl", "other")
SIDES = ("over", "under", "yes", "no", "team")

#: What a slip may carry. More legs than this is not a parlay anyone
#: should be told is graded; the rest are dropped and counted.
MAX_LEGS = 12
#: Image limits. Caddy refuses any request body over 1MB (deploy/Caddyfile,
#: pinned by tests/test_nothing_waits_forever.py), and base64 costs a third
#: again, so the picture itself stays under this. The page re-encodes a
#: screenshot at most 1568px on its long side — the size the API reads
#: images at anyway — as a JPEG, which lands well under it.
MAX_IMAGE_BYTES = 740_000
MEDIA_TYPES = {"image/jpeg": (b"\xff\xd8\xff",), "image/png": (b"\x89PNG\r\n\x1a\n",),
               "image/webp": (b"RIFF",), "image/gif": (b"GIF87a", b"GIF89a")}
MAX_TOKENS = 2000

#: The verdict bands, in points of probability: our chance against what
#: the leg's own price needs to break even.
STRONG_EDGE = 0.05
WEAK_EDGE = -0.02
AGAINST_EDGE = -0.08

SCHEMA = {
    "type": "object",
    "properties": {
        "is_bet_slip": {"type": "boolean"},
        "book": {"type": "string"},
        "total_odds": {"type": "integer"},
        "stake": {"type": "number"},
        "legs": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "sport": {"type": "string", "enum": list(SPORTS)},
                "player": {"type": "string"},
                "team": {"type": "string"},
                "game": {"type": "string"},
                "market": {"type": "string", "enum": list(MARKETS)},
                "side": {"type": "string", "enum": list(SIDES)},
                "line": {"type": "number"},
                "odds": {"type": "integer"},
                "text": {"type": "string"},
            },
            "required": ["sport", "player", "team", "game", "market", "side", "line", "odds", "text"],
            "additionalProperties": False,
        }},
    },
    "required": ["is_bet_slip", "book", "total_odds", "stake", "legs"],
    "additionalProperties": False,
}

SYSTEM = """You read sportsbook bet slips from screenshots. Report only what the picture shows.

For every leg of the ticket give:
- sport: nfl, cfb (college football), nba, wnba, mlb, nhl, or other.
- player: the player's full name as printed, or "" for a game line.
- team: for a moneyline or spread, the team picked; otherwise the player's team if printed, else "".
- game: the matchup as printed, e.g. "BUF @ LA", or "".
- market: one key from the list. Football: pass_yds, pass_td, pass_att, pass_cmp, pass_int, rush_yds,
  rush_att, rec_yds, receptions, rush_rec_yds, pass_rush_yds, anytime_td, kick_pts, fg_made, tackles_ast.
  Basketball: pts, reb, ast, pra (points+rebounds+assists), fg3m (made threes). Baseball: hits,
  total_bases, home_runs, strikeouts (a pitcher's), outs. Hockey: sog (shots on goal), points, goals,
  assists, blocks, anytime_goal, saves. Game lines: moneyline, spread, total. Anything else: other.
- side: over or under for a number; yes for an anytime scorer; team for a moneyline or spread.
- line: the number. "6+ receptions" is over 5.5; "To score" is 0.5; a spread is the picked team's
  number (-3.5); a moneyline is 0.
- odds: the leg's American price if the slip prints one, else 0.
- text: the leg exactly as printed.

total_odds is the whole ticket's American price if printed (+1250), else 0. stake is the wager if
printed, else 0. book is the sportsbook if you can tell, else "". If the picture is not a bet slip,
set is_bet_slip false and return no legs. Never invent a leg, a number or a price."""


class SlipUnreadable(Exception):
    """The picture is not a bet slip, or nothing on it could be read."""


# ---- the picture -----------------------------------------------------------
def decode_image(data: str, media_type: str) -> bytes:
    """The upload's bytes, or ValueError: a type the API takes, real base64,
    under MAX_IMAGE_BYTES, and starting the way its type starts."""
    mt = str(media_type or "").lower().strip()
    if mt not in MEDIA_TYPES:
        raise ValueError("send a JPEG, PNG, WebP or GIF")
    raw_b64 = str(data or "")
    if raw_b64.startswith("data:"):
        raw_b64 = raw_b64.split(",", 1)[-1]
    if len(raw_b64) > MAX_IMAGE_BYTES * 4 // 3 + 8:
        raise ValueError("that picture is too large")
    try:
        raw = base64.b64decode(raw_b64, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("that picture did not arrive whole") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("that picture is too large" if raw else "that picture is empty")
    if not any(raw.startswith(m) for m in MEDIA_TYPES[mt]) or (mt == "image/webp" and raw[8:12] != b"WEBP"):
        raise ValueError("that file is not the picture it says it is")
    return raw


# ---- reading ---------------------------------------------------------------
def _num(v, default=0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _odds(v) -> int:
    """An American price, or 0 for none or nonsense (|odds| under 100)."""
    o = int(_num(v, 0))
    return o if abs(o) >= 100 and abs(o) <= 100000 else 0


def _text(v, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def clean_slip(raw) -> dict:
    """The reader's reply, checked field by field. Returns
    {"is_bet_slip", "book", "total_odds", "stake", "legs", "dropped"}."""
    raw = raw if isinstance(raw, dict) else {}
    legs, dropped = [], 0
    for leg in raw.get("legs") if isinstance(raw.get("legs"), list) else []:
        if not isinstance(leg, dict) or len(legs) >= MAX_LEGS:
            dropped += 1
            continue
        market = str(leg.get("market") or "")
        side = str(leg.get("side") or "")
        sport = str(leg.get("sport") or "other")
        line = _num(leg.get("line"), float("nan"))
        player, team = _text(leg.get("player"), 60), _text(leg.get("team"), 60)
        ok = (market in MARKETS and side in SIDES and sport in SPORTS and math.isfinite(line)
              and abs(line) < 1000 and (player or team or market == "total"))
        if market in GAME_MARKETS:
            ok = ok and not player and (side == "team" if market != "total" else side in ("over", "under"))
        elif market in SCORER_MARKETS:
            ok = ok and bool(player) and side in ("yes", "no")
        elif market != "other":
            ok = ok and bool(player) and side in ("over", "under")
        if not ok:
            dropped += 1
            continue
        legs.append({"sport": sport, "player": player, "team": team, "game": _text(leg.get("game"), 40),
                     "market": market, "side": side, "line": line, "odds": _odds(leg.get("odds")),
                     "text": _text(leg.get("text"), 120)})
    return {"is_bet_slip": bool(raw.get("is_bet_slip")) and bool(legs), "book": _text(raw.get("book"), 40),
            "total_odds": _odds(raw.get("total_odds")), "stake": max(0.0, _num(raw.get("stake"))),
            "legs": legs, "dropped": dropped}


def _reply_json(response) -> dict:
    """The JSON out of a structured reply — a text block (output_config) or
    the forced tool's input (the old-SDK path)."""
    for b in getattr(response, "content", None) or []:
        kind = getattr(b, "type", "")
        if kind == "tool_use" and isinstance(getattr(b, "input", None), dict):
            return b.input
        if kind == "text":
            try:
                got = json.loads(getattr(b, "text", "") or "")
            except ValueError:
                continue
            if isinstance(got, dict):
                return got
    return {}


def read_slip(image: bytes, media_type: str, client=None, model: str | None = None, log=None) -> dict:
    """Read the legs off a bet-slip picture. Raises SlipUnreadable when the
    picture is not a slip or holds nothing readable; explainer.Unavailable
    / NotConfigured as Ask does when the API cannot be reached."""
    from . import askbot as AB
    from . import llmmodels as M
    client = client or AB._client()
    model = model or AB.model_name()
    content = [{"type": "image", "source": {"type": "base64", "media_type": media_type,
                                            "data": base64.standard_b64encode(image).decode("ascii")}},
               {"type": "text", "text": "Read this bet slip."}]
    kw = dict(model=model, max_tokens=MAX_TOKENS, system=SYSTEM,
              messages=[{"role": "user", "content": content}])
    fmt = {"format": {"type": "json_schema", "schema": SCHEMA}}
    if M.takes_effort(model):
        fmt["effort"] = "low"
    try:
        try:
            response = client.messages.create(**kw, output_config=fmt)
        except Exception as first:                                 # noqa: BLE001
            # An SDK too old for output_config (TypeError), or a model the API
            # will not hold to a schema (400): the same schema as a forced tool.
            if not (isinstance(first, TypeError) or type(first).__name__ == "BadRequestError"):
                raise
            response = client.messages.create(
                **kw, tools=[{"name": "slip", "description": "The legs read off the bet slip.",
                              "input_schema": SCHEMA}],
                tool_choice={"type": "tool", "name": "slip"})
    except Exception as exc:                                       # noqa: BLE001
        from . import explainer as EX
        if isinstance(exc, (EX.NotConfigured, EX.Unavailable)):
            raise
        raise EX.Unavailable(f"{type(exc).__name__}") from exc
    (log or AB.log_usage)(model, response)
    if getattr(response, "stop_reason", "") == "refusal":
        raise SlipUnreadable("That picture could not be read as a bet slip.")
    slip = clean_slip(_reply_json(response))
    if not slip["is_bet_slip"]:
        raise SlipUnreadable("That doesn't look like a bet slip — try a screenshot of the ticket itself.")
    return slip


# ---- grading ---------------------------------------------------------------
def implied(odds) -> float | None:
    """What an American price needs to break even."""
    o = _odds(odds)
    if not o:
        return None
    return 100.0 / (o + 100.0) if o > 0 else -o / (-o + 100.0)


def to_decimal(odds) -> float | None:
    o = _odds(odds)
    if not o:
        return None
    return 1.0 + (o / 100.0 if o > 0 else 100.0 / -o)


def _key(name) -> str:
    from .teammates import _norm
    return _norm(name)


def _boards_in_order(boards: dict, sport: str) -> list:
    order = [sport] if sport in boards else []
    return [(s, boards[s]) for s in order + [s for s in boards if s not in order] if isinstance(boards.get(s), dict)]


def _named(rows, leg: dict, ok) -> dict | None:
    """The leg's player among ``rows`` passing ``ok``: his full name first;
    else, for a slip that prints "J. Allen" or "Allen", the one row whose
    surname (and initial, and team when the slip gives one) matches. One
    row, or none — two candidates is a guess, and a guess is not graded."""
    rows = [r for r in rows or [] if isinstance(r, dict) and ok(r)]
    want = _key(leg.get("player"))
    if not want:
        return None
    for r in rows:
        if _key(r.get("player")) == want:
            return r
    words = want.split()
    if len(words) > 1 and len(words[0]) > 1:
        return None                      # a full first name that matched nobody is somebody else
    initial = words[0] if len(words) > 1 else ""
    hits = []
    for r in rows:
        got = _key(r.get("player")).split()
        if len(got) > 1 and got[-1] == words[-1] and got[0].startswith(initial):
            hits.append(r)
    team = str(leg.get("team") or "").upper()
    if len(hits) > 1 and team:
        hits = [r for r in hits if str(r.get("team") or "").upper() == team]
    return hits[0] if len(hits) == 1 else None


def _codes(text, league: str) -> set:
    """The team codes a slip's words name in a league — by name first
    ("Bills", "Buffalo": the words Ask already reads, longest name winning,
    so "LA Chargers" is the Chargers), else a code printed as the board
    writes it ("BUF @ LA")."""
    t = " ".join(str(text or "").split())
    if not t:
        return set()
    try:
        from .askbot import named_teams
        got = set(named_teams(t, league))
    except Exception:                                              # noqa: BLE001
        got = set()
    if got:
        return got
    try:
        from .teamdex import name_map
        names = name_map(league) or {}
    except Exception:                                              # noqa: BLE001
        names = {}
    if league == "nhl":                  # Ask's word list stops short of hockey
        low = f" {t.lower()} "
        for full, code in names.items():
            nick = full.lower().split()[-1] if full else ""
            if f" {full.lower()} " in low or (len(nick) > 3 and f" {nick} " in low):
                got.add(code)
        if got:
            return got
    codes = set(names.values())
    return {w for w in t.replace("@", " ").replace("/", " ").split() if w.isupper() and w in codes}


def _game_pick(board: dict, leg: dict, league: str):
    """(our chance, the board's price for the leg's side, the card, the team
    backed) for a moneyline, spread or total — the board's own game card at
    the slip's number, read from EITHER side: a card backs one side, and the
    other side's chance is its complement at the other side's price."""
    want = _codes(leg["team"], league) if leg["market"] != "total" else set()
    game = _codes(leg["game"], league) | want
    if not game:
        return None
    for r in board.get("game_bets") or []:
        if not isinstance(r, dict) or str(r.get("market") or r.get("bet_type") or "") != leg["market"]:
            continue
        home, away = r.get("home"), r.get("away")
        if not (game & ({home, away} - {None, ""})):
            continue
        p = _num(r.get("win_prob", r.get("hit_prob")), float("nan"))
        if not math.isfinite(p):
            continue
        picked = r.get("team") or r.get("pick") or ""
        if leg["market"] == "total":
            if abs(_num(r.get("line"), 1e9) - leg["line"]) > 0.01:
                continue
            same, backed = str(r.get("side") or "").lower() == leg["side"], ""
        else:
            if not (want & {home, away}):
                continue
            same = picked in want
            backed = picked if same else (away if picked == home else home)
            if leg["market"] == "spread":
                line = _num(r.get("line"), 1e9)
                if abs((line if same else -line) - leg["line"]) > 0.01:
                    continue
        if same:
            price = r.get("odds")
        elif leg["market"] == "moneyline":
            price = r.get("away_odds") if picked == home else r.get("home_odds")
        else:
            price = r.get("other_odds")
        return (p if same else 1.0 - p), price, r, backed
    return None


def _shown(r: dict) -> float:
    """The chance the Most Likely page prints for a seated pick: the tier's
    real hit rate where the board carries one (likelyboard.REAL_RATE_TIERS,
    "Worth a look", once it has the settled picks to say), else our model's
    chance — app.js reads `tier_rate != null ? tier_rate : model_prob`."""
    rate = _num(r.get("tier_rate"), None)
    return rate if rate is not None else _num(r.get("model_prob"), float("nan"))


def _likely_row(board: dict, leg: dict) -> dict | None:
    """The Most Likely board's own row for exactly this leg — same player,
    market, side and number — whose chance is the one the site shows, with
    every correction the board applies already in it."""
    rows = list((board.get("likely_board") or {}).get("rows") or []) + list(board.get("most_likely") or [])

    def ok(r):
        if r.get("market") != leg["market"] or r.get("model_prob") is None:
            return False
        if leg["market"] in SCORER_MARKETS:
            return leg["side"] == "yes"
        return (str(r.get("side") or "").lower() == leg["side"]
                and abs(_num(r.get("line"), 1e9) - leg["line"]) < 0.01)
    return _named(rows, leg, ok)


def _scorer(board: dict, leg: dict):
    """(our chance he scores, his scorer price, the row): the touchdown
    model's whole field first, then the long-shot shelves, then a scorer
    prop on the main board (hockey's anytime goal is priced there)."""
    for key in ("td_field", "longshot_watch", "long_shots"):
        r = _named(board.get(key), leg, lambda r: r.get("model_prob") is not None
                   and (r.get("market") or leg["market"]) == leg["market"])
        if r is not None:
            return _num(r.get("model_prob"), float("nan")), r.get("odds"), r
    r = _named(board.get("recommendations"), leg, lambda r: r.get("market") == leg["market"])
    if r is not None:
        from . import likely
        p = likely._prob_at(r, leg["market"], "over", 0.5)
        return (float("nan") if p is None else p), (r.get("odds") if str(r.get("side") or "").lower() == "over" else None), r
    return None


def _honest(league: str, p: float, side: str, odds) -> float:
    """A chance the Most Likely list did not seat, held to that list's own
    record (engine/likelycal): pulled toward the price by as much as the
    list's picks on this side have earned in the journal, and only ever
    lowered. No fitted record, or no price: the number stands."""
    try:
        from . import likelycal as LC
        groups = ((LC.load().get(league) or {}).get("groups") or {})
        g = LC.k_for(groups, f"list|{LC.side_of(side)}")
        q = LC.price_chance(odds)
        if not g or q is None or float(g["k"]) >= 1.0:
            return p
        return round(LC.shrink(p, q, float(g["k"])), 4)
    except Exception:                                              # noqa: BLE001
        return p


def price_leg(boards: dict, leg: dict) -> dict:
    """One leg against tonight's boards: our chance, what its price needs,
    the verdict, and where on the board it was found."""
    from . import likely
    out = dict(leg)
    out.update(prob=None, needs=implied(leg["odds"]), league="", found="", row=None)
    for league, board in _boards_in_order(boards, leg["sport"]):
        got = None
        if leg["market"] in GAME_MARKETS:
            g = _game_pick(board, leg, league)
            if g is not None:
                got = (g[0], g[1], "game", g[2])
                out["team"] = g[3] or out["team"]
        elif leg["market"] != "other":
            r = _likely_row(board, leg)
            if r is not None:
                got = (_shown(r), r.get("odds"), "likely", r)
            elif leg["market"] in SCORER_MARKETS:
                s = _scorer(board, leg)
                if s is not None:
                    yes = leg["side"] == "yes"
                    got = (s[0] if yes else 1.0 - s[0], s[1] if yes else None, "scorer", s[2])
            else:
                r = _named(board.get("recommendations"), leg, lambda r: r.get("market") == leg["market"])
                if r is not None:
                    p = likely._prob_at(r, leg["market"], leg["side"], leg["line"])
                    main = (abs(_num(r.get("line"), 1e9) - leg["line"]) < 0.01
                            and str(r.get("side") or "").lower() == leg["side"])
                    price = r.get("odds") if main else None
                    if p is not None:
                        p = _honest(league, p, leg["side"], leg["odds"] or price)
                    got = (float("nan") if p is None else p, price, "prop", r)
        if got is not None:
            prob, price, found, row = got
            out.update(prob=prob if math.isfinite(prob) else None, league=league, found=found, row=row,
                       needs=out["needs"] or implied(price))
            break
    r = out["row"] or {}
    if r.get("player") and out["market"] not in GAME_MARKETS:
        out["player"] = r["player"]      # the board's spelling: "J. Allen" was Josh Allen
    out["projection"] = r.get("projection")
    # The board's word for the seat ("Top pick"), not its key ("top").
    out["tier"] = str(r.get("tier_label") or r.get("tier") or "") if out["found"] == "likely" else ""
    out["game"] = _game_label(r, boards.get(out["league"])) or out["game"]
    out["team"] = out["team"] if out["market"] in GAME_MARKETS else (str(r.get("team") or "") or out["team"])
    out["opponent"] = str(r.get("opponent") or "")
    out["edge"] = (out["prob"] - out["needs"]) if (out["prob"] is not None and out["needs"] is not None) else None
    out["verdict"] = verdict(out["prob"], out["edge"])
    return out


def _game_label(r: dict, board: dict | None = None) -> str:
    """"AWAY @ HOME" — off the row, else off the board's own schedule."""
    if not r:
        return ""
    if r.get("away") and r.get("home"):
        return f"{r['away']} @ {r['home']}"
    g = r.get("game")
    if isinstance(g, dict) and g.get("away") and g.get("home"):
        return f"{g['away']} @ {g['home']}"
    teams = {r.get("team"), r.get("opponent")} - {None, ""}
    for g in (board or {}).get("games") or []:
        if isinstance(g, dict) and teams and teams <= {g.get("home"), g.get("away")}:
            return f"{g['away']} @ {g['home']}"
    if r.get("team") and r.get("opponent"):
        return f"{r['team']} vs {r['opponent']}"
    return ""


def verdict(prob, edge) -> str:
    """strong / fair / weak / against / unpriced."""
    if prob is None:
        return "unpriced"
    if edge is None:
        return "strong" if prob >= 0.62 else "fair" if prob >= 0.52 else "weak" if prob >= 0.42 else "against"
    if edge >= STRONG_EDGE and prob >= 0.5:
        return "strong"
    if edge >= WEAK_EDGE:
        return "fair"
    if edge >= AGAINST_EDGE:
        return "weak"
    return "against"


def _relation_leg(leg: dict) -> dict:
    """A priced leg in the shape parlays.relate reads."""
    r = leg.get("row") or {}
    g = r.get("game") if isinstance(r.get("game"), dict) else {}
    return {"player": leg.get("player") or "", "team": leg.get("team") or r.get("team") or "",
            "opponent": leg.get("opponent") or r.get("opponent") or "",
            "market": leg["market"], "side": leg["side"].upper() if leg["side"] in ("over", "under") else leg["side"],
            "line": leg["line"], "home": r.get("home") or g.get("home") or "",
            "away": r.get("away") or g.get("away") or "", "game_date": ""}


def _game_of(leg: dict) -> tuple:
    from .parlays import game_key
    return game_key(_relation_leg(leg))


def joint(legs: list[dict]) -> tuple[float | None, list[dict]]:
    """(our chance every priced leg wins, the pairs worth naming). Legs in
    different games multiply; legs in one game take the parlay engine's
    correlation (relate → joint_two / joint_three; four or more share the
    group's average). Unpriced legs are left out of this number."""
    from . import parlays as P
    priced = [l for l in legs if l.get("prob") is not None]
    if not priced:
        return None, []
    groups: dict = {}
    for l in priced:
        k = _game_of(l)
        groups.setdefault(k if any(k[0]) else ("solo", id(l)), []).append(l)
    total, notes, impossible = 1.0, [], False
    for group in groups.values():
        ps = [max(1e-6, min(1 - 1e-6, float(l["prob"]))) for l in group]
        rhos = []
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                try:
                    rel = P.relate(group[i]["league"] or "nfl", _relation_leg(group[i]), _relation_leg(group[j]))
                except Exception:                                  # noqa: BLE001
                    rel = None
                rho = float(getattr(rel, "rho", 0.0) or 0.0)
                rhos.append(rho)
                if rel is not None and getattr(rel, "verdict", "ok") in ("kill", "duplicate"):
                    notes.append({"legs": [_name(group[i]), _name(group[j])], "kind": rel.verdict,
                                  "why": getattr(rel, "mechanism", "")})
                impossible = impossible or _exclusive(rel)
        if len(group) == 1:
            total *= ps[0]
        elif len(group) == 2:
            total *= P.joint_two(ps[0], ps[1], rhos[0])
        elif len(group) == 3:
            total *= P.joint_three(tuple(ps), (rhos[0], rhos[1], rhos[2]))
        else:
            total *= joint_k(ps, sum(rhos) / len(rhos))
    # BOTH SIDES OF ONE LINE CANNOT BOTH WIN. The engine scores the pair at
    # -0.90 (a side) or -1.0 (a total) and names it a kill; a copula at
    # -0.90 still leaves a few points of "both", which no game can.
    return (0.0 if impossible else max(0.0, min(1.0, total))), notes


def _exclusive(rel) -> bool:
    """A pair the parlay engine says cannot both win — both sides of one
    side or one total (parlays.relate, §3 Type 1 "cannot both win"); a
    team-total-against-its-own-player clash is a logic problem, not this."""
    return bool(rel is not None and "cannot both win" in str(getattr(rel, "mechanism", "")))


def joint_k(ps: list[float], rho: float) -> float:
    """P(all k legs win) under a one-factor Gaussian copula with every
    pair at ``rho`` — joint_three's integral for any number of legs, the
    loading sqrt(rho) on each. A negative average is treated as none: one
    shared factor cannot pull every pair apart at once."""
    from . import parlays as P
    lam = math.sqrt(max(0.0, min(0.9, rho)))
    res = math.sqrt(max(1e-9, 1.0 - lam * lam))
    zs = [P._phi_inv(1 - p) for p in ps]
    acc = 0.0
    for x, w in zip(P._GL64_X, P._GL64_W):
        z = 8.0 * x
        term = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        for zi in zs:
            term *= 1.0 - P._phi((zi - lam * z) / res)
        acc += w * term
    return max(0.0, min(1.0, 8.0 * acc))


# ---- the facts behind each leg ---------------------------------------------
#: At most this many facts a leg, in the order a case is made. They sit
#: folded under the leg, so a full case costs a tap, not the card's length.
MAX_WHY = 16
#: A projection step worth naming moves the number at least this much.
STEP_SHOWN = 0.03
#: The warnings worth a reader's time on a parlay leg — not the Edge
#: board's grade notes ("Below confidence threshold", "Edge too small").
FLAG_WORDS = ("carried from", "questionable", "doubtful", "out", "quarterback", " qb", "teammate",
              "injur", "pulled", "returns", "back from", "limited")


def _fmt(x) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return ""
    return f"{f:.1f}".rstrip("0").rstrip(".")


def _context_row(board: dict, leg: dict) -> dict:
    """The board's full row for the leg's player and market — the one the
    projection, the defence card and the chain live on — whichever shelf
    priced the leg (a Most Likely row carries the chance, not the why)."""
    found = _named(board.get("recommendations"), leg, lambda r: r.get("market") == leg["market"])
    return found or (leg.get("row") or {})


def _scan_read(board: dict, player: str) -> dict | None:
    """The game scan's read on him: a label ("Good matchup") and the facts
    for and against, in the scan's own words."""
    want = _key(player)
    for game in (board.get("scan_reads") or {}).values():
        for r in (game or {}).get("players") or []:
            if isinstance(r, dict) and _key(r.get("player")) == want:
                return r
    return None


def _game_plan(board: dict, home, away) -> dict | None:
    for g in board.get("game_plans") or []:
        if isinstance(g, dict) and g.get("home") == home and g.get("away") == away:
            return g
    return None


def _steps(row: dict) -> list:
    return [s for s in ((row.get("chain") or {}).get("steps") or []) if isinstance(s, dict)]


def _step_mult(row: dict, key: str):
    for s in _steps(row):
        if s.get("key") == key:
            return _num(s.get("mult"), None)
    return None


def _board_game(board: dict, home, away) -> dict:
    """The board's own game — where the crowd's prices, the opening line
    and the exchange money hang."""
    for g in board.get("games") or []:
        if isinstance(g, dict) and home and g.get("home") == home and g.get("away") == away:
            return g
    return {}


def _venues(c: dict, keys) -> tuple[list[str], float | None]:
    """(the venues quoting it, their average) off a game's crowd block."""
    got = [(name, _num(c.get(k), None)) for name, k in keys]
    got = [(name, v) for name, v in got if v is not None]
    return [n for n, _ in got], (sum(v for _, v in got) / len(got) if got else None)


def _game_facts(board: dict, leg: dict, row: dict) -> list[tuple[str, str]]:
    """What the site knows about a side or a total beyond our model's own
    reasons, all of it already on the board: the books' number with the
    margin out, Kalshi and Polymarket on the same bet at the same number,
    the move since the line opened and where the exchange money sits."""
    out: list[tuple[str, str]] = []
    market, home, away = leg["market"], row.get("home"), row.get("away")
    team = leg.get("team") or ""
    is_home = team == home
    if market == "total":
        same = str(row.get("side") or "").lower() == leg["side"]
        what = f"the {leg['side']} {_fmt(leg['line'])}"
    else:
        same = (row.get("team") or row.get("pick") or "") == team
        what = team + (f" {leg['line']:+g}" if market == "spread" else "")
    fair = _num(row.get("fair_prob"), None)
    if fair is not None and row.get("has_market", True):
        out.append(("The books", f"Their own price, the margin taken out, says {(fair if same else 1 - fair):.0%}"))
    g = _board_game(board, home, away)
    c = g.get("crowd") or {}
    if market == "moneyline":
        names, p = _venues(c, (("Kalshi", "kalshi"), ("Polymarket", "polymarket")))
        mine = None if p is None else (p if is_home else 1 - p)
    elif market == "spread":
        names, p = _venues(c, (("Kalshi", "kalshi_home_cover"), ("Polymarket", "poly_home_cover")))
        at = leg["line"] if is_home else -leg["line"]
        mine = (None if p is None or abs(_num(c.get("spread_home_line"), 1e9) - at) > 0.01
                else (p if is_home else 1 - p))
    else:
        names, p = _venues(c, (("Kalshi", "kalshi_over"), ("Polymarket", "poly_over")))
        mine = (None if p is None or abs(_num(c.get("total_line"), 1e9) - leg["line"]) > 0.01
                else (p if leg["side"] == "over" else 1 - p))
    if mine is not None:
        out.append(("Prediction markets", f"{' and '.join(names)} traders put {what} at {mine:.0%}"
                    + (" to win" if market == "moneyline" else "")))
    lo = g.get("line_open") or {}
    if market == "spread" and lo.get("spread_home") is not None and lo.get("spread_move") is not None:
        o = float(lo["spread_home"])
        now = o + float(lo["spread_move"])
        o, now = (o, now) if is_home else (-o, -now)
        out.append(("Line move", f"{team} opened {o:+g}, now {now:+g}" if abs(now - o) >= 0.01
                    else f"{team} {now:+g}, where it opened"))
    elif market == "total" and lo.get("total") is not None and lo.get("total_move") is not None:
        o = float(lo["total"])
        now = o + float(lo["total_move"])
        out.append(("Line move", f"Opened {_fmt(o)}, now {_fmt(now)}" if abs(now - o) >= 0.01
                    else f"{_fmt(now)}, where it opened"))
    elif market == "moneyline":
        o, now = _odds(lo.get("home_ml" if is_home else "away_ml")), _odds(g.get("home_ml" if is_home else "away_ml"))
        if o and now:
            out.append(("Line move", f"{team} opened {o:+d}, now {now:+d}" if o != now
                        else f"{team} {now:+d}, where it opened"))
    am = lo.get("against_money") or {}
    if out and out[-1][0] == "Line move" and am.get("toward") in ("home", "away") and market == "spread":
        club = lambda w: home if w == "home" else away                   # noqa: E731
        k, t = out.pop()
        out.append((k, f"{t} — toward {club(am['toward'])} with {_num(am.get('money_share')):.0%} "
                       f"of the money on {club(am.get('money_on'))}"))
    m = g.get("money") or {}
    split = m.get({"moneyline": "ml", "spread": "spread", "total": "total"}[market]) or {}
    if split:
        if market == "total":
            ok, share = abs(_num(split.get("line"), 1e9) - leg["line"]) < 0.01, split.get(leg["side"])
        else:
            ok = market == "moneyline" or abs(_num(split.get("line"), 1e9)
                                              - (leg["line"] if is_home else -leg["line"])) < 0.01
            share = split.get("home" if is_home else "away")
        if ok and share is not None:
            where = " and ".join(m.get("venues") or []) or "the exchanges"
            usd = f"${_num(split.get('usd')):,.0f} " if split.get("usd") else ""
            out.append(("Money", f"{_num(share):.0%} of the {usd}traded on {where} is on {what}"))
    return out


def _books_fact(ctx: dict, leg: dict) -> str:
    """The market's own number for this exact bet, margin out: the sharp
    book's when it quoted the number, the field's median across books at
    the number, else the one book's. Only at the row's own line."""
    if abs(_num(ctx.get("line"), 1e9) - leg["line"]) >= 0.01 or not ctx.get("has_market"):
        return ""
    same = str(ctx.get("side") or "").lower() == leg["side"]
    parts = []
    sharp = _num(ctx.get("sharp_fair"), None) if ctx.get("sharp_anchored") else None
    if sharp is not None:
        parts.append(f"the sharp book's price, the margin taken out, says {(sharp if same else 1 - sharp):.0%}")
    field = _num(ctx.get("fair_consensus"), None)
    if field is not None and int(_num(ctx.get("consensus_books"), 0)) >= 2:
        over = field if leg["side"] == "over" else 1 - field             # the field's number is the over's
        parts.append(f"{int(ctx['consensus_books'])} books at this number together say {over:.0%}")
    fair = _num(ctx.get("fair_prob"), None)
    if not parts and fair is not None:
        return f"Their own price, the margin taken out, says {(fair if same else 1 - fair):.0%}"
    return "; ".join(parts)[:1].upper() + "; ".join(parts)[1:] if parts else ""


def _seat_facts(board: dict, leg: dict) -> list[tuple[str, str]]:
    """What the one Most Likely board wrote on this pick: the case it was
    picked on, our record on picks like it, the scout's notes. The record
    and the checks are this exact pick's (same number, same side); the
    scout's notes are about the side, so any of his lines carries them."""
    out: list[tuple[str, str]] = []
    seat = leg.get("row") if leg.get("found") == "likely" else None
    side_row = seat or _named((board.get("likely_board") or {}).get("rows"), leg,
                              lambda r: r.get("market") == leg["market"]
                              and str(r.get("side") or "").lower() in (leg["side"], ""))
    if seat:
        for t in (seat.get("case_lines") or [])[:2]:
            out.append(("The case", t))
        notes = seat.get("check_notes") or {}
        checks = seat.get("checks") or {}
        if seat.get("tier_rate") is not None and seat.get("tier_n"):
            out.append(("Our record", f"Our {seat.get('tier_label') or 'board'} tier has hit "
                                      f"{_num(seat['tier_rate']):.0%} of {int(seat['tier_n'])} settled"))
        elif notes.get("record"):
            t = str(notes["record"])
            out.append(("Our record", t[:1].upper() + t[1:]))
        passed = [k for k in ("model", "matchup", "market", "record") if checks.get(k) is True]
        if checks:
            out.append(("Checks", f"Passes {len(passed)} of our 4 checks"
                        + (f" ({', '.join(passed)})" if passed else "")
                        + (f"; market: {notes['market']}" if checks.get("market") is not True and notes.get("market") else "")))
    if side_row:
        for t in (side_row.get("scout_notes") or [])[:2]:
            out.append(("Scout", t))
        for k, label in (("milestone_note", "Milestone"), ("incentive_note", "Incentive")):
            if side_row.get(k):
                out.append((label, side_row[k]))
    return out


def why(boards: dict, leg: dict) -> list[dict]:
    """The facts behind one leg's number, in the board's own words: what we
    project and the likely range, how often he has cleared this number and
    what he did against this defence, the defence card, the steps that
    moved his projection most, the game around him, the scan's matchup
    read, who is out around him, anything the card warns about, the case
    the Most Likely board made, our record on picks like it, the scout's
    notes and what the books' own prices say. For a side or a total: our
    model's reasons, the books, Kalshi and Polymarket, the line's move,
    the exchange money and the game plan. Nothing here is computed for the
    slip; every fact is already on the row or the board."""
    out: list[dict] = []
    seen: set = set()

    def add(k, t):
        t = " ".join(str(t or "").split())
        if t and t not in seen:
            seen.add(t)
            out.append({"k": k, "t": t[:260]})

    if leg.get("prob") is None:
        return out
    board = boards.get(leg.get("league") or "") or {}
    row = leg.get("row") or {}
    market = leg["market"]
    if market in GAME_MARKETS:
        for line in (row.get("reasons") or [])[:2]:
            add("Our model", line)
        for k, t in _game_facts(board, leg, row):
            add(k, t)
        script = ((_game_plan(board, row.get("home"), row.get("away")) or {}).get("script") or {})
        if script.get("read"):
            add("Game script", (f"{script['archetype']}. " if script.get("archetype") else "") + script["read"])
        return _keep(out)
    ctx = _context_row(board, leg)
    line = leg["line"]
    over = leg["side"] in ("over", "yes")
    if market in SCORER_MARKETS:
        if ctx.get("implied_total") is not None:
            add("Game", f"{ctx.get('team') or 'His team'} expected to score {_fmt(ctx['implied_total'])}")
        if ctx.get("rz_chances") is not None:
            add("Red zone", f"{_fmt(ctx['rz_chances'])} red-zone chances expected this week")
        if ctx.get("goal_line_text"):
            add("Goal line", ctx["goal_line_text"])
    else:
        if ctx.get("projection") is not None:
            lo, hi = ctx.get("proj_low"), ctx.get("proj_high")
            span = (f" (likely range {_fmt(max(0.0, _num(lo)))}–{_fmt(hi)})"
                    if lo is not None and hi is not None else "")
            add("Projection", f"We project {_fmt(ctx['projection'])}{span} against {_fmt(line)}")
        vals = [float(v) for v in (ctx.get("recent_values") or []) if isinstance(v, (int, float))][:10]
        if vals:
            hit = sum(1 for v in vals if (v > line if over else v < line))
            shown = ", ".join(_fmt(v) for v in vals[:6]) + ("…" if len(vals) > 6 else "")
            add("Recent games", f"{'Cleared' if over else 'Stayed under'} {_fmt(line)} in {hit} of his "
                                f"last {len(vals)} ({shown}, latest first)")
        opp = str(ctx.get("opponent") or leg.get("opponent") or "")
        met = [float(g["value"]) for g in (ctx.get("logs") or [])
               if isinstance(g, dict) and opp and g.get("opponent") == opp
               and isinstance(g.get("value"), (int, float))][:5]
        if met:
            hit = sum(1 for v in met if (v > line if over else v < line))
            add(f"Against {opp}", f"{', '.join(_fmt(v) for v in met)} in his log against them "
                                  f"({'cleared' if over else 'stayed under'} {_fmt(line)} in {hit} of {len(met)})")
    card = ctx.get("matchup_card") or {}
    if card.get("text"):
        mult = _step_mult(ctx, "matchup")
        tail = f" — our number ×{mult:.2f} for it" if mult and abs(mult - 1.0) >= 0.01 else ""
        add("Defense", card["text"] + tail)
    seat = _seat_facts(board, leg)
    for k, t in seat:
        if k == "The case":
            add(k, t)
    big = sorted((s for s in _steps(ctx) if s.get("key") != "matchup"
                  and abs((_num(s.get("mult"), 1.0)) - 1.0) >= STEP_SHOWN),
                 key=lambda s: -abs(_num(s.get("mult"), 1.0) - 1.0))
    for s in big[:2]:
        add(str(s.get("label") or s.get("key") or "Model"),
            f"×{_num(s.get('mult'), 1.0):.2f}" + (f" — {s['why']}" if s.get("why") else ""))
    gs = ctx.get("game_script") or {}
    if gs.get("line") or gs.get("lean"):
        add("Game script", " — ".join(x for x in (gs.get("line"), gs.get("lean")) if x))
    read = _scan_read(board, leg["player"])
    if read:
        pro = [str(x) for x in (read.get("pro") or [])][:2]
        con = [str(x) for x in (read.get("con") or [])][:1]
        bits = [b for b in (read.get("label") or "", "; ".join(pro), f"against: {con[0]}" if con else "") if b]
        if len(bits) > 1 or pro or con:
            add("Matchup read", " · ".join(bits))
    for c in (ctx.get("qb_card"), ctx.get("mate_card")):
        if isinstance(c, dict) and c.get("headline"):
            add("Around him", c["headline"])
    ripples = sorted((r for r in ctx.get("ripples") or [] if isinstance(r, dict) and r.get("measured") and r.get("text")),
                     key=lambda r: -abs(_num(r.get("delta"), 0.0)))
    for r in ripples[:1]:
        add("Lineup", r["text"])
    if ctx.get("injury_status"):
        add("Status", f"Listed {ctx['injury_status']}")
    for w in ctx.get("warnings") or []:
        if any(word in str(w).lower() for word in FLAG_WORDS):
            add("Watch", w)
    for k, t in seat:
        if k != "The case":
            add(k, t)
    if market not in SCORER_MARKETS:
        add("The books", _books_fact(ctx, leg))
    return _keep(out)


#: Which facts give way first when a leg has more than MAX_WHY: the number
#: and the market's own price stay longest, colour goes first.
WHY_RANK = {"Projection": 0, "Game": 0, "Red zone": 0, "Our model": 0, "The books": 1, "Defense": 1,
            "Recent games": 1, "Our record": 1, "Goal line": 1, "Prediction markets": 1, "Status": 2,
            "Game script": 2, "Matchup read": 2, "Around him": 2, "Line move": 2, "Money": 2,
            "The case": 3, "Checks": 3, "Lineup": 3, "Watch": 3, "Scout": 4, "Milestone": 4,
            "Incentive": 4}


def _keep(facts: list[dict]) -> list[dict]:
    """At most MAX_WHY facts, in the order the case reads; past that the
    lowest-ranked go first, the latest of them before the earliest."""
    if len(facts) <= MAX_WHY:
        return facts
    rank = lambda f: WHY_RANK.get(f["k"], 2 if f["k"].startswith("Against ") else 3)   # noqa: E731
    order = sorted(range(len(facts)), key=lambda i: (rank(facts[i]), i))[:MAX_WHY]
    return [facts[i] for i in sorted(order)]


# ---- the ticket, replayed --------------------------------------------------
#: Nights the ticket is replayed: the Sim lab's 2,000 (web/js/app.js
#: runSim), each leg drawn from the chance its own curve gives it.
SIM_NIGHTS = 2000


def _loadings(group: list[dict]) -> list[float]:
    """Each leg's loading on its game's one shared factor — the parlay
    engine's own dependence structure, so the replay counts what
    `joint` integrates: a pair at its exact correlation (either sign), a
    trio by `parlays._factor_loadings` (scaled down so no pair is
    overstated), four or more at their average, as `joint_k`."""
    from . import parlays as P
    n = len(group)
    if n < 2:
        return [0.0] * n
    rhos, apart = [], False
    for i in range(n):
        for j in range(i + 1, n):
            try:
                rel = P.relate(group[i].get("league") or "nfl", _relation_leg(group[i]), _relation_leg(group[j]))
                rhos.append(float(getattr(rel, "rho", 0.0) or 0.0))
                apart = apart or _exclusive(rel)
            except Exception:                                      # noqa: BLE001
                rhos.append(0.0)
    if n == 2:
        r = -1.0 if apart else max(-0.999, min(0.999, rhos[0]))   # exactly opposite: never both
        s = math.sqrt(abs(r))
        return [s, s if r >= 0 else -s]
    if n == 3:
        return list(P._factor_loadings((rhos[0], rhos[1], rhos[2])))
    lam = math.sqrt(max(0.0, min(0.9, sum(rhos) / len(rhos))))
    return [lam] * n


def simulate(legs: list[dict], nights: int = SIM_NIGHTS, seed: int | None = None) -> dict | None:
    """The whole ticket played ``nights`` times. Each leg wins on a night
    with its own chance (ours, or its price's break-even where we have no
    number), and legs in one game win and lose together through the parlay
    engine's own structure — one shared factor per game, the engine's
    loadings (`_loadings`) — so the count lands on the ticket's chance give
    or take the noise of 2,000 draws. Returns how many nights the ticket
    cashed, how many legs landed each night, how often it missed by one
    and which leg was that one most often. None when a leg has neither our
    number nor a price, since there is nothing to draw it from."""
    from . import parlays as P
    entries = []
    for l in legs:
        p = l.get("prob") if l.get("prob") is not None else l.get("needs")
        if p is None:
            return None
        entries.append((l, max(1e-4, min(1 - 1e-4, float(p)))))
    n = len(entries)
    if not n:
        return None
    # Games, as `joint` groups them; a stand-in carries no opinion of ours
    # and plays alone, as it does there.
    groups: dict = {}
    for i, (l, _) in enumerate(entries):
        k = _game_of(l) if l.get("prob") is not None else None
        groups.setdefault(k if k and any(k[0]) else ("solo", i), []).append(i)
    lam = [0.0] * n
    game_of = [0] * n
    for gi, idx in enumerate(groups.values()):
        for i, v in zip(idx, _loadings([entries[i][0] for i in idx])):
            lam[i] = v
        for i in idx:
            game_of[i] = gi
    rest = [math.sqrt(max(0.0, 1.0 - v * v)) for v in lam]
    if seed is None:
        key = "|".join(sorted(f"{_name(l)}@{l.get('odds')}" for l, _ in entries))
        seed = int(hashlib.sha256(key.encode()).hexdigest()[:12], 16)
    rng = random.Random(seed)
    cut = [P._phi_inv(1.0 - p) for _, p in entries]          # a leg wins above its cut
    dist = [0] * (n + 1)
    alone = [0] * n
    hits = [0] * n
    for _ in range(nights):
        shared = [rng.gauss(0.0, 1.0) for _ in groups]
        won = [lam[i] * shared[game_of[i]] + rest[i] * rng.gauss(0.0, 1.0) > cut[i] for i in range(n)]
        k = sum(won)
        dist[k] += 1
        for i in range(n):
            hits[i] += won[i]
        if k == n - 1:
            alone[won.index(False)] += 1
    short = dist[n - 1] if n > 1 else 0
    worst = max(range(n), key=lambda i: alone[i]) if short else None
    return {"nights": nights, "cashed": dist[n], "rate": round(dist[n] / nights, 4),
            "legs_hit": dist, "one_short": round(short / nights, 4),
            "breaker": None if worst is None else {"leg": _name(entries[worst][0]),
                                                  "share": round(alone[worst] / short, 3)},
            "hits": hits}


def _name(leg: dict) -> str:
    if leg["market"] in GAME_MARKETS:
        who = leg.get("team") or leg.get("game") or "game"
        return f"{who} {leg['market']}" + (f" {leg['line']:+g}" if leg["market"] == "spread" else
                                           f" {leg['side']} {leg['line']:g}" if leg["market"] == "total" else "")
    if leg["market"] in SCORER_MARKETS:
        return f"{leg['player']} to score"
    return f"{leg['player']} {leg['side']} {leg['line']:g} {MARKET_WORDS.get(leg['market'], leg['market'])}"


def letter(ev: float | None) -> str:
    """A ticket's grade from its expected return per dollar, by our numbers."""
    if ev is None:
        return "?"
    return "A" if ev >= 0.10 else "B" if ev >= 0.0 else "C" if ev >= -0.15 else "D" if ev >= -0.30 else "F"


def _swap(boards: dict, weak: dict, legs: list | None = None) -> dict | None:
    """The board's likeliest seated pick in the weakest leg's game — not a
    bet already on the ticket."""
    board = boards.get(weak.get("league") or "") or {}
    rows = (board.get("likely_board") or {}).get("rows") or []
    teams = {weak.get("team"), weak.get("opponent")} - {"", None}
    r0 = weak.get("row") or {}
    teams |= {r0.get("home"), r0.get("away")} - {"", None}
    taken = {(_key(l.get("player")), l.get("market")) for l in (legs or [weak])}
    best = None
    for r in rows:
        if not isinstance(r, dict) or not teams & {r.get("team"), r.get("opponent")}:
            continue
        if (_key(r.get("player")), r.get("market")) in taken:
            continue
        p = _shown(r) if r.get("model_prob") is not None or r.get("tier_rate") is not None else None
        if p is not None and math.isfinite(p) and (best is None or p > best[0]):
            best = (p, r)
    if not best:
        return None
    r = best[1]
    return {"player": r.get("player") or "", "market": r.get("market") or "", "side": r.get("side") or "",
            "line": r.get("line"), "odds": r.get("odds"), "prob": round(best[0], 4),
            "tier": r.get("tier_label") or r.get("tier") or ""}


# ---- the ticket, now -------------------------------------------------------
def from_decimal(dec: float) -> int:
    """A decimal price as American."""
    if not dec or dec <= 1.0:
        return 0
    return int(round((dec - 1.0) * 100.0)) if dec >= 2.0 else int(round(-100.0 / (dec - 1.0)))


def _same_game(legs: list[dict]) -> bool:
    keys = [_game_of(l) for l in legs if l.get("prob") is not None]
    keys = [k for k in keys if any(k[0])]
    return len(keys) != len(set(keys))


def standing(legs: list[dict]) -> dict | None:
    """Where the ticket stands once its games are on (engine/sliplive):
    legs won, lost and pushed off the box score, legs in play, and our
    chance for what is left — the legs still to play at our pre-game
    numbers, a moneyline in play at the live win probability. A prop in
    play gets no number (our projection assumes a whole game), so a ticket
    with one says where each stands instead of guessing. None before any
    game starts."""
    res = [((l.get("live") or {}).get("result"), l) for l in legs]
    won = [l for r, l in res if r == "won"]
    lost = [l for r, l in res if r == "lost"]
    push = [l for r, l in res if r == "push"]
    in_play = [l for r, l in res if r is None and (l.get("live") or {}).get("state") == "live"]
    if not (won or lost or push or in_play):
        return None
    out = {"won": len(won), "lost": len(lost), "push": len(push), "live": len(in_play)}
    if lost:
        return dict(out, status="lost", left=0, start=0, chance=0.0, lost_leg=_name(lost[0]))
    rest = [l for r, l in res if r not in ("won", "push")]
    if not rest:
        return dict(out, status="won", left=0, start=0, chance=1.0)
    chance = None
    if all(l["market"] == "moneyline" and (l.get("live") or {}).get("win_prob") is not None for l in in_play):
        before = [l for l in rest if l not in in_play]
        pre = _ticket_chance(before) if before else 1.0
        if pre is not None:
            chance = pre * math.prod(float(l["live"]["win_prob"]) for l in in_play)
    return dict(out, status="open", left=len(rest), start=len(rest) - len(in_play),
                chance=None if chance is None else round(chance, 4))


def shop(legs: list[dict], total_odds=None) -> dict | None:
    """The ticket priced at each book quoting every leg at its number: the
    product of that book's prices, best first, against the slip's own.
    Books price a same-game parlay their own way, so for one the product
    is the straight parlay and says so."""
    if len(legs) < 2:
        return None
    per = []
    for l in legs:
        bk = {b["book"]: b["odds"] for b in ((l.get("price") or {}).get("books") or [])
              if isinstance(b, dict) and b.get("book") and _odds(b.get("odds"))}
        if not bk:
            return None
        per.append(bk)
    common = set.intersection(*(set(b) for b in per))
    if not common:
        return None
    rows = sorted(({"book": book, "odds": from_decimal(math.prod(to_decimal(b[book]) for b in per))}
                   for book in common), key=lambda r: (-(to_decimal(r["odds"]) or 0), r["book"]))
    yours = _odds(total_odds)
    best = rows[0]["odds"]
    return {"books": rows[:4], "same_game": _same_game(legs), "yours": yours,
            "beats_yours": bool(yours and (to_decimal(best) or 0) > (to_decimal(yours) or 0) + 1e-9)}


#: Dropping a leg is named only when it lifts the expected return this much.
DROP_GAIN = 0.03


def without(legs: list[dict], payout, ev) -> dict | None:
    """The leg this ticket is better off without, by our numbers: each of
    our priced legs taken out in turn, the payout cut by that leg's own
    price and the chance re-run with the engine's correlation. Named only
    when it lifts the expected return by DROP_GAIN. A same-game slip's
    payout is the book's own, not the product of its legs, so the cut
    payout is close rather than exact and says so."""
    if len(legs) < 3 or not payout or ev is None:
        return None
    best = None
    for i, l in enumerate(legs):
        d = to_decimal(l.get("odds"))
        if not d or l.get("prob") is None:
            continue
        rest = legs[:i] + legs[i + 1:]
        p = _ticket_chance(rest)
        if p is None:
            continue
        pay = payout / d
        ev_i = p * pay - 1.0
        if ev_i >= ev + DROP_GAIN and (best is None or ev_i > best["ev"]):
            best = {"leg": _name(l), "chance": round(p, 4), "odds": from_decimal(pay), "ev": round(ev_i, 4)}
    if best:
        best["approx"] = _same_game(legs)
    return best


#: A same-game pair is named when the engine's correlation is at least this.
PAIR_RHO = 0.15


def pairs(legs: list[dict]) -> list[dict]:
    """Same-game legs that move together or pull apart, by the parlay
    engine's own correlation and its reason in words (parlays.relate) —
    what makes the ticket's chance more or less than its legs multiplied.
    The pairs it would never build are named in `notes`."""
    from . import parlays as P
    priced = [l for l in legs if l.get("prob") is not None]
    out = []
    for i in range(len(priced)):
        for j in range(i + 1, len(priced)):
            a, b = priced[i], priced[j]
            ka, kb = _game_of(a), _game_of(b)
            if not any(ka[0]) or ka != kb:
                continue
            try:
                rel = P.relate(a.get("league") or "nfl", _relation_leg(a), _relation_leg(b))
            except Exception:                                      # noqa: BLE001
                continue
            rho = float(getattr(rel, "rho", 0.0) or 0.0)
            if getattr(rel, "verdict", "ok") in ("kill", "duplicate") or abs(rho) < PAIR_RHO:
                continue
            out.append({"legs": [_name(a), _name(b)], "rho": round(rho, 2),
                        "why": str(getattr(rel, "mechanism", "") or "")[:200]})
    return sorted(out, key=lambda x: -abs(x["rho"]))[:4]


def alerts(legs: list[dict]) -> list[str]:
    """What to read before anything else: a leg on a player listed on the
    injury report, and a prop no book is pricing right now (taken down, as
    books do when news breaks)."""
    out = []
    for l in legs:
        status = next((f["t"] for f in l.get("why") or [] if f.get("k") == "Status"), "")
        if status:
            out.append(f"{l.get('player') or _name(l)}: {status[0].lower() + status[1:]}")
        pr = l.get("price")
        if isinstance(pr, dict) and not pr.get("any") and l["market"] not in GAME_MARKETS:
            out.append(f"No book is pricing {_name(l)} right now — it may have been taken down")
    return out[:6]


def _kickoff(boards: dict, leg: dict) -> str:
    """"YYYY-MM-DD HH:MM" for the leg's game, off its board's schedule."""
    board = boards.get(leg.get("league") or "") or {}
    r = leg.get("row") or {}
    teams = ({r.get("home"), r.get("away")} - {None, ""}) or \
        ({leg.get("team") or r.get("team"), leg.get("opponent") or r.get("opponent")} - {None, ""})
    if not teams:
        return ""
    for g in board.get("games") or []:
        if isinstance(g, dict) and teams <= {g.get("home"), g.get("away")}:
            return " ".join(str(x) for x in (g.get("date"), g.get("kickoff")) if x)
    return ""


def _ticket_chance(legs: list[dict]) -> float | None:
    """Our chance every leg on ``legs`` wins: the priced legs through the
    parlay engine's correlation (`joint`), a leg off our boards at its own
    price's break-even — we add no opinion of ours, so it neither helps nor
    hurts — and None when a leg has neither, or none is ours."""
    ours, _ = joint(legs)
    if ours is None or any(l["prob"] is None and l["needs"] is None for l in legs):
        return None
    return ours * math.prod(l["needs"] for l in legs if l["prob"] is None and l["needs"] is not None)


def grade(slip: dict, boards: dict, live=None) -> dict:
    """The card: every leg priced and ranked with the facts behind its
    number, the ticket's chance by our numbers, the ticket replayed 2,000
    nights, what its payout needs, a letter, the pairs worth naming and
    the swap for the weakest leg. With ``live`` (engine/sliplive.Live):
    each leg's price at every book right now and where its game stands,
    and for the ticket where it stands, the best book to place it at, the
    leg it is better without, and the alerts worth reading first."""
    legs = [price_leg(boards, l) for l in slip.get("legs") or []]
    for l in legs:
        l["why"] = why(boards, l)
        l["kickoff"] = _kickoff(boards, l)
        if live is not None:
            l["live"] = live.state(l)
            # A started game's pre-game prices are gone from the books; the
            # leg says where it stands instead (sliplive.live_state).
            started = (l["live"] or {}).get("state") in ("live", "final")
            l["price"] = None if started else live.prices(l, boards.get(l.get("league") or ""))
    _, notes = joint(legs)
    payout = to_decimal(slip.get("total_odds"))
    if payout is None and legs and all(_odds(l["odds"]) for l in legs):
        payout = math.prod(to_decimal(l["odds"]) for l in legs)
    chance = _ticket_chance(legs)
    ev = (chance * payout - 1.0) if (chance is not None and payout) else None
    needs = (1.0 / payout) if payout else None
    ranked = sorted(legs, key=lambda l: (l["prob"] is None,
                                         -(l["edge"] if l["edge"] is not None else (l["prob"] or 0) - 0.5)))
    priced = [l for l in ranked if l["prob"] is not None]
    weakest = priced[-1] if priced else None
    sim = simulate(legs) if chance else None          # nothing to replay on a ticket that cannot cash
    if sim:
        for l, h in zip(legs, sim.pop("hits")):
            l["sim_hits"] = h
    out_legs = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in l.items()
                 if k not in ("row", "game_key")} for l in ranked]
    kicks = sorted(k for k in (l.get("kickoff") for l in legs) if k)
    now = standing(legs)
    return {
        "now": now,
        # Where to place it and what to cut are pre-game questions.
        "shop": None if now else shop(legs, slip.get("total_odds")),
        "better": None if now else without(legs, payout, ev),
        "pairs": pairs(legs),
        "alerts": alerts(legs),
        "first_kickoff": kicks[0] if kicks else "",
        "legs": out_legs,
        "n_legs": len(legs), "n_priced": len(priced), "dropped": int(slip.get("dropped") or 0),
        "book": slip.get("book") or "", "stake": slip.get("stake") or 0,
        "total_odds": slip.get("total_odds") or 0,
        "ours": None if chance is None else round(chance, 4),
        "needs": None if needs is None else round(needs, 4),
        "ev": None if ev is None else round(ev, 4),
        "grade": letter(ev) if len(priced) == len(legs) else ("?" if ev is None else letter(ev) + "*"),
        "notes": notes,
        "weakest": _name(weakest) if weakest and len(priced) > 1 else "",
        "swap": _swap(boards, weakest, legs) if weakest and len(priced) > 1 else None,
        "sim": sim,
    }


def summary(card: dict) -> str:
    """One paragraph of the card, for the conversation Ask carries on. The
    verdict comes first: Ask keeps the first askbot.MAX_TURN_CHARS of a
    turn as the context of the next question."""
    parts = [f"Graded parlay, {card['n_legs']} legs ({card['n_priced']} on our boards)."]
    now = card.get("now") or {}
    if now.get("status") == "lost":
        parts.append(f"Live: this ticket has already lost — {now.get('lost_leg')} missed.")
    elif now.get("status") == "won":
        parts.append("Live: every leg has won.")
    elif now.get("status") == "open":
        bits = [f"{now[k]} {w}" for k, w in (("won", "won"), ("push", "pushed"), ("live", "in play"),
                                              ("start", "yet to start")) if now.get(k)]
        parts.append("Live: " + ", ".join(bits)
                     + (f"; our chance for the rest {now['chance']:.0%}" if now.get("chance") is not None else "")
                     + ".")
    if card.get("ours") is not None:
        parts.append((f"Before kickoff our chance was {card['ours']:.0%}" if now
                      else f"Our chance it all hits: {card['ours']:.0%}")
                     + (f"; the payout needs {card['needs']:.0%}." if card.get("needs") else "."))
    if card.get("ev") is not None:
        parts.append(f"Expected return {card['ev']:+.0%} a dollar by our numbers, grade {card['grade']}.")
    sim = card.get("sim") or {}
    if sim.get("nights"):
        parts.append(f"In {sim['nights']:,} simulated nights it cashed {sim['cashed']:,} times"
                     + (f" and missed by one leg on {sim['one_short']:.0%}" if sim.get("one_short") else "")
                     + (f", most often {sim['breaker']['leg']}" if sim.get("breaker") else "") + ".")
    sh = card.get("shop") or {}
    if sh.get("beats_yours") and sh.get("books"):
        parts.append(f"Best place for it now: {sh['books'][0]['book']} at {sh['books'][0]['odds']:+d}"
                     f" (your slip {sh['yours']:+d}).")
    bt = card.get("better") or {}
    if bt.get("leg"):
        parts.append(f"Better without {bt['leg']}: return {bt['ev']:+.0%} a dollar, chance {bt['chance']:.0%}, "
                     f"pays {bt['odds']:+d}" + (" (about)" if bt.get("approx") else "") + ".")
    if card.get("weakest"):
        parts.append(f"Weakest leg: {card['weakest']}.")
    for l in card["legs"]:
        p = (("no number of ours at that line" if l.get("found") else "not on our board")
             if l["prob"] is None else f"ours {l['prob']:.0%}")
        n = "" if l.get("needs") is None else f", needs {l['needs']:.0%}"
        lead = next((w["t"] for w in l.get("why") or []
                     if w.get("k") in ("Defense", "Matchup read", "Prediction markets")), "")
        if len(lead) > 140:
            lead = lead[:139].rsplit(" ", 1)[0].rstrip(",;—- ") + "…"   # a whole word, never "our nu"
        parts.append(f"{_name(l)}: {p}{n} ({l['verdict']})" + (f"; {lead}" if lead else "") + ".")
    return " ".join(parts)[:1600]
