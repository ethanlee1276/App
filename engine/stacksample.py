"""Where a long call spends its time, by the function it called, sampled.

The record export (ledger.export_json) is one call of some seventy sections
and took 148.6 seconds on the box on 7 November, every ten minutes on a game
day, with nothing to say which section. cProfile would say, at a cost of
another minute or two a run; this does not need to be exact. A thread looks
at the calling thread's stack about twenty times a second and credits each
look to the function the measured call was running directly at that moment
(``(self)`` for the call's own lines), so the totals are seconds per section,
to about a twentieth of a second each, for almost nothing.

Standard library only. Never raises into the measured call: a sampler that
fails stops sampling and reports what it had.
"""
from __future__ import annotations

import sys
import threading
import time

#: How often the stack is looked at.
INTERVAL_S = 0.05


class Sampler:
    """Sample this thread's stack while the ``with`` block runs, crediting
    each sample to the direct callee of the frame running ``root`` (a code
    object, e.g. ``ledger.export_json.__code__``).

        with Sampler(export_json.__code__) as s:
            export_json(...)
        s.seconds()   # {"_two_leg_record": 10.4, "performance": 4.0, ...}
    """

    def __init__(self, root, interval: float = INTERVAL_S, clock=time.monotonic):
        self.root = root
        self.interval = float(interval)
        self.clock = clock
        self.counts: dict = {}
        self.samples = 0
        self.elapsed = 0.0
        self._tid = None
        self._stop = threading.Event()
        self._thread = None
        self._t0 = None

    def __enter__(self):
        self._tid = threading.get_ident()
        self._t0 = self.clock()
        self._thread = threading.Thread(target=self._run, name="stacksample", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self.elapsed = self.clock() - (self._t0 or self.clock())
        return False

    def _run(self):
        try:
            while not self._stop.wait(self.interval):
                frame = sys._current_frames().get(self._tid)
                name = self.callee(frame, self.root)
                if name is not None:
                    self.counts[name] = self.counts.get(name, 0) + 1
                    self.samples += 1
        except Exception:                                    # noqa: BLE001
            return

    @staticmethod
    def callee(frame, root):
        """The direct callee of the innermost frame running ``root`` on this
        stack (``(self)`` when ``root`` is the frame running), or None when
        ``root`` is not on it."""
        child = None
        while frame is not None:
            if frame.f_code is root:
                return "(self)" if child is None else child.f_code.co_name
            child, frame = frame, frame.f_back
        return None

    def seconds(self, top: int = 15) -> dict:
        """The ``top`` callees by seconds, each its share of the samples
        times the block's own length, to 0.1 s; the rest summed as
        ``(rest)``."""
        if not self.samples:
            return {}
        scale = self.elapsed / self.samples
        ranked = sorted(self.counts.items(), key=lambda kv: (-kv[1], kv[0]))
        out = {k: round(n * scale, 1) for k, n in ranked[:top]}
        rest = sum(n for _k, n in ranked[top:])
        if rest:
            out["(rest)"] = round(rest * scale, 1)
        return out
