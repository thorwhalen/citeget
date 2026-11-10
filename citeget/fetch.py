"""General-purpose URL → file fetching with format routing.

Where :mod:`citeget.resolve` is specialized for *academic references*
(structured ``Reference`` objects, libgen / arxiv / sci-hub strategies, PDF
output), this module handles the *general* case: arbitrary URLs (blog posts,
docs, specs, web pages) saved as Markdown (default), PDF, or original bytes.

Pipeline per URL:

1. Fetch the URL through :mod:`citeget.netguard` (follows redirects, refuses
   loopback / private / link-local / metadata destinations on every hop).
2. If the response is a PDF and the user wants ``"pdf"`` or ``"original"``,
   save it directly.
3. If the response is HTML and the user wants ``"pdf"``, scan for an
   embedded direct-PDF link (arxiv ``/pdf/``, GitHub ``.pdf`` assets, ACM
   ``/doi/pdf/``, etc.) and try that first; otherwise convert HTML→PDF via
   ``pdfkit`` (requires ``wkhtmltopdf``).
4. Otherwise convert HTML→Markdown via ``markdownify``.
5. If the requested format fails, fall back to Markdown.

Public API:

- :func:`fetch` — main entry point. Accepts a URL, list of URLs, file path,
  or text containing URLs. Returns a list of :class:`FetchResult`.
- :func:`fetch_one` — single-URL convenience.
- :func:`extract_urls_from_text` — parse URLs from prose / markdown /
  reference-style citations, preserving anchor text and citation numbers.
- :func:`infer_filename` — derive a slug from anchor / citation / URL path.

The HTML→PDF converter is registered as a citeget downloader under the name
``"html_to_pdf"``, and HTML→Markdown as ``"html_to_md"``, so they compose
with the existing :mod:`citeget.resolve` registry.
"""

from __future__ import annotations

import hashlib
import logging
import os
import math
import re
import time
import unicodedata
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import (
    Callable,
    Iterable,
    Iterator,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import urljoin, urlparse

from citeget import netguard
from citeget.content import (
    DEFAULT_EXTRACTOR,
    EXTRACTORS,
    MIN_MAIN_CHARS,
    clean_wayback,
    drop_junk_lines,
    is_wayback_html,
    is_wayback_url,
    page_title,
    unwrap_layout_tables,
)

logger = logging.getLogger(__name__)


PreferFormat = Literal["md", "pdf", "original", "auto"]


# ---------------------------------------------------------------------------
# Source parsing — extract URLs from text in any common form
# ---------------------------------------------------------------------------

URL_RE = re.compile(
    r'https?://[^\s<>\[\]()"\',;|]+(?:\([^\s<>]*\))*[^\s<>\[\]()"\',;.|]*'
)
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\((https?://[^)]+)\)")
REF_LINK_RE = re.compile(r"^\[(\d+)\]\s*(.*?)(https?://\S+)", re.MULTILINE)


@dataclass
class UrlEntry:
    """A URL with optional context preserved for filename inference."""

    url: str
    title: Optional[str] = None
    ref: Optional[str] = None


def extract_urls_from_text(text: str) -> list[UrlEntry]:
    """Parse URLs from prose / markdown / reference-style citations.

    Recognized forms (each URL deduped, first match wins):

    - ``[anchor](https://url)``                    → markdown link
    - ``[1] Some citation. https://url``           → reference-style
    - bare ``https://url``                          → fallback
    """
    entries: list[UrlEntry] = []
    seen: set[str] = set()

    for m in MD_LINK_RE.finditer(text):
        anchor = m.group(1).strip()
        url = m.group(2).strip().rstrip(".")
        if url not in seen:
            seen.add(url)
            entries.append(UrlEntry(url=url, title=anchor or None))

    for m in REF_LINK_RE.finditer(text):
        ref_num = m.group(1)
        citation = m.group(2).strip()
        url = m.group(3).strip().rstrip(".,;:")
        # If this matched the outer `[anchor](url)` part of a markdown link
        # (rare: `[N] text [anchor](https://...)`), strip the bracketed tail.
        url = re.sub(r"\]\(https?://.*$", "", url)
        # Skip if this URL was already captured by the markdown-link pass.
        if url and url not in seen:
            seen.add(url)
            title = citation.rstrip(",. ").strip('"*[(') or None
            entries.append(UrlEntry(url=url, title=title, ref=ref_num))

    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,;:")
        if url not in seen:
            seen.add(url)
            entries.append(UrlEntry(url=url))

    return entries


# ---------------------------------------------------------------------------
# Filename inference
# ---------------------------------------------------------------------------


def slugify(text: str, *, max_len: int = 80) -> str:
    """Return a filesystem-safe slug for *text* (lowercase, hyphenated)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    text = re.sub(r"-+", "-", text)
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text


#: Shortest path-stem slug worth using as a filename (``hp`` of ``/hp.html``).
_MIN_STEM_LEN = 2

#: Longest query-string slug folded into an inferred filename.
_MAX_QUERY_SLUG = 40


def infer_filename(entry: UrlEntry, ext: str) -> str:
    """Infer a filename for *entry*, ending in ``.{ext}``.

    Strategy (first non-empty wins):
    1. anchor text / citation title (slugified)
    2. URL's last meaningful path segment, plus its query string
       (``?currentPage=2`` → ``-currentpage-2``) so pages stay distinct
    3. domain + short hash
    """
    prefix = f"ref_{entry.ref.zfill(2)}_" if entry.ref else ""

    if entry.title and len(entry.title) > 3:
        slug = slugify(entry.title)
        if slug:
            return f"{prefix}{slug}.{ext}"

    parsed = urlparse(entry.url)
    path = parsed.path.rstrip("/")
    if path and path != "/":
        segment = path.rsplit("/", 1)[-1]
        segment = re.sub(r"\.(html?|php|aspx?)$", "", segment)
        slug = slugify(segment)
        if slug and len(slug) >= _MIN_STEM_LEN:
            query = slugify(parsed.query, max_len=_MAX_QUERY_SLUG)
            if query:
                slug = f"{slug}-{query}"
            return f"{prefix}{slug}.{ext}"

    domain = parsed.netloc.replace("www.", "").split(".")[0]
    return f"{prefix}{slugify(domain)}-{_url_hash(entry.url)}.{ext}"


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def candidate_filenames(entry: UrlEntry, ext: str) -> Iterator[str]:
    """Filenames for *entry*, most readable first, for resolving collisions.

    The :func:`infer_filename` name, then that name with the URL's query folded
    in (when the name does not already carry it), then with a short hash of the
    full URL, which is unique to it.

    >>> e = UrlEntry(url="http://a.com/post?page=2", title="A Post")
    >>> names = list(candidate_filenames(e, "md"))
    >>> names[:2]
    ['a-post.md', 'a-post-page-2.md']
    >>> names[2].startswith("a-post-") and len(names[2]) == len("a-post-12345678.md")
    True
    """
    name = infer_filename(entry, ext)
    stem = name[: -len(ext) - 1]
    yield name
    query = slugify(urlparse(entry.url).query, max_len=_MAX_QUERY_SLUG)
    if query and not stem.endswith(f"-{query}"):
        yield f"{stem}-{query}.{ext}"
    yield f"{stem}-{_url_hash(entry.url)}.{ext}"


# ---------------------------------------------------------------------------
# HTTP + content-type sniffing
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


#: Extra attempts after a transient failure, and the first backoff in seconds
#: (doubled each retry). Override per call with ``retries=`` / ``retry_backoff=``.
DEFAULT_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 1.0

#: HTTP statuses worth another attempt: rate limiting and server-side hiccups.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Ceiling (seconds) on any one wait between attempts, a server's
#: ``Retry-After`` included: a run must not stall for an hour on one URL.
MAX_RETRY_WAIT = 60.0


def _retry_after(response) -> Optional[float]:
    """The server's ``Retry-After``, in seconds, if it is a usable number.

    Only the delay-seconds form is read; an HTTP-date, a negative, an infinite
    or a NaN value (all seen in the wild) gives ``None``, and the caller's own
    backoff applies.

    >>> from types import SimpleNamespace as R
    >>> _retry_after(R(headers={"retry-after": "5"}))
    5.0
    >>> [_retry_after(R(headers={"retry-after": v})) for v in ("-1", "nan", "inf", "soon")]
    [None, None, None, None]
    >>> _retry_after(R()) is None
    True
    """
    headers = getattr(response, "headers", None) or {}
    try:
        seconds = float(headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _is_transient(exc: Exception) -> bool:
    """True for connection-level errors and retryable HTTP statuses."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status is not None:
        return status in _RETRY_STATUSES
    # No response: reset, disconnect, timeout... (but never a refused URL).
    return not isinstance(exc, netguard.UnsafeURLError)


def _http_get(
    url: str,
    *,
    timeout: int = 30,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    sleep: Callable[[float], None] = time.sleep,
):
    """Fetch *url*, following redirects. Returns the response or ``None``.

    Goes through :func:`citeget.netguard.get`, so a destination outside the
    public internet raises :class:`~citeget.netguard.UnsafeURLError` instead of
    being fetched. That one is raised, not swallowed: "refused" is an answer
    the caller should report, not a transient failure.

    Transient failures (connection resets, 429, 5xx) are retried up to
    *retries* more times, sleeping *retry_backoff*, then twice that, and so on,
    or the server's ``Retry-After`` when it gives a usable one; any wait is
    capped at :data:`MAX_RETRY_WAIT`.
    """
    for attempt in range(retries + 1):
        try:
            resp = netguard.get(url, timeout=timeout, headers=_HEADERS)
            resp.raise_for_status()
            return resp
        except netguard.UnsafeURLError:
            raise
        except Exception as e:
            if attempt < retries and _is_transient(e):
                delay = _retry_after(getattr(e, "response", None))
                if delay is None:
                    delay = retry_backoff * 2**attempt
                delay = min(delay, MAX_RETRY_WAIT)
                logger.info(
                    "Transient failure fetching %s (%s); retry %d/%d in %.1fs",
                    url,
                    e,
                    attempt + 1,
                    retries,
                    delay,
                )
                sleep(delay)
                continue
            logger.warning("Failed to fetch %s: %s", url, e)
            return None
    return None  # pragma: no cover


def _is_pdf_response(resp) -> bool:
    """True if *resp* carries PDF content (magic bytes or content-type)."""
    ct = resp.headers.get("content-type", "")
    if "application/pdf" in ct:
        return True
    return resp.content[:5] == b"%PDF-"


def _find_pdf_link(url: str, html: str) -> Optional[str]:
    """Scan *html* for a direct-PDF link associated with *url*'s domain."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return None

    soup = BeautifulSoup(html, "html.parser")
    domain = urlparse(url).netloc.lower()

    if "arxiv.org" in domain:
        m = re.search(r"arxiv\.org/abs/([0-9.]+)", url)
        if m:
            return f"https://arxiv.org/pdf/{m.group(1)}.pdf"
        for a in soup.find_all("a", href=True):
            if "/pdf/" in a["href"]:
                return urljoin(url, a["href"])

    # Generic: any link ending in .pdf
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if re.search(r"\.pdf(\?|$)", href, re.IGNORECASE):
            return urljoin(url, href)

    return None


# ---------------------------------------------------------------------------
# HTML → Markdown / PDF converters
# ---------------------------------------------------------------------------


#: Tags whose *content* is never part of the document text. ``markdownify``
#: already drops ``script``/``style``, but not ``<title>``, so the whole head
#: is removed before conversion.
NON_CONTENT_TAGS = ("head", "script", "style", "noscript")

#: Defaults handed to ``markdownify``'s ``MarkdownConverter``. Override any of
#: them by passing the same keyword to :func:`html_to_markdown`.
HTML_TO_MARKDOWN_DEFAULTS = {
    "heading_style": "ATX",  # "# Title", not the underlined setext form
    "strip": ["img"],  # images are noise in a saved-for-reading document
    "bullets": "*",
    "escape_underscores": False,  # keeps identifiers like ``foo_bar`` readable
    "escape_asterisks": False,
}

#: An opening (or closing) fence of a fenced code block, allowing markdown's
#: three spaces of leading indentation.
_CODE_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _outside_code_fences(markdown: str) -> Iterator[Tuple[bool, str]]:
    """Split *markdown* into ``(is_fenced_code, text)`` chunks.

    An unterminated fence keeps everything after it marked as code, which is the
    conservative choice: whitespace inside code is content.

    >>> list(_outside_code_fences("a\\n```\\nb\\n```\\nc\\n"))
    [(False, 'a\\n'), (True, '```\\nb\\n```\\n'), (False, 'c\\n')]
    """
    chunk: list = []
    fence = ""
    for line in markdown.splitlines(keepends=True):
        match = _CODE_FENCE_RE.match(line)
        if not fence:
            if match:
                yield False, "".join(chunk)
                chunk, fence = [line], match.group(1)[0] * 3
            else:
                chunk.append(line)
        else:
            chunk.append(line)
            if match and match.group(1)[0] * 3 == fence:
                yield True, "".join(chunk)
                chunk, fence = [], ""
    yield bool(fence), "".join(chunk)


def _collapse_blank_runs(markdown: str) -> str:
    """Collapse runs of blank lines to a single one, *outside code blocks*.

    Two blank lines between top-level ``def``s is PEP 8, so a global
    ``re.sub(r"\\n{3,}", "\\n\\n", ...)`` silently rewrites the source code on
    every technical page. Fenced regions are passed through untouched.

    >>> _collapse_blank_runs("a\\n\\n\\n\\nb\\n")
    'a\\n\\nb\\n'
    >>> _collapse_blank_runs("```\\na\\n\\n\\n\\nb\\n```\\n")
    '```\\na\\n\\n\\n\\nb\\n```\\n'
    """
    return "".join(
        text if is_code else re.sub(r"\n{3,}", "\n\n", text)
        for is_code, text in _outside_code_fences(markdown)
    )


def _resolve_markdownify_options(overrides: Mapping) -> dict:
    """Merge *overrides* over :data:`HTML_TO_MARKDOWN_DEFAULTS`, validating names.

    ``MarkdownConverter`` silently ignores unknown options, so a typo (or an
    option name carried over from another converter) would be a quiet no-op.
    Raise instead.
    """
    from markdownify import MarkdownConverter

    known = {k for k in vars(MarkdownConverter.DefaultOptions) if not k.startswith("_")}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise TypeError(
            f"Unknown markdownify option(s): {', '.join(unknown)}. "
            f"Valid options are: {', '.join(sorted(known))}."
        )
    options = {**HTML_TO_MARKDOWN_DEFAULTS, **overrides}
    if "convert" in overrides:
        # markdownify rejects `strip` and `convert` together, and `strip` is
        # ours, not the caller's -- an explicit `convert` supersedes it.
        options.pop("strip", None)
    return options


def html_to_markdown(
    html: str,
    *,
    source_url: str = "",
    content: Literal["main", "full"] = "full",
    content_extractor: Union[str, Callable[[str], str]] = DEFAULT_EXTRACTOR,
    include_links: bool = True,
    **markdownify_options,
) -> str:
    """Convert *html* to clean Markdown.

    Uses :mod:`markdownify` (MIT). Long paragraphs are left unwrapped, code
    blocks become fenced blocks and tables become GitHub-flavoured tables.

    Args:
        html: The HTML source to convert.
        source_url: If given, prepended as an HTML comment provenance line.
            A ``web.archive.org`` URL (or a page carrying the Wayback toolbar)
            also triggers Wayback cleanup, in any *content* mode. Main mode
            falls back to the full page when the extracted article is shorter
            than ``MIN_MAIN_CHARS``.
        content: ``"full"`` (default here) converts the whole page; ``"main"``
            first extracts the main article (see :mod:`citeget.content`),
            unwraps layout tables, and leads with the page title as a heading
            when the article has no heading saying it.
        content_extractor: With ``content="main"``, a name from
            :data:`citeget.content.EXTRACTORS` or any callable ``html -> html``.
        include_links: If False, links are reduced to their text.
        markdownify_options: Overrides for :data:`HTML_TO_MARKDOWN_DEFAULTS`,
            passed to ``markdownify``'s ``MarkdownConverter``. Unknown option
            names raise ``TypeError``. Passing ``convert=`` drops the default
            ``strip=["img"]``, since markdownify accepts only one of the two.

    >>> print(html_to_markdown("<h1>Hi</h1><p>A <b>bold</b> word.</p>").strip())
    # Hi
    <BLANKLINE>
    A **bold** word.

    Whitespace inside fenced code blocks is content, and is preserved:

    >>> md = html_to_markdown("<pre><code>def a(): ...\\n\\n\\ndef b(): ...</code></pre>")
    >>> "\\n\\n\\n" in md
    True
    """
    from bs4 import BeautifulSoup
    from markdownify import MarkdownConverter

    if content not in ("main", "full"):
        raise ValueError(f"content must be 'main' or 'full', got {content!r}")
    if isinstance(content_extractor, str):
        if content_extractor not in EXTRACTORS:
            raise ValueError(
                f"Unknown content_extractor {content_extractor!r}; "
                f"choose from {sorted(EXTRACTORS)} or pass a callable."
            )
        extractor = EXTRACTORS[content_extractor]
    else:
        extractor = content_extractor
    options = _resolve_markdownify_options(markdownify_options)
    if not include_links and "convert" not in markdownify_options:
        options["strip"] = [*options.get("strip", []), "a"]
    if is_wayback_url(source_url) or is_wayback_html(html):
        html = clean_wayback(html)

    def convert(fragment: str) -> str:
        soup = BeautifulSoup(fragment, "html.parser")
        for tag in soup.find_all(NON_CONTENT_TAGS):
            tag.decompose()
        return MarkdownConverter(**options).convert_soup(soup)

    md = convert(html)
    if content == "main":
        main_md = drop_junk_lines(convert(unwrap_layout_tables(extractor(html))))
        # An extractor that finds (almost) nothing must not silently empty the
        # page: fall back to the whole thing.
        if len(main_md.strip()) >= MIN_MAIN_CHARS or len(main_md) >= len(md):
            md = _with_title_heading(
                _collapse_blank_runs(main_md).strip() + "\n",
                page_title(html, url=source_url),
            )
    md = _collapse_blank_runs(md).strip() + "\n"

    if source_url:
        md = f"<!-- Source: {source_url} -->\n\n{md}"
    return md


_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def _with_title_heading(markdown: str, title: Optional[str]) -> str:
    """Lead with ``# title`` unless the document has a top-level heading already,
    or names *title* in a heading of any level.

    >>> _with_title_heading("Some prose.\\n", "On Things")
    '# On Things\\n\\nSome prose.\\n'
    >>> _with_title_heading("## On Things\\n\\nSome prose.\\n", "On Things")
    '## On Things\\n\\nSome prose.\\n'
    >>> _with_title_heading("Intro.\\n\\n# The Talk\\n", "Other")
    'Intro.\\n\\n# The Talk\\n'
    """
    if not title:
        return markdown
    wanted = slugify(title)
    for is_code, chunk in _outside_code_fences(markdown):
        if is_code:
            continue
        for line in chunk.splitlines():
            m = _HEADING_RE.match(line)
            if m and (
                line.startswith("# ")
                or slugify(re.sub(r"\]\([^)]*\)", "]", m.group(1))) == wanted
            ):
                return markdown
    return f"# {title}\n\n{markdown}"


#: Elements that make wkhtmltopdf load something (a frame, an image, a style
#: sheet, a script, an object, a redirect). Removed before an offline render.
RESOURCE_LOADING_TAGS = (
    "script",
    "noscript",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "applet",
    "link",
    "style",
    "img",
    "picture",
    "source",
    "video",
    "audio",
    "track",
    "svg",
    "math",
    "image",
    "input",
    "meta",
    "base",
    "portal",
    "template",
)

#: Attributes that can make wkhtmltopdf load something. Removed everywhere.
RESOURCE_LOADING_ATTRS = frozenset(
    {
        "src",
        "srcset",
        "srcdoc",
        "background",
        "poster",
        "data",
        "style",
        "lowsrc",
        "dynsrc",
        "longdesc",
        "formaction",
        "action",
        "ping",
        "xlink:href",
        "codebase",
        "archive",
        "manifest",
        "cite",
        "profile",
    }
)

#: wkhtmltopdf options for rendering HTML we fetched ourselves, offline:
#: no JavaScript, no local files, and every load it still attempts goes to a
#: proxy that is not there. The HTML is also stripped of everything that loads
#: (:func:`_offline_html`); the options are the second wall, not the first.
OFFLINE_PDF_OPTIONS = {
    "quiet": "",
    "encoding": "UTF-8",
    "disable-javascript": "",
    "disable-local-file-access": "",
    "proxy": "http://0.0.0.0:9",
    "load-error-handling": "ignore",
    "load-media-error-handling": "ignore",
    "no-images": "",
}

#: wkhtmltopdf options when the network guard is off (a desktop opt-out):
#: wkhtmltopdf fetches the URL and its resources itself, for a faithful page.
ONLINE_PDF_OPTIONS = {
    "quiet": "",
    "no-stop-slow-scripts": "",
    "encoding": "UTF-8",
}


def _offline_html(html: str) -> str:
    """*html* with every element and attribute that loads a resource removed.

    >>> _offline_html('<p style="x">Hi<img src="http://10.0.0.1/"></p><iframe src="x"></iframe>')
    '<p>Hi</p>'
    >>> _offline_html('<!--><img src="http://10.0.0.1/">--><p>ok</p>')
    '<p>ok</p>'
    """
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(html, "html.parser")
    # Comments, CDATA, processing instructions and doctypes go first: browsers
    # and html.parser disagree on where some of them end (``<!-->``,
    # ``--!>``), so whatever bs4 sees inside one may be live markup to
    # wkhtmltopdf, and pdfkit reads ``<meta name="pdfkit-...">`` out of them.
    for node in soup.find_all(string=True):
        if type(node) is not NavigableString:
            node.extract()
    for tag in soup.find_all(RESOURCE_LOADING_TAGS):
        tag.decompose()
    for tag in soup.find_all(True):
        for attr in list(tag.attrs):
            if attr.lower() in RESOURCE_LOADING_ATTRS or attr.lower().startswith("on"):
                del tag.attrs[attr]
        if tag.name != "a" and "href" in tag.attrs:
            del tag.attrs["href"]
    return str(soup)


def html_to_pdf(
    url: str, *, html: str = "", policy: Optional[netguard.NetPolicy] = None
) -> Optional[bytes]:
    """Render *url* to PDF bytes via pdfkit/wkhtmltopdf.

    wkhtmltopdf is a browser and would fetch whatever the page points it at,
    past :mod:`citeget.netguard`. So by default it never gets a URL: the page
    is fetched through the guard (or *html* is used if given), stripped of
    everything that loads a resource, and rendered offline. The PDF keeps the
    text and structure, not images or styles. With the guard switched off
    (``policy.allow_private``, or ``CITEGET_ALLOW_PRIVATE_NETWORK=1``),
    wkhtmltopdf renders the live URL, resources and all.

    Returns ``None`` if pdfkit / wkhtmltopdf is unavailable, the fetch is
    refused or fails, or rendering fails.
    """
    try:
        import pdfkit
    except ImportError:
        logger.info(
            "HTML→PDF conversion requires pdfkit. "
            "Install with: pip install citeget[fetch] (and `brew install wkhtmltopdf`)."
        )
        return None

    policy = policy or netguard.default_policy()
    if policy.allow_private:
        try:
            return pdfkit.from_url(
                netguard.check_url(url, policy=policy),
                False,
                options=ONLINE_PDF_OPTIONS,
            )
        except Exception as e:
            logger.debug("pdfkit.from_url failed for %s: %s", url, e)
            if not html:
                return None
            try:
                return pdfkit.from_string(html, False, options=ONLINE_PDF_OPTIONS)
            except Exception as e2:
                logger.debug("pdfkit.from_string also failed: %s", e2)
                return None

    if not html:
        try:
            resp = _http_get(url)
            if resp is None:
                return None
            html = resp.text
        except netguard.UnsafeURLError as e:
            logger.warning("%s", e)
            return None
    # pdfkit turns ``<meta name="<prefix>...">`` tags in a string source into
    # wkhtmltopdf command-line options (``--allow``, ``--header-html``...). The
    # sanitizer removes meta tags; a prefix nobody can guess makes sure.
    import secrets

    config = pdfkit.configuration(meta_tag_prefix=f"citeget-{secrets.token_hex(16)}-")
    try:
        return pdfkit.from_string(
            _offline_html(html),
            False,
            options=OFFLINE_PDF_OPTIONS,
            configuration=config,
        )
    except Exception as e:
        logger.debug("pdfkit.from_string failed for %s: %s", url, e)
        return None


# ---------------------------------------------------------------------------
# Result type & main pipeline
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    """Outcome of a single URL fetch."""

    url: str
    status: Literal["ok", "skipped", "failed"]
    output_file: Optional[Path] = None
    format: Optional[str] = None  # "pdf", "md", or "original"
    title: Optional[str] = None
    ref: Optional[str] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        """True if file was written or already existed (status in {ok, skipped})."""
        return self.status in ("ok", "skipped")


def fetch_one(
    source: Union[str, UrlEntry],
    *,
    output_dir: Path,
    prefer: PreferFormat = "md",
    timeout: int = 30,
    skip_existing: bool = True,
    content: Literal["main", "full"] = "main",
    content_extractor: Union[str, Callable[[str], str]] = DEFAULT_EXTRACTOR,
    include_links: bool = True,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    _claims: Optional[_Claims] = None,
) -> FetchResult:
    """Fetch a single URL and save it under *output_dir*.

    Args:
        source: A URL string or a :class:`UrlEntry` (carries title/ref context).
        output_dir: Directory to write into (created if missing).
        prefer: Output format. ``"md"`` (default) converts HTML to Markdown;
            PDFs are saved as-is. ``"pdf"`` tries to keep/produce a PDF
            (requires ``pdfkit`` for HTML→PDF). ``"original"`` saves whatever
            content-type the server returned. ``"auto"`` is like ``"md"``
            for HTML and saves PDFs as PDFs.
        timeout: HTTP timeout in seconds.
        skip_existing: If True (default), skip when this URL's output file
            already exists. A ``.md`` file is this URL's when its
            ``<!-- Source: -->`` header names the URL, whatever its name.
        content: ``"main"`` (default) keeps only the main article in Markdown
            output; ``"full"`` keeps the whole page (the previous behaviour).
        content_extractor: Extractor name or callable ``html -> html``.
        include_links: If False, Markdown links are reduced to their text.
        retries, retry_backoff: Extra attempts on connection resets, 429 and
            5xx, and the first sleep between them (doubled each time).
        _claims: Internal. :func:`fetch` shares one map of owned output
            paths across a run, so two URLs never share a file.

    A URL given without a title takes the page's own (``og:title``, ``<title>``,
    first ``<h1>``): it names the file and fills ``FetchResult.title``.

    Returns:
        A :class:`FetchResult` describing what happened.
    """
    entry = source if isinstance(source, UrlEntry) else UrlEntry(url=source)
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = _Target(
        output_dir,
        _existing_claims(output_dir) if _claims is None else _claims,
        skip_existing,
        adopt=not (entry.title or entry.ref),  # decided before the page names it
    )

    result = FetchResult(
        url=entry.url, status="failed", title=entry.title, ref=entry.ref
    )

    try:
        resp = _http_get(
            entry.url, timeout=timeout, retries=retries, retry_backoff=retry_backoff
        )
    except netguard.UnsafeURLError as e:
        result.error = str(e)
        return result
    if resp is None:
        result.error = "fetch_failed"
        return result

    # --- Already a PDF -----------------------------------------------------
    if _is_pdf_response(resp):
        # If user wants md, we still save it as pdf (can't convert PDF→md here);
        # for any other choice, save as pdf.
        return _save_bytes(
            entry,
            resp.content,
            ext="pdf",
            fmt="pdf",
            result=result,
            target=target,
        )

    try:
        html = resp.text
    except netguard.UnsafeURLError as e:  # over the text ceiling
        result.error = str(e)
        return result

    if not entry.title:
        title = page_title(html, url=entry.url)
        if title:
            entry = replace(entry, title=title)
            result.title = title

    # --- prefer=pdf: try direct PDF link, then HTML→PDF --------------------
    if prefer == "pdf":
        pdf_url = _find_pdf_link(entry.url, html)
        if pdf_url:
            logger.info("Found embedded PDF link: %s", pdf_url)
            try:
                pdf_resp = _http_get(
                    pdf_url,
                    timeout=timeout,
                    retries=retries,
                    retry_backoff=retry_backoff,
                )
            except netguard.UnsafeURLError as e:
                logger.warning("%s", e)
                pdf_resp = None
            if pdf_resp is not None and _is_pdf_response(pdf_resp):
                return _save_bytes(
                    entry,
                    pdf_resp.content,
                    ext="pdf",
                    fmt="pdf",
                    result=result,
                    target=target,
                )

        pdf_bytes = html_to_pdf(entry.url, html=html)
        if pdf_bytes:
            return _save_bytes(
                entry,
                pdf_bytes,
                ext="pdf",
                fmt="pdf",
                result=result,
                target=target,
            )
        logger.info("HTML→PDF unavailable; falling back to Markdown for %s", entry.url)

    # --- prefer=original: save raw response --------------------------------
    if prefer == "original":
        ct = resp.headers.get("content-type", "").lower()
        ext = "html" if "html" in ct or "xml" in ct else "bin"
        return _save_bytes(
            entry,
            resp.content,
            ext=ext,
            fmt="original",
            result=result,
            target=target,
        )

    # --- Default: Markdown -------------------------------------------------
    md = html_to_markdown(
        html,
        source_url=entry.url,
        content=content,
        content_extractor=content_extractor,
        include_links=include_links,
    )
    return _save_text(
        entry,
        md,
        ext="md",
        fmt="md",
        result=result,
        target=target,
    )


_SOURCE_RE = re.compile(r"\A<!-- Source: (.*?) -->")


def _recorded_source(path: Path) -> Optional[str]:
    """The URL a saved Markdown file says it came from, if it says."""
    try:
        with path.open(encoding="utf-8") as f:
            m = _SOURCE_RE.match(f.read(2048))
    except (OSError, UnicodeDecodeError):
        return None
    return m.group(1) if m else None


#: Which URL each output path belongs to: found on disk, or written this run.
_Claims = MutableMapping[Path, str]

#: Per folder: ``{name: ((mtime_ns, size), path, recorded source)}``, so a
#: folder is re-read only for the files that changed since the last look (and
#: each ``Path`` is built, and hashed, once).
_SOURCE_INDEX: dict = {}
_SOURCE_INDEX_MAX_DIRS = 64


def _existing_claims(output_dir: Path) -> _Claims:
    """The ``.md`` files already in *output_dir*, mapped to the URL each records.

    Seeds a run's claims, so a page fetched before is found under whatever
    name it was saved as, including a name from an older naming scheme (a
    path stem where the page title is now used). Only new or changed files
    are opened, so calling this once per URL stays cheap in a large folder.
    """
    if not output_dir.is_dir():
        return {}
    key = str(output_dir.resolve())
    known = _SOURCE_INDEX.get(key, {})
    fresh = {}
    with os.scandir(output_dir) as entries:
        for e in entries:
            if not e.name.endswith(".md") or not e.is_file():
                continue
            st = e.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            hit = known.get(e.name)
            if hit is None or hit[0] != stamp:
                path = output_dir / e.name
                hit = (stamp, path, _recorded_source(path))
            fresh[e.name] = hit
    if key not in _SOURCE_INDEX and len(_SOURCE_INDEX) >= _SOURCE_INDEX_MAX_DIRS:
        _SOURCE_INDEX.pop(next(iter(_SOURCE_INDEX)))
    _SOURCE_INDEX[key] = fresh
    return {path: src for _, path, src in fresh.values() if src}


@dataclass
class _Target:
    """Where one URL's output goes, and which paths are already owned.

    *adopt*: may this URL reuse a file it owns under another name (one saved
    by an older naming scheme)? Not when the caller named the file, with a
    title or a reference number: that name is asked for, so it is used.
    """

    output_dir: Path
    claims: _Claims
    skip_existing: bool
    adopt: bool = True

    def resolve(self, entry: UrlEntry, ext: str) -> tuple[Path, bool]:
        """The output path for *entry*, and whether it can be skipped.

        In order: a :func:`candidate_filenames` name this URL already owns; a
        file of this format it owns under another name, if *adopt*; the first
        candidate name that is free. An existing file that records no source
        (a PDF, raw bytes, a hand-made file) is trusted to be this URL's, as
        before, unless another URL wrote it in this run. Across runs that case
        stays open: thorwhalen/citeget#32.
        """
        url, candidates = (
            entry.url,
            [self.output_dir / n for n in candidate_filenames(entry, ext)],
        )

        def owner(path):
            found = self.claims.get(path)
            if found is None and path.exists():
                found = _recorded_source(path) or url
            return found

        owned = [path for path in candidates if path.exists() and owner(path) == url]
        if not owned and self.adopt:
            owned = sorted(
                path
                for path, claimant in self.claims.items()
                if claimant == url
                and path.suffix == f".{ext}"
                and path.parent == self.output_dir
            )
        if owned:
            return owned[0], self.skip_existing
        for path in candidates:
            if owner(path) is None:
                return path, False
        raise AssertionError("candidate_filenames ends with a name unique to the URL")

    def save(
        self, entry, result: FetchResult, *, ext: str, fmt: str, write
    ) -> FetchResult:
        """Resolve the path, then skip or ``write(path)``, and record the result."""
        path, skip = self.resolve(entry, ext)
        if not skip:
            write(path)
        self.claims[path] = entry.url  # only once the file is there
        result.status = "skipped" if skip else "ok"
        result.output_file = path
        result.format = fmt
        return result


def _save_bytes(
    entry: UrlEntry,
    data: bytes,
    *,
    ext: str,
    fmt: str,
    result: FetchResult,
    target: _Target,
) -> FetchResult:
    return target.save(
        entry, result, ext=ext, fmt=fmt, write=lambda p: p.write_bytes(data)
    )


def _save_text(
    entry: UrlEntry,
    text: str,
    *,
    ext: str,
    fmt: str,
    result: FetchResult,
    target: _Target,
) -> FetchResult:
    return target.save(
        entry,
        result,
        ext=ext,
        fmt=fmt,
        write=lambda p: p.write_text(text, encoding="utf-8"),
    )


# ---------------------------------------------------------------------------
# Multi-source entry point
# ---------------------------------------------------------------------------


def _coerce_to_entries(source) -> list[UrlEntry]:
    """Turn flexible *source* input into a deduped list of :class:`UrlEntry`.

    Accepts:
    - a single URL string
    - a path-like to a file containing URLs in any form
    - a string with prose / markdown / reference citations
    - an iterable of any of the above (including UrlEntry instances)
    """
    if isinstance(source, UrlEntry):
        return [source]

    if isinstance(source, (str, Path)):
        s = str(source)
        path = Path(s).expanduser()
        if path.is_file():
            return extract_urls_from_text(path.read_text(encoding="utf-8"))
        if s.startswith(("http://", "https://")) and "\n" not in s:
            return [UrlEntry(url=s.strip())]
        return extract_urls_from_text(s)

    if isinstance(source, Iterable):
        out: list[UrlEntry] = []
        seen: set[str] = set()
        for item in source:
            for entry in _coerce_to_entries(item):
                if entry.url not in seen:
                    seen.add(entry.url)
                    out.append(entry)
        return out

    raise TypeError(f"Unsupported source type: {type(source).__name__}")


def fetch(
    source,
    *,
    output_dir: Union[str, Path] = "~/Downloads",
    prefer: PreferFormat = "md",
    timeout: int = 30,
    skip_existing: bool = True,
    on_result=None,
    content: Literal["main", "full"] = "main",
    content_extractor: Union[str, Callable[[str], str]] = DEFAULT_EXTRACTOR,
    include_links: bool = True,
    retries: int = DEFAULT_RETRIES,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
) -> list[FetchResult]:
    """Fetch one or many URLs from a flexible *source*.

    Args:
        source: A URL, list of URLs, path to a file containing URLs, or
            a string of prose / markdown / reference-style text.
        output_dir: Where to save files (created if missing).
        prefer: ``"md"`` (default), ``"pdf"``, ``"original"``, or ``"auto"``.
            See :func:`fetch_one` for details.
        timeout: HTTP timeout per request.
        skip_existing: Skip URLs whose output file exists (see :func:`fetch_one`).
        on_result: Optional callback ``(index, total, FetchResult) -> None``
            invoked after each fetch (for progress reporting).
        content, content_extractor, include_links, retries, retry_backoff:
            See :func:`fetch_one`.

    Returns:
        A list of :class:`FetchResult`, one per unique URL.
    """
    entries = _coerce_to_entries(source)
    output_dir = Path(output_dir).expanduser()
    claims = _existing_claims(output_dir)

    results: list[FetchResult] = []
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        result = fetch_one(
            entry,
            output_dir=output_dir,
            prefer=prefer,
            timeout=timeout,
            skip_existing=skip_existing,
            content=content,
            content_extractor=content_extractor,
            include_links=include_links,
            retries=retries,
            retry_backoff=retry_backoff,
            _claims=claims,
        )
        results.append(result)
        if on_result is not None:
            on_result(i, total, result)
    return results


# ---------------------------------------------------------------------------
# Register HTML converters as citeget downloaders (for resolve.py composition)
# ---------------------------------------------------------------------------


def _html_to_pdf_downloader(url: str, filepath: Path, *, timeout: int = 30) -> bool:
    """Downloader: render *url* (HTML) to PDF at *filepath*."""
    pdf_bytes = html_to_pdf(url)
    if not pdf_bytes:
        return False
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_bytes(pdf_bytes)
    return filepath.stat().st_size > 1000


def _html_to_md_downloader(url: str, filepath: Path, *, timeout: int = 30) -> bool:
    """Downloader: fetch *url* (HTML) and save Markdown at *filepath*."""
    try:
        resp = _http_get(url, timeout=timeout)
        if resp is None:
            return False
        html = resp.text
    except netguard.UnsafeURLError as e:
        logger.warning("%s", e)
        return False
    md = html_to_markdown(html, source_url=url, content="main")
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(md, encoding="utf-8")
    return filepath.stat().st_size > 100


# Register only if resolve module is importable (it always is, but be defensive)
try:
    from citeget.resolve import register_downloader

    register_downloader("html_to_pdf", _html_to_pdf_downloader)
    register_downloader("html_to_md", _html_to_md_downloader)
except ImportError:  # pragma: no cover
    pass
