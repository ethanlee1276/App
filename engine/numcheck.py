"""Every number a language model writes onto the site must be in its data.

Audit 2026-09-30, P0-3. The nightly postmortem, the weekly brief, the pick
explainer and Ask all hand a model a JSON pack and publish what comes back.
The only guard was a line in the prompt — "use ONLY numbers present in the
JSON" — and a prompt is a request, not a check. A model that writes
"went 14-3" on a 13-4 night puts a false record on the public Record page
under the site's name, and nothing downstream could tell.

This is the check. `scrub(text, pack)` splits the text into sentences and
drops any sentence carrying a number the pack cannot account for, at the
precision the sentence shows it:

  * ``52.4%`` is accounted for by 0.524 (a fraction) or by 52.4;
  * ``+2.1u`` by 2.13 (shown to one decimal);
  * ``14-3`` only by a won/lost pair of 14 and 3 in the pack — or the sum
    of the pairs beside each other, which is how a column says "the night";
  * ``-110`` by -110.

A sentence with no numbers is never touched. Dropped sentences are
returned, and `log_drops` writes them to ``data/llm_drops.jsonl`` with the
pack they were checked against, so a model that keeps inventing is seen.

It is deliberately strict — a dropped true sentence costs a line of prose,
a kept false one costs the record's credibility — and deliberately small:
counts to ten, years and days of a month are free, because a sentence like
"two of the three losses" or "on Sept. 29" is not a claim about the data.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DROPS_PATH = ROOT / "data" / "llm_drops.jsonl"

#: Integers this small are counting words, not claims ("two of three").
FREE_INT = 10

_MONTHS = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|"
           r"july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
           r"dec(?:ember)?)\.?")

# Order matters: the record and date shapes are taken out before the plain
# numbers, so "14-3" is one record rather than 14 and -3.
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{4}-W\d{1,2}\b")
_MONTH_DAY = re.compile(_MONTHS + r"\s+\d{1,2}(?:st|nd|rd|th)?\b", re.I)
_RECORD = re.compile(r"(?<![\d.])(\d{1,4})-(\d{1,4})(?:-(\d{1,4}))?(?!\d|\.\d|%)")
# A number glued to letters ("49ers", "3rd", "7pm") is a name or a word,
# not a claim; a unit ("2.1u", "52%", "3 units") is part of the number.
_NUMBER = re.compile(r"(?<![\w.])([+\-\u2212]?)(\d[\d,]*(?:\.\d+)?)"
                     r"(?:\s?(%|u\b|units?\b)|(?![\w]))")

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘(])")


def _flatten(obj, out: list, pairs: list) -> None:
    """Every number in the pack, and every won/lost pair."""
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
        return
    if isinstance(obj, str):
        for m in re.finditer(r"[+-]?\d+(?:\.\d+)?", obj):
            try:
                out.append(float(m.group(0)))
            except ValueError:
                pass
        return
    if isinstance(obj, dict):
        w = obj.get("won", obj.get("wins", obj.get("w")))
        lo = obj.get("lost", obj.get("losses", obj.get("l")))
        if isinstance(w, (int, float)) and isinstance(lo, (int, float)) \
                and not isinstance(w, bool):
            pairs.append((int(w), int(lo), obj.get("pushed", obj.get("pushes"))))
        for v in obj.values():
            _flatten(v, out, pairs)
        # Siblings that are each a record (one per sport) add up to a night.
        kids = [(v.get("won", v.get("wins")), v.get("lost", v.get("losses")))
                for v in obj.values() if isinstance(v, dict)]
        kids = [(a, b) for a, b in kids
                if isinstance(a, (int, float)) and isinstance(b, (int, float))]
        if len(kids) > 1:
            pairs.append((int(sum(a for a, _ in kids)),
                          int(sum(b for _, b in kids)), None))
        return
    if isinstance(obj, (list, tuple)):
        out.append(float(len(obj)))
        for v in obj:
            _flatten(v, out, pairs)


def _implied(v: float) -> float | None:
    """The probability an American price implies, or None if ``v`` is not
    one. A writer asked to say "what the book's price implies" computes
    this from a price in the pack — it is arithmetic on the data, not a
    number from nowhere."""
    if v != int(v) or not (100 <= abs(v) <= 20000):
        return None
    return 100.0 / (v + 100.0) if v > 0 else -v / (-v + 100.0)


def allowed(pack) -> dict:
    """``{"values": [...], "pairs": {(w, l), ...}}`` — what the text may say."""
    vals: list = []
    pairs: list = []
    _flatten(pack, vals, pairs)
    vals += [p for p in (_implied(v) for v in list(vals)) if p is not None]
    ps = set()
    for w, lo, p in pairs:
        ps.add((w, lo))
        if isinstance(p, (int, float)) and not isinstance(p, bool):
            ps.add((w, lo, int(p)))
    return {"values": vals, "pairs": ps}


def _decimals(s: str) -> int:
    return len(s.split(".", 1)[1]) if "." in s else 0


def _value_ok(token: float, dec: int, pct: bool, ok: dict) -> bool:
    t = abs(token)
    for v in ok["values"]:
        a = abs(v)
        if round(a, dec) == t:
            return True
        if pct and round(a * 100, dec) == t:
            return True
        # A pack number already in percent, shown as a fraction, is rare
        # enough not to allow — the reverse (fraction → percent) is the norm.
    return False


def numbers_in(text: str) -> list[dict]:
    """The number claims in ``text``: ``{"raw", "kind", ...}`` each."""
    s = str(text or "")
    claims: list[dict] = []
    masked = s
    for rx in (_DATE, _MONTH_DAY):
        masked = rx.sub(lambda m: " " * len(m.group(0)), masked)
    for m in _RECORD.finditer(masked):
        a, b, c = m.group(1), m.group(2), m.group(3)
        claims.append({"raw": m.group(0), "kind": "record",
                       "pair": (int(a), int(b)) + ((int(c),) if c else ())})
    masked = _RECORD.sub(lambda m: " " * len(m.group(0)), masked)
    for m in _NUMBER.finditer(masked):
        sign, body, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        raw = m.group(0).strip()
        try:
            v = float(body.replace(",", ""))
        except ValueError:
            continue
        claims.append({"raw": raw, "kind": "pct" if unit == "%" else "num",
                       "value": v, "dec": _decimals(body),
                       "signed": bool(sign)})
    return claims


def _claim_ok(c: dict, ok: dict) -> bool:
    if c["kind"] == "record":
        pair = c["pair"]
        return pair in ok["pairs"]
    v, dec = c["value"], c["dec"]
    if dec == 0 and not c["signed"] and c["kind"] == "num":
        if v <= FREE_INT or 1990 <= v <= 2100:
            return True
    return _value_ok(v, dec, c["kind"] == "pct", ok)


def sentences(text: str) -> list[str]:
    return [p for p in _SENTENCE.split(str(text or "").strip()) if p]


def scrub(text: str, pack, ok: dict | None = None,
          only=None) -> tuple[str, list[dict]]:
    """``(kept text, dropped)``. ``only``, when given, is a predicate on a
    sentence: sentences it rejects are kept without a check (Ask checks
    only its claims about our own record)."""
    ok = ok if ok is not None else allowed(pack)
    kept, dropped = [], []
    for sent in sentences(text):
        if only is not None and not only(sent):
            kept.append(sent)
            continue
        bad = [c["raw"] for c in numbers_in(sent) if not _claim_ok(c, ok)]
        if bad:
            dropped.append({"sentence": sent, "numbers": bad})
        else:
            kept.append(sent)
    return " ".join(kept), dropped


def log_drops(kind: str, key: str, dropped: list, path: Path | None = None) -> None:
    """One line per dropped sentence. Never raises — a log that can break
    the lane it watches is worse than no log."""
    if not dropped:
        return
    p = Path(path) if path else DROPS_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        at = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        with p.open("a", encoding="utf-8") as fh:
            for d in dropped:
                fh.write(json.dumps({"at": at, "kind": kind, "key": key,
                                     "sentence": d["sentence"],
                                     "numbers": d["numbers"]}) + "\n")
    except OSError:
        pass


#: Ask checks the sentences that state OUR numbers — the record, ROI, CLV,
#: units — and leaves odds arithmetic and general sports talk alone: it is
#: allowed to work out that -110 is 52.4%, which no pack carries, and to
#: say the Lions are 4-0 against the Packers "in the games we hold".
_OUR_THING = re.compile(
    r"\b(?:our|qellys'?s?|the site'?s|the model'?s)\s+(?:\w+\s+){0,3}?"
    r"(?:record|roi|clv|picks?|bets?|book|units?|profit|return|hit rate|"
    r"closing line value)\b", re.I)
_WE_DID = re.compile(
    r"\b(?:we|we've|we're|the model|qellys)\s+(?:\w+\s+){0,2}?"
    r"(?:went|gone|are|is|has|have|hit|won|lost|finished|posted|sits?|"
    r"stands?|beat|beats)\b[^.]*\d", re.I)


def about_our_record(sentence: str) -> bool:
    return bool(_OUR_THING.search(sentence) or _WE_DID.search(sentence))


__all__ = ["allowed", "numbers_in", "scrub", "log_drops", "sentences",
           "about_our_record", "DROPS_PATH"]
