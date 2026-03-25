"""CLI entry points for citeget.

Provides search, download, and reference acquisition commands.
Can be used standalone or dispatched via argh.
"""

import argh


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
    print(f"\nDone: {successes}/{len(downloaded)} files downloaded to {download_dir}")


def acquire(
    reference_file: str,
    *,
    work_dir: str = "",
    delay: float = 2.0,
    max_refs: int = 0,
):
    """Acquire PDFs for all references in a document.

    Parses the REFERENCES section, tries direct URL, libgen, arxiv,
    and sci-hub, then writes references.md and a missed-references file.

    Args:
        reference_file: Path to a document containing a references section.
        work_dir: Working directory (default: derived from reference_file).
        delay: Seconds between operations (rate limiting).
        max_refs: Max references to process (0 = all).
    """
    from pathlib import Path
    from datetime import datetime
    from citeget import (
        parse_references_section,
        resolve_work_dir,
        acquire_all_references,
        write_references_md,
        write_missed_references_md,
    )

    ref_path = Path(reference_file).expanduser()
    text = ref_path.read_text()

    # Find references section
    for marker in ("## REFERENCES", "## References", "# References", "# REFERENCES"):
        idx = text.find(marker)
        if idx != -1:
            refs_text = text[idx:]
            break
    else:
        print("ERROR: Could not find a references section.")
        return

    refs = parse_references_section(refs_text)
    if not refs:
        print("No references found.")
        return

    if max_refs > 0:
        refs = refs[:max_refs]

    wd = resolve_work_dir(
        reference_file=ref_path if not work_dir else None,
        work_dir=work_dir or None,
    )
    dl_dir = wd / "references"

    print(f"Parsed {len(refs)} references")
    print(f"Work dir: {wd}")
    print(f"Download dir: {dl_dir}\n")

    successes, failures, _ = acquire_all_references(
        refs, download_dir=dl_dir, work_dir=wd, delay=delay,
    )

    write_references_md(successes, dl_dir, wd / "references.md")
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    write_missed_references_md(failures, wd / f"{ts}_missed_references.md")

    print(f"\nAcquired: {len(successes)}/{len(successes) + len(failures)}")
    print(f"Output: {wd}")


def main():
    """CLI dispatcher."""
    argh.dispatch_commands([search, download, acquire])


if __name__ == "__main__":
    main()
