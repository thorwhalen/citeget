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

    # Or acquire one copy of a *specific* book: ranked against title+author,
    # validated as a complete book, falling through to the next candidate if not
    from citeget import get_book
    get_book("Crossing the Chasm", authors="Geoffrey A. Moore", download_dir="~/books")

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
        _logging.Formatter(
            "[%(asctime)s] %(name)s %(levelname)s: %(message)s", datefmt="%H:%M:%S"
        )
    )
    _logger.addHandler(_handler)
    _logger.setLevel(_logging.WARNING)  # quiet by default; users can lower

from citeget.core import (
    search,
    download_results,
    download_one,
    download_best,
    get_book,
    search_and_download,
    check_mirrors,
    TOPIC_ALIASES,
    DEFAULT_LIBGEN_MIRRORS,
    MirrorUnreachableError,
)

from citeget.rank import (
    rank_results,
    score_result,
    dedupe_results,
    ScoredResult,
    ScoreWeights,
    SizeBounds,
)

from citeget.validate import (
    validate_download,
    validate_bytes,
    ValidationPolicy,
    ValidationResult,
    InvalidDownloadError,
    DEFAULT_POLICY,
    BOOK_POLICY,
)

from citeget.names import (
    apa7_authors,
    candidate_surnames,
    surnames,
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

from citeget.fetch import (
    fetch,
    fetch_one,
    extract_urls_from_text,
    infer_filename,
    html_to_markdown,
    html_to_pdf,
    FetchResult,
    UrlEntry,
)

__all__ = [
    # Core search/download
    "search",
    "download_results",
    "download_one",
    "download_best",
    "get_book",
    "search_and_download",
    "check_mirrors",
    "TOPIC_ALIASES",
    "DEFAULT_LIBGEN_MIRRORS",
    "MirrorUnreachableError",
    # Result ranking (pick the right book, not the first row)
    "rank_results",
    "score_result",
    "dedupe_results",
    "ScoredResult",
    "ScoreWeights",
    "SizeBounds",
    # Download validation (is this really the file we asked for?)
    "validate_download",
    "validate_bytes",
    "ValidationPolicy",
    "ValidationResult",
    "InvalidDownloadError",
    "DEFAULT_POLICY",
    "BOOK_POLICY",
    # Author-name parsing
    "apa7_authors",
    "candidate_surnames",
    "surnames",
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
    # General-purpose fetch (any URL → md/pdf)
    "fetch",
    "fetch_one",
    "extract_urls_from_text",
    "infer_filename",
    "html_to_markdown",
    "html_to_pdf",
    "FetchResult",
    "UrlEntry",
]
