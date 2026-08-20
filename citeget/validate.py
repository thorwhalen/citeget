"""Validate that a downloaded file is actually the book or paper it claims to be.

Nothing about a successful HTTP transfer says the bytes are a document. Libgen
download paths routinely hand back HTML error pages, captcha walls and
truncated stubs, and — more subtly — perfectly valid PDFs that are a 17-page
front-matter sample catalogued under the full book's title. This module is the
one place that decides whether a download is acceptable, so every download path
in :mod:`citeget.core` can route through it.

Two tiers of check, because they answer different questions:

- **Integrity** (always on): magic bytes matching the expected extension, no
  HTML body, a realistic size floor, and — when the caller knows what libgen
  advertised — a truncation check against that size.
- **Depth** (opt-in, see :data:`BOOK_POLICY`): is there enough *content* here to
  be the whole work? A PDF page count and an EPUB markup-volume measure catch
  excerpts and reviews that pass every integrity check.

Depth is opt-in because it is only meaningful when you know what you asked for:
an 80-page floor is right for a book and badly wrong for a journal article.

Simple case — validate a finished download::

    from citeget.validate import validate_download

    verdict = validate_download("book.pdf")
    if not verdict:
        print(verdict.reason)

Stricter, when the file is supposed to be a complete book::

    from citeget.validate import validate_download, BOOK_POLICY

    verdict = validate_download("book.pdf", policy=BOOK_POLICY)

Tune without editing this module by building your own policy::

    from dataclasses import replace
    lenient = replace(BOOK_POLICY, min_pages=40)

PDF page counting uses ``pypdf`` when it is installed and is skipped (with the
check reported as inconclusive rather than failed) when it is not.
"""

import zipfile
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Optional, Union

__all__ = [
    "ValidationPolicy",
    "ValidationResult",
    "InvalidDownloadError",
    "DEFAULT_POLICY",
    "BOOK_POLICY",
    "MAGIC_SIGNATURES",
    "validate_bytes",
    "validate_download",
    "looks_like_html",
    "detect_format",
    "pdf_page_count",
    "epub_markup_bytes",
]

# Leading bytes that identify each format we know how to download. A format may
# have several accepted signatures (mobi variants), and the offset is not always
# zero (djvu wraps its data in an IFF container).
MAGIC_SIGNATURES = {
    "pdf": ((0, b"%PDF"),),
    "epub": ((0, b"PK\x03\x04"), (0, b"PK\x05\x06"), (0, b"PK\x07\x08")),
    "mobi": ((60, b"BOOKMOBI"), (0, b"TPZ"), (60, b"TEXtREAd")),
    "azw": ((60, b"BOOKMOBI"), (0, b"TPZ")),
    "azw3": ((60, b"BOOKMOBI"), (0, b"TPZ")),
    "djvu": ((0, b"AT&TFORM"),),
    "djv": ((0, b"AT&TFORM"),),
    "fb2": ((0, b"<?xml"), (0, b"PK\x03\x04"), (0, b"\xef\xbb\xbf<?xml")),
    "zip": ((0, b"PK\x03\x04"),),
    "rar": ((0, b"Rar!"),),
    "chm": ((0, b"ITSF"),),
    "doc": ((0, b"\xd0\xcf\x11\xe0"),),
    "docx": ((0, b"PK\x03\x04"),),
}

# Openings that mean "this is a web page", never a document. Compared against a
# lowercased, whitespace-stripped prefix of the body.
_HTML_OPENINGS = (
    b"<!doctype html",
    b"<html",
    b"<head",
    b'<?xml version="1.0" encoding="utf-8"?><!doctype html',
    b"<script",
    b"<body",
)

# How much of the file the magic-byte and HTML checks need to look at.
_HEAD_BYTES = 2048

# A transfer that stopped early is far below the advertised size. Coarse
# libgen size strings ("2 MB") make anything tighter than this unreliable.
_TRUNCATION_RATIO = 0.5


class InvalidDownloadError(RuntimeError):
    """Raised when downloaded bytes are not a usable copy of the requested file."""


@dataclass(frozen=True)
class ValidationPolicy:
    """What counts as an acceptable download.

    Attributes:
        min_bytes: Absolute floor below which nothing can be a real document.
        min_pdf_bytes: Higher floor for PDFs, which is where landing-page stubs
            show up. A genuine short EPUB can be ~100 kB, so this cannot be a
            single shared floor.
        require_magic: Reject a file whose leading bytes do not match its
            extension. Unknown extensions are always accepted.
        reject_html: Reject a body that opens like an HTML document.
        truncation_ratio: Reject a file smaller than this fraction of the size
            the search result advertised. Set to 0 to disable.
        min_pages: Minimum PDF page count (0 disables the check). Only sensible
            when the caller knows the download should be a complete book.
        min_epub_markup_bytes: Minimum total size of the markup entries inside
            an EPUB (0 disables). Measures content volume rather than file size,
            so a small-but-complete EPUB passes where a raw size floor fails.
    """

    min_bytes: int = 10_000
    min_pdf_bytes: int = 50_000
    require_magic: bool = True
    reject_html: bool = True
    truncation_ratio: float = _TRUNCATION_RATIO
    min_pages: int = 0
    min_epub_markup_bytes: int = 0


@dataclass(frozen=True)
class ValidationResult:
    """Verdict on a download, plus the measurements behind it.

    Falsy when the download is unacceptable, so it reads naturally::

        if not validate_download(path):
            ...
    """

    ok: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.ok

    def raise_if_invalid(self) -> "ValidationResult":
        """Return self when valid, else raise :class:`InvalidDownloadError`."""
        if not self.ok:
            raise InvalidDownloadError(self.reason)
        return self


DEFAULT_POLICY = ValidationPolicy()

#: Integrity plus content-depth checks, for downloads that should be a complete
#: book. The page floor is set where excerpts and front-matter samples fall:
#: full books under 80 pages are rare, whereas samples are almost always well
#: under it.
BOOK_POLICY = replace(
    DEFAULT_POLICY,
    min_pdf_bytes=300_000,
    min_pages=80,
    min_epub_markup_bytes=150_000,
)


def looks_like_html(head: bytes) -> bool:
    """True if *head* opens like an HTML document rather than a binary file.

    >>> looks_like_html(b"<!DOCTYPE html>\\n<html>")
    True
    >>> looks_like_html(b"%PDF-1.7")
    False
    """
    stripped = (head or b"").lstrip()[:200].lower()
    return any(stripped.startswith(opening) for opening in _HTML_OPENINGS)


def detect_format(head: bytes) -> Optional[str]:
    """Best-guess format name from magic bytes, or None if unrecognized.

    >>> detect_format(b"%PDF-1.4")
    'pdf'
    """
    for name, signatures in MAGIC_SIGNATURES.items():
        if name in ("azw", "azw3", "djv", "zip", "docx"):
            continue  # aliases of a format already listed; keep the report simple
        if _matches_any_signature(head, signatures):
            return name
    return None


def _matches_any_signature(head: bytes, signatures) -> bool:
    """True if *head* starts with any (offset, magic) pair in *signatures*."""
    return any(
        head[offset : offset + len(magic)] == magic for offset, magic in signatures
    )


def pdf_page_count(source: Union[str, Path, bytes]) -> Optional[int]:
    """Page count of a PDF, or None if it cannot be determined.

    Returns None — rather than raising — when ``pypdf`` is not installed, so a
    missing optional dependency downgrades the check instead of failing it.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return None

    import io

    try:
        stream = io.BytesIO(source) if isinstance(source, bytes) else str(source)
        return len(PdfReader(stream, strict=False).pages)
    except Exception:
        return None


def epub_markup_bytes(source: Union[str, Path, bytes]) -> Optional[int]:
    """Total uncompressed size of the markup entries in an EPUB, or None.

    Measures how much text the book actually contains, which distinguishes a
    complete-but-compact EPUB from an excerpt far better than file size does.
    """
    import io

    try:
        stream = io.BytesIO(source) if isinstance(source, bytes) else str(source)
        with zipfile.ZipFile(stream) as zf:
            return sum(
                info.file_size
                for info in zf.infolist()
                if info.filename.lower().endswith((".xhtml", ".html", ".htm"))
            )
    except Exception:
        return None


def _size_checks(size: int, extension: str, policy: ValidationPolicy, detail: dict):
    """Return a failure reason for *size*, or None if the size is plausible."""
    floor = policy.min_pdf_bytes if extension == "pdf" else policy.min_bytes
    if size < floor:
        return f"file too small ({size:,} bytes < {floor:,} floor for {extension or 'file'})"
    expected = detail.get("expected_bytes")
    if expected and policy.truncation_ratio:
        if size < expected * policy.truncation_ratio:
            return (
                f"truncated transfer: {size:,} bytes for a file advertised as "
                f"{expected:,} bytes"
            )
    return None


def _depth_checks(
    source: Union[bytes, Path], extension: str, policy: ValidationPolicy, detail: dict
):
    """Return a failure reason from the content-depth checks, or None."""
    if extension == "pdf" and policy.min_pages:
        pages = pdf_page_count(source)
        detail["pages"] = pages
        if pages is not None and pages < policy.min_pages:
            return (
                f"only {pages} pages: this looks like an excerpt or review, not "
                f"the full work (expected at least {policy.min_pages})"
            )
    if extension == "epub" and policy.min_epub_markup_bytes:
        markup = epub_markup_bytes(source)
        detail["epub_markup_bytes"] = markup
        if markup is not None and markup < policy.min_epub_markup_bytes:
            return (
                f"only {markup:,} bytes of markup: this looks like an excerpt, "
                f"not the full work (expected at least "
                f"{policy.min_epub_markup_bytes:,})"
            )
    return None


def _validate(
    source: Union[bytes, Path],
    head: bytes,
    size: int,
    *,
    extension: Optional[str],
    expected_bytes: Optional[int],
    policy: ValidationPolicy,
) -> ValidationResult:
    """Shared body of :func:`validate_bytes` and :func:`validate_download`."""
    extension = (extension or "").lower().lstrip(".")
    detail = {
        "size": size,
        "extension": extension,
        "expected_bytes": expected_bytes,
        "detected_format": detect_format(head),
    }

    if size == 0:
        return ValidationResult(False, "file is empty", detail)

    if policy.reject_html and looks_like_html(head):
        return ValidationResult(
            False, "response is an HTML page, not a document", detail
        )

    signatures = MAGIC_SIGNATURES.get(extension)
    if (
        policy.require_magic
        and signatures
        and not _matches_any_signature(head, signatures)
    ):
        detected = detail["detected_format"] or "unrecognized data"
        return ValidationResult(
            False,
            f"content is not a {extension} file (leading bytes look like {detected})",
            detail,
        )

    reason = _size_checks(size, extension, policy, detail)
    if reason:
        return ValidationResult(False, reason, detail)

    reason = _depth_checks(source, extension, policy, detail)
    if reason:
        return ValidationResult(False, reason, detail)

    return ValidationResult(True, "", detail)


def validate_bytes(
    body: bytes,
    *,
    extension: Optional[str] = None,
    expected_bytes: Optional[int] = None,
    policy: ValidationPolicy = DEFAULT_POLICY,
) -> ValidationResult:
    """Validate an in-memory response body without writing it to disk.

    Args:
        body: The bytes received.
        extension: Expected file extension (``"pdf"``, ``"epub"``, ...). Drives
            the magic-byte and size-floor checks; unknown values relax them.
        expected_bytes: Size the search result advertised, for the truncation
            check. None skips it.
        policy: Which checks to apply. See :data:`DEFAULT_POLICY` and
            :data:`BOOK_POLICY`.

    >>> bool(validate_bytes(b"<!DOCTYPE html><html>...", extension="pdf"))
    False
    """
    body = body or b""
    return _validate(
        body,
        body[:_HEAD_BYTES],
        len(body),
        extension=extension,
        expected_bytes=expected_bytes,
        policy=policy,
    )


def validate_download(
    path: Union[str, Path],
    *,
    extension: Optional[str] = None,
    expected_bytes: Optional[int] = None,
    policy: ValidationPolicy = DEFAULT_POLICY,
) -> ValidationResult:
    """Validate a file on disk. Extension defaults to the file's own suffix.

    Args:
        path: File to check.
        extension: Override the expected extension; defaults to ``path``'s suffix.
        expected_bytes: Size the search result advertised, for the truncation check.
        policy: Which checks to apply.
    """
    path = Path(path)
    if not path.exists():
        return ValidationResult(False, f"file does not exist: {path}", {"size": 0})
    if extension is None:
        extension = path.suffix.lstrip(".")
    with path.open("rb") as stream:
        head = stream.read(_HEAD_BYTES)
    return _validate(
        path,
        head,
        path.stat().st_size,
        extension=extension,
        expected_bytes=expected_bytes,
        policy=policy,
    )
