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


@dataclass(frozen=True)
class NetPolicy:
    """What outbound requests are allowed to reach.

    Args:
        allow_private: Allow loopback / private / link-local destinations.
            Off by default; this is what a hosted deployment relies on.
        allowed_schemes: URL schemes allowed on the first request and on every
            redirect hop.
        max_redirects: Redirect hops followed before giving up.
    """

    allow_private: bool = False
    allowed_schemes: tuple = ("http", "https")
    max_redirects: int = 10


def default_policy() -> NetPolicy:
    """The policy in force when none is passed, read from the environment now.

    >>> default_policy().allow_private in (True, False)
    True
    """
    flag = os.environ.get(ALLOW_PRIVATE_ENV_VAR, "").strip().lower()
    return NetPolicy(allow_private=flag in _TRUTHY)


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


def get(url: str, *, policy: Optional[NetPolicy] = None, **kwargs):
    """``requests.get`` with the destination guard. Same arguments and return.

    Raises :class:`UnsafeURLError` if the URL, a redirect target, or an address
    a host resolves to is refused; ``proxies=`` is refused as well.
    """
    policy = policy or default_policy()
    if kwargs.get("proxies") and not policy.allow_private:
        raise _refuse(url, "requests through a proxy are not allowed")
    check_url(url, policy=policy)
    with guarded_session(policy=policy) as session:
        return session.get(url, **kwargs)
