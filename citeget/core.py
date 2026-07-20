"""Core search and download logic for libgen (libgen.vg-family mirrors).

Requires: playwright (with chromium browser installed).
Install browsers: ``python -m playwright install chromium``

The flow:
1. Construct search URL with query + topic
2. Load page in headless Chromium (JS-rendered table)
3. Parse results table into list of dicts
4. For each result to download:
   a. Visit /ads.php to get session key
   b. Download file from /get.php

Mirror configuration
--------------------
Libgen mirrors rotate domains often, and a mirror can also be unreachable
because the local network/DNS blocks it (e.g. resolving it to 127.0.0.1).
``search()`` therefore tries several mirrors in order and raises
:class:`MirrorUnreachableError` with an actionable message if none respond.

Override the mirror list without editing code:

- ``CITEGET_LIBGEN_MIRRORS`` — comma-separated base URLs (highest precedence)
- ``CITEGET_LIBGEN_BASE_URL`` — a single base URL
- or pass ``base_url=`` / ``mirrors=`` to ``search()`` / ``search_and_download()``

Only libgen.vg-family mirrors (JS ``#tablelibgen`` layout) are compatible with
this parser; the older libgen.is/.rs/.st forks use different HTML.
"""

import re
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


def _ts():
    """Return a bracketed timestamp string for progress messages."""
    return datetime.now().strftime("[%H:%M:%S]")


# Known libgen mirrors that share the libgen.vg-family page structure
# (JS-rendered ``#tablelibgen`` table, ``/ads.php`` -> ``/get.php`` download flow).
# The older libgen.is/.rs/.st forks use a different HTML layout and are NOT
# drop-in compatible with this parser, so they are intentionally excluded.
# Mirrors rotate domains frequently; override at runtime without editing code
# via the ``CITEGET_LIBGEN_MIRRORS`` / ``CITEGET_LIBGEN_BASE_URL`` env vars, or
# by passing ``base_url=``/``mirrors=`` to ``search()``.
DEFAULT_LIBGEN_MIRRORS = (
    "https://libgen.vg",
    "https://libgen.gs",
    "https://libgen.la",
)

# Default single base URL (first mirror). Kept for backwards compatibility with
# callers/tests that import ``BASE_URL`` directly.
BASE_URL = DEFAULT_LIBGEN_MIRRORS[0]

# Substrings that mark a browser-level "could not connect" failure, as opposed
# to a page that loaded but simply had no results. Used to decide whether to
# fail over to the next mirror.
_UNREACHABLE_MARKERS = (
    "ERR_CONNECTION_REFUSED",
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_SOCKET_NOT_CONNECTED",
    "ERR_TIMED_OUT",
    "ERR_EMPTY_RESPONSE",
    "net::ERR",
    "Timeout",
)


class MirrorUnreachableError(RuntimeError):
    """Raised when no libgen mirror could be reached.

    Distinct from an empty result set: this means every candidate mirror
    failed to connect (down, moved, or blocked by local DNS/network), so the
    caller gets an actionable message instead of a raw Playwright stack trace.
    """


def _looks_like_unreachable(exc: Exception) -> bool:
    """True if *exc* looks like a connection failure (vs. a parsing/page issue)."""
    text = str(exc)
    return any(marker in text for marker in _UNREACHABLE_MARKERS)


def _env_mirrors() -> tuple | None:
    """Read mirror overrides from the environment, or None if unset.

    ``CITEGET_LIBGEN_MIRRORS`` (comma-separated) takes precedence over
    ``CITEGET_LIBGEN_BASE_URL`` (single). Returns a normalized tuple or None.
    """
    multi = os.environ.get("CITEGET_LIBGEN_MIRRORS")
    if multi:
        mirrors = tuple(m.strip().rstrip("/") for m in multi.split(",") if m.strip())
        if mirrors:
            return mirrors
    single = os.environ.get("CITEGET_LIBGEN_BASE_URL")
    if single and single.strip():
        return (single.strip().rstrip("/"),)
    return None


def _resolve_mirrors(
    base_url: str | None = None, mirrors: tuple | list | None = None
) -> tuple:
    """Resolve the ordered list of mirror base URLs to try.

    Precedence: explicit ``mirrors`` > explicit ``base_url`` > env vars >
    ``DEFAULT_LIBGEN_MIRRORS``. This is the single source of truth for which
    mirrors ``search()`` attempts.
    """
    if mirrors:
        return tuple(m.rstrip("/") for m in mirrors)
    if base_url:
        return (base_url.rstrip("/"),)
    env = _env_mirrors()
    if env:
        return env
    return DEFAULT_LIBGEN_MIRRORS


def _format_unreachable_message(query: str, attempts: list) -> str:
    """Build an actionable error message listing the mirrors tried and why each failed."""
    tried = ", ".join(base for base, _ in attempts) or "(none)"
    lines = [
        f"Could not reach any libgen mirror for query {query!r}.",
        f"Tried: {tried}.",
        "",
        "Common causes:",
        "  - the mirror(s) are temporarily down or have moved to a new domain",
        "  - your network/DNS is blocking these domains (e.g. resolving them",
        "    to 127.0.0.1, which yields ERR_CONNECTION_REFUSED almost instantly)",
        "",
        "Fixes:",
        "  - point citeget at a working mirror without editing code:",
        "      export CITEGET_LIBGEN_MIRRORS='https://libgen.xyz,https://libgen.gs'",
        "      (or CITEGET_LIBGEN_BASE_URL for a single mirror)",
        "  - or pass base_url=/mirrors= to search()",
        "  - if a specific domain resolves to 127.0.0.1, check your DNS/VPN filter",
        "",
        "Last error per mirror:",
    ]
    for base, exc in attempts:
        first_line = str(exc).splitlines()[0] if str(exc) else repr(exc)
        lines.append(f"  {base}: {first_line}")
    return "\n".join(lines)


TOPIC_ALIASES = {
    "books": "l",
    "articles": "a",
    "fiction": "f",
    "comics": "c",
    "magazines": "m",
    "standards": "s",
    # Pass-through for raw codes
    "l": "l",
    "a": "a",
    "f": "f",
    "c": "c",
    "m": "m",
    "s": "s",
}

# Default columns and objects to search in (all of them)
_DEFAULT_COLUMNS = ["t", "a", "s", "y", "p", "i"]
_DEFAULT_OBJECTS = ["f", "e", "s", "a", "p", "w"]


def _resolve_topic(topic: str) -> str:
    """Resolve a human-friendly topic name to its single-letter code."""
    key = topic.lower().strip()
    if key not in TOPIC_ALIASES:
        valid = ", ".join(f"{k!r}" for k in TOPIC_ALIASES if len(k) > 1)
        raise ValueError(
            f"Unknown topic {topic!r}. Valid topics: {valid} "
            f"(or raw codes: l, a, f, c, m, s)"
        )
    return TOPIC_ALIASES[key]


def _build_search_url(
    query: str,
    *,
    base_url: str = BASE_URL,
    topic: str = "l",
    topics: tuple | list | None = None,
    results_per_page: int = 25,
):
    """Build the search URL for a libgen mirror.

    Args:
        query: Search terms.
        base_url: Mirror base URL (e.g. ``https://libgen.vg``).
        topic: Single topic code (used when ``topics`` is None).
        topics: Multiple topic codes to search simultaneously
            (e.g. ``("l", "f", "a")``).  Overrides ``topic``.
        results_per_page: Results per page.
    """
    from urllib.parse import quote_plus

    # Build params manually because of repeated keys (columns[], objects[])
    parts = [f"req={quote_plus(query)}"]
    for col in _DEFAULT_COLUMNS:
        parts.append(f"columns[]={col}")
    for obj in _DEFAULT_OBJECTS:
        parts.append(f"objects[]={obj}")

    if topics is not None:
        for t in topics:
            parts.append(f"topics[]={t}")
    else:
        parts.append(f"topics[]={topic}")

    parts.append(f"res={results_per_page}")
    parts.append("filesuns=all")
    return f"{base_url.rstrip('/')}/index.php?{'&'.join(parts)}"


def _parse_title_cell(cell):
    """Extract title, DOI, and series info from the compound column 0 cell."""
    links = cell.query_selector_all("a")
    title = ""
    doi = ""
    series = ""

    for link in links:
        href = link.get_attribute("href") or ""
        text = link.text_content().strip()

        if "series.php" in href:
            series = text
        elif "edition.php" in href:
            if text.startswith("DOI:"):
                doi = text[4:].strip()
            elif _is_volume_or_date(text):
                continue  # skip volume/issue/date entries
            elif text:
                if not title:  # take the first non-date, non-DOI edition link
                    title = text

    return title, doi, series


def _is_volume_or_date(text: str) -> bool:
    """Check if text is a volume/issue/date string rather than a title."""
    t = text.lower().strip()
    # "vol. X iss. Y", "vol. X", "iss. Y"
    if re.match(r"vol\.\s*\d", t):
        return True
    if re.match(r"iss\.\s*\d", t):
        return True
    # Date patterns: "2001-mar", "2001 March", etc.
    if re.match(r"\d{4}[-\s]", t):
        return True
    return False


def _parse_size(size_text: str) -> str:
    """Clean up size text (e.g., '75 kB', '2 MB')."""
    return size_text.strip()


def _parse_results_table(table) -> list:
    """Parse the #tablelibgen table into a list of result dicts."""
    rows = table.query_selector_all("tr")
    results = []

    for row in rows[1:]:  # skip header
        cells = row.query_selector_all("td")
        if len(cells) < 9:
            continue

        title, doi, series = _parse_title_cell(cells[0])
        authors = cells[1].text_content().strip()
        publisher = cells[2].text_content().strip()
        year = cells[3].text_content().strip()
        language = cells[4].text_content().strip()
        pages = cells[5].text_content().strip()
        size = _parse_size(cells[6].text_content())
        extension = cells[7].text_content().strip()

        # Extract file_id from size cell link (e.g. /file.php?id=12345)
        file_id = ""
        size_link = cells[6].query_selector("a")
        if size_link:
            size_href = size_link.get_attribute("href") or ""
            fid_match = re.search(r"id=(\d+)", size_href)
            if fid_match:
                file_id = fid_match.group(1)

        # Extract mirror links
        mirror_cell = cells[8]
        mirror_links = mirror_cell.query_selector_all("a")
        mirrors = {}
        libgen_href = ""
        for ml in mirror_links:
            name = ml.text_content().strip()
            href = ml.get_attribute("href") or ""
            mirrors[name] = href
            if not libgen_href and "/ads.php" in href:
                libgen_href = href

        # Extract md5 from the libgen mirror link
        md5 = ""
        if libgen_href:
            md5_match = re.search(r"md5=([a-fA-F0-9]{32})", libgen_href)
            if md5_match:
                md5 = md5_match.group(1)

        results.append(
            {
                "title": title,
                "authors": authors,
                "publisher": publisher,
                "year": year,
                "language": language,
                "pages": pages,
                "size": size,
                "extension": extension,
                "doi": doi,
                "series": series,
                "md5": md5,
                "file_id": file_id,
                "libgen_href": libgen_href,
                "mirrors": mirrors,
            }
        )

    return results


def _create_browser_context(playwright, *, headless=True):
    """Create a browser and context with ad blocking."""
    browser = playwright.chromium.launch(headless=headless)
    context = browser.new_context()
    # Block ad domains
    context.route("**/*inopportunefable*", lambda route: route.abort())
    return browser, context


def search(
    query: str,
    *,
    topic: str = "books",
    topics: tuple | list | None = None,
    results_per_page: int = 100,
    headless: bool = True,
    timeout: int = 20000,
    base_url: str | None = None,
    mirrors: tuple | list | None = None,
) -> list:
    """Search a libgen mirror and return a list of result dicts.

    Tries each candidate mirror in order and uses the first one that is
    reachable. If every mirror fails to connect, raises
    :class:`MirrorUnreachableError` with an actionable message rather than a
    raw browser stack trace. A mirror that loads but has no matching table is
    treated as an authoritative "no results" (returns ``[]``), not a failure.

    Args:
        query: Search terms.
        topic: What to search for — "books", "articles", "fiction", "comics",
               "magazines", or "standards".  Used when ``topics`` is None.
        topics: Multiple topics to search simultaneously, e.g.
               ``("books", "fiction", "articles")``.  Overrides ``topic``.
        results_per_page: How many results per page (25, 50, or 100).
        headless: Run browser in headless mode (default True).
        timeout: Page load timeout in ms.
        base_url: Force a single mirror (e.g. ``https://libgen.vg``). Overrides
            env vars and the default list.
        mirrors: Explicit ordered list of mirror base URLs to try. Overrides
            ``base_url``, env vars, and the default list.

    Returns:
        List of dicts with keys: title, authors, publisher, year, language,
        pages, size, extension, doi, series, md5, file_id, libgen_href,
        mirrors, and ``base_url`` (the mirror the result came from, so the
        download step can resolve the same mirror's relative links).

    Raises:
        MirrorUnreachableError: if no candidate mirror could be reached.
    """
    from playwright.sync_api import sync_playwright

    candidates = _resolve_mirrors(base_url, mirrors)

    if topics is not None:
        topic_codes = tuple(_resolve_topic(t) for t in topics)
        build_kwargs = dict(topics=topic_codes, results_per_page=results_per_page)
    else:
        topic_code = _resolve_topic(topic)
        build_kwargs = dict(topic=topic_code, results_per_page=results_per_page)

    attempts = []
    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=headless)
        try:
            page = context.new_page()
            for base in candidates:
                url = _build_search_url(query, base_url=base, **build_kwargs)
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout)
                except Exception as exc:
                    attempts.append((base, exc))
                    if _looks_like_unreachable(exc):
                        continue  # dead/blocked mirror — try the next one
                    continue  # other load errors: also move on to next mirror

                # Mirror is reachable — treat its response as authoritative.
                table = page.query_selector("#tablelibgen")
                if not table:
                    return []
                results = _parse_results_table(table)
                for r in results:
                    r["base_url"] = base
                return results

            raise MirrorUnreachableError(
                _format_unreachable_message(query, attempts)
            )
        finally:
            browser.close()


def _get_download_url(
    page, ads_url: str, *, base_url: str = BASE_URL, timeout: int = 15000
) -> Optional[str]:
    """Navigate to ads.php and extract the get.php download URL.

    Relative links are resolved against *base_url* (the mirror the result came
    from), so downloads stay on the same mirror the search succeeded on.
    """
    base = base_url.rstrip("/")
    full_url = f"{base}{ads_url}" if ads_url.startswith("/") else ads_url
    page.goto(full_url, wait_until="networkidle", timeout=timeout)

    get_link = page.query_selector('a[href*="get.php"]')
    if get_link:
        href = get_link.get_attribute("href")
        if href and not href.startswith("http"):
            href = f"{base}/{href.lstrip('/')}"
        return href
    return None


def _sanitize_filename(name: str, max_length: int = 200) -> str:
    """Make a string safe for use as a filename."""
    # Remove or replace problematic characters
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_length:
        name = name[:max_length]
    return name


def _apa7_authors(authors_str: str) -> str:
    """Format authors in APA 7 citation style (surnames only).

    Expects semicolon-separated or comma-separated author names from libgen.
    1 author  -> "Smith"
    2 authors -> "Smith & Jones"
    3+ authors -> "Smith et al."
    """
    if not authors_str:
        return "Unknown"

    # Split on semicolons (libgen format) or " and "
    parts = re.split(r"\s*;\s*|\s+and\s+", authors_str)
    surnames = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # Take last word that's not an initial
        tokens = part.split()
        real = [t for t in tokens if len(t.rstrip(".")) > 1]
        if real:
            surnames.append(real[-1])
        elif tokens:
            surnames.append(tokens[-1])

    if len(surnames) == 0:
        return "Unknown"
    elif len(surnames) == 1:
        return surnames[0]
    elif len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}"
    else:
        return f"{surnames[0]} et al."


def _make_filename(result: dict) -> str:
    """Generate a filename from result metadata.

    Format: ``{title} ({authors_apa7}, {year}).{ext}``
    """
    title = result.get("title", "")[:120] or result.get("md5", "unknown")
    apa = _apa7_authors(result.get("authors", ""))

    year = ""
    if result.get("year"):
        year_match = re.match(r"(\d{4})", result["year"])
        if year_match:
            year = year_match.group(1)

    if year:
        name = f"{title} ({apa}, {year})"
    else:
        name = f"{title} ({apa})"

    ext = result.get("extension", "pdf")
    return _sanitize_filename(name) + f".{ext}"


def _try_libgen_download(
    pg,
    ads_url: str,
    filepath: Path,
    *,
    base_url: str = BASE_URL,
    timeout: int,
    delay: float,
):
    """Try the primary libgen download path: ads.php -> get.php.

    Returns filepath on success, raises on failure with a descriptive message.
    Relative links are resolved against *base_url* (the result's mirror).
    """
    if delay:
        time.sleep(delay)

    get_url = _get_download_url(pg, ads_url, base_url=base_url, timeout=timeout)
    if not get_url:
        raise RuntimeError("No get.php link found on ads.php page")

    try:
        with pg.expect_download(timeout=timeout) as download_info:
            pg.goto(get_url, timeout=timeout)
        download = download_info.value
        download.save_as(str(filepath))
        if filepath.exists() and filepath.stat().st_size > 1000:
            return str(filepath)
        raise RuntimeError(
            f"Downloaded file too small ({filepath.stat().st_size} bytes)"
        )
    except RuntimeError:
        raise
    except Exception as exc:
        # Fallback: try direct request via page context
        try:
            response = pg.request.get(get_url, timeout=timeout)
            if response.ok and len(response.body()) > 1000:
                filepath.write_bytes(response.body())
                return str(filepath)
        except Exception:
            pass
        raise RuntimeError(f"Playwright download failed: {exc}")


def _try_mirror_download(url: str, filepath: Path, *, timeout: int = 30):
    """Try downloading from an external mirror URL via HTTP.

    Works for mirrors that serve the file directly or via a simple
    intermediate page (e.g. Anna's Archive, library.lol).
    Returns filepath on success, raises on failure.
    """
    import requests

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} from {url}")

    content_type = resp.headers.get("Content-Type", "")
    body = resp.content

    # If it's a PDF/epub/etc, save directly
    if b"%PDF" in body[:20] or "pdf" in content_type.lower() or len(body) > 100_000:
        if len(body) < 1000:
            raise RuntimeError(f"Response too small ({len(body)} bytes)")
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_bytes(body)
        return str(filepath)

    raise RuntimeError(f"Response doesn't look like a file (type={content_type})")


def download_one(
    result: dict,
    *,
    download_dir: str = ".",
    page=None,
    timeout: int = 60000,
    delay: float = 1.0,
    try_mirrors: bool = True,
    verbose: bool = False,
) -> Optional[str]:
    """Download a single result. Returns the saved file path, or None on failure.

    Tries the primary libgen download path (ads.php -> get.php) first.
    If that fails and ``try_mirrors`` is True, attempts external mirrors
    (Anna's Archive, library.lol, etc.).

    If ``page`` is provided (a Playwright Page object), reuse it.
    Otherwise, creates a new browser session (slower but standalone).

    Args:
        result: A result dict from ``search()``.
        download_dir: Where to save the file.
        page: Optional Playwright page to reuse.
        timeout: Download timeout in ms.
        delay: Seconds to wait between page loads (rate limiting).
        try_mirrors: Try external mirror URLs on primary failure.
        verbose: Print diagnostic info on failures.

    Returns:
        Path to the downloaded file, or None if download failed.
    """
    from playwright.sync_api import sync_playwright

    libgen_href = result.get("libgen_href", "")
    mirrors = result.get("mirrors", {})
    base_url = result.get("base_url") or BASE_URL
    if not libgen_href and not mirrors:
        return None

    download_dir = Path(download_dir).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = _make_filename(result)
    filepath = download_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        return str(filepath)

    errors = []

    def _do_download(pg):
        # 1. Try primary libgen path
        if libgen_href:
            try:
                return _try_libgen_download(
                    pg,
                    libgen_href,
                    filepath,
                    base_url=base_url,
                    timeout=timeout,
                    delay=delay,
                )
            except Exception as exc:
                errors.append(f"libgen primary: {exc}")
                if verbose:
                    print(f"    download_one: primary failed: {exc}")

        # 2. Try external mirrors via HTTP (no browser needed)
        if try_mirrors:
            for name, url in mirrors.items():
                if not url or "/ads.php" in url:
                    continue  # skip the primary libgen mirror (already tried)
                try:
                    result_path = _try_mirror_download(
                        url,
                        filepath,
                        timeout=timeout // 1000,
                    )
                    if result_path:
                        if verbose:
                            print(f"    download_one: succeeded via mirror {name!r}")
                        return result_path
                except Exception as exc:
                    errors.append(f"mirror {name}: {exc}")
                    if verbose:
                        print(f"    download_one: mirror {name!r} failed: {exc}")

        if verbose and errors:
            print(f"    download_one: all attempts failed: {errors}")
        return None

    if page is not None:
        return _do_download(page)

    # Standalone mode: create browser
    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=True)
        try:
            pg = context.new_page()
            return _do_download(pg)
        finally:
            browser.close()


def download_results(
    results: list,
    *,
    download_dir: str = ".",
    max_downloads: int = 0,
    delay: float = 2.0,
    headless: bool = True,
    timeout: int = 60000,
    verbose: bool = True,
) -> list:
    """Download multiple results. Returns list of (result, filepath) tuples.

    Args:
        results: List of result dicts from ``search()``.
        download_dir: Where to save files.
        max_downloads: Max number to download (0 = all).
        delay: Seconds between downloads (rate limiting).
        headless: Run browser in headless mode.
        timeout: Per-download timeout in ms.
        verbose: Print progress.

    Returns:
        List of (result_dict, filepath_or_None) tuples.
    """
    from playwright.sync_api import sync_playwright

    to_download = results[:max_downloads] if max_downloads > 0 else results
    downloaded = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=headless)
        try:
            page = context.new_page()
            for i, result in enumerate(to_download):
                if verbose:
                    title = result.get("title", "?")[:60]
                    print(f"{_ts()} [{i + 1}/{len(to_download)}] {title}...")

                filepath = download_one(
                    result,
                    download_dir=download_dir,
                    page=page,
                    timeout=timeout,
                    delay=delay,
                )
                downloaded.append((result, filepath))

                if verbose:
                    if filepath:
                        size = Path(filepath).stat().st_size
                        print(f"  {_ts()} -> saved ({size:,} bytes)")
                    else:
                        print(f"  {_ts()} -> FAILED")
        finally:
            browser.close()

    return downloaded


def search_and_download(
    query: str,
    *,
    topic: str = "books",
    download_dir: str = ".",
    max_downloads: int = 5,
    results_per_page: int = 100,
    delay: float = 2.0,
    headless: bool = True,
    timeout: int = 30000,
    verbose: bool = True,
    base_url: str | None = None,
    mirrors: tuple | list | None = None,
) -> list:
    """Search libgen and download matching results in one shot.

    This is the main convenience function. It runs the search, then downloads
    up to ``max_downloads`` results into ``download_dir``.

    Args:
        query: Search terms.
        topic: "books", "articles", "fiction", etc.
        download_dir: Where to save files.
        max_downloads: Max number to download (default 5, 0 = all).
        results_per_page: Results per search page.
        delay: Seconds between downloads.
        headless: Headless browser mode.
        timeout: Timeout in ms for page loads.
        verbose: Print progress.
        base_url: Force a single mirror. Overrides env vars and the default list.
        mirrors: Explicit ordered list of mirror base URLs to try.

    Returns:
        List of (result_dict, filepath_or_None) tuples.

    Raises:
        MirrorUnreachableError: if no candidate mirror could be reached.
    """
    if verbose:
        print(f"{_ts()} Searching libgen for: {query!r} (topic={topic})...")

    results = search(
        query,
        topic=topic,
        results_per_page=results_per_page,
        headless=headless,
        timeout=timeout,
        base_url=base_url,
        mirrors=mirrors,
    )

    if verbose:
        print(f"{_ts()} Found {len(results)} results.")

    if not results:
        return []

    if verbose and max_downloads > 0:
        print(f"{_ts()} Downloading up to {max_downloads}...")

    return download_results(
        results,
        download_dir=download_dir,
        max_downloads=max_downloads,
        delay=delay,
        headless=headless,
        timeout=timeout,
        verbose=verbose,
    )
