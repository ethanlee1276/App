"""Nothing on the request path waits forever or spends without a ceiling.

Audit 2026-09-30, E-2 / F-11 / C-4 (roadmap #14).
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_the_app_socket_has_a_timeout():
    import server
    assert getattr(server.Handler, "timeout", None) == 30


def test_caddy_bounds_reads_and_bodies():
    c = (ROOT / "deploy" / "Caddyfile").read_text()
    assert "read_header 10s" in c and "read_body 30s" in c and "idle 2m" in c
    assert "max_size 1MB" in c


def test_the_model_clients_have_a_timeout_and_one_retry():
    for f, t in (("engine/explainer.py", "timeout=30.0"), ("engine/askbot.py", "timeout=60.0")):
        src = (ROOT / f).read_text()
        assert f"anthropic.Anthropic({t}, max_retries=1)" in src, f


def test_the_explainer_key_is_the_facts_not_the_build():
    from engine import explainer as ex
    a = ex.facts_digest({"player": "A", "line": 1.5})
    assert a == ex.facts_digest({"line": 1.5, "player": "A"})
    assert a != ex.facts_digest({"player": "A", "line": 2.5})


def test_the_explainer_has_a_daily_ceiling():
    from engine import explainer as ex
    old = os.environ.get("QB_EXPLAIN_DAILY_MAX")
    os.environ["QB_EXPLAIN_DAILY_MAX"] = "2"
    ex._DAY.update(day="", n=0)
    try:
        assert ex._spend_ok() and ex._spend_ok() and not ex._spend_ok()
    finally:
        ex._DAY.update(day="", n=0)
        if old is None:
            os.environ.pop("QB_EXPLAIN_DAILY_MAX", None)
        else:
            os.environ["QB_EXPLAIN_DAILY_MAX"] = old


if __name__ == "__main__":
    import inspect
    fns = [f for n, f in sorted(globals().items()) if n.startswith("test_") and inspect.isfunction(f)]
    for f in fns:
        f()
        print(f"  ok  {f.__name__}")
    print(f"\n{len(fns)} tests passed.")
