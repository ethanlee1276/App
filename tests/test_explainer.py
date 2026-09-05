"""The plain-English explainer: one pick, read back from its own numbers.

Ethan, 2026-09-05: "a plain English explainer per pick". engine/explainer
hands the model the card's facts and nothing else, caches the answer
per build, says when it is not configured, and turns a refusal into a
sentence. The endpoint is gated like the board; the page draws every
state as words.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_TMP = tempfile.mkdtemp()
os.environ["QB_EXPLAIN_CACHE"] = os.path.join(_TMP, "explain_cache.json")
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("QB_EXPLAIN_MODEL", None)

from engine import explainer as EX                                       # noqa: E402

APP = (ROOT / "web" / "js" / "app.js").read_text()
SERVER = (ROOT / "server.py").read_text()
CSS = (ROOT / "web" / "css" / "styles.css").read_text()

ROW = {
    "player": "Amon-Ra St. Brown", "team": "DET", "opponent": "NO", "position": "WR",
    "market": "rec_yds", "market_label": "Receiving yards", "side": "OVER", "line": 74.5,
    "odds": -115, "book": "FanDuel", "projection": 81.2, "proj_low": 62.0, "proj_high": 101.0,
    "hit_prob": 0.58, "fair_prob": 0.52, "edge": 0.06, "grade": "B+", "stake_units": 1.0,
    "reasons": [f"reason {i}" for i in range(12)], "warnings": ["a warning"],
    "game_script": {"archetype": "Favorite runs", "summary": "Lions favored by 6 at 48.5", "read": "x"},
    "form": {"last3": 80.0, "last5": 77.0, "season": 74.0, "career": 70.0},
    "recent_values": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    "logs": [{"week": 1, "value": 90}], "chain": {"steps": [1]}, "checks": [1], "comps": [1],
    "all_lines": [{"book": "DK", "line": 74.5}], "headshot": "http://x", "headline": "SB over",
}
BOARD = {"date": "2026-09-05", "built_at": "2026-09-05T10:00:00", "recommendations": [ROW],
         "game_bets": [{"pick": "DET", "market": "spread", "side": "DET", "line": -6.5, "odds": -110}],
         "long_shots": [], "most_likely": []}


class _Client:
    """The shape engine/explain uses of the SDK client, and nothing more."""
    def __init__(self, text="Plain words.", stop="end_turn", raise_=None):
        self.calls = []
        self.messages = types.SimpleNamespace(create=self._create)
        self._text, self._stop, self._raise = text, stop, raise_

    def _create(self, **kw):
        self.calls.append(kw)
        if self._raise:
            raise self._raise
        block = types.SimpleNamespace(type="text", text=self._text)
        return types.SimpleNamespace(content=[block] if self._text is not None else [],
                                     stop_reason=self._stop)


def _env(model="m-test"):
    os.environ["QB_EXPLAIN_MODEL"] = model
    EX.forget_all()


def test_the_facts_are_the_cards_own_and_nothing_heavy():
    f = EX.facts_for(ROW)
    for k in ("player", "line", "odds", "projection", "hit_prob", "fair_prob", "edge", "grade",
              "stake_units", "reasons", "warnings", "headline"):
        assert k in f, k
    for k in ("logs", "chain", "checks", "comps", "all_lines", "headshot", "form"):
        assert k not in f, f"{k} is not a fact the explainer may be shown"
    assert f["reasons"] == [f"reason {i}" for i in range(8)], "capped at eight, like the card"
    assert f["game_script"] == "Lions favored by 6 at 48.5", "the script's sentence, not its arithmetic"
    assert f["form_averages"] == {"last3": 80.0, "last5": 77.0, "season": 74.0}
    assert f["recent_games_values"] == list(range(1, 11))
    assert "position" in f and EX.facts_for({"player": "x", "odds": None, "reasons": []}) == {"player": "x"}


def _node(js):
    node = shutil.which("node")
    if not node:
        return None
    i = APP.index("function propId(")
    fn = APP[i:APP.index("\n}", i) + 2]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(f"{fn}\nconsole.log(JSON.stringify((() => {{ {js} }})()));"); path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip())


def test_the_pick_id_matches_the_pages_own_rule():
    rows = [ROW, dict(ROW, line=20.0), dict(ROW, line=100.5), dict(ROW, line=None), dict(ROW, side="UNDER")]
    ours = [EX.pick_id(r) for r in rows]
    theirs = _node("return " + json.dumps(rows) + ".map(propId);")
    if theirs is None:
        print("  SKIP node not installed"); return
    assert ours == theirs, (ours, theirs)
    for r, wanted in zip(rows, theirs):
        assert EX.same_pick(r, wanted), wanted
    assert not EX.same_pick(ROW, theirs[1]) and not EX.same_pick(ROW, "x|y")


def test_the_row_is_found_on_any_of_the_four_lists():
    assert EX.find_row(BOARD, EX.pick_id(ROW)) is ROW
    gb = BOARD["game_bets"][0]
    assert EX.find_row(BOARD, "|spread|DET|-6.5") is gb, "a game bet has no player and is still findable"
    assert EX.find_row(BOARD, "Nobody|rec_yds|OVER|74.5") is None


def test_not_configured_is_said_not_guessed():
    os.environ.pop("QB_EXPLAIN_MODEL", None); os.environ.pop("ANTHROPIC_API_KEY", None)
    assert EX.configured() is False
    try:
        EX.explain("b.json", BOARD, EX.pick_id(ROW), client=_Client())
        raise AssertionError("a call went out with no model name")
    except EX.NotConfigured:
        pass
    _env()
    assert EX.configured() is False, "a model name without a key is not configured"
    try:
        EX.explain("b.json", BOARD, EX.pick_id(ROW))
        raise AssertionError("a client was built with no key")
    except EX.NotConfigured:
        pass


def test_one_call_per_pick_per_build_and_the_answer_is_cached_on_disk():
    _env()
    c = _Client("The Lions' receiver is projected over the line.")
    pid = EX.pick_id(ROW)
    a = EX.explain("recommendations.json", BOARD, pid, client=c)
    assert a["text"].startswith("The Lions") and a["cached"] is False and a["refused"] is False
    b = EX.explain("recommendations.json", BOARD, pid, client=c)
    assert b["cached"] is True and b["text"] == a["text"] and len(c.calls) == 1
    assert os.path.exists(os.environ["QB_EXPLAIN_CACHE"]), "the answer is on disk for the next reader"
    EX._MEM = None                                                     # a restarted server
    d = EX.explain("recommendations.json", BOARD, pid, client=c)
    assert d["cached"] is True and len(c.calls) == 1
    fresh = dict(BOARD, built_at="2026-09-05T11:00:00")
    e = EX.explain("recommendations.json", fresh, pid, client=c)
    assert e["cached"] is False and len(c.calls) == 2, "a new build is a new answer"
    other = EX.explain("mlb_recommendations.json", BOARD, pid, client=c)
    assert other["cached"] is False and len(c.calls) == 3, "keyed by board too"


def test_the_call_is_shaped_as_the_sdk_documents_and_shows_only_the_facts():
    _env("m-test")
    c = _Client()
    EX.explain("b.json", BOARD, EX.pick_id(ROW), client=c)
    kw = c.calls[0]
    assert kw["model"] == "m-test", "the model comes from the environment, never the code"
    assert kw["max_tokens"] == EX.MAX_TOKENS and kw["system"] == EX.SYSTEM
    assert "thinking" not in kw and "temperature" not in kw, "adaptive thinking by omission; no sampling knobs"
    assert len(kw["messages"]) == 1 and kw["messages"][0]["role"] == "user"
    user = kw["messages"][0]["content"]
    assert '"line": 74.5' in user and "Amon-Ra" in user and "Lions favored" in user
    assert "logs" not in user and "chain" not in user and "http://x" not in user
    assert str(EX.WORDS) in EX.SYSTEM and "ONLY the facts" in EX.SYSTEM and "Never tell" in EX.SYSTEM


def test_a_refusal_is_a_sentence_and_is_cached_as_one():
    _env()
    c = _Client("", stop="refusal")
    pid = EX.pick_id(ROW)
    got = EX.explain("b.json", BOARD, pid, client=c)
    assert got["refused"] is True and "declined" in got["text"]
    again = EX.explain("b.json", BOARD, pid, client=c)
    assert again["cached"] is True and again["refused"] is True and len(c.calls) == 1


def test_failures_are_unavailable_never_an_answer():
    _env()
    for bad in (_Client(None), _Client("", stop="end_turn"), _Client(raise_=RuntimeError("boom"))):
        EX.forget_all()
        try:
            EX.explain("b.json", BOARD, EX.pick_id(ROW), client=bad)
            raise AssertionError("an empty or failed call produced an answer")
        except EX.Unavailable:
            pass
    try:
        import anthropic
        try:
            import httpx2 as _hx                                       # the 1.x SDK's transport
        except ImportError:
            import httpx as _hx
        err = anthropic.APIConnectionError(request=_hx.Request("POST", "https://api.anthropic.com/v1/messages"))
        EX.forget_all()
        try:
            EX.explain("b.json", BOARD, EX.pick_id(ROW), client=_Client(raise_=err))
            raise AssertionError("a typed SDK error produced an answer")
        except EX.Unavailable as exc:
            assert "APIConnectionError" in str(exc)
    except ImportError:
        print("  (anthropic not installed here — typed-error path not exercised)")
    try:
        EX.explain("b.json", BOARD, "Nobody|x|OVER|1", client=_Client())
        raise AssertionError("a pick not on the board was explained")
    except KeyError:
        pass


def test_the_cache_is_bounded():
    _env()
    old = EX.CACHE_MAX
    EX.CACHE_MAX = 3
    try:
        for i in range(5):
            EX.remember(f"k{i}", {"text": "t", "at": i})
        mem = EX._load()
        assert set(mem) == {"k2", "k3", "k4"}, mem
    finally:
        EX.CACHE_MAX = old


def test_the_endpoint_is_gated_rate_limited_and_honest_about_configuration():
    i = SERVER.index("def _explain(self, q):")
    body = SERVER[i:SERVER.index("\n    def ", i + 10)]
    assert 'if parsed.path in ("/api/explain", "/api/explain/"):' in SERVER
    assert 'self._rate_limited(RATE_EXPLAIN_PER_MIN, "explain")' in body
    assert "RATE_EXPLAIN_PER_MIN = 20" in SERVER
    assert body.index("self._entitled(conn, who)") < body.index("EX.configured()") < body.index("EX.explain("), \
        "entitlement is checked before anything is read or spent"
    assert "401 if not who else 402" in body
    assert "GATE_.full_board_file(board) is None" in body, "the board name is resolved, never joined"
    assert body.count('"configured":false') == 2 and "except EX.Unavailable" in body and "except KeyError" in body


def test_the_page_draws_every_state_as_a_sentence():
    i = APP.index("async function explainPick()")
    body = APP[i:APP.index("\n}", i)]
    assert 'data-explain aria-controls="pp-explain"' in APP and 'id="pp-explain" class="pp-explain" hidden' in APP
    assert "/api/explain?board=" in body and "encodeURIComponent(propId(r))" in body
    for status in ("401", "402", "404", "429", "503"):
        assert f"res.status === {status}" in body, status
    assert "body.configured === false" in body and "not switched on" in body
    assert "Writing the explanation" in body
    assert "if (findProp(state.propId) !== r) return;" in body, "an answer for a pick the page has left is not drawn"
    assert "Written by an AI from the numbers on this card" in APP
    assert ".pp-explain {" in CSS and ".pp-explain-note {" in CSS
    got = _node('return [propId({player:"A B",market:"m",side:"OVER",line:1.5})];')
    if got is not None:
        assert got == ["A B|m|OVER|1.5"]


def test_the_board_name_is_the_pages_own_file():
    node = shutil.which("node")
    if not node:
        print("  SKIP node not installed"); return
    i = APP.index("function boardNameFor(")
    fn = APP[i:APP.index("\n}", i) + 2]
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(fn + '\nconsole.log(JSON.stringify([boardNameFor({fallback:"data/mlb_recommendations.json"}), boardNameFor({}), boardNameFor(null)]));')
        path = fh.name
    try:
        out = subprocess.run([node, path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    assert json.loads(out.stdout) == ["mlb_recommendations.json", "", ""], out.stdout


def test_the_deploy_docs_carry_the_one_install_and_the_two_values():
    d = (ROOT / "docs" / "DEPLOY.md").read_text()
    assert "pip install anthropic" in d and "QB_EXPLAIN_MODEL" in d and "ANTHROPIC_API_KEY" in d
    assert "explain_cache.json" in d
    assert "## 9. The explainer" in (ROOT / "docs" / "DROPLET_CHECKS.md").read_text()


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn(); print(f"  ok  {name}")
            except Exception:
                fails += 1; print(f"FAIL {name}"); traceback.print_exc()
    tests = [n for n in globals() if n.startswith("test_")]
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} FAILED")
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(1 if fails else 0)
