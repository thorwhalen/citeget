# citeget.core

Core search and download logic for libgen (libgen.vg-family mirrors).

Requires: playwright (with chromium browser installed).
Install browsers: `python -m playwright install chromium`

The flow:

1. Construct search URL with query + topic
2. Load page in headless Chromium (JS-rendered table)
3. Parse results table into list of dicts
4. For each result to download:
   a. Visit /ads.php to get session key
   b. Download file from /get.php

## Mirror configuration

Libgen mirrors rotate domains often, and a mirror can also be unreachable
because the local network/DNS blocks it (e.g. resolving it to 127.0.0.1).
`search()` therefore tries several mirrors in order and raises
[`MirrorUnreachableError`](#citeget.core.MirrorUnreachableError) with an actionable message if none respond.

Override the mirror list without editing code:

- `CITEGET_LIBGEN_MIRRORS` — comma-separated base URLs (highest precedence)
- `CITEGET_LIBGEN_BASE_URL` — a single base URL
- or pass `base_url=` / `mirrors=` to `search()` / `search_and_download()`

Only libgen.vg-family mirrors (JS `#tablelibgen` layout) are compatible with
this parser; the older libgen.is/.rs/.st forks use different HTML.

### Functions

| [`check_mirrors`](#citeget.core.check_mirrors)(\*[, mirrors, query, topic, ...])    | Probe each configured mirror and report which ones are healthy.           |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`download_best`](#citeget.core.download_best)(results, \*, title[, authors, ...])  | Download the best match for a specific title, falling through on failure. |
| [`download_one`](#citeget.core.download_one)(result, \*[, download_dir, ...])      | Download a single result.                                                 |
| [`download_results`](#citeget.core.download_results)(results, \*[, download_dir, ...]) | Download multiple results.                                                |
| [`get_book`](#citeget.core.get_book)(title, \*[, authors, download_dir, ...])  | Acquire one copy of a specific book.                                      |
| [`search`](#citeget.core.search)(query, \*[, topic, topics, ...])            | Search a libgen mirror and return a list of result dicts.                 |
| [`search_and_download`](#citeget.core.search_and_download)(query, \*[, topic, ...])       | Search libgen and download matching results in one shot.                  |

### Exceptions

| [`MirrorUnreachableError`](#citeget.core.MirrorUnreachableError)   | Raised when no libgen mirror could be reached.   |
|---------------------------------------------------------------------------|--------------------------------------------------|

### *exception* citeget.core.MirrorUnreachableError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when no libgen mirror could be reached.

Distinct from an empty result set: this means every candidate mirror
failed to connect (down, moved, or blocked by local DNS/network), so the
caller gets an actionable message instead of a raw Playwright stack trace.

### citeget.core.check_mirrors(, mirrors=None, query='design of everyday things', topic='books', timeout=45000, table_timeout=20000, headless=True, verbose=False)

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

### citeget.core.download_best(results, , title, authors=None, download_dir='.', max_candidates=5, page=None, timeout=60000, delay=1.0, headless=True, try_mirrors=True, verbose=False, validate=True, policy=None, \*\*rank_kwargs)

Download the best match for a specific title, falling through on failure.

Ranks *results* against the title and author actually wanted (see
[`citeget.rank`](citeget.rank.md#module-citeget.rank)) and downloads them in that order until one validates.
Falling through matters as much as ranking does: libgen catalogues excerpts,
front-matter samples and reviews under the full work’s title, and the next
candidate is usually the real thing.

Candidates are deliberately *not* deduplicated by format here — when the PDF
of a work turns out to be an excerpt, its EPUB often is not.

* **Parameters:**
  * **results** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)) – Result dicts from [`search()`](#citeget.core.search).
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
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    [`citeget.validate.BOOK_POLICY`](citeget.validate.md#citeget.validate.BOOK_POLICY), which also rejects excerpts.
  * **\*\*rank_kwargs** – Forwarded to [`citeget.rank.score_result()`](citeget.rank.md#citeget.rank.score_result)
    (`format_preference`, `language`, `weights`, `size_bounds`,
    `decoy_pattern`).
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if no candidate produced one.

### citeget.core.download_one(result, , download_dir='.', page=None, timeout=60000, delay=1.0, try_mirrors=True, verbose=False, validate=True, policy=None)

Download a single result. Returns the saved file path, or None on failure.

Tries the primary libgen download path (ads.php -> get.php) first.
If that fails and `try_mirrors` is True, attempts external mirrors
(Anna’s Archive, library.lol, etc.).

Every path that can return a file routes through
[`citeget.validate`](citeget.validate.md#module-citeget.validate) first, so an HTML page or a truncated transfer is
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
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    `citeget.validate.DEFAULT_POLICY`. Pass
    [`citeget.validate.BOOK_POLICY`](citeget.validate.md#citeget.validate.BOOK_POLICY) when the download should be a
    complete book, to also reject excerpts and front-matter samples.
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if download failed.

### citeget.core.download_results(results, , download_dir='.', max_downloads=0, delay=2.0, headless=True, timeout=60000, verbose=True, distinct=True, validate=True, policy=None)

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
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.md#citeget.validate.ValidationPolicy)]) – Validation policy (see [`citeget.validate`](citeget.validate.md#module-citeget.validate)).
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Returns:**
  List of (result_dict, filepath_or_None) tuples.

### citeget.core.get_book(title, , authors=None, download_dir='.', query=None, topic='books', max_candidates=5, results_per_page=50, search_attempts=2, headless=True, timeout=45000, delay=1.0, verbose=True, validate=True, policy=None, base_url=None, mirrors=None, \*\*rank_kwargs)

Acquire one copy of a specific book. The “get me *this* book” entry point.

Searches, ranks the results against *title* and *authors*, and downloads the
best candidate that validates as a complete book — as opposed to
[`search_and_download()`](#citeget.core.search_and_download), which takes libgen’s own ordering.

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
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.md#citeget.validate.ValidationPolicy)]) – Validation policy; defaults to
    [`citeget.validate.BOOK_POLICY`](citeget.validate.md#citeget.validate.BOOK_POLICY).
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Force a single mirror.
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit ordered list of mirror base URLs to try.
  * **\*\*rank_kwargs** – Forwarded to [`citeget.rank.score_result()`](citeget.rank.md#citeget.rank.score_result).
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Path to the downloaded file, or None if nothing usable was found.
* **Raises:**
  [**MirrorUnreachableError**](#citeget.core.MirrorUnreachableError) – if no candidate mirror could be reached.

### citeget.core.search(query, , topic='books', topics=None, results_per_page=100, headless=True, timeout=45000, table_timeout=20000, attempts_per_mirror=2, retry_backoff=2.0, no_table_confirmations=2, base_url=None, mirrors=None)

Search a libgen mirror and return a list of result dicts.

Tries each candidate mirror in order and uses the first one that is
reachable, retrying a mirror that merely timed out before moving on. If
every mirror fails, raises [`MirrorUnreachableError`](#citeget.core.MirrorUnreachableError) with a message
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
  [**MirrorUnreachableError**](#citeget.core.MirrorUnreachableError) – if no candidate mirror could be reached.

### citeget.core.search_and_download(query, , topic='books', download_dir='.', max_downloads=5, results_per_page=100, delay=2.0, headless=True, timeout=30000, verbose=True, distinct=True, validate=True, policy=None, base_url=None, mirrors=None)

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
  * **policy** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`ValidationPolicy`](citeget.validate.md#citeget.validate.ValidationPolicy)]) – Validation policy (see [`citeget.validate`](citeget.validate.md#module-citeget.validate)).
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Force a single mirror. Overrides env vars and the default list.
  * **mirrors** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Explicit ordered list of mirror base URLs to try.
* **Return type:**
  [*list*](https://docs.python.org/3/builtins/stdtypes.html#list)

To acquire one copy of a *specific* book rather than the top N rows, use
[`get_book()`](#citeget.core.get_book), which ranks results against the title and author you
asked for.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)
* **Returns:**
  List of (result_dict, filepath_or_None) tuples.
* **Raises:**
  [**MirrorUnreachableError**](#citeget.core.MirrorUnreachableError) – if no candidate mirror could be reached.
