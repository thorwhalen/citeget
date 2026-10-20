"""Main-article extraction, Wayback cleanup, and the fetch-level seam."""

import pytest

from citeget.content import clean_wayback, main_content
from citeget.fetch import html_to_markdown

ARTICLE = " ".join(f"Sentence number {i} of the essay body." for i in range(30))
PAGE = f"""
<html><body>
<a href="#content">Skip to content</a>
<nav><ul><li><a href="/a">View menu</a></li></ul></nav>
<div class="sidebar"><p>Your host</p></div>
<div id="content"><article><h1>Title</h1><p>{ARTICLE}</p><p>{ARTICLE}</p></article></div>
<div class="newsletter-box"><p>Subscribe now</p></div>
<footer>(c) site</footer>
</body></html>
"""


def test_main_drops_chrome():
    md = html_to_markdown(PAGE, content="main")
    assert "Sentence number 3 of the essay body." in md
    for junk in ("Skip to content", "View menu", "Your host", "Subscribe now", "(c) site"):
        assert junk not in md


def test_full_keeps_everything():
    md = html_to_markdown(PAGE, content="full")
    assert "View menu" in md and "(c) site" in md


def test_bad_content_value():
    with pytest.raises(ValueError):
        html_to_markdown(PAGE, content="some")


def test_table_layout_without_paragraphs():
    text = "word " * 200
    page = f"<table><tr><td><a href='/x'>home</a></td><td>{text}<br><br>{text}</td></tr></table>"
    md = html_to_markdown(page, content="main")
    assert "word word" in md and "home" not in md and "|" not in md


def test_custom_extractor_seam():
    md = html_to_markdown(PAGE, content="main", content_extractor=lambda h: f"<p>only me {ARTICLE}</p>")
    assert "only me" in md and "View menu" not in md and "(c) site" not in md


def test_include_links_false():
    html = "<p>see <a href='http://x.org'>this</a></p>"
    assert "[this]" in html_to_markdown(html)
    assert "http://x.org" not in html_to_markdown(html, include_links=False)


def test_wayback_links_and_toolbar():
    html = (
        "<!-- BEGIN WAYBACK TOOLBAR INSERT --><div>toolbar</div><!-- END WAYBACK TOOLBAR INSERT -->"
        f"<p>{ARTICLE} <a href='https://web.archive.org/web/20200101000000/http://x.org/a'>l</a></p>"
    )
    assert "toolbar" not in clean_wayback(html)
    md = html_to_markdown(
        html, source_url="https://web.archive.org/web/20200101000000/http://x.org/", content="main"
    )
    assert "(http://x.org/a)" in md and "web.archive.org/web/2020" not in md.split("\n", 2)[2]


def test_main_content_returns_html():
    assert "<p>" in main_content(PAGE)


def test_layout_wrapper_with_chrome_like_class_is_kept():
    page = f'<body><div class="has-sidebar"><p>{ARTICLE}</p></div></body>'
    assert "Sentence number 3" in html_to_markdown(page, content="main")


def test_tiny_extraction_falls_back_to_full_page():
    page = "<body><header><h1>Only title text here</h1></header></body>"
    assert "Only title text here" in html_to_markdown(page, content="main")


def test_unknown_extractor_name():
    with pytest.raises(ValueError):
        html_to_markdown(PAGE, content="main", content_extractor="nope")
