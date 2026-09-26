"""Ask searches the web for what our own data does not hold.

Ethan, 2026-09-23, asked whether Ask should reach past our data for the
news, trades and injury updates we do not store: "Yeah add it". What that
has to mean, and what each test below holds it to:

  * the search is Anthropic's server-side web_search tool: the version that
    filters results in code on models new enough for it, the basic one
    otherwise; at most WEB_MAX_USES searches a call and WEB_DAILY_CAP a day
    (QB_ASK_WEB_DAILY, 0 turns it off); the books' own sites left out;
  * every number a bettor acts on still comes from our data, and the prompt
    says so;
  * an answer that used the web cites its pages, as links, and is never
    served again from the answer cache;
  * a search the API pauses is handed back unchanged and resumed, a bounded
    number of times;
  * an organisation with search switched off in the Claude Console still
    gets its answer, without the search;
  * the searches are counted in the usage log at a cent apiece.

Every fixture is built in a temp directory; nothing here reads the box.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine import askbot as AB                                # noqa: E402

_TMP = Path(tempfile.mkdtemp())
DATA = _TMP / "web_data"
DATA.mkdir()
AB.CACHE_PATH = _TMP / "ask_cache.json"
AB.USAGE_PATH = _TMP / "ask_usage.json"
AB.HISTORY_DB = str(_TMP / "no_history.db")
os.environ.pop("QB_ASK_WEB_DAILY", None)
os.environ.pop("QB_ASK_MODEL", None)
NFL = {"sport": "nfl", "date": "2026-W03", "built_at": "2026-09-23T12:00:00", "games": []}
BOARDS = {"nfl": NFL}
NS = types.SimpleNamespace
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()


def _cite(url, title="A story"):
    return NS(type="web_search_result_location", url=url, title=title, cited_text="…")


def _usage(searches=0):
    return NS(input_tokens=0, output_tokens=0, cache_read_input_tokens=0, cache_creation_input_tokens=0,
              server_tool_use=NS(web_search_requests=searches))


def _searched_answer():
    return NS(stop_reason="end_turn", usage=_usage(1), content=[
        NS(type="text", text="Let me check the latest.", citations=None),
        NS(type="server_tool_use", id="srvtoolu_1", name="web_search", input={"query": "Kyle Allen Lions"}),
        NS(type="web_search_tool_result", tool_use_id="srvtoolu_1",
           content=[NS(type="web_search_result", url="https://www.espn.com/nfl/story/1", title="Allen signs",
                       encrypted_content="x", page_age="today")]),
        NS(type="text", text="Kyle Allen signed with Detroit on Monday",
           citations=[_cite("https://www.espn.com/nfl/story/1", "Lions sign Kyle Allen")]),
        NS(type="text", text=", as their third quarterback.",
           citations=[_cite("https://www.espn.com/nfl/story/1"), _cite("javascript:alert(1)"),
                      _cite("https://apnews.com/article/2", "AP: Lions add a QB")]),
    ])


class _Client:
    def __init__(self, *responses, refuse_web=None):
        self.responses, self.calls, self.refuse_web = list(responses), [], refuse_web
        self.messages = NS(create=self.create)

    def create(self, **kw):
        self.calls.append(kw)
        if self.refuse_web and any(t.get("name") == "web_search" for t in kw["tools"]):
            raise self.refuse_web
        return self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]


def _ask(client, question="Did the Lions sign a quarterback?"):
    return AB.ask(NFL, question, client=client, boards=BOARDS, board_name="recommendations.json", data_dir=DATA)


def _fresh():
    AB.CACHE_PATH.unlink(missing_ok=True)
    AB.USAGE_PATH.unlink(missing_ok=True)
    AB._WEB["off"] = False


def test_the_web_tool_by_model_capped_and_kept_off_the_books():
    _fresh()
    w = AB.web_tool("claude-sonnet-5")
    assert w == {"type": "web_search_20260209", "name": "web_search", "max_uses": AB.WEB_MAX_USES,
                 "blocked_domains": ["fanduel.com", "draftkings.com"],
                 "user_location": {"type": "approximate", "country": "US", "timezone": "America/New_York"}}
    assert AB.web_tool("claude-opus-5-5")["type"] == "web_search_20260209"
    assert AB.web_tool("claude-haiku-4-5")["type"] == "web_search_20250305", \
        "a model before 4.6 gets the basic search"
    os.environ["QB_ASK_WEB_DAILY"] = "0"
    try:
        assert AB.web_tool("claude-sonnet-5") is None, "0 turns search off"
    finally:
        os.environ.pop("QB_ASK_WEB_DAILY")
    AB.USAGE_PATH.write_text(json.dumps({"days": {TODAY: {"web_searches": AB.WEB_DAILY_CAP}}}))
    assert AB.web_tool("claude-sonnet-5") is None, "the day's searches are spent"
    AB.USAGE_PATH.write_text(json.dumps({"days": {TODAY: {"web_searches": AB.WEB_DAILY_CAP - 1}}}))
    assert AB.web_tool("claude-sonnet-5") is not None
    _fresh()


def test_the_prompt_keeps_every_number_a_bettor_acts_on_ours():
    system = " ".join(AB.SYSTEM.split())
    for rule in ("Look in our data first", "search the web with web_search",
                 "Numbers a bettor acts on (odds, lines, prices, picks, probabilities, our record) come only "
                 "from our data, never from a web page", "when a site's odds differ from ours, give ours",
                 "Say when a fact came from the web", "never pass off a site's pick or prediction as ours",
                 "our data has nothing on it"):
        assert rule in system, rule


def test_a_web_answer_cites_its_pages_as_links_and_is_never_cached():
    _fresh()
    client = _Client(_searched_answer())
    out = _ask(client)
    assert out["text"] == "Kyle Allen signed with Detroit on Monday, as their third quarterback.", \
        "the answer, not the 'let me check' before the search"
    web = [s for s in out["sources"] if s.get("url")]
    assert web == [{"label": "espn.com", "url": "https://www.espn.com/nfl/story/1", "title": "Lions sign Kyle Allen",
                    "prop": ""},
                   {"label": "apnews.com", "url": "https://apnews.com/article/2", "title": "AP: Lions add a QB",
                    "prop": ""}], "each page once, and only a real address"
    assert out["sources"][:2] == web, "the pages cited lead the chips"
    tools = client.calls[0]["tools"]
    assert tools[:len(AB.TOOLS)] == AB.TOOLS and tools[-1]["name"] == "web_search"
    again = _ask(client)
    assert again["cached"] is False and len(client.calls) == 2, "the web moves: asked twice, searched twice"
    day = json.loads(AB.USAGE_PATH.read_text())["days"][TODAY]
    assert day["web_searches"] == 2 and day["usd"] == 0.02, "a cent a search"
    assert "searches" in AB.usage_report(1).splitlines()[0]
    _fresh()


def test_the_pages_cited_lead_the_chips_ahead_of_our_lookups():
    _fresh()
    (DATA / "standings_nfl.json").write_text(json.dumps({"source": "league", "season": 2026, "groups": [
        {"label": "NFC North", "teams": [{"rank": 1, "team": "DET", "record": "3-0"}]}]}))
    lookup = NS(stop_reason="tool_use", usage=_usage(), content=[
        NS(type="tool_use", id="toolu_1", name="standings", input={"sport": "nfl"})])
    out = _ask(_Client(lookup, _searched_answer()), "Are the Lions first, and did they sign a QB?")
    assert [s["label"] for s in out["sources"]] == ["espn.com", "apnews.com", "NFL standings"], \
        "a cited page is never pushed off the answer by our own chips"
    _fresh()


def test_a_paused_search_is_handed_back_unchanged_and_resumed():
    _fresh()
    paused = NS(stop_reason="pause_turn", usage=_usage(1), content=[
        NS(type="server_tool_use", id="srvtoolu_9", name="web_search", input={"query": "Lions trade"})])
    client = _Client(paused, _searched_answer())
    out = _ask(client)
    assert out["text"].startswith("Kyle Allen signed")
    first, second = client.calls
    assert second["messages"][:-1] == first["messages"], "nothing added but the paused turn"
    assert second["messages"][-1] == {"role": "assistant", "content": paused.content}, \
        "handed back exactly as it came, no 'continue' message"
    stuck = _Client(paused)
    req = AB.build_request(NFL, "Lions trade?", data_dir=DATA, boards=BOARDS)
    req["web"] = AB.web_tool("claude-sonnet-5")
    AB.converse(stuck, "claude-sonnet-5", req, [])
    assert len(stuck.calls) == 1 + AB.MAX_CONTINUATIONS, "resumed a bounded number of times"
    _fresh()


class _Refused(Exception):
    status_code = 400


def test_search_switched_off_in_the_console_still_gets_an_answer():
    _fresh()
    plain = NS(stop_reason="end_turn", usage=_usage(), content=[NS(type="text", text="Our data has nothing on it.",
                                                                   citations=None)])
    client = _Client(plain, refuse_web=_Refused("invalid_request_error: web search is not enabled"))
    out = _ask(client)
    assert out["text"] == "Our data has nothing on it."
    assert [any(t.get("name") == "web_search" for t in c["tools"]) for c in client.calls] == [True, False]
    assert AB._WEB["off"] is True and AB.web_tool("claude-sonnet-5") is None, "and it stops asking"
    other = _Client(plain, refuse_web=_Refused("max_tokens: too large"))
    AB._WEB["off"] = False
    try:
        _ask(other, "Something else?")
        raise AssertionError("any other 400 is a real failure")
    except AB._ex.Unavailable:
        pass
    assert AB._WEB["off"] is False
    _fresh()


def test_the_page_turns_only_a_real_address_into_a_link():
    js = (ROOT / "web" / "js" / "app.js").read_text()
    fn = js[js.index("function askSourcesHTML"):js.index("function askTurnHTML")]
    assert "/^https?:\\/\\//i.test(String(s.url" in fn, "javascript: and data: stay text"
    assert 'target="_blank" rel="noopener noreferrer"' in fn
    assert "escapeAttr(s.url)" in fn and "escapeHtml(s.label)" in fn
    css = (ROOT / "web" / "css" / "styles.css").read_text()
    assert "a.ask-chip.web {" in css


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
            traceback.print_exc(limit=3)
    print(f"\n{len(tests) - fails} tests passed." if not fails else f"\n{fails} failed.")
    sys.exit(1 if fails else 0)
