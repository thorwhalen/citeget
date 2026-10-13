"""Outbound-HTTP guard: refuse to fetch anything that is not on the public internet.

citeget fetches URLs that come from its users: the ``url`` of a reference, a
page to save as Markdown, a link found inside a fetched page. When citeget runs
as a hosted web app, that is a server-side request forgery (SSRF) surface: a
user could ask the server to fetch ``http://127.0.0.1:<admin port>/`` or the
cloud metadata service and then download the response as a job result.

Every HTTP request citeget makes goes through :func:`get` (or a
:func:`guarded_session`), which enforces a :class:`NetPolicy`:

- only ``http`` and ``https`` URLs, on the first request and on every redirect;
- the host is resolved **inside the connection step**, every resolved address
  must be a public one, and the socket is opened to that vetted address. There
  is no second DNS lookup, so a rebinding DNS server cannot swap the address
  between the check and the connect, and every redirect hop that opens a
  connection is vetted the same way;
- loopback, private (RFC 1918, ``fc00::/7``), link-local (``169.254.0.0/16``,
  ``fe80::/10``, which covers the usual metadata address), shared/CGNAT,
  unspecified, reserved and multicast addresses are refused, including when
  they are wrapped in IPv6 (``::ffff:127.0.0.1``, 6to4, NAT64, Teredo);
- proxies and ``.netrc`` from the environment are ignored (``trust_env=False``)
  and explicit proxies are refused, so ``HTTP_PROXY`` cannot route a request
  around the check.

Because the check is made on the address the socket actually connects to,
alternative spellings of a host (``2130706433``, ``0x7f.1``, ``017700000001``,
a DNS name that resolves to ``10.0.0.5``) are all caught: they resolve to the
same refused address.

The guard is on by default. A desktop user who wants citeget to fetch from
their own LAN or ``localhost`` can opt out with the environment variable
``CITEGET_ALLOW_PRIVATE_NETWORK=1`` or by passing
``policy=NetPolicy(allow_private=True)``.

>>> is_public_address("8.8.8.8")
True
>>> [is_public_address(a) for a in ("127.0.0.1", "169.254.169.254", "10.1.2.3")]
[False, False, False]
>>> [is_public_address(a) for a in ("::1", "::ffff:127.0.0.1", "fd00:ec2::254")]
[False, False, False]
>>> check_url("file:///etc/passwd")
Traceback (most recent call last):
  ...
citeget.netguard.UnsafeURLError: Refused file:///etc/passwd: scheme 'file' is not allowed (allowed: http, https)
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional
from urllib.parse import urljoin, urlsplit

#: Environment variable that switches the guard off (``1``/``true``/``yes``).
ALLOW_PRIVATE_ENV_VAR = "CITEGET_ALLOW_PRIVATE_NETWORK"

#: Environment variables for the response ceilings (``0``: no ceiling).
MAX_RESPONSE_BYTES_ENV_VAR = "CITEGET_MAX_RESPONSE_BYTES"
MAX_TEXT_BYTES_ENV_VAR = "CITEGET_MAX_TEXT_BYTES"
MAX_RESPONSE_SECONDS_ENV_VAR = "CITEGET_MAX_RESPONSE_SECONDS"
#: Largest response body read: room for most books, small enough that a few at
#: once fit in a small server's RAM (the browser path holds a body ~5x over).
DEFAULT_MAX_RESPONSE_BYTES = 100 * 1024 * 1024
#: Largest body decoded as text (``.text`` / ``.json()``): parsing HTML or XML
#: costs tens of times its size in memory, so text gets a far smaller ceiling.
DEFAULT_MAX_TEXT_BYTES = 10 * 1024 * 1024
#: Longest a body may take to arrive. Socket timeouts are per read, so without
#: this a server could trickle a body for hours and hold a job slot throughout.
DEFAULT_MAX_RESPONSE_SECONDS = 600
_READ_CHUNK_BYTES = 64 * 1024

_TRUTHY = frozenset({"1", "true", "yes", "on"})

#: NAT64 well-known prefix (RFC 6052): the last 32 bits are an IPv4 address.
_NAT64_PREFIX = ipaddress.IPv6Network("64:ff9b::/96")
#: Local-use NAT64 prefix (RFC 8215).
_NAT64_LOCAL_PREFIX = ipaddress.IPv6Network("64:ff9b:1::/48")
#: IPv4-translated addresses (SIIT, RFC 2765): ``::ffff:0:a.b.c.d``.
_SIIT_PREFIX = ipaddress.IPv6Network("::ffff:0:0:0/96")


class UnsafeURLError(ValueError):
    """A URL, or an address it resolved to, is outside what the policy allows.

    A ``ValueError`` rather than a ``requests`` exception on purpose: urllib3
    retries and re-wraps ``OSError`` subclasses, which would bury the reason.
    """


class ResponseTooLargeError(UnsafeURLError):
    """A response body is larger than the policy's ``max_response_bytes``.

    A refusal like any other: callers that report refusals report this too,
    and nobody retries it.
    """


@dataclass(frozen=True)
class NetPolicy:
    """What outbound requests are allowed to reach.

    Args:
        allow_private: Allow loopback / private / link-local destinations.
            Off by default; this is what a hosted deployment relies on.
        allowed_schemes: URL schemes allowed on the first request and on every
            redirect hop.
        max_redirects: Redirect hops followed before giving up.
        max_response_bytes: Largest (decoded) response body read; a larger one
            raises :class:`ResponseTooLargeError`. ``None`` or ``0``: no ceiling.
        max_text_bytes: Largest body that ``.text`` / ``.json()`` will decode.
        max_response_seconds: Longest a body may take to arrive, in total.
    """

    allow_private: bool = False
    allowed_schemes: tuple = ("http", "https")
    max_redirects: int = 10
    max_response_bytes: Optional[int] = DEFAULT_MAX_RESPONSE_BYTES
    max_text_bytes: Optional[int] = DEFAULT_MAX_TEXT_BYTES
    max_response_seconds: Optional[float] = DEFAULT_MAX_RESPONSE_SECONDS


def default_policy() -> NetPolicy:
    """The policy in force when none is passed, read from the environment now.

    >>> default_policy().allow_private in (True, False)
    True
    """
    flag = os.environ.get(ALLOW_PRIVATE_ENV_VAR, "").strip().lower()
    return NetPolicy(
        allow_private=flag in _TRUTHY,
        max_response_bytes=_env_limit(MAX_RESPONSE_BYTES_ENV_VAR, DEFAULT_MAX_RESPONSE_BYTES),
        max_text_bytes=_env_limit(MAX_TEXT_BYTES_ENV_VAR, DEFAULT_MAX_TEXT_BYTES),
        max_response_seconds=_env_limit(
            MAX_RESPONSE_SECONDS_ENV_VAR, DEFAULT_MAX_RESPONSE_SECONDS
        ),
    )


def _env_limit(var: str, default: int) -> int:
    """A non-negative integer from environment variable *var*, else *default*."""
    raw = os.environ.get(var, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        raise ValueError(f"{var}={raw!r} must be a non-negative integer (0 for none)")
    return value


def _embedded_ipv4s(ip: ipaddress.IPv6Address) -> list:
    """The IPv4 addresses an IPv6 address carries, if it is a transition form."""
    if ip.ipv4_mapped is not None:
        return [ip.ipv4_mapped]
    if ip.sixtofour is not None:
        return [ip.sixtofour]
    if ip.teredo is not None:
        return list(ip.teredo)  # (server, client): both must be public
    if ip in _NAT64_PREFIX or ip in _NAT64_LOCAL_PREFIX or ip in _SIIT_PREFIX:
        return [ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)]
    # IPv4-compatible (deprecated, ::a.b.c.d); ``::`` and ``::1`` stay IPv6.
    if int(ip) >> 32 == 0 and int(ip) > 1:
        return [ipaddress.IPv4Address(int(ip))]
    return []


def _is_public(ip) -> bool:
    if ip.is_multicast:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        embedded = _embedded_ipv4s(ip)
        if embedded:
            # A transition form is exactly as public as what it carries.
            return all(_is_public(inner) for inner in embedded)
        if ip.is_site_local or ip.is_reserved:
            return False
    return ip.is_global


def is_public_address(address: str) -> bool:
    """True if *address* (an IP literal, possibly with a ``%zone``) is public.

    >>> is_public_address("fe80::1%eth0")
    False
    >>> is_public_address("2002:7f00:1::")  # 6to4 wrapping 127.0.0.1
    False
    >>> is_public_address("64:ff9b::a9fe:a9fe")  # NAT64 wrapping 169.254.169.254
    False
    >>> is_public_address("::ffff:0:7f00:1")  # SIIT wrapping 127.0.0.1
    False
    >>> is_public_address("fec0::1")  # deprecated site-local
    False
    """
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    return _is_public(ip)


def _refuse(url_or_host, reason: str) -> UnsafeURLError:
    return UnsafeURLError(f"Refused {url_or_host}: {reason}")


def check_url(url: str, *, policy: Optional[NetPolicy] = None) -> str:
    """Check the parts of *url* that can be judged without DNS; return it.

    The scheme must be allowed and there must be a host. A host written as an
    IP literal is judged here too. Hostnames are judged when the connection is
    made (see :func:`resolve_public`), since that is the only check a DNS
    rebind cannot race.

    >>> check_url("https://example.org/paper.pdf")
    'https://example.org/paper.pdf'
    >>> check_url("http://[::1]:8080/")
    Traceback (most recent call last):
      ...
    citeget.netguard.UnsafeURLError: Refused http://[::1]:8080/: ::1 is not a public address
    """
    policy = policy or default_policy()
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError as e:
        raise _refuse(url, f"unparseable URL ({e})") from e
    scheme = (parts.scheme or "").lower()
    if scheme not in policy.allowed_schemes:
        allowed = ", ".join(policy.allowed_schemes)
        raise _refuse(url, f"scheme {scheme!r} is not allowed (allowed: {allowed})")
    if not host:
        raise _refuse(url, "no host")
    if not policy.allow_private:
        try:
            ipaddress.ip_address(host.split("%", 1)[0])
        except ValueError:
            pass  # a name, or a non-canonical IPv4 spelling: judged at connect
        else:
            if not is_public_address(host):
                raise _refuse(url, f"{host} is not a public address")
    return url


def resolve_public(host: str, port: int, *, policy: Optional[NetPolicy] = None) -> list:
    """Resolve *host* and return its addresses, refusing if any is not public.

    Every address must pass: a name with one public and one private record is
    refused outright rather than connected to "the good one".

    Returns ``getaddrinfo`` tuples ``(family, type, proto, canonname, sockaddr)``.
    """
    policy = policy or default_policy()
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    if policy.allow_private:
        return infos
    if not infos:
        raise _refuse(host, "resolved to no address")
    for *_, sockaddr in infos:
        if not is_public_address(sockaddr[0]):
            raise _refuse(host, f"resolves to {sockaddr[0]}, not a public address")
    return infos


# ---------------------------------------------------------------------------
# requests / urllib3 integration
# ---------------------------------------------------------------------------


def _connect_vetted(conn, policy: NetPolicy):
    """Open a socket for urllib3 connection *conn*, to a vetted address only.

    Mirrors ``urllib3.connection.HTTPConnection._new_conn``, with the DNS step
    replaced by :func:`resolve_public` and the connect made to the resulting IP.
    """
    from urllib3.exceptions import ConnectTimeoutError, NewConnectionError
    from urllib3.util import connection

    try:
        infos = resolve_public(conn._dns_host, conn.port, policy=policy)
    except socket.gaierror as e:
        raise NewConnectionError(conn, f"Failed to resolve {conn.host}: {e}") from e
    last_error: Optional[OSError] = None
    for family, _type, _proto, _canon, sockaddr in infos:
        try:
            return connection.create_connection(
                (sockaddr[0], conn.port),
                conn.timeout,
                source_address=conn.source_address,
                socket_options=conn.socket_options,
            )
        except socket.timeout as e:
            raise ConnectTimeoutError(
                conn,
                f"Connection to {conn.host} timed out. (connect timeout={conn.timeout})",
            ) from e
        except OSError as e:
            last_error = e
    raise NewConnectionError(
        conn, f"Failed to establish a new connection: {last_error}"
    ) from last_error


@lru_cache(maxsize=None)
def _pool_classes(policy: NetPolicy) -> dict:
    """urllib3 pool classes whose connections connect only to vetted addresses."""
    from urllib3.connection import HTTPConnection, HTTPSConnection
    from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

    class GuardedHTTPConnection(HTTPConnection):
        def _new_conn(self):
            return _connect_vetted(self, policy)

    class GuardedHTTPSConnection(HTTPSConnection):
        def _new_conn(self):
            return _connect_vetted(self, policy)

    class GuardedHTTPConnectionPool(HTTPConnectionPool):
        ConnectionCls = GuardedHTTPConnection

    class GuardedHTTPSConnectionPool(HTTPSConnectionPool):
        ConnectionCls = GuardedHTTPSConnection

    return {"http": GuardedHTTPConnectionPool, "https": GuardedHTTPSConnectionPool}


def guarded_session(*, policy: Optional[NetPolicy] = None):
    """A ``requests.Session`` that enforces *policy* on every connection and hop.

    Use it as a context manager, like ``requests.Session``. With
    ``policy.allow_private`` it still restricts schemes, but connects wherever
    DNS points and honours environment proxies like plain ``requests``.
    """
    import requests
    from requests.adapters import HTTPAdapter

    policy = policy or default_policy()

    class _GuardedAdapter(HTTPAdapter):
        def init_poolmanager(self, *args, **kwargs):
            super().init_poolmanager(*args, **kwargs)
            if not policy.allow_private:
                self.poolmanager.pool_classes_by_scheme = _pool_classes(policy)

        def proxy_manager_for(self, proxy, **proxy_kwargs):
            if not policy.allow_private:
                raise _refuse(proxy, "requests through a proxy are not allowed")
            return super().proxy_manager_for(proxy, **proxy_kwargs)

    class _GuardedSession(requests.Session):
        def get_redirect_target(self, resp):
            target = super().get_redirect_target(resp)
            if target:
                check_url(urljoin(resp.url, target), policy=policy)
                # requests reads a redirect's body in full before following it;
                # read it here instead, under the same ceiling.
                _read_capped(resp, policy)
            return target

    session = _GuardedSession()
    # Environment proxies would route around the address check. When the
    # guard is off (a desktop opt-out), keep requests' usual proxy support.
    session.trust_env = policy.allow_private
    session.max_redirects = policy.max_redirects
    adapter = _GuardedAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _too_large(url, detail: str) -> ResponseTooLargeError:
    return ResponseTooLargeError(f"Refused {url}: {detail}")


def _guarded_response_class():
    """A ``requests.Response`` whose ``.text`` / ``.json()`` honour a text ceiling."""
    import requests

    class GuardedResponse(requests.Response):
        _max_text_bytes: Optional[int] = None

        def _check_text_size(self):
            limit = self._max_text_bytes
            if limit and len(self.content) > limit:
                raise _too_large(
                    self.url,
                    f"{len(self.content):,} bytes is over the {limit:,}-byte limit "
                    f"for text ({MAX_TEXT_BYTES_ENV_VAR})",
                )

        @property
        def text(self):
            self._check_text_size()
            return super().text

        def json(self, **kwargs):
            self._check_text_size()
            return super().json(**kwargs)

    return GuardedResponse


_GuardedResponse = None


def _read_capped(resp, policy: NetPolicy):
    """Read *resp*'s body into memory under *policy*'s size and time ceilings.

    The body is stored where ``requests`` keeps a read body, so ``.content``,
    ``.text`` and ``iter_content()`` all work afterwards, ``stream=True`` or not.
    Decoded bytes are counted, so a small compressed bomb is caught too, and
    stacked encodings (``gzip, gzip``) are refused outright.
    """
    import io
    import time

    global _GuardedResponse
    limit, deadline_s = policy.max_response_bytes, policy.max_response_seconds
    if "," in resp.headers.get("Content-Encoding", ""):
        resp.close()
        raise _too_large(resp.url, "stacked content encodings are not accepted")
    if limit:
        declared = resp.headers.get("Content-Length", "")
        if declared.isdigit() and int(declared) > limit:
            resp.close()
            raise _too_large(
                resp.url,
                f"response is {int(declared):,} bytes, over the {limit:,}-byte "
                f"limit ({MAX_RESPONSE_BYTES_ENV_VAR})",
            )
    deadline = time.monotonic() + deadline_s if deadline_s else None
    buf, total = io.BytesIO(), 0
    for chunk in resp.iter_content(_READ_CHUNK_BYTES):
        total += len(chunk)
        if limit and total > limit:
            resp.close()
            raise _too_large(
                resp.url,
                f"response passed the {limit:,}-byte limit ({MAX_RESPONSE_BYTES_ENV_VAR})",
            )
        if deadline is not None and time.monotonic() > deadline:
            resp.close()
            raise _too_large(
                resp.url,
                f"response took over {deadline_s:g}s to arrive "
                f"({MAX_RESPONSE_SECONDS_ENV_VAR})",
            )
        buf.write(chunk)
    resp._content = buf.getvalue()
    resp._content_consumed = True
    if _GuardedResponse is None:
        _GuardedResponse = _guarded_response_class()
    resp.__class__ = _GuardedResponse
    resp._max_text_bytes = policy.max_text_bytes
    return resp


def request(method: str, url: str, *, policy: Optional[NetPolicy] = None, **kwargs):
    """``requests.request`` with the destination guard. Same arguments and return.

    The body is read before returning, up to ``policy.max_response_bytes``.

    Raises :class:`UnsafeURLError` if the URL, a redirect target, or an address
    a host resolves to is refused, or ``proxies=`` is given;
    :class:`ResponseTooLargeError` (a subclass) if the body is over the size or
    time ceiling, or if ``.text`` / ``.json()`` is asked of a body over the text
    ceiling.
    """
    policy = policy or default_policy()
    if kwargs.get("proxies") and not policy.allow_private:
        raise _refuse(url, "requests through a proxy are not allowed")
    check_url(url, policy=policy)
    kwargs["stream"] = True  # read here, under the size ceiling
    with guarded_session(policy=policy) as session:
        resp = session.request(method, url, **kwargs)
        return _read_capped(resp, policy)


def get(url: str, *, policy: Optional[NetPolicy] = None, **kwargs):
    """``requests.get`` with the destination guard (see :func:`request`)."""
    return request("GET", url, policy=policy, **kwargs)


# ---------------------------------------------------------------------------
# Playwright / Chromium integration
# ---------------------------------------------------------------------------
#
# A route handler that only vets and then calls ``route.continue_()`` is not a
# guard: Playwright calls the handler for the first URL of a redirect chain
# only, and Chromium follows the rest (and does its own DNS, so it can be
# rebound). So the browser is given no network of its own at all:
#
# - every request it makes is answered by :func:`browser_route_handler`, which
#   fetches it through :func:`request` (connect-time vetting, every redirect
#   followed and vetted here, never handed back to the browser) and fulfills
#   the final response;
# - Chromium itself is pointed at a proxy that is not there, with the implicit
#   loopback bypass removed, so anything that escapes interception (a
#   preconnect, a redirect, a request type routes do not see) goes nowhere;
# - service workers, which bypass routes, are blocked; WebSockets are routed and
#   never connected; WebRTC is kept off non-proxied UDP.

#: Where Chromium's own traffic is sent: a port nothing listens on.
DEAD_PROXY = "http://127.0.0.1:9"

#: Chromium flags that leave the browser no network path of its own.
CHROMIUM_GUARD_ARGS = (
    f"--proxy-server={DEAD_PROXY}",
    "--proxy-bypass-list=<-loopback>",  # also proxy loopback (bypassed by default)
    "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
    "--dns-prefetch-disable",
)

#: Resource types refused outright: nothing citeget reads needs them, and every
#: request the route serves holds up the page (the handler runs on Playwright's
#: one thread), so ad frames, long polls and beacons are not worth a fetch.
BLOCKED_RESOURCE_TYPES = frozenset(
    {
        "image",
        "media",
        "font",
        "sub_frame",
        "ping",
        "eventsource",
        "csp_report",
        "manifest",
        "texttrack",
        "other",
    }
)

#: Timeouts (connect, read), in seconds, for a page itself and for what it loads.
DOCUMENT_TIMEOUT = (10, 60)
SUBRESOURCE_TIMEOUT = (5, 10)

#: Content types a navigation renders; any other navigation is a download.
_RENDERED_TYPES = frozenset(
    {
        "text/html",
        "application/xhtml+xml",
        "text/plain",
        "text/xml",
        "application/xml",
        "",
    }
)

#: Removed from every page before its scripts run: a SharedWorker's requests and
#: WebRTC's TURN-over-TCP do not pass through routes (the dead proxy stops them,
#: but it should not be the only wall).
_PAGE_INIT_SCRIPT = """
for (const name of ["SharedWorker", "RTCPeerConnection", "webkitRTCPeerConnection",
                    "RTCDataChannel", "RTCSessionDescription", "RTCIceCandidate"]) {
  try { delete window[name]; } catch (e) {}
}
"""

#: Request headers not forwarded from the browser (requests sets its own).
_HOP_BY_HOP_REQUEST_HEADERS = frozenset(
    {
        "host",
        "content-length",
        "connection",
        "keep-alive",
        "proxy-connection",
        "transfer-encoding",
        "upgrade",
        "te",
        "accept-encoding",
    }
)
#: Response headers dropped before fulfilling: the body is already decoded and
#: re-framed, so these would describe bytes the browser never gets.
_DROPPED_RESPONSE_HEADERS = frozenset(
    {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "set-cookie",
    }
)


def _safe_header_value(value: str) -> bool:
    # A value with CR/LF (obs-fold from the origin) makes Chromium drop the
    # fulfilled response silently, stalling the navigation until it times out.
    return "\r" not in value and "\n" not in value


def _fulfill_headers(resp, *, request_url: str) -> dict:
    """The headers to fulfill *resp* with: re-framing headers dropped, every
    ``Set-Cookie`` kept (also from redirect hops on the request's own host)."""
    headers = {
        k: v
        for k, v in resp.headers.items()
        if k.lower() not in _DROPPED_RESPONSE_HEADERS and _safe_header_value(v)
    }
    host = urlsplit(request_url).hostname
    hops = [h for h in getattr(resp, "history", []) if urlsplit(h.url).hostname == host]
    cookies = []
    for r in [*hops, resp]:
        raw = getattr(r.raw, "headers", None)
        if hasattr(raw, "getlist"):
            cookies += [c for c in raw.getlist("Set-Cookie") if _safe_header_value(c)]
    if cookies:
        headers["set-cookie"] = "\n".join(cookies)  # Playwright's multi-value form
    return headers


def _is_download(resp) -> bool:
    disposition = resp.headers.get("Content-Disposition", "").lower()
    content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return "attachment" in disposition or content_type not in _RENDERED_TYPES


#: Spooled browser downloads older than this are removed at the next launch:
#: what a killed job left behind.
STALE_SPOOL_SECONDS = 6 * 3600


def spool_dir() -> str:
    """The directory browser downloads are spooled to (per uid, created 0700)."""
    import tempfile

    uid = os.getuid() if hasattr(os, "getuid") else "user"
    path = os.path.join(tempfile.gettempdir(), f"citeget-browser-spool-{uid}")
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def remove_stale_spools(*, max_age: float = STALE_SPOOL_SECONDS) -> None:
    """Delete spooled downloads older than *max_age* seconds."""
    import time

    cutoff = time.time() - max_age
    with os.scandir(spool_dir()) as entries:
        for entry in entries:
            try:
                if (
                    entry.is_file(follow_symlinks=False)
                    and entry.stat().st_mtime < cutoff
                ):
                    os.unlink(entry.path)
            except OSError:
                pass


def _spool(resp) -> str:
    """Stream *resp*'s body to a file in :func:`spool_dir`; return its path."""
    import tempfile

    fd, path = tempfile.mkstemp(prefix="dl-", suffix=".download", dir=spool_dir())
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(64 * 1024):
                f.write(chunk)
    except BaseException:
        os.unlink(path)
        raise
    finally:
        resp.close()
    return path


class BrowserDownloads:
    """Files the route handler streamed to disk for download navigations.

    Fulfilling a whole book through Playwright copies it several times over
    (base64, a JSON pipe, the driver, CDP) and holds the ``download`` event
    until the last byte has crossed, so a large book times out. Instead the
    handler streams a download to a temp file itself and hands Chromium an
    empty attachment; the caller then takes the real file from here.
    """

    def __init__(self):
        self._paths: dict = {}

    @staticmethod
    def _key(url: str) -> str:
        from requests.utils import requote_uri

        return requote_uri(url)

    def add(self, url: str, path: str) -> None:
        old = self._paths.pop(self._key(url), None)
        if old:
            _unlink_quietly(old)
        self._paths[self._key(url)] = path

    def peek(self, url: str) -> Optional[str]:
        """The file downloaded from *url* (by URL only: never "the latest one",
        which could be a tracking pixel a page navigated to), or ``None``."""
        return self._paths.get(self._key(url))

    def take(self, url: str) -> Optional[str]:
        """Pop and return the file downloaded from *url*; the caller owns it."""
        return self._paths.pop(self._key(url), None)

    def discard_all(self) -> None:
        while self._paths:
            _unlink_quietly(self._paths.popitem()[1])


def _unlink_quietly(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def browser_route_handler(
    *,
    policy: Optional[NetPolicy] = None,
    document_timeout=DOCUMENT_TIMEOUT,
    subresource_timeout=SUBRESOURCE_TIMEOUT,
    blocked_resource_types=BLOCKED_RESOURCE_TYPES,
    downloads: Optional[BrowserDownloads] = None,
    fetch=None,
):
    """A ``context.route("**/*", ...)`` handler that fetches through the guard.

    Args:
        policy: The :class:`NetPolicy` (default: :func:`default_policy` now).
        document_timeout: ``requests`` timeout for navigations.
        subresource_timeout: ``requests`` timeout for everything a page loads.
        blocked_resource_types: Playwright resource types aborted unfetched.
        downloads: Where download navigations are streamed to (see
            :class:`BrowserDownloads`); a new one if not given. Exposed on the
            handler as ``handler.downloads``.
        fetch: The fetcher, ``(method, url, **requests_kwargs) -> Response``;
            defaults to :func:`request` with *policy*. A seam for tests.
    """
    import logging

    log = logging.getLogger(__name__)
    policy = policy or default_policy()
    fetch = fetch or (
        lambda method, url, **kw: request(method, url, policy=policy, **kw)
    )
    downloads = downloads if downloads is not None else BrowserDownloads()

    def handler(route):
        req = route.request
        if req.resource_type in blocked_resource_types:
            return route.abort("blockedbyclient")
        is_document = req.resource_type == "document"
        try:
            headers = {
                k: v
                for k, v in req.all_headers().items()
                if not k.startswith(":")
                and k.lower() not in _HOP_BY_HOP_REQUEST_HEADERS
            }
            resp = fetch(
                req.method,
                req.url,
                headers=headers,
                data=req.post_data_buffer,
                timeout=document_timeout if is_document else subresource_timeout,
                allow_redirects=True,
                stream=True,
            )
            fulfill_headers = _fulfill_headers(resp, request_url=req.url)
            if is_document and resp.ok and _is_download(resp):
                downloads.add(req.url, _spool(resp))
                disposition = {k.lower(): k for k in fulfill_headers}.get(
                    "content-disposition"
                )
                if (
                    disposition is None
                    or "attachment" not in fulfill_headers[disposition].lower()
                ):
                    fulfill_headers.pop(disposition, None)
                    fulfill_headers["Content-Disposition"] = "attachment"
                return route.fulfill(
                    status=resp.status_code, headers=fulfill_headers, body=b""
                )
            body = resp.content
        except UnsafeURLError as e:
            log.warning("Browser request refused: %s", e)
            return route.abort("blockedbyclient")
        except Exception as e:
            log.debug("Browser request failed: %s: %s", req.url, e)
            return route.abort("failed")
        return route.fulfill(
            status=resp.status_code, headers=fulfill_headers, body=body
        )

    handler.downloads = downloads
    return handler


#: The download stash of each guarded context, by ``id(context)``.
_CONTEXT_DOWNLOADS: dict = {}


def adopt_browser_download(context, url: str, dest) -> bool:
    """Move the file a guarded *context* streamed for *url* to *dest*.

    Works across filesystems; the stash entry is dropped only once the move
    has succeeded. False if there is no such file (or *context* is unguarded).
    """
    import shutil

    stash = _CONTEXT_DOWNLOADS.get(id(context))
    path = stash.peek(url) if stash is not None else None
    if not path:
        return False
    shutil.move(path, str(dest))
    stash.take(url)
    return True


def guard_browser_context(
    context, *, policy: Optional[NetPolicy] = None, **handler_kwargs
):
    """Route all of a Playwright ``BrowserContext``'s traffic through the guard.

    The context should come from a browser launched with
    :data:`CHROMIUM_GUARD_ARGS` and be created with ``service_workers="block"``
    (see :func:`launch_guarded_chromium`); this installs the request route, the
    WebSocket block and the page init script. Returns *context*.
    """
    handler = browser_route_handler(policy=policy, **handler_kwargs)
    _CONTEXT_DOWNLOADS[id(context)] = handler.downloads

    def _on_close(*_):
        stash = _CONTEXT_DOWNLOADS.pop(id(context), None)
        if stash is not None:
            stash.discard_all()

    context.route("**/*", handler)
    if hasattr(context, "route_web_socket"):  # Playwright >= 1.48
        # A WebSocket route that never calls connect_to_server is never connected.
        context.route_web_socket("**/*", lambda ws: None)
    if hasattr(context, "add_init_script"):
        context.add_init_script(_PAGE_INIT_SCRIPT)
    if hasattr(context, "on"):
        context.on("close", _on_close)
    return context


def launch_guarded_chromium(
    playwright, *, headless: bool = True, policy=None, **context_kwargs
):
    """Launch Chromium with no network of its own and return ``(browser, context)``.

    Every request the context makes is fetched through the guard.
    """
    remove_stale_spools()
    browser = playwright.chromium.launch(
        headless=headless, args=list(CHROMIUM_GUARD_ARGS)
    )
    context = browser.new_context(service_workers="block", **context_kwargs)
    return browser, guard_browser_context(context, policy=policy)


def check_navigation(url: str, *, policy: Optional[NetPolicy] = None) -> str:
    """Vet a URL before ``page.goto``: refuses ``file:``, ``data:``, internal IPs.

    >>> check_navigation("data:text/html,<p>hi</p>")
    Traceback (most recent call last):
      ...
    citeget.netguard.UnsafeURLError: Refused data:text/html,<p>hi</p>: scheme 'data' is not allowed (allowed: http, https)
    """
    return check_url(url, policy=policy)
