"""A free file has no private copy: the API serves the public file, the
only copy anything writes.

Ethan, 2026-09-14, the Record page signed in: "Updated
2026-09-10T20:54:17" four days on, the NFL haircut row missing, a
week-old brief — while the same page on another connection was
current. `export_json` writes web/data/record.json and nothing else;
record.json is free and goes through no gate; but /api/board resolved
every name to data/built/<name>, and a private copy of a free file,
once there, is never rewritten. Signed in: the frozen copy. Signed out:
the live file.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import gate  # noqa: E402
import server as S  # noqa: E402


def _tree(tmp):
    web = Path(tmp) / "web" / "data"
    built = Path(tmp) / "data" / "built"
    web.mkdir(parents=True); built.mkdir(parents=True)
    (web / "record.json").write_text(json.dumps({"generated_at": "FRESH", "overall": {}}))
    (built / "record.json").write_text(json.dumps({"generated_at": "FROZEN", "overall": {}}))
    return web, built


def test_a_free_name_resolves_to_no_private_file():
    assert gate.is_free("record.json")
    assert gate.full_board_file("record.json") is None
    assert gate.full_board_file("recommendations.json") is not None   # paid, unchanged


def test_the_api_serves_the_public_copy_of_a_free_file():
    with tempfile.TemporaryDirectory() as tmp:
        web, built = _tree(tmp)
        was = (S.WEB, gate.FULL_DIR)
        S.WEB, gate.FULL_DIR = Path(tmp) / "web", built
        try:
            body, mtime, etag = S.board_bytes("record.json")
            assert body is not None and mtime and etag
            assert json.loads(body)["generated_at"] == "FRESH"
            # The public file changes; the cache follows the stamp.
            (web / "record.json").write_text(json.dumps({"generated_at": "FRESHER"}))
            os.utime(web / "record.json", None)
            body2 = S.board_bytes("record.json")[0]
            assert json.loads(body2)["generated_at"] in ("FRESH", "FRESHER")
            # A paid name still comes from the private directory.
            (built / "recommendations.json").write_text(json.dumps({"recommendations": [1]}))
            assert json.loads(S.board_bytes("recommendations.json")[0])["recommendations"] == [1]
            # And board_source, the internal readers' door, agrees.
            assert gate.board_source(web / "record.json") == web / "record.json"
        finally:
            S.WEB, gate.FULL_DIR = was
            S._BOARD_CACHE.clear()


def test_the_seal_removes_a_private_copy_of_a_free_file():
    keep = os.environ.get("QB_PAYWALL")
    os.environ["QB_PAYWALL"] = "1"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            web, built = _tree(tmp)
            out = gate.seal(web, verbose=False)
            assert "record.json" in out["free"]
            assert "record.json" in (out.get("purged") or []), out
            assert not (built / "record.json").exists()
            assert (web / "record.json").exists()          # the public file stands
            again = gate.seal(web, verbose=False)
            assert "purged" not in again or "record.json" not in again["purged"]
    finally:
        if keep is None:
            os.environ.pop("QB_PAYWALL", None)
        else:
            os.environ["QB_PAYWALL"] = keep


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn(); print(f"  ok  {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")
