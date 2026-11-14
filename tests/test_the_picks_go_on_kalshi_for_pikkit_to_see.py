"""The Kalshi trader (engine/kalshitrade) and its signer (engine/kalshiauth),
on fixtures — no network, no key file, no money.

Ethan, 2026-10-06: "link the site to a pikkit … account so we can
legitimately track all the bets the site puts in … without actually
placing bets on a sportsbook … maybe the bets we place will be like 20
or 30 cents."

Run directly: `python3 tests/test_the_picks_go_on_kalshi_for_pikkit_to_see.py`
"""
import base64
import datetime as dt
import json
import os
import secrets
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import kalshiauth as A                             # noqa: E402
from engine import kalshitrade as KT                           # noqa: E402

NOW = dt.datetime(2026, 10, 11, 14, 0, tzinfo=dt.timezone.utc)
KICK = "2026-10-11T17:00:00Z"


# ─── a throwaway RSA key, made here so the test needs no library ───────────

def _probable_prime(bits: int) -> int:
    while True:
        # Top two bits set, as OpenSSL does, so two of these multiply to a
        # full 2048-bit modulus (the parser refuses anything shorter).
        n = secrets.randbits(bits) | (3 << (bits - 2)) | 1
        if all(n % p for p in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)) and _miller_rabin(n):
            return n


def _miller_rabin(n: int, rounds: int = 12) -> bool:
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = 2 + secrets.randbelow(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _der_len(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _der_int(v: int) -> bytes:
    b = v.to_bytes((v.bit_length() + 8) // 8, "big")          # leading 0x00 keeps it positive
    return b"\x02" + _der_len(len(b)) + b


def _der_seq(*items: bytes) -> bytes:
    body = b"".join(items)
    return b"\x30" + _der_len(len(body)) + body


def _pem(kind: str, der: bytes) -> str:
    b64 = base64.b64encode(der).decode()
    lines = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
    return f"-----BEGIN {kind}-----\n{lines}\n-----END {kind}-----\n"


def _make_key():
    p, q = _probable_prime(1024), _probable_prime(1024)
    n, e = p * q, 65537
    d = pow(e, -1, (p - 1) * (q - 1))
    pkcs1 = _der_seq(_der_int(0), _der_int(n), _der_int(e), _der_int(d), _der_int(p), _der_int(q),
                     _der_int(d % (p - 1)), _der_int(d % (q - 1)), _der_int(pow(q, -1, p)))
    alg = _der_seq(b"\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x01", b"\x05\x00")
    pkcs8 = _der_seq(_der_int(0), alg, b"\x04" + _der_len(len(pkcs1)) + pkcs1)
    return _pem("RSA PRIVATE KEY", pkcs1), _pem("PRIVATE KEY", pkcs8), {"n": n, "e": e, "d": d}


KEY1, KEY8, KEY = _make_key()


def test_the_signer_reads_both_pem_forms_and_round_trips():
    for pem in (KEY1, KEY8):
        got = A.parse_pem(pem)
        assert got["n"] == KEY["n"] and got["d"] == KEY["d"]
    msg = b"1759800000000GET/trade-api/v2/portfolio/balance"
    sig = A.sign_pure(KEY, msg)
    assert len(sig) == 256 and A.verify_pure(KEY, msg, sig)
    assert not A.verify_pure(KEY, msg + b"x", sig)
    assert not A.verify_pure(KEY, msg, bytes(256))
    # Two signatures of one message differ (random salt) and both verify.
    assert A.sign_pure(KEY, msg) != sig and A.verify_pure(KEY, msg, A.sign_pure(KEY, msg))
    # The public entry point (library or pure) produces something the pure
    # verifier accepts.
    assert A.verify_pure(KEY, msg, A.sign(KEY8, msg))


def test_the_three_headers_sign_timestamp_method_and_path_without_the_query():
    h = A.headers("key-id", KEY8, "get", "/trade-api/v2/portfolio/orders?status=resting", now_ms=1759800000000)
    assert h["KALSHI-ACCESS-KEY"] == "key-id" and h["KALSHI-ACCESS-TIMESTAMP"] == "1759800000000"
    sig = base64.b64decode(h["KALSHI-ACCESS-SIGNATURE"])
    assert A.verify_pure(KEY, b"1759800000000GET/trade-api/v2/portfolio/orders", sig)


def test_a_bad_key_is_refused_plainly():
    for bad, word in (("not a pem", "no PEM"), (_pem("EC PRIVATE KEY", b"\x30\x00"), "unsupported"),
                      (_pem("ENCRYPTED PRIVATE KEY", b"\x30\x00"), "password")):
        try:
            A.parse_pem(bad)
            assert False, bad
        except A.KeyError_ as exc:
            assert word in str(exc)


# ─── the board and Kalshi's markets ────────────────────────────────────────

GAME = {"home": "BUF", "away": "LAC", "date": "2026-10-11", "kickoff": KICK}


def _grow(market, pick, line=None, side="", prob=0.58, tier="top"):
    return {"kind": "game", "player": f"{pick} {market}", "pick_label": f"{pick} {market}", "pick": pick,
            "team": pick, "home": "BUF", "away": "LAC", "market": market, "side": side, "line": line,
            "model_prob": prob, "tier": tier, "kickoff": KICK, "matchup": "LAC @ BUF"}


def _prop(player, market, side, line, prob, tier="strong", **kw):
    return dict(player=player, team="BUF", opponent="LAC", market=market, side=side, line=line,
                model_prob=prob, tier=tier, kickoff=KICK, game="LAC@BUF", **kw)


def _board():
    ml = _grow("moneyline", "BUF", prob=0.60)
    return {
        "games": [GAME],
        "pick_of_the_day": {"pick": ml, "verdict": {"bet": True}},
        "likely_board": {"rows": [
            ml, _grow("spread", "BUF", line=-6.5, prob=0.55), _grow("total", "BUF", line=50.5, side="Under", prob=0.56),
            _prop("Josh Allen", "pass_yds", "OVER", 249.5, 0.60),
            _prop("Khalil Shakir", "receptions", "OVER", 3.5, 0.62, tier="look"),
            _prop("Dalton Kincaid", "rec_yds", "OVER", 40.5, 0.57, injury_status="Questionable"),
        ]},
        "recommendations": [_prop("James Cook", "rush_yds", "OVER", 70.5, 0.57, recommended=True)],
        "most_likely": [ml],
    }


def _m(ticker, event, title, yb, ya, strike=None, status="active", **kw):
    m = {"ticker": ticker, "event_ticker": event, "title": title, "status": status,
         "yes_bid_dollars": yb, "yes_ask_dollars": ya}
    if strike is not None:
        m.update(floor_strike=strike, strike_type="greater")
    m.update(kw)
    return m


MARKETS = {
    "KXNFLGAME": [_m("KXNFLGAME-26OCT11LACBUF-BUF", "KXNFLGAME-26OCT11LACBUF", "Buffalo wins", 0.55, 0.57),
                  _m("KXNFLGAME-26OCT11LACBUF-LAC", "KXNFLGAME-26OCT11LACBUF", "Los Angeles C wins", 0.43, 0.45)],
    "KXNFLSPREAD": [_m("KXNFLSPREAD-26OCT11LACBUF-BUF6", "KXNFLSPREAD-26OCT11LACBUF", "BUF wins by over 6.5", 0.50, 0.52, 6.5),
                    _m("KXNFLSPREAD-26OCT11LACBUF-LAC3", "KXNFLSPREAD-26OCT11LACBUF", "LAC wins by over 3.5", 0.30, 0.33, 3.5)],
    "KXNFLTOTAL": [_m("KXNFLTOTAL-26OCT11LACBUF-50", "KXNFLTOTAL-26OCT11LACBUF", "over 50.5 points", 0.46, 0.48, 50.5)],
    "KXNFLPASSYDS": [_m("KXNFLPASSYDS-26OCT11LACBUF-JALLEN-250", "KXNFLPASSYDS-26OCT11LACBUF",
                        "Josh Allen: 250+ passing yards?", 0.56, 0.58, 249.5)],
}


def fetch_events(series):
    return [{"markets": MARKETS.get(series, [])}]


def fetch_tickers(tickers):
    return [m for ms in MARKETS.values() for m in ms if m["ticker"] in tickers]


def _cfg(**kw):
    base = dict(mode="paper", lanes=("potd", "top", "strong"), prop_series=("KXNFLPASSYDS",))
    base.update(kw)
    return KT.Config(**base)


def _conn():
    d = tempfile.mkdtemp()
    return KT.connect(Path(d) / "k.db")


def test_the_lanes_choose_the_picks_once_each():
    got = KT.candidates(_board(), ("potd", "top", "strong"))
    labels = [(c["lane"], c["row"].get("player")) for c in got]
    assert labels[0] == ("potd", "BUF moneyline"), labels
    assert ("top", "BUF moneyline") not in labels, "the POTD row is not counted twice"
    assert ("strong", "Josh Allen") in labels and ("strong", "Dalton Kincaid") in labels
    assert not any(p == "Khalil Shakir" for _, p in labels), "Worth a look is not in the lanes"
    assert not any(p == "James Cook" for _, p in labels), "the Edge lane is not on"
    assert [c["lane"] for c in KT.candidates(_board(), ("edge",))] == ["edge"]


def test_game_lines_match_the_same_bet_on_the_right_side():
    ms = [m for ms in MARKETS.values() for m in ms]
    got = KT.match_game_line(_grow("moneyline", "BUF"), GAME, ms)
    assert got["ticker"].endswith("-BUF") and got["k_side"] == "yes"
    got = KT.match_game_line(_grow("moneyline", "LAC"), GAME, ms)
    assert got["ticker"].endswith("-LAC") and got["k_side"] == "yes"
    assert KT.match_game_line(_grow("spread", "BUF", line=-6.5), GAME, ms)["k_side"] == "yes"
    got = KT.match_game_line(_grow("spread", "LAC", line=-3.5), GAME, ms)
    assert got["ticker"].endswith("-LAC3") and got["k_side"] == "yes", "LAC -3.5 is YES on LAC by over 3.5"
    assert KT.match_game_line(_grow("spread", "LAC", line=3.5), GAME, ms) is None, "no BUF 3.5 market to be NO on"
    got = KT.match_game_line(_grow("spread", "LAC", line=6.5), GAME, ms)
    assert got["ticker"].endswith("-BUF6") and got["k_side"] == "no", "LAC +6.5 is NO on BUF by over 6.5"
    assert KT.match_game_line(_grow("spread", "BUF", line=-7.0), GAME, ms) is None, "a whole number has no twin"
    assert KT.match_game_line(_grow("total", "BUF", line=50.5, side="Over"), GAME, ms)["k_side"] == "yes"
    assert KT.match_game_line(_grow("total", "BUF", line=50.5, side="Under"), GAME, ms)["k_side"] == "no"
    assert KT.match_game_line(_grow("total", "BUF", line=49.5, side="Over"), GAME, ms) is None
    other = dict(GAME, home="KC", away="DEN")
    assert KT.match_game_line(_grow("moneyline", "KC"), other, ms) is None, "another game's market never matches"


def test_a_prop_matches_the_players_strike_and_nothing_else():
    ms = MARKETS["KXNFLPASSYDS"]
    assert KT.match_prop(_prop("Josh Allen", "pass_yds", "OVER", 249.5, 0.6), GAME, ms)["k_side"] == "yes"
    assert KT.match_prop(_prop("Josh Allen", "pass_yds", "UNDER", 249.5, 0.6), GAME, ms)["k_side"] == "no"
    assert KT.match_prop(_prop("Josh Allen", "pass_yds", "OVER", 274.5, 0.6), GAME, ms) is None
    assert KT.match_prop(_prop("Josh Allen", "rush_yds", "OVER", 249.5, 0.6), GAME, ms) is None
    assert KT.match_prop(_prop("Keon Coleman", "pass_yds", "OVER", 249.5, 0.6), GAME, ms) is None


def test_the_fee_is_kalshis_rounded_up_to_the_cent():
    assert KT.fee_cents(1, 50) == 2 and KT.fee_cents(1, 80) == 2 and KT.fee_cents(1, 99) == 1
    assert KT.fee_cents(10, 50) == 18 and KT.cost_cents(1, 57) == 57 + KT.fee_cents(1, 57)
    assert KT.quotes({"yes_bid_dollars": 0.55, "yes_ask_dollars": 0.57}) == (55, 57)
    assert KT.quotes({"yes_bid": 55, "yes_ask": 57}) == (55, 57)
    assert KT.ask_for("yes", 55, 57) == 57 and KT.ask_for("no", 55, 57) == 45


def test_every_guard_rail_refuses_in_its_own_words():
    cand = {"row": _grow("moneyline", "BUF", prob=0.60), "lane": "top", "pick_id": "x"}
    match = {"ticker": "T", "k_side": "yes", "how": ""}
    raw = MARKETS["KXNFLGAME"][0]
    cfg = _cfg(mode="live")
    v, order, _ = KT.decide(cand, match, raw, cfg, 0, 0, 5000)
    assert v == "place" and order["yes_price"] == 57 and order["count"] == 1 and order["_cost"] == 59
    assert KT.decide(cand, match, raw, cfg, 0, 0, 5000)[2] == ""
    assert "above our" in KT.decide({**cand, "row": _grow("moneyline", "BUF", prob=0.50)}, match, raw, cfg, 0, 0, 5000)[2]
    assert KT.decide({**cand, "row": _grow("moneyline", "BUF", prob=0.55)}, match, raw, _cfg(mode="live", slack_cents=2), 0, 0, 5000)[0] == "place"
    assert "order cap" in KT.decide(cand, match, raw, _cfg(max_order_cents=50), 0, 0, 5000)[2]
    assert "daily cap" in KT.decide(cand, match, raw, _cfg(daily_cap_cents=100), 60, 1, 5000)[2]
    assert "orders today" in KT.decide(cand, match, raw, _cfg(max_orders_day=3), 0, 3, 5000)[2]
    assert "reserve" in KT.decide(cand, match, raw, cfg, 0, 0, 1050)[2]
    assert "wide" in KT.decide(cand, match, dict(raw, yes_bid_dollars=0.40), cfg, 0, 0, 5000)[2]
    assert "market closed" in KT.decide(cand, match, dict(raw, status="closed"), cfg, 0, 0, 5000)[2]
    assert "no price" in KT.decide(cand, match, {"status": "active"}, cfg, 0, 0, 5000)[2]


def test_paper_mode_records_what_live_would_do_and_never_twice():
    conn = _conn()
    out = KT.run_cycle("nfl", _cfg(), board=_board(), now=NOW, fetch_events=fetch_events,
                       fetch_tickers=fetch_tickers, conn=conn)
    assert out["mode"] == "paper" and out["considered"] == 5, out["considered"]
    placed = {o["label"]: o for o in out["orders"]}
    # The moneyline (POTD), the spread, the under and Allen's over; Kincaid is listed, Shakir out of lane.
    assert set(placed) == {"BUF moneyline", "BUF spread", "BUF total", "Josh Allen over 249.5 pass_yds"}, placed
    assert placed["BUF total"]["k_side"] == "no" and placed["BUF total"]["price_cents"] == 54
    assert all(o["status"] == "paper" for o in placed.values())
    assert dict(out["skipped"])["Dalton Kincaid over 40.5 rec_yds"].startswith("listed")
    again = KT.run_cycle("nfl", _cfg(), board=_board(), now=NOW, fetch_events=fetch_events,
                         fetch_tickers=fetch_tickers, conn=conn)
    assert again["placed"] == 0 and again["orders"] == []
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    hb = KT.heartbeat(conn, _cfg())
    assert hb["mode"] == "paper" and hb["open"] == 4 and hb["record"] == "0-0"
    lines = KT.report(conn, _cfg())
    assert any("paper: 4 order(s)" in ln for ln in lines)


def test_a_dry_run_writes_nothing():
    conn = _conn()
    out = KT.run_cycle("nfl", _cfg(), board=_board(), now=NOW, fetch_events=fetch_events,
                       fetch_tickers=fetch_tickers, conn=conn, dry=True)
    assert len(out["orders"]) == 4 and all(o["status"] == "dry" for o in out["orders"])
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_off_and_the_stop_file_place_nothing():
    conn = _conn()
    assert KT.run_cycle("nfl", _cfg(mode="off"), board=_board(), now=NOW, conn=conn)["note"].endswith("is off")
    saved = KT.STOP_FILE
    KT.STOP_FILE = Path(tempfile.mkdtemp()) / "kalshi.STOP"
    try:
        KT.STOP_FILE.write_text("x")
        out = KT.run_cycle("nfl", _cfg(), board=_board(), now=NOW, fetch_events=fetch_events,
                           fetch_tickers=fetch_tickers, conn=conn)
        assert out["placed"] == 0 and "stopped" in out["note"]
    finally:
        KT.STOP_FILE = saved


def test_a_started_game_is_never_placed():
    conn = _conn()
    late = dt.datetime(2026, 10, 11, 17, 1, tzinfo=dt.timezone.utc)
    out = KT.run_cycle("nfl", _cfg(), board=_board(), now=late, fetch_events=fetch_events,
                       fetch_tickers=fetch_tickers, conn=conn)
    assert out["placed"] == 0 and all(why == "game under way" for _, why in out["skipped"])


class FakeKalshi:
    """The authenticated side: a balance, an order book of what was posted."""

    def __init__(self, balance=5000):
        self.balance, self.posted, self.calls = balance, [], []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers))
        assert headers["KALSHI-ACCESS-KEY"] == "kid" and headers["KALSHI-ACCESS-SIGNATURE"]
        path = url.split("/trade-api/v2", 1)[1].split("?")[0]
        if method == "GET" and path == "/portfolio/balance":
            return {"balance": self.balance}
        if method == "POST" and path == "/portfolio/orders":
            o = json.loads(body)
            self.posted.append(o)
            self.balance -= o["count"] * o.get("yes_price", o.get("no_price", 0))
            return {"order": {"order_id": f"ord-{len(self.posted)}", "status": "resting", **o}}
        if method == "GET" and path.startswith("/portfolio/orders/"):
            return {"order": {"order_id": path.rsplit("/", 1)[1], "status": "executed", "fill_count": 1}}
        raise AssertionError(f"unexpected {method} {path}")


def test_live_mode_posts_one_limit_order_a_pick_inside_the_caps_then_settles_it():
    conn = _conn()
    fake = FakeKalshi(balance=5000)
    client = KT.Client("kid", KEY8, opener=fake)
    cfg = _cfg(mode="live", daily_cap_cents=150, reserve_cents=1000)
    out = KT.run_cycle("nfl", cfg, board=_board(), now=NOW, fetch_events=fetch_events,
                       fetch_tickers=fetch_tickers, conn=conn, client=client)
    assert out["placed"] == 2, out              # 59c + 54c fit under 150c; the third would not
    assert any("daily cap" in why for _, why in out["skipped"])
    o = fake.posted[0]
    assert o["ticker"] == "KXNFLGAME-26OCT11LACBUF-BUF" and o["side"] == "yes" and o["type"] == "limit"
    assert o["action"] == "buy" and o["count"] == 1 and o["yes_price"] == 57
    assert o["client_order_id"] and o["expiration_ts"] == int(NOW.timestamp()) + KT.ORDER_TTL_S
    rows = conn.execute("SELECT status, order_id, mode FROM orders").fetchall()
    assert all(r[0] == "resting" and r[1].startswith("ord-") and r[2] == "live" for r in rows)
    # Settled: the game market resolves YES, the spread NO.
    settled = {"KXNFLGAME-26OCT11LACBUF-BUF": {"status": "settled", "result": "yes"},
               "KXNFLSPREAD-26OCT11LACBUF-BUF6": {"status": "settled", "result": "no"}}
    got = KT.sync(cfg, conn, client=client, fetch_tickers=lambda t: [dict(ticker=k, **v) for k, v in settled.items()],
                  now=NOW)
    assert got["settled"] == 2
    by = {r["ticker"]: dict(r) for r in conn.execute("SELECT * FROM orders").fetchall()}
    win = by["KXNFLGAME-26OCT11LACBUF-BUF"]
    assert win["status"] == "won" and win["pnl_cents"] == 100 - 57 - win["fee_cents"]
    loss = by["KXNFLSPREAD-26OCT11LACBUF-BUF6"]
    assert loss["status"] == "lost" and loss["pnl_cents"] == -(52 + loss["fee_cents"])
    assert KT.heartbeat(conn, cfg)["record"] == "1-1"


def test_an_unfilled_live_order_expires_at_no_cost():
    rec = {"status": "resting", "k_side": "yes", "count": 1, "price_cents": 57, "fee_cents": 2}
    upd = KT.settle_row(rec, {"status": "settled", "result": "yes"}, {"status": "canceled", "fill_count": 0}, NOW)
    assert upd["status"] == "expired" and upd["pnl_cents"] == 0
    upd = KT.settle_row(rec, {"status": "active"}, {"status": "executed"}, NOW)
    assert upd == {"status": "executed"}
    assert KT.settle_row(dict(rec, status="paper"), {"status": "active"}, None, NOW) is None


def test_the_config_clamps_every_number_and_names_the_lanes():
    c = KT.config({"QB_KALSHI_MODE": "LIVE", "QB_KALSHI_CONTRACTS": "500", "QB_KALSHI_MAX_ORDER_CENTS": "abc",
                   "QB_KALSHI_LANES": "potd, edge, bogus", "QB_KALSHI_SPORTS": "nfl,cfb",
                   "QB_KALSHI_PROP_SERIES": "kxnflpassyds"})
    assert c.mode == "live" and c.contracts == 10 and c.max_order_cents == 100
    assert c.lanes == ("potd", "edge") and c.sports == ("nfl", "cfb") and c.prop_series == ("KXNFLPASSYDS",)
    assert KT.config({}).mode == "off" and KT.config({"QB_KALSHI_MODE": "sideways"}).mode == "off"


def test_the_launcher_runs_the_trader_after_the_football_boards_and_syncs_on_settle():
    src = (Path(__file__).resolve().parents[1] / "launch.py").read_text()
    assert 'with _isolated("kalshi-trader", board=False): _kalshi_trader(quiet=quiet)' in src
    assert src.index('_note_board("cfb"') < src.index('_kalshi_trader(quiet=quiet)') < src.index('_note_board("mlb"')
    assert '"kalshi": _kalshi_heartbeat(),' in src and "_kt.sync()" in src


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    for name, fn in fns:
        fn()
        print(f"  ok  {name}")
    print(f"\n{len(fns)} tests passed.")
