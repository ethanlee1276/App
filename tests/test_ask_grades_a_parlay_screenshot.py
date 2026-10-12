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


BOARD = {
    "games": [{"home": "LA", "away": "BUF"}, {"home": "KC", "away": "DEN"}],
    "recommendations": [
        _rec("Kyren Williams", "LA", "BUF", "rush_yds", "Over", 69.5, -115, 82.0, 18.0, [80, 75, 90, 85, 70]),
        _rec("Josh Allen", "BUF", "LA", "pass_att", "Over", 32.5, -110, 33.0, 5.0, [31, 35, 30, 34]),
        _rec("James Cook", "BUF", "LA", "rush_yds", "Under", 70.5, -110, 62.0, 16.0, [60, 55, 71, 64]),
        _rec("Patrick Mahomes", "KC", "DEN", "pass_yds", "Over", 255.5, -115, 271.0, 45.0, [280, 240, 300]),
        _rec("Keenan Allen", "CHI", "GB", "receptions", "Over", 4.5, -120, 5.1, 1.8, [5, 6, 4]),
        _rec("Josh Allen", "BUF", "LA", "rush_yds", "Over", 30.5, -110, 33.0, 14.0, [30, 41, 22]),
        _rec("Davante Adams", "LA", "BUF", "receptions", "Over", 4.5, -125, 5.2, 1.7, [5, 4, 6]),
    ],
    "likely_board": {"rows": [
        {"kind": "prop", "player": "Puka Nacua", "team": "LA", "opponent": "BUF", "market": "receptions",
         "side": "Over", "line": 5.5, "odds": -140, "model_prob": 0.7712, "tier": "Top pick"},
        {"kind": "prop", "player": "Davante Adams", "team": "LA", "opponent": "BUF", "market": "rec_yds",
         "side": "Over", "line": 49.5, "odds": -120, "model_prob": 0.66, "tier": "Strong"},
    ]},
    "td_field": [{"player": "Kyren Williams", "team": "LA", "opponent": "BUF", "market": "anytime_td",
                  "model_prob": 0.48, "odds": 110}],
    "game_bets": [
        {"bet_type": "moneyline", "market": "moneyline", "home": "LA", "away": "BUF", "team": "LA", "pick": "LA",
         "pick_is_home": True, "pick_label": "LA ML", "side": "", "line": 0.0, "win_prob": 0.58, "odds": -140,
         "home_odds": -140, "away_odds": 120},
        {"bet_type": "total", "market": "total", "home": "LA", "away": "BUF", "team": "", "side": "Over",
         "line": 47.5, "pick_label": "Over 47.5", "win_prob": 0.55, "odds": -110, "other_odds": -105},
        {"bet_type": "spread", "market": "spread", "home": "LA", "away": "BUF", "team": "LA", "side": "",
         "line": -2.5, "pick_label": "LA -2.5", "win_prob": 0.53, "odds": -110, "other_odds": -110},
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


# ---- the server --------------------------------------------------------------
def _method(name):
    i = SRV.index(f"    def {name}(self")
    return SRV[i:SRV.index("\n    def ", i + 10)]


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
             "AB.configured()", "AB.over_limit(me)", "SG.read_slip(", "SG.grade(slip, boards)",
             "AB.count_question(me)", "AB.sign_turn(text)"]
    # The last count is the graded one; an unreadable slip is counted on its own path below.
    at = [body.rindex(x) if x == "AB.count_question(me)" else body.index(x) for x in order]
    assert at == sorted(at), dict(zip(order, at))
    assert "401 if not who else 402" in body and "429" in body
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
}


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
    )
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-800:]
    html, other = out.stdout.split("\n=====\n")
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
    return { grade: c.querySelector('.pgr-grade').textContent.trim(), legs: c.querySelectorAll('.pgr-leg').length,
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
    resp = {"slip": CARD, "text": "Graded parlay, 3 legs (2 on our boards).", "sig": "x"}
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
            assert c["grade"] == "A*" and c["legs"] == 3, (w, k, c)
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
