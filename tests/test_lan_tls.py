"""Local HTTPS certificates for ./floodpulse.sh --lan, created with the real openssl in tmp_path only."""
from datetime import datetime
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import lan_tls


def text(*args):
    return subprocess.run(['openssl', *args], check=True, capture_output=True, text=True).stdout


def tls(tmp_path):
    (tmp_path / 'data/tmp/launcher').mkdir(parents=True)
    return tmp_path / 'data/tmp/launcher/tls'


def test_server_certificate_meets_phone_requirements_and_keys_stay_private(tmp_path):
    folder = tls(tmp_path)
    assert lan_tls.ensure(tmp_path, '192.168.1.5') is True
    certificate = str(folder / 'lan.crt')
    assert text('verify', '-CAfile', str(folder / 'ca.crt'), certificate).strip().endswith('OK')
    details = text('x509', '-in', certificate, '-noout', '-ext', 'subjectAltName,extendedKeyUsage,basicConstraints', '-dates')
    assert 'IP Address:192.168.1.5, IP Address:127.0.0.1' in details and 'TLS Web Server Authentication' in details and 'CA:FALSE' in details
    dates = dict(line.split('=', 1) for line in details.splitlines() if line.startswith('not'))
    days = (datetime.strptime(dates['notAfter'], '%b %d %H:%M:%S %Y %Z') - datetime.strptime(dates['notBefore'], '%b %d %H:%M:%S %Y %Z')).days
    assert days <= 825  # Apple's limit for TLS server certificates.
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert {name: stat.S_IMODE((folder / name).stat().st_mode) for name in ('ca.key', 'lan.key')} == {'ca.key': 0o600, 'lan.key': 0o600}


def test_certificates_are_reused_and_reissued_only_for_a_new_address(tmp_path):
    folder = tls(tmp_path)
    lan_tls.ensure(tmp_path, '10.0.0.7')
    ca, serial = (folder / 'ca.crt').read_bytes(), text('x509', '-in', str(folder / 'lan.crt'), '-noout', '-serial')
    assert lan_tls.ensure(tmp_path, '10.0.0.7') is False
    assert text('x509', '-in', str(folder / 'lan.crt'), '-noout', '-serial') == serial
    assert lan_tls.ensure(tmp_path, '10.0.0.8') is False and (folder / 'ca.crt').read_bytes() == ca
    assert 'IP Address:10.0.0.8,' in text('x509', '-in', str(folder / 'lan.crt'), '-noout', '-ext', 'subjectAltName')


@pytest.mark.parametrize('name', ['DNS:www.google.com', 'IP:8.8.8.8'])
def test_local_authority_cannot_vouch_for_websites_or_public_addresses(tmp_path, name):
    folder = tls(tmp_path)
    lan_tls.ensure(tmp_path, '192.168.1.5')
    (tmp_path / 'ext').write_text(f'subjectAltName={name}\nextendedKeyUsage=serverAuth\n')
    lan_tls.openssl('req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                    '-keyout', str(tmp_path / 'x.key'), '-out', str(tmp_path / 'x.csr'), '-subj', '/O=test')
    lan_tls.openssl('x509', '-req', '-in', str(tmp_path / 'x.csr'), '-CA', str(folder / 'ca.crt'), '-CAkey', str(folder / 'ca.key'),
                    '-set_serial', '1', '-days', '30', '-extfile', str(tmp_path / 'ext'), '-out', str(tmp_path / 'x.crt'))
    result = subprocess.run(['openssl', 'verify', '-CAfile', str(folder / 'ca.crt'), str(tmp_path / 'x.crt')], capture_output=True, text=True)
    assert result.returncode != 0 and 'permitted subtree violation' in result.stdout + result.stderr


def test_no_private_address_creates_nothing(tmp_path, monkeypatch, capsys):
    folder = tls(tmp_path)
    monkeypatch.setattr(lan_tls, 'lan_address', lambda: None)
    monkeypatch.setattr(sys, 'argv', ['lan_tls.py', str(tmp_path)])
    with pytest.raises(SystemExit) as stopped:
        lan_tls.main()
    assert 'private Wi-Fi/LAN address' in str(stopped.value.code) and not folder.exists()
