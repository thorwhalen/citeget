#!/usr/bin/env python3
"""
extract_references.py — Extract and validate references from an article.

Parses numbered references [1], [2], ... and checks:
- All in-text citations have a corresponding reference
- All references are cited in the text
- Basic completeness (year present, title-like content, etc.)

Usage:
    python extract_references.py <article_file>
    python extract_references.py <article_file> --check ieee_software
"""

import re
import sys
from pathlib import Path


def extract_in_text_citations(text: str) -> set[int]:
    """Find all [1], [2], [1,2], [1-3] style citation numbers."""
    cited = set()
    # Single: [1] or [12]
    for m in re.finditer(r'\[(\d+)\]', text):
        cited.add(int(m.group(1)))
    # Range: [1-3]
    for m in re.finditer(r'\[(\d+)-(\d+)\]', text):
        for i in range(int(m.group(1)), int(m.group(2)) + 1):
            cited.add(i)
    # Multi: [1,2,3]
    for m in re.finditer(r'\[(\d+(?:,\s*\d+)+)\]', text):
        for part in m.group(1).split(','):
            cited.add(int(part.strip()))
    return cited


def extract_reference_list(text: str) -> dict[int, str]:
    """Extract numbered reference list. Returns {number: full_text}."""
    refs = {}

    # Find the references section
    ref_section_match = re.search(
        r'^#{1,3}\s*(references|bibliography|works cited)\s*$(.+?)(?:^#{1,3}|\Z)',
        text, re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    if ref_section_match:
        ref_text = ref_section_match.group(2)
    else:
        ref_text = text

    # Match [N] entries
    for m in re.finditer(r'^\s*\[(\d+)\]\s*(.+?)(?=^\s*\[\d+\]|\Z)', ref_text,
                         re.MULTILINE | re.DOTALL):
        num = int(m.group(1))
        body = ' '.join(m.group(2).split())  # normalize whitespace
        refs[num] = body

    return refs


def check_reference_completeness(ref_text: str) -> list[str]:
    """Check a single reference for completeness. Returns list of warnings."""
    warnings = []
    if not re.search(r'\b(19|20)\d{2}\b', ref_text):
        warnings.append('no year found')
    if len(ref_text) < 30:
        warnings.append('very short — may be incomplete')
    if not re.search(r'[A-Z][a-z]', ref_text):
        warnings.append('no proper noun detected — may be malformed')
    return warnings


def main():
    args = sys.argv[1:]
    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    path = Path(args[0])
    if not path.exists():
        print(f'Error: File not found: {path}')
        sys.exit(1)

    text = path.read_text(encoding='utf-8', errors='ignore')

    # Strip code blocks before citation detection
    text_no_code = re.sub(r'```[\s\S]*?```', '', text)
    text_no_code = re.sub(r'`[^`]+`', '', text_no_code)

    cited = extract_in_text_citations(text_no_code)
    refs = extract_reference_list(text)

    ref_limit = None
    if '--check' in args:
        idx = args.index('--check')
        if idx + 1 < len(args):
            journal_key = args[idx + 1]
            limits = {
                'ieee_software': 15,
                'cacm_practice': 40,
                'cacm_research': 40,
                'cacm_viewpoints': 10,
                'ieee_tse': None,
                'acm_queue': None,
            }
            ref_limit = limits.get(journal_key)

    print(f'\nReference Analysis: {path.name}')
    print('=' * 50)
    print(f'In-text citations found: {len(cited)}')
    print(f'Reference list entries: {len(refs)}')

    if ref_limit is not None:
        status = '✅' if len(refs) <= ref_limit else '❌ OVER LIMIT'
        print(f'Reference limit for journal: {ref_limit} {status}')

    # Cross-check
    cited_nums = cited
    ref_nums = set(refs.keys())

    missing_refs = cited_nums - ref_nums
    uncited_refs = ref_nums - cited_nums

    if missing_refs:
        print(f'\n❌ In-text citations with NO matching reference entry:')
        for n in sorted(missing_refs):
            print(f'   [{n}]')

    if uncited_refs:
        print(f'\n⚠️  Reference entries not cited in text:')
        for n in sorted(uncited_refs):
            print(f'   [{n}] {refs.get(n, "")[:80]}')

    if not missing_refs and not uncited_refs:
        print('\n✅ All citations and references are consistent.')

    # Completeness check
    print('\nReference Completeness:')
    issues_found = False
    for num in sorted(refs.keys()):
        warnings = check_reference_completeness(refs[num])
        if warnings:
            issues_found = True
            print(f'  [{num}] {refs[num][:60]}...')
            for w in warnings:
                print(f'       ⚠️  {w}')

    if not issues_found:
        print('  ✅ All reference entries look complete.')

    if refs:
        print(f'\nAll {len(refs)} references:')
        for num in sorted(refs.keys()):
            print(f'  [{num:2d}] {refs[num][:90]}')

    print()


if __name__ == '__main__':
    main()
