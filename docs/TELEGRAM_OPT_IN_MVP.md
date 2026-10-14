# Telegram consent and reviewed alerts — 13 October 2026

This P0 slice completes the missing consent gate around the existing exact-preview, explicit-admin-send, deduplication and delivery-audit workflow. No real Telegram bot, subscriber or delivery was configured or contacted during this execution.

## Behavior

Home → **Telegram alerts** (`/alerts`) checks configuration. Unconfigured means no invented bot link. A configured link opens `https://t.me/<configured_bot_username>?start=floodpulse`. The citizen explicitly sends `/start floodpulse` to request project alerts and `/stop` to opt out. The page explains that delivery/emergency dispatch is not guaranteed and a project administrator must authorize the destination.

`POST /api/telegram/webhook` accepts only the configured `X-Telegram-Bot-Api-Secret-Token` header. It processes fresh private-chat commands whose sender matches the chat and is not a bot/forwarded message. Only already operator-authorized `TELEGRAM_DESTINATIONS` are enrolled; demonstration mode accepts only explicitly marked private test destinations. Unlisted subscribers, arbitrary commands and group updates do not create recipients. New public subscriber discovery/geographic broadcast targeting remains future work.

Receipts store an opaque bot-specific HMAC subscriber key, command/receipt UTC timestamps, update identifier and consent version; no raw chat ID, username or command text is stored in the new tables. Duplicate/out-of-order messages do not override later consent. Message time handles Telegram update identifier reseeding after inactivity. Rotating the bot token requires fresh consent because the HMAC identity changes. Intake sends no automatic acknowledgement messages.

The existing authenticated administrator destination options display opt-in state. Private recipients cannot receive a preview or a new send claim without active consent. Consent is checked again immediately before the existing durable one-attempt claim. `/stop` does not recall an attempt already in progress. Group/channel destinations retain explicit operator authorization and Telegram membership; they are not presented as individually opted-in private recipients.

Every new message and audit response is labelled `ADMIN_ALERT`; it is not an `OFFICIAL_WARNING`. Experimental outputs/citizen reports never call send. Existing exact content hash/composing-admin checks, preview expiry, shelter revalidation, CSRF and opaque sessions remain. A persistent application-wide budget allows twenty attempts per fixed 15-minute bucket. Already claimed/terminal notifications do not consume another attempt or send again. Telegram API acceptance remains different from recipient reading; timeouts remain uncertain and are never automatically retried.

## Concrete setup

1. Use the actual project bot **FloodPulsebot** and an explicitly consenting authorized private test destination. Privately edit the project-root `.env` with `TELEGRAM_BOT_USERNAME=FloodPulsebot`, the real `TELEGRAM_BOT_TOKEN` and `TELEGRAM_DESTINATIONS` JSON contract in README; do not commit tokens/chat IDs or invent a bot. No default credentials exist.
2. Set private `TELEGRAM_WEBHOOK_SECRET` in the same file to a random 32–256 character string containing only letters, numbers, underscore or hyphen. Apply `chmod 600 .env`, run `./start.sh --check`, then start/restart `./start.sh`. Python automatically reads these four keys only; shell exports are unnecessary, and explicitly supplied environment values win. Configuration declares readiness, not verified live connectivity.
3. Apply additive Alembic revision `0005_telegram_subscriptions` via the existing maintenance connection, following `0004_citizen_reports`. This execution migrated disposable test databases only. Grant the actual restricted service role:

   ```sql
   GRANT SELECT, INSERT, UPDATE ON telegram_subscriptions TO floodpulse_shelter_app;
   GRANT SELECT, INSERT ON telegram_subscription_audit TO floodpulse_shelter_app;
   ```

   Existing notification and session/login-limit grants are still required. The role must not own tables or alter/delete audit history.
4. Expose the real webhook over the project's HTTPS origin and register it with Telegram's `setWebhook`, supplying that exact secret via `secret_token` and `allowed_updates=["message"]`. The application implements intake; this execution did not register a webhook or send an API request. Confirm HTTPS ingress/secret delivery rather than assuming a configured username establishes connectivity.
5. The authorized test user opens the bot and sends `/start floodpulse`; the administrator refreshes notification options to confirm opt-in. Compose → review exact server-rendered content → explicitly approve → send once. Independently inspect the provider acceptance/audit and the test user's received message. Live proof is still outstanding without credentials and reachable webhook.
6. The same user sends `/stop`; refresh options and verify a later preview/send is blocked. No silent subscription, model trigger or delivery guarantee is introduced.

Official contracts reviewed on 13 October 2026: [Telegram setWebhook and secret_token](https://core.telegram.org/bots/api#setwebhook), [bot deep linking](https://core.telegram.org/bots/features#deep-linking). No claim is made that external configuration has been completed.

## Private launcher loading — 14 October 2026

The optional root `.env` stays ignored by Git and must be a user-owned regular file with exactly `0600` permissions, at most 64 KiB. Python reads it without shell `source`, `eval`, command execution or interpolation. Symlinks, malformed/duplicate assignments, multiline values and insecure files fail startup with credential-free errors. Supported syntax is single-line `KEY=value`, optional `export`, literal single quotes, JSON-escaped double quotes and comments; quote destination JSON with single quotes. Unrelated valid keys are ignored. PostgreSQL credentials still come from the existing separate launcher profile/environment; administrator provisioning, roles and maintenance isolation are unchanged.

Explicit environment values, including empty ones, override file values. Absent keys remain absent; backend configuration validation continues to govern availability. The launcher removes all four Telegram keys from Vite, including `TELEGRAM_BOT_TOKEN`, `TELEGRAM_DESTINATIONS` and `TELEGRAM_WEBHOOK_SECRET`. The backend alone receives them. Direct backend commands do not automatically load this file. No actual credentials are included in examples/tests; configuration tests use ephemeral inert fixtures only.

Neither configuration loading nor `--check` makes a Telegram request, registers `setWebhook`, records consent or sends a notification. An operator must still configure authorized destinations and HTTPS ingress, separately register the matching webhook secret, collect `/start floodpulse` consent, and explicitly review/approve each intended send. Existing `/stop`, CSRF, deduplication, rate limits and notification audit rules remain unchanged.

## Verification

Real disposable PostGIS tests exercise signed commands, duplicate/stale/spoofed/unlisted updates, opt-out gating before a pending send, re-opt-in, one mocked audited acceptance, no resend, redacted readiness/options and persistent dispatch budget. Existing notification least-privilege tests now include the required read permission for subscription checks and existing rate-bucket permissions. Existing shelter/report workflows also pass after the additive migration. Browser fixture tests cover unavailable/available enrollment UI, exact admin review/approval, uncertain-delivery behavior and Home desktop/mobile fit. Telegram transport is mocked throughout; no actual subscriber delivery is claimed.

14 October configuration slice: **128 focused Python tests passed** (launcher/profile/parser, admin setup, notification protocol and security), plus **15 frontend tests passed** (notifications, opt-in and protected requests). New tests cover missing keys/file, explicit empty overrides, quoted JSON/comments, duplicate/malformed/invalid-UTF-8 values, exact permissions/ownership, symlinks/FIFOs/size bounds, redacted CLI errors and actual child-process environment isolation with mocked services. No genuine credentials are test fixtures. The read-only launcher check passed with ports 18051/14181 and the matching public origin; the default ports were already occupied and no running application was stopped.

Private local inspection confirmed the existing root file is owner-only `0600`, loads all four keys and uses `FloodPulsebot`. At least one configured destination's `chat_id` fails the existing numeric-string contract; the operator must privately supply a legitimate authorized nonzero chat ID as a JSON string (positive for a private test recipient). The file was preserved, not automatically corrected. Token/webhook-secret formats were checked without network authentication. Webhook registration, consent and an explicitly approved live send remain operator steps; no live delivery or bot ownership verification is claimed here.
