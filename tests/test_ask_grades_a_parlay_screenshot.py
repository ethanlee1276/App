"""Ask Qellys grades a parlay from its screenshot.

Ethan, 2026-10-12: "add a feature in the ai ask Qellys where users can
upload a screenshot of there parlay and it will rank it based on all our
data and tools and models".

What is pinned, offline, on fixtures (engine/slipgrade.py):

  * the picture is checked before anything is spent — a type the API takes,
    real base64, under the size Caddy lets through, the bytes its type
    starts with;
  * the reader's reply is held to a schema and checked again field by field;
    a leg that does not parse is dropped and counted, never guessed; the
    read is logged like every question; not a slip, or a refusal, is said;
  * every leg is priced from tonight's board the way the board prices it —
    a Most Likely row at its shown chance, a prop at the exact number held
    to the list's own record, a scorer off the touchdown field, a side or a
    total from either side of the board's card;
  * the ticket: different games multiply, one game takes the parlay
    engine's correlation, the payout is the slip's price, the grade is the
    expected return, a leg off our boards stands in at its own break-even,
    the pairs the engine would never build are named, and the weakest leg
    comes with the board's likeliest pick in its game;
  * the live line (engine/sliplive; Ethan: "make sure we are also pulling
    live line for the picks"): every book's price at the slip's number from
    the latest pull, best first, the sharp book a reference only, the
    margin taken out, and when it was pulled; a game under way read off the
    live loop's own scoreboard and box score — an over past its number has
    won, an under past it has lost — and the ticket's standing, where to
    place it, the leg it is better without, the pairs, the alerts;
  * the server gates and counts it as it does a question, before the
    picture is read, and writes the picture nowhere;
  * the page: the attach sheet's upload row, the lazy module, the card.

BROWSER HALF IS OPT-IN (`QB_BROWSER_TESTS=1`), as tests/test_ask_keyboard.py
explains: it uploads a picture through the real page, with the API answered
by a fixture, and reloads to see the card come back.

    QB_BROWSER_TESTS=1 python3 tests/test_ask_grades_a_parlay_screenshot.py
"""
import base64
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The fitted stores belong to the box that fitted them (engine/modelstate);
# these tests price against none, so a test reads the code, not this machine.
_SANDBOX = Path(tempfile.mkdtemp())
os.environ["QB_MODELS_DIR"] = str(_SANDBOX / "models")
os.environ["QB_LIKELY_CAL"] = str(_SANDBOX / "likely_calibration.json")

from engine import explainer as EX                               # noqa: E402
from engine import likely                                        # noqa: E402
from engine import likelycal as LC                               # noqa: E402
from engine import parlays as P                                  # noqa: E402
from engine import slipgrade as SG                               # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text(encoding="utf-8")
SLIP_JS = ROOT / "web" / "js" / "slip.js"
SLIP_CSS = ROOT / "web" / "css" / "slip.css"
SRV = (ROOT / "server.py").read_text(encoding="utf-8")


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _png(w=40, h=20) -> bytes:
    """A real, small, white PNG — no imaging library in the suite."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    rows = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


# ---- the picture -------------------------------------------------------------
def test_the_picture_is_checked_before_anything_is_spent():
    jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
    assert SG.decode_image(_b64(jpeg), "image/jpeg") == jpeg
    assert SG.decode_image("data:image/jpeg;base64," + _b64(jpeg), "IMAGE/JPEG ") == jpeg, \
        "a data: URL and a loosely written type are read, not refused"
    assert SG.decode_image(_b64(_png()), "image/png") == _png()
    webp = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 16
    assert SG.decode_image(_b64(webp), "image/webp") == webp
    assert SG.decode_image(_b64(b"GIF89a" + b"\x00" * 16), "image/gif")

    def refused(data, mt, words):
        try:
            SG.decode_image(data, mt)
        except ValueError as exc:
            assert words in str(exc), (str(exc), words)
            return
        raise AssertionError(f"accepted {mt}")
    refused(_b64(jpeg), "image/heic", "JPEG, PNG, WebP or GIF")
    refused("not base64 at all!", "image/jpeg", "did not arrive whole")
    refused("", "image/jpeg", "empty")
    refused(_b64(jpeg), "image/png", "not the picture it says it is")
    refused(_b64(b"RIFF\x10\x00\x00\x00AVI LIST" + b"\x00" * 8), "image/webp", "not the picture it says it is")
    refused(_b64(b"\xff\xd8\xff" + b"\x00" * SG.MAX_IMAGE_BYTES), "image/jpeg", "too large")
    refused("A" * (SG.MAX_IMAGE_BYTES * 2), "image/jpeg", "too large")
    # The ceiling sits under Caddy's 1MB once base64 and the JSON around it are counted.
    assert SG.MAX_IMAGE_BYTES * 4 / 3 + 200 < 1_000_000


# ---- the read ----------------------------------------------------------------
LEGS = [
    {"sport": "nfl", "player": "Kyren Williams", "team": "", "game": "BUF @ LA", "market": "rush_yds",
     "side": "over", "line": 69.5, "odds": -115, "text": "Kyren Williams Over 69.5 Rushing Yds"},
    {"sport": "nfl", "player": "", "team": "Buffalo Bills", "game": "Bills @ Rams", "market": "moneyline",
     "side": "team", "line": 0, "odds": 120, "text": "Bills ML"},
]


def test_the_reply_is_checked_field_by_field():
    raw = {"is_bet_slip": True, "book": "  FanDuel ", "total_odds": 450, "stake": 10, "legs": LEGS + [
        {"sport": "nfl", "player": "X", "team": "", "game": "", "market": "passing_yards", "side": "over",
         "line": 250.5, "odds": -110, "text": "a market we do not have"},
        {"sport": "nfl", "player": "", "team": "", "game": "", "market": "rec_yds", "side": "over",
         "line": 50.5, "odds": -110, "text": "a prop with nobody on it"},
        {"sport": "nfl", "player": "Josh Allen", "team": "BUF", "game": "", "market": "moneyline",
         "side": "team", "line": 0, "odds": 120, "text": "a game line with a player on it"},
        {"sport": "nfl", "player": "Kyren Williams", "team": "", "game": "", "market": "anytime_td",
         "side": "over", "line": 0.5, "odds": 110, "text": "a scorer read as over"},
        {"sport": "nfl", "player": "A", "team": "", "game": "", "market": "rec_yds", "side": "over",
         "line": float("nan"), "odds": 50, "text": "no number"},
        "not a leg",
    ]}
    got = SG.clean_slip(raw)
    assert got["is_bet_slip"] and got["book"] == "FanDuel" and got["total_odds"] == 450 and got["stake"] == 10
    assert [l["text"] for l in got["legs"]] == [l["text"] for l in LEGS] and got["dropped"] == 6
    many = SG.clean_slip({"is_bet_slip": True, "legs": [dict(LEGS[0]) for _ in range(SG.MAX_LEGS + 3)]})
    assert len(many["legs"]) == SG.MAX_LEGS and many["dropped"] == 3
    odd = SG.clean_slip({"is_bet_slip": True, "total_odds": 50, "legs": [dict(LEGS[0], odds=-99)]})
    assert odd["total_odds"] == 0 and odd["legs"][0]["odds"] == 0, "a price under 100 is no price"
    assert not SG.clean_slip({"is_bet_slip": True, "legs": []})["is_bet_slip"], "no legs, no slip"
    assert not SG.clean_slip(None)["is_bet_slip"]


class BadRequestError(Exception):
    """Named as the SDK names a 400."""


class APIConnectionError(Exception):
    pass


class Fake:
    """The SDK's client, as far as read_slip touches it."""

    def __init__(self, reply, first=None, stop="end_turn"):
        self.reply, self.first, self.stop, self.calls = reply, first, stop, []
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        if self.first is not None and len(self.calls) == 1:
            raise self.first
        block = (types.SimpleNamespace(type="tool_use", name="slip", input=self.reply) if "tools" in kw
                 else types.SimpleNamespace(type="text", text=json.dumps(self.reply)))
        return types.SimpleNamespace(content=[block], stop_reason=self.stop,
                                     usage=types.SimpleNamespace(input_tokens=1600, output_tokens=240))


def test_the_read_is_held_to_the_schema_and_logged():
    logged = []
    fake = Fake({"is_bet_slip": True, "book": "DraftKings", "total_odds": 450, "stake": 5, "legs": LEGS})
    img = _png()
    slip = SG.read_slip(img, "image/png", client=fake, model="claude-sonnet-5",
                        log=lambda m, r: logged.append((m, r)))
    assert len(fake.calls) == 1
    kw = fake.calls[0]
    assert kw["model"] == "claude-sonnet-5" and kw["system"] == SG.SYSTEM and kw["max_tokens"] == SG.MAX_TOKENS
    assert kw["output_config"]["format"] == {"type": "json_schema", "schema": SG.SCHEMA}
    assert kw["output_config"]["effort"] == "low", "a model that takes effort reads at low"
    pic = kw["messages"][0]["content"][0]
    assert pic["type"] == "image" and pic["source"] == {"type": "base64", "media_type": "image/png",
                                                        "data": _b64(img)}
    assert logged and logged[0][0] == "claude-sonnet-5", "the read is logged like every question"
    assert slip["book"] == "DraftKings" and len(slip["legs"]) == 2
    no_effort = Fake({"is_bet_slip": True, "legs": LEGS})
    SG.read_slip(img, "image/png", client=no_effort, model="claude-haiku-4-5", log=lambda m, r: None)
    assert "effort" not in no_effort.calls[0]["output_config"]


def test_an_sdk_or_model_without_the_schema_gets_it_as_a_forced_tool():
    for first in (TypeError("unexpected keyword argument 'output_config'"), BadRequestError("400")):
        fake = Fake({"is_bet_slip": True, "legs": LEGS}, first=first)
        slip = SG.read_slip(_png(), "image/png", client=fake, model="claude-sonnet-5", log=lambda m, r: None)
        second = fake.calls[1]
        assert "output_config" not in second and second["tool_choice"] == {"type": "tool", "name": "slip"}
        assert second["tools"][0]["input_schema"] == SG.SCHEMA
        assert len(slip["legs"]) == 2


def test_not_a_slip_a_refusal_and_a_dead_line_are_said_not_guessed():
    for fake in (Fake({"is_bet_slip": False, "legs": []}),
                 Fake({"is_bet_slip": True, "legs": [{"market": "nonsense"}]}),
                 Fake({"is_bet_slip": True, "legs": LEGS}, stop="refusal")):
        try:
            SG.read_slip(_png(), "image/png", client=fake, model="claude-sonnet-5", log=lambda m, r: None)
        except SG.SlipUnreadable as exc:
            assert str(exc)
            continue
        raise AssertionError("a picture with no slip on it was graded")
    try:
        SG.read_slip(_png(), "image/png", client=Fake({}, first=APIConnectionError("down")),
                     model="claude-sonnet-5", log=lambda m, r: None)
    except EX.Unavailable:
        pass
    else:
        raise AssertionError("an API failure must be Unavailable, as Ask's are")


# ---- pricing -----------------------------------------------------------------
def _rec(player, team, opp, market, side, line, odds, proj, sd, vals):
    return {"player": player, "team": team, "opponent": opp, "market": market, "side": side, "line": line,
            "odds": odds, "projection": proj, "proj_std": sd, "recent_values": vals}


KYREN_CONTEXT = {
    "proj_low": 41.0, "proj_high": 123.0, "has_market": True, "fair_prob": 0.53,
    "matchup_card": {"text": "BUF allow 128 rushing yards to RBs a game, the 4th-most (league 104), over 4 games"},
    "chain": {"steps": [{"key": "matchup", "label": "Matchup", "mult": 1.06, "why": ""},
                        {"key": "usage", "label": "Usage", "mult": 1.08, "why": "Takes 71% of the carries"},
                        {"key": "weather", "label": "Weather", "mult": 1.0, "why": "Dome"}]},
    "game_script": {"line": "LA by 3.5 at 54.5", "lean": "favored in a shootout"},
    "warnings": ["Edge too small (+0.0%)", "Carried from 2025: 16 games last season"],
    "injury_status": "Questionable",
    "mate_card": {"headline": "Puka Nacua out — 29% of the targets to go around"},
    "logs": [{"week": 5, "opponent": "SF", "value": 80}, {"week": 14, "opponent": "BUF", "value": 88},
             {"week": 3, "opponent": "BUF", "value": 61}],
    # Every book's number, as apply_odds_to_slate leaves it on the private board:
    # the main line from each book, and the ladder Ask's copy drops.
    "all_lines": [{"book": "DraftKings", "line": 69.5, "over_odds": -115, "under_odds": -105},
                  {"book": "FanDuel", "line": 69.5, "over_odds": -108, "under_odds": -112},
                  {"book": "Pinnacle", "line": 69.5, "over_odds": -104, "under_odds": -116},
                  {"book": "proxy", "line": 69.5, "over_odds": -110, "under_odds": -110}],
    "alt_lines": [{"book": "DraftKings", "line": 59.5, "over_odds": -170, "under_odds": 135}],
    "ripples": [{"out": "Tutu Atwell", "measured": False, "delta": None, "text": "Tutu Atwell out — not measured"},
                {"out": "Puka Nacua", "measured": True, "delta": 0.031,
                 "text": "Puka Nacua out — over his 6 missed games, Williams's share of the carries rose 3.1%"}],
}
# The market's own numbers, the way betting.Recommendation writes them: the
# sharp book's de-vigged chance for the row's side, and the field's median
# de-vigged chance for the OVER across the books quoting the same number.
COOK_MARKET = {"has_market": True, "sharp_anchored": True, "sharp_fair": 0.56, "fair_prob": 0.51,
               "fair_consensus": 0.47, "consensus_books": 5}
# What the one Most Likely board writes on a seated pick (likelyboard.build).
PUKA_SEAT = {
    "checks": {"model": True, "matchup": True, "market": None, "record": True},
    "check_notes": {"model": "our chance 77% (the bar here is 60%)", "matchup": "BUF soft against WRs",
                    "market": "no book price to compare", "record": "picks like this hit 74% of 212 when we said 76%"},
    "case_lines": ["BUF allow 7.1 catches a game to WRs, the 3rd-most", "Takes 29% of the targets"],
    "scout_notes": ["A catches over with his team favoured in a shootout"],
    "milestone_note": "4 catches from 400 in his career",
}

BOARD = {
    "games": [{"home": "LA", "away": "BUF", "home_ml": -140, "away_ml": 120, "date": "2026-10-12", "kickoff": "16:25",
               # Kalshi + Polymarket on the board's own bets (engine/crowd), the opener
               # (engine/lineopen) and the exchange money (engine/moneysplit).
               "crowd": {"kalshi": 0.60, "polymarket": 0.62, "crowd": 0.61, "books": 0.57,
                         "spread_home_line": -2.5, "kalshi_home_cover": 0.52, "poly_home_cover": 0.50,
                         "total_line": 47.5, "poly_over": 0.58},
               "line_open": {"spread_home": -1.5, "total": 46.5, "home_ml": -120, "away_ml": 100,
                             "spread_move": -1.0, "total_move": 1.0,
                             "against_money": {"toward": "home", "money_on": "away", "money_share": 0.64,
                                               "delta": -1.0}},
               "money": {"ml": {"home": 0.41, "away": 0.59, "usd": 48210, "n": 300},
                         "spread": {"home": 0.36, "away": 0.64, "line": -2.5, "usd": 12000, "n": 80},
                         "total": {"over": 0.70, "under": 0.30, "line": 47.5, "usd": 9000, "n": 50},
                         "venues": ["Kalshi", "Polymarket"]}},
              {"home": "KC", "away": "DEN"}],
    "scan_reads": {"BUF@LA": {"players": [
        {"player": "Kyren Williams", "label": "Good matchup",
         "pro": ["Takes 71% of the carries", "BUF gives up the 4th-most rushing yards to RBs"],
         "con": ["<b>LA</b> trail late"]}]}},
    "game_plans": [{"home": "LA", "away": "BUF", "script": {
        "archetype": "Everyone eats", "read": "High total, close spread."}}],
    "recommendations": [
        dict(_rec("Kyren Williams", "LA", "BUF", "rush_yds", "Over", 69.5, -115, 82.0, 18.0, [80, 75, 90, 85, 70]),
             **KYREN_CONTEXT),
        _rec("Josh Allen", "BUF", "LA", "pass_att", "Over", 32.5, -110, 33.0, 5.0, [31, 35, 30, 34]),
        dict(_rec("James Cook", "BUF", "LA", "rush_yds", "Under", 70.5, -110, 62.0, 16.0, [60, 55, 71, 64]),
             **COOK_MARKET),
        _rec("Patrick Mahomes", "KC", "DEN", "pass_yds", "Over", 255.5, -115, 271.0, 45.0, [280, 240, 300]),
        _rec("Keenan Allen", "CHI", "GB", "receptions", "Over", 4.5, -120, 5.1, 1.8, [5, 6, 4]),
        _rec("Josh Allen", "BUF", "LA", "rush_yds", "Over", 30.5, -110, 33.0, 14.0, [30, 41, 22]),
        _rec("Davante Adams", "LA", "BUF", "receptions", "Over", 4.5, -125, 5.2, 1.7, [5, 4, 6]),
        dict(_rec("Puka Nacua", "LA", "BUF", "receptions", "Over", 5.5, -140, 6.4, 1.9, [7, 6, 8, 5]),
             all_lines=[{"book": "FanDuel", "line": 5.5, "over_odds": -135, "under_odds": 105},
                        {"book": "DraftKings", "line": 5.5, "over_odds": -150, "under_odds": 120}]),
    ],
    # When the last paid pulls were made (nfl_build: odds_status, epoch seconds).
    "odds_status": {"priced_at": 1760283000, "lines_priced_at": 1760284800},
    "likely_board": {"rows": [
        {"kind": "prop", "player": "Puka Nacua", "team": "LA", "opponent": "BUF", "market": "receptions",
         "side": "Over", "line": 5.5, "odds": -140, "model_prob": 0.7712, "tier": "top", "tier_label": "Top pick",
         **PUKA_SEAT},
        {"kind": "prop", "player": "Davante Adams", "team": "LA", "opponent": "BUF", "market": "rec_yds",
         "side": "Over", "line": 49.5, "odds": -120, "model_prob": 0.66, "tier": "look", "tier_label": "Worth a look",
         # likelyboard.REAL_RATE_TIERS: the page prints this in place of our 66%.
         "tier_rate": 0.58, "tier_n": 140},
    ]},
    "td_field": [{"player": "Kyren Williams", "team": "LA", "opponent": "BUF", "market": "anytime_td",
                  "model_prob": 0.48, "odds": 110, "implied_total": 29.0, "rz_chances": 2.4,
                  "goal_line_text": "Takes 80% of the goal-line carries"}],
    "game_bets": [
        {"bet_type": "moneyline", "market": "moneyline", "home": "LA", "away": "BUF", "team": "LA", "pick": "LA",
         "pick_is_home": True, "pick_label": "LA ML", "side": "", "line": 0.0, "win_prob": 0.58, "odds": -140,
         "home_odds": -140, "away_odds": 120, "reasons": ["Power rating: LA +4.1 vs BUF +2.0"],
         "fair_prob": 0.57, "has_market": True, "home_book": "FanDuel", "away_book": "DraftKings", "book": "FanDuel"},
        {"bet_type": "total", "market": "total", "home": "LA", "away": "BUF", "team": "", "side": "Over",
         "line": 47.5, "pick_label": "Over 47.5", "win_prob": 0.55, "odds": -110, "other_odds": -105,
         "fair_prob": 0.52, "has_market": True, "over_book": "BetMGM", "under_book": "Caesars"},
        {"bet_type": "spread", "market": "spread", "home": "LA", "away": "BUF", "team": "LA", "side": "",
         "line": -2.5, "pick_label": "LA -2.5", "win_prob": 0.53, "odds": -110, "other_odds": -108,
         "fair_prob": 0.50, "has_market": True, "home_book": "FanDuel", "away_book": "BetMGM"},
    ],
}
BOARDS = {"nfl": BOARD}


def _leg(**kw):
    base = {"sport": "nfl", "player": "", "team": "", "game": "", "market": "rush_yds", "side": "over",
            "line": 0.0, "odds": 0, "text": ""}
    base.update(kw)
    return base


def _rec_of(player, market):
    return next(r for r in BOARD["recommendations"] if r["player"] == player and r["market"] == market)


def test_a_leg_the_most_likely_board_seats_reads_its_shown_chance():
    got = SG.price_leg(BOARDS, _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150))
    assert got["found"] == "likely" and got["prob"] == 0.7712 and got["tier"] == "Top pick"
    assert abs(got["needs"] - 150 / 250) < 1e-9, "what the slip's own price needs"
    assert got["verdict"] == "strong" and got["game"] == "BUF @ LA" and got["team"] == "LA"
    other = SG.price_leg(BOARDS, _leg(player="Puka Nacua", market="receptions", side="over", line=6.5))
    assert other["found"] != "likely", "another number is not the seated pick"


def test_a_worth_a_look_pick_reads_the_tiers_real_rate_as_the_page_does():
    """likelyboard.REAL_RATE_TIERS: on the tier that claims more than it
    hits, the Most Likely card prints the tier's real hit rate in place of
    our chance (app.js: `tier_rate != null ? tier_rate : model_prob`). The
    grade reads the number the page shows, and so does the swap."""
    got = SG.price_leg(BOARDS, _leg(player="Davante Adams", market="rec_yds", side="over", line=49.5, odds=-120))
    assert got["found"] == "likely" and got["prob"] == 0.58 and got["tier"] == "Worth a look"
    assert "tier_rate != null ? Number(r.tier_rate) : Number(r.model_prob || 0)" in APP, \
        "the page's own rule, which the grade copies"
    weak = _leg(player="Josh Allen", market="pass_att", side="over", line=32.5, odds=-120)
    strong = _leg(player="Kyren Williams", market="rush_yds", side="over", line=59.5, odds=-200)
    seated = _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-140)
    swap = SG.grade({"legs": [strong, weak, seated]}, BOARDS)["swap"]
    assert swap["player"] == "Davante Adams" and swap["prob"] == 0.58 and swap["tier"] == "Worth a look"


def test_a_prop_is_priced_at_the_slips_exact_number():
    got = SG.price_leg(BOARDS, _leg(player="Kyren Williams", market="rush_yds", side="over", line=59.5))
    want = likely._prob_at(_rec_of("Kyren Williams", "rush_yds"), "rush_yds", "over", 59.5)
    assert got["found"] == "prop" and got["prob"] == want and want > 0.75
    assert got["needs"] is None and got["verdict"] in ("strong", "fair"), \
        "an alternate number with no printed price has nothing to clear but our chance"
    main = SG.price_leg(BOARDS, _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5))
    assert abs(main["needs"] - 115 / 215) < 1e-9, "the main number borrows the board's price"


def test_an_initial_finds_the_one_player_it_can_mean_and_no_other():
    got = SG.price_leg(BOARDS, _leg(player="J. Allen", market="pass_att", side="over", line=32.5))
    assert got["found"] == "prop" and got["player"] == "Josh Allen"
    assert SG.price_leg(BOARDS, _leg(player="K. Allen", market="receptions", side="over", line=4.5))["player"] \
        == "Keenan Allen"
    assert SG.price_leg(BOARDS, _leg(player="Allen", market="pass_att", side="over", line=32.5))["found"] == "prop"
    two = {"nfl": dict(BOARD, recommendations=BOARD["recommendations"] + [
        _rec("Jalen Allen", "NYJ", "MIA", "pass_att", "Over", 30.5, -110, 31.0, 5.0, [30, 31, 29])])}
    assert SG.price_leg(two, _leg(player="J. Allen", market="pass_att", side="over", line=32.5))["prob"] is None, \
        "two J. Allens is a guess, and a guess is not graded"
    assert SG.price_leg(two, _leg(player="J. Allen", team="BUF", market="pass_att", side="over",
                                  line=32.5))["player"] == "Josh Allen", "the slip's team settles it"
    assert SG.price_leg(BOARDS, _leg(player="Jordan Allen", market="pass_att", side="over",
                                     line=32.5))["prob"] is None, "a full first name that matched nobody is somebody else"


def test_a_prop_off_the_list_is_held_to_the_lists_record():
    leg = _leg(player="James Cook", market="rush_yds", side="under", line=70.5, odds=-110)
    raw = likely._prob_at(_rec_of("James Cook", "rush_yds"), "rush_yds", "under", 70.5)
    assert SG.price_leg(BOARDS, leg)["prob"] == raw, "no fitted record: the number stands"
    Path(os.environ["QB_LIKELY_CAL"]).write_text(json.dumps({"nfl": {"groups": {
        "list|under": {"k": 0.5, "n": 80, "hit": 0.49, "claimed": 0.63}}}}))
    try:
        got = SG.price_leg(BOARDS, leg)
        q = LC.price_chance(-110)
        assert got["prob"] == round(LC.shrink(raw, q, 0.5), 4) < raw, "pulled half way to the price"
        over = SG.price_leg(BOARDS, _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5))
        assert over["prob"] == likely._prob_at(_rec_of("Kyren Williams", "rush_yds"), "rush_yds", "over", 69.5), \
            "the overs earned no correction and get none"
    finally:
        os.unlink(os.environ["QB_LIKELY_CAL"])


def test_a_scorer_reads_the_touchdown_field():
    yes = SG.price_leg(BOARDS, _leg(player="Kyren Williams", market="anytime_td", side="yes", line=0.5, odds=120))
    assert yes["found"] == "scorer" and yes["prob"] == 0.48 and abs(yes["needs"] - 100 / 220) < 1e-9
    no = SG.price_leg(BOARDS, _leg(player="Kyren Williams", market="anytime_td", side="no", line=0.5))
    assert abs(no["prob"] - 0.52) < 1e-9 and no["needs"] is None, "his yes price is not the no's"


def test_sides_and_totals_read_the_card_from_either_side():
    ml = SG.price_leg(BOARDS, _leg(team="Buffalo Bills", game="Bills @ Rams", market="moneyline", side="team"))
    assert abs(ml["prob"] - 0.42) < 1e-9 and abs(ml["needs"] - 100 / 220) < 1e-9 and ml["team"] == "BUF"
    assert ml["verdict"] == "weak" and ml["game"] == "BUF @ LA"
    fav = SG.price_leg(BOARDS, _leg(team="Rams", market="moneyline", side="team"))
    assert fav["prob"] == 0.58 and abs(fav["needs"] - 140 / 240) < 1e-9
    under = SG.price_leg(BOARDS, _leg(game="BUF @ LA", market="total", side="under", line=47.5))
    assert abs(under["prob"] - 0.45) < 1e-9 and abs(under["needs"] - 105 / 205) < 1e-9
    assert SG.price_leg(BOARDS, _leg(game="BUF @ LA", market="total", side="under", line=48.5))["prob"] is None
    dog = SG.price_leg(BOARDS, _leg(team="BUF", market="spread", side="team", line=2.5, odds=-110))
    assert abs(dog["prob"] - 0.47) < 1e-9 and dog["team"] == "BUF"
    assert SG.price_leg(BOARDS, _leg(team="BUF", market="spread", side="team", line=3.5))["prob"] is None
    lac = SG.price_leg(BOARDS, _leg(team="LA Chargers", market="moneyline", side="team", odds=-150))
    assert lac["prob"] is None and lac["verdict"] == "unpriced", "the Chargers are never the Rams"


# ---- the ticket --------------------------------------------------------------
def test_different_games_multiply_and_one_game_takes_the_engines_correlation():
    a = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    b = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    c = _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-140)
    pa, pb, pc = (SG.price_leg(BOARDS, x) for x in (a, b, c))
    apart = SG.grade({"legs": [a, b]}, BOARDS)
    assert abs(apart["ours"] - round(pa["prob"] * pb["prob"], 4)) < 1e-4
    together = SG.grade({"legs": [a, c]}, BOARDS)
    rel = P.relate("nfl", SG._relation_leg(pa), SG._relation_leg(pc))
    assert abs(together["ours"] - round(P.joint_two(pa["prob"], pc["prob"], rel.rho), 4)) < 1e-4
    assert together["n_legs"] == 2 and together["n_priced"] == 2


def test_joint_k_is_joint_three_at_three_and_independence_at_zero():
    ps = [0.7, 0.6, 0.55]
    assert abs(SG.joint_k(ps, 0.2) - P.joint_three(tuple(ps), (0.2, 0.2, 0.2))) < 2e-3
    assert abs(SG.joint_k(ps + [0.8], 0.0) - math.prod(ps + [0.8])) < 1e-3
    assert SG.joint_k(ps, 0.3) > math.prod(ps), "legs pulling together win together more often"


def test_the_payout_the_grade_and_the_legs_off_our_boards():
    a = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    b = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    card = SG.grade({"legs": [a, b], "total_odds": 260}, BOARDS)
    assert abs(card["needs"] - round(1 / 3.6, 4)) < 1e-4, "the slip's printed price"
    assert abs(card["ev"] - round(card["ours"] * 3.6 - 1, 4)) < 2e-4
    assert card["grade"] == SG.letter(card["ev"]) and "*" not in card["grade"]
    product = SG.grade({"legs": [a, b]}, BOARDS)
    assert abs(product["needs"] - round(1 / (SG.to_decimal(-115) ** 2), 4)) < 1e-4, "else its legs' prices multiplied"
    off = _leg(player="Somebody Else", market="rec_yds", side="over", line=40.5, odds=150)
    starred = SG.grade({"legs": [a, b, off], "total_odds": 900}, BOARDS)
    two = SG.grade({"legs": [a, b]}, BOARDS)["ours"]
    assert abs(starred["ours"] - round(two * 0.4, 4)) < 1e-4, "an unpriced leg counts at its own break-even"
    assert starred["grade"].endswith("*") and starred["n_priced"] == 2
    assert starred["legs"][-1]["verdict"] == "unpriced", "ranked last"
    blind = SG.grade({"legs": [a, dict(off, odds=0)]}, BOARDS)
    assert blind["ours"] is None and blind["ev"] is None and blind["grade"] == "?", \
        "a leg with no price and no number of ours leaves nothing to grade by"
    assert [SG.letter(x) for x in (0.12, 0.01, -0.10, -0.2, -0.5, None)] == ["A", "B", "C", "D", "F", "?"]


def test_pairs_the_engine_would_never_build_are_named():
    bills = _leg(team="Buffalo Bills", market="moneyline", side="team", odds=120)
    rams = _leg(team="Rams", market="moneyline", side="team", odds=-140)
    dog = _leg(team="BUF", market="spread", side="team", line=2.5, odds=-110)
    both = SG.grade({"legs": [bills, rams]}, BOARDS)
    assert both["notes"] and both["notes"][0]["kind"] == "kill"
    twice = SG.grade({"legs": [bills, dog]}, BOARDS)
    assert twice["notes"] and twice["notes"][0]["kind"] == "duplicate"


def test_the_weakest_leg_comes_with_the_boards_likeliest_pick_in_its_game():
    weak = _leg(player="Josh Allen", market="pass_att", side="over", line=32.5, odds=-120)
    strong = _leg(player="Kyren Williams", market="rush_yds", side="over", line=59.5, odds=-200)
    card = SG.grade({"legs": [strong, weak]}, BOARDS)
    assert card["weakest"] == "Josh Allen over 32.5 pass attempts"
    assert card["swap"]["player"] == "Puka Nacua" and card["swap"]["prob"] == 0.7712
    seated = _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-140)
    card = SG.grade({"legs": [strong, weak, seated]}, BOARDS)
    assert card["swap"]["player"] == "Davante Adams", "never a bet already on the ticket"
    text = SG.summary(card)
    assert text.startswith("Graded parlay, 3 legs (3 on our boards).") and len(text) <= 1600
    assert "Weakest leg: Josh Allen over 32.5 pass attempts." in text
    assert all("row" not in l for l in card["legs"]), "the board's rows stay home"


# ---- the facts behind each leg ------------------------------------------------
def _facts(leg):
    got = SG.price_leg(BOARDS, leg)
    return {f["k"]: f["t"] for f in SG.why(BOARDS, got)}


def test_every_leg_carries_the_boards_own_facts_defence_and_offence():
    f = _facts(_leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115))
    assert f["Projection"] == "We project 82 (likely range 41–123) against 69.5"
    assert f["Recent games"] == "Cleared 69.5 in 5 of his last 5 (80, 75, 90, 85, 70, latest first)"
    assert f["Defense"].startswith("BUF allow 128 rushing yards to RBs") and f["Defense"].endswith("our number ×1.06 for it")
    assert f["Usage"] == "×1.08 — Takes 71% of the carries", "the projection step that moved him most"
    assert "Weather" not in f, "a step that moved nothing is not a reason"
    assert f["Game script"] == "LA by 3.5 at 54.5 — favored in a shootout"
    assert f["Matchup read"] == ("Good matchup · Takes 71% of the carries; BUF gives up the 4th-most rushing "
                                 "yards to RBs · against: <b>LA</b> trail late")
    assert f["Around him"].startswith("Puka Nacua out") and f["Status"] == "Listed Questionable"
    assert f["Watch"].startswith("Carried from 2025"), "the Edge board's grade notes stay off a parlay"
    assert f["The books"] == "Their own price, the margin taken out, says 53%"
    under = _facts(_leg(player="Kyren Williams", market="rush_yds", side="under", line=69.5, odds=-105))
    assert under["Recent games"].startswith("Stayed under 69.5 in 0 of his last 5")
    assert under["The books"].endswith("says 47%"), "the other side of the book's own number"
    alt = _facts(_leg(player="Kyren Williams", market="rush_yds", side="over", line=59.5))
    assert "The books" not in alt, "the book's price is for its own number, not an alternate"


def test_scorers_and_game_lines_carry_their_own_facts():
    td = _facts(_leg(player="Kyren Williams", market="anytime_td", side="yes", line=0.5, odds=120))
    assert td["Game"] == "LA expected to score 29" and td["Red zone"] == "2.4 red-zone chances expected this week"
    assert td["Goal line"] == "Takes 80% of the goal-line carries"
    ml = _facts(_leg(team="Rams", market="moneyline", side="team", odds=-140))
    assert ml["Our model"] == "Power rating: LA +4.1 vs BUF +2.0"
    assert ml["Game script"] == "Everyone eats. High total, close spread."
    assert SG.why(BOARDS, SG.price_leg(BOARDS, _leg(player="Somebody Else", market="rec_yds", side="over",
                                                     line=40.5))) == [], "no number of ours, no facts of ours"


def test_a_prop_carries_his_log_against_this_defence_and_the_teammates_out():
    f = _facts(_leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115))
    assert f["Against BUF"] == "88, 61 in his log against them (cleared 69.5 in 1 of 2)"
    assert f["Lineup"].startswith("Puka Nacua out — over his 6 missed games"), "measured ripples only"
    assert "not measured" not in " ".join(f.values())


def test_the_books_line_reads_the_sharp_book_and_the_field_the_right_way_round():
    under = _facts(_leg(player="James Cook", market="rush_yds", side="under", line=70.5, odds=-110))
    assert under["The books"] == ("The sharp book's price, the margin taken out, says 56%; "
                                  "5 books at this number together say 53%"), \
        "the sharp number is the row's side; the field's is the over's"
    over = _facts(_leg(player="James Cook", market="rush_yds", side="over", line=70.5, odds=-110))
    assert over["The books"] == ("The sharp book's price, the margin taken out, says 44%; "
                                 "5 books at this number together say 47%")
    assert "The books" not in _facts(_leg(player="James Cook", market="rush_yds", side="under", line=65.5)), \
        "the market's number is for its own line"


def test_a_seated_pick_carries_the_case_the_record_the_checks_and_the_scout():
    seated = SG.price_leg(BOARDS, _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150))
    assert [x["t"] for x in SG.why(BOARDS, seated) if x["k"] == "The case"] == [
        "BUF allow 7.1 catches a game to WRs, the 3rd-most", "Takes 29% of the targets"]
    f = _facts(_leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150))
    assert f["Our record"] == "Picks like this hit 74% of 212 when we said 76%", "the record check's own words"
    assert f["Checks"] == "Passes 3 of our 4 checks (model, matchup, record); market: no book price to compare"
    assert f["Scout"] == "A catches over with his team favoured in a shootout"
    assert f["Milestone"] == "4 catches from 400 in his career"
    look = _facts(_leg(player="Davante Adams", market="rec_yds", side="over", line=49.5, odds=-120))
    assert look["Our record"] == "Our Worth a look tier has hit 58% of 140 settled", "the tier's real rate, where shown"
    other = _facts(_leg(player="Puka Nacua", market="receptions", side="over", line=6.5, odds=120))
    assert other["Projection"] == "We project 6.4 against 6.5", "priced off his prop row at the slip's number"
    assert "Our record" not in other and "Checks" not in other and "The case" not in other, \
        "the record and the checks are the seated number's, not another's"
    assert other.get("Scout") == f["Scout"], "the scout's note is about the side, so it rides any of his lines"


def test_a_side_or_total_carries_the_books_the_crowd_the_move_and_the_money():
    rams = _facts(_leg(team="Rams", market="moneyline", side="team", odds=-140))
    assert rams["The books"] == "Their own price, the margin taken out, says 57%"
    assert rams["Prediction markets"] == "Kalshi and Polymarket traders put LA at 61% to win"
    assert rams["Line move"] == "LA opened -120, now -140"
    assert rams["Money"] == "41% of the $48,210 traded on Kalshi and Polymarket is on LA"
    bills = _facts(_leg(team="Buffalo Bills", market="moneyline", side="team", odds=120))
    assert bills["The books"].endswith("says 43%") and bills["Prediction markets"].endswith("BUF at 39% to win")
    assert bills["Line move"] == "BUF opened +100, now +120" and bills["Money"].startswith("59% of")
    fav = _facts(_leg(team="Rams", market="spread", side="team", line=-2.5, odds=-110))
    assert fav["Prediction markets"] == "Kalshi and Polymarket traders put LA -2.5 at 51%"
    assert fav["Line move"] == "LA opened -1.5, now -2.5 — toward LA with 64% of the money on BUF"
    assert fav["Money"] == "36% of the $12,000 traded on Kalshi and Polymarket is on LA -2.5"
    dog = _facts(_leg(team="Bills", market="spread", side="team", line=2.5, odds=-110))
    assert dog["Prediction markets"].endswith("BUF +2.5 at 49%") and dog["Line move"].startswith("BUF opened +1.5, now +2.5")
    over = _facts(_leg(game="BUF @ LA", market="total", side="over", line=47.5, odds=-110))
    assert over["The books"].endswith("says 52%")
    assert over["Prediction markets"] == "Polymarket traders put the over 47.5 at 58%", "only the venues quoting it"
    assert over["Line move"] == "Opened 46.5, now 47.5"
    assert over["Money"] == "70% of the $9,000 traded on Kalshi and Polymarket is on the over 47.5"
    under = _facts(_leg(game="BUF @ LA", market="total", side="under", line=47.5, odds=-110))
    assert under["Prediction markets"].endswith("under 47.5 at 42%") and under["Money"].startswith("30% of")
    text = SG.summary(SG.grade({"legs": [_leg(team="Rams", market="moneyline", side="team", odds=-140),
                                         _leg(player="Patrick Mahomes", market="pass_yds", side="over",
                                              line=255.5, odds=-115)]}, BOARDS))
    assert "LA moneyline: ours 58%, needs 58% (fair); Kalshi and Polymarket traders put LA at 61% to win." in text, text


def test_a_venue_at_another_number_is_another_bet_and_stays_off():
    game = BOARD["games"][0]
    saved = json.loads(json.dumps(game))
    try:
        game["crowd"]["spread_home_line"] = -3.5
        game["money"]["spread"]["line"] = -3.5
        f = _facts(_leg(team="Rams", market="spread", side="team", line=-2.5, odds=-110))
        assert "Prediction markets" not in f and "Money" not in f
        game.pop("crowd")
        game.pop("money")
        game.pop("line_open")
        bare = _facts(_leg(team="Rams", market="moneyline", side="team", odds=-140))
        assert set(bare) == {"Our model", "The books", "Game script"}, "nothing on the board, nothing said"
    finally:
        game.clear()
        game.update(saved)


def test_a_long_case_drops_its_colour_first():
    many = [{"k": "Scout", "t": f"note {i}"} for i in range(6)] + [{"k": "Projection", "t": "p"}] + \
           [{"k": "Watch", "t": f"w {i}"} for i in range(8)] + [{"k": "Our record", "t": "r"},
                                                              {"k": "The books", "t": "b"}, {"k": "Defense", "t": "d"}]
    kept = SG._keep(many)
    assert len(kept) == SG.MAX_WHY == 16
    assert [f["k"] for f in kept if f["k"] not in ("Scout", "Watch")] == ["Projection", "Our record", "The books",
                                                                         "Defense"], "the number and the price stay"
    assert sum(f["k"] == "Watch" for f in kept) == 8
    assert [f["t"] for f in kept if f["k"] == "Scout"] == ["note 0", "note 1", "note 2", "note 3"], \
        "colour gives way first, its latest before its earliest"
    assert kept == sorted(kept, key=many.index), "the case still reads in its own order"
    assert SG._keep(many[:10]) == many[:10], "under the cap nothing goes"


def test_the_facts_ride_on_the_card_and_lead_the_summary():
    a = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    b = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    card = SG.grade({"legs": [a, b], "total_odds": 260}, BOARDS)
    ky = next(l for l in card["legs"] if l["player"] == "Kyren Williams")
    assert any(f["k"] == "Defense" for f in ky["why"]) and len(ky["why"]) <= SG.MAX_WHY
    text = SG.summary(card)
    assert text.index("simulated nights") < text.index("Kyren Williams over 69.5"), \
        "the verdict leads: Ask keeps the first 800 characters of a turn"
    assert "BUF allow 128 rushing yards" in text
    words = "BUF allow " + "plenty of rushing yards to backs, " * 8
    long = dict(BOARD, recommendations=[dict(r, matchup_card={"text": words})
                                        if r["player"] == "Kyren Williams" else r for r in BOARD["recommendations"]])
    cut = SG.summary(SG.grade({"legs": [a, b], "total_odds": 260}, {"nfl": long}))
    kept = cut[cut.index("; BUF allow ") + 2:].split("…", 1)[0]
    full = " ".join(words.split()) + " — our number ×1.06 for it"
    assert full.startswith(kept) and full[len(kept)] in " ,", (kept[-20:], "a long fact is cut at a word")
    assert len(kept) <= 140 and not kept.endswith((",", " "))


# ---- the ticket, replayed ------------------------------------------------------
def _priced(**kw):
    return SG.price_leg(BOARDS, _leg(**kw))


def test_the_replay_is_the_sim_labs_two_thousand_nights_and_repeats_itself():
    a = _priced(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    b = _priced(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    one, two = SG.simulate([a, b]), SG.simulate([a, b])
    assert SG.SIM_NIGHTS == 2000 and one["nights"] == 2000 and one == two, "the same slip, the same nights"
    assert sum(one["legs_hit"]) == 2000 and one["cashed"] == one["legs_hit"][-1]
    want = a["prob"] * b["prob"]
    assert abs(one["rate"] - want) < 0.03, (one["rate"], want)
    for h, l in zip(one["hits"], (a, b)):
        assert abs(h / 2000 - l["prob"]) < 0.035, "each leg lands as often as its own chance says"
    other = SG.simulate([a, b], seed=7)
    assert other != one and abs(other["rate"] - want) < 0.03


def test_one_game_replays_the_engines_own_correlation():
    a = _priced(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    c = _priced(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-140)
    d = _priced(player="Davante Adams", market="receptions", side="over", line=4.5, odds=-125)
    ours, _ = SG.joint([a, c, d])
    big = SG.simulate([a, c, d], nights=40000, seed=11)
    assert abs(big["rate"] - ours) < 0.012, (big["rate"], ours)
    pair, _ = SG.joint([a, c])
    assert abs(SG.simulate([a, c], nights=40000, seed=3)["rate"] - pair) < 0.012
    bills = _priced(team="Buffalo Bills", market="moneyline", side="team", odds=120)
    rams = _priced(team="Rams", market="moneyline", side="team", odds=-140)
    both = SG.simulate([bills, rams])
    assert both["cashed"] <= 10, "two sides of one game almost never both win"
    card = SG.grade({"legs": [_leg(team="Buffalo Bills", market="moneyline", side="team", odds=120),
                              _leg(team="Rams", market="moneyline", side="team", odds=-140)]}, BOARDS)
    assert card["ours"] == 0.0 and card["grade"] == "F" and card["sim"] is None, \
        "a ticket that cannot cash is graded as one, not at a copula's few points"
    over = _priced(game="BUF @ LA", market="total", side="over", line=47.5, odds=-110)
    under = _priced(game="BUF @ LA", market="total", side="under", line=47.5, odds=-105)
    assert SG.joint([over, under])[0] == 0.0


def test_the_replay_names_the_leg_that_breaks_the_ticket():
    sure = _priced(player="Kyren Williams", market="rush_yds", side="over", line=49.5, odds=-300)
    shaky = _priced(player="Josh Allen", market="pass_att", side="over", line=36.5, odds=150)
    sim = SG.simulate([sure, shaky])
    assert sim["breaker"]["leg"] == SG._name(shaky) and sim["breaker"]["share"] > 0.8
    assert sim["one_short"] == round(sim["legs_hit"][1] / 2000, 4)
    blind = dict(_priced(player="Somebody Else", market="rec_yds", side="over", line=40.5), odds=0, needs=None)
    assert SG.simulate([sure, blind]) is None, "nothing to draw a leg from, no replay"
    stand = _priced(player="Somebody Else", market="rec_yds", side="over", line=40.5, odds=150)
    got = SG.simulate([sure, stand], nights=20000, seed=5)
    assert abs(got["hits"][1] / 20000 - 0.4) < 0.015, "a leg off our boards plays at its price's break-even"


def test_the_card_carries_the_replay_and_each_legs_count():
    a = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    b = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    card = SG.grade({"legs": [a, b], "total_odds": 260}, BOARDS)
    sim = card["sim"]
    assert sim["nights"] == 2000 and "hits" not in sim and abs(sim["rate"] - card["ours"]) < 0.03
    assert all(isinstance(l["sim_hits"], int) for l in card["legs"])
    blind = SG.grade({"legs": [a, _leg(player="Somebody Else", market="rec_yds", side="over", line=40.5)]}, BOARDS)
    assert blind["sim"] is None


# ---- the server --------------------------------------------------------------
def _method(name):
    i = SRV.index(f"    def {name}(self")
    return SRV[i:SRV.index("\n    def ", i + 10)]


# ---- the live line ---------------------------------------------------------------
# Ethan, 2026-10-12: "Obv make sure we are also pulling live line for the picks
# that the user puts in the parlay checker". engine/sliplive.
from engine import sliplive as SL                                # noqa: E402


def _fast_dir(games=None, deep=None, age_s=0):
    """The live loop's files, as livescore_build writes them, in a temp dir."""
    d = Path(tempfile.mkdtemp())
    (d / "pbp").mkdir()
    doc = {"league": "nfl", "games": games if games is not None else [
        {"event_id": "401", "home": "LA", "away": "BUF",
         "live": {"state": "live", "home_score": 17, "away_score": 10, "period": 3, "clock": "8:12",
                  "detail": "8:12 - 3rd", "win_prob": {"home_win_prob": 0.74, "away_win_prob": 0.26}}},
        {"event_id": "402", "home": "KC", "away": "DEN", "live": {"state": "final", "home_score": 27, "away_score": 20}}]}
    (d / "live_nfl.json").write_text(json.dumps(doc))
    for eid, players in (deep if deep is not None else {
            "401": [{"player": "Kyren Williams", "team": "LA", "stats": {"rush_yds": 74, "carries": 15, "rush_td": 1}},
                    {"player": "Puka Nacua", "team": "LA", "stats": {"receptions": 4, "rec_yds": 51}},
                    {"player": "James Cook", "team": "BUF", "stats": {"rush_yds": 75}}],
            "402": [{"player": "Patrick Mahomes", "team": "KC", "stats": {"pass_yds": 241, "pass_att": 35}}]}).items():
        (d / "pbp" / f"nfl_{eid}.json").write_text(json.dumps({"players": players}))
    if age_s:
        old = __import__("time").time() - age_s
        os.utime(d / "live_nfl.json", (old, old))
    return d


def _live(fast=None):
    return SL.Live({"nfl": SL.quote_index(BOARD)}, fast_dir=fast or _fast_dir(games=[]))


def _priced_live(fast=None, **kw):
    leg = SG.price_leg(BOARDS, _leg(**kw))
    lv = _live(fast)
    return leg, lv.prices(leg, BOARD), lv.state(leg)


def test_every_book_at_the_slips_number_best_first_with_the_margin_out():
    _, p, _ = _priced_live(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    assert p["books"] == [{"book": "FanDuel", "odds": -108}, {"book": "DraftKings", "odds": -115}], \
        "best first; the sharp book is a reference, never the price to take; a proxy is no book"
    assert p["best"] == -108 and p["book"] == "FanDuel" and p["n"] == 2 and p["beats_yours"] is True
    from engine.odds import devig_two_way
    fairs = sorted(devig_two_way(o, u)[0] for o, u in ((-115, -105), (-108, -112), (-104, -116)))
    assert abs(p["fair"] - fairs[1]) < 1e-4, "the median of every book's own pair, the sharp one included"
    assert p["as_of"] == "2025-10-12T15:30:00Z" or p["as_of"].endswith("Z"), p["as_of"]
    import datetime as dt
    assert dt.datetime.fromisoformat(p["as_of"].replace("Z", "+00:00")).timestamp() == 1760283000, \
        "when the pull was made, not when the page loaded"
    _, under, _ = _priced_live(player="Kyren Williams", market="rush_yds", side="under", line=69.5, odds=-105)
    assert under["best"] == -105 and under["book"] == "DraftKings" and "beats_yours" in under
    assert abs(under["fair"] - (1 - p["fair"])) < 0.02
    _, alt, _ = _priced_live(player="Kyren Williams", market="rush_yds", side="over", line=59.5, odds=-160)
    assert alt["books"] == [{"book": "DraftKings", "odds": -170}] and alt["main_line"] == 69.5, \
        "a rung on the ladder, priced at its own number, with the main line beside it"
    assert alt["beats_yours"] is False
    _, none, _ = _priced_live(player="Kyren Williams", market="rush_yds", side="over", line=64.5, odds=-140)
    assert none["books"] == [] and none["any"] is True and "best" not in none
    assert _priced_live(player="Somebody Else", market="rec_yds", side="over", line=40.5)[1] is None


def test_a_side_or_total_reads_its_own_card_for_the_live_price():
    _, rams, _ = _priced_live(team="Rams", market="moneyline", side="team", odds=-150)
    assert rams["books"] == [{"book": "FanDuel", "odds": -140}] and rams["fair"] == 0.57 and rams["beats_yours"]
    _, bills, _ = _priced_live(team="Bills", market="moneyline", side="team", odds=120)
    assert bills["books"] == [{"book": "DraftKings", "odds": 120}] and bills["fair"] == 0.43
    assert not bills["beats_yours"], "the same price is not a better one"
    import datetime as dt
    assert dt.datetime.fromisoformat(rams["as_of"].replace("Z", "+00:00")).timestamp() == 1760284800, \
        "the game lines' own clock"
    _, under, _ = _priced_live(game="BUF @ LA", market="total", side="under", line=47.5, odds=-110)
    assert under["books"] == [{"book": "Caesars", "odds": -105}] and under["fair"] == 0.48
    _, dog, _ = _priced_live(team="Bills", market="spread", side="team", line=2.5, odds=-110)
    assert dog["books"] == [{"book": "BetMGM", "odds": -108}] and dog["fair"] == 0.5


def test_the_ask_loader_keeps_every_books_number_from_the_same_parse():
    from engine import askbot as AB
    d = Path(tempfile.mkdtemp())
    path = d / "recommendations.json"
    path.write_text(json.dumps(BOARD))
    idx = AB.prices_at(path)
    q = idx[(SG._key("Kyren Williams"), "rush_yds")]["quotes"]
    assert (59.5, "DraftKings", -170, 135) in q, "the ladder survives into the index"
    slim = AB.board_at(path)
    ky = next(r for r in slim["recommendations"] if r["player"] == "Kyren Williams")
    assert "alt_lines" not in ky and "all_lines" in ky, "Ask's own copy still drops the ladders"
    assert AB.prices_at(d / "missing.json") == {}


def test_a_game_under_way_reads_the_live_loops_own_files():
    fast = _fast_dir()
    _, _, ky = _priced_live(fast, player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    assert ky["state"] == "live" and ky["current"] == 74 and ky["result"] == "won", "past his number: won, live"
    assert ky["clock"] == "8:12 - 3rd" and (ky["home_score"], ky["away_score"]) == (17, 10)
    _, _, pk = _priced_live(fast, player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150)
    assert pk["current"] == 4 and pk["result"] is None, "short of his number with time left: still live"
    _, _, cook = _priced_live(fast, player="James Cook", market="rush_yds", side="under", line=70.5, odds=-110)
    assert cook["result"] == "lost", "an under past its number has lost, whatever the clock says"
    _, _, mah = _priced_live(fast, player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    assert mah["state"] == "final" and mah["current"] == 241 and mah["result"] == "lost" and mah["clock"] == "Final"
    _, _, td = _priced_live(fast, player="Kyren Williams", market="anytime_td", side="yes", line=0.5, odds=120)
    assert td["current"] == 1 and td["result"] == "won"
    _, _, adams = _priced_live(fast, player="Davante Adams", market="receptions", side="over", line=4.5, odds=-125)
    assert "current" not in adams and adams["note"] == "not in the box score yet"
    _, _, rams = _priced_live(fast, team="Rams", market="moneyline", side="team", odds=-140)
    assert rams["win_prob"] == 0.74 and rams["margin"] == 7 and "result" not in rams
    _, _, bills = _priced_live(fast, team="Bills", market="moneyline", side="team", odds=120)
    assert bills["win_prob"] == 0.26
    _, _, sp = _priced_live(fast, team="Rams", market="spread", side="team", line=-2.5, odds=-110)
    assert sp["cover_by"] == 4.5 and "result" not in sp
    _, _, over = _priced_live(fast, game="BUF @ LA", market="total", side="over", line=47.5, odds=-110)
    assert over["current"] == 27 and over["result"] is None
    kc = _fast_dir(games=[{"event_id": "402", "home": "KC", "away": "DEN",
                           "live": {"state": "final", "home_score": 20, "away_score": 20}}])
    leg = SG.price_leg(BOARDS, _leg(team="Chiefs", market="moneyline", side="team", odds=-150))
    assert SL.live_state(dict(leg, league="nfl", row={"home": "KC", "away": "DEN"}, team="KC"), kc)["result"] == "push"
    stale = _fast_dir(age_s=SL.FAST_FRESH_S + 60)
    assert _priced_live(stale, player="Kyren Williams", market="rush_yds", side="over", line=69.5)[2] is None, \
        "a stopped loop pins nothing on a leg"
    pre = _fast_dir(games=[{"event_id": "401", "home": "LA", "away": "BUF", "live": {"state": "scheduled"}}])
    st = _priced_live(pre, player="Kyren Williams", market="rush_yds", side="over", line=69.5)[2]
    assert st["state"] == "scheduled" and "current" not in st and "result" not in st
    assert SL.live_state({"league": "mlb", "market": "hits"}, fast) is None, "no fast loop, no live line"


def test_the_ticket_says_where_it_stands():
    fast = _fast_dir()
    ky = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    pk = _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150)
    rams = _leg(team="Rams", market="moneyline", side="team", odds=-140)
    mah = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    live = _live(fast)
    open_ = SG.grade({"legs": [ky, pk]}, BOARDS, live=live)
    # A PROP IN PLAY GETS ITS LIVE CHANCE. This pinned "a prop in play gets
    # no number" until 2026-10-12, when Ethan asked for "live chances for
    # props mid game"; engine/proplive is the race it now runs: Puka on 4
    # catches over 5.5, with 8:12 left in the third (1,392 of 3,600
    # seconds), held to the card's own pregame chance at kickoff.
    from engine import proplive as PL
    pk_card = next(l for l in open_["legs"] if l["player"] == "Puka Nacua")
    ch = pk_card["live"]["chance"]
    disp = PL.dispersion(SG.price_leg(BOARDS, pk)["row"], "receptions")
    mu = PL.anchor(pk_card["prob"], 5.5, disp)
    want, push = PL.race("over", 5.5, 4.0, 1392 / 3600, mu, disp)
    assert abs(ch["p"] - round(want, 4)) < 1e-4 and ch["model"] == "clock" and ch["from"] == "ours", ch
    assert abs(ch["share_left"] - 1392 / 3600) < 1e-3
    assert open_["now"] == {"won": 1, "lost": 0, "push": 0, "live": 1, "status": "open", "left": 1, "start": 0,
                            "chance": round(ch["p"] + ch["push"], 4)}, "the ticket's chance is the live race's"
    assert open_["shop"] is None and open_["better"] is None, "where to place it is a pre-game question"
    assert all(l["price"] is None for l in open_["legs"]), "a started game's pre-game price is gone"
    ml = SG.grade({"legs": [ky, rams]}, BOARDS, live=live)
    assert ml["now"]["status"] == "open" and ml["now"]["chance"] == 0.74, "a moneyline in play at its live chance"
    lost = SG.grade({"legs": [ky, mah]}, BOARDS, live=live)
    assert lost["now"]["status"] == "lost" and lost["now"]["chance"] == 0.0
    assert lost["now"]["lost_leg"] == "Patrick Mahomes over 255.5 passing yards"
    text = SG.summary(lost)
    assert text.index("Live: this ticket has already lost — Patrick Mahomes over 255.5 passing yards missed.") < \
        text.index("Before kickoff our chance was")
    won = SG.grade({"legs": [ky, _leg(player="Kyren Williams", market="anytime_td", side="yes", line=0.5, odds=120)]},
                   BOARDS, live=live)
    assert won["now"]["status"] == "won" and "Live: every leg has won." in SG.summary(won)
    t2 = SG.summary(open_)
    assert f"Live: 1 won, 1 in play; our chance for the rest {open_['now']['chance']:.0%}." in t2, t2
    calm = SG.grade({"legs": [ky, pk]}, BOARDS, live=_live())
    assert calm["now"] is None and all(l["price"] for l in calm["legs"]), "before kickoff: prices, no standing"


def test_where_to_place_it_and_the_leg_it_is_better_without():
    ky = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    pk = _leg(player="Puka Nacua", market="receptions", side="over", line=5.5, odds=-150)
    card = SG.grade({"legs": [ky, pk], "total_odds": 210}, BOARDS, live=_live())
    sh = card["shop"]
    from engine.slipgrade import to_decimal
    want = SG.from_decimal(to_decimal(-108) * to_decimal(-135))
    assert sh["books"][0] == {"book": "FanDuel", "odds": want} and want == 235
    assert sh["books"][1]["book"] == "DraftKings" and sh["yours"] == 210 and sh["beats_yours"]
    assert sh["same_game"] is True, "a same-game ticket says books price it their own way"
    assert "Best place for it now: FanDuel at +235 (your slip +210)." in SG.summary(card)
    assert SG.shop([SG.price_leg(BOARDS, ky)], 0) is None
    cook = _leg(player="James Cook", market="rush_yds", side="under", line=70.5, odds=-110)
    assert SG.grade({"legs": [ky, cook]}, BOARDS, live=_live())["shop"] is None, "a leg no book quotes: no shop"
    mah = _leg(player="Patrick Mahomes", market="pass_yds", side="over", line=255.5, odds=-115)
    fair = _leg(player="Josh Allen", market="pass_att", side="over", line=32.5, odds=-120)
    ok = SG.grade({"legs": [ky, mah, fair], "total_odds": 600}, BOARDS, live=_live())
    assert ok["better"] is None, "a leg that pays for itself: cutting it halves the payout for less than double the chance"
    # At -300 the same leg needs 75% and we say 54%: the ticket is better without it.
    weak = dict(fair, odds=-300)
    total = SG.from_decimal(to_decimal(-115) * to_decimal(-115) * to_decimal(-300))
    three = SG.grade({"legs": [ky, mah, weak], "total_odds": total}, BOARDS, live=_live())
    bt = three["better"]
    assert bt and bt["leg"] == "Josh Allen over 32.5 pass attempts", bt
    assert bt["ev"] >= three["ev"] + SG.DROP_GAIN and bt["odds"] == SG.from_decimal(to_decimal(total) / to_decimal(-300))
    rest, _ = SG.joint([SG.price_leg(BOARDS, ky), SG.price_leg(BOARDS, mah)])
    assert abs(bt["chance"] - rest) < 1e-4
    assert bt["approx"] is True, "Kyren and Josh Allen share BUF @ LA: the book's payout is its own, so it is close, not exact"
    assert "Better without Josh Allen over 32.5 pass attempts: return" in SG.summary(three)
    assert SG.without([SG.price_leg(BOARDS, ky), SG.price_leg(BOARDS, mah)], 3.0, 0.1) is None, "two legs: nothing to cut"


def test_alerts_pairs_and_kickoff():
    ky = _leg(player="Kyren Williams", market="rush_yds", side="over", line=69.5, odds=-115)
    cook = _leg(player="James Cook", market="rush_yds", side="under", line=70.5, odds=-110)
    card = SG.grade({"legs": [ky, cook]}, BOARDS, live=_live())
    assert "Kyren Williams: listed Questionable" in card["alerts"]
    assert "No book is pricing James Cook under 70.5 rushing yards right now — it may have been taken down" in card["alerts"]
    assert next(l for l in card["legs"] if l["player"] == "Kyren Williams")["kickoff"] == "2026-10-12 16:25"
    assert card["first_kickoff"] == "2026-10-12 16:25"
    legs = [SG.price_leg(BOARDS, ky), SG.price_leg(BOARDS, _leg(team="Rams", market="moneyline", side="team", odds=-140))]
    got = SG.pairs(legs)
    for x in got:
        assert abs(x["rho"]) >= SG.PAIR_RHO and len(x["legs"]) == 2 and x["why"]
    rel = P.relate("nfl", SG._relation_leg(legs[0]), SG._relation_leg(legs[1]))
    assert bool(got) == (abs(rel.rho) >= SG.PAIR_RHO and rel.verdict not in ("kill", "duplicate"))
    assert SG.pairs([SG.price_leg(BOARDS, ky), SG.price_leg(BOARDS, _leg(player="Patrick Mahomes", market="pass_yds",
                                                                        side="over", line=255.5))]) == [], \
        "different games are not a pair"
    assert SG.grade({"legs": [ky]}, BOARDS)["alerts"] == ["Kyren Williams: listed Questionable"], \
        "without the live line there are no prices to alert on"
    bare = {k: dict(v, quotes=[]) for k, v in SL.quote_index(BOARD).items()}
    dry = SG.grade({"legs": [ky, cook]}, BOARDS, live=SL.Live({"nfl": bare}, fast_dir=_fast_dir(games=[])))
    assert dry["alerts"] == ["Kyren Williams: listed Questionable"] and all(l["price"] is None for l in dry["legs"]), \
        "a board with no book's price anywhere (a pull that did not land) is no sign one prop was taken down"


def test_the_server_gates_and_counts_it_as_a_question_before_the_picture_is_read():
    route = SRV.index('if parsed.path in ("/api/ask/slip", "/api/ask/slip/"):')
    assert route < SRV.index('if parsed.path in ("/api/ask", "/api/ask/"):')
    head = SRV[route:SRV.index("return self._ask_slip(body)", route)]
    assert "length > MAX_SLIP_BYTES" in head and "413" in head
    import server
    assert server.MAX_SLIP_BYTES <= 1_000_000
    caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
    assert "max_size 1MB" in caddy, "Caddy refuses a larger body before the server sees it"
    body = _method("_ask_slip")
    order = ["self._rate_limited(RATE_ASK_PER_MIN", "self._entitled(conn, who)", "SG.decode_image(",
             # (Pin updated 2026-10-14, "do 1-11": the upload's live object is
             # engine/slipodds.FreshLive, which may buy an old leg a fresh
             # price; it was sliplive.Live. The order held is the same.)
             "AB.configured()", "AB.over_limit(me)", "SG.read_slip(",
             "SG.grade(slip, boards, live=SO.FreshLive(prices))",
             "AB.count_question(me)", "AB.sign_turn(text)"]
    # The last count is the graded one; an unreadable slip is counted on its own path below.
    at = [body.rindex(x) if x == "AB.count_question(me)" else body.index(x) for x in order]
    assert at == sorted(at), dict(zip(order, at))
    assert "401 if not who else 402" in body and "429" in body
    assert "prices[league] = AB.prices_at(path)" in body, "every book's prices from the same parse as the board"
    unread = body[body.index("except SG.SlipUnreadable"):body.index("except EX.NotConfigured")]
    assert "AB.count_question(me)" in unread and "422" in unread, "a read that was paid for is counted"
    assert "open(" not in body and ".write_" not in body and "body.get(\"image\")" in body
    assert body.count("sys.stderr.write") == 1 and "image" not in body[body.index("sys.stderr.write"):][:80], \
        "the picture is written nowhere, the log included"


# ---- the page ----------------------------------------------------------------
def _fn(name):
    i = APP.index(f"function {name}(")
    return APP[i:APP.index("\n}\n", i)]


def test_the_attach_sheet_uploads_and_the_turn_draws_the_card():
    sheet = _fn("askAttachHTML")
    assert '<label class="ask-attach-row"><span>Grade a parlay screenshot</span>' in sheet
    assert '<input type="file" accept="image/*" class="ask-sr" data-ask-slip>' in sheet, \
        "a real input in the row's label: a phone's picker opens on the tap itself"
    room = _fn("renderAsk")
    assert 'sheet.querySelectorAll("[data-ask-slip]")' in room and "askSlipSend(f.files[0])" in room
    load = _fn("loadSlip")
    assert 'css.href = "css/slip.css"' in load and 's.src = "js/slip.js"' in load and "window.QBSlip" in load
    turn = _fn("askTurnHTML")
    assert "t.slip ? askSlipCard(t) : askBodyHTML(t.text)" in turn and 't.slip ? " has-slip" : ""' in turn
    card = _fn("askSlipCard")
    assert "window.QBSlip.card(t.slip)" in card and "renderAsk()" in card and "askBodyHTML(t.text)" in card
    send = _fn("askSend")
    assert "t.sig ? { role: t.role, text: t.text, sig: t.sig }" in send, \
        "a graded slip's signed summary rides along as the conversation"
    js = SLIP_JS.read_text(encoding="utf-8")
    assert 'fetch("/api/ask/slip"' in js and 'media_type: "image/jpeg"' in js
    assert "const MAX_SIDE = 1568;" in js
    b64 = int(js.split("const MAX_B64 = ")[1].split(";")[0])
    assert b64 <= SG.MAX_IMAGE_BYTES * 4 // 3, "the page never sends what the server would refuse"
    assert 'sig: body.sig || ""' in js and "slip: body.slip" in js
    assert "Not betting advice." in js and "21+" in js
    assert ".pgr-card" in SLIP_CSS.read_text(encoding="utf-8")


CARD = {
    "legs": [
        {"sport": "nfl", "player": "Puka Nacua", "team": "LA", "game": "BUF @ LA", "market": "receptions",
         "side": "over", "line": 5.5, "odds": -140, "prob": 0.7712, "needs": 0.5833, "edge": 0.1879,
         "verdict": "strong", "found": "likely", "tier": "Top pick"},
        {"sport": "nfl", "player": "<img src=x onerror=alert(1)>", "team": "BUF", "game": "BUF @ LA",
         "market": "pass_att", "side": "over", "line": 32.5, "odds": -120, "prob": 0.51, "needs": 0.5455,
         "edge": -0.0355, "verdict": "weak", "found": "prop", "tier": ""},
        {"sport": "nfl", "player": "Somebody Else", "team": "", "game": "", "market": "rec_yds", "side": "over",
         "line": 40.5, "odds": 150, "prob": None, "needs": 0.4, "edge": None, "verdict": "unpriced", "found": ""},
    ],
    "n_legs": 3, "n_priced": 2, "dropped": 1, "book": "FanDuel", "stake": 10, "total_odds": 600,
    "ours": 0.158, "needs": 0.1429, "ev": 0.106, "grade": "A*",
    "notes": [{"legs": ["BUF moneyline", "BUF spread +2.5"], "kind": "duplicate", "why": "one opinion sold twice"}],
    "weakest": "Josh Allen over 32.5 pass attempts",
    "swap": {"player": "Kyren Williams", "market": "rush_yds", "side": "Over", "line": 59.5, "odds": -200,
             "prob": 0.81, "tier": ""},
    "sim": {"nights": 2000, "cashed": 318, "rate": 0.159, "legs_hit": [96, 520, 1066, 318],
            "one_short": 0.533, "breaker": {"leg": "Josh Allen over 32.5 pass attempts", "share": 0.62}},
}
CARD["legs"][0].update(sim_hits=1544, why=[{"k": "Defense", "t": "BUF allow 13.2 catches by WRs a game, the 7th-most"},
                                          {"k": "Matchup read", "t": "Breakout candidate · <script>x</script>"}])
# The live line, before kickoff (engine/sliplive): every book's price, the ticket's shop.
CARD["legs"][0].update(kickoff="2026-10-12 16:25", price={
    "books": [{"book": "FanDuel", "odds": -135}, {"book": "DraftKings", "odds": -150}, {"book": "<b>Evil</b>", "odds": -155},
              {"book": "BetMGM", "odds": -160}],
    "n": 4, "fair": 0.5549, "as_of": "2026-10-12T15:00:00Z", "any": True, "best": -135, "book": "FanDuel",
    "beats_yours": True})
CARD["legs"][1].update(price={"books": [{"book": "DraftKings", "odds": -125}], "n": 1, "fair": None, "any": True,
                              "best": -125, "book": "DraftKings", "beats_yours": False, "main_line": 34.5})
CARD["legs"][2].update(price={"books": [], "n": 0, "fair": None, "any": False})
CARD.update(alerts=["Kyren Williams: listed Questionable", "<i>breaking</i>"],
            shop={"books": [{"book": "FanDuel", "odds": 640}, {"book": "DraftKings", "odds": 600}],
                  "same_game": True, "yours": 600, "beats_yours": True},
            better={"leg": "Josh Allen over 32.5 pass attempts", "chance": 0.31, "odds": 310, "ev": 0.27, "approx": True},
            pairs=[{"legs": ["Puka Nacua over 5.5 receptions", "Josh Allen over 32.5 pass attempts"], "rho": -0.21,
                    "why": "they <u>share</u> the targets"},
                   {"legs": ["Puka Nacua over 5.5 receptions", "LA moneyline"], "rho": 0.32, "why": "a win needs his catches"}],
            now=None, first_kickoff="2026-10-12 16:25")

# The same ticket on game day: a leg settled, one in play, one to start.
LIVE_CARD = dict(CARD, shop=None, better=None, alerts=[], pairs=[],
                 now={"won": 1, "lost": 0, "push": 0, "live": 1, "status": "open", "left": 2, "start": 1, "chance": None},
                 legs=[dict(CARD["legs"][0], price=None, live={
                           "state": "final", "home": "LA", "away": "BUF", "home_score": 24, "away_score": 20,
                           "clock": "Final", "current": 7, "result": "won"}),
                       dict(CARD["legs"][1], price=None, live={
                           "state": "live", "home": "LA", "away": "<b>BUF</b>", "home_score": 17, "away_score": 10,
                           "clock": "8:12 - 3rd", "current": 24}),
                       dict(CARD["legs"][2], live={"state": "scheduled"})])
LOST_CARD = dict(LIVE_CARD, now={"won": 0, "lost": 1, "push": 0, "live": 0, "status": "lost", "left": 0, "start": 0,
                                 "chance": 0.0, "lost_leg": "Puka Nacua over 5.5 receptions"})


FOUND_NO_NUMBER = dict(CARD, legs=[dict(CARD["legs"][2], player="Josh Allen", found="prop")], n_legs=1,
                       n_priced=0, ours=None, ev=None, grade="?", notes=[], weakest="", swap=None, dropped=0)


def test_the_card_renders_and_escapes_what_the_picture_said():
    node = shutil.which("node")
    if not node:
        print("      (skipped: no Node)")
        return
    script = (
        "const vm = require('vm'); const fs = require('fs');"
        "const ctx = { window: {} }; vm.createContext(ctx);"
        f"vm.runInContext(fs.readFileSync({json.dumps(str(SLIP_JS))}, 'utf8'), ctx);"
        f"process.stdout.write(ctx.window.QBSlip.card({json.dumps(CARD)}));"
        "process.stdout.write('\\n=====\\n');"
        f"process.stdout.write(ctx.window.QBSlip.card({json.dumps(FOUND_NO_NUMBER)}));"
        "process.stdout.write('\\n=====\\n');"
        f"process.stdout.write(ctx.window.QBSlip.card({json.dumps(LIVE_CARD)}));"
        "process.stdout.write('\\n=====\\n');"
        f"process.stdout.write(ctx.window.QBSlip.card({json.dumps(LOST_CARD)}));"
    )
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    html, other, live, lost = out.stdout.split("\n=====\n")
    assert "No number of ours" in other and "Our projection" not in other, \
        "a player we carry at a number we can't price is not 'not on our board'"
    assert 'class="pgr-grade g-a"' in html and ">A<sup>*</sup>" in html
    assert html.count('<li class="pgr-leg') == 3 and "3-leg parlay · FanDuel" in html
    assert "Puka Nacua Over 5.5 Receptions" in html and "On our Most Likely board · Top pick" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html and "<img src=x" not in html
    assert "Not on our board" in html and "ours <b>77%</b> · needs 58% at -140" in html
    assert "Our chance it all hits <b>16%</b> · the payout needs <b>14%</b>" in html and "+11%" in html
    assert "* We can’t price 1 leg — it counts at its own price’s break-even" in html
    assert "it neither helps nor hurts the grade" in html
    assert "1 leg on the picture couldn’t be read" in html
    assert "One bet sold twice" in html and "Weakest leg:" in html and "Kyren Williams over 59.5 Rush Yds" in html
    assert 'style="width:77%"' in html and 'style="left:58%"' in html
    assert "21+ · 1-800-GAMBLER" in html
    assert "2,000 simulated nights" in html and "cashed <b>318</b> times · 15.9%" in html
    assert html.count('<div class="pgr-sim-col') == 4 and '<div class="pgr-sim-col all">' in html and "all 3" in html
    assert "Missed by one leg on 53% of nights — most often <b>Josh Allen over 32.5 pass attempts</b> (62% of those)" in html
    assert "hit in 1,544 of 2,000 simulated nights" in html
    assert '<details class="pgr-why"><summary>Why we say 77%</summary>' in html
    assert "<dt>Defense</dt><dd>BUF allow 13.2 catches by WRs a game, the 7th-most</dd>" in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html and "<script>x" not in html
    # The live line, before kickoff.
    assert "Now <b>FanDuel -135</b> · DraftKings -150 · &lt;b&gt;Evil&lt;/b&gt; -155 · 4 books" in html
    assert "55% with the margin out" in html and '<span class="up">beats your -140</span>' in html
    assert "BetMGM -160" not in html, "three books shown, the count says how many more"
    assert "main line 34.5" in html and "No book is pricing this right now." in html
    assert '<span class="pgr-when">· priced ' in html and "Mon 4:25 PM ET" in html
    assert '<div class="pgr-alerts"><b>Read this first</b>' in html and "&lt;i&gt;breaking&lt;/i&gt;" in html
    assert "<b>Place it at</b> <b>FanDuel +640</b> · DraftKings +600 · your slip +600" in html
    assert "Books price same-game parlays their own way" in html
    assert "<b>Better without</b> Josh Allen over 32.5 pass attempts: chance 31%, pays +310 (about), return" in html
    assert '<span class="down">Apart -0.21</span>' in html and '<span class="up">Together +0.32</span>' in html
    assert "they &lt;u&gt;share&lt;/u&gt; the targets" in html and "<u>share" not in html
    assert "pgr-now" not in html, "no standing before kickoff"
    # Game day.
    assert '<div class="pgr-now s-open"><b>Live</b> · 1 won · 1 in play · 1 yet to start' in live
    # Pinned "we don’t put a number on a prop mid-game" until 2026-10-13, when
    # props in play got their live chance (engine/proplive); a leg in play
    # with none (this fixture's has no `chance`) still leaves the rest unsaid.
    assert "no number for the rest — a leg in play has no live chance yet" in live
    assert "Before kickoff our chance was <b>16%</b>" in live and "Our chance it all hits" not in live
    assert '<span class="pgr-res r-won">Won</span>' in live and 'class="pgr-leg v-strong r-won"' in live
    assert '<span class="pgr-live-tag fin">Final</span> BUF 20 – 24 LA' in live and "Has <b>7</b> of 5.5" in live
    assert '<span class="pgr-live-tag">Live</span> &lt;b&gt;BUF&lt;/b&gt; 10 – 17 LA · 8:12 - 3rd · Has <b>24</b> of 32.5' in live
    assert 'style="width:74%"' in live, "24 of 32.5 drawn as progress"
    assert "pgr-price" not in live.split("Somebody Else")[0], "a started game's pre-game price is gone"
    assert '<div class="pgr-now s-lost"><b>Lost</b> — Puka Nacua over 5.5 receptions missed.</div>' in lost


# ---- the browser half ------------------------------------------------------------
_WALK = r"""
import { chromium } from 'playwright';
const [PORT, PNG, RESP] = [process.argv[2], process.argv[3], JSON.parse(process.argv[4])];
const ARGS = ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'];
let b = null, lastErr = null;
for (const path of [process.env.CHROMIUM_PATH, '/opt/pw-browsers/chromium', undefined]) {
  try { b = await chromium.launch({ executablePath: path || undefined, args: ARGS }); break; }
  catch (e) { lastErr = e; }
}
if (!b) throw lastErr;
const out = {};
for (const [w, h] of [[390, 844], [1280, 900]]) {
  const p = await (await b.newContext({ viewport: { width: w, height: h } })).newPage();
  const errs = []; p.on('pageerror', (e) => errs.push(String(e)));
  await p.addInitScript(() => { try { localStorage.setItem('qb.tour', 'done'); } catch (e) {} });
  let sent = null;
  await p.route('**/api/ask/slip', async (route) => {
    sent = JSON.parse(route.request().postData() || '{}');
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(RESP) });
  });
  await p.goto(`http://127.0.0.1:${PORT}/#ask`, { waitUntil: 'domcontentloaded' });
  await p.waitForSelector('#ask-input', { timeout: 20000 });
  await p.click('[data-ask-clip]');
  await p.waitForSelector('[data-ask-slip]', { state: 'attached', timeout: 5000 });
  await p.setInputFiles('[data-ask-slip]', { name: 'slip.png', mimeType: 'image/png', buffer: Buffer.from(PNG, 'base64') });
  await p.waitForSelector('.pgr-card', { timeout: 20000 });
  const card = () => p.evaluate(() => {
    const c = document.querySelector('.pgr-card');
    const r = c.getBoundingClientRect();
    const why = c.querySelector('.pgr-why');
    if (why) why.open = true;
    return { grade: c.querySelector('.pgr-grade').textContent.trim(), legs: c.querySelectorAll('.pgr-leg').length,
             sim: c.querySelectorAll('.pgr-sim-col').length, why: why ? why.querySelectorAll('dt').length : 0,
             price: c.querySelectorAll('.pgr-price').length, live: c.querySelectorAll('.pgr-live').length,
             extras: ['.pgr-now', '.pgr-alerts', '.pgr-shop', '.pgr-better', '.pgr-pairs'].filter((q) => c.querySelector(q)).length,
             left: Math.round(r.left), right: Math.round(r.right), screen: window.innerWidth,
             overflow: document.scrollingElement.scrollWidth > window.innerWidth + 1,
             sheet: document.getElementById('ask-attach').hidden };
  });
  const first = await card();
  await p.reload({ waitUntil: 'domcontentloaded' });
  await p.waitForSelector('.pgr-card', { timeout: 20000 });
  out[w] = { first, again: await card(), media: sent && sent.media_type,
             jpeg: !!(sent && String(sent.image || '').startsWith('/9j/')), errors: errs };
  await p.close();
}
console.log(JSON.stringify(out));
await b.close();
"""


def _have_node() -> bool:
    try:
        r = subprocess.run(["node", "-e", "import('playwright').then(()=>0,()=>process.exit(1))"],
                           capture_output=True, cwd=ROOT, timeout=30)
        return r.returncode == 0
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return False


def test_a_screenshot_goes_up_and_the_card_comes_back_at_both_widths():
    if os.environ.get("QB_BROWSER_TESTS") != "1":
        print("      (skipped: set QB_BROWSER_TESTS=1)")
        return
    if not _have_node():
        print("      (skipped: no Node/Playwright — install to enable)")
        return
    import rendercheck
    # Every piece at once — a pre-game shop beside a game-day standing never
    # happens, but the layout has to hold all of them at both widths.
    walk = dict(CARD, now=LIVE_CARD["now"], legs=[CARD["legs"][0], LIVE_CARD["legs"][1], CARD["legs"][2]])
    resp = {"slip": walk, "text": "Graded parlay, 3 legs (2 on our boards).", "sig": "x"}
    srv, port = rendercheck._serve()
    script = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, dir=ROOT) as fh:
            fh.write(_WALK)
            script = fh.name
        proc = subprocess.run(["node", script, str(port), _b64(_png(600, 1200)), json.dumps(resp)],
                              cwd=ROOT, capture_output=True, text=True, timeout=240)
    finally:
        if script:
            os.unlink(script)
        srv.shutdown()
    assert proc.returncode == 0, proc.stderr[-1500:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    for w, got in out.items():
        assert got["media"] == "image/jpeg" and got["jpeg"], f"{w}: the page sends a JPEG it drew itself"
        for k in ("first", "again"):
            c = got[k]
            assert c["grade"] == "A*" and c["legs"] == 3 and c["sim"] == 4 and c["why"] == 2, (w, k, c)
            assert c["price"] == 2 and c["live"] == 1 and c["extras"] == 5, (w, k, c)
            assert c["left"] >= 0 and c["right"] <= c["screen"] and not c["overflow"], (w, k, c)
        assert got["first"]["sheet"], "the attach sheet closes once a picture is chosen"
        assert not got["errors"], got["errors"]


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
