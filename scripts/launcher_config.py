"""Load private local connection references, then exec the launcher; never log secrets."""
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import quote, urlsplit, urlunsplit


CONNECTIONS = {'DATABASE_URL', 'SHELTER_DATABASE_URL'}


def private_file(path, limit):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('Private file must be user-owned, regular and owner-only')
    if info.st_size > limit:
        raise ValueError('Private file exceeds size limit')
    return path.read_text()


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
        environment = configured_environment(root, os.environ)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        sys.exit('FloodPulse: private launcher profile unavailable/invalid. Check data/tmp/launcher/config.json and referenced file ownership/0600 permissions; no configuration values are printed.')
    os.execve(str(root / 'start.sh'), [str(root / 'start.sh'), *sys.argv[2:]], environment)


if __name__ == '__main__':
    main()
