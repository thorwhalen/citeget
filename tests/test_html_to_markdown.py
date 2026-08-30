"""Tests for the HTML→Markdown converter used by the general `fetch` path."""

from citeget.fetch import html_to_markdown

SAMPLE_HTML = """
<html><head><title>Page title</title><style>body{color:red}</style>
<script>var x = 1;</script></head>
<body>
<h1>Heading One</h1>
<p>Some <b>bold</b> and <em>italic</em> text with a
<a href="https://example.com/a">link</a> and an <img src="p.png" alt="pic">.</p>
<ul><li>alpha</li><li>beta with <code>inline_code()</code></li></ul>
<pre><code>def f():
    return 1
</code></pre>
<table><thead><tr><th>A</th><th>B</th></tr></thead>
<tbody><tr><td>1</td><td>2</td></tr></tbody></table>
<blockquote>Quoted — with an em dash and a café.</blockquote>
</body></html>
"""


def test_structure_survives_conversion():
    md = html_to_markdown(SAMPLE_HTML)
    assert "# Heading One" in md  # ATX headings, not setext
    assert "**bold**" in md and "*italic*" in md
    assert "[link](https://example.com/a)" in md
    assert "* alpha" in md
    assert "`inline_code()`" in md
    assert "| A | B |" in md  # GitHub-flavoured table
    assert "> Quoted" in md
    assert "café" in md  # unicode passes through unescaped


def test_non_content_tags_are_dropped():
    md = html_to_markdown(SAMPLE_HTML)
    assert "Page title" not in md
    assert "color:red" not in md
    assert "var x" not in md
    assert "p.png" not in md  # images are stripped, not rendered


def test_paragraphs_are_not_hard_wrapped():
    long_sentence = " ".join(["word"] * 60)
    md = html_to_markdown(f"<p>{long_sentence}</p>")
    assert long_sentence in md


def test_source_url_is_recorded_as_a_comment():
    md = html_to_markdown("<p>hi</p>", source_url="https://example.com/x")
    assert md.startswith("<!-- Source: https://example.com/x -->")


def test_defaults_can_be_overridden():
    md = html_to_markdown("<p>a</p><ul><li>b</li></ul>", bullets="-")
    assert "- b" in md
