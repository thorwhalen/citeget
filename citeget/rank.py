"""Rank libgen search results against a requested title and author.

``search()`` returns whatever libgen's relevance ordering produced, which for a
known title is typically the same book repeated in several formats, interleaved
with derivative works (summaries, workbooks) and download-spam listings. This
module scores each result against what the caller actually asked for, so a
caller can take the best match rather than the first row.

Simple case::

    from citeget import search
    from citeget.rank import rank_results

    results = search("Introduction to Algorithms Cormen")
    best = rank_results(results, title="Introduction to Algorithms",
                        authors="Thomas H. Cormen")[0]

Everything about the scoring is overridable without editing this module: pass
``weights``, ``format_preference``, ``language``, or ``decoy_pattern``.

Scoring uses only fields already present in a ``search()`` result dict, so
ranking costs no extra requests.

Two independent guards keep non-books from winning:

- a **decoy pattern** over the title (``summary``, ``workbook``, ``gratis``, …),
  catching derivative works and download-spam landing pages, and
- a **stub check** — a PDF under a few hundred kB is a landing page, not a scan.
  This floor is much higher than the general one, because a short EPUB of a real
  book is legitimately ~100 kB; one shared floor gets one of those two wrong.

Both are penalties rather than filters, so a decoy can still surface when it is
genuinely the only thing available — it just never outranks a real match.

Based on the ranking contributed in
https://github.com/thorwhalen/citeget/issues/7.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Optional, Sequence

from citeget.names import candidate_surnames, normalize_name

__all__ = [
    "ScoreWeights",
    "SizeBounds",
    "ScoredResult",
    "DEFAULT_WEIGHTS",
    "DEFAULT_SIZE_BOUNDS",
    "DEFAULT_FORMAT_PREFERENCE",
    "DEFAULT_DECOY_PATTERN",
    "TITLE_STOPWORDS",
    "score_result",
    "rank_results",
    "dedupe_results",
    "dedupe_key",
    "parse_size",
    "candidate_surnames",
]

# Words carrying no discriminating power in a title match.
TITLE_STOPWORDS = frozenset(
    "a an and as at be by for how in is it me my not of on or the to with".split()
)

# Preferred file formats, best first. Callers with different needs (e.g. an
# e-reader workflow preferring epub) pass their own ordering.
DEFAULT_FORMAT_PREFERENCE = ("pdf", "epub", "azw3", "mobi", "azw", "djvu", "fb2", "txt")

# Derivative works and download-spam listings that match a title well but are
# not the book. Matched case-insensitively against the result title.
DEFAULT_DECOY_PATTERN = re.compile(
    r"\b("
    r"summary|summaries|workbook|study guide|sparknotes|cliffs?notes|"
    r"key takeaways|conversation starters|review and analysis|analysis of|"
    r"insights (?:on|from)|companion to|instaread|blinkist|"
    r"downloaden|gratis|free download|telecharger|descargar"
    r")\b",
    re.I,
)

_SIZE_RE = re.compile(r"([\d.]+)\s*([kKmMgG]?)i?[bB]")
_SIZE_UNITS = {"": 1, "k": 10**3, "m": 10**6, "g": 10**9}

# How token coverage and sequence similarity combine into the title score.
# Coverage leads because genuine subtitles are extremely common and must not be
# punished as hard as the extra material a summary adds.
_COVERAGE_WEIGHT = 0.65


@dataclass(frozen=True)
class ScoreWeights:
    """Relative contribution of each signal to the total score.

    Title and author dominate: format and language only break ties between
    results that are already plausibly the right book.
    """

    title: float = 5.0
    author: float = 3.0
    format: float = 1.2
    language: float = 1.0
    size: float = 0.8
    decoy_penalty: float = 6.0
    stub_penalty: float = 3.0


@dataclass(frozen=True)
class SizeBounds:
    """Plausibility bounds for a real book file.

    ``min_pdf_bytes`` is deliberately far above ``min_bytes``: a landing-page
    "download" stub is typically a valid but nearly empty PDF, whereas a short
    epub of a genuine book can legitimately be ~100 kB.
    """

    min_bytes: int = 80_000
    min_pdf_bytes: int = 300_000
    implausible_bytes: int = 120_000_000


DEFAULT_WEIGHTS = ScoreWeights()
DEFAULT_SIZE_BOUNDS = SizeBounds()


@dataclass(frozen=True)
class ScoredResult:
    """A search result with its score and the signal breakdown behind it."""

    result: dict
    score: float
    title_match: float
    author_match: float
    is_decoy: bool
    is_stub: bool

    @property
    def extension(self) -> str:
        return (self.result.get("extension") or "").lower()

    @property
    def title(self) -> str:
        return self.result.get("title", "")


def _tokens(text: str, *, drop_stopwords: bool = True) -> set:
    """Normalized word set of *text*, optionally minus non-discriminating words."""
    words = (w for w in normalize_name(text).split() if w)
    if drop_stopwords:
        return {w for w in words if w not in TITLE_STOPWORDS}
    return set(words)


def parse_size(size_text: str) -> int:
    """Bytes from a libgen size string such as ``'2 MB'``; 0 if unparseable.

    >>> parse_size("2 MB")
    2000000
    >>> parse_size("587 kB")
    587000
    >>> parse_size("")
    0
    """
    match = _SIZE_RE.match((size_text or "").strip())
    if not match:
        return 0
    value, unit = float(match.group(1)), match.group(2).lower()
    return int(value * _SIZE_UNITS[unit])


def _title_score(requested: str, found: str) -> float:
    """Blend token coverage with sequence similarity.

    Coverage alone rewards a result whose title merely contains the request
    (``'Summary of X'`` covers ``'X'`` fully); the similarity ratio penalises
    the extra material.
    """
    requested_tokens = _tokens(requested)
    coverage = len(requested_tokens & _tokens(found)) / max(1, len(requested_tokens))
    similarity = SequenceMatcher(
        None, normalize_name(requested), normalize_name(found)
    ).ratio()
    return _COVERAGE_WEIGHT * coverage + (1 - _COVERAGE_WEIGHT) * similarity


def _format_score(extension: str, preference: Sequence) -> float:
    """Score in ``(0, 1]`` by position in *preference*; 0 for unlisted formats."""
    try:
        return 1.0 - list(preference).index(extension) / max(1, len(preference))
    except ValueError:
        return 0.0


def score_result(
    result: dict,
    *,
    title: str,
    authors: Optional[str] = None,
    format_preference: Sequence = DEFAULT_FORMAT_PREFERENCE,
    language: Optional[str] = "english",
    weights: ScoreWeights = DEFAULT_WEIGHTS,
    size_bounds: SizeBounds = DEFAULT_SIZE_BOUNDS,
    decoy_pattern: re.Pattern = DEFAULT_DECOY_PATTERN,
) -> ScoredResult:
    """Score one ``search()`` result against a requested title and author.

    Args:
        result: A result dict from :func:`citeget.search`.
        title: The title actually wanted.
        authors: The author(s) wanted, in any of the orderings
            :mod:`citeget.names` understands. None skips author scoring.
        format_preference: File formats, best first.
        language: Preferred language; a result with no language set is treated
            as neutral rather than penalised, since libgen often omits it.
        weights: Per-signal weights.
        size_bounds: What counts as a plausible file size.
        decoy_pattern: Title pattern marking derivative or spam listings.
    """
    extension = (result.get("extension") or "").lower()
    size = parse_size(result.get("size"))

    title_match = _title_score(title, result.get("title", ""))

    if authors:
        wanted = candidate_surnames(authors)
        present = _tokens(result.get("authors", ""), drop_stopwords=False)
        author_match = 1.0 if wanted & present else 0.0
    else:
        author_match = 0.0

    result_language = (result.get("language") or "").lower()
    # An unset language is common and should not be penalised.
    language_match = (
        1.0
        if (not language or not result_language or language in result_language)
        else 0.0
    )

    is_stub = extension == "pdf" and 0 < size < size_bounds.min_pdf_bytes
    if size and (size < size_bounds.min_bytes or is_stub):
        size_score = 0.0
    elif size > size_bounds.implausible_bytes:
        size_score = 0.3
    else:
        size_score = 1.0

    is_decoy = bool(decoy_pattern.search(result.get("title", "")))

    total = (
        weights.title * title_match
        + weights.author * author_match
        + weights.format * _format_score(extension, format_preference)
        + weights.language * language_match
        + weights.size * size_score
        - (weights.decoy_penalty if is_decoy else 0.0)
        - (weights.stub_penalty if is_stub else 0.0)
    )
    return ScoredResult(
        result=result,
        score=total,
        title_match=title_match,
        author_match=author_match,
        is_decoy=is_decoy,
        is_stub=is_stub,
    )


def rank_results(results, *, title, authors=None, **kwargs) -> list:
    """Return ``results`` as :class:`ScoredResult` objects, best match first.

    ``kwargs`` are forwarded to :func:`score_result` (``format_preference``,
    ``language``, ``weights``, ``size_bounds``, ``decoy_pattern``).
    """
    scored = (score_result(r, title=title, authors=authors, **kwargs) for r in results)
    return sorted(scored, key=lambda s: -s.score)


def dedupe_key(result: dict) -> tuple:
    """Identity of the *work* behind a result, ignoring which format it is in.

    Libgen lists one edition once per format, so ``max_downloads=5`` otherwise
    means "five copies of one book". Title, year and author surnames together
    identify an edition well enough to collapse those rows while keeping
    genuinely different editions apart.
    """
    title = " ".join(sorted(_tokens(result.get("title", ""))))
    year = (result.get("year") or "").strip()[:4]
    return (title, year, frozenset(candidate_surnames(result.get("authors", ""))))


def dedupe_results(results, *, key: Callable[[dict], tuple] = dedupe_key) -> list:
    """Keep only the first result for each distinct work, preserving order.

    Apply after ranking so the surviving copy of each work is the best-scoring
    one. Accepts either plain result dicts or :class:`ScoredResult` objects and
    returns the same kind it was given.
    """
    seen = set()
    kept = []
    for item in results:
        raw = item.result if isinstance(item, ScoredResult) else item
        item_key = key(raw)
        if item_key in seen:
            continue
        seen.add(item_key)
        kept.append(item)
    return kept
