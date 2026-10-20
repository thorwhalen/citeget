"""The browser route handler reuses one guarded session (citeget#23): connections are
shared across a page's requests, cookies carry across a redirect chain and are kept nowhere."""

import http.server
import threading

import pytest

from citeget import netguard

LOCAL = netguard.NetPolicy(allow_private=True)


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"  # keep-alive

    def log_message(self, *a):
        pass

    def do_GET(self):
        server = self.server
        server.seen_cookies.append(self.headers.get("Cookie"))
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/next")
            self.send_header("Set-Cookie", "hop=1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"ok"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.connections = 0
        self.seen_cookies = []

    def get_request(self):
        self.connections += 1
        return super().get_request()


@pytest.fixture
def server():
    srv = _Server()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


class _Req:
    resource_type = "script"
    method = "GET"
    post_data_buffer = None

    def __init__(self, url):
        self.url = url

    def all_headers(self):
        return {"user-agent": "t"}


class _Route:
    def __init__(self, url):
        self.request = _Req(url)
        self.outcome = None

    def abort(self, reason="failed"):
        self.outcome = ("abort", reason)

    def fulfill(self, *, status, headers, body):
        self.outcome = ("fulfill", status, body)


def test_a_pages_requests_share_one_connection(server):
    handler = netguard.browser_route_handler(policy=LOCAL)
    base = f"http://127.0.0.1:{server.server_port}"
    for i in range(6):
        route = _Route(f"{base}/a{i}")
        handler(route)
        assert route.outcome == ("fulfill", 200, b"ok")
    handler.close()
    assert server.connections == 1


def test_a_redirect_chain_carries_its_cookie_but_nothing_is_kept_between_requests(server):
    handler = netguard.browser_route_handler(policy=LOCAL)
    base = f"http://127.0.0.1:{server.server_port}"
    handler(_Route(f"{base}/start"))
    handler(_Route(f"{base}/later"))
    handler.close()
    # /start (none), /next (hop=1 carried across the chain), /later (nothing stored)
    assert server.seen_cookies == [None, "hop=1", None]


def test_closing_the_context_closes_the_session(server):
    class Context:
        def route(self, pattern, handler):
            self.handler = handler

        def on(self, event, callback):
            self.on_close = callback

    context = netguard.guard_browser_context(Context(), policy=LOCAL)
    context.handler(_Route(f"http://127.0.0.1:{server.server_port}/x"))
    context.on_close()
    assert server.connections == 1
