"""The outbound-HTTP guard: what it refuses, and that it refuses at connect time.

No test here touches the network: the ``net`` fixture (``conftest.py``) makes
DNS a table and the transport a recorder of every address the guard lets
through.
"""

import socket

import pytest
import requests

from citeget import netguard
from citeget.netguard import NetPolicy, UnsafeURLError

from tests.conftest import OTHER_PUBLIC_IP, PUBLIC_IP, _response  # noqa: E402


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
        "::ffff:0:7f00:1",  # SIIT wrapping 127.0.0.1
        "::ffff:0:a9fe:a9fe",
        "fec0::1",  # site-local
        "not-an-ip",
    ],
)
def test_non_public_addresses_are_refused(address):
    assert not netguard.is_public_address(address)


@pytest.mark.parametrize(
    "address",
    ["93.184.216.34", "1.1.1.1", "2606:4700::1111", "::ffff:8.8.8.8", "64:ff9b::808:808"],
)
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
        configuration=lambda **k: k,
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


@pytest.mark.parametrize(
    "html",
    [
        '<!-- <meta name="pdfkit-allow" content="/etc"> --><p>x</p>',
        '<!--><meta name="pdfkit-header-html" content="file:///etc/hostname">--><p>x</p>',
        '<!---><img src="http://10.0.0.1/b">--><p>x</p>',
        '<![CDATA[<img src="http://10.0.0.1/">]]><p>x</p>',
        '<?xml-stylesheet href="http://10.0.0.1/s.css"?><p>x</p>',
        '<!DOCTYPE html SYSTEM "http://10.0.0.1/dtd"><p>x</p>',
    ],
)
def test_offline_html_drops_comments_and_other_non_markup(html):
    from citeget.fetch import _offline_html

    out = _offline_html(html)
    assert "10.0.0.1" not in out and "pdfkit-" not in out and "/etc" not in out
    assert "x" in out


def test_pdfkit_reads_no_options_out_of_fetched_html(net, monkeypatch):
    """pdfkit turns <meta name="pdfkit-*"> into wkhtmltopdf flags; none get through.

    Builds the real wkhtmltopdf argv with pdfkit and inspects it; nothing runs.
    """
    import sys

    pdfkit = pytest.importorskip("pdfkit")
    from pdfkit.configuration import Configuration

    seen = {}

    def argv_only(source, output, *, options, configuration):
        kit = pdfkit.PDFKit(source, "string", options=options, configuration=configuration)
        seen["argv"] = " ".join(kit.command())
        return b"%PDF"

    # Any existing file satisfies pdfkit's "is wkhtmltopdf installed" check.
    monkeypatch.setattr(
        pdfkit, "configuration", lambda **k: Configuration(wkhtmltopdf=sys.executable, **k)
    )
    monkeypatch.setattr(pdfkit, "from_string", argv_only)
    from citeget.fetch import html_to_pdf

    hostile = (
        '<meta name="pdfkit-allow" content="/etc">'
        '<!-- <meta name="pdfkit-cookie-jar" content="/tmp/x"> -->'
        '<p title=\'<meta name="pdfkit-header-html" content="file:///etc/hostname">\'>x</p>'
    )
    assert html_to_pdf("http://good.example/", html=hostile) == b"%PDF"
    for flag in ("--allow", "--header-html", "--cookie-jar"):
        assert flag not in seen["argv"]
    assert "--disable-local-file-access" in seen["argv"]


# --- response-size ceiling -----------------------------------------------------


def _capped(n):
    return NetPolicy(max_response_bytes=n)


def test_a_body_over_the_declared_limit_is_refused_before_reading(net):
    net.transport.responses[PUBLIC_IP] = _response(200, b"x" * 2000)
    with pytest.raises(netguard.ResponseTooLargeError, match="2,000 bytes"):
        netguard.get("http://good.example/big", policy=_capped(1000))


def test_a_body_without_a_length_is_cut_off_at_the_limit(net):
    chunked = (
        b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nConnection: close\r\n\r\n"
        + b"".join(b"400\r\n" + b"y" * 1024 + b"\r\n" for _ in range(8))
        + b"0\r\n\r\n"
    )
    net.transport.responses[PUBLIC_IP] = chunked
    with pytest.raises(netguard.ResponseTooLargeError, match="passed"):
        netguard.get("http://good.example/stream", policy=_capped(4096))


def test_a_compressed_bomb_is_measured_decoded(net):
    import gzip

    bomb = gzip.compress(b"\0" * 1_000_000)
    net.transport.responses[PUBLIC_IP] = _response(
        200, bomb, headers=[("Content-Encoding", "gzip")]
    )
    with pytest.raises(netguard.ResponseTooLargeError):
        netguard.get("http://good.example/bomb", policy=_capped(100_000))


def test_a_huge_redirect_body_is_capped_too(net):
    net.transport.responses[PUBLIC_IP] = _response(
        302, b"z" * 5000, headers=[("Location", "/next")]
    )
    with pytest.raises(netguard.ResponseTooLargeError):
        netguard.get("http://good.example/", policy=_capped(1000))


def test_a_body_under_the_limit_reads_normally_streamed_or_not(net):
    net.transport.responses[PUBLIC_IP] = _response(200, b"%PDF-1.4 small")
    assert netguard.get("http://good.example/", policy=_capped(1000)).content == b"%PDF-1.4 small"
    net.transport.responses[PUBLIC_IP] = _response(200, b"%PDF-1.4 small")
    resp = netguard.get("http://good.example/", policy=_capped(1000), stream=True)
    assert b"".join(resp.iter_content(4)) == b"%PDF-1.4 small"


def test_the_limit_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv(netguard.MAX_RESPONSE_BYTES_ENV_VAR, "1234")
    assert netguard.default_policy().max_response_bytes == 1234
    monkeypatch.setenv(netguard.MAX_RESPONSE_BYTES_ENV_VAR, "0")
    assert not netguard.default_policy().max_response_bytes
    monkeypatch.setenv(netguard.MAX_RESPONSE_BYTES_ENV_VAR, "lots")
    with pytest.raises(ValueError, match=netguard.MAX_RESPONSE_BYTES_ENV_VAR):
        netguard.default_policy()


def test_zero_means_no_limit(net):
    net.transport.responses[PUBLIC_IP] = _response(200, b"x" * 5000)
    assert len(netguard.get("http://good.example/", policy=_capped(0)).content) == 5000


def test_fetch_one_reports_an_oversized_page_as_refused(net, tmp_path, monkeypatch):
    from citeget.fetch import fetch_one

    monkeypatch.setenv(netguard.MAX_RESPONSE_BYTES_ENV_VAR, "100")
    net.transport.responses[PUBLIC_IP] = _response(200, b"<p>" + b"a" * 500 + b"</p>")
    result = fetch_one("http://good.example/huge", output_dir=tmp_path)
    assert result.status == "failed" and "limit" in result.error
    assert list(tmp_path.iterdir()) == []


def test_the_browser_route_aborts_an_oversized_response(net, monkeypatch):
    from tests.test_browserguard import FakeRequest, FakeRoute

    monkeypatch.setenv(netguard.MAX_RESPONSE_BYTES_ENV_VAR, "100")
    net.transport.responses[PUBLIC_IP] = _response(200, b"b" * 500)
    route = FakeRoute(FakeRequest("http://good.example/get.php"))
    netguard.browser_route_handler()(route)
    assert route.outcome == ("abort", "blockedbyclient")
