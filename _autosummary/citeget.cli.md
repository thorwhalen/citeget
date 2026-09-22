# citeget.cli

CLI entry points for citeget.

Provides search, download, and reference acquisition commands.
Can be used standalone or dispatched via cw.

### Functions

| [`acquire`](#citeget.cli.acquire)(reference_file, \*[, work_dir, ...])      | Acquire PDFs for all references in a document.                        |
|----------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`check_mirrors`](#citeget.cli.check_mirrors)(\*[, mirrors, query])               | Probe the configured libgen mirrors and report which are healthy.     |
| [`download`](#citeget.cli.download)(query, \*[, topic, download_dir, ...])   | Search libgen and download top results.                               |
| [`fetch`](#citeget.cli.fetch)(source, \*[, output_dir, prefer, ...])      | Fetch URLs and save them as Markdown (default), PDF, or original.     |
| [`get_book`](#citeget.cli.get_book)(title, \*[, authors, download_dir, ...]) | Acquire one copy of a specific book, ranked against title and author. |
| [`main`](#citeget.cli.main)()                                            | CLI dispatcher.                                                       |
| [`search`](#citeget.cli.search)(query, \*[, topic, results_per_page, ...]) | Search libgen and print results as a numbered table.                  |

### citeget.cli.acquire(reference_file, , work_dir='', delay=2.0, max_refs=0, extractor='default', strategy='', preview=False, auto=False)

Acquire PDFs for all references in a document.

Extracts references (tries headers, then broad [N] scan, then bold),
then acquires PDFs via direct URL, libgen, arxiv, and sci-hub.

* **Parameters:**
  * **reference_file** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to a document containing references.
  * **work_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Working directory (default: derived from reference_file).
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between operations (rate limiting).
  * **max_refs** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max references to process (0 = all).
  * **extractor** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Named extractor to use (default, standard, broad, bold, ai).
  * **strategy** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Named acquisition strategy (default, direct, doi, arxiv_search,
    semantic_scholar, libgen, scihub). Empty uses legacy chain.
  * **preview** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Show extracted references and ask for confirmation.
  * **auto** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Skip confirmation even in preview mode.

### citeget.cli.check_mirrors(, mirrors='', query='design of everyday things')

Probe the configured libgen mirrors and report which are healthy.

Mirror domains rotate, so the shipped default list goes stale on its own
schedule. Run this when searches start failing: it tells you whether the
problem is your network or the mirror list, and prints a ready-to-use
CITEGET_LIBGEN_MIRRORS value for the ones that work.

* **Parameters:**
  * **mirrors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Comma-separated mirrors to probe (defaults to the configured list).
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms to probe with (should be something with results).

### citeget.cli.download(query, , topic='books', download_dir='.', max_downloads=5, delay=2.0, no_distinct=False, base_url='', mirrors='')

Search libgen and download top results.

Counts distinct works towards –max-downloads, since libgen lists one
edition once per format. To acquire one copy of a specific book, use
`citeget get-book` instead, which ranks results against title and author.

* **Parameters:**
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – “books”, “articles”, “fiction”, etc.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Directory to save files into.
  * **max_downloads** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max number of files to download (0 = all).
  * **delay** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Seconds between downloads (rate limiting).
  * **no_distinct** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Take libgen’s raw result order, including the same
    edition repeated once per file format.
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Force a single mirror (e.g. [https://libgen.vg](https://libgen.vg)).
  * **mirrors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Comma-separated ordered list of mirror base URLs to try.

### citeget.cli.fetch(source, , output_dir='~/Downloads', prefer='md', timeout=30, skip_existing=True, manifest='')

Fetch URLs and save them as Markdown (default), PDF, or original.

*source* may be a URL, a file path containing URLs, or a string with
prose / markdown / reference-style citations. Multiple URLs are extracted
automatically.

* **Parameters:**
  * **source** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A URL, file path, or text containing URLs.
  * **output_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Where to save files (default: ~/Downloads).
  * **prefer** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – “md” (default), “pdf”, “original”, or “auto”.
    PDF requires the `[fetch]` extra (`pip install citeget[fetch]`)
    and a `wkhtmltopdf` system binary for HTML→PDF conversion.
  * **timeout** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – HTTP timeout per request, in seconds.
  * **skip_existing** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If true (default), skip URLs whose output exists.
  * **manifest** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Optional path to write a JSON manifest of results.

### citeget.cli.get_book(title, , authors='', download_dir='.', query='', topic='books', max_candidates=5, base_url='', mirrors='')

Acquire one copy of a specific book, ranked against title and author.

Unlike `download`, which takes libgen’s own top results (usually the same
book in several formats), this ranks every result against what you asked
for and downloads the best candidate that validates as a complete book,
falling through to the next one if it turns out to be an excerpt or a stub.

* **Parameters:**
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The book’s title.
  * **authors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The author(s), if known — strongly improves matching.
  * **download_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Directory to save the file into.
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Override the libgen search string (defaults to title + surname).
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – “books”, “fiction”, “articles”, etc.
  * **max_candidates** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many ranked candidates to try before giving up.
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Force a single mirror (e.g. [https://libgen.vg](https://libgen.vg)).
  * **mirrors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Comma-separated ordered list of mirror base URLs to try.

### citeget.cli.main()

CLI dispatcher. Returns the exit code.

`cw.dispatch` returns the exit code rather than exiting, so the caller
turns it into a process status: the console script does `sys.exit(main())`
and `citeget/__main__.py` does `raise SystemExit(main())`.

### citeget.cli.search(query, , topic='books', results_per_page=100, base_url='', mirrors='')

Search libgen and print results as a numbered table.

* **Parameters:**
  * **query** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Search terms.
  * **topic** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – “books”, “articles”, “fiction”, “comics”, “magazines”, “standards”.
  * **results_per_page** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Results per page (25, 50, or 100).
  * **base_url** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Force a single mirror (e.g. [https://libgen.vg](https://libgen.vg)).
  * **mirrors** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Comma-separated ordered list of mirror base URLs to try.
