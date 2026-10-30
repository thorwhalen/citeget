"""Tests for citeget.extract — reference extraction from documents."""

from citeget.extract import (
    extract_references,
    regex_extractor,
    chain,
    merge,
    list_extractors,
    ExtractionResult,
    EXTRACTORS,
)
from citeget.acquire_references import Reference


SAMPLE_WITH_HEADER = """\
# Introduction

Some text here.

## References

[1] A. Smith, "Graph theory basics," *J. Math.*, 2020.
[2] B. Jones, C. Lee, "Advanced algorithms," *Proc. ALGO*, 2021.
https://doi.org/10.1234/algo.2021
[3] D. Brown et al., "Survey of networks," arXiv, 2022.
https://arxiv.org/abs/2201.12345
"""

SAMPLE_NO_HEADER = """\
Here are the papers to find:

**[1] Kahl, "Graph vulnerability parameters," *DAM*, 2019.**
- http://example.com/kahl2019

**[2] Gu, "A proof of Brouwer's toughness conjecture," *SIAM*, 2021.**
- https://doi.org/10.1137/20M1372652
"""

SAMPLE_MARKDOWN_LINKS = """\
Check out [Graph Theory](https://example.com/graph.pdf) and
also [Network Analysis](https://example.com/network.pdf) for background.
"""


def test_extract_with_header():
    result = extract_references(SAMPLE_WITH_HEADER)
    assert isinstance(result, ExtractionResult)
    assert len(result.references) == 3
    assert result.references[0].number == 1
    assert "Graph theory basics" in result.references[0].title
    assert result.references[1].number == 2
    assert result.references[2].number == 3
    assert result.confidence == "high"


def test_extract_no_header_bold():
    result = extract_references(SAMPLE_NO_HEADER)
    assert len(result.references) == 2
    assert result.references[0].number == 1
    assert "Kahl" in result.references[0].authors or "Kahl" in result.references[0].raw
    assert result.references[1].number == 2


def test_standard_extractor_misses_no_header():
    result = extract_references(SAMPLE_NO_HEADER, extractor="standard")
    assert len(result.references) == 0


def test_broad_extractor():
    result = extract_references(SAMPLE_WITH_HEADER, extractor="broad")
    assert len(result.references) == 3


def test_registry_populated():
    names = list_extractors()
    assert "default" in names
    assert "standard" in names
    assert "broad" in names
    assert "bold" in names
    assert "ai" in names
    assert "markdown_links" in names


def test_regex_extractor_custom():
    ext = regex_extractor(
        section_patterns=(r"(?mi)^## References\s*$",),
        whole_document_fallback=False,
    )
    result = ext(SAMPLE_WITH_HEADER)
    assert len(result) == 3

    # Should not match document without that header
    result2 = ext(SAMPLE_NO_HEADER)
    assert len(result2) == 0


def test_chain_composition():
    always_empty = lambda text: []
    always_one = lambda text: [Reference(number=1, raw="test")]
    chained = chain(always_empty, always_one)
    result = chained("anything")
    assert len(result) == 1


def test_merge_composition():
    ext_a = lambda text: [Reference(number=1, raw="a", title="Title A")]
    ext_b = lambda text: [
        Reference(number=1, raw="b", title="", authors="Smith"),
        Reference(number=2, raw="b2", title="Title B"),
    ]
    merged = merge(ext_a, ext_b)
    result = merged("anything")
    assert len(result) == 2
    # Ref 1: title from ext_a, authors filled from ext_b
    assert result[0].title == "Title A"
    assert result[0].authors == "Smith"
    assert result[1].number == 2


def test_markdown_links_extractor():
    result = extract_references(SAMPLE_MARKDOWN_LINKS, extractor="markdown_links")
    assert len(result.references) == 2
    assert result.references[0].title == "Graph Theory"
    assert "example.com/graph.pdf" in result.references[0].url
    assert result.references[1].title == "Network Analysis"


def test_source_text_preserved():
    result = extract_references(SAMPLE_WITH_HEADER)
    for ref in result.references:
        assert ref.source_text  # Should not be empty


# ---------------------------------------------------------------------------
# Short, unnumbered one-line citations (paraphrased shapes of real failures)
# ---------------------------------------------------------------------------


def test_author_comma_single_quoted_title():
    (ref,) = extract_references("Jane Doe, 'Oak'").references
    assert (ref.authors, ref.title) == ("Jane Doe", "Oak")


def test_numbered_with_dot_by_author_and_year():
    (ref,) = extract_references('[1.] "Pine Cones," by Sam Roe, 2018').references
    assert (ref.number, ref.title, ref.authors, ref.year) == (
        1,
        "Pine Cones",
        "Sam Roe",
        "2018",
    )


def test_lowercase_author_then_quoted_title_no_comma():
    (ref,) = extract_references("sam roe 'big river'").references
    assert (ref.authors, ref.title) == ("sam roe", "big river")


def test_several_plain_lines_numbered_in_order():
    text = "Jane Doe, 'Oak'\n\nsam roe 'big river'\n"
    refs = extract_references(text).references
    assert [(r.number, r.title) for r in refs] == [(1, "Oak"), (2, "big river")]


def test_apostrophe_is_not_a_title_quote():
    (ref,) = extract_references("Jane Doe, Roe's guide to oaks").references
    assert ref.title == "Roe's guide to oaks"


def test_prose_is_not_a_reference():
    assert extract_references("hello there\n" + "word " * 100).references == []


def test_unquoted_author_comma_title():
    (ref,) = extract_references("Jane Doe, Oak Trees").references
    assert (ref.authors, ref.title) == ("Jane Doe", "Oak Trees")


def test_prose_code_table_url_lines_with_commas_are_not_references():
    junk = (
        "This is a note, with a comma.\n- Buy milk, eggs\ndef f(a, b):\n"
        "return a, b\n| x, y | z |\nhttps://example.com/a, b\n"
    )
    assert extract_references(junk).references == []


def test_leading_list_number_is_not_part_of_authors():
    (ref,) = extract_references("1. Jane Doe, Oak Trees").references
    assert ref.authors == "Jane Doe"
