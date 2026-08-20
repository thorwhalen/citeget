"""Tests for author-name parsing (issue #5).

Every case in the issue's reproduction table is locked down here: these are
pure string handling with no network dependency, and getting them wrong
misnames every downloaded file.
"""

import pytest

from citeget.names import (
    apa7_authors,
    candidate_surnames,
    split_author_chunks,
    surname_of,
    surnames,
    normalize_name,
)


@pytest.mark.parametrize(
    "authors, expected",
    [
        # The bug: libgen's most common format is "Surname, Given", and the old
        # code took the last token, yielding the given name.
        ("Moore, Geoffrey A.", "Moore"),
        ("Fitzpatrick, Rob", "Fitzpatrick"),
        ("Alexander, Christopher", "Alexander"),
        # '&' was missing from the separator set, so one author vanished.
        ("Chris Voss & Tahl Raz", "Voss & Raz"),
        # Role markers survived as the "surname".
        ("Tufte, Edward R. (author);Krasny, Dmitry (author)", "Tufte & Krasny"),
        # The case that always worked, and must keep working.
        ("Edward R. Tufte", "Tufte"),
    ],
)
def test_issue_5_reproduction_table(authors, expected):
    assert apa7_authors(authors) == expected


@pytest.mark.parametrize(
    "authors, expected",
    [
        ("", "Unknown"),
        (None, "Unknown"),
        ("   ", "Unknown"),
        ("(author)", "Unknown"),
        ("Smith, John", "Smith"),
        ("Smith, John; Jones, Alice", "Smith & Jones"),
        ("Smith, John; Jones, Alice; Brown, Bob", "Smith et al."),
        ("Smith, J. and Jones, A.", "Smith & Jones"),
    ],
)
def test_apa7_authors_shapes(authors, expected):
    assert apa7_authors(authors) == expected


@pytest.mark.parametrize(
    "authors, expected",
    [
        ("Cormen, Thomas H.", {"cormen"}),
        ("Thomas H. Cormen", {"cormen"}),
        ("Cormen, T. (author);Leiserson, C. (author)", {"cormen", "leiserson"}),
        ("Alice Smith & Bob Jones", {"smith", "jones"}),
        ("Sander van der Linden", {"linden"}),
        ("", set()),
    ],
)
def test_candidate_surnames(authors, expected):
    assert candidate_surnames(authors) == expected


def test_split_author_chunks_strips_role_markers():
    assert split_author_chunks("Tufte, Edward R. (author);Krasny, Dmitry (editor)") == [
        "Tufte, Edward R.",
        "Krasny, Dmitry",
    ]


def test_split_author_chunks_handles_all_separators():
    assert split_author_chunks("A Smith; B Jones & C Brown and D Green") == [
        "A Smith",
        "B Jones",
        "C Brown",
        "D Green",
    ]


def test_surname_of_keeps_multiword_surnames_for_display():
    # Display keeps the particle; matching (candidate_surnames) reduces to the
    # last word, since that is what a caller-supplied name is likeliest to share.
    assert surname_of("van der Linden, Sander") == "van der Linden"
    assert candidate_surnames("van der Linden, Sander") == {"linden"}


def test_surname_of_ignores_generational_suffixes():
    assert surname_of("Martin Luther King Jr.") == "King"
    assert surname_of("Sammy Davis, Jr.") == "Sammy Davis"


def test_surname_of_falls_back_to_initials_when_thats_all_there_is():
    assert surname_of("J. R.") == "R"


def test_surnames_preserves_order():
    assert surnames("Voss, Chris; Raz, Tahl") == ["Voss", "Raz"]


def test_normalize_name_folds_accents():
    assert normalize_name("Émile Durkheim") == "emile durkheim"


def test_core_apa7_authors_delegates_here():
    # core._apa7_authors is what _make_filename uses; it must not drift.
    from citeget.core import _apa7_authors

    assert _apa7_authors("Moore, Geoffrey A.") == apa7_authors("Moore, Geoffrey A.")


def test_make_filename_uses_surname_not_given_name():
    from citeget.core import _make_filename

    assert (
        _make_filename(
            {
                "title": "Crossing the Chasm",
                "authors": "Moore, Geoffrey A.",
                "year": "2014",
                "extension": "epub",
            }
        )
        == "Crossing the Chasm (Moore, 2014).epub"
    )


def test_make_filename_keeps_both_coauthors():
    from citeget.core import _make_filename

    assert (
        _make_filename(
            {
                "title": "Visual Explanations",
                "authors": "Tufte, Edward R. (author);Krasny, Dmitry (author)",
                "year": "1997",
                "extension": "pdf",
            }
        )
        == "Visual Explanations (Tufte & Krasny, 1997).pdf"
    )
