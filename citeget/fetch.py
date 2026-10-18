"""General-purpose URL → file fetching with format routing.

Where :mod:`citeget.resolve` is specialized for *academic references*
(structured ``Reference`` objects, libgen / arxiv / sci-hub strategies, PDF
output), this module handles the *general* case: arbitrary URLs (blog posts,
docs, specs, web pages) saved as Markdown (default), PDF, or original bytes.

Pipeline per URL:

1. Fetch the URL (httpx, follows redirects).
2. If the response is a PDF and the user wants ``"pdf"`` or ``"original"``,
   save it directly.
3. If the response is HTML and the user wants ``"pdf"``, scan for an
   embedded direct-PDF link (arxiv ``/pdf/``, GitHub ``.pdf`` assets, ACM
   ``/doi/pdf/``, etc.) and try that first; otherwise convert HTML→PDF via
   ``pdfkit`` (requires ``wkhtmltopdf``).
4. Otherwise convert HTML→Markdown via ``markdownify``. By default only the
   page's *main content* is kept (``content="main"``): site chrome is dropped
   by :mod:`citeget.main_content` first. ``content="full"`` converts the whole
   page.
5. If the requested format fails, fall back to Markdown.

Transient HTTP failures (connection resets, timeouts, 429 and 5xx) are retried
with exponential backoff (``retries=``). Files are named from the link text,
then the page title, then the URL path, then the domain plus a hash. Two
different URLs never share a file, and ``skip_existing`` only skips a file
recorded as coming from the same URL.

Public API:

- :func:`fetch` — main entry point. Accepts a URL, list of URLs, file path,
  or text containing URLs. Returns a list of :class:`FetchResult`.
- :func:`fetch_one` — single-URL convenience.
- :func:`extract_urls_from_text` — parse URLs from prose / markdown /
  reference-style citations, preserving anchor text and citation numbers.
- :func:`infer_filename` — derive a slug from anchor / citation / page title /
  URL path.
- :func:`main_content_markdown` — HTML→Markdown of the main content only.

The HTML→PDF converter is registered as a citeget downloader under the name
``"html_to_pdf"``, and HTML→Markdown as ``"html_to_md"``, so they compose
with the existing :mod:`citeget.resolve` registry.
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
import unicodedata
from dataclasses import dataclass
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

from citeget.main_content import (
    Extractor,
    clean_wayback_html,
    page_title,
    resolve_extractor,
    unwrap_layout_tables,
)

logger = logging.getLogger(__name__)


PreferFormat = Literal["md", "pdf", "original", "auto"]

#: ``"main"`` keeps the article only; ``"full"`` converts the whole page.
ContentMode = Literal["main", "full"]
DFLT_CONTENT: ContentMode = "main"

#: Extra attempts after a transient failure, and the first backoff (seconds),
#: doubled on each retry.
DFLT_RETRIES = 2
DFLT_RETRY_BACKOFF = 1.0


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


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


def infer_filename(entry: UrlEntry, ext: str, *, page_title: str = "") -> str:
    """Infer a filename for *entry*, ending in ``.{ext}``.

    Strategy (first non-empty wins):
    1. anchor text / citation title (slugified)
    2. *page_title*, the title of the fetched page, if known
    3. URL's last meaningful path segment
    4. domain + short hash

    >>> infer_filename(UrlEntry("http://paulgraham.com/hp.html"), "md")
    'hp.md'
    >>> infer_filename(
    ...     UrlEntry("http://paulgraham.com/hp.html"), "md",
    ...     page_title="Hackers and Painters",
    ... )
    'hackers-and-painters.md'
    """
    prefix = f"ref_{entry.ref.zfill(2)}_" if entry.ref else ""

    for title in (entry.title, page_title):
        if title and len(title) > 3:
            slug = slugify(title)
            if slug:
                return f"{prefix}{slug}.{ext}"

    parsed = urlparse(entry.url)
    path = parsed.path.rstrip("/")
    if path and path != "/":
        segment = path.rsplit("/", 1)[-1]
        segment = re.sub(r"\.(html?|php|aspx?)$", "", segment)
        slug = slugify(segment)
        if slug and len(slug) > 1:
            return f"{prefix}{slug}.{ext}"

    domain = parsed.netloc.replace("www.", "").split(".")[0]
    return f"{prefix}{slugify(domain)}-{_url_hash(entry.url)}.{ext}"


def candidate_filenames(
    entry: UrlEntry, ext: str, *, page_title: str = ""
) -> Iterator[str]:
    """Filenames for *entry*, most readable first, for resolving collisions.

    The :func:`infer_filename` name, then that name with the URL's query folded
    in (``?currentPage=2`` → ``-currentpage-2``), then with a short hash of the
    full URL, which is unique.

    >>> names = list(candidate_filenames(UrlEntry("http://a.com/post?page=2"), "md"))
    >>> names[:2]
    ['post.md', 'post-page-2.md']
    >>> names[2].startswith("post-") and len(names[2]) == len("post-12345678.md")
    True
    """
    name = infer_filename(entry, ext, page_title=page_title)
    stem = name[: -len(ext) - 1]
    yield name
    query = slugify(urlparse(entry.url).query)
    if query:
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


#: HTTP statuses worth retrying: rate limiting and server-side hiccups.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
#: Ceiling on any one wait, including a server's ``Retry-After``.
MAX_RETRY_WAIT = 60.0


def _retry_after(resp) -> Optional[float]:
    """The server's ``Retry-After`` in seconds, if it is a usable number.

    Negative, infinite and NaN values (all seen in the wild) are ignored rather
    than handed to ``time.sleep``, which raises on them.
    """
    try:
        seconds = float(resp.headers.get("retry-after", ""))
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _http_get(
    url: str,
    *,
    timeout: int = 30,
    retries: int = DFLT_RETRIES,
    retry_backoff: float = DFLT_RETRY_BACKOFF,
    transport=None,
    sleep: Callable[[float], None] = time.sleep,
):
    """Fetch *url* via httpx with redirect-following. Returns response or ``None``.

    Transport errors (a reset connection, "Server disconnected without sending
    a response", a timeout) and :data:`RETRY_STATUSES` are retried up to
    *retries* times, waiting ``retry_backoff * 2**attempt`` seconds (or the
    server's ``Retry-After``), capped at :data:`MAX_RETRY_WAIT`. Any other
    error status fails at once. *transport* is handed to ``httpx.Client``
    (tests pass an ``httpx.MockTransport``).
    """
    try:
        import httpx
    except ImportError as e:
        raise ImportError(
            "citeget.fetch requires httpx. Install with: pip install httpx"
        ) from e

    attempts = max(retries, 0) + 1
    with httpx.Client(
        follow_redirects=True, timeout=timeout, headers=_HEADERS, transport=transport
    ) as client:
        for attempt in range(attempts):
            last = attempt == attempts - 1
            wait = retry_backoff * 2**attempt
            try:
                resp = client.get(url)
                if resp.status_code not in RETRY_STATUSES or last:
                    resp.raise_for_status()
                    return resp
                wait = _retry_after(resp) or wait
                logger.info("HTTP %s from %s, retrying", resp.status_code, url)
            except httpx.TransportError as e:
                if last:
                    logger.warning("Failed to fetch %s: %s", url, e)
                    return None
                logger.info("Fetching %s failed (%s), retrying", url, e)
            except Exception as e:
                logger.warning("Failed to fetch %s: %s", url, e)
                return None
            sleep(max(0.0, min(wait, MAX_RETRY_WAIT)))
    return None  # pragma: no cover - the loop always returns


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


def html_to_markdown(html: str, *, source_url: str = "", **markdownify_options) -> str:
    """Convert *html* to clean Markdown.

    Uses :mod:`markdownify` (MIT). Long paragraphs are left unwrapped, code
    blocks become fenced blocks and tables become GitHub-flavoured tables.

    Args:
        html: The HTML source to convert.
        source_url: If given, prepended as an HTML comment provenance line.
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

    options = _resolve_markdownify_options(markdownify_options)

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(NON_CONTENT_TAGS):
        tag.decompose()

    md = MarkdownConverter(**options).convert_soup(soup)
    md = _collapse_blank_runs(md).strip() + "\n"

    if source_url:
        md = f"<!-- Source: {source_url} -->\n\n{md}"
    return md


#: Lines that are only the debris of a layout table: pipes, dashes, colons.
_TABLE_RESIDUE_RE = re.compile(r"^\s*\|[\s|:\-]*$")
#: A list bullet with nothing after it.
_EMPTY_BULLET_RE = re.compile(r"^\s*[*+-]\s*$")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def _drop_residue_lines(markdown: str) -> str:
    """Remove table-rule and empty-bullet lines, outside code blocks.

    >>> _drop_residue_lines("| --- | --- |\\n* \\ntext\\n---\\n")
    'text\\n---\\n'
    """

    def _clean(text):
        return "".join(
            line
            for line in text.splitlines(keepends=True)
            if not (_TABLE_RESIDUE_RE.match(line) or _EMPTY_BULLET_RE.match(line))
        )

    return "".join(
        text if is_code else _clean(text)
        for is_code, text in _outside_code_fences(markdown)
    )


def _with_title_heading(markdown: str, title: Optional[str]) -> str:
    """Lead with ``# title`` unless the document already has it as a heading."""
    if not title:
        return markdown
    wanted = slugify(title)
    for line in markdown.splitlines():
        m = _HEADING_RE.match(line)
        if m and slugify(m.group(1)) == wanted:
            return markdown
    return f"# {title}\n\n{markdown}"


def main_content_markdown(
    html: str,
    *,
    source_url: str = "",
    extractor: Union[str, Extractor, None] = None,
    title: Optional[str] = None,
    **markdownify_options,
) -> str:
    """Markdown of the *main content* of the page in *html*, without its chrome.

    Pipeline: drop the web.archive.org toolbar and un-prefix its links
    (:func:`~citeget.main_content.clean_wayback_html`), keep the main content
    (*extractor*: a name from
    :data:`~citeget.main_content.MAIN_CONTENT_EXTRACTORS` or any callable
    ``html -> html``; default the built-in, dependency-free one), unwrap
    layout tables, convert with :func:`html_to_markdown`, drop table debris,
    and lead with the page title as a heading if the article does not.

    Args:
        html: The page's HTML.
        source_url: If given, prepended as an HTML comment provenance line.
        extractor: Main-content strategy (name or callable).
        title: The heading to lead with; defaults to the page's own title.
        markdownify_options: Passed to :func:`html_to_markdown`.

    >>> page = (
    ...     "<html><head><title>On Things | My Blog</title></head><body>"
    ...     "<nav><a href='/'>Home</a> <a href='/about'>About</a></nav>"
    ...     "<article><p>The first sentence of the essay is here.</p>"
    ...     "<p>The essay ends here.</p></article>"
    ...     "<footer>Copyright me</footer></body></html>"
    ... )
    >>> print(main_content_markdown(page))
    # On Things
    <BLANKLINE>
    The first sentence of the essay is here.
    <BLANKLINE>
    The essay ends here.
    <BLANKLINE>
    """
    html = clean_wayback_html(html)
    if title is None:
        title = page_title(html)
    main = unwrap_layout_tables(resolve_extractor(extractor)(html))
    md = html_to_markdown(main, **markdownify_options)
    md = _collapse_blank_runs(_drop_residue_lines(md)).strip() + "\n"
    md = _with_title_heading(md, title)
    if source_url:
        md = f"<!-- Source: {source_url} -->\n\n{md}"
    return md


def page_to_markdown(
    html: str,
    *,
    content: ContentMode = DFLT_CONTENT,
    source_url: str = "",
    extractor: Union[str, Extractor, None] = None,
    **markdownify_options,
) -> str:
    """Markdown of the main content (``"main"``) or of the whole page (``"full"``).

    ``"full"`` is exactly :func:`html_to_markdown`, the behaviour before
    main-content extraction existed. *markdownify_options* go to the converter.
    """
    if content == "full":
        return html_to_markdown(html, source_url=source_url, **markdownify_options)
    if content == "main":
        return main_content_markdown(
            html, source_url=source_url, extractor=extractor, **markdownify_options
        )
    raise ValueError(f"content must be 'main' or 'full', not {content!r}")


def html_to_pdf(url: str, *, html: str = "") -> Optional[bytes]:
    """Render *url* (or *html* fallback) to PDF bytes via pdfkit/wkhtmltopdf.

    Returns ``None`` if pdfkit / wkhtmltopdf is unavailable or rendering fails.
    """
    try:
        import pdfkit
    except ImportError:
        logger.info(
            "HTML→PDF conversion requires pdfkit. "
            "Install with: pip install citeget[fetch] (and `brew install wkhtmltopdf`)."
        )
        return None

    options = {
        "quiet": "",
        "no-stop-slow-scripts": "",
        "encoding": "UTF-8",
        "enable-local-file-access": "",
    }
    try:
        return pdfkit.from_url(url, False, options=options)
    except Exception as e:
        logger.debug("pdfkit.from_url failed for %s: %s", url, e)
        if html:
            try:
                return pdfkit.from_string(html, False, options=options)
            except Exception as e2:
                logger.debug("pdfkit.from_string also failed: %s", e2)
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


#: Which URL each output path was written for in the current run.
Claims = MutableMapping[Path, str]

_SOURCE_HEADER_RE = re.compile(r"<!--\s*Source:\s*(\S+)\s*-->")
_SOURCE_HEADER_PEEK = 4096  # bytes: the header is the first line


def recorded_source(path: Path) -> Optional[str]:
    """The URL a saved file records as its source, or ``None`` if it records none.

    Markdown files written by :func:`fetch_one` begin with a
    ``<!-- Source: URL -->`` line. Other formats carry no such record.
    """
    if path.suffix != ".md":
        return None
    try:
        with path.open("rb") as f:
            head = f.read(_SOURCE_HEADER_PEEK).decode("utf-8", "ignore")
    except OSError:
        return None
    m = _SOURCE_HEADER_RE.search(head)
    return m.group(1) if m else None


def existing_claims(output_dir: Path) -> Claims:
    """The ``.md`` files already in *output_dir*, mapped to the URL each records.

    Seeds a run's claims, so a page fetched before is found under whatever name
    it was saved as -- including names from an older naming scheme (a path
    stem where the page title is now used).
    """
    output_dir = Path(output_dir).expanduser()
    if not output_dir.is_dir():
        return {}
    found = ((path, recorded_source(path)) for path in output_dir.glob("*.md"))
    return {path: url for path, url in found if url}


def _output_path(
    entry: UrlEntry,
    output_dir: Path,
    ext: str,
    *,
    page_title: str,
    claims: Claims,
) -> Path:
    """The path to write *entry* to: its own, never another URL's.

    A file of this format already claimed by this URL (in this run, or found
    by :func:`existing_claims`) is reused. Otherwise walks
    :func:`candidate_filenames` and takes the first name that is free, or
    that already belongs to this URL. An existing file that records no source
    (a PDF, say) is taken to be this URL's unless another URL claimed it in
    this run, which is the pre-collision-check behaviour of ``skip_existing``.
    """
    suffix = f".{ext}"
    for path, url in claims.items():
        if url == entry.url and path.suffix == suffix:
            return path
    for name in candidate_filenames(entry, ext, page_title=page_title):
        path = output_dir / name
        owner = claims.get(path)
        if owner is None and path.exists():
            owner = recorded_source(path) or entry.url
        if owner is None or owner == entry.url:
            claims[path] = entry.url
            return path
    raise AssertionError("candidate_filenames ends with a name unique to the URL")


def fetch_one(
    source: Union[str, UrlEntry],
    *,
    output_dir: Path,
    prefer: PreferFormat = "md",
    content: ContentMode = DFLT_CONTENT,
    extractor: Union[str, Extractor, None] = None,
    timeout: int = 30,
    retries: int = DFLT_RETRIES,
    skip_existing: bool = True,
    claims: Optional[Claims] = None,
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
        content: For Markdown output, ``"main"`` (default) keeps only the
            page's main content; ``"full"`` converts the whole page.
        extractor: The main-content strategy for ``content="main"``: a name
            in :data:`citeget.main_content.MAIN_CONTENT_EXTRACTORS`
            (``"builtin"``, the default, or ``"trafilatura"``) or a callable
            ``html -> html``.
        timeout: HTTP timeout in seconds.
        retries: Extra attempts after a transient HTTP failure.
        skip_existing: If True (default), skip when the output file already
            exists *and was written for this same URL*.
        claims: Output paths already owned, mapped to their URL.
            :func:`fetch` passes one for the whole run so that no two URLs
            share a file. Defaults to :func:`existing_claims` of
            *output_dir*.

    Returns:
        A :class:`FetchResult` describing what happened.
    """
    entry = source if isinstance(source, UrlEntry) else UrlEntry(url=source)
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    claims = existing_claims(output_dir) if claims is None else claims

    result = FetchResult(
        url=entry.url, status="failed", title=entry.title, ref=entry.ref
    )

    resp = _http_get(entry.url, timeout=timeout, retries=retries)
    if resp is None:
        result.error = "fetch_failed"
        return result

    def _save(data, *, ext, fmt, title=""):
        path = _output_path(entry, output_dir, ext, page_title=title, claims=claims)
        return _save_to(path, data, fmt=fmt, skip_existing=skip_existing, result=result)

    # --- Already a PDF -----------------------------------------------------
    if _is_pdf_response(resp):
        # If user wants md, we still save it as pdf (can't convert PDF→md here);
        # for any other choice, save as pdf.
        return _save(resp.content, ext="pdf", fmt="pdf")

    html = resp.text
    title = page_title(html, url=entry.url) or ""
    if not result.title:
        result.title = title or None

    # --- prefer=pdf: try direct PDF link, then HTML→PDF --------------------
    if prefer == "pdf":
        pdf_url = _find_pdf_link(entry.url, html)
        if pdf_url:
            logger.info("Found embedded PDF link: %s", pdf_url)
            pdf_resp = _http_get(pdf_url, timeout=timeout, retries=retries)
            if pdf_resp is not None and _is_pdf_response(pdf_resp):
                return _save(pdf_resp.content, ext="pdf", fmt="pdf", title=title)

        pdf_bytes = html_to_pdf(entry.url, html=html)
        if pdf_bytes:
            return _save(pdf_bytes, ext="pdf", fmt="pdf", title=title)
        logger.info("HTML→PDF unavailable; falling back to Markdown for %s", entry.url)

    # --- prefer=original: save raw response --------------------------------
    if prefer == "original":
        ct = resp.headers.get("content-type", "").lower()
        ext = "html" if "html" in ct or "xml" in ct else "bin"
        return _save(resp.content, ext=ext, fmt="original", title=title)

    # --- Default: Markdown -------------------------------------------------
    md = page_to_markdown(
        html, content=content, source_url=entry.url, extractor=extractor
    )
    return _save(md, ext="md", fmt="md", title=title)


def _save_to(
    path: Path,
    data: Union[bytes, str],
    *,
    fmt: str,
    skip_existing: bool,
    result: FetchResult,
) -> FetchResult:
    result.output_file = path
    result.format = fmt
    if skip_existing and path.exists():
        result.status = "skipped"
        return result
    if isinstance(data, str):
        path.write_text(data, encoding="utf-8")
    else:
        path.write_bytes(data)
    result.status = "ok"
    return result


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
    content: ContentMode = DFLT_CONTENT,
    extractor: Union[str, Extractor, None] = None,
    timeout: int = 30,
    retries: int = DFLT_RETRIES,
    skip_existing: bool = True,
    on_result=None,
) -> list[FetchResult]:
    """Fetch one or many URLs from a flexible *source*.

    Args:
        source: A URL, list of URLs, path to a file containing URLs, or
            a string of prose / markdown / reference-style text.
        output_dir: Where to save files (created if missing).
        prefer: ``"md"`` (default), ``"pdf"``, ``"original"``, or ``"auto"``.
            See :func:`fetch_one` for details.
        content: ``"main"`` (default) keeps only each page's main content;
            ``"full"`` converts the whole page.
        extractor: Main-content strategy (name or callable ``html -> html``).
        timeout: HTTP timeout per request.
        retries: Extra attempts after a transient HTTP failure.
        skip_existing: Skip URLs whose output file exists and was written for
            the same URL. Distinct URLs never share an output file.
        on_result: Optional callback ``(index, total, FetchResult) -> None``
            invoked after each fetch (for progress reporting).

    Returns:
        A list of :class:`FetchResult`, one per unique URL.
    """
    entries = _coerce_to_entries(source)
    output_dir = Path(output_dir).expanduser()

    results: list[FetchResult] = []
    claims: Claims = existing_claims(output_dir)
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        result = fetch_one(
            entry,
            output_dir=output_dir,
            prefer=prefer,
            content=content,
            extractor=extractor,
            timeout=timeout,
            retries=retries,
            skip_existing=skip_existing,
            claims=claims,
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
    resp = _http_get(url, timeout=timeout)
    if resp is None:
        return False
    md = page_to_markdown(resp.text, source_url=url)
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
