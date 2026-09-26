"""A restart is a pause, not a 502.

Ethan, 2026-09-09, with a photo of his phone on opener day: "the site
crashed. It won't load anything and won't show logos."

It had not crashed. `systemctl restart` is a hard stop and start —
`Type=simple`, no `ExecReload`, no signal handling in launch.py — so for
a second or two the socket refuses connections, and Caddy's default for a
single upstream is to give up on the first refused dial and answer 502.

A 502 IS WORSE THAN A WAIT, and that is the whole reason this file
exists. `boardFetch` treats an ANSWERED request as the wire being up — a
404 is not a wire failure, and neither is a 502 — so the page does not
say it could not reach us. It draws an empty board, which reads as "the
model has nothing for you today" on the night of the Week 1 opener.

Eight deploys in one afternoon is eight of those windows.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _caddy():
    return open(os.path.join(HERE, "deploy", "Caddyfile"), encoding="utf-8").read()


def _directives(src):
    """Lines that are configuration, not prose.

    The Caddyfile argues with itself in comments as much as the
    stylesheet does, and the paragraph added beside this change names
    `retry_match` in order to explain why it is absent. A grep over the
    raw file finds five of them and none are real.
    """
    return "\n".join(l for l in src.splitlines()
                     if l.strip() and not l.strip().startswith("#"))


def _blocks(src):
    return re.findall(r"reverse_proxy 127\.0\.0\.1:8000 \{(.*?)\n\t*\}", src, re.S)


def test_every_proxy_block_waits_for_the_app_to_come_back():
    blocks = _blocks(_caddy())
    assert len(blocks) == 5, f"the proxy blocks moved: {len(blocks)}"
    for i, b in enumerate(blocks):
        assert "lb_try_duration" in b, \
            f"proxy block {i} still answers 502 the moment a dial is refused"


def test_the_wait_outlasts_a_restart():
    """The app takes a second or two to bind. A one-second window would
    turn most of the outage into a 502 anyway and look like a fix."""
    m = re.search(r"lb_try_duration (\d+)s", _directives(_caddy()))
    assert m, "no retry window at all"
    assert int(m.group(1)) >= 5, \
        f"{m.group(1)}s is shorter than a restart takes"


def test_only_a_refused_dial_is_replayed():
    """WITHOUT a `retry_match`, Caddy retries only when it could not get a
    connection — the request was never delivered, so replaying it is safe
    even for a POST. A request the app ACCEPTED and then failed is not
    retried, which is the property that keeps a double-charge impossible
    on /api/billing/checkout."""
    code = _directives(_caddy())
    assert not re.search(r"(?m)^\s*retry_match\b", code), \
        "retry_match would replay requests the app already accepted"


def test_the_config_still_parses_as_far_as_we_can_tell_here():
    """`caddy validate` runs in deploy.sh and is the real gate; there is
    no caddy binary on the box that runs this suite. Balanced braces is
    the one structural claim that can be made without it, and it is the
    failure mode a hand-edit actually produces."""
    code = _directives(_caddy())
    assert code.count("{") == code.count("}"), "unbalanced braces"
    assert "caddy validate" in open(
        os.path.join(HERE, "deploy", "deploy.sh"), encoding="utf-8").read(), \
        "the real validation step left deploy.sh"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
