"""The copy of a board a browser downloads: without what no page reads.

The site audit, 2026-09-24 (docs/AUDIT_2026-09-24.md, M-3). Two things
rode every published board to every phone and were never drawn:

* EVERY PROP ROW'S WHOLE ALTERNATE LADDER — `alt_lines`, the sharp
  book's `alt_sharp_lines` on the same rungs, and `rung_probs`, the
  model's number at each rung. The build reads them (`likely._best_rung`
  picks the likelier rung from them) and the droplet's report tools read
  them (`potd_report._ladders`), both from the PRIVATE copy in
  data/built/ through `gate.board_source`. No script in web/js reads any
  of the three.
* `board_shelves` REPEATED EVERY MOST LIKELY ROW IN FULL — each shelf's
  `rows` are the same dicts as `most_likely`'s, filtered by market
  (`engine/boards.shelves`), so the board carried its Most Likely section
  twice (27 KB against 26 KB on the demo NFL board).

WHAT THIS DOES. `served()` returns the board with the three ladder keys
removed at any depth and each shelf's rows replaced by `row_ix`, their
positions in `most_likely`. The page rebuilds the rows from those
positions (`boardShelves` in web/js/app.js). A shelf holding a row that is
not in `most_likely` keeps its rows exactly as they were — it is left
alone rather than guessed at.

WHERE IT RUNS. On the two ways a board reaches a browser: the public file
`gate.publish` writes into web/data (and so the light copy, published the
same way), and the subscriber copy `server.board_bytes` serves from
data/built. The private copy on disk is untouched — it is the truth every
tool on the droplet reads.
"""

from __future__ import annotations

import json

#: Keys no page reads, dropped at any depth. Distinctive names, so a walk
#: over the whole board cannot catch an unrelated field.
DROP_KEYS = ("alt_lines", "alt_sharp_lines", "rung_probs")

#: The build's diagnostics for the droplet's tools, dropped from the top
#: of the board (the audit's L-7: published, never drawn). `td_census` is
#: read by engine/devigcheck, `bar_status` by `homecheck.py inputs`, both
#: from the private copy.
DROP_TOP = ("td_census", "bar_status")


def _drop(node):
    if isinstance(node, dict):
        return {k: _drop(v) for k, v in node.items() if k not in DROP_KEYS}
    if isinstance(node, list):
        return [_drop(v) for v in node]
    return node


def _key(row) -> str:
    return json.dumps(row, sort_keys=True, default=str)


def _shelves_by_reference(board: dict) -> None:
    shelves = board.get("board_shelves")
    rows = board.get("most_likely")
    if not isinstance(shelves, list) or not isinstance(rows, list):
        return
    where: dict = {}
    for i, r in enumerate(rows):
        where.setdefault(_key(r), i)
    out = []
    for sh in shelves:
        if not isinstance(sh, dict) or not isinstance(sh.get("rows"), list):
            out.append(sh)
            continue
        ix = [where.get(_key(r)) for r in sh["rows"]]
        if any(i is None for i in ix):
            out.append(sh)                      # not ours to guess at
            continue
        slim = {k: v for k, v in sh.items() if k != "rows"}
        slim["row_ix"] = ix
        out.append(slim)
    board["board_shelves"] = out


def served(payload):
    """The board a browser gets. A new object; ``payload`` is untouched."""
    if not isinstance(payload, dict):
        return payload
    out = _drop({k: v for k, v in payload.items() if k not in DROP_TOP})
    _shelves_by_reference(out)
    return out
