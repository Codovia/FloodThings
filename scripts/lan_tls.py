"""Same-Wi-Fi HTTPS for ./floodpulse.sh --lan.

Creates (once) a private certificate authority for this laptop and, per Wi-Fi address, a server
certificate it signs. Phones and other laptops trust the CA once; after that GPS, camera, reports and
admin sign-in work as on the HTTPS server, under the unchanged origin and Secure-cookie rules.
The CA may sign private IP addresses only (name constraints), never a website name, and its key stays
in data/tmp/launcher/tls (0700, keys 0600; data/tmp is not in Git).

Usage: lan_tls.py ROOT  ->  prints the Wi-Fi address; messages go to stderr.
"""
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile

from launcher_processes import lan_address, LAN_MISSING

CA_DAYS = 3650
SERVER_DAYS = 397      # Below Apple's 825-day limit for TLS server certificates.
RENEW_SECONDS = 30 * 24 * 3600
CA_CONSTRAINTS = ('nameConstraints=critical,permitted;IP:10.0.0.0/255.0.0.0,permitted;IP:172.16.0.0/255.240.0.0,'
                  'permitted;IP:192.168.0.0/255.255.0.0,permitted;IP:127.0.0.0/255.0.0.0,permitted;DNS:floodpulse.invalid')


def openssl(*args):
    subprocess.run(['openssl', *args], check=True, stdin=subprocess.DEVNULL,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


def valid(certificate, *extra):
    try:
        openssl('x509', '-in', str(certificate), '-noout', '-checkend', str(RENEW_SECONDS), *extra)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def server_matches(folder, address):
    try:
        names = subprocess.run(['openssl', 'x509', '-in', str(folder / 'lan.crt'), '-noout', '-ext', 'subjectAltName'],
                               check=True, capture_output=True, text=True, timeout=30).stdout
        openssl('verify', '-CAfile', str(folder / 'ca.crt'), str(folder / 'lan.crt'))
    except (subprocess.CalledProcessError, OSError):
        return False
    return f'IP Address:{address},' in names.replace('\n', ',') + ',' and valid(folder / 'lan.crt')


def private_folder(root):
    folder = root / 'data/tmp/launcher/tls'
    folder.mkdir(mode=0o700, exist_ok=True)
    info = folder.lstat()
    if folder.is_symlink() or info.st_uid != os.getuid():
        raise ValueError('TLS folder must be a user-owned directory')
    folder.chmod(0o700)
    return folder


def ensure(root, address):
    """Returns True when a new CA was created (every device must then install it again)."""
    folder = private_folder(root)
    new_ca = not ((folder / 'ca.key').exists() and valid(folder / 'ca.crt'))
    if new_ca:
        for name in ('ca.key', 'ca.crt', 'lan.key', 'lan.crt'):
            (folder / name).unlink(missing_ok=True)
        openssl('req', '-x509', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                '-keyout', str(folder / 'ca.key'), '-out', str(folder / 'ca.crt'), '-days', str(CA_DAYS), '-sha256',
                '-subj', f'/O=FloodPulse local test/CN=FloodPulse local test CA {secrets.token_hex(4)}',
                '-addext', 'basicConstraints=critical,CA:TRUE,pathlen:0',
                '-addext', 'keyUsage=critical,keyCertSign,cRLSign', '-addext', CA_CONSTRAINTS)
    if new_ca or not server_matches(folder, address):
        with tempfile.TemporaryDirectory(dir=folder) as work:
            work = Path(work)
            (work / 'ext').write_text(f'subjectAltName=IP:{address},IP:127.0.0.1\nbasicConstraints=critical,CA:FALSE\n'
                                      'keyUsage=critical,digitalSignature\nextendedKeyUsage=serverAuth\n')
            openssl('req', '-new', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1', '-nodes',
                    '-keyout', str(work / 'lan.key'), '-out', str(work / 'lan.csr'), '-subj', '/O=FloodPulse local test')
            openssl('x509', '-req', '-in', str(work / 'lan.csr'), '-CA', str(folder / 'ca.crt'), '-CAkey', str(folder / 'ca.key'),
                    '-set_serial', '0x' + secrets.token_hex(16), '-days', str(SERVER_DAYS), '-sha256',
                    '-extfile', str(work / 'ext'), '-out', str(work / 'lan.crt'))
            for name in ('lan.key', 'lan.crt'):
                os.replace(work / name, folder / name)
    for name in ('ca.key', 'lan.key'):
        (folder / name).chmod(0o600)
    for name in ('ca.crt', 'lan.crt'):
        (folder / name).chmod(0o644)
    return new_ca


def main():
    root = Path(sys.argv[1]).resolve()
    address = lan_address()
    if not address:
        sys.exit('FloodPulse: ' + LAN_MISSING)
    try:
        if ensure(root, address):
            print('FloodPulse: created a new local certificate for this laptop; install it on each device (README, "Same Wi-Fi").',
                  file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        sys.exit('FloodPulse: could not create the local HTTPS certificate (needs openssl); nothing was opened to the network.')
    print(address)


if __name__ == '__main__':
    main()
