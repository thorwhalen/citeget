"""Composable reference extraction from documents.

An **extractor** is any ``Callable[[str], list[Reference]]``.  This module
provides a registry of named extractors, a regex-based factory for creating
new ones, and composition helpers (``chain``, ``merge``) for combining them.

The main entry point is :func:`extract_references`, which runs the default
extraction chain (or a caller-specified extractor) and returns an
:class:`ExtractionResult`.

Usage::

    from citeget.extract import extract_references

    result = extract_references(document_text)
    for ref in result.references:
        print(ref.number, ref.title)

    # Custom extractor
    from citeget.extract import regex_extractor, register
    my_ext = regex_extractor(section_patterns=(r"(?mi)^REFERENCES\\s*$",))
    register("ieee", my_ext)

    # Compose
    from citeget.extract import chain
    combined = chain(my_ext, extract_references)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

from citeget.acquire_references import Reference, parse_reference


# ---------------------------------------------------------------------------
# Protocol & result type
# ---------------------------------------------------------------------------


@runtime_checkable
class Extractor(Protocol):
    """Any callable: ``(str) -> list[Reference]``."""

    def __call__(self, text: str) -> list[Reference]: ...


@dataclass
class ExtractionResult:
    """Result of extracting references from text."""

    references: list[Reference]
    extractor_name: str = ""
    confidence: str = "unknown"  # "high", "medium", "low"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

EXTRACTORS: dict[str, Extractor] = {}


def register(name: str, extractor: Extractor) -> None:
    """Register a named extractor."""
    EXTRACTORS[name] = extractor


def get_extractor(name: str) -> Extractor:
    """Retrieve a registered extractor by name.

    Raises:
        KeyError: If *name* is not registered.
    """
    return EXTRACTORS[name]


def list_extractors() -> list[str]:
    """Return names of all registered extractors."""
    return list(EXTRACTORS.keys())


# ---------------------------------------------------------------------------
# AI-agent signal
# ---------------------------------------------------------------------------


class AIExtractionRequested(Exception):
    """Signal that AI-based extraction should be used.

    Not an error — a control-flow signal caught by the CLI or agent layer.
    """


def ai_extractor(text: str) -> list[Reference]:
    """Placeholder extractor that signals AI extraction is needed."""
    raise AIExtractionRequested(
        "AI-based extraction requested. "
        "This should be caught by the CLI or agent layer."
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

DEFAULT_SECTION_PATTERNS: tuple[str, ...] = (
    r"(?mi)^#{1,3}\s*(references|bibliography|works\s+cited|literature)\s*$",
)


def _find_section(
    text: str,
    section_patterns: tuple[str, ...],
    stop_pattern: str | None,
) -> str | None:
    """Find a references section in *text* using regex patterns."""
    for pattern in section_patterns:
        match = re.search(pattern, text)
        if match:
            rest = text[match.end() :]
            if stop_pattern:
                end_match = re.search(stop_pattern, rest)
                if end_match:
                    return rest[: end_match.start()]
            return rest
    return None


def _strip_markdown(text: str) -> str:
    """Remove markdown bold/italic markers from text."""
    return re.sub(r"\*{1,2}", "", text)


def _extract_entries(text: str, entry_pattern: str) -> list[Reference]:
    """Extract numbered reference entries from *text*."""
    lines = text.split("\n")
    entries: list[Reference] = []
    current_lines: list[str] = []
    current_num = 0

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Strip markdown bold markers for pattern matching
        clean = re.sub(r"\*\*", "", stripped)
        m = re.match(entry_pattern, clean)
        if m:
            if current_lines:
                source = "\n".join(current_lines)
                raw = _strip_markdown(" ".join(current_lines))
                ref = parse_reference(raw, current_num)
                ref.source_text = source
                entries.append(ref)
            current_num = int(m.group(1))
            current_lines = [stripped]
        elif current_lines:
            current_lines.append(stripped)

    if current_lines:
        source = "\n".join(current_lines)
        raw = _strip_markdown(" ".join(current_lines))
        ref = parse_reference(raw, current_num)
        ref.source_text = source
        entries.append(ref)

    return entries


# ---------------------------------------------------------------------------
# Regex extractor factory
# ---------------------------------------------------------------------------


def regex_extractor(
    *,
    section_patterns: tuple[str, ...] = DEFAULT_SECTION_PATTERNS,
    entry_pattern: str = r"^\s*\[(\d+)\]",
    stop_pattern: str | None = r"(?m)^#{1,3}\s+\S",
    whole_document_fallback: bool = True,
) -> Extractor:
    """Create an extractor from regex patterns.

    Args:
        section_patterns: Regexes to find the start of a references section.
            Tried in order; first match wins.  Pass ``()`` to skip header
            detection entirely.
        entry_pattern: Regex matching the start of a reference entry.
            Must have group(1) capturing the reference number.
        stop_pattern: Regex signalling the end of the section (e.g. a new
            heading).  ``None`` means extract to end of text.
        whole_document_fallback: If no section header is found, scan the
            whole document for *entry_pattern* matches.
    """

    def _extract(text: str) -> list[Reference]:
        section_text = _find_section(text, section_patterns, stop_pattern)
        if section_text is None and whole_document_fallback:
            section_text = text
        if section_text is None:
            return []
        return _extract_entries(section_text, entry_pattern)

    # Attach config for serialisation support
    _extract._config = {  # type: ignore[attr-defined]
        "section_patterns": section_patterns,
        "entry_pattern": entry_pattern,
        "stop_pattern": stop_pattern,
        "whole_document_fallback": whole_document_fallback,
    }
    return _extract  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def chain(*extractors: Extractor) -> Extractor:
    """Try *extractors* in order, return the first non-empty result."""

    def _chained(text: str) -> list[Reference]:
        for ext in extractors:
            result = ext(text)
            if result:
                return result
        return []

    return _chained  # type: ignore[return-value]


def merge(*extractors: Extractor) -> Extractor:
    """Run all *extractors*, deduplicate by reference number.

    Fields from earlier extractors take priority; later ones fill blanks.
    """

    def _merged(text: str) -> list[Reference]:
        by_number: dict[int, Reference] = {}
        for ext in extractors:
            for ref in ext(text):
                if ref.number not in by_number:
                    by_number[ref.number] = ref
                else:
                    existing = by_number[ref.number]
                    for fld in ("title", "authors", "year", "venue", "url", "doi"):
                        if not getattr(existing, fld) and getattr(ref, fld):
                            setattr(existing, fld, getattr(ref, fld))
        return sorted(by_number.values(), key=lambda r: r.number)

    return _merged  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Built-in extractors
# ---------------------------------------------------------------------------


def markdown_link_extractor(
    *,
    context_chars: int = 200,
) -> Extractor:
    """Create an extractor that treats every ``[name](url)`` as a reference.

    Each markdown hyperlink becomes a :class:`Reference` with:

    - ``title`` ← the link text (*name*)
    - ``url`` ← the link target
    - ``raw`` ← the surrounding context (up to *context_chars* around the link)
    - ``source_text`` ← same context, preserving original formatting
    - ``year`` ← extracted from context if a 4-digit year is nearby
    - ``authors`` ← extracted from context if text before the link looks
      like an author list (heuristic: comma-separated capitalised words)

    Args:
        context_chars: How many characters of surrounding text to capture
            on each side of the link.
    """
    _link_re = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")

    def _extract(text: str) -> list[Reference]:
        refs: list[Reference] = []
        for i, m in enumerate(_link_re.finditer(text), start=1):
            name = m.group(1)
            url = m.group(2)

            # Gather context around the match
            start = max(0, m.start() - context_chars)
            end = min(len(text), m.end() + context_chars)
            context = text[start:end].strip()

            # Try to extract year from context
            year = ""
            year_match = re.search(r"\b((?:19|20)\d{2})\b", context)
            if year_match:
                year = year_match.group(1)

            # Heuristic for authors: look at text just before the link
            # on the same line for patterns like "Author, Author, ..."
            authors = ""
            pre_text = text[max(0, m.start() - 300) : m.start()]
            # Take the last line fragment before the link
            last_line = pre_text.rsplit("\n", 1)[-1].strip()
            # Strip leading markdown (bullets, bold, brackets)
            last_line = re.sub(r"^[\s\-*>#]+", "", last_line)
            # If it looks like "Surname, Surname, ..." before a quote/title
            author_match = re.match(
                r"^([A-Z][a-z]+(?:\s*,\s*[A-Z][a-z]+)*(?:\s*,?\s*(?:and|&)\s*[A-Z][a-z]+)?)\s*[,.]",
                last_line,
            )
            if author_match:
                authors = author_match.group(1)

            refs.append(
                Reference(
                    number=i,
                    raw=context,
                    title=name,
                    authors=authors,
                    year=year,
                    url=url,
                    source_text=context,
                )
            )
        return refs

    return _extract  # type: ignore[return-value]


def _build_default_extractor() -> Extractor:
    """Build the default extraction chain."""
    # 1. Standard: explicit References/Bibliography header + [N] entries
    standard = regex_extractor(whole_document_fallback=False)

    # 2. Broad: any [N] pattern in the whole document (no header needed)
    broad = regex_extractor(section_patterns=())

    # 3. Bold-numbered: **[N]** patterns (e.g. tiered reference lists)
    bold = regex_extractor(
        section_patterns=(),
        entry_pattern=r"^\s*\*?\*?\[(\d+)\]",
    )

    return chain(standard, broad, bold)


# Register built-ins at import time
register("standard", regex_extractor(whole_document_fallback=False))
register("broad", regex_extractor(section_patterns=()))
register(
    "bold",
    regex_extractor(
        section_patterns=(),
        entry_pattern=r"^\s*\*?\*?\[(\d+)\]",
    ),
)
register("markdown_links", markdown_link_extractor())
register("default", _build_default_extractor())
register("ai", ai_extractor)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def extract_references(
    text: str,
    *,
    extractor: Extractor | str | None = None,
) -> ExtractionResult:
    """Extract references from document text.

    Args:
        text: Full document text.
        extractor: An :class:`Extractor` callable, a registered extractor
            name (``str``), or ``None`` to use the ``"default"`` chain.

    Returns:
        :class:`ExtractionResult` with parsed references and metadata.

    Raises:
        AIExtractionRequested: If the ``"ai"`` extractor is selected.
        KeyError: If a string name is not in the registry.
    """
    if extractor is None:
        ext = EXTRACTORS["default"]
        name = "default"
    elif isinstance(extractor, str):
        ext = get_extractor(extractor)
        name = extractor
    else:
        ext = extractor
        name = getattr(extractor, "__name__", "custom")

    refs = ext(text)
    confidence = "high" if len(refs) >= 3 else ("medium" if refs else "low")

    return ExtractionResult(
        references=refs,
        extractor_name=name,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Persistence (save/load regex-based extractors)
# ---------------------------------------------------------------------------


def save_extractors(
    path: str | Path,
    *,
    names: list[str] | None = None,
) -> None:
    """Save regex-based extractors to a JSON file.

    Only extractors whose underlying callable carries a ``_config`` dict
    (i.e. those created via :func:`regex_extractor`) can be serialised.
    Built-in names (``default``, ``ai``) are skipped.

    Args:
        path: JSON file to write.
        names: Extractor names to save.  ``None`` saves all serialisable ones.
    """
    skip = {"default", "ai"}
    data: dict[str, dict] = {}
    for name, ext in EXTRACTORS.items():
        if name in skip:
            continue
        if names is not None and name not in names:
            continue
        config = getattr(ext, "_config", None)
        if config is not None:
            data[name] = config

    Path(path).write_text(json.dumps(data, indent=2))


def load_extractors(path: str | Path) -> list[str]:
    """Load extractors from a JSON file and register them.

    Returns:
        Names of the extractors that were loaded and registered.
    """
    data = json.loads(Path(path).read_text())
    loaded: list[str] = []
    for name, config in data.items():
        # Convert lists back to tuples where needed
        if "section_patterns" in config:
            config["section_patterns"] = tuple(config["section_patterns"])
        ext = regex_extractor(**config)
        register(name, ext)
        loaded.append(name)
    return loaded
