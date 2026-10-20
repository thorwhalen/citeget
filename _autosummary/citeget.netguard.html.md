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

| [`ALLOW_PRIVATE_ENV_VAR`](#citeget.netguard.ALLOW_PRIVATE_ENV_VAR)        | Environment variable that switches the guard off (`1`/`true`/`yes`).                                                                                                                              |
|-------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`MAX_RESPONSE_BYTES_ENV_VAR`](#citeget.netguard.MAX_RESPONSE_BYTES_ENV_VAR)   | no ceiling).                                                                                                                                                                                      |
| [`DEFAULT_MAX_RESPONSE_BYTES`](#citeget.netguard.DEFAULT_MAX_RESPONSE_BYTES)   | room for most books, small enough that a few at once fit in a small server's RAM (the browser path holds a body ~5x over).                                                                        |
| [`DEFAULT_MAX_TEXT_BYTES`](#citeget.netguard.DEFAULT_MAX_TEXT_BYTES)       | parsing HTML or XML costs tens of times its size in memory, so text gets a far smaller ceiling.                                                                                                   |
| [`DEFAULT_MAX_RESPONSE_SECONDS`](#citeget.netguard.DEFAULT_MAX_RESPONSE_SECONDS) | Longest a body may take to arrive.                                                                                                                                                                |
| [`DEFAULT_TIMEOUT`](#citeget.netguard.DEFAULT_TIMEOUT)              | the total deadline is only checked between reads, so a read must not hang.                                                                                                                        |
| [`DEAD_PROXY`](#citeget.netguard.DEAD_PROXY)                   | a port nothing listens on.                                                                                                                                                                        |
| [`CHROMIUM_GUARD_ARGS`](#citeget.netguard.CHROMIUM_GUARD_ARGS)          | Chromium flags that leave the browser no network path of its own.                                                                                                                                 |
| [`BLOCKED_RESOURCE_TYPES`](#citeget.netguard.BLOCKED_RESOURCE_TYPES)       | nothing citeget reads needs them, and every request the route serves holds up the page (the handler runs on Playwright's one thread), so ad frames, long polls and beacons are not worth a fetch. |
| [`DOCUMENT_TIMEOUT`](#citeget.netguard.DOCUMENT_TIMEOUT)             | Timeouts (connect, read), in seconds, for a page itself and for what it loads.                                                                                                                    |
| [`STALE_SPOOL_SECONDS`](#citeget.netguard.STALE_SPOOL_SECONDS)          | Spooled browser downloads older than this are removed at the next launch: what a killed job left behind.                                                                                          |

### Functions

| [`adopt_browser_download`](#citeget.netguard.adopt_browser_download)(context, url, dest)     | Move the file a guarded *context* streamed for *url* to *dest*.                                                     |
|-------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------|
| [`browser_route_handler`](#citeget.netguard.browser_route_handler)(\*[, policy, ...])       | A `context.route("**/*", ...)` handler that fetches through the guard.                                              |
| [`capped`](#citeget.netguard.capped)(policy)                                 | *policy* with the [`response_ceiling()`](#citeget.netguard.response_ceiling) in force applied, if tighter. |
| [`check_navigation`](#citeget.netguard.check_navigation)(url, \*[, policy])            | Vet a URL before `page.goto`: refuses `file:`, `data:`, internal IPs.                                               |
| [`check_url`](#citeget.netguard.check_url)(url, \*[, policy])                   | Check the parts of *url* that can be judged without DNS; return it.                                                 |
| [`default_policy`](#citeget.netguard.default_policy)()                               | The policy in force when none is passed, read from the environment now.                                             |
| [`env_limit`](#citeget.netguard.env_limit)(var, default)                        | A non-negative integer from environment variable *var*, else *default*.                                             |
| [`get`](#citeget.netguard.get)(url, \*[, policy])                         | `requests.get` with the destination guard (see [`request()`](#citeget.netguard.request)).         |
| [`guard_browser_context`](#citeget.netguard.guard_browser_context)(context, \*[, policy])   | Route all of a Playwright `BrowserContext`'s traffic through the guard.                                             |
| [`guarded_session`](#citeget.netguard.guarded_session)(\*[, policy])                  | A `requests.Session` that enforces *policy* on every connection and hop.                                            |
| [`is_public_address`](#citeget.netguard.is_public_address)(address)                     | True if *address* (an IP literal, possibly with a `%zone`) is public.                                               |
| [`launch_guarded_chromium`](#citeget.netguard.launch_guarded_chromium)(playwright, \*[, ...]) | Launch Chromium with no network of its own and return `(browser, context)`.                                         |
| [`remove_stale_spools`](#citeget.netguard.remove_stale_spools)(\*[, max_age])             | Delete spooled downloads older than *max_age* seconds.                                                              |
| [`request`](#citeget.netguard.request)(method, url, \*[, policy, session])    | `requests.request` with the destination guard.                                                                      |
| [`resolve_public`](#citeget.netguard.resolve_public)(host, port, \*[, policy])       | Resolve *host* and return its addresses, refusing if any is not public.                                             |
| [`response_ceiling`](#citeget.netguard.response_ceiling)(limit, \*[, source])          | Cap every response body fetched in this block at *limit* bytes.                                                     |
| [`spool_dir`](#citeget.netguard.spool_dir)()                                    | The directory browser downloads are spooled to (per uid, created 0700).                                             |

### Classes

| [`BrowserDownloads`](#citeget.netguard.BrowserDownloads)()                               | Files the route handler streamed to disk for download navigations.                                              |
|---------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| [`Ceiling`](#citeget.netguard.Ceiling)([limit, source, fired])                  | A [`response_ceiling()`](#citeget.netguard.response_ceiling) in force; `fired` once it refused a body. |
| [`GuardedResponse`](#citeget.netguard.GuardedResponse)()                                | A `requests.Response` that honours a [`NetPolicy`](#citeget.netguard.NetPolicy)'s ceilings.     |
| [`NetPolicy`](#citeget.netguard.NetPolicy)([allow_private, allowed_schemes, ...]) | What outbound requests are allowed to reach.                                                                    |

### Exceptions

| [`ResponseTooLargeError`](#citeget.netguard.ResponseTooLargeError)   | A response body is larger than the policy's `max_response_bytes`.       |
|--------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`UnsafeURLError`](#citeget.netguard.UnsafeURLError)          | A URL, or an address it resolved to, is outside what the policy allows. |

### citeget.netguard.ALLOW_PRIVATE_ENV_VAR *= 'CITEGET_ALLOW_PRIVATE_NETWORK'*

Environment variable that switches the guard off (`1`/`true`/`yes`).

### citeget.netguard.BLOCKED_RESOURCE_TYPES *= frozenset({'csp_report', 'eventsource', 'font', 'image', 'manifest', 'media', 'other', 'ping', 'sub_frame', 'texttrack'})*

nothing citeget reads needs them, and every
request the route serves holds up the page (the handler runs on Playwright’s
one thread), so ad frames, long polls and beacons are not worth a fetch.

* **Type:**
  Resource types refused outright

### *class* citeget.netguard.BrowserDownloads

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Files the route handler streamed to disk for download navigations.

Fulfilling a whole book through Playwright copies it several times over
(base64, a JSON pipe, the driver, CDP) and holds the `download` event
until the last byte has crossed, so a large book times out. Instead the
handler streams a download to a temp file itself and hands Chromium an
empty attachment; the caller then takes the real file from here.

#### peek(url)

The file downloaded from *url* (by URL only: never “the latest one”,
which could be a tracking pixel a page navigated to), or `None`.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

#### take(url)

Pop and return the file downloaded from *url*; the caller owns it.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.netguard.CHROMIUM_GUARD_ARGS *= ('--proxy-server=http://127.0.0.1:9', '--proxy-bypass-list=<-loopback>', '--force-webrtc-ip-handling-policy=disable_non_proxied_udp', '--dns-prefetch-disable')*

Chromium flags that leave the browser no network path of its own.

### *class* citeget.netguard.Ceiling(limit=None, source='', fired=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A [`response_ceiling()`](#citeget.netguard.response_ceiling) in force; `fired` once it refused a body.

### citeget.netguard.DEAD_PROXY *= 'http://127.0.0.1:9'*

a port nothing listens on.

* **Type:**
  Where Chromium’s own traffic is sent

### citeget.netguard.DEFAULT_MAX_RESPONSE_BYTES *= 104857600*

room for most books, small enough that a few at
once fit in a small server’s RAM (the browser path holds a body ~5x over).

* **Type:**
  Largest response body read

### citeget.netguard.DEFAULT_MAX_RESPONSE_SECONDS *= 600*

Longest a body may take to arrive. Socket timeouts are per read, so without
this a server could trickle a body for hours and hold a job slot throughout.

### citeget.netguard.DEFAULT_MAX_TEXT_BYTES *= 10485760*

parsing HTML or XML
costs tens of times its size in memory, so text gets a far smaller ceiling.

* **Type:**
  Largest body decoded as text (`.text` / `.json()`)

### citeget.netguard.DEFAULT_TIMEOUT *= (10, 60)*

the
total deadline is only checked between reads, so a read must not hang.

* **Type:**
  Default `requests` timeout (connect, read) when the caller gives none

### citeget.netguard.DOCUMENT_TIMEOUT *= (10, 60)*

Timeouts (connect, read), in seconds, for a page itself and for what it loads.

### *class* citeget.netguard.GuardedResponse

Bases: `Response`

A `requests.Response` that honours a [`NetPolicy`](#citeget.netguard.NetPolicy)’s ceilings.

`iter_content` (and so `.content`, which reads through it) is capped by
size and by a deadline, both counted per response however many times the
body is iterated; `.text` / `.json()` refuse a body over the text
ceiling. Parsing `.content` directly bypasses the text ceiling (not the
size one): citeget’s parsers all go through `.text` / `.json()`.

#### iter_content(chunk_size=1, decode_unicode=False)

Iterates over the response data.  When stream=True is set on the
request, this avoids reading the content at once into memory for
large responses.  The chunk size is the number of bytes it should
read into memory.  This is not necessarily the length of each item
returned as decoding can take place.

chunk_size must be of type int or None. A value of None will
function differently depending on the value of `stream`.
stream=True will read data as it arrives in whatever size the
chunks are received. If stream=False, data is returned as
a single chunk.

If decode_unicode is True, content will be decoded using encoding
information from the response. If no encoding information is available,
bytes will be returned. This can be bypassed by manually setting
`encoding` on the response.

#### json(\*\*kwargs)

Decodes the JSON response body (if any) as a Python object.

This may return a dictionary, list, etc. depending on what is in the response.

* **Parameters:**
  **\*\*kwargs** – Optional arguments that `json.loads` takes.
* **Raises:**
  **requests.exceptions.JSONDecodeError** – If the response body does not
  contain valid json.

#### *property* text

Content of the response, in unicode.

If Response.encoding is None, encoding will be guessed using
`charset_normalizer` or `chardet`.

The encoding of the response content is determined based solely on HTTP
headers, following RFC 2616 to the letter. If you can take advantage of
non-HTTP knowledge to make a better guess at the encoding, you should
set `r.encoding` appropriately before accessing this property.

### citeget.netguard.MAX_RESPONSE_BYTES_ENV_VAR *= 'CITEGET_MAX_RESPONSE_BYTES'*

no ceiling).

* **Type:**
  Environment variables for the response ceilings (`0`

### *class* citeget.netguard.NetPolicy(allow_private=False, allowed_schemes=('http', 'https'), max_redirects=10, max_response_bytes=104857600, max_text_bytes=10485760, max_response_seconds=600, max_response_bytes_source='CITEGET_MAX_RESPONSE_BYTES', on_too_large=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What outbound requests are allowed to reach.

* **Parameters:**
  * **allow_private** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Allow loopback / private / link-local destinations.
    Off by default; this is what a hosted deployment relies on.
  * **allowed_schemes** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – URL schemes allowed on the first request and on every
    redirect hop.
  * **max_redirects** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Redirect hops followed before giving up.
  * **max_response_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Largest (decoded) response body read; a larger one
    raises [`ResponseTooLargeError`](#citeget.netguard.ResponseTooLargeError). `None` or `0`: no ceiling.
  * **max_text_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Largest body that `.text` / `.json()` will decode.
  * **max_response_seconds** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]) – Longest a body may take to arrive, in total.
  * **max_response_bytes_source** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – What sets *max_response_bytes*, named in the
    refusal so the reader knows which knob to turn.
  * **on_too_large** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[], [`None`](https://docs.python.org/3/builtins/constants.html#None)]]) – Called when a body is refused for *max_response_bytes*,
    before the error is raised: how a [`response_ceiling()`](#citeget.netguard.response_ceiling) learns it
    fired although the caller swallowed the error.

### *exception* citeget.netguard.ResponseTooLargeError

Bases: [`UnsafeURLError`](#citeget.netguard.UnsafeURLError)

A response body is larger than the policy’s `max_response_bytes`.

A refusal like any other: callers that report refusals report this too,
and nobody retries it.

### citeget.netguard.STALE_SPOOL_SECONDS *= 21600*

Spooled browser downloads older than this are removed at the next launch:
what a killed job left behind.

### *exception* citeget.netguard.UnsafeURLError

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

A URL, or an address it resolved to, is outside what the policy allows.

A `ValueError` rather than a `requests` exception on purpose: urllib3
retries and re-wraps `OSError` subclasses, which would bury the reason.

### citeget.netguard.adopt_browser_download(context, url, dest)

Move the file a guarded *context* streamed for *url* to *dest*.

Works across filesystems; the stash entry is dropped only once the move
has succeeded. False if there is no such file (or *context* is unguarded).

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### citeget.netguard.browser_route_handler(, policy=None, document_timeout=(10, 60), subresource_timeout=(5, 10), blocked_resource_types=frozenset({'csp_report', 'eventsource', 'font', 'image', 'manifest', 'media', 'other', 'ping', 'sub_frame', 'texttrack'}), downloads=None, fetch=None)

A `context.route("**/*", ...)` handler that fetches through the guard.

* **Parameters:**
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`NetPolicy`](#citeget.netguard.NetPolicy)]) – The [`NetPolicy`](#citeget.netguard.NetPolicy) (default: [`default_policy()`](#citeget.netguard.default_policy) now).
  * **document_timeout** – `requests` timeout for navigations.
  * **subresource_timeout** – `requests` timeout for everything a page loads.
  * **blocked_resource_types** – Playwright resource types aborted unfetched.
  * **downloads** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`BrowserDownloads`](#citeget.netguard.BrowserDownloads)]) – Where download navigations are streamed to (see
    [`BrowserDownloads`](#citeget.netguard.BrowserDownloads)); a new one if not given. Exposed on the
    handler as `handler.downloads`.
  * **fetch** – The fetcher, `(method, url, **requests_kwargs) -> Response`;
    defaults to [`request()`](#citeget.netguard.request) with *policy* over one guarded session
    for the whole handler, so a page’s subresources reuse connections
    (the browser owns cookies; the session keeps none between requests).
    A seam for tests. Playwright calls the handler from one thread.

The handler has `.downloads` and `.close()`, which closes the session.

### citeget.netguard.capped(policy)

*policy* with the [`response_ceiling()`](#citeget.netguard.response_ceiling) in force applied, if tighter.

* **Return type:**
  [`NetPolicy`](#citeget.netguard.NetPolicy)

### citeget.netguard.check_navigation(url, , policy=None)

Vet a URL before `page.goto`: refuses `file:`, `data:`, internal IPs.

```pycon
>>> check_navigation("data:text/html,<p>hi</p>")
Traceback (most recent call last):
  ...
citeget.netguard.UnsafeURLError: Refused data:text/html,<p>hi</p>: scheme 'data' is not allowed (allowed: http, https)
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.netguard.check_url(url, , policy=None)

Check the parts of *url* that can be judged without DNS; return it.

The scheme must be allowed and there must be a host. A host written as an
IP literal is judged here too. Hostnames are judged when the connection is
made (see [`resolve_public()`](#citeget.netguard.resolve_public)), since that is the only check a DNS
rebind cannot race.

```pycon
>>> check_url("https://example.org/paper.pdf")
'https://example.org/paper.pdf'
>>> check_url("http://[::1]:8080/")
Traceback (most recent call last):
  ...
citeget.netguard.UnsafeURLError: Refused http://[::1]:8080/: ::1 is not a public address
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.netguard.default_policy()

The policy in force when none is passed, read from the environment now.

```pycon
>>> default_policy().allow_private in (True, False)
True
```

* **Return type:**
  [`NetPolicy`](#citeget.netguard.NetPolicy)

### citeget.netguard.env_limit(var, default)

A non-negative integer from environment variable *var*, else *default*.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### citeget.netguard.get(url, , policy=None, \*\*kwargs)

`requests.get` with the destination guard (see [`request()`](#citeget.netguard.request)).

### citeget.netguard.guard_browser_context(context, , policy=None, \*\*handler_kwargs)

Route all of a Playwright `BrowserContext`’s traffic through the guard.

The context should come from a browser launched with
[`CHROMIUM_GUARD_ARGS`](#citeget.netguard.CHROMIUM_GUARD_ARGS) and be created with `service_workers="block"`
(see [`launch_guarded_chromium()`](#citeget.netguard.launch_guarded_chromium)); this installs the request route, the
WebSocket block and the page init script. Returns *context*.

### citeget.netguard.guarded_session(, policy=None)

A `requests.Session` that enforces *policy* on every connection and hop.

Use it as a context manager, like `requests.Session`. With
`policy.allow_private` it still restricts schemes, but connects wherever
DNS points and honours environment proxies like plain `requests`.

### citeget.netguard.is_public_address(address)

True if *address* (an IP literal, possibly with a `%zone`) is public.

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

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### citeget.netguard.launch_guarded_chromium(playwright, , headless=True, policy=None, \*\*context_kwargs)

Launch Chromium with no network of its own and return `(browser, context)`.

Every request the context makes is fetched through the guard.

### citeget.netguard.remove_stale_spools(, max_age=21600)

Delete spooled downloads older than *max_age* seconds.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.netguard.request(method, url, , policy=None, session=None, \*\*kwargs)

`requests.request` with the destination guard. Same arguments and return.

`session` is a [`guarded_session()`](#citeget.netguard.guarded_session) (under the same *policy*) to reuse, so
successive requests share connections; the caller closes it. The session’s cookie
jar is emptied before and after each call: a redirect chain still carries cookies
from hop to hop, and nothing is kept between calls. Not for concurrent use.

The body is read before returning (or, with `stream=True`, as the caller
iterates), up to `policy.max_response_bytes`, and the whole exchange,
redirects included, must finish within `policy.max_response_seconds` of
the call. `timeout` defaults to [`DEFAULT_TIMEOUT`](#citeget.netguard.DEFAULT_TIMEOUT).

Raises [`UnsafeURLError`](#citeget.netguard.UnsafeURLError) if the URL, a redirect target, or an address
a host resolves to is refused, or `proxies=` is given;
[`ResponseTooLargeError`](#citeget.netguard.ResponseTooLargeError) (a subclass) if the body is over the size or
time ceiling, or if `.text` / `.json()` is asked of a body over the text
ceiling.

### citeget.netguard.resolve_public(host, port, , policy=None)

Resolve *host* and return its addresses, refusing if any is not public.

Every address must pass: a name with one public and one private record is
refused outright rather than connected to “the good one”.

Returns `getaddrinfo` tuples `(family, type, proto, canonname, sockaddr)`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.netguard.response_ceiling(limit, , source="a caller's ceiling")

Cap every response body fetched in this block at *limit* bytes.

For a caller that cannot reach each fetch’s `policy=` – a job spending a
byte budget across strategies it does not see into. Applied wherever a
policy is resolved ([`request()`](#citeget.netguard.request), [`guarded_session()`](#citeget.netguard.guarded_session),
[`browser_route_handler()`](#citeget.netguard.browser_route_handler)), so it only ever tightens: the policy’s own
ceiling still holds when it is the smaller one. Nested blocks take the
smaller limit. `None` or `0` adds no ceiling.

Yields the [`Ceiling`](#citeget.netguard.Ceiling) in force. Callers in between usually swallow
the refusal (a strategy that fails tries the next), so `ceiling.fired` is
how the block’s owner learns its ceiling, not some other failure, stopped a
fetch.

```pycon
>>> with response_ceiling(400, source="the job budget") as ceiling:
...     capped(NetPolicy()).max_response_bytes, ceiling.fired
(400, False)
>>> capped(NetPolicy()).max_response_bytes == DEFAULT_MAX_RESPONSE_BYTES
True
```

### citeget.netguard.spool_dir()

The directory browser downloads are spooled to (per uid, created 0700).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
