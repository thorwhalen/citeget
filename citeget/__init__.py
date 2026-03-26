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

import logging as _logging

# Configure a default handler with timestamps for citeget loggers.
# Only adds a handler if the citeget logger has none, so user config takes precedence.
_logger = _logging.getLogger(__name__)
if not _logger.handlers:
    _handler = _logging.StreamHandler()
    _handler.setFormatter(
        _logging.Formatter("[%(asctime)s] %(name)s %(levelname)s: %(message)s",
                           datefmt="%H:%M:%S")
    )
    _logger.addHandler(_handler)
    _logger.setLevel(_logging.WARNING)  # quiet by default; users can lower

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

from citeget.extract import (
    extract_references,
    regex_extractor,
    chain as chain_extractors,
    merge as merge_extractors,
    register as register_extractor,
    list_extractors,
    ExtractionResult,
    EXTRACTORS,
)

from citeget.resolve import (
    resolve_reference,
    url_rewriter,
    resolve_and_download,
    chain as chain_strategies,
    chain_resolvers,
    register_resolver,
    register_downloader,
    register_strategy,
    list_resolvers,
    list_downloaders,
    list_strategies,
    RESOLVERS,
    DOWNLOADERS,
    STRATEGIES,
    BUILTIN_URL_RULES,
)

__all__ = [
    # Core search/download
    "search",
    "download_results",
    "download_one",
    "search_and_download",
    "TOPIC_ALIASES",
    # Reference parsing (low-level)
    "parse_reference",
    "parse_references_section",
    # Reference extraction (composable)
    "extract_references",
    "regex_extractor",
    "chain_extractors",
    "merge_extractors",
    "register_extractor",
    "list_extractors",
    "ExtractionResult",
    "EXTRACTORS",
    # Reference resolution/download (composable)
    "resolve_reference",
    "url_rewriter",
    "resolve_and_download",
    "chain_strategies",
    "chain_resolvers",
    "register_resolver",
    "register_downloader",
    "register_strategy",
    "list_resolvers",
    "list_downloaders",
    "list_strategies",
    "RESOLVERS",
    "DOWNLOADERS",
    "STRATEGIES",
    "BUILTIN_URL_RULES",
    # Acquisition (orchestrator)
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
