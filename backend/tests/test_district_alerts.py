"""District Telegram alerts: commands, district matching and drafts (offline; no sockets or database)."""
import re
import uuid

import pytest
from pydantic import ValidationError

from app.district_alerts import ALIASES, FORMER_NAMES, help_reply, help_text, keyboard, match, parse, start_payload, suggest
from app.notifications import DraftInput, render_message

# The 31 districts as named by the active place directory (karnataka_location_directory_v2).
NAMES = {'bagalkot': 'Bagalkote', 'ballari': 'Ballari', 'belagavi': 'Belagavi', 'bangalorerural': 'Bengaluru Rural',
         'ramanagara': 'Bengaluru South', 'bengaluruurban': 'Bengaluru Urban', 'bidar': 'Bidar', 'chamrajnagar': 'Chamarajanagar',
         'chikkaballapur': 'Chikkaballapura', 'chikkamagaluru': 'Chikkamagaluru', 'chitradurga': 'Chitradurga', 'dk': 'Dakshina Kannada',
         'davanagere': 'Davanagere', 'dharwad': 'Dharwad', 'gadag': 'Gadag', 'hassan': 'Hassan', 'haveri': 'Haveri',
         'kalaburagi': 'Kalaburagi', 'kodagu': 'Kodagu', 'kolar': 'Kolar', 'koppal': 'Koppal', 'mandya': 'Mandya', 'mysore': 'Mysuru',
         'raichur': 'Raichur', 'shimoga': 'Shivamogga', 'tumkur': 'Tumakuru', 'udupi': 'Udupi', 'uttarakannada': 'Uttara Kannada',
         'vijayanagara': 'Vijayanagara', 'vijayapura': 'Vijayapura', 'yadgir': 'Yadgir'}
DISTRICTS = [{'id': f'nic:{k}.nic.in', 'name': v, 'start': start_payload(v)} for k, v in NAMES.items()]


@pytest.mark.parametrize('command, expected', [
    ('/start floodpulse udupi', ('subscribe', 'udupi')), ('/start floodpulse_dakshina_kannada', ('subscribe', 'dakshina_kannada')),
    ('/start FloodPulse-Kodagu', ('subscribe', 'Kodagu')), ('/start floodpulse', ('bare', '')), ('/start', ('help', '')),
    ('/start somethingelse', ('help', '')), ('/help', ('help', '')), ('/mydistricts', ('status', '')),
    ('/stop', ('stop', '')), ('/stop udupi', ('unsubscribe', 'udupi')), ('/stop floodpulse_udupi', ('unsubscribe', 'udupi')),
    ('Udupi', ('name', 'Udupi')), (' dakshina kannada ', ('name', 'dakshina kannada')), ('a', None), ('see http://x.test', None),
    ('', None), (None, None), ('/start floodpulse ' + 'x' * 300, None)])
def test_commands(command, expected):
    assert parse(command) == expected


@pytest.mark.parametrize('text, name', [('udupi', 'Udupi'), ('Udupi district', 'Udupi'), ('dakshina_kannada', 'Dakshina Kannada'),
    ('DakshinaKannada', 'Dakshina Kannada'), ('Mangalore', 'Dakshina Kannada'), ('coorg', 'Kodagu'), ('Belgaum', 'Belagavi'),
    ('bangalore', 'Bengaluru Urban'), ('Ramanagara', 'Bengaluru South'), ('bengaluru_south', 'Bengaluru South'), ('mysore', 'Mysuru')])
def test_district_names_and_former_names_match(text, name):
    assert match(text, DISTRICTS)['name'] == name


@pytest.mark.parametrize('text', ['goa', 'udup', 'kannada', ''])
def test_unknown_or_partial_names_do_not_guess(text):
    assert match(text, DISTRICTS) is None


def test_every_alias_points_to_a_directory_district_and_every_link_is_a_valid_start_parameter():
    ids = {d['id'] for d in DISTRICTS}
    assert set(ALIASES.values()) <= ids
    for d in DISTRICTS:
        assert re.fullmatch(r'[A-Za-z0-9_-]{1,64}', d['start']) and match(d['start'], DISTRICTS) is d
    assert 'Udupi' in help_text(DISTRICTS) and 'not an official warning' in help_text(DISTRICTS)


def test_a_draft_names_exactly_one_target_and_district_notices_say_how_to_stop():
    base = dict(request_id=uuid.uuid4(), kind='informational', message='Isolated protocol test only')
    for targets in ({}, {'destination_id': 'private-test', 'district_id': 'nic:udupi.nic.in'}, {'district_id': 'udupi'}):
        with pytest.raises(ValidationError):
            DraftInput(**base, **targets)
    draft = DraftInput(**base, district_id='nic:udupi.nic.in')
    out = render_message(draft, None, {'id': 'nic:udupi.nic.in', 'name': 'Udupi'})
    assert 'District: Udupi\n' in out and out.endswith('Stop: /stop udupi · Stop all: /stop') and draft.message in out
    assert render_message(DraftInput(**base, destination_id='private-test'), None).endswith(draft.message)


@pytest.mark.parametrize('typed, expected', [('udpi', ['Udupi']), ('dakshin kanada', ['Dakshina Kannada']), ('mangalor', ['Dakshina Kannada']),
    ('belgam', ['Belagavi']), ('shivamoga', ['Shivamogga']), ('chikmagalore', ['Chikkamagaluru']), ('davangare', ['Davanagere']),
    ('kannada', ['Uttara Kannada', 'Dakshina Kannada']), ('goa', []), ('hello', [])])
def test_misspelt_names_get_the_closest_districts_only(typed, expected):
    assert [d['name'] for d in suggest(typed, DISTRICTS)] == expected


def test_plain_messages_are_answered_only_when_clearly_close_to_a_district():
    assert [d['name'] for d in suggest('udpi', DISTRICTS, cutoff=0.75)] == ['Udupi']
    assert suggest('kannada', DISTRICTS, cutoff=0.75) == [] and suggest('thank you', DISTRICTS, cutoff=0.75) == []


def test_district_buttons_cover_every_district_with_short_labels():
    reply = help_reply(DISTRICTS); board = reply['reply_markup']
    names = [b['text'] for row in board['keyboard'] for b in row]
    assert names == [d['name'] for d in DISTRICTS] and all(len(row) <= 3 for row in board['keyboard'])
    assert board['one_time_keyboard'] and 1 <= len(board['input_field_placeholder']) <= 64 and 'Tap your district' in reply['text']
    assert all(match(n, DISTRICTS)['name'] == n for n in names)  # tapping a button sends a name that subscribes
    assert set(FORMER_NAMES) <= {d['id'] for d in DISTRICTS} and keyboard(DISTRICTS[:1], 'x' * 80)['input_field_placeholder'] == 'x' * 64

