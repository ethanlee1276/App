"""A team's name as a reader should see it, from the feed's display name."""

from __future__ import annotations


def tidy_team_name(name, loc="") -> str:
    """ESPN's display name with its own slips taken out.

    ESPN's records for some schools below Division I repeat a word or tack
    an all-caps code onto the end (18 November 2026, the college boards'
    team tables): "Regent Regent Royals", "Oklahoma Panhandle PANHANDLE
    ST", "Midland MIDLAND LUTHERAN", "Sterling STERLING KS", "University of
    Mexico MEXICO U". An all-caps tail that repeats a word already in the
    name is dropped, then a word said twice in a row is said once — unless
    the school's location is named that way (``loc``: "Walla Walla"). A
    real school's capitals ("UCLA Bruins", "Texas A&M Aggies", "Boston U")
    never repeat an earlier word at the end, so they stand."""
    words = str(name or "").split()
    tail = len(words)
    while tail > 1 and words[tail - 1].isupper() and any(c.isalpha() for c in words[tail - 1]):
        tail -= 1
    if tail < len(words):
        earlier = {w.lower() for w in words[:tail]}
        if any(len(w) >= 3 and w.lower() in earlier for w in words[tail:]):
            words = words[:tail]
    place = " ".join(str(loc or "").split()).lower()
    out: list = []
    for w in words:
        if out and w.lower() == out[-1].lower() and f"{out[-1]} {w}".lower() not in place:
            continue
        out.append(w)
    return " ".join(out)
