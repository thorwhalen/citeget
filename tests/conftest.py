"""Shared fixtures: a network that is a table, so no test ever dials out.

DNS is :class:`FakeDNS`; the transport (urllib3's ``create_connection``) is
:class:`FakeTransport`, a socket pair per connection carrying a canned HTTP
response, which records every address the guard lets through.
"""

import socket

import pytest

from citeget import netguard

PUBLIC_IP = "93.184.216.34"
OTHER_PUBLIC_IP = "93.184.216.35"


class FakeDNS:
    """``getaddrinfo`` from a table; numeric hosts parsed locally, never sent out."""

    def __init__(self, table):
        self.table = {k: list(v) for k, v in table.items()}
        self.calls = []
        self._real = socket.getaddrinfo

    def __call__(self, host, port, family=0, type=0, proto=0, flags=0):
        self.calls.append(host)
        if host in self.table:
            answers = self.table[host]
            ip = answers.pop(0) if len(answers) > 1 else answers[0]
            fam = socket.AF_INET6 if ":" in ip else socket.AF_INET
            sockaddr = (ip, port, 0, 0) if fam == socket.AF_INET6 else (ip, port)
            return [(fam, socket.SOCK_STREAM, 6, "", sockaddr)]
        # Numeric spellings (2130706433, 0x7f.1, ::ffff:127.0.0.1) only.
        return self._real(host, port, family, type, proto, flags | socket.AI_NUMERICHOST)


class FakeTransport:
    """Stands in for ``urllib3.util.connection.create_connection``."""

    def __init__(self, responses):
        self.responses = responses  # ip -> raw HTTP response bytes (or a list)
        self.connected = []
        self._peers = []  # keep each peer alive while its response is read

    def __call__(self, address, timeout=None, source_address=None, socket_options=None):
        ip, _port = address
        self.connected.append(ip)
        ours, theirs = socket.socketpair()
        canned = self.responses.get(ip, _response(404, b"nope"))
        if isinstance(canned, list):  # one per connection, the last one repeats
            canned = canned.pop(0) if len(canned) > 1 else canned[0]
        theirs.sendall(canned)
        theirs.shutdown(socket.SHUT_WR)
        self._peers.append(theirs)
        return ours


def _response(status, body=b"", headers=()):
    reason = {200: "OK", 302: "Found", 404: "Not Found"}.get(status, "X")
    lines = [f"HTTP/1.1 {status} {reason}", f"Content-Length: {len(body)}"]
    lines += [f"{k}: {v}" for k, v in headers]
    lines += ["Connection: close", "", ""]
    return "\r\n".join(lines).encode() + body


@pytest.fixture
def net(monkeypatch):
    """Install fake DNS + transport; return a small namespace to configure them."""
    from urllib3.util import connection

    monkeypatch.delenv(netguard.ALLOW_PRIVATE_ENV_VAR, raising=False)
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY"):
        monkeypatch.delenv(var, raising=False)

    class Net:
        dns = FakeDNS({})
        transport = FakeTransport({})

        def install(self):
            monkeypatch.setattr(socket, "getaddrinfo", self.dns)
            monkeypatch.setattr(connection, "create_connection", self.transport)

    n = Net()
    n.dns = FakeDNS({"good.example": [PUBLIC_IP]})
    n.transport = FakeTransport({PUBLIC_IP: _response(200, b"public page")})
    n.install()
    return n


