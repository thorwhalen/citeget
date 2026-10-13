"""The outbound-HTTP guard: what it refuses, and that it refuses at connect time.

No test here touches the network. DNS is a table (:class:`FakeDNS`), and the
transport is a socket pair per connection carrying a canned HTTP response
(:class:`FakeTransport`), so every address the guard lets through is recorded
instead of dialled.
"""

import socket

import pytest
import requests

from citeget import netguard
from citeget.netguard import NetPolicy, UnsafeURLError

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
        self.responses = responses  # ip -> raw HTTP response bytes
        self.connected = []
        self._peers = []  # keep each peer alive while its response is read

    def __call__(self, address, timeout=None, source_address=None, socket_options=None):
        ip, _port = address
        self.connected.append(ip)
        ours, theirs = socket.socketpair()
        theirs.sendall(self.responses.get(ip, _response(404, b"nope")))
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


# --- address classification ------------------------------------------------


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "127.1.2.3",
        "0.0.0.0",
        "10.0.0.5",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata
        "100.100.100.200",  # Alibaba metadata, CGNAT range
        "192.0.0.192",  # Oracle metadata
        "224.0.0.1",
        "255.255.255.255",
        "::1",
        "::",
        "fe80::1",
        "fe80::1%eth0",
        "fc00::1",
        "fd00:ec2::254",  # AWS IPv6 metadata
        "::ffff:127.0.0.1",  # IPv4-mapped
        "::ffff:169.254.169.254",
        "::127.0.0.1",  # IPv4-compatible
        "2002:7f00:1::",  # 6to4 wrapping 127.0.0.1
        "2002:a9fe:a9fe::",  # 6to4 wrapping 169.254.169.254
        "64:ff9b::7f00:1",  # NAT64 wrapping 127.0.0.1
        "64:ff9b::a9fe:a9fe",
        "ff02::1",
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_refused(address):
    assert not netguard.is_public_address(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "1.1.1.1", "2606:4700::1111"])
def test_public_addresses_pass(address):
    assert netguard.is_public_address(address)


# --- URL-level checks ------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "gopher://good.example/", "ftp://good.example/x", "//good.example/"],
)
def test_only_http_and_https_are_allowed(url):
    with pytest.raises(UnsafeURLError, match="scheme"):
        netguard.check_url(url)


def test_a_url_without_a_host_is_refused():
    with pytest.raises(UnsafeURLError, match="no host"):
        netguard.check_url("http:///path")


# --- connect-time enforcement ----------------------------------------------


def test_a_public_host_is_fetched(net):
    resp = netguard.get("http://good.example/paper")
    assert resp.status_code == 200 and resp.content == b"public page"
    assert net.transport.connected == [PUBLIC_IP]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]:8080/",
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:a9fe:a9fe]/",
        "http://2130706433/",  # decimal 127.0.0.1
        "http://0x7f.1/",  # hex + short form
        "http://017700000001/",  # octal
        "http://0177.0.0.1/",
        "http://127.1/",
        "http://0/",
        "https://127.0.0.1/",
        "http://localhost./",
    ],
)
def test_internal_destinations_are_refused_before_connecting(net, url):
    net.dns.table["localhost."] = ["127.0.0.1"]
    with pytest.raises(UnsafeURLError):
        netguard.get(url, timeout=5)
    assert net.transport.connected == []


def test_a_name_that_resolves_to_a_private_address_is_refused(net):
    net.dns.table["intranet.example"] = ["10.0.0.5"]
    with pytest.raises(UnsafeURLError, match="10.0.0.5"):
        netguard.get("http://intranet.example/")
    assert net.transport.connected == []


def test_a_redirect_to_an_internal_host_is_refused(net):
    net.dns.table["evil.example"] = ["169.254.169.254"]
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://evil.example/latest/meta-data/")]
    )
    with pytest.raises(UnsafeURLError, match="169.254.169.254"):
        netguard.get("http://good.example/")
    assert net.transport.connected == [PUBLIC_IP]


def test_a_redirect_to_an_internal_ip_literal_is_refused(net):
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://127.0.0.1:2019/config/")]
    )
    with pytest.raises(UnsafeURLError):
        netguard.get("http://good.example/")
    assert net.transport.connected == [PUBLIC_IP]


def test_a_redirect_to_a_file_url_is_refused(net):
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "file:///etc/passwd")]
    )
    with pytest.raises(UnsafeURLError, match="scheme"):
        netguard.get("http://good.example/")


def test_a_redirect_to_a_public_host_is_followed(net):
    net.dns.table["mirror.example"] = [OTHER_PUBLIC_IP]
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://mirror.example/file.pdf")]
    )
    net.transport.responses[OTHER_PUBLIC_IP] = _response(200, b"%PDF-1.4")
    resp = netguard.get("http://good.example/")
    assert resp.content == b"%PDF-1.4"
    assert net.transport.connected == [PUBLIC_IP, OTHER_PUBLIC_IP]


def test_dns_rebinding_cannot_swap_the_address_after_the_check(net):
    """The host resolves once per connection, and the socket goes to that answer.

    The rebinding server answers public first, then loopback. The guard must
    connect to the public answer it vetted, never look the name up again.
    """
    net.dns.table["rebind.example"] = [PUBLIC_IP, "127.0.0.1"]
    netguard.get("http://rebind.example/")
    assert net.dns.calls.count("rebind.example") == 1
    assert net.transport.connected == [PUBLIC_IP]


def test_a_name_with_any_private_record_is_refused_outright(net, monkeypatch):
    def mixed(host, port, *a, **k):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", mixed)
    with pytest.raises(UnsafeURLError, match="127.0.0.1"):
        netguard.get("http://mixed.example/")
    assert net.transport.connected == []


def test_environment_proxies_are_ignored(net, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://10.0.0.1:3128")
    monkeypatch.setenv("http_proxy", "http://10.0.0.1:3128")
    netguard.get("http://good.example/")
    assert net.transport.connected == [PUBLIC_IP]


def test_explicit_proxies_are_refused(net):
    with pytest.raises(UnsafeURLError, match="proxy"):
        netguard.get("http://good.example/", proxies={"http": "http://good.example:3128"})
    assert net.transport.connected == []


def test_https_connections_are_guarded_too():
    pools = netguard._pool_classes(NetPolicy())
    assert set(pools) == {"http", "https"}
    for pool in pools.values():
        assert pool.ConnectionCls._new_conn.__qualname__.startswith("_pool_classes")


# --- opting out --------------------------------------------------------------


def test_the_guard_can_be_switched_off_by_environment(net, monkeypatch):
    monkeypatch.setenv(netguard.ALLOW_PRIVATE_ENV_VAR, "1")
    net.transport.responses["127.0.0.1"] = _response(200, b"local")
    assert netguard.get("http://127.0.0.1:8000/").content == b"local"
    assert net.transport.connected == ["127.0.0.1"]


def test_the_guard_can_be_switched_off_by_policy(net):
    net.transport.responses["127.0.0.1"] = _response(200, b"local")
    policy = NetPolicy(allow_private=True)
    assert netguard.get("http://127.0.0.1/", policy=policy).content == b"local"


def test_switching_the_guard_off_still_restricts_schemes():
    with pytest.raises(UnsafeURLError, match="scheme"):
        netguard.check_url("file:///etc/passwd", policy=NetPolicy(allow_private=True))


# --- the callers ---------------------------------------------------------------


def test_fetch_one_reports_a_refusal_and_writes_nothing(net, tmp_path):
    from citeget.fetch import fetch_one

    result = fetch_one("http://169.254.169.254/latest/meta-data/", output_dir=tmp_path)
    assert result.status == "failed"
    assert "Refused" in result.error
    assert list(tmp_path.iterdir()) == []
    assert net.transport.connected == []


def test_fetch_one_still_fetches_a_public_page(net, tmp_path):
    from citeget.fetch import fetch_one

    net.transport.responses[PUBLIC_IP] = _response(
        200, b"<html><body><h1>Hello</h1></body></html>",
        headers=[("Content-Type", "text/html")],
    )
    result = fetch_one("http://good.example/post", output_dir=tmp_path)
    pytest.importorskip("markdownify")
    assert result.status == "ok"
    assert "# Hello" in result.output_file.read_text()


def test_direct_reference_download_refuses_internal_urls(net, tmp_path):
    from citeget.acquire_references import _download_url

    assert _download_url("http://127.0.0.1:2019/config/", tmp_path / "x.pdf") is False
    assert net.transport.connected == []


def test_registered_downloaders_refuse_internal_urls(net, tmp_path):
    from citeget.resolve import _any_downloader, _pdf_downloader

    for downloader in (_any_downloader, _pdf_downloader):
        assert downloader("http://10.0.0.5/", tmp_path / "x") is False
    assert net.transport.connected == []


def test_offline_html_drops_everything_that_loads():
    from citeget.fetch import _offline_html

    html = (
        '<body background="http://10.0.0.1/bg"><p style="background:url(http://x)">Text</p>'
        '<iframe src="http://127.0.0.1/"></iframe><img src="http://169.254.169.254/">'
        '<object data="file:///etc/passwd"></object><link rel=stylesheet href="http://x">'
        '<meta http-equiv="refresh" content="0;url=http://127.0.0.1/">'
        '<svg><image href="http://127.0.0.1/"/></svg><a href="https://ok.example/">link</a>'
        '<div onload="x()">d</div></body>'
    )
    out = _offline_html(html)
    for needle in ("10.0.0.1", "127.0.0.1", "169.254", "file:", "style=", "onload", "refresh"):
        assert needle not in out
    assert "Text" in out and 'href="https://ok.example/"' in out


def test_html_to_pdf_never_hands_wkhtmltopdf_a_url_by_default(net, monkeypatch):
    import sys
    import types

    calls = []
    fake = types.SimpleNamespace(
        from_url=lambda *a, **k: calls.append(("url", a, k)) or b"%PDF",
        from_string=lambda *a, **k: calls.append(("string", a, k)) or b"%PDF",
    )
    monkeypatch.setitem(sys.modules, "pdfkit", fake)
    from citeget.fetch import html_to_pdf

    assert html_to_pdf("http://127.0.0.1/") is None  # refused, nothing rendered
    net.transport.responses[PUBLIC_IP] = _response(
        200, b'<p>hi</p><iframe src="file:///etc/passwd"></iframe>'
    )
    assert html_to_pdf("http://good.example/") == b"%PDF"
    [(kind, args, kwargs)] = calls
    assert kind == "string" and "passwd" not in args[0]
    assert "disable-local-file-access" in kwargs["options"]
    assert "enable-local-file-access" not in kwargs["options"]
