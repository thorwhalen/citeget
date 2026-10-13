"""The browser guard: Chromium gets no network of its own; netguard fetches for it.

Most tests drive :func:`citeget.netguard.browser_route_handler` with fake
Playwright route objects over the fake network of ``conftest.py``. One test
launches a real Chromium if one is installed, but every request it makes is
answered from that same fake network, and the browser's own traffic goes to a
dead loopback proxy: nothing leaves the machine and nothing reaches a private
address.
"""

import pytest

from citeget import core, netguard

from tests.conftest import OTHER_PUBLIC_IP, PUBLIC_IP, _response


class FakeRequest:
    def __init__(self, url, *, method="GET", resource_type="document", headers=None, body=None):
        self.url = url
        self.method = method
        self.resource_type = resource_type
        self._headers = headers or {"user-agent": "test", "accept-encoding": "gzip"}
        self.post_data_buffer = body

    def all_headers(self):
        return dict(self._headers)


class FakeRoute:
    def __init__(self, request):
        self.request = request
        self.outcome = None

    def abort(self, reason="failed"):
        self.outcome = ("abort", reason)

    def fulfill(self, *, status, headers, body):
        self.outcome = ("fulfill", status, headers, body)


def _route(url, **kw):
    route = FakeRoute(FakeRequest(url, **kw))
    netguard.browser_route_handler()(route)
    return route


# --- the route handler ------------------------------------------------------


def test_a_public_document_is_fetched_by_the_guard_and_fulfilled(net):
    net.transport.responses[PUBLIC_IP] = _response(
        200, b"<p>page</p>", headers=[("Content-Type", "text/html")]
    )
    route = _route("http://good.example/index.php")
    kind, status, headers, body = route.outcome
    assert (kind, status, body) == ("fulfill", 200, b"<p>page</p>")
    assert headers["Content-Type"] == "text/html"
    assert net.transport.connected == [PUBLIC_IP]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:2019/config/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:127.0.0.1]/",
        "http://2130706433/",
    ],
)
def test_internal_requests_are_aborted_unfetched(net, url):
    for resource_type in ("document", "sub_frame", "script", "xhr", "fetch"):
        assert _route(url, resource_type=resource_type).outcome == ("abort", "blockedbyclient")
    assert net.transport.connected == []


def test_a_redirect_to_an_internal_address_is_aborted_not_handed_to_the_browser(net):
    """Playwright routes see only the first URL of a redirect chain, so the
    guard follows redirects itself and never fulfills a 3xx."""
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://127.0.0.1:2019/config/")]
    )
    assert _route("http://good.example/get.php").outcome == ("abort", "blockedbyclient")
    assert net.transport.connected == [PUBLIC_IP]


def test_a_public_redirect_is_followed_and_only_the_final_response_fulfilled(net):
    net.dns.table["cdn.example"] = [OTHER_PUBLIC_IP]
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://cdn.example/book.pdf")]
    )
    net.transport.responses[OTHER_PUBLIC_IP] = _response(
        200,
        b"%PDF-1.4",
        headers=[("Content-Disposition", 'attachment; filename="b.pdf"')],
    )
    handler = netguard.browser_route_handler()
    route = FakeRoute(FakeRequest("http://good.example/get.php"))
    handler(route)
    kind, status, headers, body = route.outcome
    # A download is streamed to disk by the guard; Chromium gets an empty
    # attachment (fulfilling a whole book through Playwright is what timed out).
    assert (kind, status, body) == ("fulfill", 200, b"")
    assert "attachment" in headers["Content-Disposition"]
    path = handler.downloads.take("http://good.example/get.php")
    with open(path, "rb") as f:
        assert f.read() == b"%PDF-1.4"
    import os

    os.unlink(path)


def test_images_media_and_fonts_are_not_fetched(net):
    for resource_type in netguard.BLOCKED_RESOURCE_TYPES:
        assert _route("http://good.example/x", resource_type=resource_type).outcome == (
            "abort",
            "blockedbyclient",
        )
    assert net.transport.connected == []


def test_a_non_html_navigation_is_a_download_even_without_a_disposition(net):
    net.transport.responses[PUBLIC_IP] = _response(
        200, b"%PDF-1.4 x", headers=[("Content-Type", "application/pdf")]
    )
    handler = netguard.browser_route_handler()
    route = FakeRoute(FakeRequest("http://good.example/b.pdf"))
    handler(route)
    assert route.outcome[3] == b"" and route.outcome[2]["Content-Disposition"] == "attachment"
    assert handler.downloads.take("http://good.example/b.pdf") is not None


def test_a_subresource_is_never_spooled_as_a_download(net):
    net.transport.responses[PUBLIC_IP] = _response(
        200, b"var x;", headers=[("Content-Type", "application/javascript")]
    )
    handler = netguard.browser_route_handler()
    route = FakeRoute(FakeRequest("http://good.example/a.js", resource_type="script"))
    handler(route)
    assert route.outcome[3] == b"var x;" and not handler.downloads._paths


def test_folded_header_values_are_dropped_not_passed_to_chromium(net):
    raw = (
        b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nX-B: v\r\n X-Injected: 1\r\n"
        b"Content-Length: 2\r\nConnection: close\r\n\r\nok"
    )
    net.transport.responses[PUBLIC_IP] = raw
    _, status, headers, body = _route("http://good.example/").outcome
    assert status == 200 and body == b"ok"
    assert all("\n" not in v and "\r" not in v for v in headers.values())


def test_set_cookies_from_same_host_redirect_hops_are_kept(net):
    net.transport.responses[PUBLIC_IP] = [
        _response(302, headers=[("Location", "/final"), ("Set-Cookie", "hop=1; Path=/")]),
        _response(200, b"ok", headers=[("Set-Cookie", "end=2; Path=/")]),
    ]
    _, _, headers, _ = _route("http://good.example/start").outcome
    assert headers["set-cookie"].split("\n") == ["hop=1; Path=/", "end=2; Path=/"]


def test_cookies_and_body_are_forwarded_and_multiple_set_cookies_survive(net):
    seen = {}

    def fetch(method, url, **kw):
        seen.update(method=method, url=url, **kw)
        return netguard.request(method, url, **kw)

    net.transport.responses[PUBLIC_IP] = _response(
        200,
        b"ok",
        headers=[("Set-Cookie", "a=1; Path=/"), ("Set-Cookie", "b=2; Path=/"),
                 ("Content-Encoding", "identity")],
    )
    route = FakeRoute(
        FakeRequest(
            "http://good.example/form",
            method="POST",
            headers={"cookie": "s=1", "host": "good.example", ":authority": "x"},
            body=b"q=1",
        )
    )
    netguard.browser_route_handler(fetch=fetch)(route)
    assert seen["method"] == "POST" and seen["data"] == b"q=1"
    assert seen["headers"] == {"cookie": "s=1"}
    _, _, headers, _ = route.outcome
    assert headers["set-cookie"].split("\n") == ["a=1; Path=/", "b=2; Path=/"]
    assert "Content-Encoding" not in headers


def test_a_transport_failure_aborts_rather_than_raising(net):
    def broken(*a, **k):
        raise ConnectionError("down")

    route = FakeRoute(FakeRequest("http://good.example/"))
    netguard.browser_route_handler(fetch=broken)(route)
    assert route.outcome == ("abort", "failed")


# --- the browser and the navigations ---------------------------------------


class _FakeContext:
    def __init__(self):
        self.routes, self.ws_routes, self.init_scripts = [], [], []

    def add_init_script(self, script):
        self.init_scripts.append(script)

    def on(self, event, handler):
        pass

    def route(self, pattern, handler):
        self.routes.append(pattern)

    def route_web_socket(self, pattern, handler):
        self.ws_routes.append(pattern)


class _FakeBrowser:
    def __init__(self):
        self.context_kwargs = None

    def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return _FakeContext()


class _FakeChromium:
    def __init__(self):
        self.launch_kwargs = None
        self.browser = _FakeBrowser()

    def launch(self, **kwargs):
        self.launch_kwargs = kwargs
        return self.browser


def test_the_browser_is_launched_with_no_network_of_its_own():
    class P:
        chromium = _FakeChromium()

    browser, context = core._create_browser_context(P)
    args = P.chromium.launch_kwargs["args"]
    assert f"--proxy-server={netguard.DEAD_PROXY}" in args
    assert "--proxy-bypass-list=<-loopback>" in args
    assert browser.context_kwargs["service_workers"] == "block"
    assert "**/*" in context.routes and context.ws_routes == ["**/*"]
    assert "SharedWorker" in context.init_scripts[0]
    assert "RTCPeerConnection" in context.init_scripts[0]


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "data:text/html,<iframe src=x>", "javascript:alert(1)",
     "http://127.0.0.1/", "http://[::1]/"],
)
def test_navigations_to_local_or_internal_urls_are_refused(url):
    class Page:
        def goto(self, *a, **k):
            pytest.fail("navigated")

    with pytest.raises(netguard.UnsafeURLError):
        core._goto(Page(), url)


def test_the_http_download_fallback_is_guarded(net, tmp_path):
    class Ctx:
        def cookies(self, urls):
            return [{"name": "k", "value": "v"}]

    class Page:
        context = Ctx()

    assert not core._fetch_via_page_request(
        Page(), "http://127.0.0.1/get.php?key=1", tmp_path / "x", timeout=1000
    )
    assert net.transport.connected == []
    net.transport.responses[PUBLIC_IP] = _response(200, b"%PDF-1.4 book")
    assert core._fetch_via_page_request(
        Page(), "http://good.example/get.php?key=1", tmp_path / "x", timeout=1000
    )
    assert (tmp_path / "x").read_bytes() == b"%PDF-1.4 book"


# --- a real Chromium, on the fake network ------------------------------------


@pytest.fixture
def chromium():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        manager = sync_api.sync_playwright().start()
    except Exception as e:  # pragma: no cover - environment dependent
        pytest.skip(f"playwright unavailable: {e}")
    try:
        browser, context = netguard.launch_guarded_chromium(manager)
    except Exception as e:  # no browser installed (CI); never downloaded here
        manager.stop()
        pytest.skip(f"no chromium: {str(e).splitlines()[0]}")
    yield browser, context
    browser.close()
    manager.stop()


def test_a_real_page_cannot_reach_internal_addresses(net, chromium):
    _, context = chromium
    net.transport.responses[PUBLIC_IP] = _response(
        200,
        b"<html><body><p id=ok>mirror</p>"
        b'<iframe src="http://127.0.0.1:2019/config/"></iframe>'
        b'<script src="http://169.254.169.254/latest/user-data"></script>'
        b"<script>fetch('http://10.0.0.5/').catch(()=>{});"
        b"new WebSocket('ws://127.0.0.1:8000/');</script>"
        b"</body></html>",
        headers=[("Content-Type", "text/html")],
    )
    page = context.new_page()
    page.goto("http://good.example/", wait_until="load", timeout=15000)
    assert page.query_selector("#ok") is not None
    page.wait_for_timeout(500)
    assert net.transport.connected == [PUBLIC_IP]


def test_a_real_browser_has_no_route_around_the_guard(chromium):
    """With the routes removed, Chromium's own traffic dead-ends at the proxy."""
    _, context = chromium
    context.unroute_all()
    page = context.new_page()
    with pytest.raises(Exception, match="ERR_PROXY_CONNECTION_FAILED|ERR_TUNNEL"):
        page.goto("http://203.0.113.10/", timeout=10000)  # TEST-NET-3, never routed


def test_a_real_libgen_style_download_is_streamed_and_adopted(net, chromium, tmp_path):
    """ads.php -> get.php -> 302 -> attachment, end to end through a real Chromium."""
    _, context = chromium
    net.dns.table["cdn.example"] = [OTHER_PUBLIC_IP]
    book = b"%PDF-1.4 " + b"b" * 50_000
    net.transport.responses[PUBLIC_IP] = _response(
        200,
        b'<html><body><a href="get.php?md5=x&key=k">GET</a></body></html>',
        headers=[("Content-Type", "text/html")],
    )
    page = context.new_page()
    get_url = core._get_download_url(
        page, "/ads.php?md5=x", base_url="http://good.example", timeout=15000
    )
    assert get_url == "http://good.example/get.php?md5=x&key=k"
    net.transport.responses[PUBLIC_IP] = _response(
        302, headers=[("Location", "http://cdn.example/b.pdf")]
    )
    net.transport.responses[OTHER_PUBLIC_IP] = _response(
        200, book, headers=[("Content-Type", "application/pdf"),
                            ("Content-Disposition", 'attachment; filename="b.pdf"')]
    )
    monkey_target = tmp_path / "book.pdf"
    original = core._get_download_url
    try:
        core._get_download_url = lambda *a, **k: get_url
        saved = core._try_libgen_download(
            page, "/ads.php?md5=x", monkey_target, base_url="http://good.example",
            timeout=15000, delay=0, extension="pdf", validate=False,
        )
    finally:
        core._get_download_url = original
    assert monkey_target.read_bytes() == book and saved == str(monkey_target)
    assert net.transport.connected.count(OTHER_PUBLIC_IP) == 1  # the key is used once


def test_adoption_is_by_url_never_the_latest_download(net, tmp_path):
    """A page that navigated to a tracking pixel must not have it adopted as the book."""
    net.transport.responses[PUBLIC_IP] = _response(
        200, b"GIF89a pixel", headers=[("Content-Type", "image/gif")]
    )

    class Ctx:
        pass

    ctx = Ctx()
    handler = netguard.browser_route_handler()
    netguard._CONTEXT_DOWNLOADS[id(ctx)] = handler.downloads
    try:
        handler(FakeRoute(FakeRequest("http://good.example/junk.bin")))
        assert not netguard.adopt_browser_download(
            ctx, "http://good.example/get.php?key=1", tmp_path / "book.pdf"
        )
        assert not (tmp_path / "book.pdf").exists()
        assert netguard.adopt_browser_download(
            ctx, "http://good.example/junk.bin", tmp_path / "pixel"
        )
        assert (tmp_path / "pixel").read_bytes() == b"GIF89a pixel"
    finally:
        netguard._CONTEXT_DOWNLOADS.pop(id(ctx), None)


def test_stale_spools_are_removed_at_launch(tmp_path, monkeypatch):
    import os
    import tempfile
    import time

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    old = os.path.join(netguard.spool_dir(), "dl-old.download")
    new = os.path.join(netguard.spool_dir(), "dl-new.download")
    for path in (old, new):
        open(path, "wb").close()
    os.utime(old, (time.time() - 2 * netguard.STALE_SPOOL_SECONDS,) * 2)
    netguard.remove_stale_spools()
    assert not os.path.exists(old) and os.path.exists(new)
