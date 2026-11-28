"""The site's picks, placed on Kalshi — so a Pikkit account can verify them.

    python3 -m engine.kalshitrade check          # key loads, signs, balance reads
    python3 -m engine.kalshitrade run --dry      # what it would place, nothing written
    python3 -m engine.kalshitrade run            # one pass (paper or live, per QB_KALSHI_MODE)
    python3 -m engine.kalshitrade sync           # fills and results for every order
    python3 -m engine.kalshitrade report         # the ledger: today, open, record, P&L
    python3 -m engine.kalshitrade stop | go      # the kill switch (data/kalshi.STOP)
    python3 -m engine.kalshitrade series         # which NFL series Kalshi lists today

Ethan, 2026-10-06: "link the site to a pikkit or juice reel account so we
can legitimately track all the bets the site puts in … it should get
synced to a pikkit account and the bets get placed … without actually
placing bets on a sportsbook." Pikkit and Juice Reel count a bet as
verified only when it comes from an account they sync, and both sync
Kalshi. Kalshi is an exchange with an official trading API, so a program
placing orders there is allowed; a sportsbook is not (and this site never
logs into one). Every pick the trader places shows up in Pikkit by itself.

THE MONEY IS SMALL ON PURPOSE. One contract per pick (QB_KALSHI_CONTRACTS)
risks the contract's price — 20 to 99 cents, under a dollar, never more
— so a $50 account covers a week of picks. The site's units are not these
stakes: a Top pick and a Worth-a-look get the same one contract.

WHAT IT PLACES. Only the lanes QB_KALSHI_LANES names (default: the Pick of
the Day and the one board's Top and Strong tiers), only before kickoff,
only where Kalshi lists the same bet at the same line, and only at a price
no worse than our own chance (QB_KALSHI_SLACK_CENTS above it at most).
"No edge, no bet" on an exchange is simply "never pay more than we think
it is worth".

THE GUARD RAILS, every one a line in /etc/qellys/env:
    QB_KALSHI_MODE              off | paper | live        (default off)
    QB_KALSHI_CONTRACTS         contracts per pick        (default 1)
    QB_KALSHI_MAX_ORDER_CENTS   cost cap per order, fee in (default 100)
    QB_KALSHI_DAILY_CAP_CENTS   cost cap per day          (default 1000 = $10)
    QB_KALSHI_MAX_ORDERS_DAY    orders per day            (default 20)
    QB_KALSHI_RESERVE_CENTS     stop live when the balance would fall under (default 1000)
    QB_KALSHI_LANES             potd,top,strong,look,edge,game (default potd,top,strong)
    QB_KALSHI_SPORTS            nfl,cfb                   (default nfl)
    QB_KALSHI_SLACK_CENTS       cents over our chance we still pay (default 0)
    QB_KALSHI_PROP_SERIES       Kalshi series tickers for player props, comma-separated
    QB_KALSHI_KEY_ID            the API key id (live only)
    QB_KALSHI_KEY_FILE          the private key PEM (default /etc/qellys/kalshi.pem)
    QB_PIKKIT_MODEL_URL         the Pikkit profile the Kalshi account is synced to
Plus the kill switch: a file data/kalshi.STOP, or `stop` here, and nothing
is placed until `go`. Paper mode records exactly what live would have done
and places nothing; it needs no key.

ONE ORDER PER PICK. Each pick gets one client_order_id (a UUID off the pick
and the date) and the ledger refuses a second while the first is open or
filled; an order that expired unfilled may be retried on a later pass.
Orders are limit orders at the current ask, good for fifteen minutes, so
nothing rests on the book waiting to fill at a price the slate has moved
past. The ledger is data/kalshi_trades.db; `sync` settles each row from
Kalshi's own result for the market, which is also what Pikkit grades on.

Nothing here touches the model's journal (engine/ledger): the record on
the Record page is the site's, graded on the book prices it posts; this
ledger is what one real account did with those picks.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "kalshi_trades.db"
STOP_FILE = DATA / "kalshi.STOP"
API = "https://api.elections.kalshi.com/trade-api/v2"
API_PATH = "/trade-api/v2"
#: The order endpoint. Kalshi's docs name a newer "events/orders" shape;
#: this is the documented one that remains supported, in one place.
ORDERS_PATH = "/portfolio/orders"
NAMESPACE = uuid.UUID("7d3a1c9e-5b2f-4e8a-9c6d-2f1e0b4a8c73")
BOARD_FILE = {"nfl": "recommendations.json", "cfb": "cfb.json"}
LANES = ("potd", "top", "strong", "look", "edge", "game")
ORDER_TTL_S = 15 * 60
FEE_RATE = 0.07
TIMEOUT_S = 20
#: A book wider than this is not a price to take one contract at.
MAX_SPREAD_CENTS = 10

#: Words a Kalshi player-prop title uses for each of our markets.
PROP_WORDS = {
    "pass_yds": ("passing yards", "pass yards", "passing yds"),
    "rush_yds": ("rushing yards", "rush yards", "rushing yds"),
    "rec_yds": ("receiving yards", "rec yards", "receiving yds"),
    "receptions": ("receptions", "catches"),
    "pass_td": ("passing touchdowns", "touchdown passes", "passing tds"),
    "anytime_td": ("touchdown", "td"),
    "rush_att": ("rushing attempts", "carries"),
    "pass_att": ("passing attempts", "pass attempts"),
    "pass_cmp": ("completions",),
}


# ─── configuration ─────────────────────────────────────────────────────────

@dataclass
class Config:
    mode: str = "off"
    key_id: str = ""
    key_file: str = "/etc/qellys/kalshi.pem"
    contracts: int = 1
    max_order_cents: int = 100
    daily_cap_cents: int = 1000
    max_orders_day: int = 20
    reserve_cents: int = 1000
    lanes: tuple = ("potd", "top", "strong")
    sports: tuple = ("nfl",)
    slack_cents: int = 0
    prop_series: tuple = ()
    pikkit_url: str = ""
    extra: dict = field(default_factory=dict)


def _int(v, default: int) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return default


def _csv(v, default: tuple) -> tuple:
    got = tuple(x.strip().lower() for x in str(v or "").split(",") if x.strip())
    return got or default


def config(env: dict | None = None) -> Config:
    """The trader's settings out of the environment (/etc/qellys/env on
    the box). Every number is clamped to a sane range: a typo cannot
    turn a 100-cent cap into a 10,000-cent one."""
    if env is None:
        try:
            from .secrets import load_local_secrets
            load_local_secrets()
        except Exception:                                    # noqa: BLE001
            pass
        env = os.environ
    mode = str(env.get("QB_KALSHI_MODE", "off") or "off").strip().lower()
    if mode not in ("off", "paper", "live"):
        mode = "off"
    lanes = tuple(x for x in _csv(env.get("QB_KALSHI_LANES"), ("potd", "top", "strong")) if x in LANES)
    return Config(
        mode=mode,
        key_id=str(env.get("QB_KALSHI_KEY_ID", "") or "").strip(),
        key_file=str(env.get("QB_KALSHI_KEY_FILE", "") or "").strip() or "/etc/qellys/kalshi.pem",
        contracts=max(1, min(10, _int(env.get("QB_KALSHI_CONTRACTS"), 1))),
        max_order_cents=max(1, min(2000, _int(env.get("QB_KALSHI_MAX_ORDER_CENTS"), 100))),
        daily_cap_cents=max(1, min(20000, _int(env.get("QB_KALSHI_DAILY_CAP_CENTS"), 1000))),
        max_orders_day=max(1, min(200, _int(env.get("QB_KALSHI_MAX_ORDERS_DAY"), 20))),
        reserve_cents=max(0, _int(env.get("QB_KALSHI_RESERVE_CENTS"), 1000)),
        lanes=lanes or ("potd", "top", "strong"),
        sports=_csv(env.get("QB_KALSHI_SPORTS"), ("nfl",)),
        slack_cents=max(0, min(10, _int(env.get("QB_KALSHI_SLACK_CENTS"), 0))),
        prop_series=tuple(x.upper() for x in _csv(env.get("QB_KALSHI_PROP_SERIES"), ())),
        pikkit_url=str(env.get("QB_PIKKIT_MODEL_URL", "") or "").strip(),
    )


def stopped(path: Path | None = None) -> bool:
    """The kill switch: a file at STOP_FILE (read at call time, so a test
    or a deploy can move it)."""
    return Path(path or STOP_FILE).exists()


# ─── the ledger ────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    client_id TEXT PRIMARY KEY, ts TEXT, day TEXT, mode TEXT, sport TEXT, lane TEXT,
    pick_id TEXT, player TEXT, market TEXT, side TEXT, line REAL, label TEXT,
    ticker TEXT, k_side TEXT, count INTEGER, price_cents INTEGER, fee_cents INTEGER,
    cost_cents INTEGER, our_cents INTEGER, status TEXT, order_id TEXT, note TEXT,
    result TEXT, pnl_cents INTEGER, settled_at TEXT
);
CREATE INDEX IF NOT EXISTS orders_day ON orders(day);
CREATE INDEX IF NOT EXISTS orders_pick ON orders(pick_id);
CREATE TABLE IF NOT EXISTS runs (
    ts TEXT, sport TEXT, mode TEXT, considered INTEGER, matched INTEGER, placed INTEGER,
    note TEXT
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _today(now: _dt.datetime) -> str:
    return now.strftime("%Y-%m-%d")


def spent_today(conn, day: str) -> tuple[int, int]:
    """(cents, orders) placed for real today — paper rows do not count."""
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_cents),0), COUNT(*) FROM orders WHERE day=? AND mode='live' "
        "AND status NOT IN ('canceled','error','expired')", (day,)).fetchone()
    return int(row[0] or 0), int(row[1] or 0)


def open_for_pick(conn, pick_id: str, mode: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM orders WHERE pick_id=? AND mode=? AND status NOT IN ('canceled','error','expired') "
        "LIMIT 1", (pick_id, mode)).fetchone() is not None


# ─── money ─────────────────────────────────────────────────────────────────

def fee_cents(count: int, price_cents: int) -> int:
    """Kalshi's taker fee, rounded UP to the next cent per order:
    0.07 × contracts × P × (1 − P)."""
    p = price_cents / 100.0
    return int(math.ceil(FEE_RATE * count * p * (1.0 - p) * 100.0 - 1e-9))


def cost_cents(count: int, price_cents: int) -> int:
    return count * price_cents + fee_cents(count, price_cents)


def quotes(raw: dict) -> tuple[int | None, int | None]:
    """(yes_bid, yes_ask) in cents off a raw Kalshi market, dollars first."""
    def cents(dollars_key, cents_key):
        v = raw.get(dollars_key)
        if v not in (None, ""):
            try:
                return int(round(float(v) * 100))
            except (TypeError, ValueError):
                return None
        v = raw.get(cents_key)
        try:
            return None if v in (None, "") else int(round(float(v)))
        except (TypeError, ValueError):
            return None
    return cents("yes_bid_dollars", "yes_bid"), cents("yes_ask_dollars", "yes_ask")


def ask_for(k_side: str, yes_bid, yes_ask) -> int | None:
    """What one contract on ``k_side`` costs to take right now: the YES
    ask, or 100 minus the YES bid for a NO."""
    if k_side == "yes":
        return yes_ask if yes_ask else None
    return (100 - yes_bid) if yes_bid else None


# ─── the picks ─────────────────────────────────────────────────────────────

def pick_id(row: dict) -> str:
    from .explainer import pick_id as _pid
    return _pid(row)


def _prob(row: dict):
    for k in ("model_prob", "hit_prob", "prob"):
        v = row.get(k)
        if v not in (None, ""):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def candidates(board: dict, lanes: tuple) -> list[dict]:
    """Every pick in the chosen lanes, once each (the first lane that names
    it keeps it): [{"lane", "row", "pick_id"}]."""
    out, seen = [], set()

    def add(lane, r):
        if not isinstance(r, dict) or not (r.get("player") or r.get("kind") == "game"):
            return
        pid = pick_id(r)
        if pid in seen:
            return
        seen.add(pid)
        out.append({"lane": lane, "row": r, "pick_id": pid})

    for lane in LANES:
        if lane not in lanes:
            continue
        if lane == "potd":
            card = board.get("pick_of_the_day") or {}
            pick = card.get("pick")
            verdict = card.get("verdict") or {}
            if pick and verdict.get("bet") is not False:
                add("potd", pick)
        elif lane in ("top", "strong", "look"):
            for r in ((board.get("likely_board") or {}).get("rows")) or []:
                if r.get("tier") == lane:
                    add(lane, r)
        elif lane == "edge":
            for r in board.get("recommendations") or []:
                if r.get("recommended"):
                    add("edge", r)
        elif lane == "game":
            for r in board.get("most_likely") or []:
                if r.get("kind") == "game":
                    add("game", r)
    return out


def _game_of(row: dict, games: list[dict]) -> dict | None:
    home, away = row.get("home"), row.get("away")
    if home and away:
        for g in games:
            if g.get("home") == home and g.get("away") == away:
                return g
    team = row.get("team") or row.get("pick")
    key = str(row.get("game") or "")
    for g in games:
        if key and key == f"{g.get('away')}@{g.get('home')}":
            return g
        if team and team in (g.get("home"), g.get("away")):
            return g
    return None


def _kick(row: dict, g: dict | None) -> _dt.datetime | None:
    for src in (row, g or {}):
        k = str(src.get("kickoff") or "")
        if re.search(r"(Z|[+-]\d{2}:?\d{2})$", k):
            try:
                return _dt.datetime.fromisoformat(k.replace("Z", "+00:00"))
            except ValueError:
                pass
    return None


def started(row: dict, g: dict | None, now: _dt.datetime) -> bool:
    if row.get("live") is True or ((g or {}).get("live") or {}).get("state") in ("live", "final"):
        return True
    k = _kick(row, g)
    if k is not None:
        return k <= now
    day = str((g or {}).get("date") or row.get("game_date") or "")[:10]
    return bool(day) and day < _today(now)


# ─── matching our pick to Kalshi's market ──────────────────────────────────

def _event_game(event_ticker: str):
    from .crowd import _kalshi_event_game
    return _kalshi_event_game(event_ticker)


def _club(ticker: str) -> str:
    return str(ticker or "").upper().rsplit("-", 1)[-1].rstrip("0123456789")


def _same_game(m: dict, g: dict) -> bool:
    got = _event_game(m.get("event_ticker") or m.get("ticker"))
    if not got:
        return False
    home, away = str(g.get("home") or "").upper(), str(g.get("away") or "").upper()
    date = str(g.get("date") or "")[:10]
    return got[1] in (away + home, home + away) and (not date or got[0] == date)


def _strike(m: dict):
    try:
        return None if m.get("floor_strike") in (None, "") else float(m["floor_strike"])
    except (TypeError, ValueError):
        return None


def match_game_line(row: dict, g: dict, markets: list[dict]) -> dict | None:
    """The Kalshi market for a moneyline, spread or total pick, and which
    side of it pays when our pick wins: {"ticker", "k_side", "title", "how"}.

    A spread "T −6.5" is YES on "T wins by over 6.5"; "T +6.5" is NO on
    "OPP wins by over 6.5" (the other club failing to cover it). Whole-
    number lines have no twin on Kalshi and match nothing — a push is a
    different bet."""
    market = str(row.get("market") or "")
    team = str(row.get("pick") or row.get("team") or "").upper()
    home, away = str(g.get("home") or "").upper(), str(g.get("away") or "").upper()
    opp = away if team == home else home
    line = row.get("line")
    try:
        line = None if line in (None, "") else float(line)
    except (TypeError, ValueError):
        line = None
    for m in markets:
        if not _same_game(m, g):
            continue
        series = str(m.get("event_ticker") or m.get("ticker") or "").upper().split("-")[0]
        f = _strike(m)
        if market == "moneyline" and "GAME" in series and _club(m.get("ticker")) == team:
            return {"ticker": m["ticker"], "k_side": "yes", "title": m.get("title", ""), "how": f"{team} to win"}
        if market == "spread" and "SPREAD" in series and f is not None and line is not None \
                and abs(line * 2 - round(line * 2)) < 1e-9 and int(round(line * 2)) % 2:
            club = _club(m.get("ticker"))
            if line < 0 and club == team and abs(f + line) < 0.01:
                return {"ticker": m["ticker"], "k_side": "yes", "title": m.get("title", ""),
                        "how": f"{team} wins by over {f:g}"}
            if line > 0 and club == opp and abs(f - line) < 0.01:
                return {"ticker": m["ticker"], "k_side": "no", "title": m.get("title", ""),
                        "how": f"NO on {opp} wins by over {f:g}"}
        if market == "total" and "TOTAL" in series and f is not None and line is not None \
                and abs(f - line) < 0.01:
            over = str(row.get("side") or "").lower().startswith("o")
            return {"ticker": m["ticker"], "k_side": "yes" if over else "no", "title": m.get("title", ""),
                    "how": f"{'YES' if over else 'NO'} on over {f:g} points"}
    return None


def _name_ok(title: str, player: str) -> bool:
    t = title.lower()
    parts = [p for p in re.split(r"[^a-z]+", str(player or "").lower()) if len(p) >= 2]
    if not parts:
        return False
    last = parts[-1]
    return last in t and (len(parts) == 1 or parts[0] in t or parts[0][0] + "." in t)


def match_prop(row: dict, g: dict | None, markets: list[dict]) -> dict | None:
    """A player prop on a Kalshi prop series (QB_KALSHI_PROP_SERIES): the
    player named, the stat named, the strike equal to our line — "250+
    passing yards" is a floor strike of 249.5, our over 249.5 is YES on it,
    our under 249.5 is NO. Anytime touchdown is YES on his scorer market."""
    market = str(row.get("market") or "")
    words = PROP_WORDS.get(market)
    if not words:
        return None
    player = str(row.get("player") or "")
    side = str(row.get("side") or "").lower()
    try:
        line = None if row.get("line") in (None, "") else float(row["line"])
    except (TypeError, ValueError):
        line = None
    for m in markets:
        if g and not _same_game(m, g) and _event_game(m.get("event_ticker")) is not None:
            continue
        text = f"{m.get('title', '')} {m.get('yes_sub_title', '')} {m.get('subtitle', '')}"
        if not _name_ok(text, player) or not any(w in text.lower() for w in words):
            continue
        if market == "anytime_td":
            if side in ("yes", "over", ""):
                return {"ticker": m["ticker"], "k_side": "yes", "title": m.get("title", ""),
                        "how": f"{player} scores"}
            continue
        f = _strike(m)
        if f is None or line is None:
            continue
        # A "250+" market may carry its strike as 250 or 249.5; our line is
        # the half point under it.
        if abs(f - line) < 0.01 or abs(f - 0.5 - line) < 0.01:
            over = side in ("over", "yes")
            return {"ticker": m["ticker"], "k_side": "yes" if over else "no", "title": m.get("title", ""),
                    "how": f"{'YES' if over else 'NO'} on {player} {f:g}+ ({market})"}
    return None


# ─── the client ────────────────────────────────────────────────────────────

class KalshiError(RuntimeError):
    pass


class Client:
    """Authenticated calls. ``opener`` is injectable for tests."""

    def __init__(self, key_id: str, pem: str | bytes, opener=None):
        self.key_id, self.pem = key_id, pem
        self.opener = opener or self._http

    @staticmethod
    def _http(method: str, url: str, headers: dict, body: bytes | None) -> dict:
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode(errors="replace")[:300]
            raise KalshiError(f"HTTP {exc.code} on {method} {url.split('?')[0]}: {text}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise KalshiError(f"{method} {url.split('?')[0]}: {exc}") from exc

    def call(self, method: str, path: str, body: dict | None = None, query: str = "") -> dict:
        from .kalshiauth import headers as _headers
        h = _headers(self.key_id, self.pem, method, API_PATH + path)
        h.update({"Content-Type": "application/json", "Accept": "application/json",
                  "User-Agent": "qellys-kalshi-trader/1"})
        data = json.dumps(body).encode() if body is not None else None
        return self.opener(method, API + path + (f"?{query}" if query else ""), h, data)

    def balance_cents(self) -> int:
        got = self.call("GET", "/portfolio/balance")
        # Cents today; Kalshi has been moving money fields to *_dollars.
        if got.get("balance_dollars") not in (None, ""):
            return int(round(float(got["balance_dollars"]) * 100))
        return int(got.get("balance") or 0)

    def create_order(self, order: dict) -> dict:
        return (self.call("POST", ORDERS_PATH, order) or {}).get("order") or {}

    def order(self, order_id: str) -> dict:
        return (self.call("GET", f"{ORDERS_PATH}/{order_id}") or {}).get("order") or {}


def load_pem(cfg: Config) -> str:
    p = Path(cfg.key_file)
    try:
        return p.read_text()
    except OSError as exc:
        raise KalshiError(f"cannot read the key file {p}: {exc}") from exc


def client_for(cfg: Config, opener=None) -> Client:
    if not cfg.key_id:
        raise KalshiError("QB_KALSHI_KEY_ID is not set")
    from .kalshiauth import parse_pem
    pem = load_pem(cfg)
    parse_pem(pem)
    return Client(cfg.key_id, pem, opener=opener)


# ─── one pass ──────────────────────────────────────────────────────────────

def _load_board(sport: str) -> dict:
    from . import gate
    path = Path(gate.board_source(ROOT / "web" / "data" / BOARD_FILE[sport]))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _series_for(sport: str, cfg: Config) -> list[str]:
    from .sources import kalshi as K
    out = list(K.SPORT_SERIES.get(sport, ())[:1]) + list(K.LINE_SERIES.get(sport, ()))
    return out + [s for s in cfg.prop_series if s not in out]


def _markets(series: list[str], fetch_events) -> tuple[list[dict], dict]:
    markets, report = [], {}
    for s in series:
        try:
            events = fetch_events(s)
        except Exception as exc:                             # noqa: BLE001
            report[s] = f"error: {exc}"
            continue
        n = 0
        for ev in events or []:
            for m in ev.get("markets") or []:
                if m.get("ticker"):
                    markets.append(m)
                    n += 1
        report[s] = n
    return markets, report


def decide(cand: dict, match: dict, raw: dict, cfg: Config, spent: int, n_today: int,
           balance: int | None) -> tuple[str, dict | None, str]:
    """("place" | "skip", order, note) for one matched pick at a fresh quote."""
    row = cand["row"]
    status = str(raw.get("status") or "open").lower()
    if status not in ("open", "active", ""):
        return "skip", None, f"market {status}"
    yb, ya = quotes(raw)
    ask = ask_for(match["k_side"], yb, ya)
    if ask is None or not 1 <= ask <= 99:
        return "skip", None, "no price on our side of the book"
    if yb and ya and ya - yb > MAX_SPREAD_CENTS:
        return "skip", None, f"book {ya - yb}c wide"
    p = _prob(row)
    if p is None:
        return "skip", None, "the pick has no chance on it"
    our = int(round(p * 100))
    if ask > our + cfg.slack_cents:
        return "skip", None, f"ask {ask}c is above our {our}c"
    count = cfg.contracts
    cost = cost_cents(count, ask)
    if cost > cfg.max_order_cents:
        return "skip", None, f"cost {cost}c over the {cfg.max_order_cents}c order cap"
    if spent + cost > cfg.daily_cap_cents:
        return "skip", None, f"would pass the daily cap ({spent + cost}c of {cfg.daily_cap_cents}c)"
    if n_today >= cfg.max_orders_day:
        return "skip", None, f"{n_today} orders today already"
    if balance is not None and balance - cost < cfg.reserve_cents:
        return "skip", None, f"balance {balance}c would fall under the {cfg.reserve_cents}c reserve"
    order = {"ticker": match["ticker"], "action": "buy", "side": match["k_side"], "type": "limit",
             "count": count, ("yes_price" if match["k_side"] == "yes" else "no_price"): ask}
    return "place", dict(order, _cost=cost, _fee=fee_cents(count, ask), _our=our), ""


def _label(row: dict) -> str:
    if row.get("kind") == "game":
        return str(row.get("pick_label") or row.get("player") or "")
    try:
        line = "" if row.get("line") in (None, "") else f"{float(row['line']):g}"
    except (TypeError, ValueError):
        line = str(row.get("line"))
    return " ".join(x for x in (str(row.get("player") or ""), str(row.get("side") or "").lower(), line,
                                str(row.get("market") or "")) if x)


def run_cycle(sport: str = "nfl", cfg: Config | None = None, board: dict | None = None,
              now: _dt.datetime | None = None, fetch_events=None, fetch_tickers=None,
              client: Client | None = None, conn=None, dry: bool = False, log=print) -> dict:
    """One pass over one sport's board. Returns a summary dict; in paper
    mode records what live would have placed; in live mode places it."""
    cfg = cfg or config()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    out = {"sport": sport, "mode": cfg.mode, "considered": 0, "matched": 0, "placed": 0,
           "skipped": [], "orders": [], "series": {}}
    if cfg.mode == "off":
        out["note"] = "QB_KALSHI_MODE is off"
        return out
    if stopped():
        out["note"] = f"stopped — {STOP_FILE.name} is present (`go` removes it)"
        return out
    from .sources import kalshi as K
    fetch_events = fetch_events or K.fetch_events
    fetch_tickers = fetch_tickers or (lambda t: K.fetch_markets_by_tickers(t, ttl=0))
    board = board if board is not None else _load_board(sport)
    games = board.get("games") or []
    cands = candidates(board, cfg.lanes)
    out["considered"] = len(cands)
    if not cands:
        out["note"] = "no picks in the chosen lanes"
        return out
    markets, out["series"] = _markets(_series_for(sport, cfg), fetch_events)
    conn = conn or connect()
    day = _today(now)
    matched = []
    for c in cands:
        row = c["row"]
        g = _game_of(row, games)
        if started(row, g, now):
            out["skipped"].append((_label(row), "game under way"))
            continue
        if str(row.get("injury_status") or "").strip():
            out["skipped"].append((_label(row), f"listed {row['injury_status']}"))
            continue
        if open_for_pick(conn, c["pick_id"], cfg.mode):
            continue                                         # already placed (or on paper)
        if row.get("kind") == "game":
            m = match_game_line(row, g, markets) if g else None
        else:
            m = match_prop(row, g, markets)
        if not m:
            out["skipped"].append((_label(row), "no Kalshi market for this bet"))
            continue
        matched.append((c, g, m))
    out["matched"] = len(matched)
    if not matched:
        _run_row(conn, now, sport, cfg.mode, out, "nothing matched")
        return out
    try:
        fresh = {m.get("ticker"): m for m in fetch_tickers(sorted({m["ticker"] for _, _, m in matched}))}
    except Exception as exc:                                 # noqa: BLE001
        out["note"] = f"could not read fresh prices: {exc}"
        _run_row(conn, now, sport, cfg.mode, out, out["note"])
        return out
    balance = None
    if cfg.mode == "live" and not dry:
        try:
            client = client or client_for(cfg)
            balance = client.balance_cents()
        except Exception as exc:                             # noqa: BLE001
            out["note"] = f"live mode but the account cannot be reached: {exc}"
            _run_row(conn, now, sport, cfg.mode, out, out["note"])
            return out
    spent, n_today = spent_today(conn, day)
    for c, g, m in matched:
        row = c["row"]
        raw = fresh.get(m["ticker"]) or {}
        verdict, order, note = decide(c, m, raw, cfg, spent, n_today, balance)
        if verdict != "place":
            out["skipped"].append((_label(row), note))
            continue
        cid = str(uuid.uuid5(NAMESPACE, f"{sport}|{c['pick_id']}|{day}|{cfg.mode}|{n_today}"))
        rec = {"client_id": cid, "ts": now.isoformat(timespec="seconds"), "day": day, "mode": cfg.mode,
               "sport": sport, "lane": c["lane"], "pick_id": c["pick_id"], "player": row.get("player"),
               "market": row.get("market"), "side": row.get("side"), "line": row.get("line"),
               "label": _label(row), "ticker": m["ticker"], "k_side": m["k_side"], "count": order["count"],
               "price_cents": order.get("yes_price") or order.get("no_price"), "fee_cents": order["_fee"],
               "cost_cents": order["_cost"], "our_cents": order["_our"], "status": "paper",
               "order_id": "", "note": m["how"], "result": None, "pnl_cents": None, "settled_at": None}
        if dry:
            rec["status"] = "dry"
            out["orders"].append(rec)
            continue
        if cfg.mode == "live":
            body = {k: v for k, v in order.items() if not k.startswith("_")}
            body["client_order_id"] = cid
            body["expiration_ts"] = int(now.timestamp()) + ORDER_TTL_S
            try:
                got = client.create_order(body)
                rec["order_id"] = str(got.get("order_id") or "")
                rec["status"] = str(got.get("status") or "resting")
            except Exception as exc:                         # noqa: BLE001
                rec["status"], rec["note"] = "error", f"{m['how']} — {exc}"
                log(f"  ⚠️  Kalshi order failed for {rec['label']}: {exc}")
        _insert(conn, rec)
        out["orders"].append(rec)
        if rec["status"] not in ("error",):
            out["placed"] += 1
            if cfg.mode == "live":
                spent += rec["cost_cents"]
                n_today += 1
                if balance is not None:
                    balance -= rec["cost_cents"]
    if not dry:
        _run_row(conn, now, sport, cfg.mode, out, "")
    return out


def _insert(conn, rec: dict) -> None:
    cols = ("client_id", "ts", "day", "mode", "sport", "lane", "pick_id", "player", "market", "side", "line",
            "label", "ticker", "k_side", "count", "price_cents", "fee_cents", "cost_cents", "our_cents",
            "status", "order_id", "note", "result", "pnl_cents", "settled_at")
    conn.execute(f"INSERT OR REPLACE INTO orders ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                 tuple(rec.get(k) for k in cols))
    conn.commit()


def _run_row(conn, now, sport, mode, out, note) -> None:
    conn.execute("INSERT INTO runs (ts, sport, mode, considered, matched, placed, note) VALUES (?,?,?,?,?,?,?)",
                 (now.isoformat(timespec="seconds"), sport, mode, out["considered"], out["matched"],
                  out["placed"], note or out.get("note") or ""))
    conn.commit()


# ─── settlement ────────────────────────────────────────────────────────────

def settle_row(rec: dict, market: dict, order: dict | None, now: _dt.datetime) -> dict | None:
    """The updated row, or None when nothing has changed. A live order's
    fill comes from the order itself; the result comes from the market."""
    upd = {}
    filled = rec["status"] in ("executed", "paper")        # paper fills by definition
    if order:
        st = str(order.get("status") or "").lower()
        n_filled = int(order.get("fill_count") or order.get("filled_count") or 0)
        filled = filled or st == "executed" or n_filled > 0
        if st in ("canceled", "cancelled", "expired") and not filled:
            upd["status"] = "expired"
            upd["pnl_cents"], upd["settled_at"] = 0, now.isoformat(timespec="seconds")
            return upd
        if filled and rec["status"] == "resting":
            upd["status"] = "executed"
    status = str(market.get("status") or "").lower()
    result = str(market.get("result") or "").lower()
    if status in ("settled", "finalized", "determined") and result in ("yes", "no"):
        won = result == rec["k_side"]
        count, price, fee = int(rec["count"]), int(rec["price_cents"]), int(rec["fee_cents"])
        if not filled:
            upd.update(status="expired", pnl_cents=0, result=result)
        else:
            upd.update(result=result, pnl_cents=(count * (100 - price) - fee) if won else -(count * price + fee),
                       status="won" if won else "lost")
        upd["settled_at"] = now.isoformat(timespec="seconds")
    return upd or None


def sync(cfg: Config | None = None, conn=None, client: Client | None = None, fetch_tickers=None,
         now: _dt.datetime | None = None, log=print) -> dict:
    """Fills and results for every open row."""
    cfg = cfg or config()
    now = now or _dt.datetime.now(_dt.timezone.utc)
    conn = conn or connect()
    from .sources import kalshi as K
    fetch_tickers = fetch_tickers or (lambda t: K.fetch_markets_by_tickers(t, ttl=300))
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM orders WHERE status IN ('paper','resting','executed')").fetchall()]
    out = {"open": len(rows), "settled": 0, "filled": 0, "expired": 0}
    if not rows:
        return out
    try:
        markets = {m.get("ticker"): m for m in fetch_tickers(sorted({r["ticker"] for r in rows}))}
    except Exception as exc:                                 # noqa: BLE001
        out["note"] = f"could not read the markets: {exc}"
        return out
    if client is None and cfg.mode == "live" and any(r["mode"] == "live" and r["order_id"] for r in rows):
        try:
            client = client_for(cfg)
        except Exception as exc:                             # noqa: BLE001
            log(f"  ⚠️  Kalshi sync: orders not refreshed — {exc}")
    for r in rows:
        order = None
        if client and r["mode"] == "live" and r["order_id"] and r["status"] in ("resting", "executed"):
            try:
                order = client.order(r["order_id"])
            except Exception as exc:                         # noqa: BLE001
                log(f"  ⚠️  Kalshi sync: {r['label']}: {exc}")
        upd = settle_row(r, markets.get(r["ticker"]) or {}, order, now)
        if not upd:
            continue
        sets = ", ".join(f"{k}=?" for k in upd)
        conn.execute(f"UPDATE orders SET {sets} WHERE client_id=?", (*upd.values(), r["client_id"]))
        if upd.get("status") in ("won", "lost"):
            out["settled"] += 1
        elif upd.get("status") == "expired":
            out["expired"] += 1
        elif upd.get("status") == "executed":
            out["filled"] += 1
    conn.commit()
    return out


# ─── reporting ─────────────────────────────────────────────────────────────

def heartbeat(conn=None, cfg: Config | None = None) -> dict:
    """Counts only, for web/data/heartbeat.json (a public file)."""
    cfg = cfg or config()
    out = {"mode": cfg.mode, "pikkit": cfg.pikkit_url or None, "stopped": stopped()}
    if cfg.mode == "off" and conn is None:
        return out                                           # no ledger file for a trader that is off
    try:
        conn = conn or connect()
        day = _today(_dt.datetime.now(_dt.timezone.utc))
        out["today"] = conn.execute("SELECT COUNT(*) FROM orders WHERE day=? AND mode=? AND status NOT IN "
                                    "('error','expired','dry')", (day, cfg.mode)).fetchone()[0]
        out["open"] = conn.execute("SELECT COUNT(*) FROM orders WHERE mode=? AND status IN "
                                   "('paper','resting','executed')", (cfg.mode,)).fetchone()[0]
        w, l = conn.execute("SELECT SUM(status='won'), SUM(status='lost') FROM orders WHERE mode=?",
                            (cfg.mode,)).fetchone()
        out["record"] = f"{int(w or 0)}-{int(l or 0)}"
        last = conn.execute("SELECT ts FROM runs ORDER BY ts DESC LIMIT 1").fetchone()
        out["last_run"] = last[0] if last else None
    except Exception as exc:                                 # noqa: BLE001
        out["error"] = str(exc)
    return out


def report(conn=None, cfg: Config | None = None, limit: int = 25) -> list[str]:
    cfg = cfg or config()
    conn = conn or connect()
    day = _today(_dt.datetime.now(_dt.timezone.utc))
    lines = [f"Kalshi trader — mode {cfg.mode}" + (" — STOPPED" if stopped() else ""),
             f"  lanes {', '.join(cfg.lanes)} · {cfg.contracts} contract(s) a pick · order cap "
             f"{cfg.max_order_cents}c · daily cap {cfg.daily_cap_cents}c · {cfg.max_orders_day} orders a day"
             f" · reserve {cfg.reserve_cents}c · slack {cfg.slack_cents}c"]
    for mode in ("live", "paper"):
        n, cost = conn.execute("SELECT COUNT(*), COALESCE(SUM(cost_cents),0) FROM orders WHERE mode=? AND "
                               "status NOT IN ('error','expired','dry')", (mode,)).fetchone()
        if not n:
            continue
        w, l, pnl = conn.execute("SELECT SUM(status='won'), SUM(status='lost'), COALESCE(SUM(pnl_cents),0) "
                                 "FROM orders WHERE mode=?", (mode,)).fetchone()
        t_n, t_cost = conn.execute("SELECT COUNT(*), COALESCE(SUM(cost_cents),0) FROM orders WHERE mode=? "
                                   "AND day=? AND status NOT IN ('error','expired','dry')", (mode, day)).fetchone()
        lines.append(f"  {mode}: {n} order(s), ${cost / 100:.2f} laid · today {t_n} for ${t_cost / 100:.2f} · "
                     f"record {int(w or 0)}-{int(l or 0)} · P&L ${pnl / 100:+.2f}")
    lines.append("")
    rows = conn.execute("SELECT * FROM orders ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    if not rows:
        lines.append("  no orders yet")
    for r in rows:
        pnl = "" if r["pnl_cents"] is None else f" {r['pnl_cents'] / 100:+.2f}"
        lines.append(f"  {r['ts'][:16]} {r['mode']:5} {r['lane']:6} {r['label'][:38]:38} {r['k_side'].upper():3} "
                     f"{r['count']}×{r['price_cents']}c (we say {r['our_cents']}c) {r['status']:8}{pnl}  {r['ticker']}")
    runs = conn.execute("SELECT * FROM runs ORDER BY ts DESC LIMIT 5").fetchall()
    if runs:
        lines.append("")
        for x in runs:
            lines.append(f"  run {x['ts'][:16]} {x['sport']} {x['mode']}: {x['considered']} considered, "
                         f"{x['matched']} matched, {x['placed']} placed{(' — ' + x['note']) if x['note'] else ''}")
    return lines


# ─── CLI ───────────────────────────────────────────────────────────────────

def _cmd_check(cfg: Config) -> int:
    print(f"mode: {cfg.mode}" + ("  (STOPPED)" if stopped() else ""))
    if not cfg.key_id:
        print("QB_KALSHI_KEY_ID is not set — paper mode needs no key; live does.")
        return 0 if cfg.mode != "live" else 2
    try:
        from .kalshiauth import parse_pem
        pem = load_pem(cfg)
        key = parse_pem(pem)
        print(f"key file: ok ({key['n'].bit_length()}-bit RSA)")
        c = Client(cfg.key_id, pem)
        bal = c.balance_cents()
        print(f"ok — connected; balance ${bal / 100:.2f}")
        if bal < cfg.reserve_cents + cfg.max_order_cents:
            print(f"  note: the balance is under the reserve ({cfg.reserve_cents}c) plus one order; "
                  "live mode would place nothing until it is funded or QB_KALSHI_RESERVE_CENTS is lowered")
        return 0
    except Exception as exc:                                 # noqa: BLE001
        print(f"FAILED — {exc}")
        return 2


def _cmd_series(sport: str) -> int:
    """Which sports series Kalshi lists right now — for QB_KALSHI_PROP_SERIES."""
    from .sources.fetch import fetch_text
    hint = {"nfl": "NFL", "cfb": "NCAAF"}.get(sport, sport.upper())
    try:
        raw = json.loads(fetch_text(f"{API}/series?category=Sports&limit=500", "kalshi_series_sports.json", ttl=0))
    except Exception as exc:                                 # noqa: BLE001
        print(f"could not list series: {exc}")
        return 2
    rows = [s for s in raw.get("series") or [] if hint in str(s.get("ticker") or "").upper()
            or hint in str(s.get("title") or "").upper()]
    for s in sorted(rows, key=lambda s: s.get("ticker") or ""):
        print(f"  {s.get('ticker'):28} {s.get('title', '')}")
    print(f"{len(rows)} series mention {hint}. Player-prop ones go in QB_KALSHI_PROP_SERIES, comma-separated.")
    return 0


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="place the site's picks on Kalshi (paper or live)")
    ap.add_argument("cmd", choices=("check", "run", "sync", "report", "balance", "series", "stop", "go"))
    ap.add_argument("--sport", default=None)
    ap.add_argument("--dry", action="store_true", help="print the plan, write nothing")
    a = ap.parse_args(argv)
    cfg = config()
    if a.cmd == "check":
        return _cmd_check(cfg)
    if a.cmd == "balance":
        try:
            print(f"${client_for(cfg).balance_cents() / 100:.2f}")
            return 0
        except Exception as exc:                             # noqa: BLE001
            print(f"FAILED — {exc}")
            return 2
    if a.cmd == "series":
        return _cmd_series(a.sport or "nfl")
    if a.cmd == "stop":
        STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
        STOP_FILE.write_text(_dt.datetime.now().isoformat(timespec="seconds") + "\n")
        print(f"stopped — nothing will be placed until `go` ({STOP_FILE})")
        return 0
    if a.cmd == "go":
        try:
            STOP_FILE.unlink()
        except FileNotFoundError:
            pass
        print(f"go — mode {cfg.mode}")
        return 0
    if a.cmd == "report":
        for ln in report(cfg=cfg):
            print(ln)
        return 0
    if a.cmd == "sync":
        print(json.dumps(sync(cfg), indent=1))
        return 0
    sports = (a.sport,) if a.sport else cfg.sports
    for sport in sports:
        if sport not in BOARD_FILE:
            print(f"{sport}: no board file known")
            continue
        try:
            out = run_cycle(sport, cfg, dry=a.dry)
        except Exception as exc:                             # noqa: BLE001
            print(f"{sport}: failed — {exc}")
            continue
        print(f"{sport.upper()} — mode {out['mode']}{' (dry)' if a.dry else ''}: {out['considered']} pick(s) "
              f"considered, {out['matched']} matched on Kalshi, {out['placed']} placed"
              + (f" — {out['note']}" if out.get("note") else ""))
        for s, n in (out.get("series") or {}).items():
            print(f"    series {s}: {n}")
        for o in out["orders"]:
            print(f"    {o['status']:8} {o['label'][:40]:40} {o['k_side'].upper():3} {o['count']}×{o['price_cents']}c"
                  f" (fee {o['fee_cents']}c, we say {o['our_cents']}c)  {o['ticker']}  {o['note']}")
        for label, why in out["skipped"]:
            print(f"    skip     {label[:40]:40} {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
