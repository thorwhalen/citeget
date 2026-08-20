"""Tests for result ranking (issue #7).

The cases here are the ones that made a naive top-1 pick take the wrong file:
download-spam landing pages and summaries that libgen ranks above the book, and
the same edition repeated once per format.
"""

import pytest

from citeget.rank import (
    DEFAULT_DECOY_PATTERN,
    ScoreWeights,
    dedupe_results,
    parse_size,
    rank_results,
    score_result,
)


def _result(
    title, *, authors="", extension="pdf", size="3 MB", year="2020", language="English"
):
    return {
        "title": title,
        "authors": authors,
        "extension": extension,
        "size": size,
        "year": year,
        "language": language,
    }


@pytest.mark.parametrize(
    "text, expected",
    [
        ("2 MB", 2_000_000),
        ("587 kB", 587_000),
        ("1.5 GB", 1_500_000_000),
        ("", 0),
        ("junk", 0),
    ],
)
def test_parse_size(text, expected):
    assert parse_size(text) == expected


def test_spam_landing_page_never_outranks_the_book():
    """Both decoy markers fire here: the title pattern and the sub-300 kB PDF."""
    spam = _result("Downloaden Company of One PDF Gratis - Paul Jarvis", size="93 kB")
    book = _result(
        "Company of One: Why Staying Small Is the Next Big Thing",
        authors="Jarvis, Paul",
        size="1 MB",
    )
    ranked = rank_results([spam, book], title="Company of One", authors="Paul Jarvis")
    assert ranked[0].result is book
    assert ranked[1].is_decoy or ranked[1].is_stub


def test_summary_never_outranks_the_book():
    summary = _result(
        "Summary of Algorithms to Live By", extension="epub", size="560 kB"
    )
    book = _result(
        "Algorithms to Live By: The Computer Science of Human Decisions",
        authors="Christian, Brian; Griffiths, Tom",
        size="3 MB",
    )
    ranked = rank_results(
        [summary, book],
        title="Algorithms to Live By",
        authors="Brian Christian & Tom Griffiths",
    )
    assert ranked[0].result is book
    assert ranked[1].is_decoy


def test_author_match_breaks_a_title_tie():
    right = _result("The Design of Everyday Things", authors="Norman, Donald A.")
    wrong = _result("The Design of Everyday Things", authors="Smith, John")
    ranked = rank_results(
        [wrong, right], title="The Design of Everyday Things", authors="Donald Norman"
    )
    assert ranked[0].result is right
    assert ranked[0].author_match == 1.0


def test_author_match_works_for_both_name_orderings():
    """The bug behind issue #5 would have made one of these miss."""
    surname_first = _result("Introduction to Algorithms", authors="Cormen, Thomas H.")
    given_first = _result("Introduction to Algorithms", authors="Thomas H. Cormen")
    for result in (surname_first, given_first):
        scored = score_result(
            result, title="Introduction to Algorithms", authors="Cormen, Thomas H."
        )
        assert scored.author_match == 1.0


def test_format_preference_orders_copies_of_the_same_book():
    rows = [
        _result("Crossing the Chasm", extension=ext) for ext in ("mobi", "epub", "pdf")
    ]
    ranked = rank_results(rows, title="Crossing the Chasm")
    assert [s.extension for s in ranked] == ["pdf", "epub", "mobi"]


def test_format_preference_is_caller_supplied():
    rows = [_result("Crossing the Chasm", extension=ext) for ext in ("pdf", "epub")]
    ranked = rank_results(
        rows, title="Crossing the Chasm", format_preference=("epub", "pdf")
    )
    assert ranked[0].extension == "epub"


def test_subtitles_are_not_punished_like_summaries():
    """A real subtitle adds material too; it must not score like 'Summary of'."""
    subtitled = score_result(
        _result("Crossing the Chasm: Marketing and Selling Disruptive Products"),
        title="Crossing the Chasm",
    )
    summary = score_result(
        _result("Summary of Crossing the Chasm"), title="Crossing the Chasm"
    )
    assert subtitled.score > summary.score
    assert not subtitled.is_decoy


def test_missing_language_is_neutral_not_wrong():
    """Libgen often omits the language; absent must not read as 'not English'."""
    unset = score_result(_result("A Book", language=""), title="A Book")
    english = score_result(_result("A Book", language="English"), title="A Book")
    german = score_result(_result("A Book", language="German"), title="A Book")
    assert unset.score == english.score > german.score


def test_weights_are_injectable_not_baked_into_the_arithmetic():
    rows = [
        _result("Some Book", authors="Right, Author", extension="mobi"),
        _result("Some Book", authors="Wrong, Person", extension="pdf"),
    ]
    author_led = rank_results(rows, title="Some Book", authors="Author Right")
    assert author_led[0].result is rows[0]

    format_led = rank_results(
        rows,
        title="Some Book",
        authors="Author Right",
        weights=ScoreWeights(author=0.0, format=5.0),
    )
    assert format_led[0].result is rows[1]


def test_decoy_is_a_penalty_not_a_filter():
    """A decoy still surfaces when it is genuinely all there is."""
    only = _result("Summary of Some Book")
    ranked = rank_results([only], title="Some Book")
    assert len(ranked) == 1 and ranked[0].is_decoy


@pytest.mark.parametrize(
    "title",
    [
        "Summary of X",
        "X Workbook",
        "X: A Study Guide",
        "Key Takeaways from X",
        "Instaread Summary",
        "Downloaden X PDF",
        "X gratis",
    ],
)
def test_decoy_pattern_covers_the_reported_markers(title):
    assert DEFAULT_DECOY_PATTERN.search(title)


def test_decoy_pattern_is_overridable():
    ranked = rank_results(
        [_result("Summary of X")],
        title="X",
        decoy_pattern=__import__("re").compile(r"(?!x)x"),
    )
    assert not ranked[0].is_decoy


# --- deduplication: 'five results' should mean five books -------------------


def test_dedupe_collapses_one_edition_across_formats():
    rows = [
        _result(
            "Crossing the Chasm, 3rd Edition",
            authors="Moore, Geoffrey A.",
            extension=ext,
        )
        for ext in ("pdf", "azw", "epub", "azw3")
    ]
    assert len(dedupe_results(rows)) == 1


def test_dedupe_keeps_genuinely_different_editions():
    revised = _result(
        "Crossing the Chasm Revised edition", authors="Moore, Geoffrey A."
    )
    third = _result("Crossing the Chasm, 3rd Edition", authors="Moore, Geoffrey A.")
    assert len(dedupe_results([revised, third])) == 2


def test_dedupe_keeps_the_first_which_after_ranking_is_the_best():
    rows = [
        _result("A Book", authors="Smith, John", extension="mobi"),
        _result("A Book", authors="Smith, John", extension="pdf"),
    ]
    kept = dedupe_results(rank_results(rows, title="A Book"))
    assert len(kept) == 1 and kept[0].extension == "pdf"


def test_dedupe_returns_the_kind_it_was_given():
    rows = [_result("A Book"), _result("A Book")]
    assert isinstance(dedupe_results(rows)[0], dict)
    assert dedupe_results(rank_results(rows, title="A Book"))[0].title == "A Book"


def test_dedupe_key_is_overridable():
    rows = [_result("A"), _result("B")]
    assert len(dedupe_results(rows, key=lambda r: "same")) == 1
