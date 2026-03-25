#!/usr/bin/env python3
"""
word_count.py — Count words in an article file, excluding code blocks and comments.

Usage:
    python word_count.py <file>
    python word_count.py <file> --verbose
    python word_count.py <file> --breakdown
"""

import re
import sys
from pathlib import Path


def count_words_with_breakdown(text: str) -> dict:
    """Count words with a breakdown by section type."""
    # Track what was removed
    code_blocks_content = re.findall(r'```[\s\S]*?```', text)
    inline_code_content = re.findall(r'`[^`]+`', text)
    html_comments = re.findall(r'<!--[\s\S]*?-->', text)
    latex_math_block = re.findall(r'\$\$[\s\S]*?\$\$', text)
    latex_math_inline = re.findall(r'\$[^$]+\$', text)

    code_words = sum(len(c.split()) for c in code_blocks_content)
    inline_code_words = sum(len(c.split()) for c in inline_code_content)
    comment_words = sum(len(c.split()) for c in html_comments)

    # Strip all excluded content
    clean = text
    clean = re.sub(r'```[\s\S]*?```', '', clean)
    clean = re.sub(r'`[^`]+`', '', clean)
    clean = re.sub(r'<!--[\s\S]*?-->', '', clean)
    clean = re.sub(r'\$\$[\s\S]*?\$\$', '', clean)
    clean = re.sub(r'\$[^$]+\$', '', clean)
    clean = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean)  # links: keep text
    clean = re.sub(r'^#+\s+', '', clean, flags=re.MULTILINE)
    # Remove LaTeX commands
    clean = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', clean)
    clean = re.sub(r'\\[a-zA-Z]+', ' ', clean)
    clean = re.sub(r'[{}]', ' ', clean)

    main_words = len(clean.split())

    return {
        'main_text_words': main_words,
        'code_block_words': code_words,
        'inline_code_words': inline_code_words,
        'comment_words': comment_words,
        'total_in_file': len(text.split()),
        'counted_words': main_words,
    }


def find_sections(text: str) -> list[tuple[str, int]]:
    """Return list of (section_title, word_count) for each section."""
    parts = re.split(r'^(#{1,3}\s+.+)$', text, flags=re.MULTILINE)
    sections = []
    current_title = 'Preamble'
    for i, part in enumerate(parts):
        if re.match(r'^#{1,3}\s+', part):
            current_title = part.strip('#').strip()
        else:
            # Count words in this section body
            section_text = part
            section_text = re.sub(r'```[\s\S]*?```', '', section_text)
            section_text = re.sub(r'`[^`]+`', '', section_text)
            section_text = re.sub(r'<!--[\s\S]*?-->', '', section_text)
            word_count = len(section_text.split())
            if word_count > 0:
                sections.append((current_title, word_count))
    return sections


def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    path = Path(args[0])
    if not path.exists():
        print(f'Error: File not found: {path}')
        sys.exit(1)

    if path.is_dir():
        texts = []
        for ext in ('*.md', '*.txt', '*.tex'):
            for f in sorted(path.glob(ext)):
                texts.append(f.read_text(encoding='utf-8', errors='ignore'))
        text = '\n\n'.join(texts)
    else:
        text = path.read_text(encoding='utf-8', errors='ignore')

    verbose = '--verbose' in args or '-v' in args
    breakdown = '--breakdown' in args or '-b' in args

    stats = count_words_with_breakdown(text)

    print(f'\nWord count for: {path}')
    print('-' * 40)
    print(f'Counted words (body text): {stats["counted_words"]}')

    if verbose or breakdown:
        print(f'  Excluded: {stats["code_block_words"]} words in code blocks')
        print(f'  Excluded: {stats["inline_code_words"]} words in inline code')
        print(f'  Excluded: {stats["comment_words"]} words in HTML comments')
        print(f'  Total words in file (all): {stats["total_in_file"]}')

    if breakdown:
        print('\nBreakdown by section:')
        sections = find_sections(text)
        for title, count in sections:
            bar = '█' * (count // 50)
            print(f'  {title[:35]:35s} {count:5d}  {bar}')

    # Quick journal comparison
    print('\nJournal limits:')
    limits = [
        ('IEEE Software', 4200, '(+ figs×250)'),
        ('CACM Practice', 7000, '(~10 pages)'),
        ('CACM Research', 7000, '(~10 pages)'),
        ('CACM Viewpoints', 3000, '(~5 pages)'),
        ('IEEE TSE', 9000, '(~12 IEEE pages)'),
        ('ACM Queue', 3500, '(target)'),
    ]
    wc = stats['counted_words']
    for name, limit, note in limits:
        pct = wc / limit * 100
        if pct <= 80:
            indicator = '✅ well within'
        elif pct <= 100:
            indicator = '✅ within'
        elif pct <= 120:
            indicator = '⚠️  slightly over'
        else:
            indicator = '❌ over'
        print(f'  {name:20s} {limit:6d} {note:20s} → {pct:5.0f}% {indicator}')

    print()


if __name__ == '__main__':
    main()
