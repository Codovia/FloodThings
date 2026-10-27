"""Public Telegram district alerts: commands, district matching and the subscription store.

A person subscribes with their own command (/start floodpulse udupi, or the t.me link ?start=floodpulse_udupi) and
gets one confirmation reply; nothing else is ever sent automatically. Alerts reach a district's subscribers only
after an administrator previews and approves them (notifications.py). /stop deletes the stored chat ID.
"""
import re
import time
import uuid
from difflib import SequenceMatcher

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from .district_alert_schema import district_audit, district_subscriptions, subscribers
from .location_database import active as directory_active, districts as directory_districts

CONSENT_VERSION = 'telegram-district-alerts-v1-2026-10-27'
PREFIX = 'floodpulse'
DISCLAIMER = 'FloodPulse is a student project prototype, not an official warning service. Follow IMD, KSNDMC and district administration advice.'
# Former names, common English spellings and main towns (project-chosen), shown to people as "also matches".
FORMER_NAMES = {
    'nic:bengaluruurban.nic.in': ['Bengaluru', 'Bangalore', 'Bangalore Urban'], 'nic:bangalorerural.nic.in': ['Bangalore Rural'],
    'nic:ramanagara.nic.in': ['Ramanagara', 'Ramanagaram'], 'nic:dk.nic.in': ['Mangaluru', 'Mangalore', 'South Canara', 'DK'],
    'nic:uttarakannada.nic.in': ['Karwar', 'North Canara', 'UK'], 'nic:mysore.nic.in': ['Mysore'], 'nic:tumkur.nic.in': ['Tumkur'],
    'nic:shimoga.nic.in': ['Shimoga'], 'nic:chikkamagaluru.nic.in': ['Chikmagalur', 'Chikkamagalur'], 'nic:kodagu.nic.in': ['Coorg', 'Madikeri'],
    'nic:belagavi.nic.in': ['Belgaum'], 'nic:ballari.nic.in': ['Bellary'], 'nic:kalaburagi.nic.in': ['Gulbarga', 'Kalburgi'],
    'nic:vijayapura.nic.in': ['Bijapur'], 'nic:bagalkot.nic.in': ['Bagalkot'], 'nic:davanagere.nic.in': ['Davangere'],
    'nic:chamrajnagar.nic.in': ['Chamrajnagar', 'Chamarajnagar'], 'nic:chikkaballapur.nic.in': ['Chikballapur', 'Chikkaballapur'],
    'nic:vijayanagara.nic.in': ['Hospet', 'Hosapete'], 'nic:dharwad.nic.in': ['Hubballi', 'Hubli', 'Dharwar'], 'nic:yadgir.nic.in': ['Yadagiri'],
}
ALIASES = {re.sub(r'[^a-z0-9]', '', n.lower()): district_id for district_id, names in FORMER_NAMES.items() for n in names}
REMOVE_KEYBOARD = {'remove_keyboard': True}
_cache = {}


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def start_payload(name):
    """Telegram start parameter (A-Z, a-z, 0-9, _ and -; at most 64 characters)."""
    return PREFIX + '_' + normalize(name).replace(' ', '_')


def parse(command):
    """(action, district text) for district commands and short plain messages that may name a district
    (a tapped district button sends just its name); None for anything else (ignored, as before)."""
    if not isinstance(command, str) or len(command) > 200:
        return None
    if not command.startswith('/'):
        text = command.strip()
        return ('name', text) if 2 <= len(text) <= 40 and re.fullmatch(r"[\w .'-]+", text) else None
    head, _, rest = command.strip().partition(' ')
    head, rest = head.lower(), rest.strip()
    if head in ('/help', '/start') and not rest:
        return ('help', '')
    if head == '/mydistricts' and not rest:
        return ('status', '')
    if head == '/start':
        match = re.fullmatch(r'floodpulse(?:[ _-]+(.+))?', rest, re.I)
        if not match:
            return ('help', '')
        return ('subscribe', match.group(1)) if match.group(1) else ('bare', '')
    if head == '/stop':
        rest = re.sub(r'^floodpulse(?:[ _-]+|$)', '', rest, flags=re.I).strip()
        return ('unsubscribe', rest) if rest else ('stop', '')
    return None


def key(value):
    value = re.sub(r'^floodpulse ', '', normalize(value))
    return re.sub(r' district$', '', value).replace(' ', '')


def match(value, items):
    compact = key(value)
    for district in items:
        if normalize(district['name']).replace(' ', '') == compact:
            return district
    target = ALIASES.get(compact)
    return next((d for d in items if d['id'] == target), None)


def suggest(value, items, n=3, cutoff=0.6):
    """Closest district names or former names for a misspelt name (no automatic subscription)."""
    keys = {key(d['name']): d['id'] for d in items}
    keys.update({k: v for k, v in ALIASES.items() if any(d['id'] == v for d in items)})
    wanted = key(value)
    scored = sorted(((SequenceMatcher(None, wanted, k).ratio(), k) for k in keys), reverse=True)
    best = scored[0][0] if scored else 0
    found = []
    for score, close in scored:
        district = next(d for d in items if d['id'] == keys[close])
        # Only names nearly as close as the best one (e.g. "mangalor" -> Mangalore, not also Bangalore).
        if score >= cutoff and score >= best - 0.1 and district not in found:
            found.append(district)
    return found[:n]


def keyboard(items, placeholder, columns=3):
    """District buttons: tapping one sends the district's name, which subscribes to it."""
    names = [d['name'] for d in items]
    return {'keyboard': [[{'text': n} for n in names[i:i + columns]] for i in range(0, len(names), columns)],
            'one_time_keyboard': True, 'resize_keyboard': True, 'input_field_placeholder': placeholder[:64]}


def active_districts(engine, ttl=600):
    """The active place directory's districts (id, name, start link payload), cached briefly per engine."""
    hit = _cache.get(id(engine))
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    with engine.connect().execution_options(postgresql_readonly=True) as c:
        version = c.execute(select(directory_active.c.version).where(directory_active.c.singleton == 1)).scalar_one_or_none()
        rows = c.execute(select(directory_districts.c.id, directory_districts.c.name).where(directory_districts.c.version == version)
                         .order_by(directory_districts.c.ordinal)).all() if version else []
    items = [{'id': r.id, 'name': r.name, 'start': start_payload(r.name)} for r in rows]
    _cache[id(engine)] = (time.monotonic(), items)
    return items


def help_text(items):
    return ('FloodPulse district flood alerts.\nTap your district below to subscribe, or send /start floodpulse <district>, for example /start floodpulse udupi\n'
            'Your districts: /mydistricts\nStop one district: /stop <district>. Stop all and delete your chat ID: /stop\n'
            'Districts: ' + ', '.join(d['name'] for d in items) + '.\n' + DISCLAIMER)


def help_reply(items):
    return {'text': help_text(items), 'reply_markup': keyboard(items, 'Tap your district')}


class DistrictSubscriptions:
    def __init__(self, engine, districts=None):
        self.engine = engine
        self._districts = districts

    def districts(self):
        return self._districts() if self._districts else active_districts(self.engine)

    def names(self, connection, key):
        ids = connection.execute(select(district_subscriptions.c.district_id).where(district_subscriptions.c.subscriber_key == key)).scalars().all()
        return [d['name'] for d in self.districts() if d['id'] in ids]

    def handle(self, action, value, key, chat_id, update_id, command_at, received_at, demonstration):
        """Apply one command; return the reply (text and optional buttons), or None when nothing should be sent."""
        items = self.districts()
        if action in ('help', 'bare'):
            return help_reply(items)
        district = match(value, items) if action in ('subscribe', 'unsubscribe', 'name') else None
        if action == 'name':
            if district is None:
                # A plain message is answered only when it is close to a district name; anything else stays ignored.
                close = suggest(value, items, cutoff=0.75)
                return {'text': f'FloodPulse: did you mean {" or ".join(d["name"] for d in close)}? Tap it below to get its flood alerts.',
                        'reply_markup': keyboard(close, 'Tap your district', columns=1)} if close else None
            action = 'subscribe'
        if action in ('subscribe', 'unsubscribe') and district is None:
            shown = re.sub(r'[^\w .-]', '', value)[:40]
            close = suggest(value, items)
            if close:
                return {'text': f'FloodPulse: "{shown}" is not a district name. Did you mean {" or ".join(d["name"] for d in close)}? Tap it below.',
                        'reply_markup': keyboard(close, 'Tap your district', columns=1)}
            return {'text': f'FloodPulse: "{shown}" is not a Karnataka district. Tap your district below.\nDistricts: ' + ', '.join(d['name'] for d in items) + '.',
                    'reply_markup': keyboard(items, 'Tap your district')}
        if action == 'status':
            with self.engine.connect().execution_options(postgresql_readonly=True) as c:
                names = self.names(c, key)
            return {'text': ('FloodPulse: your districts: ' + ', '.join(names) + '.') if names else 'FloodPulse: you are not subscribed to any district. Send /start floodpulse <district>, for example /start floodpulse udupi.'}
        with self.engine.begin() as c:
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': 'district-subscription:' + key})
            # The append-only audit log orders commands, so a retried or older Telegram update changes nothing.
            last = c.execute(select(district_audit.c.command_at, district_audit.c.update_id).where(district_audit.c.subscriber_key == key)
                             .order_by(district_audit.c.command_at.desc(), district_audit.c.update_id.desc()).limit(1)).first()
            if last and (command_at, update_id) <= (last.command_at, last.update_id):
                return None
            row = c.execute(select(subscribers).where(subscribers.c.subscriber_key == key)).mappings().one_or_none()
            if action == 'stop' and row is None:
                return None  # Not a district subscriber (e.g. an operator destination using /stop): nothing to confirm.
            c.execute(district_audit.insert().values(id=str(uuid.uuid4()), subscriber_key=key, action=action,
                                                     district_id=district['id'] if district else None,
                                                     command_at=command_at, received_at=received_at, update_id=update_id))
            if action == 'subscribe':
                if row is None:
                    c.execute(subscribers.insert().values(subscriber_key=key, chat_id=chat_id, consent_version=CONSENT_VERSION,
                                                          demonstration=demonstration, created_at=received_at))
                elif row['chat_id'] != chat_id or row['demonstration'] != demonstration or row['consent_version'] != CONSENT_VERSION:
                    c.execute(update(subscribers).where(subscribers.c.subscriber_key == key)
                              .values(chat_id=chat_id, demonstration=demonstration, consent_version=CONSENT_VERSION))
                c.execute(insert(district_subscriptions).values(subscriber_key=key, district_id=district['id'], created_at=received_at)
                          .on_conflict_do_nothing())
                return {'text': f'FloodPulse: you will receive administrator-approved flood alerts for {district["name"]} district.\n'
                                f'Your districts: {", ".join(self.names(c, key))}.\n'
                                f'Stop {district["name"]} alerts: /stop {normalize(district["name"])}. Stop all and delete your chat ID: /stop\n' + DISCLAIMER,
                        'reply_markup': REMOVE_KEYBOARD}
            if action == 'unsubscribe':
                if row is not None:
                    c.execute(delete(district_subscriptions).where(district_subscriptions.c.subscriber_key == key,
                                                                   district_subscriptions.c.district_id == district['id']))
                remaining = self.names(c, key)
                if row is not None and not remaining:
                    c.execute(delete(subscribers).where(subscribers.c.subscriber_key == key))
                return {'text': f'FloodPulse: you will no longer receive {district["name"]} alerts.'
                        + (f' You still receive: {", ".join(remaining)}.' if remaining else ' You have no district alerts left; your chat ID is not stored by FloodPulse.')}
            c.execute(delete(subscribers).where(subscribers.c.subscriber_key == key))  # 'stop': districts cascade
            return {'text': 'FloodPulse: all district alerts stopped and your chat ID was deleted from FloodPulse. Send /start floodpulse <district> to subscribe again.',
                    'reply_markup': REMOVE_KEYBOARD}


def recipients(connection, district_id, demonstration):
    return connection.execute(select(subscribers.c.subscriber_key, subscribers.c.chat_id)
                              .join(district_subscriptions, district_subscriptions.c.subscriber_key == subscribers.c.subscriber_key)
                              .where(district_subscriptions.c.district_id == district_id, subscribers.c.demonstration == demonstration)
                              .order_by(subscribers.c.subscriber_key)).all()


def subscriber_counts(connection, demonstration):
    rows = connection.execute(select(district_subscriptions.c.district_id, func.count())
                              .join(subscribers, district_subscriptions.c.subscriber_key == subscribers.c.subscriber_key)
                              .where(subscribers.c.demonstration == demonstration).group_by(district_subscriptions.c.district_id)).all()
    return {district_id: count for district_id, count in rows}


def forget_blocked(connection, key, at):
    """Telegram refused delivery because the person blocked the bot: delete their chat ID (data minimisation)."""
    if connection.execute(delete(subscribers).where(subscribers.c.subscriber_key == key)).rowcount:
        connection.execute(district_audit.insert().values(id=str(uuid.uuid4()), subscriber_key=key, action='blocked',
                                                          command_at=at, received_at=at, update_id=0))
