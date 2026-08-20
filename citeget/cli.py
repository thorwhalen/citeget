"""CLI entry points for citeget.

Provides search, download, and reference acquisition commands.
Can be used standalone or dispatched via argh.
"""

import argh
from datetime import datetime


def _ts():
    """Return a bracketed timestamp string for progress messages."""
    return datetime.now().strftime("[%H:%M:%S]")


def search(
    query: str,
    *,
    topic: str = "books",
    results_per_page: int = 100,
    base_url: str = "",
    mirrors: str = "",
):
    """Search libgen and print results as a numbered table.

    Args:
        query: Search terms.
        topic: "books", "articles", "fiction", "comics", "magazines", "standards".
        results_per_page: Results per page (25, 50, or 100).
        base_url: Force a single mirror (e.g. https://libgen.vg).
        mirrors: Comma-separated ordered list of mirror base URLs to try.
    """
    from citeget import search as do_search, MirrorUnreachableError

    mirror_list = [m.strip() for m in mirrors.split(",") if m.strip()] or None

    try:
        results = do_search(
            query,
            topic=topic,
            results_per_page=results_per_page,
            base_url=base_url or None,
            mirrors=mirror_list,
        )
    except MirrorUnreachableError as exc:
        print(f"ERROR: {exc}")
        return

    if not results:
        print("No results found.")
        return

    print(f"Found {len(results)} results:\n")
    for i, r in enumerate(results, 1):
        title = r["title"][:80] or "(no title)"
        authors = r["authors"][:50] or "?"
        year = r["year"] or "?"
        ext = r["extension"]
        size = r["size"]
        print(f"  {i:3d}. [{ext:4s} {size:>8s}] {title}")
        print(f"       {authors} ({year})")
    print()


def download(
    query: str,
    *,
    topic: str = "books",
    download_dir: str = ".",
    max_downloads: int = 5,
    delay: float = 2.0,
    no_distinct: bool = False,
    base_url: str = "",
    mirrors: str = "",
):
    """Search libgen and download top results.

    Counts distinct works towards --max-downloads, since libgen lists one
    edition once per format. To acquire one copy of a specific book, use
    ``citeget get-book`` instead, which ranks results against title and author.

    Args:
        query: Search terms.
        topic: "books", "articles", "fiction", etc.
        download_dir: Directory to save files into.
        max_downloads: Max number of files to download (0 = all).
        delay: Seconds between downloads (rate limiting).
        no_distinct: Take libgen's raw result order, including the same
            edition repeated once per file format.
        base_url: Force a single mirror (e.g. https://libgen.vg).
        mirrors: Comma-separated ordered list of mirror base URLs to try.
    """
    from citeget import search_and_download, MirrorUnreachableError

    mirror_list = [m.strip() for m in mirrors.split(",") if m.strip()] or None

    try:
        downloaded = search_and_download(
            query,
            topic=topic,
            download_dir=download_dir,
            max_downloads=max_downloads,
            delay=delay,
            distinct=not no_distinct,
            base_url=base_url or None,
            mirrors=mirror_list,
        )
    except MirrorUnreachableError as exc:
        print(f"ERROR: {exc}")
        return

    successes = sum(1 for _, f in downloaded if f)
    print(
        f"\n{_ts()} Done: {successes}/{len(downloaded)} files downloaded to {download_dir}"
    )


def acquire(
    reference_file: str,
    *,
    work_dir: str = "",
    delay: float = 2.0,
    max_refs: int = 0,
    extractor: str = "default",
    strategy: str = "",
    preview: bool = False,
    auto: bool = False,
):
    """Acquire PDFs for all references in a document.

    Extracts references (tries headers, then broad [N] scan, then bold),
    then acquires PDFs via direct URL, libgen, arxiv, and sci-hub.

    Args:
        reference_file: Path to a document containing references.
        work_dir: Working directory (default: derived from reference_file).
        delay: Seconds between operations (rate limiting).
        max_refs: Max references to process (0 = all).
        extractor: Named extractor to use (default, standard, broad, bold, ai).
        strategy: Named acquisition strategy (default, direct, doi, arxiv_search,
            semantic_scholar, libgen, scihub). Empty uses legacy chain.
        preview: Show extracted references and ask for confirmation.
        auto: Skip confirmation even in preview mode.
    """
    from pathlib import Path
    from datetime import datetime
    from citeget import (
        resolve_work_dir,
        acquire_all_references,
        write_references_md,
        write_missed_references_md,
    )
    from citeget.extract import extract_references, AIExtractionRequested

    ref_path = Path(reference_file).expanduser()
    text = ref_path.read_text()

    try:
        result = extract_references(text, extractor=extractor)
    except AIExtractionRequested:
        print("AI extraction mode requires an AI agent context.")
        print("Use the 'acquire-references' Claude skill instead.")
        return

    refs = result.references
    if not refs:
        print(
            f"ERROR: Could not extract references (extractor: {result.extractor_name})."
        )
        print("Try: --extractor broad  or  --extractor ai")
        return

    if preview and not auto:
        print(
            f"Extracted {len(refs)} references "
            f"(extractor: {result.extractor_name}, "
            f"confidence: {result.confidence}):\n"
        )
        for ref in refs:
            print(f"  [{ref.number}] {ref.title[:70]}")
            if ref.authors:
                print(f"         {ref.authors[:50]} ({ref.year})")
        response = input("\nProceed with acquisition? [Y/n] ")
        if response.strip().lower() in ("n", "no"):
            return

    if max_refs > 0:
        refs = refs[:max_refs]

    wd = resolve_work_dir(
        reference_file=ref_path if not work_dir else None,
        work_dir=work_dir or None,
    )
    dl_dir = wd / "references"

    print(f"{_ts()} Parsed {len(refs)} references")
    print(f"{_ts()} Work dir: {wd}")
    print(f"{_ts()} Download dir: {dl_dir}\n")

    successes, failures, _ = acquire_all_references(
        refs,
        download_dir=dl_dir,
        work_dir=wd,
        strategy=strategy or None,
        delay=delay,
    )

    write_references_md(successes, dl_dir, wd / "references.md")
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    write_missed_references_md(failures, wd / f"{ts}_missed_references.md")

    print(f"\n{_ts()} Acquired: {len(successes)}/{len(successes) + len(failures)}")
    print(f"{_ts()} Output: {wd}")


def fetch(
    source: str,
    *,
    output_dir: str = "~/Downloads",
    prefer: str = "md",
    timeout: int = 30,
    skip_existing: bool = True,
    manifest: str = "",
):
    """Fetch URLs and save them as Markdown (default), PDF, or original.

    *source* may be a URL, a file path containing URLs, or a string with
    prose / markdown / reference-style citations. Multiple URLs are extracted
    automatically.

    Args:
        source: A URL, file path, or text containing URLs.
        output_dir: Where to save files (default: ~/Downloads).
        prefer: "md" (default), "pdf", "original", or "auto".
            PDF requires the `[fetch]` extra (`pip install citeget[fetch]`)
            and a `wkhtmltopdf` system binary for HTML→PDF conversion.
        timeout: HTTP timeout per request, in seconds.
        skip_existing: If true (default), skip URLs whose output exists.
        manifest: Optional path to write a JSON manifest of results.
    """
    import json
    from pathlib import Path
    from citeget import fetch as do_fetch

    def _on_result(i, total, result):
        title = f" — {result.title[:60]}" if result.title else ""
        ref = f"[{result.ref}] " if result.ref else ""
        if result.status == "ok":
            print(
                f"{_ts()} [{i}/{total}] OK   {ref}{result.url}{title}\n"
                f"           -> {result.output_file.name} ({result.format})"
            )
        elif result.status == "skipped":
            print(f"{_ts()} [{i}/{total}] SKIP {ref}{result.url} (exists)")
        else:
            print(
                f"{_ts()} [{i}/{total}] FAIL {ref}{result.url}: "
                f"{result.error or 'unknown'}"
            )

    results = do_fetch(
        source,
        output_dir=output_dir,
        prefer=prefer,
        timeout=timeout,
        skip_existing=skip_existing,
        on_result=_on_result,
    )

    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    print(f"\n{_ts()} Done: {ok} fetched, {skipped} skipped, {failed} failed")

    if manifest:
        manifest_path = Path(manifest).expanduser()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                [
                    {
                        "url": r.url,
                        "status": r.status,
                        "output_file": str(r.output_file) if r.output_file else None,
                        "format": r.format,
                        "title": r.title,
                        "ref": r.ref,
                        "error": r.error,
                    }
                    for r in results
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"{_ts()} Manifest: {manifest_path}")


def get_book(
    title: str,
    *,
    authors: str = "",
    download_dir: str = ".",
    query: str = "",
    topic: str = "books",
    max_candidates: int = 5,
    base_url: str = "",
    mirrors: str = "",
):
    """Acquire one copy of a specific book, ranked against title and author.

    Unlike ``download``, which takes libgen's own top results (usually the same
    book in several formats), this ranks every result against what you asked
    for and downloads the best candidate that validates as a complete book,
    falling through to the next one if it turns out to be an excerpt or a stub.

    Args:
        title: The book's title.
        authors: The author(s), if known — strongly improves matching.
        download_dir: Directory to save the file into.
        query: Override the libgen search string (defaults to title + surname).
        topic: "books", "fiction", "articles", etc.
        max_candidates: How many ranked candidates to try before giving up.
        base_url: Force a single mirror (e.g. https://libgen.vg).
        mirrors: Comma-separated ordered list of mirror base URLs to try.
    """
    from citeget import get_book as do_get_book, MirrorUnreachableError

    mirror_list = [m.strip() for m in mirrors.split(",") if m.strip()] or None

    try:
        path = do_get_book(
            title,
            authors=authors or None,
            download_dir=download_dir,
            query=query or None,
            topic=topic,
            max_candidates=max_candidates,
            base_url=base_url or None,
            mirrors=mirror_list,
            verbose=True,
        )
    except MirrorUnreachableError as exc:
        print(f"ERROR: {exc}")
        return

    if path:
        from pathlib import Path as _Path

        print(f"\n{_ts()} Saved: {path} ({_Path(path).stat().st_size:,} bytes)")
    else:
        print(
            f"\n{_ts()} No usable copy found for {title!r}. "
            "Try a different --query, or raise --max-candidates."
        )


def check_mirrors(*, mirrors: str = "", query: str = "design of everyday things"):
    """Probe the configured libgen mirrors and report which are healthy.

    Mirror domains rotate, so the shipped default list goes stale on its own
    schedule. Run this when searches start failing: it tells you whether the
    problem is your network or the mirror list, and prints a ready-to-use
    CITEGET_LIBGEN_MIRRORS value for the ones that work.

    Args:
        mirrors: Comma-separated mirrors to probe (defaults to the configured list).
        query: Search terms to probe with (should be something with results).
    """
    from citeget import check_mirrors as do_check

    mirror_list = [m.strip() for m in mirrors.split(",") if m.strip()] or None
    reports = do_check(mirrors=mirror_list, query=query)

    print(f"Probing {len(reports)} mirror(s) with query {query!r}:\n")
    print(f"  {'status':7s} {'mirror':28s} {'hits':>5s}  {'time':>7s}  detail")
    for r in reports:
        status = "OK" if r["ok"] else "FAIL"
        print(
            f"  {status:7s} {r['mirror']:28s} {r['results']:5d}  "
            f"{r['elapsed_ms']:6d}ms  {r['error']}"
        )

    healthy = [r["mirror"] for r in reports if r["ok"] and r["results"]]
    print()
    if healthy:
        print("Working mirrors — use them without editing code:")
        print(f"  export CITEGET_LIBGEN_MIRRORS='{','.join(healthy)}'")
    else:
        print(
            "No mirror returned results. Either every listed domain has moved "
            "(check for current libgen mirrors and pass --mirrors), or your "
            "network/DNS is blocking them."
        )


def main():
    """CLI dispatcher."""
    argh.dispatch_commands([search, download, get_book, acquire, fetch, check_mirrors])


if __name__ == "__main__":
    main()
