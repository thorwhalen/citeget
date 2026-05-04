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
4. Otherwise convert HTML→Markdown via ``html2text``.
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
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal, Optional, Union
from urllib.parse import urljoin, urlparse

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


def infer_filename(entry: UrlEntry, ext: str) -> str:
    """Infer a filename for *entry*, ending in ``.{ext}``.

    Strategy (first non-empty wins):
    1. anchor text / citation title (slugified)
    2. URL's last meaningful path segment
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
        if slug and len(slug) > 2:
            return f"{prefix}{slug}.{ext}"

    domain = parsed.netloc.replace("www.", "").split(".")[0]
    url_hash = hashlib.md5(entry.url.encode()).hexdigest()[:8]
    return f"{prefix}{slugify(domain)}-{url_hash}.{ext}"


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


def _http_get(url: str, *, timeout: int = 30):
    """Fetch *url* via httpx with redirect-following. Returns response or ``None``."""
    try:
        import httpx
    except ImportError as e:
        raise ImportError(
            "citeget.fetch requires httpx. Install with: pip install httpx"
        ) from e
    try:
        with httpx.Client(
            follow_redirects=True, timeout=timeout, headers=_HEADERS
        ) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", url, e)
        return None


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


def html_to_markdown(html: str, *, source_url: str = "") -> str:
    """Convert *html* to clean Markdown via html2text."""
    try:
        import html2text
    except ImportError as e:
        raise ImportError(
            "HTML→Markdown conversion requires html2text. "
            "Install with: pip install html2text"
        ) from e

    h = html2text.HTML2Text()
    h.body_width = 0
    h.ignore_links = False
    h.ignore_images = True
    h.ignore_emphasis = False
    h.protect_links = True
    h.unicode_snob = True
    h.skip_internal_links = True
    h.ignore_tables = False

    md = h.handle(html)
    if source_url:
        md = f"<!-- Source: {source_url} -->\n\n{md}"
    return md


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


def fetch_one(
    source: Union[str, UrlEntry],
    *,
    output_dir: Path,
    prefer: PreferFormat = "md",
    timeout: int = 30,
    skip_existing: bool = True,
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
        skip_existing: If True (default), skip when the inferred output
            file already exists.

    Returns:
        A :class:`FetchResult` describing what happened.
    """
    entry = source if isinstance(source, UrlEntry) else UrlEntry(url=source)
    output_dir = Path(output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    result = FetchResult(url=entry.url, status="failed", title=entry.title, ref=entry.ref)

    resp = _http_get(entry.url, timeout=timeout)
    if resp is None:
        result.error = "fetch_failed"
        return result

    # --- Already a PDF -----------------------------------------------------
    if _is_pdf_response(resp):
        # If user wants md, we still save it as pdf (can't convert PDF→md here);
        # for any other choice, save as pdf.
        return _save_bytes(
            entry, output_dir, resp.content, ext="pdf",
            fmt="pdf", skip_existing=skip_existing, result=result,
        )

    html = resp.text

    # --- prefer=pdf: try direct PDF link, then HTML→PDF --------------------
    if prefer == "pdf":
        pdf_url = _find_pdf_link(entry.url, html)
        if pdf_url:
            logger.info("Found embedded PDF link: %s", pdf_url)
            pdf_resp = _http_get(pdf_url, timeout=timeout)
            if pdf_resp is not None and _is_pdf_response(pdf_resp):
                return _save_bytes(
                    entry, output_dir, pdf_resp.content, ext="pdf",
                    fmt="pdf", skip_existing=skip_existing, result=result,
                )

        pdf_bytes = html_to_pdf(entry.url, html=html)
        if pdf_bytes:
            return _save_bytes(
                entry, output_dir, pdf_bytes, ext="pdf",
                fmt="pdf", skip_existing=skip_existing, result=result,
            )
        logger.info("HTML→PDF unavailable; falling back to Markdown for %s", entry.url)

    # --- prefer=original: save raw response --------------------------------
    if prefer == "original":
        ct = resp.headers.get("content-type", "").lower()
        ext = "html" if "html" in ct or "xml" in ct else "bin"
        return _save_bytes(
            entry, output_dir, resp.content, ext=ext,
            fmt="original", skip_existing=skip_existing, result=result,
        )

    # --- Default: Markdown -------------------------------------------------
    md = html_to_markdown(html, source_url=entry.url)
    return _save_text(
        entry, output_dir, md, ext="md", fmt="md",
        skip_existing=skip_existing, result=result,
    )


def _save_bytes(
    entry: UrlEntry,
    output_dir: Path,
    data: bytes,
    *,
    ext: str,
    fmt: str,
    skip_existing: bool,
    result: FetchResult,
) -> FetchResult:
    out_path = output_dir / infer_filename(entry, ext)
    if skip_existing and out_path.exists():
        result.status = "skipped"
        result.output_file = out_path
        result.format = fmt
        return result
    out_path.write_bytes(data)
    result.status = "ok"
    result.output_file = out_path
    result.format = fmt
    return result


def _save_text(
    entry: UrlEntry,
    output_dir: Path,
    text: str,
    *,
    ext: str,
    fmt: str,
    skip_existing: bool,
    result: FetchResult,
) -> FetchResult:
    out_path = output_dir / infer_filename(entry, ext)
    if skip_existing and out_path.exists():
        result.status = "skipped"
        result.output_file = out_path
        result.format = fmt
        return result
    out_path.write_text(text, encoding="utf-8")
    result.status = "ok"
    result.output_file = out_path
    result.format = fmt
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
    timeout: int = 30,
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
        timeout: HTTP timeout per request.
        skip_existing: Skip URLs whose inferred output file exists.
        on_result: Optional callback ``(index, total, FetchResult) -> None``
            invoked after each fetch (for progress reporting).

    Returns:
        A list of :class:`FetchResult`, one per unique URL.
    """
    entries = _coerce_to_entries(source)
    output_dir = Path(output_dir).expanduser()

    results: list[FetchResult] = []
    total = len(entries)
    for i, entry in enumerate(entries, 1):
        result = fetch_one(
            entry,
            output_dir=output_dir,
            prefer=prefer,
            timeout=timeout,
            skip_existing=skip_existing,
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
    md = html_to_markdown(resp.text, source_url=url)
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
