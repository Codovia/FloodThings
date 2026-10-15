"""Full supervisor with real isolated processes/ports and fake provider responses.

Every port is relocated in temporary source copies. The production launcher,
database, Telegram, Cloudflare and existing proxy are never started/contacted.
"""
import json
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]

APP = r'''
import os,sys,subprocess,time,signal
from pathlib import Path
root=Path(__file__).resolve().parent
if '--check' in sys.argv:
 (root/'checked').touch();sys.exit(0)
sys.path.insert(0,str(root/'scripts'))
from launcher_config import telegram_environment
os.environ.update(telegram_environment(root,os.environ))
(root/'app-started').touch()
print('discarded-private-application-log',flush=True)
code=r"""
import os,sys,json,signal,time,subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
root=Path(sys.argv[1]);port=int(sys.argv[2]);kind=sys.argv[3]
with (root/'pids').open('a') as f:f.write(str(os.getpid())+'\n')
if kind=='backend':
 assert all(os.environ.get(k) for k in ['TELEGRAM_BOT_TOKEN','TELEGRAM_WEBHOOK_SECRET','TELEGRAM_DESTINATIONS'])
 assert 'LOCATION_DIRECTORY_ADMIN_URL' not in os.environ
 worker=subprocess.Popen([sys.executable,'-c',"import os,signal,time;os.setsid();signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(90)"])
 with (root/'pids').open('a') as f:f.write(str(worker.pid)+'\n')
else:
 assert not any(k.startswith('TELEGRAM_') or k in ['DATABASE_URL','SHELTER_DATABASE_URL','LOCATION_DIRECTORY_ADMIN_URL'] for k in os.environ)
 (root/'frontend-isolated').touch()
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_GET(self):
  value={'mode':'live'} if self.path=='/api/environment' else {'status':'available','url':'https://t.me/FloodPulsebot?start=floodpulse'} if self.path=='/api/alerts/subscription' else {'status':'ok'}
  body=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  self.send_response(403);self.send_header('Content-Length','0');self.end_headers()
server=ThreadingHTTPServer(('127.0.0.1',port),Handler);server.serve_forever()
"""
children=[]
for kind,port in [('backend',BACKEND_PORT),('frontend',FRONTEND_PORT)]:
 env=dict(os.environ)
 if kind=='frontend':
  env={k:v for k,v in env.items() if not k.startswith('TELEGRAM_') and k not in ['DATABASE_URL','SHELTER_DATABASE_URL','LOCATION_DIRECTORY_ADMIN_URL']}
 children.append(subprocess.Popen([sys.executable,'-B','-c',code,str(root),str(port),kind],env=env))
def stop(*a):
 for child in children:child.terminate()
 for child in children:child.wait()
 sys.exit(0)
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
time.sleep(90)
'''

TUNNEL = r'''
import json,os,sys,time
from pathlib import Path
root=Path(__file__).resolve().parent
assert not any(k.startswith('TELEGRAM_') or k in ['DATABASE_URL','SHELTER_DATABASE_URL','LOCATION_DIRECTORY_ADMIN_URL','HTTPS_PROXY','TUNNEL_TOKEN'] for k in os.environ)
assert sys.argv[1:]==['--no-autoupdate','tunnel','--config','/dev/null','--url','http://127.0.0.1:PROXY_PORT','--logformat','json','--loglevel','info','--metrics','127.0.0.1:0']
(root/'cloud-isolated').touch()
with (root/'pids').open('a') as f:f.write(str(os.getpid())+'\n')
mode=(root/'mode').read_text()
if mode=='cloud-failure':sys.exit(9)
if mode=='cloud-timeout':time.sleep(90)
url='http://invalid.trycloudflare.com' if mode=='invalid-url' else 'https://rehearsal.trycloudflare.com'
print('discarded-private-cloudflare-log',flush=True)
print(json.dumps({'message':'| '+url+' |'}),flush=True)
if mode=='late-failure':time.sleep(.8);sys.exit(9)
time.sleep(90)
'''

DRIVER = r'''
import json,os,sys
from pathlib import Path
root=Path(__file__).resolve().parent;sys.path.insert(0,str(root/'scripts'))
import full_launcher as f
from telegram_webhook_setup import load_configuration
f.START_TIMEOUT=4;f.TUNNEL_TIMEOUT=.4;f.PUBLIC_TIMEOUT=.8;f.GRACE=.2;f.TERM_GRACE=.2
mode=(root/'mode').read_text()
class Telegram:
 def __init__(self,config):self.config=config;self.url='https://unrelated.example/hook' if mode=='unrelated-webhook' else ''
 def call(self,method,payload=None):
  with (root/'telegram-calls').open('a') as stream:stream.write(method+'\n')
  if method=='getMe':return {'id':int(self.config.token.split(':')[0]),'is_bot':True,'username':'FloodPulsebot'}
  if method=='getWebhookInfo':return {'url':self.url,'allowed_updates':['message'],'max_connections':4}
  assert method=='setWebhook'
  assert payload['secret_token']==self.config.secret and payload['drop_pending_updates'] is False
  self.url=payload['url'];return True
f.TelegramAPI=Telegram
original=f.wait_public
def public(origin,pulse,environment):
 def resolver(*args):return ['1.1.1.1']
 def probe(origin,path,method,addresses):return f.local_status(PROXY_PORT,path,method)[0]
 return original(origin,pulse,environment,resolver,probe)
f.wait_public=public
if '--check' in sys.argv:
 sys.exit(f.main())
if mode=='local-only':sys.exit(f.main())
try:
 config=load_configuration(root,os.environ)
 sys.exit(f.supervise(root,os.environ,config,str(root/'cloudflared')))
except (f.SetupError,f.LaunchError) as error:
 print('FloodPulse: '+str(error),file=sys.stderr);sys.exit(1)
'''


def active(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
    except FileNotFoundError:
        return False


@pytest.fixture
def project(tmp_path):
    # Reserve three free ports together, then release before isolated launch.
    sockets = [socket.socket() for _ in range(3)]
    for sock in sockets:
        sock.bind(('127.0.0.1', 0))
    ports = [sock.getsockname()[1] for sock in sockets]
    for sock in sockets:
        sock.close()
    replacements = dict(zip(['18050', '14180', '18060'], map(str, ports)))
    def relocate(text):
        for original, replacement in replacements.items():
            text = text.replace(original, replacement)
        return text
    scripts = tmp_path / 'scripts'; scripts.mkdir()
    for name in ['full_launcher.py', 'telegram_webhook_setup.py', 'telegram_webhook_proxy.py', 'launcher_config.py', 'launcher_processes.py']:
        (scripts / name).write_text(relocate((ROOT / 'scripts' / name).read_text()))
    venv = tmp_path / 'backend/.venv/bin'; venv.mkdir(parents=True)
    (venv / 'python').symlink_to(sys.executable)
    package = tmp_path / 'backend/app'; package.mkdir()
    (package / '__init__.py').touch()
    (package / 'telegram_delivery.py').write_bytes((ROOT / 'backend/app/telegram_delivery.py').read_bytes())
    replacements = {'BACKEND_PORT': str(ports[0]), 'FRONTEND_PORT': str(ports[1]), 'PROXY_PORT': str(ports[2])}
    for name, body in [('start.sh', APP), ('cloudflared', TUNNEL), ('driver.py', DRIVER)]:
        for original, replacement in replacements.items():
            body = body.replace(original, replacement)
        path = tmp_path / name; path.write_text('#!' + sys.executable + '\n' + body); path.chmod(0o700)
    token = str(secrets.randbelow(900000) + 100000) + ':' + secrets.token_urlsafe(32)
    secret, password = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    private = {'TELEGRAM_BOT_USERNAME': 'FloodPulsebot', 'TELEGRAM_BOT_TOKEN': token, 'TELEGRAM_WEBHOOK_SECRET': secret,
               'TELEGRAM_DESTINATIONS': json.dumps({'test': {'label': 'Isolated fixture', 'chat_id': str(secrets.randbelow(100000) + 1), 'test_only': True}})}
    path = tmp_path / '.env'; path.write_text('\n'.join(k + '=' + json.dumps(v) for k, v in private.items())); path.chmod(0o600)
    (tmp_path / 'mode').write_text('success')
    (tmp_path / 'database-preserved').write_text(secrets.token_hex(32))
    env = {'PATH': str(tmp_path) + ':' + os.environ['PATH'], 'LANG': 'C.UTF-8',
           'DATABASE_URL': password, 'SHELTER_DATABASE_URL': password, 'LOCATION_DIRECTORY_ADMIN_URL': password,
           'HTTPS_PROXY': password, 'TUNNEL_TOKEN': password}
    before = {name: (tmp_path / name).read_bytes() for name in ['.env', 'database-preserved']}
    processes = []
    def launch(*args):
        child = subprocess.Popen([sys.executable, '-B', str(tmp_path / 'driver.py'), *args], cwd=tmp_path,
                                 env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
        processes.append(child)
        return child
    yield tmp_path, ports, launch
    for child in processes:
        if child.poll() is None:
            child.send_signal(signal.SIGTERM)
        output = child.communicate(timeout=12)[0]
        for private_value in [token, secret, password, 'discarded-private-application-log', 'discarded-private-cloudflare-log']:
            assert private_value not in output
    for name, contents in before.items():
        assert (tmp_path / name).read_bytes() == contents
    if (tmp_path / 'pids').exists():
        assert not any(active(int(pid)) for pid in (tmp_path / 'pids').read_text().splitlines()), 'Owned process orphaned'


def ready(root, child):
    receipt = root / 'data/tmp/full_launcher/webhook.json'
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if receipt.exists():
            return
        if child.poll() is not None:
            pytest.fail('Isolated startup failed: ' + child.communicate()[0])
        time.sleep(.02)
    pytest.fail('Isolated startup did not become ready')


@pytest.mark.parametrize('sig', [signal.SIGINT, signal.SIGTERM])
def test_complete_startup_signal_cleanup_and_repeat(project, sig):
    root, ports, launch = project
    for _ in range(2):
        receipt = root / 'data/tmp/full_launcher/webhook.json'; receipt.unlink(missing_ok=True)
        child = launch(); ready(root, child)
        assert (root / 'frontend-isolated').exists() and (root / 'cloud-isolated').exists()
        child.send_signal(sig)
        output = child.communicate(timeout=10)[0]
        assert child.returncode == 128 + sig
        assert 'webhook registration: verified' in output
        assert receipt.exists() and not (receipt.parent / 'processes.json').exists()
        for port in ports:
            with socket.socket() as check:
                check.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); check.bind(('127.0.0.1', port))


@pytest.mark.parametrize('mode,expected', [('cloud-failure', 'failed'), ('cloud-timeout', 'before timeout'),
    ('invalid-url', 'failed'), ('unrelated-webhook', 'unrelated'), ('late-failure', 'failed')])
def test_failures_stop_only_owned_services(project, mode, expected):
    root, ports, launch = project
    (root / 'mode').write_text(mode)
    child = launch()
    output = child.communicate(timeout=10)[0]
    assert child.returncode == 1 and expected in output
    if mode != 'late-failure':
        assert 'webhook registration: verified' not in output
        if (root / 'telegram-calls').exists():
            assert 'setWebhook' not in (root / 'telegram-calls').read_text()


def test_unrelated_listener_is_not_terminated(project):
    root, ports, launch = project
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', ports[2])); listener.listen()
        child = launch(); output = child.communicate(timeout=5)[0]
        assert child.returncode == 1 and str(ports[2]) in output and 'PID' in output
        assert not (root / 'app-started').exists()
        assert listener.getsockname()[1] == ports[2]


def test_exclusive_lock_and_no_check_side_effects(project):
    root, ports, launch = project
    child = launch('--check', '--telegram'); output = child.communicate(timeout=5)[0]
    assert child.returncode == 0 and 'No service started' in output
    assert (root / 'checked').exists() and not (root / 'data').exists()
    assert not (root / 'telegram-calls').exists() and not (root / 'app-started').exists()
    running = launch(); ready(root, running)
    second = launch(); output = second.communicate(timeout=5)[0]
    assert second.returncode == 1 and 'already running' in output
    check = launch('--check', '--telegram'); output = check.communicate(timeout=5)[0]
    assert check.returncode == 1 and 'already running' in output
    running.send_signal(signal.SIGTERM); running.communicate(timeout=10)


def test_recovery_after_killed_supervisor_and_no_pid_takeover(project):
    root, ports, launch = project
    child = launch(); ready(root, child)
    receipt = root / 'data/tmp/full_launcher/processes.json'
    original = json.loads(receipt.read_text())
    child.kill(); child.wait(timeout=3)
    (root / 'data/tmp/full_launcher/webhook.json').unlink()
    recovered = launch(); ready(root, recovered)
    assert json.loads(receipt.read_text())['run_id'] != original['run_id']
    recovered.send_signal(signal.SIGTERM); recovered.communicate(timeout=10)


@pytest.mark.parametrize('problem', ['permissions', 'missing', 'malformed'])
def test_invalid_private_configuration_starts_nothing(project, problem):
    root, ports, launch = project
    path = root / '.env'; before = path.read_bytes()
    try:
        if problem == 'permissions':path.chmod(0o644)
        elif problem == 'missing':path.unlink()
        else:path.write_text('not an assignment')
        child = launch(); output = child.communicate(timeout=5)[0]
        assert child.returncode == 1 and 'Private Telegram configuration' in output
        assert not (root / 'app-started').exists() and not (root / 'telegram-calls').exists()
    finally:
        path.write_bytes(before); path.chmod(0o600)


def test_without_telegram_uses_only_existing_application(project):
    root, ports, launch = project
    (root / 'mode').write_text('local-only')
    child = launch()
    deadline = time.monotonic() + 6
    while not (root / 'frontend-isolated').exists() and time.monotonic() < deadline:
        assert child.poll() is None
        time.sleep(.02)
    assert (root / 'frontend-isolated').exists()
    child.send_signal(signal.SIGINT); output = child.communicate(timeout=10)[0]
    assert child.returncode == 130
    assert not (root / 'cloud-isolated').exists() and not (root / 'telegram-calls').exists()


def test_help_is_available_without_configuration_or_environment(tmp_path):
    script = tmp_path / 'start-full.sh'
    script.write_bytes((ROOT / 'start-full.sh').read_bytes()); script.chmod(0o700)
    result = subprocess.run([str(script), '--help'], env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=3)
    assert result.returncode == 0 and 'Usage:' in result.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ['start-full.sh']


def test_ctrl_c_during_tunnel_startup_cleans_every_owned_process(project):
    root, ports, launch = project
    (root / 'mode').write_text('cloud-timeout')
    child = launch()
    deadline = time.monotonic() + 6
    while not (root / 'cloud-isolated').exists() and time.monotonic() < deadline:
        assert child.poll() is None
        time.sleep(.01)
    assert (root / 'cloud-isolated').exists()
    child.send_signal(signal.SIGINT); child.communicate(timeout=10)
    assert child.returncode == 130 and not (root / 'telegram-calls').exists()
    assert not (root / 'data/tmp/full_launcher/processes.json').exists()


def test_missing_cloudflared_fails_check_without_starting_or_registration(project):
    root, ports, launch = project
    (root / 'cloudflared').unlink()
    # Remove the system executable from lookup without affecting Python/start.sh.
    driver = root / 'driver.py'
    driver.write_text(driver.read_text().replace("if '--check' in sys.argv:", "f.shutil.which=lambda name: None\nif '--check' in sys.argv:"))
    child = launch('--check', '--telegram'); output = child.communicate(timeout=5)[0]
    assert child.returncode == 1 and 'cloudflared is missing' in output
    assert not (root / 'app-started').exists() and not (root / 'telegram-calls').exists()
