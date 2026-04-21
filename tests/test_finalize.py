"""Tests for extension detection, finalize, and convert_to_pdf behavior.

These tests exercise the "no .pdf extension on non-PDFs" invariant and
the optional pdfdol-backed conversion path.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from citeget.acquire_references import (
    Reference,
    _detect_real_extension,
    _finalize_acquired_file,
    _make_ref_basename,
    _try_convert_to_pdf,
    check_existing_downloads,
)


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n" + b"x" * 2000


def _epub_bytes() -> bytes:
    # Minimal ZIP header + mimetype entry contents for EPUB detection.
    return (
        b"PK\x03\x04"
        + b"\x00" * 26
        + b"mimetypeapplication/epub+zip"
        + b"x" * 2000
    )


def _mobi_bytes() -> bytes:
    # 32-byte DB name, 28 bytes of garbage, then BOOKMOBI creator id at 60.
    return b"MyBook" + b"\x00" * 26 + b"\x00" * 28 + b"BOOKMOBI" + b"x" * 2000


def _djvu_bytes() -> bytes:
    return b"CR\x07\x8a" + b"x" * 2000


def _html_bytes() -> bytes:
    return b"<!DOCTYPE html><html><body>Error 404</body></html>"


# ---------------------------------------------------------------------------
# _detect_real_extension
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "content,expected",
    [
        (_pdf_bytes(), ".pdf"),
        (_epub_bytes(), ".epub"),
        (_mobi_bytes(), ".mobi"),
        (_djvu_bytes(), ".djvu"),
        (b"Rar!\x1a\x07\x00" + b"x" * 100, ".rar"),
        (b"ITOLITLS" + b"x" * 100, ".lit"),
        (_html_bytes(), None),
        (b"<html><body>oops</body></html>", None),
        (b"random garbage without a magic", None),
    ],
)
def test_detect_real_extension(tmp_path: Path, content: bytes, expected):
    p = tmp_path / "sample.pdf"
    p.write_bytes(content)
    assert _detect_real_extension(p) == expected


# ---------------------------------------------------------------------------
# _finalize_acquired_file
# ---------------------------------------------------------------------------


def test_finalize_renames_epub(tmp_path: Path):
    src = tmp_path / "Foo.pdf"
    src.write_bytes(_epub_bytes())
    out = _finalize_acquired_file(src)
    assert out is not None
    assert out.suffix == ".epub"
    assert out.exists()
    assert not src.exists()


def test_finalize_keeps_pdf_name(tmp_path: Path):
    src = tmp_path / "Foo.pdf"
    src.write_bytes(_pdf_bytes())
    out = _finalize_acquired_file(src)
    assert out == src
    assert out.suffix == ".pdf"


def test_finalize_deletes_html_junk(tmp_path: Path):
    src = tmp_path / "Foo.pdf"
    src.write_bytes(_html_bytes())
    out = _finalize_acquired_file(src)
    assert out is None
    assert not src.exists()


def test_finalize_moves_to_target_base(tmp_path: Path):
    src = tmp_path / "tempdownload.pdf"
    src.write_bytes(_epub_bytes())
    target_base = tmp_path / "subdir" / "nicely_named_book"
    out = _finalize_acquired_file(src, target_base=target_base)
    assert out == target_base.with_suffix(".epub")
    assert out.exists()
    assert not src.exists()


def test_finalize_never_puts_pdf_on_non_pdf(tmp_path: Path):
    # Even with convert_to_pdf=True, if the converter is unavailable and
    # fails, the file must keep its real extension — never .pdf.
    src = tmp_path / "Foo.pdf"
    src.write_bytes(_epub_bytes())
    # Monkeypatch _try_convert_to_pdf via a patch so conversion "fails".
    import citeget.acquire_references as m

    original = m._try_convert_to_pdf
    try:
        m._try_convert_to_pdf = lambda s, t: None  # type: ignore[assignment]
        out = m._finalize_acquired_file(src, convert_to_pdf=True)
    finally:
        m._try_convert_to_pdf = original

    assert out is not None
    assert out.suffix == ".epub"


def test_finalize_converts_to_pdf_when_converter_available(tmp_path: Path):
    src = tmp_path / "tempdownload.pdf"
    src.write_bytes(_epub_bytes())
    target_base = tmp_path / "Final Book"

    import citeget.acquire_references as m

    # Fake a successful converter: writes a real PDF at the requested target.
    def fake_convert(source: Path, target_pdf: Path):
        target_pdf.write_bytes(_pdf_bytes())
        return target_pdf

    original = m._try_convert_to_pdf
    try:
        m._try_convert_to_pdf = fake_convert  # type: ignore[assignment]
        out = m._finalize_acquired_file(
            src, target_base=target_base, convert_to_pdf=True,
        )
    finally:
        m._try_convert_to_pdf = original

    assert out is not None
    assert out == target_base.with_suffix(".pdf")
    assert out.read_bytes().startswith(b"%PDF")
    assert not src.exists()  # source removed after successful conversion


# ---------------------------------------------------------------------------
# _make_ref_basename
# ---------------------------------------------------------------------------


def test_make_ref_basename_has_no_extension():
    ref = Reference(
        number=1, raw="", title="A Book", authors="Jane Doe", year="2020"
    )
    base = _make_ref_basename(ref)
    assert not base.endswith(".pdf")
    assert "A Book" in base
    assert "Doe" in base
    assert "2020" in base


# ---------------------------------------------------------------------------
# check_existing_downloads — now matches any known extension
# ---------------------------------------------------------------------------


def test_check_existing_downloads_matches_epub(tmp_path: Path):
    ref = Reference(
        number=1, raw="", title="Hunger", authors="Roxane Gay", year="2017"
    )
    base = tmp_path / _make_ref_basename(ref)
    (base.with_suffix(".epub")).write_bytes(_epub_bytes())

    to_acquire, already_have = check_existing_downloads([ref], tmp_path)
    assert to_acquire == []
    assert len(already_have) == 1
    assert already_have[0][1].endswith(".epub")


def test_check_existing_downloads_finds_pdf(tmp_path: Path):
    ref = Reference(
        number=1, raw="", title="Hunger", authors="Roxane Gay", year="2017"
    )
    base = tmp_path / _make_ref_basename(ref)
    (base.with_suffix(".pdf")).write_bytes(_pdf_bytes())

    to_acquire, already_have = check_existing_downloads([ref], tmp_path)
    assert to_acquire == []
    assert len(already_have) == 1
    assert already_have[0][1].endswith(".pdf")


def test_check_existing_downloads_misses_when_absent(tmp_path: Path):
    ref = Reference(
        number=1, raw="", title="Hunger", authors="Roxane Gay", year="2017"
    )
    to_acquire, already_have = check_existing_downloads([ref], tmp_path)
    assert already_have == []
    assert to_acquire == [ref]


# ---------------------------------------------------------------------------
# _try_convert_to_pdf — gracefully absent when pdfdol missing
# ---------------------------------------------------------------------------


def test_try_convert_to_pdf_returns_none_when_converter_missing(tmp_path: Path):
    # An obviously unsupported extension should yield None, never crash.
    src = tmp_path / "weird.foo"
    src.write_bytes(b"xxx")
    target = tmp_path / "out.pdf"
    assert _try_convert_to_pdf(src, target) is None
