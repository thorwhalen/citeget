# citeget.netguard

Outbound-HTTP guard: refuse to fetch anything that is not on the public internet.

citeget fetches URLs that come from its users: the `url` of a reference, a
page to save as Markdown, a link found inside a fetched page. When citeget runs
as a hosted web app, that is a server-side request forgery (SSRF) surface: a
user could ask the server to fetch `http://127.0.0.1:<admin port>/` or the
cloud metadata service and then download the response as a job result.

Every HTTP request citeget makes goes through [`get()`](#citeget.netguard.get) (or a
[`guarded_session()`](#citeget.netguard.guarded_session)), which enforces a [`NetPolicy`](#citeget.netguard.NetPolicy):

- only `http` and `https` URLs, on the first request and on every redirect;
- the host is resolved **inside the connection step**, every resolved address
  must be a public one, and the socket is opened to that vetted address. There
  is no second DNS lookup, so a rebinding DNS server cannot swap the address
  between the check and the connect, and every redirect hop that opens a
  connection is vetted the same way;
- loopback, private (RFC 1918, `fc00::/7`), link-local (`169.254.0.0/16`,
  `fe80::/10`, which covers the usual metadata address), shared/CGNAT,
  unspecified, reserved and multicast addresses are refused, including when
  they are wrapped in IPv6 (`::ffff:127.0.0.1`, 6to4, NAT64, Teredo);
- proxies and `.netrc` from the environment are ignored (`trust_env=False`)
  and explicit proxies are refused, so `HTTP_PROXY` cannot route a request
  around the check.

Because the check is made on the address the socket actually connects to,
alternative spellings of a host (`2130706433`, `0x7f.1`, `017700000001`,
a DNS name that resolves to `10.0.0.5`) are all caught: they resolve to the
same refused address.

The guard is on by default. A desktop user who wants citeget to fetch from
their own LAN or `localhost` can opt out with the environment variable
`CITEGET_ALLOW_PRIVATE_NETWORK=1` or by passing
`policy=NetPolicy(allow_private=True)`.

```pycon
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
```

### Module Attributes

| [`ALLOW_PRIVATE_ENV_VAR`](#citeget.netguard.ALLOW_PRIVATE_ENV_VAR)   | Environment variable that switches the guard off (`1`/`true`/`yes`).   |
|--------------------------------------------------------------------------|------------------------------------------------------------------------|

### Functions

| [`check_url`](#citeget.netguard.check_url)(url, \*[, policy])             | Check the parts of *url* that can be judged without DNS; return it.      |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| [`default_policy`](#citeget.netguard.default_policy)()                         | The policy in force when none is passed, read from the environment now.  |
| [`get`](#citeget.netguard.get)(url, \*[, policy])                   | `requests.get` with the destination guard.                               |
| [`guarded_session`](#citeget.netguard.guarded_session)(\*[, policy])            | A `requests.Session` that enforces *policy* on every connection and hop. |
| [`is_public_address`](#citeget.netguard.is_public_address)(address)               | True if *address* (an IP literal, possibly with a `%zone`) is public.    |
| [`resolve_public`](#citeget.netguard.resolve_public)(host, port, \*[, policy]) | Resolve *host* and return its addresses, refusing if any is not public.  |

### Classes

| [`NetPolicy`](#citeget.netguard.NetPolicy)([allow_private, allowed_schemes, ...])   | What outbound requests are allowed to reach.   |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------|

### Exceptions

| [`UnsafeURLError`](#citeget.netguard.UnsafeURLError)   | A URL, or an address it resolved to, is outside what the policy allows.   |
|-------------------------------------------------------------------|---------------------------------------------------------------------------|

### citeget.netguard.ALLOW_PRIVATE_ENV_VAR *= 'CITEGET_ALLOW_PRIVATE_NETWORK'*

Environment variable that switches the guard off (`1`/`true`/`yes`).

### *class* citeget.netguard.NetPolicy(allow_private=False, allowed_schemes=('http', 'https'), max_redirects=10)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What outbound requests are allowed to reach.

* **Parameters:**
  * **allow_private** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Allow loopback / private / link-local destinations.
    Off by default; this is what a hosted deployment relies on.
  * **allowed_schemes** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – URL schemes allowed on the first request and on every
    redirect hop.
  * **max_redirects** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Redirect hops followed before giving up.

### *exception* citeget.netguard.UnsafeURLError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A URL, or an address it resolved to, is outside what the policy allows.

A `ValueError` rather than a `requests` exception on purpose: urllib3
retries and re-wraps `OSError` subclasses, which would bury the reason.

### citeget.netguard.check_url(url, , policy=None)

Check the parts of *url* that can be judged without DNS; return it.

The scheme must be allowed and there must be a host. A host written as an
IP literal is judged here too. Hostnames are judged when the connection is
made (see [`resolve_public()`](#citeget.netguard.resolve_public)), since that is the only check a DNS
rebind cannot race.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> check_url("https://example.org/paper.pdf")
'https://example.org/paper.pdf'
>>> check_url("http://[::1]:8080/")
Traceback (most recent call last):
  ...
citeget.netguard.UnsafeURLError: Refused http://[::1]:8080/: ::1 is not a public address
```

### citeget.netguard.default_policy()

The policy in force when none is passed, read from the environment now.

* **Return type:**
  [`NetPolicy`](#citeget.netguard.NetPolicy)

```pycon
>>> default_policy().allow_private in (True, False)
True
```

### citeget.netguard.get(url, , policy=None, \*\*kwargs)

`requests.get` with the destination guard. Same arguments and return.

Raises [`UnsafeURLError`](#citeget.netguard.UnsafeURLError) if the URL, a redirect target, or an address
a host resolves to is refused; `proxies=` is refused as well.

### citeget.netguard.guarded_session(, policy=None)

A `requests.Session` that enforces *policy* on every connection and hop.

Use it as a context manager, like `requests.Session`. With
`policy.allow_private` it still restricts schemes, but connects wherever
DNS points and honours environment proxies like plain `requests`.

### citeget.netguard.is_public_address(address)

True if *address* (an IP literal, possibly with a `%zone`) is public.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
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
```

### citeget.netguard.resolve_public(host, port, , policy=None)

Resolve *host* and return its addresses, refusing if any is not public.

Every address must pass: a name with one public and one private record is
refused outright rather than connected to “the good one”.

Returns `getaddrinfo` tuples `(family, type, proto, canonname, sockaddr)`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
