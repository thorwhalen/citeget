"""Author-name parsing for libgen metadata.

Libgen supplies an ``authors`` field in a mix of conventions, and getting the
surname out of it is needed in two places: building the download filename
(``core._make_filename``) and matching a result against a requested author
(``rank.score_result``). This module is the single source of truth for that
parsing so the two never drift apart.

The conventions this handles::

    "Moore, Geoffrey A."                              surname first, comma inside one name
    "Edward R. Tufte"                                 surname last
    "Chris Voss & Tahl Raz"                           '&' between authors
    "Tufte, Edward R. (author);Krasny, Dmitry (author)"   ';' between, role markers

The key rule, and the one that is easy to get wrong: **in libgen data a comma
separates the surname from the given name inside a single author**, it does not
separate one author from the next. Authors are separated by ``;``, ``&`` or
``and``.

Basic use::

    >>> apa7_authors("Moore, Geoffrey A.")
    'Moore'
    >>> apa7_authors("Chris Voss & Tahl Raz")
    'Voss & Raz'
    >>> sorted(candidate_surnames("Cormen, T. (author);Leiserson, C. (author)"))
    ['cormen', 'leiserson']

Note: reference strings parsed out of a *document* (as opposed to libgen
metadata) use the opposite convention — ``"A. B. Smith, C. D. Jones"`` separates
authors with commas — and are handled by
:func:`citeget.acquire_references._parse_all_surnames` instead.
"""

import re
import unicodedata

__all__ = [
    "split_author_chunks",
    "surname_of",
    "surnames",
    "candidate_surnames",
    "apa7_authors",
    "normalize_name",
]

# Separators *between* authors. Note that ',' is deliberately absent: in libgen
# data the comma separates surname from given name within a single author.
_AUTHOR_SEPARATOR_RE = re.compile(r"\s*;\s*|\s*&\s*|\s+and\s+", re.I)

# Role markers libgen appends to names, e.g. "Tufte, Edward R. (author)".
_ROLE_MARKER_RE = re.compile(
    r"\((?:author|editor|translator|illustrator|contributor|compiler|foreword"
    r"|introduction|narrator|photographer)s?\)",
    re.I,
)

# Separator noise sometimes left on a name once role markers are stripped.
# Deliberately does not strip "." so that trailing initials ("Edward R.")
# survive intact.
_TRAILING_PUNCT_RE = re.compile(r"^[\s,;:&-]+|[\s,;:&-]+$")

# Generational and honorific suffixes that are never the surname.
_NAME_SUFFIXES = frozenset("jr sr ii iii iv v phd md dphil llb llm esq".split())


def normalize_name(text: str) -> str:
    """Fold *text* to lowercase ASCII alphanumerics plus spaces, for matching.

    >>> normalize_name("Émile Durkheim")
    'emile durkheim'
    """
    folded = unicodedata.normalize("NFKD", text or "")
    folded = folded.encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", " ", folded.lower()).strip()


def _is_initial(token: str) -> bool:
    """True for tokens like ``'R.'`` or ``'J'`` that are initials, not surnames."""
    return len(token.rstrip(".")) <= 1


def _is_suffix(token: str) -> bool:
    """True for generational/honorific suffixes such as ``'Jr.'`` or ``'PhD'``."""
    return token.strip(".,").lower() in _NAME_SUFFIXES


def split_author_chunks(authors: str) -> list:
    """Split an authors string into one chunk per author, cleaned of role markers.

    >>> split_author_chunks("Tufte, Edward R. (author);Krasny, Dmitry (author)")
    ['Tufte, Edward R.', 'Krasny, Dmitry']
    >>> split_author_chunks("Chris Voss & Tahl Raz")
    ['Chris Voss', 'Tahl Raz']
    """
    chunks = []
    for raw in _AUTHOR_SEPARATOR_RE.split(authors or ""):
        cleaned = _TRAILING_PUNCT_RE.sub("", _ROLE_MARKER_RE.sub(" ", raw))
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            chunks.append(cleaned)
    return chunks


def surname_of(chunk: str) -> str:
    """Extract the surname from a single author *chunk*, preserving its casing.

    If the chunk contains a comma, the surname is everything before it
    (libgen's ``"Surname, Given"`` form). Otherwise it is the last token that
    is not an initial.

    >>> surname_of("Moore, Geoffrey A.")
    'Moore'
    >>> surname_of("Edward R. Tufte")
    'Tufte'
    >>> surname_of("van der Linden, Sander")
    'van der Linden'
    >>> surname_of("Martin Luther King Jr.")
    'King'
    """
    chunk = (chunk or "").strip()
    if not chunk:
        return ""
    if "," in chunk:
        head = chunk.split(",", 1)[0].strip()
        if head:
            return head
        chunk = chunk.lstrip(",").strip()
    tokens = chunk.split()
    if not tokens:
        return ""
    real = [t for t in tokens if not _is_initial(t) and not _is_suffix(t)]
    return (real or tokens)[-1].strip(".,")


def surnames(authors: str) -> list:
    """Surnames of every author in *authors*, in order, casing preserved.

    >>> surnames("Tufte, Edward R. (author);Krasny, Dmitry (author)")
    ['Tufte', 'Krasny']
    >>> surnames("Chris Voss & Tahl Raz")
    ['Voss', 'Raz']
    """
    found = []
    for chunk in split_author_chunks(authors):
        name = surname_of(chunk)
        if name:
            found.append(name)
    return found


def candidate_surnames(authors: str) -> set:
    """Normalized surnames usable for matching, in either name ordering.

    Multi-word surnames contribute their last word, since that is what a
    caller-supplied author string is most likely to share.

    >>> sorted(candidate_surnames("Alice Smith & Bob Jones"))
    ['jones', 'smith']
    >>> sorted(candidate_surnames("Sander van der Linden"))
    ['linden']
    """
    found = set()
    for name in surnames(authors):
        words = [w for w in normalize_name(name).split() if len(w) > 1]
        if words:
            found.add(words[-1])
    return found


def apa7_authors(authors: str) -> str:
    """Format *authors* APA 7 style, surnames only.

    1 author -> ``"Smith"``; 2 -> ``"Smith & Jones"``; 3+ -> ``"Smith et al."``;
    nothing usable -> ``"Unknown"``.

    >>> apa7_authors("Moore, Geoffrey A.")
    'Moore'
    >>> apa7_authors("Tufte, Edward R. (author);Krasny, Dmitry (author)")
    'Tufte & Krasny'
    >>> apa7_authors("")
    'Unknown'
    """
    names = surnames(authors)
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} & {names[1]}"
    return f"{names[0]} et al."
