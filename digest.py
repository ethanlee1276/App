#!/usr/bin/env python3
"""Render — and, once a relay exists, send — the two email digests.

    python3 digest.py morning              # print it, send nothing
    python3 digest.py nightly
    python3 digest.py morning --locked     # what a signed-out reader gets
    python3 digest.py morning --send       # needs QB_SMTP_* — see docs/EMAIL.md

PRINTING IS THE DEFAULT AND `--send` IS THE FLAG, which is the right way
round for a thing that can mail several hundred people. The copy can be
read, argued with and changed for as long as anybody likes before a
single message leaves the machine.

`--send` walks the opt-in list in accounts.db and sends one message per
recipient, each with that person's own unsubscribe token in it. It stops
on the first failure rather than half-delivering a run: a provider that
has started refusing is a problem to look at, not to push through.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import digest as D                                # noqa: E402
from engine import mailer                                     # noqa: E402


def _preview(kind: str, locked: bool) -> int:
    msg = D.build(kind, entitled=not locked, token="PREVIEW-TOKEN")
    if msg is None:
        print(f"Nothing to send for the {kind} digest.")
        print("  morning: no recommended picks on any board right now.")
        print("  nightly: no settled recap in the feed yet.")
        print("A digest that arrives to say there is nothing to say is one "
              "people learn to filter.")
        return 0
    print("=" * 68)
    print("Subject:", msg["subject"])
    print("=" * 68)
    print(msg["text"])
    print("-" * 68)
    print(f"(the HTML part is {len(msg['html'])} bytes; both are always sent)")
    if not mailer.configured():
        print()
        print("Not sending: " + ", ".join(mailer.missing()) + " unset.")
        print("docs/EMAIL.md has the three steps, in order.")
    return 0


def _send(kind: str) -> int:
    if not mailer.configured():
        print("Refusing to send: " + ", ".join(mailer.missing()) + " unset.")
        print("See docs/EMAIL.md. Nothing was sent.")
        return 2
    from engine import accounts
    conn = accounts.connect()
    try:
        people = D.recipients(conn, kind)
    finally:
        conn.close()
    if not people:
        print(f"Nobody has opted in to the {kind} digest.")
        return 0
    sent = 0
    for who in people:
        msg = D.build(kind, entitled=True, token=who["token"])
        if msg is None:
            print(f"Nothing to send for the {kind} digest.")
            return 0
        mailer.send(who["email"], msg["subject"], msg["text"], msg["html"])
        sent += 1
    print(f"Sent {sent} message(s).")
    return 0


def main(argv: list) -> int:
    kind = next((a for a in argv if a in ("morning", "nightly")), "")
    if not kind:
        print(__doc__)
        return 2
    if "--send" in argv:
        return _send(kind)
    return _preview(kind, "--locked" in argv)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
