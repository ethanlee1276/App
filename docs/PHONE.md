# Qellys Book on your phone

The site runs on your Mac. Your phone just needs a path to it. There are
two, and they stack — set up both once and the right one simply works
wherever you are.

## At home (same Wi-Fi) — nothing to install

1. Run the site like always: `python3 launch.py`
2. The startup message prints a line like:

       On your phone (same Wi-Fi):     → http://192.168.1.23:8000

3. On your phone (same Wi-Fi as the Mac), open Safari and type that
   address exactly, including the `:8000`.
4. First time only: macOS may ask **"Allow Python to accept incoming
   network connections?"** — click **Allow**. (Clicked Deny once? System
   Settings → Network → Firewall → Options… → set Python to Allow.)

## Away from home (cellular, work, anywhere) — Tailscale, free

Tailscale puts your Mac and your phone on a tiny private network of
their own, encrypted end to end. Nothing about your Mac is exposed to
the public internet — only devices signed into YOUR Tailscale account
can reach it. The free plan covers this use completely.

**One-time setup, ~10 minutes:**

1. **On the Mac:** install Tailscale from <https://tailscale.com/download>
   (or the Mac App Store). Open it, sign in — Google or Apple login is
   fine. A little icon appears in the menu bar; you're done.
2. **On the phone:** install the **Tailscale** app from the App Store.
   Sign in with the SAME account. Toggle the VPN on when it asks.
3. **Relaunch the site** on the Mac. The startup message now adds:

       On your phone ANYWHERE (Tailscale): → http://100.x.y.z:8000

4. Open that address in Safari on the phone. It works on cellular, at
   work, anywhere — as long as the Tailscale toggle on the phone is on.

**Make it feel like an app:** with the page open in Safari, tap Share →
**Add to Home Screen**. One tap from then on. It lands as a dark tile with
the blue **Q** on it, labelled "Qellys Book". That icon is
`web/apple-touch-icon.png`, which `make_icon.py` draws from the same shape
as the site's favicon — iOS ignores SVG icons, which is the only reason a
PNG lives in the repo at all.

### "Bad request version" garbage in the Mac terminal?

Lines full of `code 400 … Bad request version ('jjt\x9e…')` mean the
phone spoke **HTTPS to our HTTP-only server**. Safari silently upgrades
addresses to `https://` — the site can't answer that handshake, so the
terminal prints the encrypted bytes as noise. Two fixes, either works:

1. **Quick:** on the phone, type the address with `http://` spelled out
   — `http://100.x.y.z:8000`, not just `100.x.y.z:8000`. If Safari
   keeps forcing https, Chrome for iOS respects `http://` reliably.
2. **Clean (recommended, one command):** give the site a REAL https
   address through Tailscale. In the Mac terminal:

       tailscale serve --bg 8000

   It prints a link like `https://ethans-macbook.tail1234.ts.net` —
   use THAT on the phone (and for the home-screen icon). Certificates
   are automatic; the link only works for your own devices. First run
   may ask you to enable HTTPS in the Tailscale admin page — the
   command prints the exact link to click. `tailscale serve reset`
   turns it off.

## The fine print (worth reading once)

- **The Mac must be awake with `launch.py` running.** The site lives on
  your laptop; if it sleeps, the site sleeps. For evening use, plug the
  Mac in and set System Settings → Battery → Options → "Prevent
  automatic sleeping on power adapter when the display is off".
- **The Tailscale address is stable** — it doesn't change day to day,
  so the home-screen icon keeps working.
- **Battery:** the Tailscale app on the phone idles at roughly nothing;
  leaving the toggle on is fine.
- **Never do this instead:** don't port-forward 8000 on your router or
  use a public tunnel without a password — that hands your dashboard
  (and a foothold on your Mac) to the whole internet. Tailscale exists
  so you never have to.
