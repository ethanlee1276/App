"""The weekly backup zip, run as a detached child of the daily chores.

    python3 -m engine.backupzip 2026-09-30

Audit 2026-09-30, F-5: the zip ran synchronously on the refresher thread —
the sqlite backup API copying a ~3.5 GB history.db and deflating it on one
vCPU while every board waited. `maintenance.run_if_due` now starts this and
moves on; `maintenance.reap_children` logs its exit on a later cycle. The
archive is written beside, read back with `testzip()`, then renamed
(`maintenance._maybe_backup`)."""

from __future__ import annotations

import datetime as _dt
import sys


def main(argv: list[str]) -> int:
    from . import maintenance
    today = _dt.date.fromisoformat(argv[0]) if argv else _dt.date.today()
    try:
        maintenance._maybe_backup({}, today, print)
    except Exception as exc:                                  # noqa: BLE001
        print(f"backup failed: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
