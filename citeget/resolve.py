"""Composable download and URL-resolution for academic references.

The acquisition pipeline has three layers:

- **UrlResolver** ``(Reference) -> list[str]`` — turn citation info into
  candidate download URLs (URL rewriting, DOI lookup, search APIs).
- **Downloader** ``(url, filepath) -> bool`` — fetch a URL, validate the
  content, save to disk.
- **AcquisitionStrategy** ``(Reference, Path) -> Optional[str]`` — a complete
  unit that combines resolvers and downloaders (or does its own thing, like
  libgen's playwright-based search+download).

The factory :func:`resolve_and_download` wires a resolver to a downloader.
:func:`chain` composes strategies (try first, fall back to second).

Usage::

    from citeget.resolve import resolve_reference

    # Zero-config: tries all built-in strategies in order
    path = resolve_reference(ref, Path("paper.pdf"))

    # Custom chain
    from citeget.resolve import chain, STRATEGIES
    my = chain(STRATEGIES["direct"], STRATEGIES["arxiv_search"])
    resolve_reference(ref, filepath, strategy=my)

    # Add a repository rule
    from citeget.resolve import url_rewriter, BUILTIN_URL_RULES, register_resolver
    rules = {**BUILTIN_URL_RULES, "myrepo.org": lambda u: u.replace("/view/", "/dl/")}
    register_resolver("my_rewriter", url_rewriter(rules=rules))
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, Optional, Protocol, runtime_checkable

from citeget.acquire_references import Reference

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class UrlResolver(Protocol):
    """Turn a :class:`Reference` into candidate download URLs."""

    def __call__(self, ref: Reference) -> list[str]: ...


@runtime_checkable
class Downloader(Protocol):
    """Fetch *url*, validate content, save to *filepath*.

    Returns ``True`` on success.
    """

    def __call__(self, url: str, filepath: Path, *, timeout: int = 30) -> bool: ...


@runtime_checkable
class AcquisitionStrategy(Protocol):
    """Complete acquire-one-reference unit.

    Returns the filepath string on success, ``None`` on failure.
    """

    def __call__(self, ref: Reference, filepath: Path) -> Optional[str]: ...


# ---------------------------------------------------------------------------
# Registries  (same pattern as citeget.extract)
# ---------------------------------------------------------------------------

RESOLVERS: dict[str, UrlResolver] = {}
DOWNLOADERS: dict[str, Downloader] = {}
STRATEGIES: dict[str, AcquisitionStrategy] = {}


def register_resolver(name: str, resolver: UrlResolver) -> None:
    """Register a named URL resolver."""
    RESOLVERS[name] = resolver


def get_resolver(name: str) -> UrlResolver:
    """Retrieve a registered resolver by name.

    Raises:
        KeyError: If *name* is not registered.
    """
    return RESOLVERS[name]


def list_resolvers() -> list[str]:
    """Return names of all registered resolvers."""
    return list(RESOLVERS.keys())


def register_downloader(name: str, downloader: Downloader) -> None:
    """Register a named downloader."""
    DOWNLOADERS[name] = downloader


def get_downloader(name: str) -> Downloader:
    """Retrieve a registered downloader by name.

    Raises:
        KeyError: If *name* is not registered.
    """
    return DOWNLOADERS[name]


def list_downloaders() -> list[str]:
    """Return names of all registered downloaders."""
    return list(DOWNLOADERS.keys())


def register_strategy(name: str, strategy: AcquisitionStrategy) -> None:
    """Register a named acquisition strategy."""
    STRATEGIES[name] = strategy


def get_strategy(name: str) -> AcquisitionStrategy:
    """Retrieve a registered strategy by name.

    Raises:
        KeyError: If *name* is not registered.
    """
    return STRATEGIES[name]


def list_strategies() -> list[str]:
    """Return names of all registered strategies."""
    return list(STRATEGIES.keys())


# ---------------------------------------------------------------------------
# Composition helpers
# ---------------------------------------------------------------------------


def chain(*strategies: AcquisitionStrategy) -> AcquisitionStrategy:
    """Try *strategies* in order, return the first success."""

    def _chained(ref: Reference, filepath: Path) -> Optional[str]:
        for strategy in strategies:
            result = strategy(ref, filepath)
            if result:
                return result
        return None

    return _chained  # type: ignore[return-value]


def chain_resolvers(*resolvers: UrlResolver) -> UrlResolver:
    """Concatenate URL lists from multiple resolvers (deduped, order-preserving)."""

    def _chained(ref: Reference) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        for resolver in resolvers:
            for url in resolver(ref):
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
        return urls

    return _chained  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Strategy factory
# ---------------------------------------------------------------------------


def resolve_and_download(
    resolver: UrlResolver | str,
    *,
    downloader: Downloader | str | None = None,
) -> AcquisitionStrategy:
    """Create a strategy that resolves URLs then tries to download each.

    Args:
        resolver: A :class:`UrlResolver` callable or registered name.
        downloader: A :class:`Downloader` callable or registered name.
            ``None`` uses the ``"pdf"`` downloader.
    """
    if isinstance(resolver, str):
        resolver = RESOLVERS[resolver]
    if downloader is None:
        downloader = DOWNLOADERS.get("pdf", _pdf_downloader)
    elif isinstance(downloader, str):
        downloader = DOWNLOADERS[downloader]

    _res, _dl = resolver, downloader  # close over resolved values

    def _strategy(ref: Reference, filepath: Path) -> Optional[str]:
        for url in _res(ref):
            logger.debug("Trying URL: %s", url)
            if _dl(url, filepath):
                return str(filepath)
        return None

    return _strategy  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Built-in downloaders
# ---------------------------------------------------------------------------

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _pdf_downloader(url: str, filepath: Path, *, timeout: int = 30) -> bool:
    """Download *url*, validate as PDF (``%PDF`` magic or content-type)."""
    import requests

    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return False

        content_type = resp.headers.get("Content-Type", "")
        first_bytes = b""
        chunks: list[bytes] = []
        for chunk in resp.iter_content(chunk_size=8192):
            if not first_bytes:
                first_bytes = chunk[:5]
            chunks.append(chunk)

        if b"%PDF" in first_bytes or "pdf" in content_type.lower():
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
            return filepath.stat().st_size > 1000
        return False
    except Exception as e:
        logger.debug("PDF download failed for %s: %s", url, e)
        return False


def _any_downloader(url: str, filepath: Path, *, timeout: int = 30) -> bool:
    """Download *url* without format validation (HTML, PDF, anything)."""
    import requests

    try:
        resp = requests.get(url, headers=_DEFAULT_HEADERS, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return False

        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return filepath.stat().st_size > 500
    except Exception as e:
        logger.debug("Download failed for %s: %s", url, e)
        return False


register_downloader("pdf", _pdf_downloader)
register_downloader("any", _any_downloader)


# ---------------------------------------------------------------------------
# Built-in URL rewrite rules
# ---------------------------------------------------------------------------

UrlTransform = Callable[[str], str]


def _rewrite_arxiv(url: str) -> str:
    """``arxiv.org/abs/X`` → ``arxiv.org/pdf/X.pdf``"""
    url = url.replace("/abs/", "/pdf/")
    if not url.endswith(".pdf"):
        url += ".pdf"
    return url


def _rewrite_openreview(url: str) -> str:
    """``openreview.net/forum?id=X`` → ``openreview.net/pdf?id=X``"""
    return url.replace("/forum?", "/pdf?")


def _rewrite_pmc(url: str) -> str:
    """``ncbi.nlm.nih.gov/pmc/articles/PMCX`` → PDF endpoint."""
    m = re.search(r"(PMC\d+)", url)
    if m:
        return f"https://www.ncbi.nlm.nih.gov/pmc/articles/{m.group(1)}/pdf/"
    return url


def _rewrite_biorxiv(url: str) -> str:
    """``biorxiv.org`` / ``medrxiv.org`` content → ``.full.pdf``."""
    if url.endswith(".full.pdf") or url.endswith(".pdf"):
        return url
    return url.rstrip("/") + ".full.pdf"


def _rewrite_ssrn(url: str) -> str:
    """``ssrn.com/abstract=X`` → direct PDF delivery URL."""
    m = re.search(r"abstract[_=](\d+)", url)
    if m:
        aid = m.group(1)
        return (
            f"https://papers.ssrn.com/sol3/Delivery.cfm/"
            f"SSRN_ID{aid}_code.pdf?abstractid={aid}"
        )
    return url


def _rewrite_acm(url: str) -> str:
    """``dl.acm.org/doi/10.X`` → ``dl.acm.org/doi/pdf/10.X``"""
    if "/doi/pdf/" not in url and "/doi/" in url:
        return url.replace("/doi/", "/doi/pdf/", 1)
    return url


def _rewrite_ieee(url: str) -> str:
    """``ieeexplore.ieee.org/document/X`` → stamp PDF endpoint."""
    m = re.search(r"/document/(\d+)", url)
    if m:
        return f"https://ieeexplore.ieee.org/stampPDF/getPDF.jsp?arnumber={m.group(1)}"
    return url


def _rewrite_siam(url: str) -> str:
    """``epubs.siam.org/doi/X`` → ``epubs.siam.org/doi/pdf/X``"""
    if "/doi/pdf/" not in url and "/doi/" in url:
        return url.replace("/doi/", "/doi/pdf/", 1)
    return url


def _rewrite_springer(url: str) -> str:
    """``link.springer.com/article/10.X`` → content/pdf endpoint."""
    if "/content/pdf/" not in url and "/article/" in url:
        return url.replace("/article/", "/content/pdf/", 1) + ".pdf"
    return url


BUILTIN_URL_RULES: dict[str, UrlTransform] = {
    "arxiv.org": _rewrite_arxiv,
    "openreview.net": _rewrite_openreview,
    "ncbi.nlm.nih.gov/pmc": _rewrite_pmc,
    "biorxiv.org": _rewrite_biorxiv,
    "medrxiv.org": _rewrite_biorxiv,
    "ssrn.com": _rewrite_ssrn,
    "dl.acm.org": _rewrite_acm,
    "ieeexplore.ieee.org": _rewrite_ieee,
    "epubs.siam.org": _rewrite_siam,
    "link.springer.com": _rewrite_springer,
}


# ---------------------------------------------------------------------------
# URL-rewriter resolver factory
# ---------------------------------------------------------------------------


def url_rewriter(
    *,
    rules: dict[str, UrlTransform] | None = None,
) -> UrlResolver:
    """Create a resolver that rewrites known repository URLs to direct PDFs.

    Args:
        rules: Domain-substring → transform mapping.
            ``None`` uses :data:`BUILTIN_URL_RULES`.
    """
    _rules = dict(BUILTIN_URL_RULES) if rules is None else dict(rules)

    def _resolve(ref: Reference) -> list[str]:
        if not ref.url:
            return []
        urls: list[str] = []
        for domain, transform in _rules.items():
            if domain in ref.url:
                rewritten = transform(ref.url)
                if rewritten and rewritten != ref.url:
                    urls.append(rewritten)
        # Always include the original URL as fallback
        urls.append(ref.url)
        return urls

    return _resolve  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# DOI resolver  (Crossref lookup → Unpaywall open-access → sci-hub fallback)
# ---------------------------------------------------------------------------


def _lookup_doi_crossref(ref: Reference) -> str:
    """Look up a DOI via Crossref text search.  Returns DOI string or ``""``."""
    import requests

    clean_title = re.sub(r"[\"':;,.!?(){}[\]—–\-]", " ", ref.title)
    clean_title = re.sub(r"\s+", " ", clean_title).strip()
    surname = ""
    if ref.authors:
        from citeget.acquire_references import _first_author_surname

        surname = _first_author_surname(ref.authors)

    query = f"{clean_title} {surname}".strip()
    if not query:
        return ""

    try:
        resp = requests.get(
            f"https://api.crossref.org/works?query={query}&rows=3",
            headers=_DEFAULT_HEADERS,
            timeout=15,
        )
        if resp.status_code != 200:
            return ""
        items = resp.json()["message"]["items"]
        ref_words = set(re.findall(r"\w+", ref.title.lower()))
        for item in items:
            item_title = item.get("title", [""])[0].lower()
            item_words = set(re.findall(r"\w+", item_title))
            if ref_words and item_words:
                overlap = len(ref_words & item_words) / max(len(ref_words), 1)
                if overlap >= 0.5:
                    return item.get("DOI", "")
    except Exception as e:
        logger.debug("Crossref lookup failed: %s", e)
    return ""


def _unpaywall_pdf(doi: str, *, email: str = "") -> str:
    """Query Unpaywall for an open-access PDF URL.  Returns URL or ``""``."""
    if not email:
        return ""
    import requests

    try:
        resp = requests.get(
            f"https://api.unpaywall.org/v2/{doi}?email={email}",
            timeout=10,
        )
        if resp.status_code != 200:
            return ""
        data = resp.json()
        best = data.get("best_oa_location") or {}
        return best.get("url_for_pdf", "") or ""
    except Exception:
        return ""


def doi_resolver(*, email: str = "") -> UrlResolver:
    """Resolve via DOI: Crossref lookup → Unpaywall (open access) → Sci-Hub.

    Args:
        email: Email for the Unpaywall API (optional; skipped if empty).
    """

    def _resolve(ref: Reference) -> list[str]:
        doi = ref.doi or _lookup_doi_crossref(ref)
        if not doi:
            return []
        urls: list[str] = []
        # Unpaywall (legal open access)
        oa_url = _unpaywall_pdf(doi, email=email)
        if oa_url:
            urls.append(oa_url)
        # Sci-hub last resort
        urls.append(f"https://sci-hub.ru/{doi}")
        return urls

    return _resolve  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Arxiv API search resolver
# ---------------------------------------------------------------------------


def arxiv_search_resolver() -> UrlResolver:
    """Search the arxiv API by author + title, return PDF URLs."""

    def _resolve(ref: Reference) -> list[str]:
        import requests
        from xml.etree import ElementTree as ET

        surname = ""
        if ref.authors:
            from citeget.acquire_references import _first_author_surname

            surname = _first_author_surname(ref.authors)

        clean_title = re.sub(r"[\"':;,.!?(){}[\]—–\-]", " ", ref.title)
        clean_title = re.sub(r"\s+", " ", clean_title).strip()

        query_parts: list[str] = []
        if surname:
            query_parts.append(f"au:{surname}")
        if clean_title:
            title_words = clean_title.split()[:6]
            query_parts.append(f"ti:{'+'.join(title_words)}")
        if not query_parts:
            return []

        query = "+AND+".join(query_parts)
        api_url = (
            f"http://export.arxiv.org/api/query?search_query={query}&max_results=5"
        )

        try:
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                return []
            root = ET.fromstring(resp.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}

            ref_words = set(re.findall(r"\w+", ref.title.lower()))
            urls: list[str] = []
            for entry in root.findall("a:entry", ns):
                title_el = entry.find("a:title", ns)
                if title_el is None or not title_el.text:
                    continue
                entry_words = set(re.findall(r"\w+", title_el.text.strip().lower()))
                if not ref_words or not entry_words:
                    continue
                overlap = len(ref_words & entry_words) / max(len(ref_words), 1)
                if overlap < 0.5:
                    continue
                for link in entry.findall("a:link", ns):
                    if link.get("type") == "application/pdf":
                        href = link.get("href", "")
                        if href:
                            urls.append(href)
            return urls
        except Exception as e:
            logger.debug("Arxiv search failed: %s", e)
            return []

    return _resolve  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Semantic Scholar resolver
# ---------------------------------------------------------------------------


def semantic_scholar_resolver() -> UrlResolver:
    """Query the Semantic Scholar API for open-access PDF links."""

    def _resolve(ref: Reference) -> list[str]:
        import requests

        if not ref.title:
            return []

        try:
            params = {
                "query": ref.title[:200],
                "limit": "3",
                "fields": "openAccessPdf,title",
            }
            resp = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params=params,
                timeout=15,
            )
            if resp.status_code != 200:
                return []

            ref_words = set(re.findall(r"\w+", ref.title.lower()))
            urls: list[str] = []
            for paper in resp.json().get("data", []):
                paper_title = paper.get("title", "")
                paper_words = set(re.findall(r"\w+", paper_title.lower()))
                if ref_words and paper_words:
                    overlap = len(ref_words & paper_words) / max(len(ref_words), 1)
                    if overlap < 0.5:
                        continue
                oa = paper.get("openAccessPdf")
                if oa and oa.get("url"):
                    urls.append(oa["url"])
            return urls
        except Exception as e:
            logger.debug("Semantic Scholar search failed: %s", e)
            return []

    return _resolve  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Wrappers for existing search+download strategies
# ---------------------------------------------------------------------------


def libgen_strategy(
    *,
    topics: tuple[str, ...] = ("articles", "books"),
    timeout: int = 30000,
) -> AcquisitionStrategy:
    """Wrap the existing libgen search+download as an :class:`AcquisitionStrategy`.

    This is a self-contained strategy (not a resolver+downloader pair) because
    libgen requires playwright-based browser automation for both search and
    download.
    """

    def _strategy(ref: Reference, filepath: Path) -> Optional[str]:
        from citeget.acquire_references import _try_libgen

        log_entries: list[dict] = []
        for topic in topics:
            result = _try_libgen(
                ref,
                filepath,
                topic=topic,
                log_entries=log_entries,
                timeout=timeout,
            )
            if result:
                return result
        return None

    return _strategy  # type: ignore[return-value]


def scihub_strategy() -> AcquisitionStrategy:
    """Wrap the existing Sci-Hub/DOI download as an :class:`AcquisitionStrategy`."""

    def _strategy(ref: Reference, filepath: Path) -> Optional[str]:
        from citeget.acquire_references import _try_scihub_via_doi

        log_entries: list[dict] = []
        return _try_scihub_via_doi(ref, filepath, log_entries=log_entries)

    return _strategy  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Logging wrapper
# ---------------------------------------------------------------------------


def with_logging(
    strategy: AcquisitionStrategy,
    *,
    name: str = "",
    log_entries: list | None = None,
) -> AcquisitionStrategy:
    """Wrap a strategy to append a log entry on each call.

    Args:
        strategy: The strategy to wrap.
        name: Label for log entries.
        log_entries: List to append dicts to (mutated in place).
    """
    from datetime import datetime

    def _logged(ref: Reference, filepath: Path) -> Optional[str]:
        result = strategy(ref, filepath)
        if log_entries is not None:
            log_entries.append(
                {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "ref_number": ref.number,
                    "ref_title": ref.title[:80],
                    "strategy": name,
                    "success": result is not None,
                    "filepath": result or "",
                }
            )
        return result

    return _logged  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Register built-in resolvers and strategies
# ---------------------------------------------------------------------------

register_resolver("url_rewriter", url_rewriter())
register_resolver("doi", doi_resolver())
register_resolver("arxiv_search", arxiv_search_resolver())
register_resolver("semantic_scholar", semantic_scholar_resolver())

register_strategy("direct", resolve_and_download("url_rewriter"))
register_strategy("doi", resolve_and_download("doi"))
register_strategy("arxiv_search", resolve_and_download("arxiv_search"))
register_strategy("semantic_scholar", resolve_and_download("semantic_scholar"))
register_strategy("libgen", libgen_strategy())
register_strategy("scihub", scihub_strategy())


def _build_default_strategy() -> AcquisitionStrategy:
    """Build the default acquisition chain.

    Order:
    1. Direct URL + repository-aware rewriting  (fast, free)
    2. DOI → Unpaywall open-access PDF          (legal)
    3. Arxiv API search                         (free preprints)
    4. Semantic Scholar API                     (open-access PDFs)
    5. Libgen search                            (broad, playwright)
    6. Sci-Hub via DOI                          (last resort)
    """
    return chain(
        STRATEGIES["direct"],
        STRATEGIES["doi"],
        STRATEGIES["arxiv_search"],
        STRATEGIES["semantic_scholar"],
        STRATEGIES["libgen"],
        STRATEGIES["scihub"],
    )


register_strategy("default", _build_default_strategy())


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def resolve_reference(
    ref: Reference,
    filepath: Path,
    *,
    strategy: AcquisitionStrategy | str | None = None,
) -> Optional[str]:
    """Resolve and download a single reference.

    Args:
        ref: The reference to acquire.
        filepath: Target file path for the download.
        strategy: An :class:`AcquisitionStrategy` callable, a registered
            strategy name (``str``), or ``None`` to use ``"default"``.

    Returns:
        Filepath string on success, ``None`` on failure.

    Raises:
        KeyError: If a string name is not in the registry.
    """
    if strategy is None:
        strat = STRATEGIES["default"]
    elif isinstance(strategy, str):
        strat = get_strategy(strategy)
    else:
        strat = strategy

    return strat(ref, filepath)
