"""Bad words on the public feed: slurs refused, swearing masked.

Ethan, 2026-10-06, on the social feed: *"make sure we censor bad words or
make it so users can use bad words."* Both, split by kind:

* **Slurs are refused at write time.** A post, comment, bio or handle
  carrying one is not stored at all and the writer is told why. There
  is no viewer setting that brings them back, because there is nothing
  stored to bring back. This is the line a public page owes the people
  it names.
* **Swearing is stored as written and MASKED on the way out** ("f***"),
  unless the viewer turned on "show strong language" — the reader's
  choice, not the writer's, so nobody meets it who did not ask to.

The lists are rot13-encoded so the source reads clean in a diff and a
grep of the repository does not light up; :func:`_decode` is the whole
cipher. Matching is per word, after undoing the common dodges (``sh1t``,
``a$$``, ``fuuuck``), with a short tail of endings (``-ing``, ``-er``,
``-s``). Whole-word matching is what keeps "class", "assess",
"Scunthorpe" and "Dickens" alone; a handful of words that are never
innocent inside another word (:data:`_ANYWHERE`) are also caught inside
compounds ("dumbfuck"). A filter like this is a floor, not a moderator —
the report button and the owner's hide are the rest of it.
"""

from __future__ import annotations

import codecs
import re
from itertools import groupby


def _decode(words: str) -> list[str]:
    return [codecs.decode(w, "rot13") for w in words.split()]


#: Masked on display (rot13).
_STRONG = _decode(
    "shpx fuvg ovgpu phag nffubyr nff onfgneq qvpx pbpx chffl cvff fyhg "
    "juber gjng cevpx jnaxre ohyyfuvg zbgureshpxre qhzonff wnpxnff qbhpur "
    "qbhpuront gvgf qvyqb wvmm")

#: Refused at write time (rot13).
_SLURS = _decode(
    "avttre avttn snttbg snt ergneq ergneqrq xvxr fcvp fcvpx puvax tbbx "
    "jrgonpx genaal qlxr pbba ornare enturnq gbjryurnq cnxv xlxr")

#: Never innocent inside a longer word, so caught there too (rot13).
_ANYWHERE = _decode("shpx fuvg ovgpu juber avtt")

#: Real words that a pattern above would otherwise catch.
_ALLOW = {"cocky", "cockiness", "shiitake", "shitake", "cocker", "dicker",
          "scunthorpe", "spicy", "spice", "passion"}

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
                       "7": "t", "@": "a", "$": "s"})
_TOKEN = re.compile(r"[A-Za-z0-9@$]+")

_STRONG_TAIL = r"(?:s|es|ed|er|ers|ing|in|y|head|heads|hole|holes|face|bag)?"
_SLUR_TAIL = r"(?:s|z|es)?"


def _pat(term: str) -> str:
    """Each run of letters at least as long as written: 'ass' needs two s,
    so 'as' never matches it, while 'asssss' still does."""
    return "".join(f"{re.escape(c)}{{{len(list(g))},}}" for c, g in groupby(term))


_STRONG_RE = re.compile("^(?:" + "|".join(_pat(t) for t in _STRONG) + ")" + _STRONG_TAIL + "$")
_SLUR_RE = re.compile("^(?:" + "|".join(_pat(t) for t in _SLURS) + ")" + _SLUR_TAIL + "$")
_ANY_RE = re.compile("|".join(_pat(t) for t in _ANYWHERE))
_ANY_SLUR_RE = re.compile(_pat(codecs.decode("avtt", "rot13")))


def _norm(token: str) -> str:
    return re.sub(r"[^a-z]", "", token.lower().translate(_LEET))


def classify(token: str) -> str:
    """'slur', 'strong' or '' for one word."""
    w = _norm(token)
    if not w or w in _ALLOW:
        return ""
    if _SLUR_RE.match(w):
        return "slur"
    if _ANY_SLUR_RE.search(w):
        return "slur"
    hit = _ANY_RE.search(w)
    if _STRONG_RE.match(w) or hit:
        return "strong"
    return ""


def has_slur(text: str) -> bool:
    return any(classify(m.group(0)) == "slur" for m in _TOKEN.finditer(str(text or "")))


def has_strong(text: str) -> bool:
    return any(classify(m.group(0)) for m in _TOKEN.finditer(str(text or "")))


def mask(text: str) -> str:
    """The text with every bad word reduced to its first letter and stars."""
    s = str(text or "")

    def _sub(m):
        tok = m.group(0)
        return tok[0] + "*" * (len(tok) - 1) if classify(tok) else tok
    return _TOKEN.sub(_sub, s)


def check(text: str, what: str = "That") -> str:
    """'' when the text may be stored, else the reason it may not."""
    if has_slur(text):
        return (f"{what} has a slur in it. Swearing is fine (readers can hide it); "
                "slurs are not posted here.")
    return ""


def clean_name(name: str) -> bool:
    """A handle carries no bad word of either kind, in any of its parts."""
    parts = [p for p in re.split(r"[_\W\d]+", str(name or "")) if p] + [str(name or "")]
    return not any(classify(p) for p in parts)
