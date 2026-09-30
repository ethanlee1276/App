"""Email the owner when a systemd unit fails (audit 2026-09-30, P1-13).

Run by `deploy/qellys-alert@.service`, which `OnFailure=` in
`qellys.service` and `qellys-update.service` starts with the failed
unit's name. Before this a failed unit was visible only to someone already
running `systemctl status` — the site kept serving yesterday's files and
nobody was told.

The address is `QB_ALERT_EMAIL` (set on the box with `deploy/setenv.sh`);
the mail goes through `engine.mailer`, the same SMTP settings the site's
own mail uses. Never raises: an alert that crashes is an alert not sent,
and the unit that started it has already failed.

    python3 -m engine.alert qellys.service
"""

from __future__ import annotations

import os
import subprocess
import sys


def _journal(unit: str) -> str:
    try:
        out = subprocess.run(["journalctl", "-u", unit, "-n", "40", "--no-pager"],
                             capture_output=True, text=True, timeout=20)
        return out.stdout[-6000:] or out.stderr[-2000:]
    except Exception as exc:                                  # noqa: BLE001
        return f"(journal unavailable: {type(exc).__name__})"


def run(unit: str, send=None, env=None, journal=None) -> str:
    """``"sent"``, ``"no-address"``, ``"no-mailer"`` or ``"failed"``."""
    env = os.environ if env is None else env
    to = str(env.get("QB_ALERT_EMAIL") or "").strip()
    if not to:
        print(f"alert: {unit} failed, but QB_ALERT_EMAIL is not set")
        return "no-address"
    if send is None:
        from . import mailer
        if not mailer.configured():
            print(f"alert: {unit} failed, but mail is not configured "
                  f"({', '.join(mailer.missing())})")
            return "no-mailer"
        send = mailer.send
    log = (journal or _journal)(unit)
    subject = f"Qellys Book: {unit} failed"
    text = (f"The unit {unit} failed on the box.\n\n"
            f"Check it:\n  sudo systemctl status {unit}\n"
            f"  journalctl -u {unit} -n 80\n\nLast lines of its journal:\n\n{log}\n")
    try:
        send(to, subject, text)
    except Exception as exc:                                  # noqa: BLE001
        print(f"alert: could not send ({type(exc).__name__}: {exc})")
        return "failed"
    print(f"alert: {unit} failure mailed")
    return "sent"


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "unknown unit")
