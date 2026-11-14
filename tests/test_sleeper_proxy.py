"""Tests for the Sleeper proxy allowlist — must never become an open proxy."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import sleeper_path_ok


def test_allowed_paths():
    assert sleeper_path_ok("user/ethanlee1276")
    assert sleeper_path_ok("user/123456789/leagues/nfl/2026")
    assert sleeper_path_ok("league/987654321")
    assert sleeper_path_ok("league/987654321/rosters")
    assert sleeper_path_ok("league/987654321/users")
    assert sleeper_path_ok("players/nfl")


def test_rejected_paths():
    # Writes, traversal, other hosts' shapes, and junk all bounce.
    assert not sleeper_path_ok("")
    assert not sleeper_path_ok("user/../secrets")
    assert not sleeper_path_ok("user/name/leagues/nba/2026")
    assert not sleeper_path_ok("league/abc/rosters")
    assert not sleeper_path_ok("players/nba")
    assert not sleeper_path_ok("http://evil.example/steal")
    assert not sleeper_path_ok("user/a b")
    assert not sleeper_path_ok("league/1/transactions/1")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
