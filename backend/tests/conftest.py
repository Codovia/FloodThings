import socket

import pytest


@pytest.fixture(autouse=True)
def isolate_tests(monkeypatch, tmp_path):
    """Run in a temporary directory and forbid real network/database sockets."""
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        raise AssertionError("Real network or database access is forbidden in unit tests")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    yield
    assert list(tmp_path.iterdir()) == [], "Tests must not create data archives"
