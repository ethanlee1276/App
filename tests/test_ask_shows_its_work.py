"""Ask Qellys shows its work: the steps as they happen, the numbers as cards,
and what to ask next (engine/askcards, engine/askbot, server.py _ask_stream,
web/js/ask.js).

Ethan, 2026-10-27: "go on to looking at our Ask Kelly feature and auditing
that and making that look better visually, and then also making it function
better ... do it better." The assistants we looked at (FanDuel's AceAI,
Action Network's Playbook, Rithmm's Scout) show a spinner and then an
answer; this one says what it is reading while it reads it, draws the
lookups' own numbers under the answer, and offers the next question.

What these hold: a lookup is said in words before it answers, once; the
cards are the tools' own numbers, one of each kind and two at most, and a
card never appears from a failed lookup; the start/sit call is the
compare's own; the next questions never repeat the one asked; the loop
tells each step, a reader who leaves never stops the answer, and a cached
answer keeps its cards; the stream opens only after every check and ends
in the answer or the failure `_ask` would have sent; the page reads the
stream, draws the steps in the waiting bubble, the cards in the answer and
the next questions under the newest one, and styles every class it draws.

Run directly: `python3 tests/test_ask_shows_its_work.py`
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import askbot as AB                                # noqa: E402
from engine import askcards as AC                              # noqa: E402
from engine import explainer as EX                             # noqa: E402

_TMP = Path(tempfile.mkdtemp())
AB.CACHE_PATH = _TMP / "ask_cache.json"
AB.USAGE_PATH = _TMP / "ask_usage.json"

ASK_JS = (ROOT / "web" / "js" / "ask.js").read_text(encoding="utf-8")
ASK_CSS = (ROOT / "web" / "css" / "ask.css").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")

HITS = {"player": "Josh Allen", "sport": "nfl", "stat": "Passing Yards", "line": 259.5, "side": "under",
        "last_10_games": [{"vs": "MIA", "value": 233.0}, {"vs": "NE", "value": 281.0}],
        "last_5": {"games": 5, "over": 2, "under": 3, "under_hit_rate": 0.6, "average": 241.2},
        "last_10": {"games": 10, "over": 4, "under": 6, "under_hit_rate": 0.6},
        "season_2026": {"games": 8, "over": 3, "under": 5, "under_hit_rate": 0.625},
        "every_stored_game": {"games": 73, "over": 31, "under": 41, "push": 1, "under_hit_rate": 0.569},
        "against": {"opponent": "Chiefs", "games": 4, "over": 1, "under": 3, "under_hit_rate": 0.75}}
SHOP = {"picks": [{"league": "nfl", "pick": "Josh Allen UNDER 259.5 Passing Yards", "our_price": -108,
                   "books": [{"book": "DraftKings", "line": 259.5, "over_odds": -112, "under_odds": -108},
                             {"book": "FanDuel", "line": 259.5, "over_odds": -108, "under_odds": -112}],
                   "best_price_at_this_line": {"book": "DraftKings", "odds": -108},
                   "line_move": {"open": 262.5, "current": 259.5, "delta": -3}}]}
RECORD = {"since": "2026-08-01", "all_bets": {"settled": 430, "wins": 233, "losses": 197, "roi": 0.062,
                                              "net_units": 19.1},
          "last_30_days": {"wins": 60, "losses": 51, "net_units": 4.2}}
FANTASY = {"scoring": "PPR", "players": [
    {"player": "A Back", "team": "PHI", "position": "RB", "opponent": "DAL", "projected_points": 15.2},
    {"player": "B Back", "team": "MIA", "position": "RB", "opponent": "NYJ", "projected_points": 12.0,
     "injury": "Questionable"}],
    "compare": {"call": {"start": "A Back", "order": ["A Back", "B Back"], "text": "Start A Back: 64% to outscore."},
                "pairs": [], "notes": []}}


# --- the words, the cards, the next questions -------------------------------------------------
def test_a_lookup_is_said_in_words_before_it_answers():
    assert AC.step_label("prop_hit_rate", {"player": "Josh Allen", "stat": "passing yards"}) == \
        "Checking Josh Allen’s passing yards history against the line"
    assert AC.step_label("line_shop", {"query": "Allen pass yds"}) == "Comparing every book’s price for Allen pass yds"
    assert AC.step_label("tonight_board", {"sport": "nfl"}) == "Reading tonight’s NFL board"
    assert AC.step_label("team_history", {"team": "Lions", "opponent": "Packers"}) == "Looking up Lions against Packers"
    assert AC.step_label("fantasy_points", {"players": ["A", "B"]}) == "Scoring A, B in fantasy points"
    assert AC.step_label("web_search", None) == "Searching the web"
    assert AC.step_label("something_new", {}) == "Looking it up"
    assert AC.step_label("player_history", "not a dict") == "Pulling a game log", "a bad input never raises"


def test_the_hit_card_is_the_tools_own_tallies():
    c = AC.hits_card(HITS)
    assert c["kind"] == "hits" and c["side"] == "under" and c["line"] == 259.5
    assert [w["label"] for w in c["windows"]] == ["Last 5", "Last 10", "2026", "All", "vs Chiefs"]
    assert c["windows"][0] == {"label": "Last 5", "hit": 3, "of": 5, "rate": 0.6, "avg": 241.2}
    assert c["windows"][3]["of"] == 72, "a push is not a decided game"
    assert c["games"] == [{"vs": "MIA", "value": 233.0}, {"vs": "NE", "value": 281.0}]
    for bad in ({"error": "no player named"}, {"found": False}, {"player": "X"}):
        assert AC.hits_card(bad) is None, bad


def test_the_price_record_and_start_sit_cards():
    p = AC.prices_card(SHOP)
    assert p["best"] == "DraftKings" and p["best_odds"] == -108 and p["move"] == {"open": 262.5, "current": 259.5}
    assert AC.prices_card({"found": False}) is None and AC.prices_card({"picks": [{"books": []}]}) is None
    r = AC.record_card(RECORD)
    assert (r["wins"], r["losses"], r["roi"], r["units"]) == (233, 197, 0.062, 19.1)
    assert r["last_30"] == {"wins": 60, "losses": 51, "net_units": 4.2}
    assert AC.record_card({"all_bets": {}}) is None, "nothing settled, no card"
    s = AC.startsit_card(FANTASY)
    assert [x["player"] for x in s["players"]] == ["A Back", "B Back"] and s["players"][1]["injury"] == "Questionable"
    assert s["call"] == {"start": "A Back", "text": "Start A Back: 64% to outscore."}, "the compare's own call"
    assert AC.startsit_card({"players": FANTASY["players"][:1]}) is None, "one player is not a start/sit"


def test_one_card_of_each_kind_and_two_at_most():
    calls = [("prop_hit_rate", {}, HITS), ("prop_hit_rate", {}, HITS), ("line_shop", {}, SHOP),
             ("our_record", {}, RECORD), ("injuries", {}, {"rows": []})]
    got = AC.cards(calls)
    assert [c["kind"] for c in got] == ["hits", "prices"]
    assert AC.cards([("prop_hit_rate", {}, {"error": "x"})]) == []
    assert AC.cards(None) == []


def test_the_next_questions_follow_the_answer_and_never_repeat_the_question():
    calls = [("prop_hit_rate", {"player": "Josh Allen"}, HITS)]
    got = AC.follow_ups("Is Josh Allen over 259.5?", calls, "nfl")
    assert got[0] == "What’s the best price on Josh Allen?" and len(got) == 3
    shop = AC.follow_ups("x", calls + [("line_shop", {"query": "Allen"}, SHOP)], "nfl")
    assert "What’s the best price on Josh Allen?" not in shop, "it already looked the prices up"
    assert "How has our record been lately?" not in AC.follow_ups("How has our record been lately?", [], "nfl")
    team = AC.follow_ups("x", [("team_history", {"team": "Lions"}, {})], "nfl")
    assert team[0] == "How have the Lions done lately?"
    assert AC.follow_ups("x", [], "")[0] == "What’s the best bet on tonight’s board?", "no double space"


# --- the loop, the answer, the cache ----------------------------------------------------------
def _block(**kw):
    return types.SimpleNamespace(**kw)


class Script:
    """Rounds: a list of (tool, input) calls, or the answer's text."""
    def __init__(self, *steps):
        self.steps = list(steps)
        self.messages = types.SimpleNamespace(create=self._create)

    def _create(self, **kw):
        step = self.steps.pop(0) if self.steps else "Done."
        use = types.SimpleNamespace(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
                                    cache_creation_input_tokens=0)
        if isinstance(step, str):
            return types.SimpleNamespace(content=[_block(type="text", text=step)], stop_reason="end_turn", usage=use)
        return types.SimpleNamespace(content=[_block(type="tool_use", id=f"t{n}", name=name, input=args)
                                              for n, (name, args) in enumerate(step)],
                                     stop_reason="tool_use", usage=use)


def _req():
    return {"system": [{"type": "text", "text": "s"}], "messages": [{"role": "user", "content": "q"}],
            "boards": {}, "league": "nfl", "data_dir": _TMP, "matched": 0, "focused": False, "sources": [],
            "about": {}, "facts": {}}


def _with(run_tool, build=None):
    saved = (AB.run_tool, AB.build_request, AB.model_name, AB.web_tool)
    AB.run_tool = run_tool
    if build:
        AB.build_request = build
    AB.model_name = lambda: "claude-test"
    AB.web_tool = lambda model: None
    return saved


def _restore(saved):
    AB.run_tool, AB.build_request, AB.model_name, AB.web_tool = saved


def test_the_loop_tells_each_step_and_keeps_every_call():
    outs = {"prop_hit_rate": HITS, "line_shop": SHOP}
    saved = _with(lambda name, args, boards, league, data_dir=None: outs[name])
    told = []
    try:
        req = {**_req(), "on_step": told.append, "used": set()}
        AB.converse(Script([("prop_hit_rate", {"player": "Josh Allen", "stat": "passing yards"}),
                            ("line_shop", {"query": "Allen"})], "Lean under."), "m", req, [])
    finally:
        _restore(saved)
    assert told == ["Checking Josh Allen’s passing yards history against the line",
                    "Comparing every book’s price for Allen"]
    assert req["steps"] == told and [c[0] for c in req["calls"]] == ["prop_hit_rate", "line_shop"]


def test_a_reader_who_leaves_never_stops_the_answer():
    saved = _with(lambda name, args, boards, league, data_dir=None: HITS)

    def gone(label):
        raise BrokenPipeError("the page left")
    try:
        req = {**_req(), "on_step": gone, "used": set()}
        resp, _src, made = AB.converse(Script([("prop_hit_rate", {"player": "A"})],
                                              [("prop_hit_rate", {"player": "B"})], "Done here."), "m", req, [])
    finally:
        _restore(saved)
    assert made == 2 and req["on_step"] is None and len(req["steps"]) == 2
    assert AB.answer_text(resp) == "Done here."


def test_the_answer_carries_its_cards_and_the_cache_keeps_them():
    AB.CACHE_PATH.unlink(missing_ok=True)
    saved = _with(lambda name, args, boards, league, data_dir=None: {"prop_hit_rate": HITS,
                                                                     "line_shop": SHOP}[name],
                  build=lambda *a, **k: _req())
    key_saved = AB.answer_key
    AB.answer_key = lambda *a, **k: "k1"
    try:
        script = Script([("prop_hit_rate", {"player": "Josh Allen", "stat": "passing yards"}),
                         ("line_shop", {"query": "Allen"})], "Lean under, mildly.")
        out = AB.ask({}, "Is Josh Allen over 259.5?", board_name="recommendations.json", client=script,
                     data_dir=_TMP)
        again = AB.ask({}, "Is Josh Allen over 259.5?", board_name="recommendations.json", client=Script("x"),
                       data_dir=_TMP)
    finally:
        _restore(saved)
        AB.answer_key = key_saved
    assert [c["kind"] for c in out["cards"]] == ["hits", "prices"] and out["steps"][0].startswith("Checking")
    assert out["follow"] and "best price" not in " ".join(out["follow"]), "prices were looked up already"
    assert again["cached"] and again["cards"] == out["cards"] and again["follow"] == out["follow"]


# --- the stream ---------------------------------------------------------------------------------
def _handler():
    import server
    h = object.__new__(server.Handler)
    h.wfile = io.BytesIO()
    h.sent_headers = []
    h.send_response = lambda code: h.sent_headers.append(("status", code))
    h.send_header = lambda k, v: h.sent_headers.append((k, v))
    h.end_headers = lambda: None
    h._is_https = lambda: False
    return h


def _events(raw: bytes):
    out = []
    for chunk in raw.decode().split("\n\n"):
        kind = re.search(r"^event: (.*)$", chunk, re.M)
        data = re.search(r"^data: (.*)$", chunk, re.M)
        if kind and data:
            out.append((kind.group(1), json.loads(data.group(1))))
    return out


def test_the_stream_tells_the_steps_then_the_answer_or_the_failure():
    h = _handler()
    saved = AB.ask, AB.sign_turn, AB.count_question
    counted = []

    def fake_ask(*a, on_step=None, **k):
        on_step("Reading tonight’s NFL board")
        return {"text": "Lean under.", "refused": False, "matched": 1, "focused": False, "sources": [],
                "cached": False, "steps": ["Reading tonight’s NFL board"], "cards": [{"kind": "record"}],
                "follow": ["How has our record been lately?"]}
    AB.ask, AB.sign_turn, AB.count_question = fake_ask, (lambda t: "sig"), counted.append
    try:
        h._ask_stream(AB, EX, {}, "q", [], "", "recommendations.json", {}, "reader")
        ev = _events(h.wfile.getvalue())

        def broken(*a, **k):
            raise EX.Unavailable("the model is down")
        AB.ask = broken
        h2 = _handler()
        h2._ask_stream(AB, EX, {}, "q", [], "", "recommendations.json", {}, "reader")
        ev2 = _events(h2.wfile.getvalue())
    finally:
        AB.ask, AB.sign_turn, AB.count_question = saved
    assert ("Content-Type", "text/event-stream; charset=utf-8") in h.sent_headers
    assert ("Cache-Control", "no-store, no-transform") in h.sent_headers, "no proxy compresses or holds it"
    assert [k for k, _ in ev] == ["step", "answer"] and ev[0][1] == {"label": "Reading tonight’s NFL board"}
    ans = ev[1][1]
    assert ans["text"] == "Lean under." and ans["sig"] == "sig" and ans["cards"] == [{"kind": "record"}]
    assert ans["follow"] == ["How has our record been lately?"] and counted == ["reader"]
    assert ev2 == [("fail", {"status": 503})], "the detail goes to the log, not the page"


def test_the_stream_opens_only_after_every_check():
    body = SERVER.split("    def _ask(self, body):")[1].split("\n    def ")[0]
    i = body.index('if body.get("stream") is True:')
    for check in ("self._rate_limited(", "self._entitled(conn, who)", "AB.configured()", "AB.over_limit(me)",
                  "AB.board_at(", "boards[league] = got"):
        assert body.index(check) < i, check


# --- the page -----------------------------------------------------------------------------------
def test_the_page_reads_the_stream_and_draws_the_steps_cards_and_next():
    assert "stream: ASK_STREAMS" in ASK_JS and "async function askReadStream(res)" in ASK_JS
    assert '/event-stream/.test(res.headers.get("Content-Type") || "")' in ASK_JS, "JSON still works"
    assert '<span class="ask-sr">Looking it up…</span>${askStepsHTML()}' in ASK_JS
    i = ASK_JS.index("function askTurnHTML(")
    turn = ASK_JS[i:ASK_JS.index("\n}\n", i)]
    assert "${askCardsHTML(t)}${askSourcesHTML(t)}" in turn and 'live ? askNextHTML(t) : ""' in turn
    j = ASK_JS.index("function askTypeOut(")
    typed = ASK_JS[j:ASK_JS.index("\n}\n", j)]
    assert "askBodyHTML(t.text) + askCardsHTML(t) + askSourcesHTML(t)" in typed and "askNextHTML(t)" in typed
    assert "cards: body.cards || [], follow: body.follow || []" in ASK_JS


def test_every_class_the_room_draws_new_is_styled():
    drawn = set(re.findall(r"\b(ask-(?:steps|card[a-z-]*|hw[a-z-]*|bars?[a-z-]*|line|pr|rec|ss-r|next[a-z-]*))\b",
                           ASK_JS))
    styled = set(re.findall(r"\.(ask-[a-z-]+)", ASK_CSS))
    assert drawn and drawn <= styled, sorted(drawn - styled)


def test_the_cards_in_node():
    if not shutil.which("node"):
        return
    i = ASK_JS.index("const ASK_CARD = {")
    j = ASK_JS.index("/* WHAT TO ASK NEXT", i)
    harness = ("const escapeHtml=(x)=>String(x==null?'':x);const escapeAttr=escapeHtml;\n" + ASK_JS[i:j]
               + "\nconst cards=" + json.dumps(AC.cards([("prop_hit_rate", {}, HITS), ("line_shop", {}, SHOP)])) + ";"
               + "const rec=" + json.dumps(AC.record_card(RECORD)) + ";"
               + "process.stdout.write(JSON.stringify([askCardsHTML({cards}), ASK_CARD.record(rec)]));")
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-500:]
    html, rec = json.loads(out.stdout)
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    assert "Josh Allen Passing Yards · under 259.5" in text and "60% 3/5 Last 5" in text
    assert html.count('class="ask-bar ') == 2 and 'class="ask-bar hit in"' in html, "233 under the line: a hit"
    assert 'class="ask-bar miss in"' in html, "281 over it: a miss"
    assert "DraftKings 259.5 -108 best" in text and "FanDuel 259.5 -112" in text, "the under side, the best marked"
    assert "Line 262.5 at open, 259.5 now" in text
    rtext = " ".join(re.sub(r"<[^>]+>", " ", rec).split())
    assert "233–197" in rtext and "+6.2%" in rtext and "+19.1u" in rtext and "Last 30 days: 60–51, +4.2u" in rtext


if __name__ == "__main__":
    fails = 0
    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for name, fn in tests:
        try:
            fn()
            print(f"  ok  {name}")
        except Exception as exc:                                    # noqa: BLE001
            import traceback
            fails += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
            traceback.print_exc(limit=4)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
