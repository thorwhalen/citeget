# citeget

citeget — Find, acquire, and manage academic references.

Tools for searching Library Genesis, downloading papers, and bulk-acquiring
all references cited in a document. Designed for use by AI agents (via Claude
Code skills) and by humans (via CLI and Python API).

Usage:

```default
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
```

Topics (for libgen search):

> - “books” or “l” — Libgen (books)
> - “articles” or “a” — Scientific Articles
> - “fiction” or “f” — Fiction
> - “comics” or “c” — Comics
> - “magazines” or “m” — Magazines
> - “standards” or “s” — Standards

### Functions

| [`search`](#citeget.search)(query, \*[, topic, topics, ...])            | Search a libgen mirror and return a list of result dicts.                                                    |
|-----------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
| [`download_results`](#citeget.download_results)(results, \*[, download_dir, ...]) | Download multiple results.                                                                                   |
| [`download_one`](#citeget.download_one)(result, \*[, download_dir, ...])      | Download a single result.                                                                                    |
| [`download_best`](#citeget.download_best)(results, \*, title[, authors, ...])  | Download the best match for a specific title, falling through on failure.                                    |
| [`get_book`](#citeget.get_book)(title, \*[, authors, download_dir, ...])  | Acquire one copy of a specific book.                                                                         |
| [`search_and_download`](#citeget.search_and_download)(query, \*[, topic, ...])       | Search libgen and download matching results in one shot.                                                     |
| [`check_mirrors`](#citeget.check_mirrors)(\*[, mirrors, query, topic, ...])    | Probe each configured mirror and report which ones are healthy.                                              |
| [`rank_results`](#citeget.rank_results)(results, \*, title[, authors])        | Return `results` as [`ScoredResult`](#citeget.ScoredResult) objects, best match first. |
| [`score_result`](#citeget.score_result)(result, \*, title[, authors, ...])    | Score one `search()` result against a requested title and author.                                            |
| [`dedupe_results`](#citeget.dedupe_results)(results, \*[, key])                 | Keep only the first result for each distinct work, preserving order.                                         |
| [`validate_download`](#citeget.validate_download)(path, \*[, extension, ...])      | Validate a file on disk.                                                                                     |
| [`validate_bytes`](#citeget.validate_bytes)(body, \*[, extension, ...])         | Validate an in-memory response body without writing it to disk.                                              |
| [`apa7_authors`](#citeget.apa7_authors)(authors)                              | Format *authors* APA 7 style, surnames only.                                                                 |
| [`candidate_surnames`](#citeget.candidate_surnames)(authors)                        | Normalized surnames usable for matching, in either name ordering.                                            |
| [`surnames`](#citeget.surnames)(authors)                                  | Surnames of every author in *authors*, in order, casing preserved.                                           |
| [`parse_reference`](#citeget.parse_reference)(text[, number])                    | Parse a reference string into a Reference object.                                                            |
| [`parse_references_section`](#citeget.parse_references_section)(text)                     | Parse a references section into a list of Reference objects.                                                 |
| [`extract_references`](#citeget.extract_references)(text, \*[, extractor])          | Extract references from document text.                                                                       |
| [`regex_extractor`](#citeget.regex_extractor)(\*[, section_patterns, ...])       | Create an extractor from regex patterns.                                                                     |
| [`chain_extractors`](#citeget.chain_extractors)(\*extractors)                     | Try *extractors* in order, return the first non-empty result.                                                |
| [`merge_extractors`](#citeget.merge_extractors)(\*extractors)                     | Run all *extractors*, deduplicate by reference number.                                                       |
| [`register_extractor`](#citeget.register_extractor)(name, extractor)                | Register a named extractor.                                                                                  |
| [`list_extractors`](#citeget.list_extractors)()                                  | Return names of all registered extractors.                                                                   |
| [`resolve_reference`](#citeget.resolve_reference)(ref, filepath, \*[, strategy])   | Resolve and download a single reference.                                                                     |
| [`url_rewriter`](#citeget.url_rewriter)(\*[, rules])                          | Create a resolver that rewrites known repository URLs to direct PDFs.                                        |
| [`resolve_and_download`](#citeget.resolve_and_download)(resolver, \*[, downloader])   | Create a strategy that resolves URLs then tries to download each.                                            |
| [`chain_strategies`](#citeget.chain_strategies)(\*strategies)                     | Try *strategies* in order, return the first success.                                                         |
| [`chain_resolvers`](#citeget.chain_resolvers)(\*resolvers)                       | Concatenate URL lists from multiple resolvers (deduped, order-preserving).                                   |
| [`register_resolver`](#citeget.register_resolver)(name, resolver)                  | Register a named URL resolver.                                                                               |
| [`register_downloader`](#citeget.register_downloader)(name, downloader)              | Register a named downloader.                                                                                 |
| [`register_strategy`](#citeget.register_strategy)(name, strategy)                  | Register a named acquisition strategy.                                                                       |
| [`list_resolvers`](#citeget.list_resolvers)()                                   | Return names of all registered resolvers.                                                                    |
| [`list_downloaders`](#citeget.list_downloaders)()                                 | Return names of all registered downloaders.                                                                  |
| [`list_strategies`](#citeget.list_strategies)()                                  | Return names of all registered strategies.                                                                   |
| [`acquire_reference`](#citeget.acquire_reference)(ref, download_dir, \*, ...)      | Try to acquire a single reference.                                                                           |
| [`acquire_all_references`](#citeget.acquire_all_references)(references, ...[, ...])     | Acquire files for a list of references.                                                                      |
| [`generate_search_queries`](#citeget.generate_search_queries)(ref)                       | Generate a sequence of search queries from most to least specific.                                           |
| [`resolve_work_dir`](#citeget.resolve_work_dir)([reference_file, work_dir])       | Resolve the working directory for an acquisition session.                                                    |
| [`check_existing_downloads`](#citeget.check_existing_downloads)(references, ...)          | Check which references already have downloaded files.                                                        |
| [`write_references_md`](#citeget.write_references_md)(successes, download_dir, ...)  | Write a references.md with hyperlinks to local downloaded files.                                             |
| [`write_missed_references_md`](#citeget.write_missed_references_md)(failures, output_file)  | Write a markdown file listing references that could not be acquired.                                         |
| [`fetch`](#citeget.fetch)(source, \*[, output_dir, prefer, ...])       | Fetch one or many URLs from a flexible *source*.                                                             |
| [`fetch_one`](#citeget.fetch_one)(source, \*, output_dir[, prefer, ...])   | Fetch a single URL and save it under *output_dir*.                                                           |
| [`extract_urls_from_text`](#citeget.extract_urls_from_text)(text)                       | Parse URLs from prose / markdown / reference-style citations.                                                |
| [`infer_filename`](#citeget.infer_filename)(entry, ext)                         | Infer a filename for *entry*, ending in `.{ext}`.                                                            |
| [`html_to_markdown`](#citeget.html_to_markdown)(html, \*[, source_url])           | Convert *html* to clean Markdown.                                                                            |
| [`html_to_pdf`](#citeget.html_to_pdf)(url, \*[, html])                       | Render *url* (or *html* fallback) to PDF bytes via pdfkit/wkhtmltopdf.                                       |

### Classes

| [`ScoredResult`](#citeget.ScoredResult)(result, score, title_match, ...)     | A search result with its score and the signal breakdown behind it.   |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`ScoreWeights`](#citeget.ScoreWeights)([title, author, format, ...])        | Relative contribution of each signal to the total score.             |
| [`SizeBounds`](#citeget.SizeBounds)([min_bytes, min_pdf_bytes, ...])       | Plausibility bounds for a real book file.                            |
| [`ValidationPolicy`](#citeget.ValidationPolicy)([min_bytes, min_pdf_bytes, ...]) | What counts as an acceptable download.                               |
| [`ValidationResult`](#citeget.ValidationResult)(ok[, reason, detail])            | Verdict on a download, plus the measurements behind it.              |
| [`ExtractionResult`](#citeget.ExtractionResult)(references[, ...])               | Result of extracting references from text.                           |
| [`Reference`](#citeget.Reference)(number, raw[, title, authors, ...])     | A parsed academic reference.                                         |
| [`AcquisitionResult`](#citeget.AcquisitionResult)(reference[, success, ...])      | Result of trying to acquire a reference.                             |
| [`FetchResult`](#citeget.FetchResult)(url, status[, output_file, ...])      | Outcome of a single URL fetch.                                       |
| [`UrlEntry`](#citeget.UrlEntry)(url[, title, ref])                       | A URL with optional context preserved for filename inference.        |

### Exceptions

| [`MirrorUnreachableError`](#citeget.MirrorUnreachableError)   | Raised when no libgen mirror could be reached.                            |
|---------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`InvalidDownloadError`](#citeget.InvalidDownloadError)     | Raised when downloaded bytes are not a usable copy of the requested file. |

### *class* citeget.AcquisitionResult(reference, success=False, filepath=None, method='', queries_tried=<factory>, notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of trying to acquire a reference.

### *class* citeget.ExtractionResult(references, extractor_name='', confidence='unknown')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of extracting references from text.

### *class* citeget.FetchResult(url, status, output_file=None, format=None, title=None, ref=None, error=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of a single URL fetch.

#### *property* ok *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

True if file was written or already existed (status in {ok, skipped}).

### *exception* citeget.InvalidDownloadError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when downloaded bytes are not a usable copy of the requested file.

### *exception* citeget.MirrorUnreachableError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when no libgen mirror could be reached.

Distinct from an empty result set: this means every candidate mirror
failed to connect (down, moved, or blocked by local DNS/network), so the
caller gets an actionable message instead of a raw Playwright stack trace.

### *class* citeget.Reference(number, raw, title='', authors='', year='', venue='', url='', doi='', source_text='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed academic reference.

### *class* citeget.ScoreWeights(title=5.0, author=3.0, format=1.2, language=1.0, size=0.8, decoy_penalty=6.0, stub_penalty=3.0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Relative contribution of each signal to the total score.

Title and author dominate: format and language only break ties between
results that are already plausibly the right book.

### *class* citeget.ScoredResult(result, score, title_match, author_match, is_decoy, is_stub)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A search result with its score and the signal breakdown behind it.

### *class* citeget.SizeBounds(min_bytes=80000, min_pdf_bytes=300000, implausible_bytes=120000000)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Plausibility bounds for a real book file.

`min_pdf_bytes` is deliberately far above `min_bytes`: a landing-page
“download” stub is typically a valid but nearly empty PDF, whereas a short
epub of a genuine book can legitimately be ~100 kB.

### *class* citeget.UrlEntry(url, title=None, ref=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A URL with optional context preserved for filename inference.

### *class* citeget.ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What counts as an acceptable download.

#### min_bytes

Absolute floor below which nothing can be a real document.

#### min_pdf_bytes

Higher floor for PDFs, which is where landing-page stubs
show up. A genuine short EPUB can be ~100 kB, so this cannot be a
single shared floor.

#### require_magic

Reject a file whose leading bytes do not match its
extension. Unknown extensions are always accepted.

#### reject_html

Reject a body that opens like an HTML document.

#### truncation_ratio

Reject a file smaller than this fraction of the size
the search result advertised. Set to 0 to disable.

#### min_pages

Minimum PDF page count (0 disables the check). Only sensible
when the caller knows the download should be a complete book.

#### min_epub_markup_bytes

Minimum total size of the markup entries inside
an EPUB (0 disables). Measures content volume rather than file size,
so a small-but-complete EPUB passes where a raw size floor fails.

### *class* citeget.ValidationResult(ok, reason='', detail=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Verdict on a download, plus the measurements behind it.

Falsy when the download is unacceptable, so it reads naturally:

```default
if not validate_download(path):
    ...
```

#### raise_if_invalid()

Return self when valid, else raise [`InvalidDownloadError`](#citeget.InvalidDownloadError).

* **Return type:**
  [`ValidationResult`](citeget.validate.html.md#citeget.validate.ValidationResult)

### citeget.acquire_all_references(references, download_dir, , work_dir=None, log_file=None, strategy=None, libgen_topics=('articles', 'books'), delay=2.0, verbose=True, convert_to_pdf=False, fetch_fallback=True)

Acquire files for a list of references.

Checks for already-downloaded files first and skips them, reporting
which references are being skipped so the user can re-download by
renaming or removing the existing file.

Each downloaded file is saved with an extension that matches its
actual content (`.pdf`, `.epub`, `.mobi`, `.djvu`, …). A
non-PDF is never renamed to `.pdf`.

* **Parameters:**
  * **references** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)) – List of Reference objects.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Where to save files (the `references/` subdirectory
    inside the work_dir, or a standalone directory).
  * **work_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Optional work directory — if given, `log_file` defaults
    to `{work_dir}/{datetime}__acquisition_log.txt`.
  * **log_file** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit path for the acquisition log. If None and
    `work_dir` is given, auto-generated with timestamp.
  * **strategy** – Acquisition strategy — a callable, registered name,
    or `None` for the legacy chain.  Pass `"default"` to use
    the composable default from [`citeget.resolve`](citeget.resolve.html.md#module-citeget.resolve).
  * **libgen_topics** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – Libgen topics to try (legacy chain only).
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between operations (rate limiting).
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress.
  * **convert_to_pdf** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When `True`, convert non-PDF downloads to PDF
    via `pdfdol` (Calibre’s `ebook-convert`) when available.
    Prints a hint if the flag is on but the converter isn’t
    available. Defaults to `False` — native formats preserved.
  * **fetch_fallback** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True (default), fall back to fetching `ref.url`
    as Markdown when all academic strategies fail (catches non-paper
    references like blog posts, docs, product pages).
* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
* **Returns:**
  (successes, failures, log_entries) where successes and failures
  are lists of AcquisitionResult.

### citeget.acquire_reference(ref, download_dir, , log_entries, strategy=None, libgen_topics=('articles', 'books'), timeout=30000, verbose=False, convert_to_pdf=False, fetch_fallback=True)

Try to acquire a single reference.

When *strategy* is given, delegates entirely to the composable
strategy system in [`citeget.resolve`](citeget.resolve.html.md#module-citeget.resolve).  Otherwise falls back to
the legacy hard-coded chain for backward compatibility.

The legacy chain now searches all `libgen_topics` simultaneously
in a single request (multi-topic search), rather than sequentially.

If all academic strategies fail and *fetch_fallback* is `True` (the
default), and the reference has a URL, the page is fetched as Markdown
via `citeget.fetch.fetch_one()`. This catches non-paper references
(blog posts, docs, product pages) that won’t appear in libgen/arxiv.

* **Parameters:**
  * **ref** ([`Reference`](citeget.acquire_references.html.md#citeget.acquire_references.Reference)) – The reference to acquire.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Where to save the file.
  * **log_entries** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)) – List to append log dicts to (mutated in place).
  * **strategy** – An `AcquisitionStrategy` callable, a registered
    strategy name (`str`), or `None` for the legacy chain.
    Pass `"default"` to use the new composable default.
  * **libgen_topics** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – Topics to search on libgen (searched simultaneously).
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Timeout for browser operations (legacy chain only).
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print diagnostic info on download attempts.
  * **convert_to_pdf** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – When `True`, non-PDF downloads (EPUB, MOBI,
    DjVu, …) are converted to PDF via `pdfdol` (Calibre’s
    `ebook-convert` under the hood) when available. On
    conversion failure or when the converter is missing, the
    native format is kept — a non-PDF is never renamed to
    `.pdf`.
  * **fetch_fallback** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True (default), fall back to fetching `ref.url`
    as Markdown when all academic strategies fail.
* **Return type:**
  [`AcquisitionResult`](citeget.acquire_references.html.md#citeget.acquire_references.AcquisitionResult)

### citeget.apa7_authors(authors)

Format *authors* APA 7 style, surnames only.

1 author -> `"Smith"`; 2 -> `"Smith & Jones"`; 3+ -> `"Smith et al."`;
nothing usable -> `"Unknown"`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> apa7_authors("Moore, Geoffrey A.")
'Moore'
>>> apa7_authors("Tufte, Edward R. (author);Krasny, Dmitry (author)")
'Tufte & Krasny'
>>> apa7_authors("")
'Unknown'
```

### citeget.candidate_surnames(authors)

Normalized surnames usable for matching, in either name ordering.

Multi-word surnames contribute their last word, since that is what a
caller-supplied author string is most likely to share.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)

```pycon
>>> sorted(candidate_surnames("Alice Smith & Bob Jones"))
['jones', 'smith']
>>> sorted(candidate_surnames("Sander van der Linden"))
['linden']
```

### citeget.chain_extractors(\*extractors)

Try *extractors* in order, return the first non-empty result.

* **Return type:**
  [`Extractor`](citeget.extract.html.md#citeget.extract.Extractor)

### citeget.chain_resolvers(\*resolvers)

Concatenate URL lists from multiple resolvers (deduped, order-preserving).

* **Return type:**
  [`UrlResolver`](citeget.resolve.html.md#citeget.resolve.UrlResolver)

### citeget.chain_strategies(\*strategies)

Try *strategies* in order, return the first success.

* **Return type:**
  [`AcquisitionStrategy`](citeget.resolve.html.md#citeget.resolve.AcquisitionStrategy)

### citeget.check_existing_downloads(references, download_dir)

Check which references already have downloaded files.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
* **Returns:**
  (to_acquire, already_have) — two lists of Reference objects.
  `already_have` is a list of (Reference, filepath) tuples.

### citeget.check_mirrors(, mirrors=None, query='design of everyday things', topic='books', timeout=45000, table_timeout=20000, headless=True, verbose=False)

Probe each configured mirror and report which ones are healthy.

Mirror domains rotate, so the default list goes stale on its own schedule.
This turns the resulting “citeget is broken” into the actionable “your
mirror list needs updating”, and gives you the working list to pass to
`CITEGET_LIBGEN_MIRRORS`.

* **Parameters:**
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Mirrors to probe; defaults to the configured list.
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms to probe with. Should be something with results.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Libgen topic to search.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Page navigation timeout in ms.
  * **table_timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How long to wait for the results table, in ms.
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Headless browser mode.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print each result as it is probed.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Returns:**
  One dict per mirror with keys `mirror`, `ok`, `results`,
  `elapsed_ms` and `error`, in the order probed.

### citeget.dedupe_results(results, \*, key=<function dedupe_key>)

Keep only the first result for each distinct work, preserving order.

Apply after ranking so the surviving copy of each work is the best-scoring
one. Accepts either plain result dicts or [`ScoredResult`](#citeget.ScoredResult) objects and
returns the same kind it was given.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.download_best(results, , title, authors=None, download_dir='.', max_candidates=5, page=None, timeout=60000, delay=1.0, headless=True, try_mirrors=True, verbose=False, validate=True, policy=None, \*\*rank_kwargs)

Download the best match for a specific title, falling through on failure.

Ranks *results* against the title and author actually wanted (see
[`citeget.rank`](citeget.rank.html.md#module-citeget.rank)) and downloads them in that order until one validates.
Falling through matters as much as ranking does: libgen catalogues excerpts,
front-matter samples and reviews under the full work’s title, and the next
candidate is usually the real thing.

Candidates are deliberately *not* deduplicated by format here — when the PDF
of a work turns out to be an excerpt, its EPUB often is not.

* **Parameters:**
  * **results** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)) – Result dicts from [`search()`](#citeget.search).
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The title actually wanted.
  * **authors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – The author(s) wanted, if known — a strong disambiguating signal.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save the file.
  * **max_candidates** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many ranked candidates to try before giving up.
  * **page** – Optional Playwright page to reuse.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Per-download timeout in ms.
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between page loads (rate limiting).
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Headless browser mode (ignored when `page` is given).
  * **try_mirrors** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Try external mirror URLs when the primary path fails.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress and the reason each candidate was rejected.
  * **validate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check that what arrived is really the requested file.
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    [`citeget.validate.BOOK_POLICY`](citeget.validate.html.md#citeget.validate.BOOK_POLICY), which also rejects excerpts.
  * **\*\*rank_kwargs** – Forwarded to [`citeget.rank.score_result()`](citeget.rank.html.md#citeget.rank.score_result)
    (`format_preference`, `language`, `weights`, `size_bounds`,
    `decoy_pattern`).
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if no candidate produced one.

### citeget.download_one(result, , download_dir='.', page=None, timeout=60000, delay=1.0, try_mirrors=True, verbose=False, validate=True, policy=None)

Download a single result. Returns the saved file path, or None on failure.

Tries the primary libgen download path (ads.php -> get.php) first.
If that fails and `try_mirrors` is True, attempts external mirrors
(Anna’s Archive, library.lol, etc.).

Every path that can return a file routes through
[`citeget.validate`](citeget.validate.html.md#module-citeget.validate) first, so an HTML page or a truncated transfer is
reported as a failure rather than saved under the book’s name. An existing
file is re-validated before being accepted as a cached success, so a stub
left by an earlier failure cannot make that failure permanent.

If `page` is provided (a Playwright Page object), reuse it.
Otherwise, creates a new browser session (slower but standalone).

* **Parameters:**
  * **result** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – A result dict from `search()`.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save the file.
  * **page** – Optional Playwright page to reuse.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Download timeout in ms.
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds to wait between page loads (rate limiting).
  * **try_mirrors** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Try external mirror URLs on primary failure.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print diagnostic info on failures.
  * **validate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check that what arrived is really the requested file.
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    `citeget.validate.DEFAULT_POLICY`. Pass
    [`citeget.validate.BOOK_POLICY`](citeget.validate.html.md#citeget.validate.BOOK_POLICY) when the download should be a
    complete book, to also reject excerpts and front-matter samples.
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if download failed.

### citeget.download_results(results, , download_dir='.', max_downloads=0, delay=2.0, headless=True, timeout=60000, verbose=True, distinct=True, validate=True, policy=None)

Download multiple results. Returns list of (result, filepath) tuples.

* **Parameters:**
  * **results** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)) – List of result dicts from `search()`.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save files.
  * **max_downloads** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max number to download (0 = all).
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between downloads (rate limiting).
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Run browser in headless mode.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Per-download timeout in ms.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress.
  * **distinct** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Collapse rows that are the same work in different file
    formats, so `max_downloads=5` means five different works rather
    than five copies of one. Set False for the raw result order.
  * **validate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check that each download really is the requested file.
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)]) – Validation policy (see [`citeget.validate`](citeget.validate.html.md#module-citeget.validate)).
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Returns:**
  List of (result_dict, filepath_or_None) tuples.

### citeget.extract_references(text, , extractor=None)

Extract references from document text.

* **Parameters:**
  * **text** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full document text.
  * **extractor** ([`Extractor`](citeget.extract.html.md#citeget.extract.Extractor) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – An `Extractor` callable, a registered extractor
    name (`str`), or `None` to use the `"default"` chain.
* **Return type:**
  [`ExtractionResult`](citeget.extract.html.md#citeget.extract.ExtractionResult)
* **Returns:**
  [`ExtractionResult`](#citeget.ExtractionResult) with parsed references and metadata.
* **Raises:**
  * [**AIExtractionRequested**](citeget.extract.html.md#citeget.extract.AIExtractionRequested) – If the `"ai"` extractor is selected.
  * [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If a string name is not in the registry.

### citeget.extract_urls_from_text(text)

Parse URLs from prose / markdown / reference-style citations.

Recognized forms (each URL deduped, first match wins):

- `[anchor](https://url)`                    → markdown link
- `[1] Some citation. https://url`           → reference-style
- bare `https://url`                          → fallback

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`UrlEntry`](#citeget.UrlEntry)]

### citeget.fetch(source, , output_dir='~/Downloads', prefer='md', timeout=30, skip_existing=True, on_result=None)

Fetch one or many URLs from a flexible *source*.

* **Parameters:**
  * **source** – A URL, list of URLs, path to a file containing URLs, or
    a string of prose / markdown / reference-style text.
  * **output_dir** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – Where to save files (created if missing).
  * **prefer** ([`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'md'`, `'pdf'`, `'original'`, `'auto'`]) – `"md"` (default), `"pdf"`, `"original"`, or `"auto"`.
    See [`fetch_one()`](#citeget.fetch_one) for details.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – HTTP timeout per request.
  * **skip_existing** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Skip URLs whose inferred output file exists.
  * **on_result** – Optional callback `(index, total, FetchResult) -> None`
    invoked after each fetch (for progress reporting).
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`FetchResult`](#citeget.FetchResult)]
* **Returns:**
  A list of [`FetchResult`](#citeget.FetchResult), one per unique URL.

### citeget.fetch_one(source, , output_dir, prefer='md', timeout=30, skip_existing=True)

Fetch a single URL and save it under *output_dir*.

* **Parameters:**
  * **source** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`UrlEntry`](#citeget.UrlEntry)]) – A URL string or a [`UrlEntry`](#citeget.UrlEntry) (carries title/ref context).
  * **output_dir** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Directory to write into (created if missing).
  * **prefer** ([`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'md'`, `'pdf'`, `'original'`, `'auto'`]) – Output format. `"md"` (default) converts HTML to Markdown;
    PDFs are saved as-is. `"pdf"` tries to keep/produce a PDF
    (requires `pdfkit` for HTML→PDF). `"original"` saves whatever
    content-type the server returned. `"auto"` is like `"md"`
    for HTML and saves PDFs as PDFs.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – HTTP timeout in seconds.
  * **skip_existing** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True (default), skip when the inferred output
    file already exists.
* **Return type:**
  [`FetchResult`](#citeget.FetchResult)
* **Returns:**
  A [`FetchResult`](#citeget.FetchResult) describing what happened.

### citeget.generate_search_queries(ref)

Generate a sequence of search queries from most to least specific.

Returns list of (query_string, description) tuples.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.get_book(title, , authors=None, download_dir='.', query=None, topic='books', max_candidates=5, results_per_page=50, search_attempts=2, headless=True, timeout=45000, delay=1.0, verbose=True, validate=True, policy=None, base_url=None, mirrors=None, \*\*rank_kwargs)

Acquire one copy of a specific book. The “get me *this* book” entry point.

Searches, ranks the results against *title* and *authors*, and downloads the
best candidate that validates as a complete book — as opposed to
[`search_and_download()`](#citeget.search_and_download), which takes libgen’s own ordering.

Simple case:

```default
from citeget import get_book

path = get_book("Crossing the Chasm", authors="Geoffrey A. Moore",
                download_dir="~/books")
```

* **Parameters:**
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The book’s title.
  * **authors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – The author(s), if known. Strongly improves matching, since
    libgen titles alone are noisy.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save the file.
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Override the search string sent to libgen. Defaults to the title
    plus the first author’s surname.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Libgen topic to search (“books”, “fiction”, “articles”, …).
  * **max_candidates** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many ranked candidates to try before giving up.
  * **results_per_page** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many results to fetch to rank.
  * **search_attempts** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many times to re-run a search that came back empty
    before accepting “not found”. Libgen returns a spurious empty result
    set often enough that a single empty answer is weak evidence.
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Headless browser mode.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Page load timeout in ms.
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between page loads (rate limiting).
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress.
  * **validate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check that what arrived is really the requested book.
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    [`citeget.validate.BOOK_POLICY`](citeget.validate.html.md#citeget.validate.BOOK_POLICY).
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Force a single mirror.
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit ordered list of mirror base URLs to try.
  * **\*\*rank_kwargs** – Forwarded to [`citeget.rank.score_result()`](citeget.rank.html.md#citeget.rank.score_result).
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if nothing usable was found.
* **Raises:**
  [**MirrorUnreachableError**](#citeget.MirrorUnreachableError) – if no candidate mirror could be reached.

### citeget.html_to_markdown(html, , source_url='', \*\*markdownify_options)

Convert *html* to clean Markdown.

Uses `markdownify` (MIT). Long paragraphs are left unwrapped, code
blocks become fenced blocks and tables become GitHub-flavoured tables.

* **Parameters:**
  * **html** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The HTML source to convert.
  * **source_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – If given, prepended as an HTML comment provenance line.
  * **markdownify_options** – Overrides for `HTML_TO_MARKDOWN_DEFAULTS`,
    passed to `markdownify`’s `MarkdownConverter`. Unknown option
    names raise `TypeError`. Passing `convert=` drops the default
    `strip=["img"]`, since markdownify accepts only one of the two.
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> print(html_to_markdown("<h1>Hi</h1><p>A <b>bold</b> word.</p>").strip())
# Hi

A **bold** word.
```

Whitespace inside fenced code blocks is content, and is preserved:

```pycon
>>> md = html_to_markdown("<pre><code>def a(): ...\n\n\ndef b(): ...</code></pre>")
>>> "\n\n\n" in md
True
```

### citeget.html_to_pdf(url, , html='')

Render *url* (or *html* fallback) to PDF bytes via pdfkit/wkhtmltopdf.

Returns `None` if pdfkit / wkhtmltopdf is unavailable or rendering fails.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]

### citeget.infer_filename(entry, ext)

Infer a filename for *entry*, ending in `.{ext}`.

Strategy (first non-empty wins):

1. anchor text / citation title (slugified)
2. URL’s last meaningful path segment
3. domain + short hash

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### citeget.list_downloaders()

Return names of all registered downloaders.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.list_extractors()

Return names of all registered extractors.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.list_resolvers()

Return names of all registered resolvers.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.list_strategies()

Return names of all registered strategies.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.merge_extractors(\*extractors)

Run all *extractors*, deduplicate by reference number.

Fields from earlier extractors take priority; later ones fill blanks.

* **Return type:**
  [`Extractor`](citeget.extract.html.md#citeget.extract.Extractor)

### citeget.parse_reference(text, number=0)

Parse a reference string into a Reference object.

* **Return type:**
  [`Reference`](citeget.acquire_references.html.md#citeget.acquire_references.Reference)

Handles formats like:
: [1] A. Author, “Title,” in *Venue*, year. URL
  A. Author, “Title,” Venue, vol. X, pp. Y-Z, year.

### citeget.parse_references_section(text)

Parse a references section into a list of Reference objects.

Expects lines starting with [N] as reference entries.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.rank_results(results, , title, authors=None, \*\*kwargs)

Return `results` as [`ScoredResult`](#citeget.ScoredResult) objects, best match first.

`kwargs` are forwarded to [`score_result()`](#citeget.score_result) (`format_preference`,
`language`, `weights`, `size_bounds`, `decoy_pattern`).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.regex_extractor(, section_patterns=('(?mi)^#{1,3}\\\\\\\\s\*(references|bibliography|works\\\\\\\\s+cited|literature)\\\\\\\\s\*$',), entry_pattern='^\\\\\\\\s\*\\\\\\\\[(\\\\\\\\d+)\\\\\\\\]', stop_pattern='(?m)^#{1,3}\\\\\\\\s+\\\\\\\\S', whole_document_fallback=True)

Create an extractor from regex patterns.

* **Parameters:**
  * **section_patterns** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]) – Regexes to find the start of a references section.
    Tried in order; first match wins.  Pass `()` to skip header
    detection entirely.
  * **entry_pattern** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Regex matching the start of a reference entry.
    Must have group(1) capturing the reference number.
  * **stop_pattern** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Regex signalling the end of the section (e.g. a new
    heading).  `None` means extract to end of text.
  * **whole_document_fallback** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If no section header is found, scan the
    whole document for *entry_pattern* matches.
* **Return type:**
  [`Extractor`](citeget.extract.html.md#citeget.extract.Extractor)

### citeget.register_downloader(name, downloader)

Register a named downloader.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.register_extractor(name, extractor)

Register a named extractor.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.register_resolver(name, resolver)

Register a named URL resolver.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.register_strategy(name, strategy)

Register a named acquisition strategy.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.resolve_and_download(resolver, , downloader=None)

Create a strategy that resolves URLs then tries to download each.

* **Parameters:**
  * **resolver** ([`UrlResolver`](citeget.resolve.html.md#citeget.resolve.UrlResolver) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A `UrlResolver` callable or registered name.
  * **downloader** ([`Downloader`](citeget.resolve.html.md#citeget.resolve.Downloader) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – A `Downloader` callable or registered name.
    `None` uses the `"pdf"` downloader.
* **Return type:**
  [`AcquisitionStrategy`](citeget.resolve.html.md#citeget.resolve.AcquisitionStrategy)

### citeget.resolve_reference(ref, filepath, , strategy=None)

Resolve and download a single reference.

* **Parameters:**
  * **ref** ([`Reference`](citeget.acquire_references.html.md#citeget.acquire_references.Reference)) – The reference to acquire.
  * **filepath** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Target file path for the download.
  * **strategy** ([`AcquisitionStrategy`](citeget.resolve.html.md#citeget.resolve.AcquisitionStrategy) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – An `AcquisitionStrategy` callable, a registered
    strategy name (`str`), or `None` to use `"default"`.
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Filepath string on success, `None` on failure.
* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If a string name is not in the registry.

### citeget.resolve_work_dir(reference_file=None, work_dir=None)

Resolve the working directory for an acquisition session.

Rules:

- If `work_dir` is given as a full path, use it (create if needed,
  parent must exist).
- If `work_dir` is a bare name (no slashes), use `~/Downloads/{name}`.
- If `work_dir` is None and `reference_file` is given, derive from the
  reference file: `{stem} -- acquired_references/` in the same directory.
- If neither is given, raise ValueError.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
* **Returns:**
  Resolved Path to the working directory.
* **Raises:**
  * [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If inputs are insufficient or invalid.
  * [**FileNotFoundError**](https://docs.python.org/3/builtins/exceptions.html#FileNotFoundError) – If a specified parent directory doesn’t exist.

### citeget.score_result(result, \*, title, authors=None, format_preference=('pdf', 'epub', 'azw3', 'mobi', 'azw', 'djvu', 'fb2', 'txt'), language='english', weights=ScoreWeights(title=5.0, author=3.0, format=1.2, language=1.0, size=0.8, decoy_penalty=6.0, stub_penalty=3.0), size_bounds=SizeBounds(min_bytes=80000, min_pdf_bytes=300000, implausible_bytes=120000000), decoy_pattern=re.compile('\\\\\\\\b(summary|summaries|workbook|study guide|sparknotes|cliffs?notes|key takeaways|conversation starters|review and analysis|analysis of|insights (?:on|from)|companion to|instaread|blinkist|downloaden|, re.IGNORECASE))

Score one `search()` result against a requested title and author.

* **Parameters:**
  * **result** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – A result dict from [`citeget.search()`](#citeget.search).
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The title actually wanted.
  * **authors** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – The author(s) wanted, in any of the orderings
    [`citeget.names`](citeget.names.html.md#module-citeget.names) understands. None skips author scoring.
  * **format_preference** ([`Sequence`](https://docs.python.org/3/library/typing.html#typing.Sequence)) – File formats, best first.
  * **language** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Preferred language; a result with no language set is treated
    as neutral rather than penalised, since libgen often omits it.
  * **weights** ([`ScoreWeights`](citeget.rank.html.md#citeget.rank.ScoreWeights)) – Per-signal weights.
  * **size_bounds** ([`SizeBounds`](citeget.rank.html.md#citeget.rank.SizeBounds)) – What counts as a plausible file size.
  * **decoy_pattern** ([`Pattern`](https://docs.python.org/3/library/re.html#re.Pattern)) – Title pattern marking derivative or spam listings.
* **Return type:**
  [`ScoredResult`](citeget.rank.html.md#citeget.rank.ScoredResult)

### citeget.search(query, , topic='books', topics=None, results_per_page=100, headless=True, timeout=45000, table_timeout=20000, attempts_per_mirror=2, retry_backoff=2.0, no_table_confirmations=2, base_url=None, mirrors=None)

Search a libgen mirror and return a list of result dicts.

Tries each candidate mirror in order and uses the first one that is
reachable, retrying a mirror that merely timed out before moving on. If
every mirror fails, raises [`MirrorUnreachableError`](#citeget.MirrorUnreachableError) with a message
that says which failure mode it was, rather than a raw browser stack trace.
A mirror that loads but shows no results table is not on its own taken as
“no results”: libgen serves the same page shape for a query with no matches
and for a page whose table has not rendered, so a second mirror has to agree
before `[]` is returned.

* **Parameters:**
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – What to search for — “books”, “articles”, “fiction”, “comics”,
    “magazines”, or “standards”.  Used when `topics` is None.
  * **topics** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Multiple topics to search simultaneously, e.g.
    `("books", "fiction", "articles")`.  Overrides `topic`.
  * **results_per_page** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many results per page (25, 50, or 100).
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Run browser in headless mode (default True).
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Page navigation timeout in ms.
  * **table_timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How long to wait, after the DOM is ready, for the results
    table to be rendered. Also bounds how long an empty result set takes
    to report.
  * **attempts_per_mirror** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many times to try a mirror whose page timed out
    before failing over to the next one. Hard connection failures are
    never retried.
  * **retry_backoff** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds to wait before a retry, multiplied by the attempt
    number.
  * **no_table_confirmations** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many mirrors must load without a results
    table before the query is reported as having no results.
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Force a single mirror (e.g. `https://libgen.vg`). Overrides
    env vars and the default list.
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit ordered list of mirror base URLs to try. Overrides
    `base_url`, env vars, and the default list.
* **Returns:**
  title, authors, publisher, year, language,
  pages, size, extension, doi, series, md5, file_id, libgen_href,
  mirrors, and `base_url` (the mirror the result came from, so the
  download step can resolve the same mirror’s relative links).
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Raises:**
  [**MirrorUnreachableError**](#citeget.MirrorUnreachableError) – if no candidate mirror could be reached.

### citeget.search_and_download(query, , topic='books', download_dir='.', max_downloads=5, results_per_page=100, delay=2.0, headless=True, timeout=30000, verbose=True, distinct=True, validate=True, policy=None, base_url=None, mirrors=None)

Search libgen and download matching results in one shot.

This is the main convenience function. It runs the search, then downloads
up to `max_downloads` results into `download_dir`.

* **Parameters:**
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – “books”, “articles”, “fiction”, etc.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save files.
  * **max_downloads** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max number to download (default 5, 0 = all).
  * **results_per_page** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Results per search page.
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between downloads.
  * **headless** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Headless browser mode.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Timeout in ms for page loads.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress.
  * **distinct** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Count distinct works rather than file formats towards
    `max_downloads`. Libgen lists one edition once per format, so
    without this `max_downloads=5` returns five copies of one book.
  * **validate** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Check that each download really is the requested file.
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)]) – Validation policy (see [`citeget.validate`](citeget.validate.html.md#module-citeget.validate)).
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Force a single mirror. Overrides env vars and the default list.
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit ordered list of mirror base URLs to try.
* **Return type:**
  [*list*](https://docs.python.org/3/builtins/stdtypes.html#list)

To acquire one copy of a *specific* book rather than the top N rows, use
[`get_book()`](#citeget.get_book), which ranks results against the title and author you
asked for.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Returns:**
  List of (result_dict, filepath_or_None) tuples.
* **Raises:**
  [**MirrorUnreachableError**](#citeget.MirrorUnreachableError) – if no candidate mirror could be reached.

### citeget.surnames(authors)

Surnames of every author in *authors*, in order, casing preserved.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> surnames("Tufte, Edward R. (author);Krasny, Dmitry (author)")
['Tufte', 'Krasny']
>>> surnames("Chris Voss & Tahl Raz")
['Voss', 'Raz']
```

### citeget.url_rewriter(, rules=None)

Create a resolver that rewrites known repository URLs to direct PDFs.

* **Parameters:**
  **rules** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Domain-substring → transform mapping.
  `None` uses `BUILTIN_URL_RULES`.
* **Return type:**
  [`UrlResolver`](citeget.resolve.html.md#citeget.resolve.UrlResolver)

### citeget.validate_bytes(body, , extension=None, expected_bytes=None, policy=ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0))

Validate an in-memory response body without writing it to disk.

* **Parameters:**
  * **body** ([`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)) – The bytes received.
  * **extension** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Expected file extension (`"pdf"`, `"epub"`, …). Drives
    the magic-byte and size-floor checks; unknown values relax them.
  * **expected_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Size the search result advertised, for the truncation
    check. None skips it.
  * **policy** ([`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)) – Which checks to apply. See `DEFAULT_POLICY` and
    `BOOK_POLICY`.
* **Return type:**
  [`ValidationResult`](citeget.validate.html.md#citeget.validate.ValidationResult)

```pycon
>>> bool(validate_bytes(b"<!DOCTYPE html><html>...", extension="pdf"))
False
```

### citeget.validate_download(path, , extension=None, expected_bytes=None, policy=ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0))

Validate a file on disk. Extension defaults to the file’s own suffix.

* **Parameters:**
  * **path** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – File to check.
  * **extension** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the expected extension; defaults to `path`’s suffix.
  * **expected_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Size the search result advertised, for the truncation check.
  * **policy** ([`ValidationPolicy`](citeget.validate.html.md#citeget.validate.ValidationPolicy)) – Which checks to apply.
* **Return type:**
  [`ValidationResult`](citeget.validate.html.md#citeget.validate.ValidationResult)

### citeget.write_missed_references_md(failures, output_file)

Write a markdown file listing references that could not be acquired.

### citeget.write_references_md(successes, download_dir, output_file)

Write a references.md with hyperlinks to local downloaded files.

### Modules

| [`acquire_references`](citeget.acquire_references.html.md#module-citeget.acquire_references)   | Tools for acquiring academic references as PDFs.                               |
|---------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`article_pub`](citeget.article_pub.html.md#module-citeget.article_pub)                 | Article publication toolkit — journal profiling, checking, and formatting.     |
| [`cli`](citeget.cli.html.md#module-citeget.cli)                                 | CLI entry points for citeget.                                                  |
| [`core`](citeget.core.html.md#module-citeget.core)                               | Core search and download logic for libgen (libgen.vg-family mirrors).          |
| [`extract`](citeget.extract.html.md#module-citeget.extract)                         | Composable reference extraction from documents.                                |
| [`names`](citeget.names.html.md#module-citeget.names)                             | Author-name parsing for libgen metadata.                                       |
| [`rank`](citeget.rank.html.md#module-citeget.rank)                               | Rank libgen search results against a requested title and author.               |
| [`resolve`](citeget.resolve.html.md#module-citeget.resolve)                         | Composable download and URL-resolution for academic references.                |
| [`validate`](citeget.validate.html.md#module-citeget.validate)                       | Validate that a downloaded file is actually the book or paper it claims to be. |
