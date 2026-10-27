"""Public Telegram district alerts: commands, district matching and the subscription store.

A person subscribes with their own command (/start floodpulse udupi, or the t.me link ?start=floodpulse_udupi) and
gets one confirmation reply; nothing else is ever sent automatically. Alerts reach a district's subscribers only
after an administrator previews and approves them (notifications.py). /stop deletes the stored chat ID.
"""
import re
import time
import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from .district_alert_schema import district_audit, district_subscriptions, subscribers
from .location_database import active as directory_active, districts as directory_districts

CONSENT_VERSION = 'telegram-district-alerts-v1-2026-10-27'
PREFIX = 'floodpulse'
DISCLAIMER = 'FloodPulse is a student project prototype, not an official warning service. Follow IMD, KSNDMC and district administration advice.'
# Former and common English names (project-chosen), keyed without spaces, mapped to the directory's district IDs.
ALIASES = {
    'bengaluru': 'nic:bengaluruurban.nic.in', 'bangalore': 'nic:bengaluruurban.nic.in', 'bangaloreurban': 'nic:bengaluruurban.nic.in',
    'bangalorerural': 'nic:bangalorerural.nic.in', 'ramanagara': 'nic:ramanagara.nic.in', 'ramanagaram': 'nic:ramanagara.nic.in',
    'mangalore': 'nic:dk.nic.in', 'mangaluru': 'nic:dk.nic.in', 'southcanara': 'nic:dk.nic.in', 'dk': 'nic:dk.nic.in',
    'karwar': 'nic:uttarakannada.nic.in', 'northcanara': 'nic:uttarakannada.nic.in', 'uk': 'nic:uttarakannada.nic.in',
    'mysore': 'nic:mysore.nic.in', 'tumkur': 'nic:tumkur.nic.in', 'shimoga': 'nic:shimoga.nic.in',
    'chikmagalur': 'nic:chikkamagaluru.nic.in', 'chikkamagalur': 'nic:chikkamagaluru.nic.in',
    'coorg': 'nic:kodagu.nic.in', 'madikeri': 'nic:kodagu.nic.in', 'belgaum': 'nic:belagavi.nic.in', 'bellary': 'nic:ballari.nic.in',
    'gulbarga': 'nic:kalaburagi.nic.in', 'kalburgi': 'nic:kalaburagi.nic.in', 'bijapur': 'nic:vijayapura.nic.in',
    'bagalkot': 'nic:bagalkot.nic.in', 'davangere': 'nic:davanagere.nic.in', 'chamrajnagar': 'nic:chamrajnagar.nic.in',
    'chamarajnagar': 'nic:chamrajnagar.nic.in', 'chikballapur': 'nic:chikkaballapur.nic.in', 'chikkaballapur': 'nic:chikkaballapur.nic.in',
    'hospet': 'nic:vijayanagara.nic.in', 'hosapete': 'nic:vijayanagara.nic.in', 'hubli': 'nic:dharwad.nic.in',
    'hubballi': 'nic:dharwad.nic.in', 'dharwar': 'nic:dharwad.nic.in', 'yadagiri': 'nic:yadgir.nic.in',
}
_cache = {}


def normalize(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip()


def start_payload(name):
    """Telegram start parameter (A-Z, a-z, 0-9, _ and -; at most 64 characters)."""
    return PREFIX + '_' + normalize(name).replace(' ', '_')


def parse(command):
    """(action, district text) for district commands; None for anything else (ignored, as before)."""
    if not isinstance(command, str) or len(command) > 200:
        return None
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


def match(value, items):
    key = normalize(value)
    key = re.sub(r'^floodpulse ', '', key)
    key = re.sub(r' district$', '', key)
    compact = key.replace(' ', '')
    for district in items:
        if normalize(district['name']).replace(' ', '') == compact:
            return district
    target = ALIASES.get(compact)
    return next((d for d in items if d['id'] == target), None)


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
    return ('FloodPulse district flood alerts.\nSubscribe: /start floodpulse <district>, for example /start floodpulse udupi\n'
            'Your districts: /mydistricts\nStop one district: /stop <district>. Stop all and delete your chat ID: /stop\n'
            'Districts: ' + ', '.join(d['name'] for d in items) + '.\n' + DISCLAIMER)


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
        """Apply one command and return the reply, or None when nothing should be sent (duplicate/older update)."""
        items = self.districts()
        if action in ('help', 'bare'):
            return help_text(items)
        district = match(value, items) if action in ('subscribe', 'unsubscribe') else None
        if action in ('subscribe', 'unsubscribe') and district is None:
            shown = re.sub(r'[^\w .-]', '', value)[:40]
            return f'FloodPulse: "{shown}" is not a Karnataka district. Example: /start floodpulse udupi\nDistricts: ' + ', '.join(d['name'] for d in items) + '.'
        if action == 'status':
            with self.engine.connect().execution_options(postgresql_readonly=True) as c:
                names = self.names(c, key)
            return ('FloodPulse: your districts: ' + ', '.join(names) + '.') if names else 'FloodPulse: you are not subscribed to any district. Send /start floodpulse <district>, for example /start floodpulse udupi.'
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
                return (f'FloodPulse: you will receive administrator-approved flood alerts for {district["name"]} district.\n'
                        f'Your districts: {", ".join(self.names(c, key))}.\n'
                        f'Stop {district["name"]} alerts: /stop {normalize(district["name"])}. Stop all and delete your chat ID: /stop\n' + DISCLAIMER)
            if action == 'unsubscribe':
                if row is not None:
                    c.execute(delete(district_subscriptions).where(district_subscriptions.c.subscriber_key == key,
                                                                   district_subscriptions.c.district_id == district['id']))
                remaining = self.names(c, key)
                if row is not None and not remaining:
                    c.execute(delete(subscribers).where(subscribers.c.subscriber_key == key))
                return (f'FloodPulse: you will no longer receive {district["name"]} alerts.'
                        + (f' You still receive: {", ".join(remaining)}.' if remaining else ' You have no district alerts left; your chat ID is not stored by FloodPulse.'))
            c.execute(delete(subscribers).where(subscribers.c.subscriber_key == key))  # 'stop': districts cascade
            return 'FloodPulse: all district alerts stopped and your chat ID was deleted from FloodPulse. Send /start floodpulse <district> to subscribe again.'


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
