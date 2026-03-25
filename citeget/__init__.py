"""citeget — Find, acquire, and manage academic references.

Tools for searching Library Genesis, downloading papers, and bulk-acquiring
all references cited in a document. Designed for use by AI agents (via Claude
Code skills) and by humans (via CLI and Python API).

Usage::

    from citeget import search, search_and_download

    # Search libgen and get metadata
    results = search("graph theory", topic="articles")

    # Search and download top results
    search_and_download("python programming", download_dir="~/papers", max_downloads=5)

    # Acquire all references from a document
    from citeget import parse_references_section, acquire_all_references, resolve_work_dir

    work_dir = resolve_work_dir(reference_file="my_paper.md")
    refs = parse_references_section(refs_text)
    successes, failures, log = acquire_all_references(
        refs, download_dir=work_dir / "references", work_dir=work_dir,
    )

Topics (for libgen search):
    - "books" or "l" — Libgen (books)
    - "articles" or "a" — Scientific Articles
    - "fiction" or "f" — Fiction
    - "comics" or "c" — Comics
    - "magazines" or "m" — Magazines
    - "standards" or "s" — Standards
"""

from citeget.core import (
    search,
    download_results,
    download_one,
    search_and_download,
    TOPIC_ALIASES,
)

from citeget.acquire_references import (
    parse_reference,
    parse_references_section,
    acquire_reference,
    acquire_all_references,
    generate_search_queries,
    resolve_work_dir,
    check_existing_downloads,
    write_references_md,
    write_missed_references_md,
    Reference,
    AcquisitionResult,
)

__all__ = [
    "search",
    "download_results",
    "download_one",
    "search_and_download",
    "TOPIC_ALIASES",
    "parse_reference",
    "parse_references_section",
    "acquire_reference",
    "acquire_all_references",
    "generate_search_queries",
    "resolve_work_dir",
    "check_existing_downloads",
    "write_references_md",
    "write_missed_references_md",
    "Reference",
    "AcquisitionResult",
]
