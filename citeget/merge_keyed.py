"""Merge keyed-citation Markdown parts into one Vancouver-numbered document.

A long cited document written in parts (one writer or agent per chapter) cites
with stable keys that survive the split. Each part is a Markdown body, then an
optional ``<!-- REFERENCES -->`` section of ``KEY | entry`` lines, then an
optional ``<!-- GLOSSARY -->`` section of ``Term | definition`` lines::

    ... as shown by {ref:smith2020} and {ref:lee2019}.
    <!-- REFERENCES -->
    smith2020 | Smith J. A title. Journal. 2020.
    <!-- GLOSSARY -->
    Widget | A thing.

:func:`merge_keyed` turns inline ``{ref:KEY}`` into ``[n]``, numbered in order
of first appearance across all parts; dedupes entries shared by several parts;
and appends one References list and one merged glossary (or fills the
``{{REFERENCES}}`` / ``{{GLOSSARY}}`` placeholders of *tail*). Use
:func:`merge_keyed_report` to also get the missing keys and the keys whose
entries disagree between parts.
"""

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional

DFLT_CITE_PATTERN = r"\{ref:([^}]+)\}"
REFERENCES_MARK = "<!-- REFERENCES -->"
GLOSSARY_MARK = "<!-- GLOSSARY -->"
REFERENCES_PLACEHOLDER = "{{REFERENCES}}"
GLOSSARY_PLACEHOLDER = "{{GLOSSARY}}"
MISSING_ENTRY = "MISSING {key}"


@dataclass
class MergedDocument:
    """The merged text plus what a caller needs to check it."""

    text: str
    order: dict[str, int] = field(default_factory=dict)  # key -> number
    missing: list[str] = field(default_factory=list)  # cited, never defined
    conflicts: dict[str, list[str]] = field(default_factory=dict)  # key -> entries
    glossary: dict[str, str] = field(default_factory=dict)


def _pairs(block: str) -> list[tuple[str, str]]:
    """``KEY | value`` lines of *block* (optional leading ``-`` bullet)."""
    out = []
    for line in block.splitlines():
        line = line.strip().lstrip("-").strip()
        if "|" in line:
            key, value = line.split("|", 1)
            out.append((key.strip(), value.strip()))
    return out


def parse_part(text: str) -> tuple[str, list[tuple[str, str]], list[tuple[str, str]]]:
    """Split a part into ``(body, reference pairs, glossary pairs)``."""
    body, _, rest = text.partition(REFERENCES_MARK)
    if not _:  # no references section: a glossary may still follow the body
        body, _, gloss = text.partition(GLOSSARY_MARK)
        return body.strip(), [], _pairs(gloss)
    refs, _, gloss = rest.partition(GLOSSARY_MARK)
    return body.strip(), _pairs(refs), _pairs(gloss)


def merge_keyed_report(
    parts: Iterable[str],
    *,
    head: Optional[str] = None,
    tail: Optional[str] = None,
    cite_pattern: str = DFLT_CITE_PATTERN,
    missing_entry: str = MISSING_ENTRY,
) -> MergedDocument:
    """Merge *parts* (Markdown strings); see the module docstring.

    Args:
        parts: Part texts, in document order.
        head: Text placed before the first part.
        tail: Text placed after the last part; may contain ``{{REFERENCES}}``
            and ``{{GLOSSARY}}``. Default: a ``## References`` section and, if
            any term was defined, a ``## Glossary`` section.
        cite_pattern: Regex with one group capturing the key.
        missing_entry: Template for a cited key with no entry (``{key}``).
    """
    cite_re = re.compile(cite_pattern)
    bodies: list[str] = []
    refs: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    glossary: dict[str, str] = {}
    for part in parts:
        body, ref_pairs, gloss_pairs = parse_part(part)
        bodies.append(body)
        for key, entry in ref_pairs:
            if key not in refs:
                refs[key] = entry
            elif refs[key] != entry:
                conflicts.setdefault(key, [refs[key]])
                if entry not in conflicts[key]:
                    conflicts[key].append(entry)
        for term, definition in gloss_pairs:
            glossary.setdefault(term, definition)

    text = "\n\n".join(s for s in [(head or "").strip(), *bodies] if s)
    order: dict[str, int] = {}
    for key in cite_re.findall(text):
        order.setdefault(key.strip(), len(order) + 1)
    text = cite_re.sub(lambda m: f"[{order[m.group(1).strip()]}]", text)

    missing = [k for k in order if k not in refs]
    reflist = "\n\n".join(
        f"[{n}] {refs[k] if k in refs else missing_entry.format(key=k)}"
        for k, n in order.items()
    )
    glossary_md = "\n\n".join(
        f"**{term}**: {definition}"
        for term, definition in sorted(glossary.items(), key=lambda kv: kv[0].lower())
    )
    if tail is None:
        sections = [f"## References\n\n{reflist}"] if reflist else []
        if glossary_md:
            sections.append(f"## Glossary\n\n{glossary_md}")
        tail = "\n\n".join(sections)
    else:
        tail = tail.strip().replace(GLOSSARY_PLACEHOLDER, glossary_md)
        tail = tail.replace(REFERENCES_PLACEHOLDER, reflist)
    text = "\n\n".join(s for s in (text, tail.strip()) if s) + "\n"
    return MergedDocument(text, order, missing, conflicts, glossary)


def merge_keyed(parts: Iterable[str], **kwargs) -> str:
    """The merged Markdown only; keyword arguments as :func:`merge_keyed_report`."""
    return merge_keyed_report(parts, **kwargs).text
