"""Tests for citeget.merge_keyed: numbering, dedupe, glossary, missing, conflicts."""

from citeget import merge_keyed, merge_keyed_report

P1 = """Intro {ref:b} then {ref:a}.
<!-- REFERENCES -->
- a | Entry A.
b | Entry B.
<!-- GLOSSARY -->
Zeta | last
"""
P2 = """More {ref:a} and {ref:ghost}.
<!-- REFERENCES -->
a | Entry A.
<!-- GLOSSARY -->
alpha | first
Zeta | ignored duplicate
"""


def test_numbering_in_order_of_first_appearance_and_dedupe():
    r = merge_keyed_report([P1, P2], head="# Title")
    assert r.order == {"b": 1, "a": 2, "ghost": 3}
    assert "Intro [1] then [2]." in r.text
    assert "More [2] and [3]." in r.text
    assert r.text.count("Entry A.") == 1


def test_missing_and_references_section():
    r = merge_keyed_report([P1, P2])
    assert r.missing == ["ghost"]
    assert "[3] MISSING ghost" in r.text
    assert "## References\n\n[1] Entry B." in r.text


def test_glossary_sorted_case_insensitive_first_wins():
    r = merge_keyed_report([P1, P2])
    assert r.text.index("**alpha**") < r.text.index("**Zeta**")
    assert "**Zeta**: last" in r.text and "ignored" not in r.text


def test_tail_placeholders():
    out = merge_keyed([P1], tail="END\n{{REFERENCES}}\n--\n{{GLOSSARY}}")
    assert "END\n[1] Entry B." in out and "**Zeta**: last" in out


def test_conflicting_entries_reported():
    p3 = "x {ref:a}\n<!-- REFERENCES -->\na | Different A.\n"
    r = merge_keyed_report([P1, p3])
    assert r.conflicts == {"a": ["Entry A.", "Different A."]}
    assert "Entry A." in r.text  # first definition wins


def test_custom_cite_pattern_and_no_refs_section():
    out = merge_keyed(["see @@k@@\n<!-- REFERENCES -->\nk | K."], cite_pattern=r"@@(\w+)@@")
    assert out.startswith("see [1]")
    assert merge_keyed(["plain text"]).strip() == "plain text"
