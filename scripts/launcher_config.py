"""Load private local configuration, then exec the launcher; never log secrets."""
import errno
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import quote, urlsplit, urlunsplit


CONNECTIONS = {'DATABASE_URL', 'SHELTER_DATABASE_URL'}
TELEGRAM_KEYS = {'TELEGRAM_BOT_USERNAME', 'TELEGRAM_BOT_TOKEN',
                 'TELEGRAM_DESTINATIONS', 'TELEGRAM_WEBHOOK_SECRET'}
ROUTING_KEYS = {'OPENROUTESERVICE_API_KEY'}  # Backend only; launcher_processes strips it from Vite.


def private_file(path, limit, required_mode=None):
    # Validate the opened descriptor: no symlink swap or FIFO blocking before checks.
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        if error.errno == errno.ELOOP:
            raise ValueError('Private file must not be a symlink') from None
        raise
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or (required_mode is not None and stat.S_IMODE(info.st_mode) != required_mode)):
            raise ValueError('Private file must be user-owned, regular and owner-only')
        data = stream.read(limit + 1)
        if info.st_size > limit or len(data) > limit:
            raise ValueError('Private file exceeds size limit')
    return data.decode('utf-8')


def telegram_environment(root, environment):
    """Read only Telegram and routing keys; no evaluation, interpolation or DB overrides."""
    result = dict(environment)
    try:
        contents = private_file(root / '.env', 65536, required_mode=0o600)
    except FileNotFoundError:
        # A dangling symlink is invalid configuration, not an absent optional file.
        if (root / '.env').is_symlink():
            raise ValueError('Invalid private Telegram configuration') from None
        return result
    try:
        if any(ord(c) < 32 and c not in '\r\n\t' for c in contents):
            raise ValueError()
        seen = set()
        for line in contents.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            match = re.fullmatch(r'(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*(.*)', line)
            if not match or match[1] in seen:
                raise ValueError()
            key, raw = match[1], match[2]
            seen.add(key)
            if raw.startswith('"'):
                value, end = json.JSONDecoder().raw_decode(raw)
                tail = raw[end:].strip()
                if tail and not tail.startswith('#'):
                    raise ValueError()
            elif raw.startswith("'"):
                end = raw.index("'", 1)
                value, tail = raw[1:end], raw[end + 1:].strip()
                if tail and not tail.startswith('#'):
                    raise ValueError()
            else:
                value = re.split(r'[ \t]+#', raw, maxsplit=1)[0].rstrip()
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError()
            value.encode('utf-8')  # Reject escaped surrogates before exec errors can echo values.
            if key in TELEGRAM_KEYS | ROUTING_KEYS:
                result.setdefault(key, value)  # Explicit empty values also override.
        return result
    except (ValueError, TypeError):
        raise ValueError('Invalid private Telegram configuration') from None


def configured_environment(root, environment):
    """Environment overrides the profile; referenced passwords exist only in memory."""
    result = dict(environment)
    profile = json.loads(private_file(root / 'data/tmp/launcher/config.json', 16384))
    if set(profile) != {'database_connections'}:
        raise ValueError('Unknown profile fields')
    connections = profile['database_connections']
    if not isinstance(connections, dict) or set(connections) != CONNECTIONS:
        raise ValueError('Both service connections must be explicitly configured')
    for name, record in connections.items():
        if not isinstance(record, dict) or set(record) != {'url', 'password_file'}:
            raise ValueError('Invalid connection reference')
        if result.get(name):
            continue
        parsed = urlsplit(record['url'])
        if (parsed.scheme != 'postgresql+psycopg' or not parsed.username
                or parsed.password is not None or parsed.hostname != '127.0.0.1'
                or parsed.port != 55436 or parsed.path != '/floodpulse_directory'
                or parsed.query or parsed.fragment):
            raise ValueError('Expected credential-free local service URL')
        password = private_file(root / record['password_file'], 4096).strip()
        if not password or '\n' in password or '\r' in password or '\x00' in password:
            raise ValueError('Invalid password file')
        authority = f'{parsed.username}:{quote(password, safe="")}@{parsed.hostname}:{parsed.port}'
        result[name] = urlunsplit((parsed.scheme, authority, parsed.path, '', ''))
    result['FLOODPULSE_CONFIG_LOADED'] = '1'
    return result


def main():
    root = Path(sys.argv[1]).resolve()
    try:
        environment = telegram_environment(root, os.environ)
    except (OSError, ValueError):
        sys.exit('FloodPulse: root .env unavailable/invalid. Use a user-owned regular 0600 file with valid single-line assignments; no configuration values are printed.')
    try:
        if (not all(environment.get(key) for key in CONNECTIONS)
                and (root / 'data/tmp/launcher/config.json').exists()):
            environment = configured_environment(root, environment)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        sys.exit('FloodPulse: private launcher profile unavailable/invalid. Check data/tmp/launcher/config.json and referenced file ownership/0600 permissions; no configuration values are printed.')
    environment['FLOODPULSE_CONFIG_LOADED'] = '1'
    os.execve(str(root / 'start.sh'), [str(root / 'start.sh'), *sys.argv[2:]], environment)


if __name__ == '__main__':
    main()
