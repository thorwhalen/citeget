#!/usr/bin/env python3
"""
check_article.py — Pre-submission article checker

Usage:
    python check_article.py <article_file> <journal_key>
    python check_article.py <article_file> --all
    python check_article.py <article_file>       # word count only

Journal keys: ieee_software, cacm_practice, cacm_research, cacm_viewpoints,
              ieee_tse, acm_queue

Examples:
    python check_article.py my_article.md ieee_software
    python check_article.py my_article.md --all
"""

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR.parent / 'data'
JOURNAL_PROFILES_FILE = DATA_DIR / 'journal_profiles.json'


def load_profiles():
    with open(JOURNAL_PROFILES_FILE) as f:
        return json.load(f)


def load_article(path: Path) -> str:
    """Load article text from a file or all .md/.txt/.tex files in a directory."""
    if path.is_dir():
        texts = []
        for ext in ('*.md', '*.txt', '*.tex'):
            for f in sorted(path.glob(ext)):
                texts.append(f.read_text(encoding='utf-8', errors='ignore'))
        return '\n\n'.join(texts)
    return path.read_text(encoding='utf-8', errors='ignore')


def strip_latex_commands(text: str) -> str:
    """Remove LaTeX commands for word counting."""
    text = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', ' ', text)
    text = re.sub(r'\\[a-zA-Z]+', ' ', text)
    text = re.sub(r'[{}]', ' ', text)
    return text


def count_words(text: str) -> int:
    """Count words in markdown/plain text/LaTeX, skipping code blocks and comments."""
    # Remove fenced code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'`[^`]+`', '', text)
    # Remove LaTeX math
    text = re.sub(r'\$\$[\s\S]*?\$\$', '', text)
    text = re.sub(r'\$[^$]+\$', '', text)
    # Remove HTML comments
    text = re.sub(r'<!--[\s\S]*?-->', '', text)
    # Remove markdown links, keep link text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove markdown headers markers
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # Strip remaining LaTeX
    text = strip_latex_commands(text)
    words = text.split()
    return len(words)


def count_figures_and_tables(text: str) -> int:
    """Estimate number of figures and tables."""
    figures = len(re.findall(r'(?i)(^|\n)\s*(\!\[|\\begin\{figure\}|figure\s+\d)', text))
    tables = len(re.findall(r'(?i)(^|\n)\s*(\|.+\|.+\||\\begin\{table\})', text))
    return figures + tables


def count_references(text: str) -> int:
    """Estimate number of references."""
    # Match numbered references like [1] Author, Title...
    numbered = re.findall(r'^\s*\[\d+\]', text, re.MULTILINE)
    if numbered:
        return len(numbered)
    # Match bibliography entries in LaTeX
    bibitems = re.findall(r'\\bibitem', text)
    if bibitems:
        return len(bibitems)
    # Fallback: count lines in a References section
    ref_section = re.search(
        r'^#{1,3}\s*(references|bibliography|works cited)\s*$(.+?)(?:^#{1,3}|\Z)',
        text, re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    if ref_section:
        lines = [l.strip() for l in ref_section.group(2).splitlines() if l.strip()]
        # Rough: non-empty lines that look like reference entries
        entries = [l for l in lines if len(l) > 20]
        return len(entries)
    return 0


def extract_abstract(text: str) -> str:
    """Extract abstract text."""
    abstract_match = re.search(
        r'^#{1,3}\s*abstract\s*$\s*(.+?)(?=^#{1,3}|\Z)',
        text, re.IGNORECASE | re.MULTILINE | re.DOTALL
    )
    if abstract_match:
        return abstract_match.group(1).strip()
    # LaTeX abstract environment
    latex_match = re.search(
        r'\\begin\{abstract\}(.+?)\\end\{abstract\}',
        text, re.DOTALL
    )
    if latex_match:
        return latex_match.group(1).strip()
    return ''


def check_required_elements(text: str, journal_key: str) -> list[dict]:
    """Check for presence of required elements. Returns list of {item, present, note}."""
    checks = []
    text_lower = text.lower()

    if journal_key == 'ieee_software':
        checks.append({
            'item': 'Practitioner Takeaways (3 bullets)',
            'present': bool(re.search(r'(?i)practitioner\s+takeaway', text)),
            'note': 'Required: 3 actionable bullet points'
        })
        checks.append({
            'item': 'Author bio',
            'present': bool(re.search(r'(?i)(about the author|author bio|biography)', text)),
            'note': 'Required for each author'
        })

    if journal_key in ('cacm_practice', 'cacm_research', 'cacm_viewpoints'):
        checks.append({
            'item': 'Abstract',
            'present': bool(re.search(r'(?i)^#{1,3}\s*abstract', text, re.MULTILINE)),
            'note': 'Required'
        })

    if journal_key == 'ieee_tse':
        checks.append({
            'item': 'Structured abstract (Objective/Methods/Results/Conclusion)',
            'present': bool(re.search(r'(?i)(objective|methods|results|conclusion)', text[:2000])),
            'note': 'Structured abstract preferred'
        })
        checks.append({
            'item': 'Threats to Validity section',
            'present': bool(re.search(r'(?i)threats?\s+to\s+validity', text)),
            'note': 'Required for empirical work'
        })
        checks.append({
            'item': 'Related Work section',
            'present': bool(re.search(r'(?i)^#{1,3}\s*related\s+work', text, re.MULTILINE)),
            'note': 'Expected'
        })
        checks.append({
            'item': 'Data Availability statement',
            'present': bool(re.search(r'(?i)(data\s+availability|replication\s+package)', text)),
            'note': 'Strongly recommended'
        })

    if journal_key == 'acm_queue':
        checks.append({
            'item': 'Problem-focused framing (not promotional)',
            'present': True,  # Can't auto-detect; flag for human review
            'note': 'Manual check required: must focus on what is HARD, not product promotion'
        })

    return checks


def format_status(present: bool) -> str:
    return '✅' if present else '❌'


def format_count_check(actual: int, limit: int | None, label: str) -> str:
    if limit is None:
        return f'  {label}: {actual} (no limit)'
    pct = actual / limit * 100
    status = '✅' if actual <= limit else '❌ OVER LIMIT'
    return f'  {label}: {actual} / {limit} ({pct:.0f}%) {status}'


def run_check(article_path: Path, journal_key: str | None) -> None:
    profiles = load_profiles()

    if not article_path.exists():
        print(f'Error: File not found: {article_path}')
        sys.exit(1)

    text = load_article(article_path)

    word_count = count_words(text)
    fig_table_count = count_figures_and_tables(text)
    ref_count = count_references(text)
    abstract = extract_abstract(text)
    abstract_word_count = count_words(abstract) if abstract else 0

    print(f'\n{"="*60}')
    print(f'ARTICLE CHECK: {article_path.name}')
    print(f'{"="*60}\n')

    print('BASIC METRICS')
    print('-' * 40)
    print(f'  Word count (excluding code blocks): {word_count}')
    print(f'  Estimated figures + tables: {fig_table_count}')
    print(f'  Estimated references: {ref_count}')
    print(f'  Abstract word count: {abstract_word_count}')

    if journal_key is None:
        print('\nNo journal specified. Showing counts only.')
        print('\nJournal limits for reference:')
        for key, p in profiles.items():
            wl = p.get('word_limit') or f"{p.get('page_limit', '?')} pages"
            al = p.get('abstract_word_limit', '?')
            rl = p.get('reference_limit', 'unlimited')
            print(f'  {key:20s} words:{str(wl):10s}  abstract:{str(al):6s}  refs:{rl}')
        return

    if journal_key not in profiles:
        print(f'\nUnknown journal key: {journal_key}')
        print(f'Available: {", ".join(profiles.keys())}')
        sys.exit(1)

    profile = profiles[journal_key]

    print(f'\n{"="*60}')
    print(f'JOURNAL: {profile["name"]}')
    print(f'{"="*60}\n')

    print('LIMITS CHECK')
    print('-' * 40)

    # Word count (IEEE Software: figures count as 250 words each)
    if journal_key == 'ieee_software':
        effective_word_count = word_count + (fig_table_count * 250)
        limit = profile.get('word_limit')
        status = '✅' if effective_word_count <= limit else '❌ OVER LIMIT'
        print(f'  Word count (+ {fig_table_count} figs×250): {effective_word_count} / {limit} {status}')
    else:
        print(format_count_check(word_count, profile.get('word_limit'), 'Word count'))

    print(format_count_check(abstract_word_count, profile.get('abstract_word_limit'), 'Abstract words'))
    print(format_count_check(ref_count, profile.get('reference_limit'), 'References'))

    if profile.get('page_limit'):
        print(f'  Page limit: {profile["page_limit"]} {profile.get("page_limit_format", "")} (manual check required)')

    print('\nREQUIRED ELEMENTS')
    print('-' * 40)
    element_checks = check_required_elements(text, journal_key)
    if element_checks:
        for check in element_checks:
            print(f'  {format_status(check["present"])} {check["item"]}')
            if not check['present']:
                print(f'     → {check["note"]}')
    else:
        print('  (no automated checks for this journal)')

    if profile.get('submission_model') == 'invitation_only':
        print('\n⚠️  WARNING: ACM Queue is INVITATION ONLY')
        print('   You must receive an editorial invitation or pitch to queue-info@acm.org')

    print('\nSUBMISSION INFO')
    print('-' * 40)
    print(f'  Portal: {profile.get("submission_portal", "see author guidelines")}')
    if profile.get('pre_submission_recommended'):
        print(f'  Pre-submission email recommended: {profile.get("pre_submission_contact", "see guidelines")}')
    print(f'  Review timeline: ~{profile.get("decision_timeline_weeks", "?")} weeks')
    print(f'  Author guidelines: {profile.get("author_guidelines_url", "")}')

    print()


def main():
    args = sys.argv[1:]

    if not args or args[0] in ('-h', '--help'):
        print(__doc__)
        sys.exit(0)

    article_path = Path(args[0])

    if len(args) == 1:
        run_check(article_path, None)
    elif args[1] == '--all':
        profiles = load_profiles()
        for key in profiles:
            run_check(article_path, key)
    else:
        run_check(article_path, args[1])


if __name__ == '__main__':
    main()
