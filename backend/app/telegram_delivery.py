"""One bounded HTTPS POST; never log token-bearing URLs or provider bodies."""
import hashlib
import http.client
import json
import os
import re
import ssl
from dataclasses import dataclass, field

TOKEN_PATTERN = re.compile(r'\b[0-9]{5,}:[A-Za-z0-9_-]{20,}\b')


class ConfigurationUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class Destination:
    id: str
    label: str
    chat_id: str = field(repr=False)
    test_only: bool = False


@dataclass(frozen=True)
class TelegramConfig:
    token: str = field(repr=False)
    destinations: dict = field(repr=False)

    @classmethod
    def from_environment(cls):
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        raw = os.environ.get('TELEGRAM_DESTINATIONS', '')
        if not token or not raw:
            raise ConfigurationUnavailable('Telegram bot and authorized destinations are not configured')
        if not re.fullmatch(r'[0-9]{5,}:[A-Za-z0-9_-]{20,120}', token):
            raise ConfigurationUnavailable('Telegram configuration is invalid')
        try:
            rows = json.loads(raw)
            if not isinstance(rows, dict) or not 1 <= len(rows) <= 20:
                raise ValueError()
            destinations = {}
            chat_ids = set()
            labels = set()
            for identity, row in rows.items():
                if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', identity) or not isinstance(row, dict):
                    raise ValueError()
                if set(row) - {'label', 'chat_id', 'test_only'}:
                    raise ValueError()
                label, chat = row['label'], row['chat_id']
                test_only = row.get('test_only', False)
                if not isinstance(label, str) or not 1 <= len(label.strip()) <= 80 or TOKEN_PATTERN.search(label) or any(ord(c) < 32 for c in label):
                    raise ValueError()
                label = label.strip()
                label.encode('utf-8')
                if label.casefold() in labels:
                    raise ValueError()
                labels.add(label.casefold())
                if not isinstance(chat, str) or not re.fullmatch(r'-?[1-9][0-9]{0,19}', chat) or type(test_only) is not bool:
                    raise ValueError()
                # Optional private test destination must be explicitly designated.
                if test_only and int(chat) < 0 or chat in chat_ids:
                    raise ValueError()
                chat_ids.add(chat)
                destinations[identity] = Destination(identity, label.strip(), chat, test_only)
            return cls(token, destinations)
        except (ValueError, TypeError, KeyError):
            raise ConfigurationUnavailable('Telegram destination configuration is invalid') from None

    def fingerprint(self, destination):
        return hashlib.sha256((self.token + '\0' + destination.chat_id).encode()).hexdigest()


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    code: str
    http_status: int | None = None
    telegram_error_code: int | None = None
    telegram_message_id: int | None = None


class TelegramSender:
    def send(self, config, destination, text):
        connection = None
        try:
            # stdlib client has no automatic URL logging, redirects or retries.
            # Fixed host and TLS verification; environment proxies are not used.
            connection = http.client.HTTPSConnection('api.telegram.org', timeout=10, context=ssl.create_default_context())
            connection.set_debuglevel(0)
            body = json.dumps({'chat_id': destination.chat_id, 'text': text,
                               'link_preview_options': {'is_disabled': True}}, ensure_ascii=False).encode('utf-8')
            connection.request('POST', '/bot' + config.token + '/sendMessage', body=body,
                               headers={'Content-Type': 'application/json; charset=utf-8'})
            response = connection.getresponse()
            payload = response.read(65537)
            if len(payload) > 65536:
                return DeliveryResult('delivery_unknown', 'unverifiable_response', response.status)
            data = json.loads(payload)
            if not isinstance(data, dict):
                raise ValueError()
            if data.get('ok') is False:
                code = data.get('error_code')
                return DeliveryResult('rejected', 'telegram_rejected', response.status,
                                      code if type(code) is int and 100 <= code <= 599 else None)
            result = data.get('result', {})
            if response.status == 200 and data.get('ok') is True and isinstance(result, dict):
                chat = result.get('chat', {})
                if (type(result.get('message_id')) is int and result['message_id'] > 0
                    and isinstance(chat, dict) and type(chat.get('id')) is int
                    and str(chat['id']) == destination.chat_id and result.get('text') == text
                    and (not destination.test_only or chat.get('type') == 'private')):
                    return DeliveryResult('accepted', 'telegram_accepted', 200, telegram_message_id=result['message_id'])
            return DeliveryResult('delivery_unknown', 'unverifiable_response', response.status)
        except (TimeoutError, OSError, http.client.HTTPException):
            # Do not stringify exceptions: they can contain the credential URL.
            return DeliveryResult('delivery_unknown', 'transport_uncertain')
        except (ValueError, UnicodeError):
            return DeliveryResult('delivery_unknown', 'unverifiable_response')
        finally:
            if connection is not None:
                try:
                    connection.close()
                except OSError:
                    pass  # Cleanup must not expose a credential-bearing transport error.


def get_sender():
    return TelegramSender()
