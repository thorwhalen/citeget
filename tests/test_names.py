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
        # Surname first with compound initials and no comma — libgen uses this
        # too, and it produced "Crossing the Chasm Revised edition (G.A, 1991)".
        ("Moore G.A.", "Moore"),
        ("Tufte E.R.", "Tufte"),
        ("Voss C. & Raz T.", "Voss & Raz"),
        # ...without swallowing genuinely short surnames.
        ("Wu J.", "Wu"),
        ("Hu, Tung-Hui", "Hu"),
        ("Tung-Hui Hu", "Hu"),
        # Or abbreviations that are part of the name.
        ("St. John, Mary", "St. John"),
    ],
)
def test_compound_initials_are_not_mistaken_for_surnames(authors, expected):
    assert apa7_authors(authors) == expected


def test_compound_initials_still_match_by_surname():
    assert candidate_surnames("Moore G.A.") == {"moore"}


@pytest.mark.parametrize(
    "authors",
    [
        # All four forms libgen actually returns for the same two authors.
        "Brian Christian, Tom Griffiths",
        "Christian, Brian; Griffiths, Tom",
        "Christian, Brian;Griffiths, Tom",
        "Brian Christian; Tom Griffiths",
    ],
)
def test_every_libgen_convention_for_the_same_pair_agrees(authors):
    """A comma is usually intra-name, but libgen does use it between full
    names too, which produced 'Algorithms to Live By (Brian Christian, 2016)'."""
    assert apa7_authors(authors) == "Christian & Griffiths"
    assert candidate_surnames(authors) == {"christian", "griffiths"}


@pytest.mark.parametrize(
    "authors, expected",
    [
        # A comma after a lone token is intra-name...
        ("Moore, Geoffrey A.", "Moore"),
        ("Hu, Tung-Hui", "Hu"),
        # ...as is one after a particle-glued surname.
        ("van der Linden, Sander", "van der Linden"),
        ("St. John, Mary", "St. John"),
        # A trailing suffix segment is not an author.
        ("Sammy Davis, Jr.", "Davis"),
        # Three full names separated by commas.
        ("Alice Smith, Bob Jones, Carol Brown", "Smith et al."),
    ],
)
def test_comma_disambiguation(authors, expected):
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
