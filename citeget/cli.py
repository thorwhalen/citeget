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
):
    """Search libgen.vg and print results as a numbered table.

    Args:
        query: Search terms.
        topic: "books", "articles", "fiction", "comics", "magazines", "standards".
        results_per_page: Results per page (25, 50, or 100).
    """
    from citeget import search as do_search

    results = do_search(query, topic=topic, results_per_page=results_per_page)

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
):
    """Search libgen.vg and download top results.

    Args:
        query: Search terms.
        topic: "books", "articles", "fiction", etc.
        download_dir: Directory to save files into.
        max_downloads: Max number of files to download (0 = all).
        delay: Seconds between downloads (rate limiting).
    """
    from citeget import search_and_download

    downloaded = search_and_download(
        query,
        topic=topic,
        download_dir=download_dir,
        max_downloads=max_downloads,
        delay=delay,
    )

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


def main():
    """CLI dispatcher."""
    argh.dispatch_commands([search, download, acquire])


if __name__ == "__main__":
    main()
