# citeget.validate

Validate that a downloaded file is actually the book or paper it claims to be.

Nothing about a successful HTTP transfer says the bytes are a document. Libgen
download paths routinely hand back HTML error pages, captcha walls and
truncated stubs, and — more subtly — perfectly valid PDFs that are a 17-page
front-matter sample catalogued under the full book’s title. This module is the
one place that decides whether a download is acceptable, so every download path
in [`citeget.core`](citeget.core.md#module-citeget.core) can route through it.

Two tiers of check, because they answer different questions:

- **Integrity** (always on): magic bytes matching the expected extension, no
  HTML body, a realistic size floor, and — when the caller knows what libgen
  advertised — a truncation check against that size.
- **Depth** (opt-in, see [`BOOK_POLICY`](#citeget.validate.BOOK_POLICY)): is there enough *content* here to
  be the whole work? A PDF page count and an EPUB markup-volume measure catch
  excerpts and reviews that pass every integrity check.

Depth is opt-in because it is only meaningful when you know what you asked for:
an 80-page floor is right for a book and badly wrong for a journal article.

Simple case — validate a finished download:

```default
from citeget.validate import validate_download

verdict = validate_download("book.pdf")
if not verdict:
    print(verdict.reason)
```

Stricter, when the file is supposed to be a complete book:

```default
from citeget.validate import validate_download, BOOK_POLICY

verdict = validate_download("book.pdf", policy=BOOK_POLICY)
```

Tune without editing this module by building your own policy:

```default
from dataclasses import replace
lenient = replace(BOOK_POLICY, min_pages=40)
```

PDF page counting uses `pypdf` when it is installed and is skipped (with the
check reported as inconclusive rather than failed) when it is not.

### Module Attributes

| [`BOOK_POLICY`](#citeget.validate.BOOK_POLICY)   | Integrity plus content-depth checks, for downloads that should be a complete book.   |
|----------------------------------------------------------------|--------------------------------------------------------------------------------------|

### Functions

| [`validate_bytes`](#citeget.validate.validate_bytes)(body, \*[, extension, ...])    | Validate an in-memory response body without writing it to disk.       |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`validate_download`](#citeget.validate.validate_download)(path, \*[, extension, ...]) | Validate a file on disk.                                              |
| [`looks_like_html`](#citeget.validate.looks_like_html)(head)                         | True if *head* opens like an HTML document rather than a binary file. |
| [`detect_format`](#citeget.validate.detect_format)(head)                           | Best-guess format name from magic bytes, or None if unrecognized.     |
| [`pdf_page_count`](#citeget.validate.pdf_page_count)(source)                        | Page count of a PDF, or None if it cannot be determined.              |
| [`epub_markup_bytes`](#citeget.validate.epub_markup_bytes)(source)                     | Total uncompressed size of the markup entries in an EPUB, or None.    |

### Classes

| [`ValidationPolicy`](#citeget.validate.ValidationPolicy)([min_bytes, min_pdf_bytes, ...])   | What counts as an acceptable download.                  |
|------------------------------------------------------------------------------------------------------|---------------------------------------------------------|
| [`ValidationResult`](#citeget.validate.ValidationResult)(ok[, reason, detail])              | Verdict on a download, plus the measurements behind it. |

### Exceptions

| [`InvalidDownloadError`](#citeget.validate.InvalidDownloadError)   | Raised when downloaded bytes are not a usable copy of the requested file.   |
|-------------------------------------------------------------------------|-----------------------------------------------------------------------------|

### citeget.validate.BOOK_POLICY *= ValidationPolicy(min_bytes=10000, min_pdf_bytes=300000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=80, min_epub_markup_bytes=150000)*

Integrity plus content-depth checks, for downloads that should be a complete
book. The page floor is set where excerpts and front-matter samples fall:
full books under 80 pages are rare, whereas samples are almost always well
under it.

### *exception* citeget.validate.InvalidDownloadError

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

Raised when downloaded bytes are not a usable copy of the requested file.

### *class* citeget.validate.ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0)

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

### *class* citeget.validate.ValidationResult(ok, reason='', detail=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Verdict on a download, plus the measurements behind it.

Falsy when the download is unacceptable, so it reads naturally:

```default
if not validate_download(path):
    ...
```

#### raise_if_invalid()

Return self when valid, else raise [`InvalidDownloadError`](#citeget.validate.InvalidDownloadError).

* **Return type:**
  [`ValidationResult`](#citeget.validate.ValidationResult)

### citeget.validate.detect_format(head)

Best-guess format name from magic bytes, or None if unrecognized.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> detect_format(b"%PDF-1.4")
'pdf'
```

### citeget.validate.epub_markup_bytes(source)

Total uncompressed size of the markup entries in an EPUB, or None.

Measures how much text the book actually contains, which distinguishes a
complete-but-compact EPUB from an excerpt far better than file size does.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

### citeget.validate.looks_like_html(head)

True if *head* opens like an HTML document rather than a binary file.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

```pycon
>>> looks_like_html(b"<!DOCTYPE html>\n<html>")
True
>>> looks_like_html(b"%PDF-1.7")
False
```

### citeget.validate.pdf_page_count(source)

Page count of a PDF, or None if it cannot be determined.

Returns None — rather than raising — when `pypdf` is not installed, so a
missing optional dependency downgrades the check instead of failing it.

* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]

### citeget.validate.validate_bytes(body, , extension=None, expected_bytes=None, policy=ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0))

Validate an in-memory response body without writing it to disk.

* **Parameters:**
  * **body** ([`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)) – The bytes received.
  * **extension** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Expected file extension (`"pdf"`, `"epub"`, …). Drives
    the magic-byte and size-floor checks; unknown values relax them.
  * **expected_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Size the search result advertised, for the truncation
    check. None skips it.
  * **policy** ([`ValidationPolicy`](#citeget.validate.ValidationPolicy)) – Which checks to apply. See `DEFAULT_POLICY` and
    [`BOOK_POLICY`](#citeget.validate.BOOK_POLICY).
* **Return type:**
  [`ValidationResult`](#citeget.validate.ValidationResult)

```pycon
>>> bool(validate_bytes(b"<!DOCTYPE html><html>...", extension="pdf"))
False
```

### citeget.validate.validate_download(path, , extension=None, expected_bytes=None, policy=ValidationPolicy(min_bytes=10000, min_pdf_bytes=50000, require_magic=True, reject_html=True, truncation_ratio=0.5, min_pages=0, min_epub_markup_bytes=0))

Validate a file on disk. Extension defaults to the file’s own suffix.

* **Parameters:**
  * **path** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]) – File to check.
  * **extension** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Override the expected extension; defaults to `path`’s suffix.
  * **expected_bytes** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`int`](https://docs.python.org/3/builtins/functions.html#int)]) – Size the search result advertised, for the truncation check.
  * **policy** ([`ValidationPolicy`](#citeget.validate.ValidationPolicy)) – Which checks to apply.
* **Return type:**
  [`ValidationResult`](#citeget.validate.ValidationResult)
