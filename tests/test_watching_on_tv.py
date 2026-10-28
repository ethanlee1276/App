"""Watching on TV: the game page and its chat held back by the reader's
delay, so nothing spoils a play the TV has not shown yet (js/detail.js
tvPick, js/chat.js chatReady).

What these hold: with no delay the newest copy is drawn; with one, the
newest copy fetched at least that long ago (the oldest kept until the
buffer is that deep), three minutes kept; a delayed page does not take the
fast scoreboard's "final" early, and this game's strip chip is held too;
the chat holds a message younger than the delay, never the reader's own,
and appends it once when its time comes.

    python3 tests/test_watching_on_tv.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DET = (ROOT / "web" / "js" / "detail.js").read_text()
CHAT = (ROOT / "web" / "js" / "chat.js").read_text()


def _node(prog):
    out = subprocess.run(["node", "-e", prog], capture_output=True, text=True)
    if out.returncode == 127:
        return None
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_page_draws_the_copy_from_the_delay_ago():
    src = DET[DET.index("const TV_KEY"):DET.index("function pbpTvHTML(")]
    got = _node("""
      const store = {}; const localStorage = { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = String(v); } };
      const window = {};
      """ + src + """
      const out = {};
      const t0 = 1000000;
      out.off = tvPick("nfl_1", "A", { n: "A" }, t0).raw;
      tvPick("nfl_1", "B", { n: "B" }, t0 + 15000);
      tvPick("nfl_1", "C", { n: "C" }, t0 + 31000);
      store.qb_tv_delay_v1 = "30";
      out.held30 = tvPick("nfl_1", "D", { n: "D" }, t0 + 46000);
      store.qb_tv_delay_v1 = "60";
      out.young = tvPick("nfl_1", "D", { n: "D" }, t0 + 47000).raw;
      out.window = window.QB_TV_DELAY;
      store.qb_tv_delay_v1 = "45";
      out.odd = tvPick("nfl_1", "D", { n: "D" }, t0 + 48000).held;
      out.trimmed = tvPick("nfl_1", "E", { n: "E" }, t0 + 400000) && _tv.list.map((x) => x.raw);
      out.other = (store.qb_tv_delay_v1 = "10", tvPick("nfl_2", "Z", { n: "Z" }, t0 + 500000).raw);
      console.log(JSON.stringify(out));""")
    if got is None:
        return
    assert got["off"] == "A", "no delay: the newest"
    assert got["held30"]["raw"] == "B" and got["held30"]["held"] == 30, "30s: the newest fetched 30s or more ago"
    assert got["young"] == "A", "the buffer is not yet that deep: the oldest kept"
    assert got["window"] == 60, "the chat reads the same delay"
    assert got["odd"] == 0, "only the choices offered"
    assert got["trimmed"] == ["E"], "three minutes kept"
    assert got["other"] == "Z", "a new game starts its own buffer"


def test_the_page_holds_the_final_and_the_strip_and_offers_the_choice():
    fn = DET[DET.index("async function renderPbpPage("):]
    i = fn.index("const tvHeld = tvPick(")
    assert fn.index("if (state.view !== \"pbp\") return;") < i < fn.index("chatMount(league, event, d);"), \
        "the chat's scoreboard is the held one too"
    assert "? { ...g, live: { ...(g.live || {}), ...(d.live || {}) } } : g));" in fn[i:i + 600]
    assert '(!tvHeld.held && fast && (fast.live || {}).state === "final")' in fn
    assert "${pbpTvHTML(d)}${pbpSpoilHTML(d, league, event)}${pbpAwayHTML(d, league)}" in DET
    assert "callit: pbpTvHTML(d) + pbpSpoilHTML(d, league, event) + pbpAwayHTML(d, league)" in DET, "basketball and hockey too"
    tv = DET[DET.index("function pbpTvHTML("):]
    assert 'if (!d || (d.live || {}).state !== "live") return "";' in tv[:120]


def test_the_chat_holds_a_young_message_but_never_the_readers_own():
    src = CHAT[CHAT.index("function chatReady("):]
    src = src[:src.index("\n}\n") + 3]
    got = _node("""
      const window = { QB_TV_DELAY: 30 };
      """ + src + """
      const now = Date.now() / 1000;
      console.log(JSON.stringify([chatReady({ at: now - 5 }), chatReady({ at: now - 40 }), chatReady({ at: now - 5, own: true }),
        (window.QB_TV_DELAY = 0, chatReady({ at: now }))]));""")
    if got is None:
        return
    assert got == [False, True, True, True]
    app = CHAT[CHAT.index("function chatAppend("):CHAT.index("function chatScrolled(")]
    assert "CH.held = pool.filter((m) => !chatReady(m));" in app
    assert '!body.querySelector(`.gch-msg[data-id="${Number(m.id)}"]`)' in app, "appended once"
    assert "CH.msgs.filter(want).filter(chatReady)" in CHAT
    assert "m.body && chatReady(m)" in CHAT, "the card and the bar too"


if __name__ == "__main__":
    fails = ran = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                ran += 1
                print(f"  ok  {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
            except Exception as exc:                          # noqa: BLE001
                fails += 1
                print(f"  FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{ran} tests passed." if not fails else f"\n{fails} failed")
    sys.exit(1 if fails else 0)
