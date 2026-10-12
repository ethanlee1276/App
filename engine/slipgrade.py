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
import json
import math

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
                got = (_num(r.get("model_prob"), float("nan")), r.get("odds"), "likely", r)
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
    out["tier"] = str(r.get("tier") or "") if out["found"] == "likely" else ""
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
    total, notes = 1.0, []
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
        if len(group) == 1:
            total *= ps[0]
        elif len(group) == 2:
            total *= P.joint_two(ps[0], ps[1], rhos[0])
        elif len(group) == 3:
            total *= P.joint_three(tuple(ps), (rhos[0], rhos[1], rhos[2]))
        else:
            total *= joint_k(ps, sum(rhos) / len(rhos))
    return max(0.0, min(1.0, total)), notes


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
        p = _num(r.get("model_prob"), None)
        if p is not None and (best is None or p > best[0]):
            best = (p, r)
    if not best:
        return None
    r = best[1]
    return {"player": r.get("player") or "", "market": r.get("market") or "", "side": r.get("side") or "",
            "line": r.get("line"), "odds": r.get("odds"), "prob": round(best[0], 4), "tier": r.get("tier") or ""}


def grade(slip: dict, boards: dict) -> dict:
    """The card: every leg priced and ranked, the ticket's chance by our
    numbers, what its payout needs, a letter, the pairs worth naming and
    the swap for the weakest leg."""
    legs = [price_leg(boards, l) for l in slip.get("legs") or []]
    ours, notes = joint(legs)
    # The unpriced legs stand in at their own price's break-even — we add no
    # opinion of ours, so they neither help nor hurt the grade.
    stand_in = math.prod(l["needs"] for l in legs if l["prob"] is None and l["needs"] is not None)
    unpriced_no_price = [l for l in legs if l["prob"] is None and l["needs"] is None]
    payout = to_decimal(slip.get("total_odds"))
    if payout is None and legs and all(_odds(l["odds"]) for l in legs):
        payout = math.prod(to_decimal(l["odds"]) for l in legs)
    chance = (ours * stand_in) if (ours is not None and not unpriced_no_price) else None
    ev = (chance * payout - 1.0) if (chance is not None and payout) else None
    needs = (1.0 / payout) if payout else None
    ranked = sorted(legs, key=lambda l: (l["prob"] is None,
                                         -(l["edge"] if l["edge"] is not None else (l["prob"] or 0) - 0.5)))
    priced = [l for l in ranked if l["prob"] is not None]
    weakest = priced[-1] if priced else None
    out_legs = [{k: (round(v, 4) if isinstance(v, float) else v) for k, v in l.items()
                 if k not in ("row", "game_key")} for l in ranked]
    return {
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
    }


def summary(card: dict) -> str:
    """One paragraph of the card, for the conversation Ask carries on."""
    parts = [f"Graded parlay, {card['n_legs']} legs ({card['n_priced']} on our boards)."]
    if card.get("ours") is not None:
        parts.append(f"Our chance it all hits: {card['ours']:.0%}"
                     + (f"; the payout needs {card['needs']:.0%}." if card.get("needs") else "."))
    if card.get("ev") is not None:
        parts.append(f"Expected return {card['ev']:+.0%} a dollar by our numbers, grade {card['grade']}.")
    for l in card["legs"]:
        p = (("no number of ours at that line" if l.get("found") else "not on our board")
             if l["prob"] is None else f"ours {l['prob']:.0%}")
        n = "" if l.get("needs") is None else f", needs {l['needs']:.0%}"
        parts.append(f"{_name(l)}: {p}{n} ({l['verdict']}).")
    if card.get("weakest"):
        parts.append(f"Weakest leg: {card['weakest']}.")
    return " ".join(parts)[:1600]
