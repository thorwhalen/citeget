# citeget.acquire_references

Tools for acquiring academic references as PDFs.

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

### Module Attributes

| [`MAX_JOB_BYTES_ENV_VAR`](#citeget.acquire_references.MAX_JOB_BYTES_ENV_VAR)   | no budget).                                                                                                                         |
|--------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------|
| [`DEFAULT_MAX_JOB_BYTES`](#citeget.acquire_references.DEFAULT_MAX_JOB_BYTES)   | Most bytes one [`acquire_all_references()`](#citeget.acquire_references.acquire_all_references) run may write into its download directory. |
| [`JOB_BUDGET_NOTE`](#citeget.acquire_references.JOB_BUDGET_NOTE)         | The note on a reference refused because the job's byte budget was spent.                                                            |

### Functions

| [`acquire_all_references`](#citeget.acquire_references.acquire_all_references)(references, ...[, ...])    | Acquire files for a list of references.                              |
|----------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`acquire_reference`](#citeget.acquire_references.acquire_reference)(ref, download_dir, \*, ...)     | Try to acquire a single reference.                                   |
| [`check_existing_downloads`](#citeget.acquire_references.check_existing_downloads)(references, ...)         | Check which references already have downloaded files.                |
| [`generate_search_queries`](#citeget.acquire_references.generate_search_queries)(ref)                      | Generate a sequence of search queries from most to least specific.   |
| [`parse_reference`](#citeget.acquire_references.parse_reference)(text[, number])                   | Parse a reference string into a Reference object.                    |
| [`parse_references_section`](#citeget.acquire_references.parse_references_section)(text)                    | Parse a references section into a list of Reference objects.         |
| [`resolve_work_dir`](#citeget.acquire_references.resolve_work_dir)([reference_file, work_dir])      | Resolve the working directory for an acquisition session.            |
| [`write_missed_references_md`](#citeget.acquire_references.write_missed_references_md)(failures, output_file) | Write a markdown file listing references that could not be acquired. |
| [`write_references_md`](#citeget.acquire_references.write_references_md)(successes, download_dir, ...) | Write a references.md with hyperlinks to local downloaded files.     |

### Classes

| [`AcquisitionResult`](#citeget.acquire_references.AcquisitionResult)(reference[, success, ...])   | Result of trying to acquire a reference.   |
|-------------------------------------------------------------------------------------------------|--------------------------------------------|
| [`Reference`](#citeget.acquire_references.Reference)(number, raw[, title, authors, ...])  | A parsed academic reference.               |

### *class* citeget.acquire_references.AcquisitionResult(reference, success=False, filepath=None, method='', queries_tried=list(), notes='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of trying to acquire a reference.

### citeget.acquire_references.DEFAULT_MAX_JOB_BYTES *= 536870912*

Most bytes one [`acquire_all_references()`](#citeget.acquire_references.acquire_all_references) run may write into its download
directory. The per-response ceiling (`CITEGET_MAX_RESPONSE_BYTES`) bounds one
file; this bounds a job of many references, on a disk shared by every user of
a hosted deployment (#22). Five full-size responses: a job of many books needs
the variable raised, which is the point on a small shared server.

### citeget.acquire_references.JOB_BUDGET_NOTE *= 'job byte budget reached'*

The note on a reference refused because the job’s byte budget was spent.

### citeget.acquire_references.MAX_JOB_BYTES_ENV_VAR *= 'CITEGET_MAX_JOB_BYTES'*

no budget).

* **Type:**
  Environment variable for the per-job byte budget (`0`

### *class* citeget.acquire_references.Reference(number, raw, title='', authors='', year='', venue='', url='', doi='', source_text='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A parsed academic reference.

### citeget.acquire_references.acquire_all_references(references, download_dir, , work_dir=None, log_file=None, strategy=None, libgen_topics=('articles', 'books'), delay=2.0, verbose=True, convert_to_pdf=False, fetch_fallback=True, concurrency_key='auto', max_concurrent_jobs=None, max_job_bytes=None)

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
  * **concurrency_key** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Who this run counts against for the concurrent-run
    cap (see [`citeget.joblimit`](citeget.joblimit.html.md#module-citeget.joblimit)). `"auto"` (default) uses the
    parent of `work_dir`, so runs whose work dirs sit side by side
    (a hosted app’s per-user `jobs/` directory) share one cap; with
    no `work_dir` there is no cap. Pass a string (a user id) to
    choose the key, or `None` to switch the cap off.
  * **max_concurrent_jobs** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – The cap for that key. Defaults to the
    `CITEGET_MAX_CONCURRENT_JOBS` environment variable, else
    [`citeget.joblimit.DEFAULT_MAX_CONCURRENT_JOBS`](citeget.joblimit.html.md#citeget.joblimit.DEFAULT_MAX_CONCURRENT_JOBS); `0` means
    no cap.
  * **max_job_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Most bytes this run may add to `download_dir`.
    Defaults to the `CITEGET_MAX_JOB_BYTES` environment variable, else
    [`DEFAULT_MAX_JOB_BYTES`](#citeget.acquire_references.DEFAULT_MAX_JOB_BYTES); `0` means no budget. Once it is
    spent, the remaining references fail with [`JOB_BUDGET_NOTE`](#citeget.acquire_references.JOB_BUDGET_NOTE)
    instead of being fetched. A reference whose download would overshoot
    it is refused the same way, its file is removed, and the budget
    counts as spent. Every file that appears in `download_dir` while a
    reference is acquired counts, which over-counts (never under-counts)
    when another run shares the directory; files already there before
    the run do not count. A browser download’s temporary spool file
    lives outside `download_dir` and is bounded by the per-response
    ceiling instead.
* **Raises:**
  [**JobLimitExceeded**](citeget.joblimit.html.md#citeget.joblimit.JobLimitExceeded) – the key already has
      `max_concurrent_jobs` runs in progress. Raised before any work.
* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
* **Returns:**
  (successes, failures, log_entries) where successes and failures
  are lists of AcquisitionResult.

### citeget.acquire_references.acquire_reference(ref, download_dir, , log_entries, strategy=None, libgen_topics=('articles', 'books'), timeout=30000, verbose=False, convert_to_pdf=False, fetch_fallback=True)

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
  * **ref** ([`Reference`](#citeget.acquire_references.Reference)) – The reference to acquire.
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
  [`AcquisitionResult`](#citeget.acquire_references.AcquisitionResult)

### citeget.acquire_references.check_existing_downloads(references, download_dir)

Check which references already have downloaded files.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)
* **Returns:**
  (to_acquire, already_have) — two lists of Reference objects.
  `already_have` is a list of (Reference, filepath) tuples.

### citeget.acquire_references.generate_search_queries(ref)

Generate a sequence of search queries from most to least specific.

Returns list of (query_string, description) tuples.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.acquire_references.parse_reference(text, number=0)

Parse a reference string into a Reference object.

Handles formats like:
: [1] A. Author, “Title,” in *Venue*, year. URL
  A. Author, “Title,” Venue, vol. X, pp. Y-Z, year.

* **Return type:**
  [`Reference`](#citeget.acquire_references.Reference)

### citeget.acquire_references.parse_references_section(text)

Parse a references section into a list of Reference objects.

Expects lines starting with [N] as reference entries.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### citeget.acquire_references.resolve_work_dir(reference_file=None, work_dir=None)

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

### citeget.acquire_references.write_missed_references_md(failures, output_file)

Write a markdown file listing references that could not be acquired.

### citeget.acquire_references.write_references_md(successes, download_dir, output_file)

Write a references.md with hyperlinks to local downloaded files.
