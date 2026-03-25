"""Core search and download logic for libgen.vg.

Requires: playwright (with chromium browser installed).
Install browsers: ``python -m playwright install chromium``

The flow:
1. Construct search URL with query + topic
2. Load page in headless Chromium (JS-rendered table)
3. Parse results table into list of dicts
4. For each result to download:
   a. Visit /ads.php to get session key
   b. Download file from /get.php
"""

import re
import os
import time
from pathlib import Path
from typing import Optional

BASE_URL = "https://libgen.vg"

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
    topic: str = "l",
    results_per_page: int = 25,
):
    """Build the search URL for libgen.vg."""
    from urllib.parse import urlencode, quote_plus

    # Build params manually because of repeated keys (columns[], objects[])
    parts = [f"req={quote_plus(query)}"]
    for col in _DEFAULT_COLUMNS:
        parts.append(f"columns[]={col}")
    for obj in _DEFAULT_OBJECTS:
        parts.append(f"objects[]={obj}")
    parts.append(f"topics[]={topic}")
    parts.append(f"res={results_per_page}")
    parts.append("filesuns=all")
    return f"{BASE_URL}/index.php?{'&'.join(parts)}"


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
    results_per_page: int = 100,
    headless: bool = True,
    timeout: int = 20000,
) -> list:
    """Search libgen.vg and return a list of result dicts.

    Args:
        query: Search terms.
        topic: What to search for — "books", "articles", "fiction", "comics",
               "magazines", or "standards".
        results_per_page: How many results per page (25, 50, or 100).
        headless: Run browser in headless mode (default True).
        timeout: Page load timeout in ms.

    Returns:
        List of dicts with keys: title, authors, publisher, year, language,
        pages, size, extension, doi, series, md5, libgen_href, mirrors.
    """
    from playwright.sync_api import sync_playwright

    topic_code = _resolve_topic(topic)
    url = _build_search_url(query, topic=topic_code, results_per_page=results_per_page)

    with sync_playwright() as p:
        browser, context = _create_browser_context(p, headless=headless)
        try:
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout)

            table = page.query_selector("#tablelibgen")
            if not table:
                return []

            return _parse_results_table(table)
        finally:
            browser.close()


def _get_download_url(page, ads_url: str, *, timeout: int = 15000) -> Optional[str]:
    """Navigate to ads.php and extract the get.php download URL."""
    full_url = f"{BASE_URL}{ads_url}" if ads_url.startswith("/") else ads_url
    page.goto(full_url, wait_until="networkidle", timeout=timeout)

    get_link = page.query_selector('a[href*="get.php"]')
    if get_link:
        href = get_link.get_attribute("href")
        if href and not href.startswith("http"):
            href = f"{BASE_URL}/{href}"
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


def download_one(
    result: dict,
    *,
    download_dir: str = ".",
    page=None,
    timeout: int = 60000,
    delay: float = 1.0,
) -> Optional[str]:
    """Download a single result. Returns the saved file path, or None on failure.

    If ``page`` is provided (a Playwright Page object), reuse it.
    Otherwise, creates a new browser session (slower but standalone).

    Args:
        result: A result dict from ``search()``.
        download_dir: Where to save the file.
        page: Optional Playwright page to reuse.
        timeout: Download timeout in ms.
        delay: Seconds to wait between page loads (rate limiting).

    Returns:
        Path to the downloaded file, or None if download failed.
    """
    from playwright.sync_api import sync_playwright

    libgen_href = result.get("libgen_href", "")
    if not libgen_href:
        return None

    download_dir = Path(download_dir).expanduser()
    download_dir.mkdir(parents=True, exist_ok=True)

    filename = _make_filename(result)
    filepath = download_dir / filename

    # Skip if already downloaded
    if filepath.exists() and filepath.stat().st_size > 0:
        return str(filepath)

    def _do_download(pg):
        if delay:
            time.sleep(delay)

        get_url = _get_download_url(pg, libgen_href, timeout=timeout)
        if not get_url:
            return None

        # Use Playwright's download handling
        try:
            with pg.expect_download(timeout=timeout) as download_info:
                pg.goto(get_url, timeout=timeout)
            download = download_info.value

            # Use server-suggested filename if available, else our generated one
            suggested = download.suggested_filename
            if suggested and suggested != "download":
                # Keep our naming but use suggested extension if different
                pass

            download.save_as(str(filepath))
            return str(filepath)
        except Exception:
            # Fallback: try direct request via page context
            try:
                response = pg.request.get(get_url, timeout=timeout)
                if response.ok:
                    filepath.write_bytes(response.body())
                    return str(filepath)
            except Exception:
                pass
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
                    print(f"[{i + 1}/{len(to_download)}] {title}...")

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
                        print(f"  -> saved ({size:,} bytes)")
                    else:
                        print("  -> FAILED")
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

    Returns:
        List of (result_dict, filepath_or_None) tuples.
    """
    if verbose:
        print(f"Searching libgen.vg for: {query!r} (topic={topic})...")

    results = search(
        query,
        topic=topic,
        results_per_page=results_per_page,
        headless=headless,
        timeout=timeout,
    )

    if verbose:
        print(f"Found {len(results)} results.")

    if not results:
        return []

    if verbose and max_downloads > 0:
        print(f"Downloading up to {max_downloads}...")

    return download_results(
        results,
        download_dir=download_dir,
        max_downloads=max_downloads,
        delay=delay,
        headless=headless,
        timeout=timeout,
        verbose=verbose,
    )
