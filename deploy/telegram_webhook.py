"""Point the Telegram bot's webhook at this server, then show Telegram's status.

Run inside the app container (it already has the bot settings):
    docker compose run --rm --no-deps app python -B /app/deploy-tools/telegram_webhook.py
The bot token and webhook secret are never printed. Registering replaces any earlier webhook
(for example a temporary Cloudflare tunnel), so stop old tunnels first.
"""
import os
import sys

import httpx

PATH = '/api/telegram/webhook'


def main():
    token, secret, origin = (os.environ.get(k, '') for k in ('TELEGRAM_BOT_TOKEN', 'TELEGRAM_WEBHOOK_SECRET', 'SHELTER_PUBLIC_ORIGIN'))
    if not token or not secret:
        sys.exit('Telegram is not configured: set TELEGRAM_BOT_TOKEN and TELEGRAM_WEBHOOK_SECRET in deploy/.env, then rerun ./setup.sh.')
    if not origin.startswith('https://'):
        sys.exit('SHELTER_PUBLIC_ORIGIN must be the public https:// address.')
    api = f'https://api.telegram.org/bot{token}/'
    try:
        with httpx.Client(timeout=15) as client:
            result = client.post(api + 'setWebhook', json={'url': origin + PATH, 'secret_token': secret,
                                                           'allowed_updates': ['message'], 'drop_pending_updates': True}).json()
            if not result.get('ok'):
                sys.exit('Telegram refused the webhook: ' + str(result.get('description', 'no reason given')))
            info = client.get(api + 'getWebhookInfo').json().get('result', {})
    except httpx.HTTPError:
        sys.exit('Could not reach Telegram (network error). No token was printed.')
    print('Webhook set to', info.get('url'))
    print('Pending updates:', info.get('pending_update_count'), '| Last error:', info.get('last_error_message') or 'none')


if __name__ == '__main__':
    main()
