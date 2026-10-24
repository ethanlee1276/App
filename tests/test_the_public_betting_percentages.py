"""The public betting percentages: licensed, off until keyed, read by shape, paid, and said as context.

Ethan, 2026-10-24: "yes build all of D" — the public betting percentages
first. engine/splits reads SharpAPI's DraftKings and Circa splits (the share
of the bets and of the money on each side) once a key is set with
deploy/setenv.sh, puts them on the board under a paid key, keeps every
reading, and the game report says them.

What these hold: the documented reply and a differently nested one both
read, 0-100 as 0-1, and a number that is not a share is dropped rather than
shown; the board's games are matched by full name or code; the sentence
leads with DraftKings, the spread before the moneyline, adds the total and
Circa's money, and calls it context; with no key nothing is fetched and the
board says it is off; the key rides in a header and never the URL, the client names
itself, and a refusal says what the API said; the splits are a paid key, kept in the history, and the report and the NFL
build carry them.

Run directly: `python3 tests/test_the_public_betting_percentages.py`
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import gate                                            # noqa: E402
from engine import splits as SP                                    # noqa: E402

DOCUMENTED = {"data": [
    {"home_team": "Kansas City Chiefs", "away_team": "Denver Broncos", "fetched_at": "2026-10-25T15:00:00Z",
     "splits": [
         {"book": "DraftKings",
          "moneyline": {"handle_pct": {"home": 0.71, "away": 0.29}, "bets_pct": {"home": 0.66, "away": 0.34}},
          "spread": {"handle_pct": {"home": 0.58, "away": 0.42}, "bets_pct": {"home": 0.72, "away": 0.28}},
          "total": {"handle_pct": {"over": 0.40, "under": 0.60}, "bets_pct": {"over": 0.61, "under": 0.39}}},
         {"book": "Circa", "spread": {"handle_pct": {"home": 0.35, "away": 0.65}}}]},
    {"home_team": "Buffalo Bills", "away_team": "Miami Dolphins", "splits": []},
    {"home_team": "Detroit Lions", "away_team": "Green Bay Packers", "splits": [
        {"book": "DraftKings", "spread": {"bets_pct": {"home": 1.7, "away": -0.7}}}]}]}

NESTED = {"events": [{"teams": {"home": {"name": "Seattle Seahawks"}, "away": {"name": "Los Angeles Rams"}},
                      "books": {"DraftKings": {"spreads": {"money_pct": {"home": 64, "away": 36},
                                                           "tickets_pct": {"home": 55, "away": 45}}}}}]}


def test_the_documented_reply_reads_and_a_bad_share_is_dropped():
    got = SP.parse(DOCUMENTED)
    assert [(e["away"], e["home"]) for e in got] == [("Denver Broncos", "Kansas City Chiefs")], \
        "no splits and a number that is not a share give nothing"
    dk = got[0]["books"]["DraftKings"]
    assert dk["spread"] == {"bets": {"home": 0.72, "away": 0.28}, "money": {"home": 0.58, "away": 0.42}}
    assert dk["total"]["bets"] == {"over": 0.61, "under": 0.39}
    assert got[0]["books"]["Circa"] == {"spread": {"money": {"home": 0.35, "away": 0.65}}}
    assert got[0]["at"] == "2026-10-25T15:00:00Z"
    assert SP._sides({"home": 0.6, "away": 0.6}) == {}, "two sides past the whole are not shares"
    assert SP._sides({"over": 61, "under": 39}) == {"over": 0.61, "under": 0.39}
    assert SP._sides({"home": 140, "away": -40}) == {}


def test_another_nesting_and_percent_points_read_the_same():
    got = SP.parse(NESTED)
    assert got[0]["home"] == "Seattle Seahawks"
    assert got[0]["books"]["DraftKings"]["spread"] == {"bets": {"home": 0.55, "away": 0.45},
                                                       "money": {"home": 0.64, "away": 0.36}}
    assert SP.parse({"error": "unauthorized"}) == [] and SP.parse(None) == []


def test_the_boards_games_are_matched_by_name_or_code():
    games = [{"away": "DEN", "home": "KC"}, {"away": "LA", "home": "SEA"}, {"away": "NYJ", "home": "NE"}]
    got = SP.match(SP.parse(DOCUMENTED) + SP.parse(NESTED), games)
    assert set(got) == {"DEN@KC", "LA@SEA"}, got
    assert got["DEN@KC"]["_at"] == "2026-10-25T15:00:00Z"
    coded = SP.match([{"away": "den", "home": "kc", "books": {"DraftKings": {}}}], games)
    assert set(coded) == {"DEN@KC"}


def test_the_sentence_leads_with_draftkings_adds_circa_and_calls_it_context():
    books = SP.match(SP.parse(DOCUMENTED), [{"away": "DEN", "home": "KC"}])["DEN@KC"]
    text = SP.words(books, "KC", "DEN")
    assert text.startswith("Public betting at DraftKings: 72% of the bets and 58% of the money on KC to cover; "
                           "61% of the bets and 40% of the money on the over"), text
    assert "At Circa, where bigger bettors play, 65% of the spread money is on DEN" in text
    assert text.endswith("Who the public backs is context; the line already prices it")
    ml_only = {"FanDuel": {"moneyline": {"bets": {"home": 0.3, "away": 0.7}}}}
    assert SP.words(ml_only, "KC", "DEN").startswith("Public betting at FanDuel: 70% of the bets on DEN to win")
    assert SP.words({}, "KC", "DEN") == "" and SP.words({"_at": "x"}, "KC", "DEN") == ""


def test_off_until_the_key_is_set_and_the_key_never_in_the_url():
    saved = os.environ.pop(SP.ENV, None)
    try:
        assert SP.fetch("nfl") is None
        result = {"games": [{"away": "DEN", "home": "KC"}]}
        msg = SP.attach_to_board(result, "nfl")
        assert msg.startswith("Public betting: off") and "setenv.sh SHARPAPI_KEY" in msg
        assert "betting_splits" not in result
    finally:
        if saved is not None:
            os.environ[SP.ENV] = saved
    src = open(os.path.join(ROOT, "engine", "splits.py"), encoding="utf-8").read()
    assert '"X-API-Key": key' in src and "{key}" not in SP.URL and "api_key" not in SP.URL


def test_a_refusal_says_why_and_the_client_says_who_it_is():
    import io
    import urllib.error
    import urllib.request
    seen = []

    def refuse(body):
        def opener(req, timeout=0):
            seen.append(req)
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, io.BytesIO(body.encode()))
        return opener
    real, real_path = urllib.request.urlopen, SP._cache_path
    SP._cache_path = (lambda league, _d=tempfile.mkdtemp(): os.path.join(_d, f"sharpsplits_{league}.json"))
    try:
        urllib.request.urlopen = refuse('{"error": {"message": "Betting splits require the Pro plan"}}')
        try:
            SP.fetch("nfl", key="sk-test-secret", ttl=0)
            raise AssertionError("a 403 must raise")
        except SP.Refused as exc:
            assert exc.status == 403 and "require the Pro plan" in str(exc) and "sk-test" not in str(exc)
        req = seen[-1]
        assert req.get_header("X-api-key") == "sk-test-secret" and "sk-test" not in req.full_url
        assert req.get_header("User-agent") == SP.AGENT, "never urllib's default name"
        msg = SP.attach_to_board({"games": []}, "nfl", fetcher=lambda lg: SP.fetch(lg, key="sk-test-secret", ttl=0))
        assert msg == "Public betting unavailable (SharpAPI HTTP 403: Betting splits require the Pro plan)", msg
        urllib.request.urlopen = refuse("<html><head><title>Attention Required</title></head></html>")
        try:
            SP.fetch("nfl", key="k", ttl=0)
        except SP.Refused as exc:
            assert "a firewall in front of it" in str(exc)
    finally:
        urllib.request.urlopen, SP._cache_path = real, real_path


def test_a_reading_is_on_the_board_kept_in_the_history_and_paid():
    hist = os.path.join(tempfile.mkdtemp(), "h.jsonl")
    result = {"games": [{"away": "DEN", "home": "KC"}, {"away": "LA", "home": "SEA"}]}
    msg = SP.attach_to_board(result, "nfl", fetcher=lambda league: DOCUMENTED, history=hist)
    assert msg == "Public betting: 1 of 2 game(s)", msg
    assert result["betting_splits"]["DEN@KC"]["DraftKings"]["spread"]["bets"]["home"] == 0.72
    rows = [json.loads(x) for x in open(hist, encoding="utf-8")]
    assert len(rows) == 1 and rows[0]["game"] == "DEN@KC" and rows[0]["sport"] == "nfl"

    def broken(league):
        raise TimeoutError("slow")
    assert SP.attach_to_board(result, "nfl", fetcher=broken) == "Public betting unavailable (TimeoutError)"
    assert "betting_splits" in gate.PAID_KEYS


def test_the_report_and_the_build_carry_it():
    rep = open(os.path.join(ROOT, "engine", "gamereport.py"), encoding="utf-8").read()
    assert '(c.result.get("betting_splits") or {}).get(f"{c.away}@{c.home}")' in rep
    build = open(os.path.join(ROOT, "nfl_build.py"), encoding="utf-8").read()
    assert build.index('_splits.attach_to_board(result, "nfl")') < build.index("_greport.attach(result")
    from engine import gamereport as R
    board = {"date": "2026-W08", "games": [{"away": "DEN", "home": "KC", "date": "2026-10-25", "spread": -3.5,
                                             "total": 44.5, "home_ml": -180, "away_ml": 150}],
             "betting_splits": SP.match(SP.parse(DOCUMENTED), [{"away": "DEN", "home": "KC"}])}
    built = R.build(board["games"][0], board, names={})
    market = json.dumps(next(s for s in built["sections"] if s["key"] == "market"), ensure_ascii=False)
    assert "Public betting at DraftKings: 72% of the bets" in market


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
