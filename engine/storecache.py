"""A walk's stores, read once (2026-11-05).

The fitters' walks (engine/logwalk, engine/mlb/backtest) price every stored
player-game through the board's own chain, and six stores on that chain
(player memory, the selection haircut, the loss patterns, the hypotheses,
the shelf stop and the position spreads) each built a path and asked the
disk for its file's time on every game, to see whether the store had
changed. One NFL market's walk made 125,000 such calls, a fifth of its
time; the dial makes 21 walks a market, and on the box the NFL's dial
outgrew the deep refit's hour.

Inside `frozen()` a file's time is asked once and remembered until the
walk ends. Nothing inside a walk writes a store, so every answer is the one
the disk would have given; and each store's writer calls `forget` after
writing, so one written inside a walk is read again all the same. Outside
it, `mtime` asks the disk every time, as the loaders always did: the board
and the launcher see a store the moment a fitter rewrites it.
"""
from __future__ import annotations

import os
from contextlib import contextmanager

_DEPTH = [0]
_MEMO: dict = {}
_MISS = object()


@contextmanager
def frozen():
    """Remember each store file's time until the outermost walk ends."""
    _DEPTH[0] += 1
    try:
        yield
    finally:
        _DEPTH[0] -= 1
        if not _DEPTH[0]:
            _MEMO.clear()


def mtime(path) -> float | None:
    """``os.stat(path).st_mtime``, None when the file cannot be read; asked
    once per file while `frozen`."""
    key = os.fspath(path)
    if _DEPTH[0]:
        hit = _MEMO.get(key, _MISS)
        if hit is not _MISS:
            return hit
    try:
        m = os.stat(key).st_mtime
    except OSError:
        m = None
    if _DEPTH[0]:
        _MEMO[key] = m
    return m


def forget(path) -> None:
    """A store's writer, after writing: its next `mtime` asks the disk."""
    _MEMO.pop(os.fspath(path), None)
