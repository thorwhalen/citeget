# Changelog

## Unreleased

### Changed
- **HTML→Markdown conversion now uses `markdownify` (MIT) instead of
  `html2text` (GPL-3.0-or-later).** `html2text` was a *core* dependency of
  this Apache-2.0 package, so `pip install citeget` pulled a copyleft
  distribution. `markdownify>=1.0` replaces it as a core dependency. It adds
  exactly one new distribution to the install closure — `six` (MIT, ~35 KB),
  which `markdownify` requires; `beautifulsoup4` and `soupsieve` were already
  there.

  `html_to_markdown()` keeps its signature and still returns unwrapped
  Markdown, but the *output text differs in detail*: code blocks are now
  fenced rather than indented, tables are GitHub-flavoured, `<title>` and
  other head content is dropped, and intra-page `#anchor` links are kept as
  links rather than flattened to plain text. HTML entities and non-breaking
  spaces are also preserved verbatim where `html2text` folded them to ASCII
  (`&copy;` stays `©` rather than becoming `(C)`, `&nbsp;` stays U+00A0
  rather than becoming a plain space). Callers that diff, grep or
  pattern-match the generated Markdown may need to re-baseline.

  Blank-line runs are normalised **outside fenced code blocks only** — the
  two blank lines PEP 8 puts between top-level `def`s survive conversion.

  The function also gained a `**markdownify_options` pass-through, overriding
  the new `HTML_TO_MARKDOWN_DEFAULTS`. Unknown option names raise `TypeError`
  rather than being silently ignored (which is what `MarkdownConverter` does
  on its own).

## 0.2.0

### Fixed
- **Saved files now always carry their real extension.** Previously, every
  acquired file was named `… .pdf` regardless of actual content — so an
  EPUB or MOBI returned by libgen was saved as `.pdf` and wouldn't open
  on a reader. Files are now saved as `.pdf`, `.epub`, `.mobi`, `.djvu`,
  `.rar`, `.lit`, `.azw`, or `.zip` based on a magic-byte sniff of the
  downloaded bytes. HTML error pages are detected and discarded as
  failures rather than written to disk.

### Added
- `acquire_reference()` and `acquire_all_references()` gained a
  `convert_to_pdf: bool = False` option. When `True`, non-PDF downloads
  are converted to PDF via `pdfdol.tools.get_format_converter` (Calibre's
  `ebook-convert` under the hood). On conversion failure or when the
  converter is missing, the native format is kept — a non-PDF is **never**
  renamed to `.pdf`.
- `check_existing_downloads()` now recognises previously-acquired files
  under any known extension, so reruns won't re-download a book because
  there's no matching `.pdf`.

### Changed (internal)
- Private helper `_make_ref_filename` renamed to `_make_ref_basename`;
  it now returns a basename without an extension. The actual extension
  is decided after download from content. If you were importing this
  private helper, update the name and drop the `.pdf` assumption.
- Protocols `Downloader` and `AcquisitionStrategy` in
  `citeget.resolve` are now documented as treating their `filepath`
  argument as **advisory** — the resulting file may have a different
  extension reflecting the real content format. Existing implementations
  still work; the high-level `acquire_reference` takes care of renaming.
