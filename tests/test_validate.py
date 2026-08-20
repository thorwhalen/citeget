"""Tests for download validation (issue #6).

Covers both reproductions from the issue — an HTML page saved as a ``.pdf``
book, and a truncated stub that a later run reads back as a cached success —
plus the content-depth checks added in the follow-up comment, where a file has
valid magic bytes and a healthy size but is an excerpt rather than the work.
"""

import zipfile

import pytest

from citeget.validate import (
    BOOK_POLICY,
    DEFAULT_POLICY,
    InvalidDownloadError,
    ValidationPolicy,
    detect_format,
    epub_markup_bytes,
    looks_like_html,
    pdf_page_count,
    validate_bytes,
    validate_download,
)

pypdf = pytest.importorskip("pypdf")

# Floors low enough that these fixtures are judged on content, not file size.
_TINY = ValidationPolicy(min_bytes=100, min_pdf_bytes=100)


def _pdf_bytes(pages: int) -> bytes:
    """A syntactically valid PDF with *pages* blank pages."""
    import io

    writer = pypdf.PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=72, height=72)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _epub_bytes(markup_bytes: int) -> bytes:
    """A minimal EPUB-shaped zip carrying *markup_bytes* of xhtml."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/ch1.xhtml", "x" * markup_bytes)
    return buffer.getvalue()


# --- HTML rejection: reproduction B ----------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        b"<!DOCTYPE html>\n<html><body>hi</body></html>",
        b"<html lang='en'>",
        b"  \n  <!doctype HTML>",
        b"<head><title>Attention Required! | Cloudflare</title></head>",
    ],
)
def test_html_bodies_are_rejected(body):
    assert looks_like_html(body)
    verdict = validate_bytes(body + b"x" * 200_000, extension="pdf")
    assert not verdict
    assert "HTML" in verdict.reason


def test_large_html_page_is_not_a_book():
    """The old code accepted any response over 100 kB. Size is not content."""
    page = b"<!DOCTYPE html>" + b"<p>filler</p>" * 100_000
    assert len(page) > 100_000
    assert not validate_bytes(page, extension="pdf")


# --- magic bytes ------------------------------------------------------------


def test_pdf_magic_required_for_pdf_extension():
    assert validate_bytes(_pdf_bytes(1), extension="pdf", policy=_TINY)
    assert not validate_bytes(b"\x00\x01\x02" + b"x" * 200_000, extension="pdf")


def test_epub_magic_required_for_epub_extension():
    assert validate_bytes(_epub_bytes(50_000), extension="epub", policy=_TINY)
    assert not validate_bytes(b"not a zip" * 5000, extension="epub")


def test_unknown_extension_skips_the_magic_check():
    # We only claim to know signatures for formats we list; an unknown one must
    # not be rejected merely for being unrecognized.
    assert validate_bytes(b"x" * 50_000, extension="xyz")


def test_detect_format_reports_what_it_actually_saw():
    assert detect_format(b"%PDF-1.7") == "pdf"
    assert detect_format(b"PK\x03\x04") == "epub"
    assert detect_format(b"nothing familiar") is None


def test_reason_names_the_detected_format():
    verdict = validate_bytes(_epub_bytes(50_000), extension="pdf", policy=_TINY)
    assert not verdict
    assert "epub" in verdict.reason


# --- size floors and truncation --------------------------------------------


def test_stub_below_the_size_floor_is_rejected():
    verdict = validate_bytes(_pdf_bytes(1), extension="pdf")
    assert not verdict
    assert "too small" in verdict.reason


def test_empty_file_is_rejected():
    assert not validate_bytes(b"", extension="pdf")


def test_truncated_transfer_is_caught_against_advertised_size():
    body = _pdf_bytes(200)
    verdict = validate_bytes(
        body, extension="pdf", expected_bytes=len(body) * 10, policy=_TINY
    )
    assert not verdict
    assert "truncated" in verdict.reason


def test_advertised_size_close_enough_is_accepted():
    body = _pdf_bytes(200)
    assert validate_bytes(
        body, extension="pdf", expected_bytes=int(len(body) * 1.2), policy=_TINY
    )


def test_truncation_check_can_be_disabled():
    body = _pdf_bytes(200)
    lenient = ValidationPolicy(min_bytes=100, min_pdf_bytes=100, truncation_ratio=0)
    assert validate_bytes(
        body, extension="pdf", expected_bytes=len(body) * 10, policy=lenient
    )


# --- content depth: the three books that passed every byte-level check ------


def test_page_count_catches_an_excerpt():
    """A 33-page front-matter sample is a valid PDF and megabytes in size."""
    excerpt = _pdf_bytes(33)
    book_policy = ValidationPolicy(min_bytes=100, min_pdf_bytes=100, min_pages=80)
    verdict = validate_bytes(excerpt, extension="pdf", policy=book_policy)
    assert not verdict
    assert "excerpt" in verdict.reason
    assert verdict.detail["pages"] == 33


def test_page_count_passes_a_full_book():
    book_policy = ValidationPolicy(min_bytes=100, min_pdf_bytes=100, min_pages=80)
    assert validate_bytes(_pdf_bytes(241), extension="pdf", policy=book_policy)


def test_depth_check_is_off_by_default():
    """An 80-page floor is right for a book and badly wrong for an article."""
    assert DEFAULT_POLICY.min_pages == 0
    assert validate_bytes(_pdf_bytes(12), extension="pdf", policy=_TINY)


def test_book_policy_turns_depth_checks_on():
    assert BOOK_POLICY.min_pages >= 80
    assert BOOK_POLICY.min_epub_markup_bytes > 0


def test_epub_markup_volume_distinguishes_compact_book_from_excerpt():
    """File size gets this wrong: a real 272 kB epub must pass where an
    excerpt of similar size fails. Markup volume is the signal that works."""
    policy = ValidationPolicy(
        min_bytes=100, min_pdf_bytes=100, min_epub_markup_bytes=150_000
    )
    full = _epub_bytes(400_000)  # lots of text, compresses to a small file
    excerpt = _epub_bytes(20_000)
    # Both are tiny on disk; only the markup measure tells them apart.
    assert len(full) < 5_000 and len(excerpt) < 5_000
    assert validate_bytes(full, extension="epub", policy=policy)
    assert not validate_bytes(excerpt, extension="epub", policy=policy)


def test_pdf_page_count_and_epub_markup_helpers():
    assert pdf_page_count(_pdf_bytes(7)) == 7
    assert pdf_page_count(b"not a pdf") is None
    assert epub_markup_bytes(_epub_bytes(1234)) == 1234
    assert epub_markup_bytes(b"not a zip") is None


# --- file-on-disk API -------------------------------------------------------


def test_validate_download_infers_extension_from_suffix(tmp_path):
    path = tmp_path / "book.pdf"
    path.write_bytes(b"<!DOCTYPE html><html>")
    assert not validate_download(path)


def test_validate_download_missing_file(tmp_path):
    verdict = validate_download(tmp_path / "nope.pdf")
    assert not verdict
    assert "does not exist" in verdict.reason


def test_result_is_falsy_and_can_raise():
    verdict = validate_bytes(b"<html>", extension="pdf")
    assert not verdict
    assert bool(verdict) is False
    with pytest.raises(InvalidDownloadError):
        verdict.raise_if_invalid()
    good = validate_bytes(_pdf_bytes(1), extension="pdf", policy=_TINY)
    assert good.raise_if_invalid() is good


def test_validation_can_be_bypassed_wholesale():
    anything = ValidationPolicy(
        min_bytes=0, min_pdf_bytes=0, require_magic=False, reject_html=False
    )
    assert validate_bytes(b"<html>whatever", extension="pdf", policy=anything)
