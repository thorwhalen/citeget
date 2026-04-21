"""Tools for acquiring academic references as PDFs.

Given a structured reference (title, authors, year, URL, etc.), this module
tries multiple strategies to obtain a PDF:
1. Direct URL download (if a URL is provided and yields a PDF)
2. ArXiv download (if URL is an arxiv link, get the PDF directly)
3. Libgen search with progressively adjusted query specificity

The query strategy for libgen searches:
- Start with the full title (no punctuation) as a mid-specificity query
- If too many results (>20) and no good match: add first author surname
- If no results: try shorter title (first 5 words)
- If still no results: try author + key title words
"""

import contextlib
import re
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _ts():
    """Return a bracketed timestamp string for progress messages."""
    return datetime.now().strftime("[%H:%M:%S]")


REFERENCES_SUBDIR = "references"


def resolve_work_dir(
    reference_file: str | Path | None = None,
    work_dir: str | Path | None = None,
) -> Path:
    """Resolve the working directory for an acquisition session.

    Rules:
    - If ``work_dir`` is given as a full path, use it (create if needed,
      parent must exist).
    - If ``work_dir`` is a bare name (no slashes), use ``~/Downloads/{name}``.
    - If ``work_dir`` is None and ``reference_file`` is given, derive from the
      reference file: ``{stem} -- acquired_references/`` in the same directory.
    - If neither is given, raise ValueError.

    Returns:
        Resolved Path to the working directory.

    Raises:
        ValueError: If inputs are insufficient or invalid.
        FileNotFoundError: If a specified parent directory doesn't exist.
    """
    if work_dir is not None:
        work_dir = str(work_dir).strip()
        if "/" in work_dir or work_dir.startswith("~"):
            # Full or home-relative path
            p = Path(work_dir).expanduser()
            if not p.parent.exists():
                raise FileNotFoundError(f"Parent directory does not exist: {p.parent}")
            p.mkdir(parents=True, exist_ok=True)
            return p
        elif work_dir:
            # Bare name → ~/Downloads/{name}
            p = Path.home() / "Downloads" / work_dir
            p.mkdir(parents=True, exist_ok=True)
            return p
        else:
            raise ValueError("work_dir is empty")

    if reference_file is not None:
        ref_path = Path(reference_file).expanduser().resolve()
        if not ref_path.exists():
            raise FileNotFoundError(f"Reference file not found: {ref_path}")
        stem = ref_path.stem
        dirname = f"{stem} -- acquired_references"
        p = ref_path.parent / dirname
        p.mkdir(parents=True, exist_ok=True)
        return p

    raise ValueError(
        "Either reference_file or work_dir must be provided. "
        "Pass work_dir as a full path or a bare name (uses ~/Downloads/{name})."
    )


def check_existing_downloads(
    references: list,
    download_dir: str | Path,
) -> tuple:
    """Check which references already have downloaded files.

    Returns:
        (to_acquire, already_have) — two lists of Reference objects.
        ``already_have`` is a list of (Reference, filepath) tuples.
    """
    download_dir = Path(download_dir)
    to_acquire = []
    already_have = []

    for ref in references:
        base = download_dir / _make_ref_basename(ref)
        # Accept any previously-acquired file that shares the base name,
        # regardless of extension (citeget may have saved as .epub/.mobi/etc).
        found = None
        for ext in _KNOWN_EXTENSIONS:
            candidate = base.with_suffix(ext)
            if candidate.exists() and candidate.stat().st_size > 1000:
                found = candidate
                break
        if found is not None:
            already_have.append((ref, str(found)))
        else:
            to_acquire.append(ref)

    return to_acquire, already_have


@dataclass
class Reference:
    """A parsed academic reference."""

    number: int
    raw: str  # The full reference text as written
    title: str = ""
    authors: str = ""
    year: str = ""
    venue: str = ""
    url: str = ""
    doi: str = ""
    source_text: str = ""  # Original unprocessed text span (for fallback)

    def __str__(self):
        return f"[{self.number}] {self.title} ({self.year})"


@dataclass
class AcquisitionResult:
    """Result of trying to acquire a reference."""

    reference: Reference
    success: bool = False
    filepath: Optional[str] = None
    method: str = ""  # "direct_url", "arxiv", "libgen", "failed"
    queries_tried: list = field(default_factory=list)
    notes: str = ""


def parse_reference(text: str, number: int = 0) -> Reference:
    """Parse a reference string into a Reference object.

    Handles formats like:
        [1] A. Author, "Title," in *Venue*, year. URL
        A. Author, "Title," Venue, vol. X, pp. Y-Z, year.
    """
    raw = text.strip()

    # Extract number if present
    num_match = re.match(r"\[(\d+)\]\s*", raw)
    if num_match:
        number = int(num_match.group(1))
        raw_body = raw[num_match.end() :]
    else:
        raw_body = raw

    # Extract URL (at end, or embedded)
    url = ""
    url_match = re.search(r"(https?://\S+)", raw_body)
    if url_match:
        url = url_match.group(1).rstrip(".")

    # Extract title — typically in quotes or after author block before comma+venue
    title = ""
    # Try quoted title first: "Title" or "Title,"
    title_match = re.search(r'["\u201c](.+?)["\u201d]', raw_body)
    if title_match:
        title = title_match.group(1).rstrip(",").strip()

    # Extract year
    year = ""
    year_match = re.search(r"\b((?:19|20)\d{2})\b", raw_body)
    if year_match:
        year = year_match.group(1)

    # Extract authors — everything before the first quote or title
    authors = ""
    if title_match:
        authors = raw_body[: title_match.start()].strip().rstrip(",").strip()
    else:
        # Fallback: take everything before first comma-separated chunk with year
        parts = raw_body.split(",")
        if len(parts) >= 2:
            authors = parts[0].strip()

    # Extract venue — between title and year, typically in *Venue* or plain
    venue = ""
    venue_match = re.search(r"\*(.+?)\*", raw_body)
    if venue_match:
        venue = venue_match.group(1)

    return Reference(
        number=number,
        raw=raw,
        title=title,
        authors=authors,
        year=year,
        venue=venue,
        url=url,
    )


def parse_references_section(text: str) -> list:
    """Parse a references section into a list of Reference objects.

    Expects lines starting with [N] as reference entries.
    """
    refs = []
    current_ref = ""
    current_num = 0

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        num_match = re.match(r"\[(\d+)\]", line)
        if num_match:
            # Save previous ref
            if current_ref:
                refs.append(parse_reference(current_ref, current_num))
            current_num = int(num_match.group(1))
            current_ref = line
        elif current_ref:
            # Continuation line
            current_ref += " " + line

    # Don't forget the last one
    if current_ref:
        refs.append(parse_reference(current_ref, current_num))

    return refs


def _clean_title_for_query(title: str) -> str:
    """Remove punctuation and normalize whitespace for search queries."""
    # Remove common punctuation that hurts search
    cleaned = re.sub(r"[\"':;,.!?(){}[\]—–\-]", " ", title)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _first_author_surname(authors: str) -> str:
    """Extract the surname of the first author."""
    surnames = _parse_all_surnames(authors)
    return surnames[0] if surnames else ""


def _parse_all_surnames(authors: str) -> list:
    """Extract all author surnames from an author string.

    Handles formats like:
        "A. B. Smith, C. D. Jones, and E. F. Brown"
        "S. De et al."
    """
    if not authors:
        return []

    # Handle "et al." — only first author is known
    if "et al" in authors:
        before_et = authors.split("et al")[0].strip().rstrip(",").strip()
        tokens = before_et.split()
        real = [t for t in tokens if len(t.rstrip(".")) > 1]
        return real[-1:] if real else tokens[-1:]

    # Split on comma and "and"
    s = authors.replace(" and ", ", ")
    parts = [p.strip() for p in s.split(",") if p.strip()]

    surnames = []
    for part in parts:
        tokens = part.split()
        # Skip initials (single letter or letter+period)
        real_words = [t for t in tokens if len(t.rstrip(".")) > 1]
        if real_words:
            surnames.append(real_words[-1])
    return surnames


def _apa7_authors(authors: str) -> str:
    """Format authors in APA 7 citation style (surnames only).

    1 author  -> "Smith"
    2 authors -> "Smith & Jones"
    3+ authors -> "Smith et al."
    """
    surnames = _parse_all_surnames(authors)
    if len(surnames) == 0:
        return "Unknown"
    elif len(surnames) == 1:
        return surnames[0]
    elif len(surnames) == 2:
        return f"{surnames[0]} & {surnames[1]}"
    else:
        return f"{surnames[0]} et al."


def generate_search_queries(ref: Reference) -> list:
    """Generate a sequence of search queries from most to least specific.

    Returns list of (query_string, description) tuples.
    """
    queries = []
    clean_title = _clean_title_for_query(ref.title)
    title_words = clean_title.split()
    surname = _first_author_surname(ref.authors)
    apa = _apa7_authors(ref.authors) if ref.authors else ""

    if clean_title:
        # 1. APA-style: "Title (Author & Author)" — matches how humans search
        if apa and apa != "Unknown":
            queries.append((f"{clean_title} ({apa})", "title (APA authors)"))

        # 2. Full clean title (mid-specificity — good starting point)
        queries.append((clean_title, "full title"))

        # 3. Title + first author (more specific)
        if surname:
            queries.append((f"{clean_title} {surname}", "title + author"))

        # 4. First 6 words of title (less specific)
        if len(title_words) > 6:
            short_title = " ".join(title_words[:6])
            queries.append((short_title, "short title (6 words)"))

        # 5. First 4 words + author (different balance)
        if len(title_words) > 4 and surname:
            queries.append(
                (" ".join(title_words[:4]) + " " + surname, "4 words + author")
            )

        # 6. First 3 words only (very broad)
        if len(title_words) > 3:
            queries.append((" ".join(title_words[:3]), "3 words (broad)"))

    # 7. Author + year (last resort, very broad)
    if surname and ref.year:
        queries.append((f"{surname} {ref.year}", "author + year"))

    return queries


def _is_arxiv_url(url: str) -> bool:
    return "arxiv.org" in url


def _arxiv_pdf_url(url: str) -> str:
    """Convert an arxiv abstract/abs URL to a PDF URL."""
    # https://arxiv.org/abs/2206.11893 -> https://arxiv.org/pdf/2206.11893
    url = url.replace("/abs/", "/pdf/")
    if not url.endswith(".pdf"):
        url += ".pdf"
    return url


def _download_url(url: str, filepath: Path, *, timeout: int = 30) -> bool:
    """Try to download a URL as a PDF. Returns True on success."""
    import requests

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=timeout, stream=True)
        if resp.status_code != 200:
            return False

        content_type = resp.headers.get("Content-Type", "")

        # Check if it's actually a PDF
        first_bytes = b""
        chunks = []
        for chunk in resp.iter_content(chunk_size=8192):
            if not first_bytes:
                first_bytes = chunk[:5]
            chunks.append(chunk)

        # Accept if content-type says PDF or first bytes are %PDF
        if b"%PDF" in first_bytes or "pdf" in content_type.lower():
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, "wb") as f:
                for chunk in chunks:
                    f.write(chunk)
            return filepath.stat().st_size > 1000  # Reject tiny files

        return False
    except Exception as e:
        logger.debug(f"Download failed for {url}: {e}")
        return False


def _try_direct_download(ref: Reference, filepath: Path) -> bool:
    """Try to download the reference directly from its URL."""
    if not ref.url:
        return False

    url = ref.url

    # ArXiv: convert to PDF URL
    if _is_arxiv_url(url):
        url = _arxiv_pdf_url(url)

    # OpenReview: try PDF URL
    if "openreview.net" in url and "/pdf?" not in url:
        url = url.replace("/forum?", "/pdf?")

    # Intel white papers and other direct PDFs
    return _download_url(url, filepath)


# Known ebook/document extensions citeget may produce. Used by
# ``check_existing_downloads`` when looking up a previously-acquired file
# whose actual extension may not be ``.pdf``.
_KNOWN_EXTENSIONS = (
    ".pdf",
    ".epub",
    ".mobi",
    ".azw",
    ".azw3",
    ".djvu",
    ".lit",
    ".rar",
    ".zip",
)


def _detect_real_extension(path: Path) -> Optional[str]:
    """Return the canonical extension for a file based on its magic bytes.

    Returns ``None`` for HTML/unknown responses (typically error pages served
    by the download mirror, not actual book files).
    """
    try:
        with open(path, "rb") as f:
            head = f.read(1024)
    except OSError:
        return None
    if not head:
        return None
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"PK\x03\x04"):
        # EPUB is a ZIP whose first stored entry is mimetype=application/epub+zip
        if b"application/epub+zip" in head:
            return ".epub"
        return ".zip"
    if head.startswith(b"Rar!"):
        return ".rar"
    if head.startswith(b"CR\x07\x8a") or head.startswith(b"CR!"):
        return ".djvu"
    if head.startswith(b"ITOL"):
        return ".lit"
    # MOBI / AZW: PalmDB header — first 32 bytes are DB name, then creator at 60-68.
    creator = head[60:68]
    if creator == b"BOOKMOBI":
        return ".mobi"
    if creator.startswith(b"TPZ"):
        return ".azw"
    # HTML error page
    lower = head[:64].lstrip().lower()
    if lower.startswith((b"<!doctype", b"<html", b"<?xml", b"<head")):
        return None
    return None


def _try_convert_to_pdf(src: Path, target_pdf: Path) -> Optional[Path]:
    """Best-effort convert *src* to a PDF at *target_pdf* using pdfdol.

    Returns *target_pdf* on success, ``None`` if conversion isn't available
    or fails. Does not delete *src* on success — the caller decides.
    """
    try:
        from pdfdol.tools import get_format_converter  # type: ignore
    except Exception:
        return None
    converter = get_format_converter(src.suffix)
    if converter is None:
        return None
    try:
        pdf_bytes = converter(str(src))
    except Exception as e:
        logger.debug("pdfdol conversion failed for %s: %s", src.name, e)
        return None
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return None
    target_pdf.parent.mkdir(parents=True, exist_ok=True)
    target_pdf.write_bytes(pdf_bytes)
    return target_pdf


def _finalize_acquired_file(
    written_path: Path,
    *,
    target_base: Optional[Path] = None,
    convert_to_pdf: bool = False,
) -> Optional[Path]:
    """Move a just-downloaded file to its correct final path and extension.

    Args:
        written_path: Where the downloader actually wrote the bytes.
        target_base: Intended final path *without* extension. If ``None``,
            uses ``written_path`` minus its extension — i.e. the rename
            happens in-place.
        convert_to_pdf: When ``True`` and the content isn't already a PDF,
            attempt conversion via ``pdfdol.tools.get_format_converter``.
            On success the PDF is written and the native source is removed.
            On failure (converter unavailable, ``ebook-convert`` missing,
            conversion error) the native file is kept with its real
            extension — the hard rule "no ``.pdf`` on non-PDFs" is never
            broken.

    Returns:
        The final :class:`Path` on success, or ``None`` if the content was
        an HTML error page (the file is deleted in that case).
    """
    if not written_path.exists():
        return None
    real_ext = _detect_real_extension(written_path)
    if real_ext is None:
        with contextlib.suppress(OSError):
            written_path.unlink()
        return None

    base = (target_base or written_path).with_suffix("")

    # Optional conversion to PDF.
    if convert_to_pdf and real_ext != ".pdf":
        pdf_target = base.with_suffix(".pdf")
        converted = _try_convert_to_pdf(written_path, pdf_target)
        if converted is not None:
            # Remove the native source, unless it happens to be the target
            # path itself (e.g. in-place conversion of tempfoo.pdf → foo.pdf).
            if written_path.resolve() != converted.resolve():
                with contextlib.suppress(OSError):
                    written_path.unlink()
            return converted
        # Fall through to native-format save if conversion didn't happen.

    final_path = base.with_suffix(real_ext)
    if final_path == written_path:
        return final_path
    # Replace a stale file that might share the final path.
    if final_path.exists():
        with contextlib.suppress(OSError):
            final_path.unlink()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    written_path.rename(final_path)
    return final_path


def _sanitize_filename(name: str, max_length: int = 150) -> str:
    """Make a string safe for use as a filename."""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) > max_length:
        name = name[:max_length]
    return name


def _make_ref_basename(ref: Reference) -> str:
    """Generate a base filename for a reference (without extension).

    Format: ``{title} ({authors_apa7}, {year})``
    where authors_apa7 follows APA 7 citation style:
    1 author -> "Smith", 2 -> "Smith & Jones", 3+ -> "Smith et al."

    The final extension is decided after download by
    :func:`_finalize_acquired_file` based on the actual file content.
    """
    title = ref.title[:120] if ref.title else f"ref_{ref.number}"
    apa = _apa7_authors(ref.authors) if ref.authors else "Unknown"

    # Extract just the 4-digit year
    year = ref.year
    if year:
        year_match = re.match(r"(\d{4})", year)
        if year_match:
            year = year_match.group(1)

    if year:
        name = f"{title} ({apa}, {year})"
    else:
        name = f"{title} ({apa})"
    return _sanitize_filename(name)


def _match_result_to_ref(result: dict, ref: Reference) -> float:
    """Score how well a libgen result matches a reference (0-1)."""
    score = 0.0

    ref_title_lower = ref.title.lower()
    result_title_lower = result.get("title", "").lower()

    if not result_title_lower:
        return 0.0

    # Title similarity
    ref_words = set(re.findall(r"\w+", ref_title_lower))
    result_words = set(re.findall(r"\w+", result_title_lower))

    if ref_words and result_words:
        overlap = len(ref_words & result_words)
        title_score = overlap / max(len(ref_words), 1)
        score += title_score * 0.6

    # Author match
    if ref.authors and result.get("authors"):
        ref_surname = _first_author_surname(ref.authors).lower()
        if ref_surname and ref_surname in result["authors"].lower():
            score += 0.25

    # Year match
    if ref.year and result.get("year"):
        if ref.year in result["year"]:
            score += 0.15

    return score


def _try_libgen(
    ref: Reference,
    filepath: Path,
    *,
    topic: str = "articles",
    topics: tuple | None = None,
    log_entries: list,
    timeout: int = 30000,
    verbose: bool = False,
) -> Optional[str]:
    """Try to find and download the reference from libgen.

    Args:
        ref: Reference to search for.
        filepath: Target file path for the download.
        topic: Single topic to search (used when ``topics`` is None).
        topics: Multiple topics to search simultaneously, e.g.
            ``("books", "fiction", "articles")``.  Overrides ``topic``.
        log_entries: Log list (mutated in place).
        timeout: Browser timeout in ms.
        verbose: Print diagnostic info.

    Returns filepath on success, None on failure.
    """
    from citeget.core import search as libgen_search, download_one

    queries = generate_search_queries(ref)

    # Build search kwargs for single vs multi-topic
    search_kwargs = dict(results_per_page=25, timeout=timeout)
    if topics is not None:
        search_kwargs["topics"] = topics
        topic_label = "+".join(topics)
    else:
        search_kwargs["topic"] = topic
        topic_label = topic

    for query_text, query_desc in queries:
        timestamp = datetime.now().isoformat(timespec="seconds")

        try:
            results = libgen_search(query_text, **search_kwargs)
        except Exception as e:
            log_entries.append(
                {
                    "timestamp": timestamp,
                    "ref_number": ref.number,
                    "ref_title": ref.title[:80],
                    "query": query_text,
                    "query_type": f"{query_desc} [{topic_label}]",
                    "num_results": -1,
                    "matched": False,
                    "error": str(e)[:200],
                }
            )
            continue

        # Score results
        best_result = None
        best_score = 0.0
        for r in results:
            score = _match_result_to_ref(r, ref)
            if score > best_score:
                best_score = score
                best_result = r

        matched = best_score >= 0.4 and best_result is not None

        log_entry = {
            "timestamp": timestamp,
            "ref_number": ref.number,
            "ref_title": ref.title[:80],
            "query": query_text,
            "query_type": f"{query_desc} [{topic_label}]",
            "num_results": len(results),
            "matched": matched,
            "best_score": round(best_score, 2),
            "best_title": (best_result["title"][:80] if best_result else ""),
            "error": "",
        }
        log_entries.append(log_entry)

        if matched:
            try:
                downloaded = download_one(
                    best_result,
                    download_dir=str(filepath.parent),
                    timeout=60000,
                    try_mirrors=True,
                    verbose=verbose,
                )
                if downloaded:
                    # Rename to our standard name
                    dl_path = Path(downloaded)
                    if dl_path != filepath and dl_path.exists():
                        if filepath.exists():
                            filepath.unlink()
                        dl_path.rename(filepath)
                    return str(filepath)
                else:
                    log_entry["error"] = "download returned None (all methods failed)"
            except Exception as e:
                log_entry["error"] = f"download failed: {e}"
                continue

    return None


def _try_arxiv_search(
    ref: Reference,
    filepath: Path,
    *,
    log_entries: list,
) -> Optional[str]:
    """Search arxiv API for the paper and download if found."""
    import requests
    from xml.etree import ElementTree as ET

    surname = _first_author_surname(ref.authors)
    clean_title = _clean_title_for_query(ref.title)

    # Build arxiv query: author + title keywords
    query_parts = []
    if surname:
        query_parts.append(f"au:{surname}")
    if clean_title:
        # Use first few significant title words
        title_words = clean_title.split()[:6]
        title_q = "+".join(title_words)
        query_parts.append(f"ti:{title_q}")

    if not query_parts:
        return None

    query = "+AND+".join(query_parts)
    url = f"http://export.arxiv.org/api/query?search_query={query}&max_results=5"

    timestamp = datetime.now().isoformat(timespec="seconds")
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None

        root = ET.fromstring(resp.text)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        entries = root.findall("a:entry", ns)

        for entry in entries:
            title_el = entry.find("a:title", ns)
            if title_el is None:
                continue
            entry_title = title_el.text.strip()

            # Check title similarity
            ref_words = set(re.findall(r"\w+", ref.title.lower()))
            entry_words = set(re.findall(r"\w+", entry_title.lower()))
            if ref_words and entry_words:
                overlap = len(ref_words & entry_words) / max(len(ref_words), 1)
                if overlap < 0.5:
                    continue
            else:
                continue

            # Find PDF link
            pdf_links = [
                link.get("href")
                for link in entry.findall("a:link", ns)
                if link.get("type") == "application/pdf"
            ]
            if not pdf_links:
                continue

            pdf_url = pdf_links[0]
            if _download_url(pdf_url, filepath):
                log_entries.append(
                    {
                        "timestamp": timestamp,
                        "ref_number": ref.number,
                        "ref_title": ref.title[:80],
                        "query": query,
                        "query_type": "arxiv_search",
                        "num_results": len(entries),
                        "matched": True,
                        "best_score": round(overlap, 2),
                        "best_title": entry_title[:80],
                        "error": "",
                    }
                )
                return str(filepath)

    except Exception as e:
        logger.debug(f"Arxiv search failed: {e}")

    return None


def _try_scihub_via_doi(
    ref: Reference,
    filepath: Path,
    *,
    log_entries: list,
) -> Optional[str]:
    """Look up DOI via Crossref, then try Sci-Hub."""
    import requests
    from bs4 import BeautifulSoup

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
    }
    timestamp = datetime.now().isoformat(timespec="seconds")

    # Step 1: Find DOI via Crossref
    clean_title = _clean_title_for_query(ref.title)
    surname = _first_author_surname(ref.authors)
    crossref_query = f"{clean_title} {surname}".strip()

    doi = ""
    try:
        resp = requests.get(
            f"https://api.crossref.org/works?query={crossref_query}&rows=3",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 200:
            items = resp.json()["message"]["items"]
            for item in items:
                item_title = item.get("title", [""])[0].lower()
                ref_words = set(re.findall(r"\w+", ref.title.lower()))
                item_words = set(re.findall(r"\w+", item_title))
                if ref_words and item_words:
                    overlap = len(ref_words & item_words) / max(len(ref_words), 1)
                    if overlap >= 0.5:
                        doi = item.get("DOI", "")
                        break
    except Exception:
        pass

    if not doi:
        return None

    # Step 2: Try Sci-Hub with DOI
    try:
        scihub_url = f"https://sci-hub.ru/{doi}"
        resp = requests.get(
            scihub_url, headers=headers, timeout=30, allow_redirects=True
        )
        if resp.status_code != 200:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")
        # Find storage links (direct PDF paths on Sci-Hub)
        storage_links = [
            a.get("href", "")
            for a in soup.find_all("a", href=True)
            if "/storage/" in a.get("href", "")
        ]

        if storage_links:
            pdf_link = storage_links[0]
            if pdf_link.startswith("/"):
                pdf_link = "https://sci-hub.ru" + pdf_link

            pdf_resp = requests.get(pdf_link, headers=headers, timeout=60)
            if pdf_resp.status_code == 200 and len(pdf_resp.content) > 1000:
                filepath.parent.mkdir(parents=True, exist_ok=True)
                filepath.write_bytes(pdf_resp.content)
                log_entries.append(
                    {
                        "timestamp": timestamp,
                        "ref_number": ref.number,
                        "ref_title": ref.title[:80],
                        "query": doi,
                        "query_type": "scihub_doi",
                        "num_results": 1,
                        "matched": True,
                        "best_score": 1.0,
                        "best_title": "",
                        "error": "",
                    }
                )
                return str(filepath)
    except Exception as e:
        logger.debug(f"Sci-Hub DOI lookup failed: {e}")

    return None


def acquire_reference(
    ref: Reference,
    download_dir: str | Path,
    *,
    log_entries: list,
    strategy=None,
    libgen_topics: tuple = ("articles", "books"),
    timeout: int = 30000,
    verbose: bool = False,
    convert_to_pdf: bool = False,
) -> AcquisitionResult:
    """Try to acquire a single reference.

    When *strategy* is given, delegates entirely to the composable
    strategy system in :mod:`citeget.resolve`.  Otherwise falls back to
    the legacy hard-coded chain for backward compatibility.

    The legacy chain now searches all ``libgen_topics`` simultaneously
    in a single request (multi-topic search), rather than sequentially.

    Args:
        ref: The reference to acquire.
        download_dir: Where to save the file.
        log_entries: List to append log dicts to (mutated in place).
        strategy: An ``AcquisitionStrategy`` callable, a registered
            strategy name (``str``), or ``None`` for the legacy chain.
            Pass ``"default"`` to use the new composable default.
        libgen_topics: Topics to search on libgen (searched simultaneously).
        timeout: Timeout for browser operations (legacy chain only).
        verbose: Print diagnostic info on download attempts.
        convert_to_pdf: When ``True``, non-PDF downloads (EPUB, MOBI,
            DjVu, ...) are converted to PDF via ``pdfdol`` (Calibre's
            ``ebook-convert`` under the hood) when available. On
            conversion failure or when the converter is missing, the
            native format is kept — a non-PDF is never renamed to
            ``.pdf``.
    """
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    target_base = download_dir / _make_ref_basename(ref)

    # Skip if already exists (under any known extension)
    for ext in _KNOWN_EXTENSIONS:
        candidate = target_base.with_suffix(ext)
        if candidate.exists() and candidate.stat().st_size > 1000:
            return AcquisitionResult(
                reference=ref,
                success=True,
                filepath=str(candidate),
                method="already_exists",
            )

    # Strategies/downloaders write to this tentative ``filepath`` (``.pdf``
    # extension). After a successful download the finalizer below moves it
    # to target_base.with_suffix(<detected_ext>) — or (if convert_to_pdf)
    # converts it to a real PDF at that name.
    filepath = target_base.with_suffix(".pdf")

    def _success(path: str | Path, method: str) -> AcquisitionResult:
        """Finalize a freshly-downloaded file to its correct extension and
        return the AcquisitionResult — or a failure if the content was HTML."""
        final = _finalize_acquired_file(
            Path(path),
            target_base=target_base,
            convert_to_pdf=convert_to_pdf,
        )
        if final is None:
            return AcquisitionResult(
                reference=ref,
                success=False,
                method="failed",
                notes=f"{method}: response was HTML/unknown, not a book",
            )
        return AcquisitionResult(
            reference=ref,
            success=True,
            filepath=str(final),
            method=method,
        )

    # --- New composable path ---
    if strategy is not None:
        from citeget.resolve import resolve_reference, with_logging

        if isinstance(strategy, str):
            from citeget.resolve import get_strategy

            strat = get_strategy(strategy)
        else:
            strat = strategy

        strat = with_logging(strat, name="resolve", log_entries=log_entries)
        result_path = resolve_reference(ref, filepath, strategy=strat)

        if result_path:
            return _success(result_path, "resolved")
        return AcquisitionResult(
            reference=ref,
            success=False,
            method="failed",
            notes="All strategies exhausted",
        )

    # --- Legacy hard-coded chain (backward compatible) ---
    timestamp = datetime.now().isoformat(timespec="seconds")

    # 1. Try direct URL
    if ref.url:
        if _try_direct_download(ref, filepath):
            log_entries.append(
                {
                    "timestamp": timestamp,
                    "ref_number": ref.number,
                    "ref_title": ref.title[:80],
                    "query": ref.url,
                    "query_type": "direct_url",
                    "num_results": 1,
                    "matched": True,
                    "best_score": 1.0,
                    "best_title": "",
                    "error": "",
                }
            )
            return _success(filepath, "direct_url")
        else:
            log_entries.append(
                {
                    "timestamp": timestamp,
                    "ref_number": ref.number,
                    "ref_title": ref.title[:80],
                    "query": ref.url,
                    "query_type": "direct_url",
                    "num_results": 0,
                    "matched": False,
                    "best_score": 0,
                    "best_title": "",
                    "error": "direct download failed or not PDF",
                }
            )

    # 2. Try libgen — search all topics simultaneously
    result_path = _try_libgen(
        ref,
        filepath,
        topics=libgen_topics,
        log_entries=log_entries,
        timeout=timeout,
        verbose=verbose,
    )
    if result_path:
        topic_label = "+".join(libgen_topics)
        return _success(result_path, f"libgen_{topic_label}")

    # 3. Try arxiv API search (finds preprints not caught by URL)
    arxiv_path = _try_arxiv_search(ref, filepath, log_entries=log_entries)
    if arxiv_path:
        return _success(arxiv_path, "arxiv_search")

    # 4. Try Sci-Hub via DOI lookup (Crossref → Sci-Hub)
    scihub_path = _try_scihub_via_doi(ref, filepath, log_entries=log_entries)
    if scihub_path:
        return _success(scihub_path, "scihub_doi")

    return AcquisitionResult(
        reference=ref,
        success=False,
        method="failed",
        notes="All strategies exhausted",
    )


def acquire_all_references(
    references: list,
    download_dir: str | Path,
    *,
    work_dir: str | Path | None = None,
    log_file: str | Path | None = None,
    strategy=None,
    libgen_topics: tuple = ("articles", "books"),
    delay: float = 2.0,
    verbose: bool = True,
    convert_to_pdf: bool = False,
) -> tuple:
    """Acquire files for a list of references.

    Checks for already-downloaded files first and skips them, reporting
    which references are being skipped so the user can re-download by
    renaming or removing the existing file.

    Each downloaded file is saved with an extension that matches its
    actual content (``.pdf``, ``.epub``, ``.mobi``, ``.djvu``, ...). A
    non-PDF is never renamed to ``.pdf``.

    Args:
        references: List of Reference objects.
        download_dir: Where to save files (the ``references/`` subdirectory
            inside the work_dir, or a standalone directory).
        work_dir: Optional work directory — if given, ``log_file`` defaults
            to ``{work_dir}/{datetime}__acquisition_log.txt``.
        log_file: Explicit path for the acquisition log. If None and
            ``work_dir`` is given, auto-generated with timestamp.
        strategy: Acquisition strategy — a callable, registered name,
            or ``None`` for the legacy chain.  Pass ``"default"`` to use
            the composable default from :mod:`citeget.resolve`.
        libgen_topics: Libgen topics to try (legacy chain only).
        delay: Seconds between operations (rate limiting).
        verbose: Print progress.
        convert_to_pdf: When ``True``, convert non-PDF downloads to PDF
            via ``pdfdol`` (Calibre's ``ebook-convert``) when available.
            Prints a hint if the flag is on but the converter isn't
            available. Defaults to ``False`` — native formats preserved.

    Returns:
        (successes, failures, log_entries) where successes and failures
        are lists of AcquisitionResult.
    """
    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    # Default log file with timestamp
    if log_file is None and work_dir is not None:
        ts = datetime.now().strftime("%Y-%m-%d_%H%M")
        log_file = Path(work_dir) / f"{ts}__acquisition_log.txt"

    log_entries = []
    successes = []
    failures = []

    if convert_to_pdf and verbose:
        try:
            from pdfdol.tools import find_ebook_convert  # type: ignore

            if find_ebook_convert() is None:
                print(
                    f"{_ts()} Note: convert_to_pdf=True but Calibre's "
                    "'ebook-convert' was not found. Install Calibre "
                    "(https://calibre-ebook.com/download) to enable "
                    "EPUB/MOBI/DjVu→PDF conversion. Native formats will be "
                    "kept as-is."
                )
        except Exception:
            print(
                f"{_ts()} Note: convert_to_pdf=True but pdfdol is not "
                "available. Install it (`pip install pdfdol`) to enable "
                "conversion. Native formats will be kept as-is."
            )

    # (C) Check for already-downloaded files
    to_acquire, already_have = check_existing_downloads(references, download_dir)

    if already_have and verbose:
        print(f"{_ts()} Skipping {len(already_have)} already-downloaded reference(s):")
        for ref, fpath in already_have:
            print(f"  [{ref.number}] {ref.title[:60]}")
            print(f"        -> {Path(fpath).name}")
        print("  (To re-download, rename or move the existing file.)\n")

    # Record already-have as successes
    for ref, fpath in already_have:
        successes.append(
            AcquisitionResult(
                reference=ref,
                success=True,
                filepath=fpath,
                method="already_exists",
            )
        )

    for i, ref in enumerate(to_acquire):
        if verbose:
            print(
                f"\n{_ts()} [{i + 1}/{len(to_acquire)}] Ref [{ref.number}]: {ref.title[:60]}..."
            )

        result = acquire_reference(
            ref,
            download_dir,
            log_entries=log_entries,
            strategy=strategy,
            libgen_topics=libgen_topics,
            verbose=verbose,
            convert_to_pdf=convert_to_pdf,
        )

        if result.success:
            successes.append(result)
            if verbose:
                print(f"  {_ts()} SUCCESS ({result.method}) -> {result.filepath}")
        else:
            failures.append(result)
            if verbose:
                print(f"  {_ts()} FAILED: {result.notes}")

        # Rate limit between libgen operations
        if i < len(to_acquire) - 1 and delay:
            time.sleep(delay)

    # Write log
    if log_file:
        _write_log(log_entries, log_file)

    return successes, failures, log_entries


def _write_log(log_entries: list, log_file: str | Path):
    """Write acquisition log as a TSV file for easy parsing."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    headers = [
        "timestamp",
        "ref_number",
        "ref_title",
        "query",
        "query_type",
        "num_results",
        "matched",
        "best_score",
        "best_title",
        "error",
    ]

    with open(log_file, "w") as f:
        f.write("\t".join(headers) + "\n")
        for entry in log_entries:
            row = []
            for h in headers:
                val = str(entry.get(h, ""))
                # Escape tabs and newlines
                val = val.replace("\t", " ").replace("\n", " ")
                row.append(val)
            f.write("\t".join(row) + "\n")


def write_references_md(
    successes: list,
    download_dir: str | Path,
    output_file: str | Path,
):
    """Write a references.md with hyperlinks to local downloaded files."""
    from urllib.parse import quote

    download_dir = Path(download_dir)
    output_file = Path(output_file)

    with open(output_file, "w") as f:
        f.write("# Acquired References\n\n")
        for result in sorted(successes, key=lambda r: r.reference.number):
            ref = result.reference
            filepath = Path(result.filepath) if result.filepath else None
            if filepath and filepath.exists():
                # Relative path from output_file's directory, URL-encoded
                try:
                    rel = filepath.relative_to(output_file.parent)
                except ValueError:
                    rel = filepath
                # Use ./ prefix and URL-encode for markdown link compatibility
                encoded = "/".join(quote(part) for part in rel.parts)
                link = f"./{encoded}" if not str(rel).startswith("./") else encoded
                f.write(f"{ref.raw}\n")
                f.write(f"  - **Local file**: [{filepath.name}]({link})\n")
                f.write(f"  - Method: {result.method}\n\n")
            else:
                f.write(f"{ref.raw}\n")
                f.write(f"  - Method: {result.method} (file missing)\n\n")


def write_missed_references_md(
    failures: list,
    output_file: str | Path,
):
    """Write a markdown file listing references that could not be acquired."""
    output_file = Path(output_file)
    with open(output_file, "w") as f:
        f.write("# Missed References\n\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total missed: {len(failures)}\n\n")
        for result in sorted(failures, key=lambda r: r.reference.number):
            ref = result.reference
            f.write(f"{ref.raw}\n")
            f.write(f"  - Notes: {result.notes}\n\n")
