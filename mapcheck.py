#!/usr/bin/env python3
"""Do the docs' ✅ rows still point at code that exists?

    python3 mapcheck.py            # report drift
    python3 mapcheck.py --quiet    # exit code only, for CI

WHY

Each model doc ends with an implementation map: one row per rule in the
spec, a ✅ when it is built, and the evidence — the file and usually the
constant or function that does it. Those rows are the only place the
system says what it has actually finished, and they are prose, so nothing
stops them rotting. A constant gets renamed during a fix and the row still
claims the old name; a module moves and the row still names the old path.
The map then reads as authoritative and is quietly wrong, which is worse
than having no map at all.

This is deliberately the DUMB half of the audit. It cannot tell whether
`engine/rules.py` really implements a forcing rule — that is a judgement
call and belongs to a person, or to the weekly sweep. It only checks the
thing a machine can check and a human never will: that every path and
symbol a ✅ row cites is still there.

WHAT IT WILL NOT DO

Guess. Backticks in these docs hold plenty that is not code — market
names, prose, JSON keys, shell fragments. Anything that does not look
unmistakably like a path or a code symbol is skipped rather than reported,
because an audit with false positives is one you stop reading, and then
the real drift goes past unnoticed too.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"

#: A row of an implementation map: pipe-delimited, and carrying a tick.
ROW = re.compile(r"^\|(?P<rule>[^|]+)\|(?P<state>[^|]*✅[^|]*)\|(?P<why>.+)\|\s*$")

#: Anything inside single backticks.
TICKED = re.compile(r"`([^`]+)`")

#: A path we can check: ends .py/.js/.css/.md and has no spaces.
PATHISH = re.compile(r"^[\w./-]+\.(py|js|css|md|json|yml)$")

#: A code symbol worth checking: CONSTANT_CASE, or dotted/attr access, or
#: a call. Deliberately narrow — `hit_prob` alone is as likely to be a
#: JSON key as a function, and checking it would invent failures.
SYMBOL = re.compile(r"^(?:[A-Za-z_][\w.]*\.)?([A-Z][A-Z0-9_]{3,}|[a-z_]{3,})(?:\(\))?$")


def _rows(path: Path):
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        m = ROW.match(line.strip())
        if m and "---" not in m.group("rule"):
            yield n, m.group("rule").strip(), m.group("why").strip()


def _paths_in(text: str) -> list[str]:
    return [t for t in TICKED.findall(text) if PATHISH.match(t)]


def _symbols_in(text: str) -> list[str]:
    out = []
    for t in TICKED.findall(text):
        if PATHISH.match(t):
            continue
        m = SYMBOL.match(t.strip())
        if m:
            out.append(m.group(1))
    return out


#: Where code lives. Checked once and reused — the alternative is walking
#: the tree per symbol, and there are a few hundred symbols.
def _sources() -> list[Path]:
    out = [p for p in ROOT.glob("*.py")]
    for sub in ("engine", "tests", "web/js", "web/css", ".github/workflows"):
        d = ROOT / sub
        if d.exists():
            out += [p for p in d.rglob("*")
                    if p.is_file() and p.suffix in (".py", ".js", ".css", ".yml")
                    and "__pycache__" not in p.parts]
    return out


_SRC: list[Path] = []
_BLOB = ""


def _corpus() -> str:
    global _SRC, _BLOB
    if not _BLOB:
        _SRC = _sources()
        _BLOB = "\n".join(p.read_text(encoding="utf-8", errors="ignore")
                          for p in _SRC)
    return _BLOB


def _resolve(path_str: str) -> bool:
    """Does this file exist — under the cited path, or anywhere?

    The docs cite bare names (`rules.py`) as often as full paths, and
    resolving only the literal string reported ten renames that had not
    happened. An audit that cries wolf is one nobody reads, and then the
    real drift walks past too.
    """
    if (ROOT / path_str).exists():
        return True
    name = Path(path_str).name
    return any(p.name == name for p in (_SRC or _sources()))


def audit() -> list[dict]:
    """Every ✅ row whose cited code cannot be found ANYWHERE.

    Deliberately not "found in the file the row names". A row citing the
    right symbol in the wrong module is a judgement call about how tidy
    the prose is; a row citing a symbol that no longer exists is drift.
    Only the second is reported, because only the second is a fact.
    """
    findings: list[dict] = []
    _corpus()
    for doc in sorted(DOCS.glob("*.md")):
        for n, rule, why in _rows(doc):
            for p in _paths_in(why):
                if not _resolve(p):
                    findings.append({"doc": doc.name, "line": n, "rule": rule,
                                     "kind": "path", "what": p})
            for s in _symbols_in(why):
                if not re.search(rf"\b{re.escape(s)}\b", _BLOB):
                    findings.append({"doc": doc.name, "line": n, "rule": rule,
                                     "kind": "symbol", "what": s})
    return findings


def main(argv: list[str]) -> int:
    quiet = "--quiet" in argv
    found = audit()
    checked = sum(1 for d in sorted(DOCS.glob("*.md")) for _ in _rows(d))
    if not found:
        if not quiet:
            print(f"✅ implementation map clean — {checked} ✅ row(s) checked, "
                  f"every cited file and symbol exists")
        return 0
    if not quiet:
        print(f"{len(found)} row(s) cite code that is not there "
              f"({checked} checked):\n")
        for f in found:
            where = f" in {f['in']}" if f.get("in") else ""
            print(f"  {f['doc']}:{f['line']}  {f['kind']}: `{f['what']}`{where}")
            print(f"      row: {f['rule'][:88]}")
        print("\nA ✅ row is the system's own claim that something is "
              "finished. One pointing at a renamed constant or a moved file "
              "is not a typo — it is the map disagreeing with the code, and "
              "the map is what gets believed.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
