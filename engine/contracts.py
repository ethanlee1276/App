"""Contract years: the last season of a player's deal, for the scout.

Ethan, 2026-10-11, of the list of situations we could track for players
("revenge game, primetime, rest ... contract year — final year of his
deal"): "all of it".

WHERE THE DEALS COME FROM: nflverse's contracts release (Over The Cap's
contract history, republished as open data — downloaded as a file, never
scraped). Its CSV stopped updating in May 2022; the R file beside it
(``historical_contracts.rds``) is refreshed weekly, so that is the one
read here, by a small reader of R's own save format (``read_rds``) — the
standard library has gzip and struct, which is all the format needs.

WHAT COUNTS AS A CONTRACT YEAR, written 2026-10-11 before anything was
measured (the repo's rule: never choose a setting because a backtest
liked it). Each player's deals are walked in the order they were signed,
every deal signed in or before the season counted:

  * a new deal (drafted, free agent, franchise tag, …) runs from the year
    it was signed for its listed years;
  * an EXTENSION adds its years to the end of the deal it extends — and a
    first-round pick's rookie deal ends a year later when it is extended,
    because the fifth-year option is what the extension builds on (Justin
    Jefferson: drafted 2020 for four years, option 2024, extended 2024 by
    four → through 2028, as signed);
  * the season is a contract year when it is the last season of the deal
    in force — or the year after a first-round rookie deal with nothing
    signed since (he is playing on the fifth-year option). A first-round
    pick's fourth season is left UNKNOWN: whether the option was taken up
    that May is not in the data, and a guess would flag half of them wrong.

The data's limits, stated: a deal signed during the season counts from
its first game (the file keeps the year, not the date), and a player the
file does not list, or two with one name and one position, is unknown.

    sudo -u qellys python3 -m engine.contracts              # build and save the table
    sudo -u qellys python3 -m engine.contracts --dry-run    # build and report only
    sudo -u qellys python3 -m engine.contracts --player "Tee Higgins"

Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import gzip
import json
import struct
import sys
from pathlib import Path

CONTRACTS_URL = "https://github.com/nflverse/nflverse-data/releases/download/contracts/historical_contracts.rds"
CACHE_NAME = "nflverse_historical_contracts.rds"
STORE = "nfl_contracts.json"
#: Rebuilt by the weekly replay when older than this (the release is weekly).
STALE_S = 6 * 86400
#: The positions the board bets on; everyone else is left out of the store.
POSITIONS = frozenset({"QB", "RB", "WR", "TE", "FB"})


# --- R's save format ------------------------------------------------------------------
class RdsError(ValueError):
    """The file is not an R save this reader understands."""


_NIL, _SYM, _LIST, _LANG, _CHAR, _LGL, _INT, _REAL, _STR, _VEC, _EXPR = 254, 1, 2, 6, 9, 10, 13, 14, 16, 19, 20
_ALTREP, _REF, _NILSXP = 238, 255, 0


class _Reader:
    """R's XDR serialization (format 2 or 3), enough for a data frame of
    strings, numbers and nested data frames — read from a stream a
    megabyte at a time, because the contracts file unpacks to 140MB and
    the box has 1GB. ``frame_hook`` turns each NESTED data frame into what
    is kept of it (None drops it): the file carries a salary table for
    every one of its 50,000 deals, and only the contract history is read."""

    CHUNK = 1 << 20

    def __init__(self, stream, frame_hook=None):
        self.f, self.buf, self.i, self.refs, self.hook = stream, b"", 0, [], frame_hook

    def _need(self, n: int) -> None:
        if self.i + n > len(self.buf):
            rest = self.buf[self.i:]
            self.buf = rest + self.f.read(max(n - len(rest), self.CHUNK))
            self.i = 0
            if len(self.buf) < n:
                raise RdsError("the file ends early")

    def _int(self) -> int:
        self._need(4)
        v = struct.unpack_from(">i", self.buf, self.i)[0]
        self.i += 4
        return v

    def _bytes(self, n: int) -> bytes:
        self._need(n)
        b = self.buf[self.i:self.i + n]
        self.i += n
        return b

    def _array(self, code: str, n: int, size: int) -> tuple:
        out: list = []
        while n:
            k = min(n, self.CHUNK // size)
            self._need(k * size)
            out.extend(struct.unpack_from(f">{k}{code}", self.buf, self.i))
            self.i += k * size
            n -= k
        return tuple(out)

    def item(self, nested: bool = False):
        flags = self._int()
        kind = flags & 0xFF
        attr, tag = bool(flags & 0x200), bool(flags & 0x400)
        if kind in (_NIL, _NILSXP):
            return None
        if kind == _REF:
            idx = flags >> 8 or self._int()
            return self.refs[idx - 1]
        if kind == _SYM:
            sym = ("sym", self.item())
            self.refs.append(sym)
            return sym
        if kind == _CHAR:
            n = self._int()
            return None if n < 0 else sys.intern(self._bytes(n).decode("utf-8", "replace"))
        if kind in (_LIST, _LANG):
            return self._pairlist(attr, tag)
        if kind == _ALTREP:
            return self._altrep()
        if kind in (_STR, _VEC, _EXPR):
            n = self._int()
            vals = [self.item(nested=kind == _VEC) for _ in range(n)]
        elif kind == _REAL:
            vals = list(self._array("d", self._int(), 8))
        elif kind in (_INT, _LGL):
            vals = [None if v == -2147483648 else v for v in self._array("i", self._int(), 4)]
        else:
            raise RdsError(f"R type {kind} is not read here")
        if not attr:
            return vals
        names = next((v for k, v in self._pairlist_items(self.item()) if k == "names"), None)
        if kind != _VEC or not names:
            return vals
        frame = dict(zip(names, vals))
        return self.hook(frame) if nested and self.hook is not None else frame

    def _pairlist(self, attr: bool, tag: bool):
        out = []
        while True:
            if attr:
                self.item()
            key = self.item() if tag else None
            out.append((key[1] if isinstance(key, tuple) else key, self.item()))
            flags = self._int()
            if flags & 0xFF == _NIL:
                return ("pairlist", out)
            if flags & 0xFF not in (_LIST, _LANG):
                raise RdsError("a pairlist that does not end")
            attr, tag = bool(flags & 0x200), bool(flags & 0x400)

    @staticmethod
    def _pairlist_items(p):
        return p[1] if isinstance(p, tuple) and p and p[0] == "pairlist" else []

    def _altrep(self):
        info, state = self.item(), self.item()
        self.item()                                          # its attributes
        items = self._pairlist_items(info)
        cls = items[0][1] if items else None
        cls = cls[1] if isinstance(cls, tuple) else cls
        if cls in ("compact_intseq", "compact_realseq"):
            n, start, step = state
            return [start + k * step for k in range(int(n))]
        if str(cls or "").startswith("wrap_"):
            return state[0]
        raise RdsError(f"R compact vector {cls!r} is not read here")


def read_rds(source, frame_hook=None):
    """The object an R ``saveRDS`` file holds (gzip or plain) — ``source``
    is the file's bytes or a path."""
    import io
    if isinstance(source, (bytes, bytearray)):
        raw = io.BytesIO(source)
    else:
        raw = open(source, "rb")
    try:
        stream = gzip.GzipFile(fileobj=raw) if raw.read(2) == b"\x1f\x8b" else raw
        raw.seek(0)
        r = _Reader(stream, frame_hook)
        if r._bytes(2) != b"X\n":
            raise RdsError("not an R XDR save")
        version = r._int()
        r._int()
        r._int()
        if version == 3:
            r._bytes(r._int())                               # the native encoding's name
        return r.item()
    except (OSError, EOFError, struct.error) as exc:
        raise RdsError(f"the file would not read ({type(exc).__name__})") from exc
    finally:
        raw.close()


# --- deals and contract years ---------------------------------------------------------
def _num(v):
    try:
        return None if v is None or v != v else int(v)
    except (TypeError, ValueError):
        return None


def deals_of(history) -> list:
    """[[year signed, years, type], …] from one contract-history table (or
    the list it was already cut down to)."""
    if isinstance(history, list):
        return history
    if not isinstance(history, dict) or "contract_type" not in history:
        return []
    out = []
    for ys, yrs, kind in zip(history.get("year_signed") or [], history.get("yrs") or [],
                             history.get("contract_type") or []):
        ys, yrs = _num(ys), _num(yrs)
        if ys and yrs:
            out.append([ys, yrs, str(kind or "")])
    return out


def _nested(frame: dict):
    """What the reader keeps of a nested table: a contract history, cut to
    its deals; nothing else."""
    return deals_of(frame) if "contract_type" in frame else None


def players_from_frame(frame: dict) -> dict:
    """{name key: [{"pos", "round", "deals": [[year signed, years, type], …]}]}
    — one entry per player (Over The Cap id), skill positions only."""
    from .hometown import norm_name
    by_id: dict = {}
    n = len(frame.get("player") or [])
    for i in range(n):
        pos = str((frame.get("position") or [""] * n)[i] or "").upper()
        if pos not in POSITIONS:
            continue
        pid = (frame.get("otc_id") or [None] * n)[i] or frame["player"][i]
        deals = deals_of((frame.get("contract_history") or [None] * n)[i])
        if pid in by_id or not deals:
            continue
        by_id[pid] = {"name": frame["player"][i], "pos": pos,
                      "round": _num((frame.get("draft_round") or [None] * n)[i]), "deals": deals}
    out: dict = {}
    for p in by_id.values():
        out.setdefault(norm_name(p["name"]), []).append({"pos": p["pos"], "round": p["round"],
                                                         "deals": p["deals"]})
    return out


def contract_year(entry: dict | None, season) -> bool | None:
    """True when ``season`` is the last season of his deal (the rule at the
    top of this file); False when it is not; None when it cannot be told."""
    if not entry or season is None:
        return None
    s = int(season)
    known = [d for d in entry.get("deals") or [] if d[0] <= s]
    if not known:
        return None
    end, rookie_r1 = None, False
    for ys, yrs, kind in known:
        k = kind.lower()
        if k == "extension" and end is not None:
            end = end + (1 if rookie_r1 else 0) + yrs
            rookie_r1 = False
        else:
            end = ys + yrs - 1
            rookie_r1 = k == "drafted" and entry.get("round") == 1
    if rookie_r1:
        if s == end:
            return None                       # option taken up or not: not in the data
        if s == end + 1:
            return True                       # playing on the fifth-year option
    if s > end:
        return None
    return s == end


def lookup(table: dict, player, position="") -> dict | None:
    """His entry, or None — two players with one name are told apart by
    position, and with no way to tell them apart neither is used."""
    from .hometown import norm_name
    rows = ((table or {}).get("players") or {}).get(norm_name(player)) or []
    if len(rows) == 1:
        return rows[0]
    pos = str(position or "").upper()
    match = [r for r in rows if r["pos"] == pos]
    return match[0] if len(match) == 1 else None


# --- the stored table -----------------------------------------------------------------
def _store() -> Path:
    from . import modelstate
    return Path(modelstate.path(STORE))


_CACHE: dict = {}


def load(path=None) -> dict:
    p = Path(path) if path else _store()
    try:
        stamp = (str(p), p.stat().st_mtime)
    except OSError:
        return {}
    if _CACHE.get("stamp") != stamp:
        try:
            _CACHE["table"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _CACHE["table"] = {}
        _CACHE["stamp"] = stamp
    return _CACHE["table"]


def save(table: dict, path=None) -> None:
    p = Path(path) if path else _store()
    p.parent.mkdir(parents=True, exist_ok=True)
    table = dict(table, at=_dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"))
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(table, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def stale(path=None) -> bool:
    p = Path(path) if path else _store()
    try:
        return (_dt.datetime.now().timestamp() - p.stat().st_mtime) > STALE_S
    except OSError:
        return True


def _download(url: str = CONTRACTS_URL) -> bytes:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "qellysbook/1.0 (contract years)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def build(source=None) -> dict:
    """The table from the release file: ``source`` is its bytes or a path;
    by default it is downloaded and kept in the cache, then read from disk."""
    if source is None:
        from .sources.fetch import CACHE_DIR
        path = Path(CACHE_DIR) / CACHE_NAME
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(_download())
        tmp.replace(path)
        source = path
    frame = read_rds(source, frame_hook=_nested)
    if not isinstance(frame, dict) or "player" not in frame:
        raise RdsError("the contracts file is not the table it used to be")
    players = players_from_frame(frame)
    return {"players": players, "rows": len(frame.get("player") or []),
            "counted": sum(len(v) for v in players.values())}


def refresh(log=print, source=None) -> dict:
    """Build and save. Never raises: a file that will not load is a logged
    line, and yesterday's table stays."""
    try:
        table = build(source)
        save(table)
        return table
    except Exception as exc:                                  # noqa: BLE001
        log(f"contracts: not rebuilt ({type(exc).__name__}: {exc})")
        return {}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m engine.contracts")
    ap.add_argument("--dry-run", action="store_true", help="build and report; save nothing")
    ap.add_argument("--player", default="", help="show one player's deals and contract years")
    a = ap.parse_args(argv)
    table = load() if a.player else {}
    if not table.get("players"):
        print("reading nflverse's contract file (about a minute)…", flush=True)
        table = build()
        print(f"contracts: {table['rows']} deals in the file; {table['counted']} skill players kept")
        if not a.dry_run:
            save(table)
            print("saved; the board and the weekly replay read it")
    from .seasons import season_of
    season = season_of("nfl", _dt.date.today().isoformat())
    if a.player:
        e = lookup(table, a.player)
        if not e:
            print(f"{a.player}: not in the table (or two players share the name)")
            return 0
        print(f"{a.player} ({e['pos']}, round {e['round'] or '—'}):")
        for ys, yrs, kind in e["deals"]:
            print(f"  {ys}  {yrs} yr  {kind}")
        for s in range(season - 4, season + 1):
            cy = contract_year(e, s)
            print(f"  {s}: " + ("contract year" if cy else "not a contract year" if cy is False else "unknown"))
        return 0
    rows = [(name, e) for name, es in (table.get("players") or {}).items() for e in es
            if e["pos"] in ("QB", "RB", "WR", "TE") and contract_year(e, season)]
    print(f"{season}: {len(rows)} skill players in a contract year, for example:")
    for name, e in sorted(rows)[:15]:
        print(f"  {name:26} {e['pos']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
