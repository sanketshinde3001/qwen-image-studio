# Remote access design

Use the studio from a phone or any other device, while every image is still made on this Mac.

## Goals

* One **Share** button in the studio. It returns an HTTPS link and a QR code.
* Two modes, picked when sharing starts:
  * **Anonymous.** A small mobile page: upload or take a photo, describe the edit, get the result, download it. Nothing is written to this Mac's disk. Text to image works the same way.
  * **Full studio.** The phone gets the normal studio, including the gallery. Results are saved exactly like local runs.
* Safe by default: nobody can use the link without its secret key, and stopping sharing kills the link.
* No accounts, no installs outside this folder, no traces left behind.

## Tunnel

[Cloudflare Quick Tunnels](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) via `cloudflared`, a single signed binary kept in `bin/`.

* No account or DNS setup. Each start gives a fresh random `https://<words>.trycloudflare.com` address.
* Real TLS to the phone, works behind NAT and on mobile data.
* Started with `--no-autoupdate` and `HOME` pointed at `studio/tmp/`, so it writes nothing to the user's home folder. Its log stays in memory and is only read to find the link.
* `caffeinate -i -w <pid>` keeps the Mac from idle-sleeping while the tunnel runs.

Alternatives considered: SSH reverse tunnels (localhost.run, serveo) need no binary but drop connections and write `known_hosts`. ngrok and Tailscale Funnel need accounts.

Traffic is encrypted between the phone and Cloudflare and between Cloudflare and this Mac, but Cloudflare terminates TLS in between. That is stated in the UI and README.

## Isolation

The tunnel never points at the main studio port. The server opens a **second listener on 127.0.0.1** only while sharing, and `cloudflared` forwards to that one. Every request on it goes through a gate:

1. **Key.** Each share creates a random 32-byte key. The link is `https://…/k/<key>`. Opening it sets an `HttpOnly; Secure; SameSite=Lax` cookie and redirects to `/`. Requests without the cookie get a small "link expired" page. A new share means a new key, so old links die.
2. **Mode allowlist.** Anonymous mode only serves the anonymous page and its three API routes. Full-studio mode serves the normal studio.
3. **Limits.** 15 MB per upload, 3 queued jobs per anonymous visitor, 100 jobs total.

The local listener on port 7860 keeps working exactly as before.

## Anonymous pipeline (zero disk writes)

1. The phone decodes the photo (HEIC, JPEG, PNG) in the browser, shrinks it to 1024 px and sends it as a data URL. The server never runs `sips` or touches a file.
2. The job runs on the warm engine, which takes images as base64 and returns the result as base64, so the image stays in memory end to end.
3. No log file, settings sidecar, gallery entry or speed calibration. The engine's own output has no prompts in it.
4. The result is kept in memory, visible only to the visitor's session (a random cookie), and served with `Cache-Control: no-store`.
5. It is deleted when the visitor presses Delete, after 30 minutes, or when sharing stops.
6. The owner's local queue shows these jobs as "anonymous remote job" with no prompt or image.

Live preview, masks and upscaling are local-only, because they need files on disk.

## Studio UI

* A **Share** button in the header opens a panel: choose Anonymous or Full studio, then Start.
* While sharing: the link with a Copy button, a QR code, the mode, active visitors, and Stop.
* The QR code is drawn locally by a small vendored MIT library (`studio/vendor/qrcode.js`), so the link never goes to a third-party QR service.
