"""Public endpoint rate limits, configurable thresholds and the routing daily cap."""
from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import rate_limit
from app.rate_limit import RateLimiter, group, install, parse_rule
from app.routing import DailyQuota


def test_groups_and_rule_parsing():
    assert group('/api/risk/area') == 'expensive' and group('/api/route') == 'expensive' and group('/api/admin/place') == 'expensive'
    assert group('/api/weather') == 'public' and group('/api/official/warnings') == 'public'
    assert group('/api/admin/shelters') is None and group('/api/telegram/webhook') is None and group('/api/reports') is None
    assert group('/api/health') is None and group('/shelters') is None
    assert parse_rule('10/30', (1, 1)) == (10, 30)
    for bad in (None, '', 'abc', '0/60', '5/-1', '5'):
        assert parse_rule(bad, (30, 60)) == (30, 60)


def test_sliding_window_per_address_and_retry_after():
    now = [1000.0]
    limiter = RateLimiter({'expensive': (2, 60), 'public': (100, 60)}, clock=lambda: now[0])
    assert limiter.check('expensive', 'a') == 0 and limiter.check('expensive', 'a') == 0
    assert limiter.check('expensive', 'a') == 60          # third request waits a full window
    assert limiter.check('expensive', 'b') == 0           # other addresses unaffected
    now[0] += 61
    assert limiter.check('expensive', 'a') == 0           # window slid


def test_middleware_returns_429_json_and_leaves_other_routes(monkeypatch):
    app = FastAPI()

    @app.get('/api/risk/area')
    def area():
        return {'ok': True}

    @app.get('/api/admin/shelters')
    def admin():
        return {'ok': True}
    install(app, RateLimiter({'expensive': (1, 60), 'public': (100, 60)}))
    with TestClient(app) as http:
        assert http.get('/api/risk/area').status_code == 200
        blocked = http.get('/api/risk/area')
        assert blocked.status_code == 429 and blocked.json()['status'] == 'rate_limited' and int(blocked.headers['retry-after']) >= 1
        for _ in range(3):
            assert http.get('/api/admin/shelters').status_code == 200


def test_thresholds_come_from_environment(monkeypatch):
    monkeypatch.setenv('FLOODPULSE_RATE_EXPENSIVE', '7/30')
    monkeypatch.setenv('FLOODPULSE_RATE_PUBLIC', 'nonsense')
    assert RateLimiter().rules == {'expensive': (7, 30), 'public': (300, 60)}


def test_routing_daily_cap_resets_each_day(monkeypatch):
    monkeypatch.setenv('FLOODPULSE_ROUTE_DAILY_LIMIT', '2')
    day = [date(2026, 10, 19)]
    quota = DailyQuota(clock=lambda: day[0])
    assert quota.take() and quota.take() and not quota.take()
    day[0] = date(2026, 10, 20)
    assert quota.take()


def test_login_and_report_limits_are_configurable(monkeypatch):
    from app.shelter_security import env_limit
    monkeypatch.setenv('FLOODPULSE_LOGIN_LIMIT_PER_ACCOUNT', '3')
    assert env_limit('FLOODPULSE_LOGIN_LIMIT_PER_ACCOUNT', 5) == 3
    for bad in ('0', '-4', 'many'):
        monkeypatch.setenv('FLOODPULSE_LOGIN_LIMIT_PER_ACCOUNT', bad)
        assert env_limit('FLOODPULSE_LOGIN_LIMIT_PER_ACCOUNT', 5) == 5
