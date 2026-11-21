"""The sentences a gate writes when it refuses a pick, told apart from reasons.

Ethan's screenshot of a game's parlays (2026-11-15) showed, under "why" for
DeMario Douglas over 2.5 receptions: "The record shows a blind spot here: nfl
receptions, OVER — said 63%, hit 57% over 732 bets — ran hot; this slice
closed itself". That is the Edge board's loss-pattern veto: the gate that
refused the Edge pick puts its refusal first in the pick's reasons
(engine/betting, `reasons.insert(0, pattern_block)`), and the Most Likely row
and the parlay leg built on the same bet copied the reasons whole. Read under
"why", a refusal reads as an argument for the pick. The Most Likely board
judges the bet on its own bars and its own record (engine/likelyboard), so the
Edge board's refusal is not its reason, and it says its own record in numbers.

`is_refusal` names every such sentence by how its gate opens it, so the rows
that borrow an Edge card's reasons can leave them out.
"""
from __future__ import annotations

import re

#: How each refusing gate opens its sentence.
REFUSAL_HEADS = (
    "The record shows a blind spot here",          # engine/losspatterns.veto
    "Rule proposed by the hypothesis lab",          # engine/hypotheses.blocked
    "This shelf is stopped",                        # engine/shelfstop.blocked
    "Model disagrees with the market by more than",  # engine/betting.IMPLAUSIBLE_EDGE_REASON
)
#: engine/betting: "Edge +2.1% is under the Tier B bar (3.0% post-haircut) — pass, not a lean".
_UNDER_BAR = re.compile(r"^Edge [+−-]?\d[\d.]*% is under the Tier \S+ bar")


def is_refusal(text) -> bool:
    s = str(text or "").strip()
    return s.startswith(REFUSAL_HEADS) or bool(_UNDER_BAR.match(s))


def reasons_only(reasons) -> list:
    """The reasons, without the gates' refusals."""
    return [x for x in reasons or [] if x and not is_refusal(x)]
