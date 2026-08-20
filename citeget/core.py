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

from citeget.names import apa7_authors, surnames
from citeget.rank import dedupe_results, parse_size, rank_results
from citeget.validate import (
    BOOK_POLICY,
    DEFAULT_POLICY,
    ValidationPolicy,
    validate_bytes,
    validate_download,
)


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
    "https://libgen.la",
    "https://libgen.li",
    "https://libgen.bz",
    "https://libgen.gl",
)

# Page-load defaults. Libgen result pages are ad-heavy and JS-rendered, so a
# tight timeout fails on mirrors that are perfectly healthy, just slow.
DEFAULT_SEARCH_TIMEOUT = 45000
# Once the DOM is ready the table is rendered by JS almost immediately, so this
# window can be much shorter than the navigation timeout. It also bounds how
# long a genuinely empty result set takes to report.
DEFAULT_TABLE_TIMEOUT = 20000
DEFAULT_ATTEMPTS_PER_MIRROR = 2
DEFAULT_RETRY_BACKOFF = 2.0
RESULTS_TABLE_SELECTOR = "#tablelibgen"

# Default single base URL (first mirror). Kept for backwards compatibility with
# callers/tests that import ``BASE_URL`` directly.
BASE_URL = DEFAULT_LIBGEN_MIRRORS[0]

# Failures where the mirror never answered at all: a domain that no longer
# exists, a refused connection, no route. Retrying these is pointless — the
# right move is to fail over to the next mirror immediately.
_HARD_UNREACHABLE_MARKERS = (
    "ERR_NAME_NOT_RESOLVED",
    "ERR_CONNECTION_REFUSED",
    "ERR_ADDRESS_UNREACHABLE",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_CERT_",
)

# Failures where the mirror did answer, or might have, but the page did not
# finish in time. A healthy mirror under load produces these, so they are worth
# retrying before writing the mirror off.
_TRANSIENT_MARKERS = (
    "Timeout",
    "ERR_TIMED_OUT",
    "ERR_CONNECTION_TIMED_OUT",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_EMPTY_RESPONSE",
    "ERR_SOCKET_NOT_CONNECTED",
    "chrome-error://",
    "interrupted by another navigation",
)

# Substrings that mark a browser-level "could not connect" failure, as opposed
# to a page that loaded but simply had no results. Used to decide whether to
# fail over to the next mirror.
_UNREACHABLE_MARKERS = _HARD_UNREACHABLE_MARKERS + _TRANSIENT_MARKERS + ("net::ERR",)


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


def _is_hard_unreachable(exc: Exception) -> bool:
    """True if *exc* means the mirror is dead or blocked, so retrying is futile.

    Distinguished from a timeout, which a healthy-but-loaded mirror produces and
    which a retry usually clears.
    """
    text = str(exc)
    return any(marker in text for marker in _HARD_UNREACHABLE_MARKERS)


def _looks_like_transient(exc: Exception) -> bool:
    """True if *exc* is a slow or interrupted load worth retrying."""
    text = str(exc)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


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
    """Build an actionable error message listing the mirrors tried and why each failed.

    The advice depends on *how* the mirrors failed: a refused connection or a
    failed DNS lookup points at the mirror list or a local network filter, while
    a timeout points at pages that are merely slow. Telling someone to check
    their DNS when the real fix is a longer timeout sends them down a dead end.
    """
    tried = ", ".join(base for base, _ in attempts) or "(none)"
    any_hard = any(_is_hard_unreachable(exc) for _, exc in attempts)
    any_timeout = any(
        _looks_like_transient(exc) and not _is_hard_unreachable(exc)
        for _, exc in attempts
    )

    lines = [
        f"Could not reach any libgen mirror for query {query!r}.",
        f"Tried: {tried}.",
        "",
    ]

    if any_hard and not any_timeout:
        lines += [
            "Diagnosis: every mirror refused the connection or failed to resolve,",
            "so nothing answered at all.",
        ]
    elif any_timeout and not any_hard:
        lines += [
            "Diagnosis: the mirrors responded but their pages did not finish",
            "loading in time — they are reachable, just slow.",
        ]
    else:
        lines += [
            "Diagnosis: some mirrors did not answer at all and others were too",
            "slow to finish loading.",
        ]

    lines += ["", "Common causes:"]
    if any_hard:
        lines += [
            "  - the mirror(s) are temporarily down or have moved to a new domain",
            "  - your network/DNS is blocking these domains (e.g. resolving them",
            "    to 127.0.0.1, which yields ERR_CONNECTION_REFUSED almost instantly)",
        ]
    if any_timeout:
        lines += [
            "  - libgen pages are ad-heavy and JS-rendered; under load they can",
            "    take longer than the current timeout allows",
        ]

    lines += ["", "Fixes:"]
    if any_timeout:
        lines += [
            f"  - raise the timeout (current default {DEFAULT_SEARCH_TIMEOUT}ms):",
            "      search(query, timeout=90000)",
            "  - or allow more attempts per mirror:",
            "      search(query, attempts_per_mirror=4)",
        ]
    lines += [
        "  - point citeget at a working mirror without editing code:",
        "      export CITEGET_LIBGEN_MIRRORS='https://libgen.la,https://libgen.li'",
        "      (or CITEGET_LIBGEN_BASE_URL for a single mirror)",
        "  - or pass base_url=/mirrors= to search()",
        "  - run 'citeget check-mirrors' to see which mirrors are healthy today",
    ]
    if any_hard:
        lines += [
            "  - if a specific domain resolves to 127.0.0.1, check your DNS/VPN filter",
        ]

    lines += ["", "Last error per mirror:"]
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


def _load_results_table(page, url: str, *, timeout: int, table_timeout: int):
    """Load *url* and return the results table element, or None if there is none.

    Waits for the table itself rather than for network idle. Libgen result pages
    carry polling ad traffic that can keep the network busy indefinitely, so
    ``wait_until="networkidle"`` times out on pages that have been fully usable
    for seconds. The table is the only thing we actually need.

    Raises whatever Playwright raises if the navigation itself fails; a missing
    table is reported as None, not as an error, because a mirror that answered
    is authoritative about having no results.
    """
    page.goto(url, wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_selector(
            RESULTS_TABLE_SELECTOR, timeout=table_timeout, state="attached"
        )
    except Exception:
        pass  # no table within the window — resolved as "no results" below
    return page.query_selector(RESULTS_TABLE_SELECTOR)


def _load_with_retries(
    page,
    url: str,
    *,
    timeout: int,
    table_timeout: int,
    attempts: int,
    backoff: float,
):
    """Load *url*, retrying transient failures. Returns ``(table, exception)``.

    Exactly one of the pair is meaningful: on success ``exception`` is None (and
    ``table`` may still be None, meaning the page loaded with no results); on
    failure ``table`` is None and ``exception`` is the last error seen.

    A hard connection failure is never retried — a domain that does not resolve
    will not start resolving two seconds later — but a timeout is, since that is
    what a healthy mirror under load produces.
    """
    last_exc = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            table = _load_results_table(
                page, url, timeout=timeout, table_timeout=table_timeout
            )
            return table, None
        except Exception as exc:
            last_exc = exc
            if _is_hard_unreachable(exc) or attempt >= attempts:
                break
            time.sleep(backoff * attempt)
    return None, last_exc


def search(
    query: str,
    *,
    topic: str = "books",
    topics: tuple | list | None = None,
    results_per_page: int = 100,
    headless: bool = True,
    timeout: int = DEFAULT_SEARCH_TIMEOUT,
    table_timeout: int = DEFAULT_TABLE_TIMEOUT,
    attempts_per_mirror: int = DEFAULT_ATTEMPTS_PER_MIRROR,
    retry_backoff: float = DEFAULT_RETRY_BACKOFF,
    base_url: str | None = None,
    mirrors: tuple | list | None = None,
) -> list:
    """Search a libgen mirror and return a list of result dicts.

    Tries each candidate mirror in order and uses the first one that is
    reachable, retrying a mirror that merely timed out before moving on. If
    every mirror fails, raises :class:`MirrorUnreachableError` with a message
    that says which failure mode it was, rather than a raw browser stack trace.
    A mirror that loads but has no matching table is treated as an authoritative
    "no results" (returns ``[]``), not a failure.

    Args:
        query: Search terms.
        topic: What to search for — "books", "articles", "fiction", "comics",
               "magazines", or "standards".  Used when ``topics`` is None.
        topics: Multiple topics to search simultaneously, e.g.
               ``("books", "fiction", "articles")``.  Overrides ``topic``.
        results_per_page: How many results per page (25, 50, or 100).
        headless: Run browser in headless mode (default True).
        timeout: Page navigation timeout in ms.
        table_timeout: How long to wait, after the DOM is ready, for the results
            table to be rendered. Also bounds how long an empty result set takes
            to report.
        attempts_per_mirror: How many times to try a mirror whose page timed out
            before failing over to the next one. Hard connection failures are
            never retried.
        retry_backoff: Seconds to wait before a retry, multiplied by the attempt
            number.
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
                table, exc = _load_with_retries(
                    page,
                    url,
                    timeout=timeout,
                    table_timeout=table_timeout,
                    attempts=attempts_per_mirror,
                    backoff=retry_backoff,
                )
                if exc is not None:
                    attempts.append((base, exc))
                    continue  # unreachable or persistently slow — next mirror

                # Mirror is reachable — treat its response as authoritative.
                if table is None:
                    return []
                results = _parse_results_table(table)
                for r in results:
                    r["base_url"] = base
                return results

            raise MirrorUnreachableError(_format_unreachable_message(query, attempts))
        finally:
            browser.close()


# The download link on an ads.php page. Waiting for this specific element is
# both faster and more reliable than waiting for the whole ad-heavy page.
DOWNLOAD_LINK_SELECTOR = 'a[href*="get.php"]'


def _get_download_url(
    page,
    ads_url: str,
    *,
    base_url: str = BASE_URL,
    timeout: int = 15000,
    link_timeout: int = DEFAULT_TABLE_TIMEOUT,
) -> Optional[str]:
    """Navigate to ads.php and extract the get.php download URL.

    Relative links are resolved against *base_url* (the mirror the result came
    from), so downloads stay on the same mirror the search succeeded on.

    Like the search page, ads.php is ad-heavy and may never reach network idle,
    so this waits for the download link itself rather than for the page to go
    quiet — otherwise every candidate costs the full timeout even when the link
    was there immediately.
    """
    base = base_url.rstrip("/")
    full_url = f"{base}{ads_url}" if ads_url.startswith("/") else ads_url
    page.goto(full_url, wait_until="domcontentloaded", timeout=timeout)
    try:
        page.wait_for_selector(
            DOWNLOAD_LINK_SELECTOR, timeout=link_timeout, state="attached"
        )
    except Exception:
        pass  # no link within the window — reported as None below

    get_link = page.query_selector(DOWNLOAD_LINK_SELECTOR)
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
    """Format libgen authors in APA 7 citation style (surnames only).

    Thin wrapper over :func:`citeget.names.apa7_authors`, which is the single
    source of truth for author parsing. Getting this right matters beyond
    cosmetics: :func:`_make_filename` builds the filename from it, and
    ``check_existing_downloads`` keys idempotency off those filenames.

    >>> _apa7_authors("Moore, Geoffrey A.")
    'Moore'
    >>> _apa7_authors("Chris Voss & Tahl Raz")
    'Voss & Raz'
    """
    return apa7_authors(authors_str)


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


def _temp_path(filepath: Path) -> Path:
    """Where to download before validating, alongside the eventual file."""
    return filepath.with_name(f".{filepath.name}.part")


def _first_line(exc) -> str:
    """First line of an exception's message — Playwright's call logs are long."""
    text = str(exc)
    return text.splitlines()[0] if text else repr(exc)


def _is_download_started(exc) -> bool:
    """True for Playwright's "Download is starting" navigation error.

    Serving a file as an attachment makes ``page.goto()`` raise this. It is
    documented, expected behaviour rather than a failure — the download is in
    flight and ``expect_download`` will hand it over.
    """
    return "Download is starting" in str(exc)


def _finalize_download(
    tmp_path: Path,
    filepath: Path,
    *,
    extension: Optional[str] = None,
    expected_bytes: Optional[int] = None,
    policy: ValidationPolicy = DEFAULT_POLICY,
    validate: bool = True,
) -> str:
    """Validate the bytes at *tmp_path* and move them into place.

    Downloading to a temporary path and only moving on success is what stops a
    failed attempt from leaving a stub where the real file belongs — a stub that
    a later run would otherwise read back as a cached success.

    Raises :class:`citeget.validate.InvalidDownloadError` if the file does not
    validate, having first removed it.
    """
    try:
        if validate:
            validate_download(
                tmp_path,
                extension=extension,
                expected_bytes=expected_bytes,
                policy=policy,
            ).raise_if_invalid()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        os.replace(tmp_path, filepath)
        return str(filepath)
    finally:
        # Only still present when validation rejected it; os.replace consumed it
        # on the success path.
        if tmp_path.exists():
            tmp_path.unlink()


def _fetch_via_page_request(pg, url: str, tmp_path: Path, *, timeout: int) -> bool:
    """Fetch *url* through the page's request context. True if bytes landed."""
    try:
        response = pg.request.get(url, timeout=timeout)
        if not response.ok:
            return False
        body = response.body()
        if not body:
            return False
        tmp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_bytes(body)
        return True
    except Exception:
        return False


def _try_libgen_download(
    pg,
    ads_url: str,
    filepath: Path,
    *,
    base_url: str = BASE_URL,
    timeout: int,
    delay: float,
    extension: Optional[str] = None,
    expected_bytes: Optional[int] = None,
    policy: ValidationPolicy = DEFAULT_POLICY,
    validate: bool = True,
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

    tmp_path = _temp_path(filepath)
    goto_error = None
    try:
        with pg.expect_download(timeout=timeout) as download_info:
            try:
                pg.goto(get_url, timeout=timeout)
            except Exception as exc:
                # When libgen serves the file as an attachment, goto raises
                # "Download is starting". Swallowing it here — inside the
                # expect_download block — is the whole point: letting it escape
                # would discard a download that is already succeeding.
                goto_error = exc
        download = download_info.value
        download.save_as(str(tmp_path))
    except Exception as exc:
        # No download materialised. Refetching get.php only helps if the request
        # never reached libgen: the ``key`` is single-use, so once the transfer
        # has started a retry gets an HTML error page, not the file.
        if goto_error is None or not _is_download_started(goto_error):
            if _fetch_via_page_request(pg, get_url, tmp_path, timeout=timeout):
                return _finalize_download(
                    tmp_path,
                    filepath,
                    extension=extension,
                    expected_bytes=expected_bytes,
                    policy=policy,
                    validate=validate,
                )
        if tmp_path.exists():
            tmp_path.unlink()
        raise RuntimeError(f"Playwright download failed: {_first_line(exc)}")

    return _finalize_download(
        tmp_path,
        filepath,
        extension=extension,
        expected_bytes=expected_bytes,
        policy=policy,
        validate=validate,
    )


def _try_mirror_download(
    url: str,
    filepath: Path,
    *,
    timeout: int = 30,
    extension: Optional[str] = None,
    expected_bytes: Optional[int] = None,
    policy: ValidationPolicy = DEFAULT_POLICY,
    validate: bool = True,
):
    """Try downloading from an external mirror URL via HTTP.

    Works for mirrors that serve the file directly or via a simple
    intermediate page (e.g. Anna's Archive, library.lol).
    Returns filepath on success, raises on failure.

    The response body is validated before anything is written, so a captcha
    wall, a Cloudflare interstitial, or any other HTML page is rejected instead
    of being saved under a book's name.

    Args:
        url: The mirror URL to fetch.
        filepath: Where to save the file on success.
        timeout: HTTP timeout in seconds.
        extension: Expected file extension; defaults to ``filepath``'s suffix.
        expected_bytes: Size the search result advertised, for the truncation check.
        policy: Validation policy (see :mod:`citeget.validate`).
        validate: Set False to accept whatever the mirror returns.
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

    body = resp.content

    if validate:
        verdict = validate_bytes(
            body,
            extension=extension or filepath.suffix.lstrip("."),
            expected_bytes=expected_bytes,
            policy=policy,
        )
        if not verdict:
            raise RuntimeError(f"{url} did not return the file: {verdict.reason}")

    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _temp_path(filepath)
    tmp_path.write_bytes(body)
    os.replace(tmp_path, filepath)
    return str(filepath)


def download_one(
    result: dict,
    *,
    download_dir: str = ".",
    page=None,
    timeout: int = 60000,
    delay: float = 1.0,
    try_mirrors: bool = True,
    verbose: bool = False,
    validate: bool = True,
    policy: Optional[ValidationPolicy] = None,
) -> Optional[str]:
    """Download a single result. Returns the saved file path, or None on failure.

    Tries the primary libgen download path (ads.php -> get.php) first.
    If that fails and ``try_mirrors`` is True, attempts external mirrors
    (Anna's Archive, library.lol, etc.).

    Every path that can return a file routes through
    :mod:`citeget.validate` first, so an HTML page or a truncated transfer is
    reported as a failure rather than saved under the book's name. An existing
    file is re-validated before being accepted as a cached success, so a stub
    left by an earlier failure cannot make that failure permanent.

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
        validate: Check that what arrived is really the requested file.
        policy: Validation policy; defaults to
            :data:`citeget.validate.DEFAULT_POLICY`. Pass
            :data:`citeget.validate.BOOK_POLICY` when the download should be a
            complete book, to also reject excerpts and front-matter samples.

    Returns:
        Path to the downloaded file, or None if download failed.
    """
    from playwright.sync_api import sync_playwright

    libgen_href = result.get("libgen_href", "")
    mirrors = result.get("mirrors", {})
    base_url = result.get("base_url") or BASE_URL
    if not libgen_href and not mirrors:
        return None

    policy = policy or DEFAULT_POLICY
    extension = (result.get("extension") or "").lower() or None
    expected_bytes = parse_size(result.get("size")) or None

    download_dir = Path(download_dir).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = _make_filename(result)
    filepath = download_dir / filename

    # An existing file counts as a cached success only if it still validates.
    # A previous failed attempt could have left a stub here, and returning that
    # would make one bad download permanent.
    if filepath.exists() and filepath.stat().st_size > 0:
        if not validate:
            return str(filepath)
        verdict = validate_download(
            filepath,
            extension=extension,
            expected_bytes=expected_bytes,
            policy=policy,
        )
        if verdict:
            return str(filepath)
        if verbose:
            print(
                "    download_one: discarding unusable cached file "
                f"({verdict.reason})"
            )
        filepath.unlink()

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
                    extension=extension,
                    expected_bytes=expected_bytes,
                    policy=policy,
                    validate=validate,
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
                        extension=extension,
                        expected_bytes=expected_bytes,
                        policy=policy,
                        validate=validate,
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
    distinct: bool = True,
    validate: bool = True,
    policy: Optional[ValidationPolicy] = None,
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
        distinct: Collapse rows that are the same work in different file
            formats, so ``max_downloads=5`` means five different works rather
            than five copies of one. Set False for the raw result order.
        validate: Check that each download really is the requested file.
        policy: Validation policy (see :mod:`citeget.validate`).

    Returns:
        List of (result_dict, filepath_or_None) tuples.
    """
    from playwright.sync_api import sync_playwright

    if distinct:
        results = dedupe_results(results)
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
                    verbose=verbose,
                    validate=validate,
                    policy=policy,
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
    distinct: bool = True,
    validate: bool = True,
    policy: Optional[ValidationPolicy] = None,
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
        distinct: Count distinct works rather than file formats towards
            ``max_downloads``. Libgen lists one edition once per format, so
            without this ``max_downloads=5`` returns five copies of one book.
        validate: Check that each download really is the requested file.
        policy: Validation policy (see :mod:`citeget.validate`).
        base_url: Force a single mirror. Overrides env vars and the default list.
        mirrors: Explicit ordered list of mirror base URLs to try.

    To acquire one copy of a *specific* book rather than the top N rows, use
    :func:`get_book`, which ranks results against the title and author you
    asked for.

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
        distinct=distinct,
        validate=validate,
        policy=policy,
    )


def download_best(
    results: list,
    *,
    title: str,
    authors: str | None = None,
    download_dir: str = ".",
    max_candidates: int = 5,
    page=None,
    timeout: int = 60000,
    delay: float = 1.0,
    headless: bool = True,
    try_mirrors: bool = True,
    verbose: bool = False,
    validate: bool = True,
    policy: Optional[ValidationPolicy] = None,
    **rank_kwargs,
) -> Optional[str]:
    """Download the best match for a specific title, falling through on failure.

    Ranks *results* against the title and author actually wanted (see
    :mod:`citeget.rank`) and downloads them in that order until one validates.
    Falling through matters as much as ranking does: libgen catalogues excerpts,
    front-matter samples and reviews under the full work's title, and the next
    candidate is usually the real thing.

    Candidates are deliberately *not* deduplicated by format here — when the PDF
    of a work turns out to be an excerpt, its EPUB often is not.

    Args:
        results: Result dicts from :func:`search`.
        title: The title actually wanted.
        authors: The author(s) wanted, if known — a strong disambiguating signal.
        download_dir: Where to save the file.
        max_candidates: How many ranked candidates to try before giving up.
        page: Optional Playwright page to reuse.
        timeout: Per-download timeout in ms.
        delay: Seconds between page loads (rate limiting).
        headless: Headless browser mode (ignored when ``page`` is given).
        try_mirrors: Try external mirror URLs when the primary path fails.
        verbose: Print progress and the reason each candidate was rejected.
        validate: Check that what arrived is really the requested file.
        policy: Validation policy; defaults to
            :data:`citeget.validate.BOOK_POLICY`, which also rejects excerpts.
        **rank_kwargs: Forwarded to :func:`citeget.rank.score_result`
            (``format_preference``, ``language``, ``weights``, ``size_bounds``,
            ``decoy_pattern``).

    Returns:
        Path to the downloaded file, or None if no candidate produced one.
    """
    from playwright.sync_api import sync_playwright

    if not results:
        return None

    policy = policy or BOOK_POLICY
    ranked = rank_results(results, title=title, authors=authors, **rank_kwargs)

    def _walk(pg):
        for position, scored in enumerate(ranked[:max_candidates], 1):
            if verbose:
                print(
                    f"{_ts()}   candidate {position}"
                    f"/{min(max_candidates, len(ranked))}: [{scored.extension}] "
                    f"{scored.title[:70]} (score {scored.score:.2f})"
                )
            path = download_one(
                scored.result,
                download_dir=download_dir,
                page=pg,
                timeout=timeout,
                delay=delay,
                try_mirrors=try_mirrors,
                verbose=verbose,
                validate=validate,
                policy=policy,
            )
            if path:
                return path
        return None

    if page is not None:
        return _walk(page)

    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=headless)
        try:
            return _walk(context.new_page())
        finally:
            browser.close()


def get_book(
    title: str,
    *,
    authors: str | None = None,
    download_dir: str = ".",
    query: str | None = None,
    topic: str = "books",
    max_candidates: int = 5,
    results_per_page: int = 50,
    headless: bool = True,
    timeout: int = DEFAULT_SEARCH_TIMEOUT,
    delay: float = 1.0,
    verbose: bool = True,
    validate: bool = True,
    policy: Optional[ValidationPolicy] = None,
    base_url: str | None = None,
    mirrors: tuple | list | None = None,
    **rank_kwargs,
) -> Optional[str]:
    """Acquire one copy of a specific book. The "get me *this* book" entry point.

    Searches, ranks the results against *title* and *authors*, and downloads the
    best candidate that validates as a complete book — as opposed to
    :func:`search_and_download`, which takes libgen's own ordering.

    Simple case::

        from citeget import get_book

        path = get_book("Crossing the Chasm", authors="Geoffrey A. Moore",
                        download_dir="~/books")

    Args:
        title: The book's title.
        authors: The author(s), if known. Strongly improves matching, since
            libgen titles alone are noisy.
        download_dir: Where to save the file.
        query: Override the search string sent to libgen. Defaults to the title
            plus the first author's surname.
        topic: Libgen topic to search ("books", "fiction", "articles", ...).
        max_candidates: How many ranked candidates to try before giving up.
        results_per_page: How many results to fetch to rank.
        headless: Headless browser mode.
        timeout: Page load timeout in ms.
        delay: Seconds between page loads (rate limiting).
        verbose: Print progress.
        validate: Check that what arrived is really the requested book.
        policy: Validation policy; defaults to
            :data:`citeget.validate.BOOK_POLICY`.
        base_url: Force a single mirror.
        mirrors: Explicit ordered list of mirror base URLs to try.
        **rank_kwargs: Forwarded to :func:`citeget.rank.score_result`.

    Returns:
        Path to the downloaded file, or None if nothing usable was found.

    Raises:
        MirrorUnreachableError: if no candidate mirror could be reached.
    """
    if query is None:
        surname = next(iter(surnames(authors or "")), "")
        query = f"{title} {surname}".strip()

    if verbose:
        print(f"{_ts()} Searching libgen for {query!r}...")

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
        print(f"{_ts()} Found {len(results)} results; ranking against {title!r}.")

    if not results:
        return None

    return download_best(
        results,
        title=title,
        authors=authors,
        download_dir=download_dir,
        max_candidates=max_candidates,
        timeout=max(timeout, 60000),
        delay=delay,
        headless=headless,
        verbose=verbose,
        validate=validate,
        policy=policy,
        **rank_kwargs,
    )


def check_mirrors(
    *,
    mirrors: tuple | list | None = None,
    query: str = "design of everyday things",
    topic: str = "books",
    timeout: int = DEFAULT_SEARCH_TIMEOUT,
    table_timeout: int = DEFAULT_TABLE_TIMEOUT,
    headless: bool = True,
    verbose: bool = False,
) -> list:
    """Probe each configured mirror and report which ones are healthy.

    Mirror domains rotate, so the default list goes stale on its own schedule.
    This turns the resulting "citeget is broken" into the actionable "your
    mirror list needs updating", and gives you the working list to pass to
    ``CITEGET_LIBGEN_MIRRORS``.

    Args:
        mirrors: Mirrors to probe; defaults to the configured list.
        query: Search terms to probe with. Should be something with results.
        topic: Libgen topic to search.
        timeout: Page navigation timeout in ms.
        table_timeout: How long to wait for the results table, in ms.
        headless: Headless browser mode.
        verbose: Print each result as it is probed.

    Returns:
        One dict per mirror with keys ``mirror``, ``ok``, ``results``,
        ``elapsed_ms`` and ``error``, in the order probed.
    """
    from playwright.sync_api import sync_playwright

    candidates = _resolve_mirrors(mirrors=mirrors)
    topic_code = _resolve_topic(topic)
    reports = []

    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=headless)
        try:
            page = context.new_page()
            for base in candidates:
                url = _build_search_url(query, base_url=base, topic=topic_code)
                started = time.monotonic()
                try:
                    table = _load_results_table(
                        page, url, timeout=timeout, table_timeout=table_timeout
                    )
                    count = len(_parse_results_table(table)) if table else 0
                    report = {
                        "mirror": base,
                        "ok": table is not None,
                        "results": count,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "error": "" if table is not None else "no results table",
                    }
                except Exception as exc:
                    report = {
                        "mirror": base,
                        "ok": False,
                        "results": 0,
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                        "error": _first_line(exc),
                    }
                reports.append(report)
                if verbose:
                    status = "OK" if report["ok"] else "FAIL"
                    elapsed = report["elapsed_ms"]
                    print(f"  {status:4s} {base} ({elapsed}ms) {report['error']}")
        finally:
            browser.close()

    return reports
