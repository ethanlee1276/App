"""Breakout candidates and fades, the way the research reports wrote them (2026-11-15).

Ethan, 2026-11-15: "I want our game reports for each game to be scanning for
all that type of data and matchup shit and all of that and finding breakout,
because obviously those reports were able to find the good matchups and make
very good picks ... I just want to be able to go on our app, and that
research is already done for me for each game, for every sport."

His research reports (the 128 deep-research results and 114 report
artifacts, read on 15 November) gave a game a "Breakout candidates" list, in
32 of them, and "Fades" beside it. Each player came with the case in
numbers: his role and where it is moving, the defense's leak to him, the
game around him. Then came the pick, and the main way it loses ("reasoning
and the main way each one loses"). The reports said those in sentences; the
app's matchup scan already measures the same things, in every league, as a
read's reasons for and against (engine/gamescan, engine/nba/scan, the hockey
and baseball scans). Every league's report now writes the research's list
from those reads, one card a player:

  * ranked by the strength of the case: a role moving toward him first (a
    breakout spot), then the reasons for over the reasons against, then his
    work (target or carry share, usage, minutes);
  * every measured reason, up to REASONS_N, and the scan's notes on his form
    and his games against this opponent;
  * his pick on the read's side, from the board (gamereport.read_pick):
    never a forced one;
  * the main way it loses: his strongest reason against, or for a fade, what
    could still go right.

It reads what the scan found and never moves a number.
"""
from __future__ import annotations

#: The reads a candidate list and a fade list take, best case first.
UP_READS = ("breakout", "good")
DOWN_READS = ("avoid", "tough")
#: Reasons and notes on one card; cards in each list.
REASONS_N, NOTES_N = 4, 2
CANDIDATES_N, FADES_N = 6, 4
#: The headings the research used.
CANDIDATES_HEAD, FADES_HEAD = "Breakout candidates", "Fades"
NONE_LINE = "No one in this game reads as a breakout candidate or a good matchup"


def _sentence(text: str) -> str:
    t = str(text or "").strip()
    return t if not t or t[-1] in ".!?" else t + "."


def volume(r: dict) -> float:
    """His work, 0..1, for the tie between two cases of the same strength:
    a target or carry share, a usage rate, or minutes (or ice time) as a
    share of a game."""
    u = (r or {}).get("usage") or {}

    def f(k, scale=1.0):
        try:
            return float(u.get(k) or 0) / scale
        except (TypeError, ValueError):
            return 0.0
    return max(f("tgt_share"), f("carry_share"), f("usg"), f("mpg", 48.0), f("toi", 24.0),
               1.0 if str((r or {}).get("pos") or "").upper() == "QB" else 0.0)


def strength(r: dict, tone: str, vol=volume) -> tuple:
    """The sort key: the strongest case first."""
    pro = [x for x in r.get("pro") or [] if x]
    con = [x for x in r.get("con") or [] if x]
    lead = r.get("read") == ("breakout" if tone == "up" else "avoid")
    case = (len(pro) - 0.5 * len(con)) if tone == "up" else (len(con) - 0.5 * len(pro))
    return (not lead, -case, -vol(r), str(r.get("player") or ""))


def card(r: dict, tone: str, *, pick: str = "", role: str = "", form=None) -> dict:
    """One player's case as a card: his reasons, his notes, the main way it
    loses, his pick; the page draws it as a verdict card."""
    pro = [str(x) for x in r.get("pro") or [] if x]
    con = [str(x) for x in r.get("con") or [] if x]
    mine, other = (pro, con) if tone == "up" else (con, pro)
    notes = [str(x) for x in r.get("notes") or [] if x]
    why = [_sentence(w) for w in mine[:REASONS_N] + notes[:NOTES_N]]
    if other:
        # The reason as the scan wrote it: its first word may be a name.
        lead = "The main way it loses" if tone == "up" else "What could still go right"
        why.append(_sentence(f"{lead}: {other[0]}"))
    out = {"title": r.get("player"), "player": r.get("player"), "team": r.get("team"),
           "pos": r.get("pos") or "", "label": r.get("label") or "", "verdict": tone,
           "headshot": r.get("headshot") or "", "why": why}
    if role:
        out["role"] = role
    if pick:
        out["pick"] = pick
        # The pick itself, graded on a finished game's page (engine/gameresults).
        from .gameresults import read_bet
        bet = read_bet(r)
        if bet:
            out["bet"] = bet
    if form:
        out["form"] = form
    # MAY SIT (engine/availability, 2026-11-14): the mark, and why, first; the
    # scan's own "listed questionable" note gives way to it.
    if r.get("availability"):
        from .availability import LABELS
        out["status"] = LABELS.get(r["availability"], "")
        out["why"] = [_sentence(r.get("availability_note") or "")] + [
            w for w in out["why"] if "listed questionable" not in w and "is listed" not in w]
    return out


def blocks(reads: list, *, pick_fn=None, role_fn=None, form_fn=None, fade_ok=None, vol=volume,
           head_fn=None) -> list:
    """The research's two lists for a game, as report blocks: the breakout
    candidates, then the fades. ``fade_ok`` keeps a fade to the players
    worth one (football: a featured role who is not his team's go-to
    scorer); ``head_fn`` makes a heading block (the report's own)."""
    head = head_fn or (lambda text: {"type": "h", "text": text})
    reads = [r for r in reads or [] if isinstance(r, dict) and r.get("player")]
    up = sorted((r for r in reads if r.get("read") in UP_READS), key=lambda r: strength(r, "up", vol))
    down = sorted((r for r in reads if r.get("read") in DOWN_READS and (fade_ok is None or fade_ok(r))),
                  key=lambda r: strength(r, "down", vol))

    def one(r, tone):
        return card(r, tone, pick=(pick_fn(r) if pick_fn else "") or "",
                    role=(role_fn(r) if role_fn else "") or "", form=form_fn(r) if form_fn else None)
    out = []
    if up:
        out += [head(CANDIDATES_HEAD), {"type": "verdicts", "items": [one(r, "up") for r in up[:CANDIDATES_N]]}]
    if down:
        out += [head(FADES_HEAD), {"type": "verdicts", "items": [one(r, "down") for r in down[:FADES_N]]}]
    if reads and not up:
        out.append({"type": "p", "text": _sentence(NONE_LINE)})
    return out
