"""Every field we publish, and whether any page reads it.

Ethan, 2026-09-09: *"we are using every single piece of data we have"*.

The FILE half of that question was easy and came back clean — every
`web/data/*.json` has a reader, including the ones whose names are built
at runtime (`standings_${sport}.json` and friends, which a naive grep
reports as orphans).

The FIELD half is this. A key the build computes every cycle and no page
ever names is one of two things, and they look identical from here:

  * a feature that silently is not showing — the number is there, correct,
    and nobody sees it; or
  * an internal the build needs and the front end was never meant to read.

Both are worth knowing. The first is a bug with no symptom. The second is
fine, and saying so out loud is how it stays fine.

WHY THIS IS A TOOL AND NOT A TEST. It reads `web/data/`, which is build
output and not in git — a test that read it would pass or fail depending
on what happened to be on the machine, which is the exact failure
tests/test_backup_remote.py has a long comment about. So it runs on
demand, against real data, on the box where real data lives.

WHAT IT CANNOT SEE, stated plainly so the output is not over-read: the
front end reaches some fields dynamically (`market_words[m]`,
`teams[abbr]`), and a lookup table read that way is reported as unused
when it is not. Anything listed here is a LEAD, not a verdict.

    python3 -m engine.feedaudit                 # every feed
    python3 -m engine.feedaudit record.json     # one of them
    python3 -m engine.feedaudit --all           # include the quiet ones
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"

#: Read by the build, never meant for a page. Named one at a time, with a
#: reason, because "it is probably internal" is how a real gap hides.
INTERNAL = {
    "whole_board": "gate.redact's own bookkeeping — how much it stripped",
    "team_count": "a build-side sanity count on the roster pull",
    "unfinished_skipped": "how many rows the standings build declined",
    "generated": "a build stamp; the page shows generated_at instead",
    "bucket_pts": "the calibration chart is drawn from `buckets`",
    "min_row_n": "the floor the CLV board applies before it will draw",
    "stats_season": "which season the offseason fallback pulled from",
    # CLASSIFIED BY LOOKING, not by assuming. It is the touch fit the
    # buy/sell and draft boards use to turn volume into expected points,
    # and it is the basis behind the `expected_ppg` column those boards
    # already show. It stays off the page because half of it is fit on
    # volume that barely exists — a tight end takes ~0 carries a season,
    # so the per-carry coefficient beside his per-target one is noise
    # wearing two decimal places. A number like that needs its sample
    # printed next to it or it should not be printed at all.
    "rates": "the touch fit behind expected_ppg; per-position, build-side",
}

#: Maps the front end indexes by a variable rather than by name —
#: `market_words[m]`, `teams[abbr]`. Their inner keys are DATA, so
#: reporting them is noise, and noise is how a tool like this gets
#: ignored. The map itself is still checked; only the descent is skipped.
DYNAMIC = {"market_words", "teams", "days", "by_sport", "tax_by_book",
           "by_type", "by_book", "by_market", "by_reason", "by_route"}

#: Names too short or too common to grep for without drowning in noise.
_MIN_LEN = 4

#: A key that is a DATE, an ALL-CAPS team abbreviation or a number is a
#: row identifier, not a field somebody forgot to render.
_DATA_KEY = re.compile(r"^(\d{4}-\d{2}-\d{2}|[A-Z0-9]{2,5}|\d+)$")


def _readers() -> str:
    out = []
    for rel in ("js/app.js", "js/visuals.js", "index.html", "sw.js"):
        p = WEB / rel
        if p.is_file():
            out.append(p.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(out)


def _walk(obj, prefix="", depth=0, out=None):
    """Top-level keys, one level of nesting, and the shape of list rows."""
    if out is None:
        out = []
    if depth > 1 or not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if _DATA_KEY.match(k):
            continue                     # a row id, not a field name
        out.append(prefix + k)
        if depth == 0 and isinstance(v, dict) and k not in DYNAMIC:
            _walk(v, k + ".", depth + 1, out)
        if depth == 0 and isinstance(v, list) and v and isinstance(v[0], dict):
            for kk in v[0]:
                out.append(k + "[]." + kk)
    return out


def _emptiness(obj, key):
    """Is this key empty everywhere it appears? ``None`` when unknown.

    THREE CATEGORIES, NOT TWO, and the third is the useful one. A field
    no page reads which is FULL of real numbers is something computed
    every cycle for nobody — the interesting kind. One that is also empty
    is usually just a corner this machine has no data for, which is why
    the report says "on this machine" and not "dead".
    """
    seen, empty = 0, 0
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k == key:
                    seen += 1
                    if v in (None, "", 0, 0.0, [], {}):
                        empty += 1
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(cur, list):
            stack.extend(x for x in cur if isinstance(x, (dict, list)))
    if not seen:
        return None
    return empty == seen


def _named(leaf: str, blob: str) -> bool:
    """Does anything the browser loads mention this key by name?

    Quoted, dotted or bracketed — `"foo"`, `.foo`, `[foo` — so a word that
    merely appears in prose does not count as a reader.
    """
    return bool(re.search(r"""["'.\[]""" + re.escape(leaf) + r"\b", blob))


def audit(paths=None, show_internal=False, data_dir=None, blob=None):
    """`data_dir` and `blob` are for the tests.

    The real answer lives in build output, which is not in git, so a test
    that read `web/data` would be asserting facts about whatever machine
    it ran on. Handing both sides in means the TOOL can be tested without
    the tool's own subject matter being on disk.
    """
    blob = _readers() if blob is None else blob
    data = Path(data_dir) if data_dir else WEB / "data"
    files = sorted(p for p in data.glob("*.json")
                   if not paths or p.name in paths)
    lines, leads = [], 0
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            lines.append(f"{p.name}: unreadable — {exc}")
            continue
        if not isinstance(d, dict):
            continue
        rows = []
        for key in _walk(d):
            leaf = key.split(".")[-1].split("[]")[-1].lstrip(".")
            if len(leaf) < _MIN_LEN or _named(leaf, blob):
                continue
            why = INTERNAL.get(leaf)
            if why and not show_internal:
                continue
            rows.append((key, why))
        if not rows:
            continue
        # GROUPED BY NAME, because thirty lines of `money_bets` in thirty
        # scopes is ONE decision to make, not thirty. The count says how
        # widely it is published, which is itself a signal about whether
        # somebody meant it.
        by_name = {}
        for key, why in rows:
            leaf = key.split(".")[-1].split("[]")[-1].lstrip(".")
            by_name.setdefault(leaf, [why, []])[1].append(key)
        lines.append(f"\n{p.name}")
        for leaf in sorted(by_name, key=lambda n: (-len(by_name[n][1]), n)):
            why, where = by_name[leaf]
            tail = (f"{where[0]}" if len(where) == 1
                    else f"{where[0]} and {len(where) - 1} more")
            blank = _emptiness(d, leaf)
            mark = "  [always empty]" if blank else ""
            lines.append(f"    {leaf:26s} {tail}{mark}")
            if why:
                lines.append(f"    {'':26s} internal — {why}")
        leads += sum(1 for why, _ in by_name.values() if not why)
    lines.append(f"\n{leads} field(s) published and named by no page.")
    if leads:
        lines.append("Each is either a feature nobody can see or an internal")
        lines.append("nobody has written down. Both are worth ten seconds.")
        lines.append("Fields reached dynamically (market_words[m]) show up")
        lines.append("here too — check before believing.")
        lines.append("")
        lines.append("[always empty] IN THE FILE ON THIS MACHINE — which on a")
        lines.append("dev box usually means this box has no data for it, not")
        lines.append("that the build never fills it. Run this where the real")
        lines.append("data lives before deleting anything.")
        lines.append("Anything WITHOUT that mark is carrying real values that")
        lines.append("no page shows, which is the shorter and more interesting")
        lines.append("list.")
    return lines, leads


def _main(argv):
    show = "--all" in argv
    data_dir = None
    if "--data-dir" in argv:
        i = argv.index("--data-dir")
        data_dir = argv[i + 1] if i + 1 < len(argv) else None
        argv = argv[:i] + argv[i + 2:]
    names = [a for a in argv if not a.startswith("-")]
    lines, leads = audit(names or None, show_internal=show, data_dir=data_dir)
    for line in lines:
        print(line)
    # Never nonzero: this is a reading, not a gate. A tool that fails the
    # deploy over a lead nobody has classified yet would be turned off.
    return 0


if __name__ == "__main__":                       # pragma: no cover
    raise SystemExit(_main(sys.argv[1:]))
