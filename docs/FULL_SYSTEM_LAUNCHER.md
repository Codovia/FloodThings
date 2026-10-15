# Full-system local launcher — 15 October 2026

This optional Linux supervisor invokes the existing `start.sh` unchanged. It
starts the configured **live** application, a webhook-only proxy and a temporary
Cloudflare Quick Tunnel. An explicit `--telegram` start authorizes only the
ownership-constrained webhook setup below. It never sends an alert or creates an
account. The isolated DEMO ONLY manual two-server procedure remains separate;
never import these Telegram secrets into that runtime.

## Daily use and stop procedure

From the project root:

```bash
./start-full.sh --help
./start-full.sh --check --telegram
./start-full.sh --telegram
```

The check validates private configuration, installed `cloudflared` and free
ports, then invokes the unchanged `start.sh --check` for dependencies, saved
artifact and existing PostgreSQL/schema/roles. It starts/recovers no process,
makes no Telegram request and changes no service or database data. The existing
launcher may open its normal lock file. A passing check does **not** prove public
connectivity, bot identity or webhook ownership.

Without `--telegram`, `./start-full.sh` starts only the existing application.
`./start.sh` remains available unchanged. Do not run these concurrently for the
same checkout. Fixed loopback ports: backend **18050**, frontend **14180**,
Telegram proxy **18060**; no automatic port substitution.

Use the existing private PostgreSQL profile/restricted roles, migration/import,
Python environment, installed frontend dependencies and saved rainfall artifact.
Install `cloudflared` separately; the launcher downloads nothing. Privately set
all four root `.env` keys: `TELEGRAM_BOT_USERNAME=FloodPulsebot`,
`TELEGRAM_BOT_TOKEN`, `TELEGRAM_DESTINATIONS`, `TELEGRAM_WEBHOOK_SECRET`.
No token/chat ID is provided here. The existing safe Python parser requires a
user-owned regular **0600** file; explicit environment values (even empty ones)
win. Existing backend validation checks the authorized destination contract.

Press **Ctrl+C** and wait for the terminal prompt before restarting. SIGTERM to
the full supervisor also works. It gives `start.sh` its normal shutdown grace,
then terminates remaining verified owned descendants using PID/start checks and
pidfds, including detached workers. The exclusive lock remains held until owned
processes terminate and listening ports release. PostgreSQL/data stay preserved.
Normal stop exit codes are 130/143. No process-name/port-based kill is used.

The tunnel stops, but Telegram's registration is deliberately **not deleted**.
It points at the offline temporary hostname until the next successful authorized
start. Pending updates are not discarded; queued commands may arrive on recovery
and still face backend freshness/consent checks. Shutdown sends no notification.

## Startup checks and security

1. Acquire the separate full-launcher lock and recover only proven children of
   its previous crashed session. Check all requested ports with safe PID/UID/
   executable diagnostics. Invoke `start.sh`; its database/ownership guards and
   separate lock stay authoritative. No setup, migration, import or reset occurs.
2. Verify health, frontend response, live mode and that application listeners
   belong to this launch. Verify backend bot configuration and unsigned webhook
   POST rejection (403).
3. Start maintained `scripts/telegram_webhook_proxy.py` on `127.0.0.1:18060`.
   Only exact `POST /api/telegram/webhook` forwards to 18050. Other paths/methods,
   query/path variants, transfer encoding, malformed/oversized inputs are denied.
   Requests/replies are bounded to 64 KiB, concurrency to eight and connections
   to 30 seconds overall, plus socket/upstream timeouts. The proxy checks header
   syntax; **the backend checks the secret value** and existing consent rules.
4. Start owned `cloudflared tunnel --url http://127.0.0.1:18060`, with a minimal
   environment, empty isolated home, explicit empty `/dev/null` configuration
   (ignoring system/user tunnel configurations) and loopback metrics. Parse only its pipe for
   an exact HTTPS single-label `*.trycloudflare.com` origin. Raw tunnel/application
   output is not echoed by the full supervisor; tunnel output is discarded.
5. Wait for public DNS and certificate-verified HTTPS pinned to checked public
   addresses. Require public `/admin` **404** and unsigned webhook POST **403**
   before any Telegram request. These probes submit no valid consent update.
6. Call Telegram `getMe`; match ID to token and username to FloodPulsebot.
   Inspect `getWebhookInfo`. Register only if the current URL is empty, exactly
   the new URL, or matches a confirmed signed previous-session receipt for this
   user/bot/checkout. An unrelated URL is never replaced or printed.
7. Call `setWebhook` once with private `secret_token`,
   `allowed_updates=["message"]`, `max_connections=4`,
   `drop_pending_updates=false`. Confirm exact URL/settings with `getWebhookInfo`
   before showing verified registration. No alert is sent. Periodic public
   checks and child monitoring stop the owned stack on detected tunnel failure.

Startup bounds: application 120 s, tunnel URL 45 s, public readiness 60 s plus
final bounded probes; DNS calls 3 s, public HTTPS probes 4 s and Telegram calls
8 s overall. No automatic Telegram request retries, redirects or environment
HTTP proxies are used. Backend/frontend remain loopback-only; only the restricted
proxy is exposed. TLS terminates at Cloudflare, so webhook traffic and its secret
header traverse that provider. Bot/database credentials are not passed to
cloudflared/proxy arguments or environment. No request logs, secrets or chat IDs
are printed. The supervisor reads bot credentials in memory for setup; the
unchanged launcher passes application credentials only to backend, strips
Telegram/database keys from Vite and maintenance credentials from the API. Keep
external APM/network logging from recording Telegram's credential-bearing path.

## Ownership and uncertain outcomes

Ignored `data/tmp/full_launcher/` requires **0700** user-owned directories; its
process receipt, lock and `webhook.json` require **0600**. The webhook receipt has
a public URL/bot identity and token-keyed HMAC, never raw credentials/chat IDs.
It is written atomically only after confirmation. Keep it across restarts: token
rotation, a different checkout, damaged/lost receipts or an unrelated webhook
prevent automatic replacement. Do not edit receipts to bypass ownership.

A lost Telegram reply, failed confirmation or receipt write can leave registration
uncertain. The launcher stops clearly, does not manufacture ownership or retry,
and requires private operator investigation. Telegram has no conditional webhook
compare-and-swap: coordinate one operator; do not concurrently change registration
outside this launcher. No takeover override or automatic unregister is provided.

## Troubleshooting

| Result | Safe action |
| --- | --- |
| Named port occupied | Use safe PID information to identify its owner. Stop its known terminal normally; never kill by port. A legacy manual proxy/tunnel is not owned here. |
| Launcher already running | Stop its owning terminal and wait; do not delete a held lock/receipt. |
| Existing launcher check failed | Run `./start.sh --check` separately for precise dependency/model/config/database diagnostics. |
| Private config invalid | Correct four keys, destination contract, user ownership and exact 0600 privately. Never paste values into support requests. |
| Missing cloudflared | Install the official executable separately and put it on PATH. |
| No/invalid tunnel URL, DNS/TLS failure | Check college networking/Cloudflare/DNS, then retry after shutdown. No connected status is claimed. |
| Unrelated webhook or missing/invalid receipt | Stop. Authorized operator must privately inspect and explicitly authorize a separate migration; no implicit takeover. |
| Uncertain registration | Inspect through a credential-safe Telegram client; preserve pending updates. Timeout does not prove failure. |
| Ownership/permissions failure | Investigate the private file; do not relax permissions or signal unknown PIDs. Normal startup can recover proven crash children; `--check` never does. |

The ignored `data/tmp/telegram/webhook_proxy.py` is a historical helper, not a
clone/runtime dependency. Do not run it alongside the maintained proxy.

Quick Tunnels are for testing/development: hostname changes each run, no uptime
guarantee, 200 in-flight requests maximum and no SSE. The local ingress is more
restrictive. Interactive Cloudflare email login is incompatible with Telegram's
non-interactive webhook. A future production service needs a separately reviewed
stable deployment. This is no emergency-service readiness claim.

Official references checked 15 October 2026:
[Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/),
[Telegram setWebhook](https://core.telegram.org/bots/api#setwebhook),
[Telegram getWebhookInfo](https://core.telegram.org/bots/api#getwebhookinfo).

## Demonstration verification boundary

Final test counts/check outcomes are recorded chronologically in `update.md`.
Tests use relocated loopback ports, temporary source/config trees, random inert
private fixtures and fake providers. They never register a real webhook, send a
message, change live consent or connect to operational PostgreSQL. Prior 14 October
delivery evidence remains separate. Live connectivity/registration is **NOT
TESTED** until the operator deliberately runs `./start-full.sh --telegram` and
confirms its connection. Live administrator authentication stays blocked pending
private password rotation. No fictional reports/shelters, database provisioning,
model training or scientific/security boundary changes are part of this command.
