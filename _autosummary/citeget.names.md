# citeget.names

Author-name parsing for libgen metadata.

Libgen supplies an `authors` field in a mix of conventions, and getting the
surname out of it is needed in two places: building the download filename
(`core._make_filename`) and matching a result against a requested author
(`rank.score_result`). This module is the single source of truth for that
parsing so the two never drift apart.

The conventions this handles:

```default
"Moore, Geoffrey A."                              surname first, comma inside one name
"Moore G.A."                                      surname first, joined initials
"Edward R. Tufte"                                 surname last
"Chris Voss & Tahl Raz"                           '&' between authors
"Tufte, Edward R. (author);Krasny, Dmitry (author)"   ';' between, role markers
"Brian Christian, Tom Griffiths"                  comma between authors
```

The rule that is easy to get wrong: \*\*a comma usually separates the surname
from the given name inside a single author\*\*, not one author from the next —
authors are separated by `;`, `&` or `and`. Libgen does occasionally put
a comma between full names too, so what a comma means is decided by whether the
text before it reads as a surname on its own (see `_reads_as_one_surname()`).

Basic use:

```default
>>> apa7_authors("Moore, Geoffrey A.")
'Moore'
>>> apa7_authors("Chris Voss & Tahl Raz")
'Voss & Raz'
>>> sorted(candidate_surnames("Cormen, T. (author);Leiserson, C. (author)"))
['cormen', 'leiserson']
```

#### NOTE
reference strings parsed out of a *document* (as opposed to libgen
metadata) use the opposite convention — `"A. B. Smith, C. D. Jones"` separates
authors with commas — and are handled by
`citeget.acquire_references._parse_all_surnames()` instead.

### Functions

| [`split_author_chunks`](#citeget.names.split_author_chunks)(authors)   | Split an authors string into one chunk per author, cleaned of role markers.   |
|---------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`surname_of`](#citeget.names.surname_of)(chunk)              | Extract the surname from a single author *chunk*, preserving its casing.      |
| [`surnames`](#citeget.names.surnames)(authors)              | Surnames of every author in *authors*, in order, casing preserved.            |
| [`candidate_surnames`](#citeget.names.candidate_surnames)(authors)    | Normalized surnames usable for matching, in either name ordering.             |
| [`apa7_authors`](#citeget.names.apa7_authors)(authors)          | Format *authors* APA 7 style, surnames only.                                  |
| [`normalize_name`](#citeget.names.normalize_name)(text)           | Fold *text* to lowercase ASCII alphanumerics plus spaces, for matching.       |

### citeget.names.apa7_authors(authors)

Format *authors* APA 7 style, surnames only.

1 author -> `"Smith"`; 2 -> `"Smith & Jones"`; 3+ -> `"Smith et al."`;
nothing usable -> `"Unknown"`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> apa7_authors("Moore, Geoffrey A.")
'Moore'
>>> apa7_authors("Tufte, Edward R. (author);Krasny, Dmitry (author)")
'Tufte & Krasny'
>>> apa7_authors("")
'Unknown'
```

### citeget.names.candidate_surnames(authors)

Normalized surnames usable for matching, in either name ordering.

Multi-word surnames contribute their last word, since that is what a
caller-supplied author string is most likely to share.

* **Return type:**
  [`set`](https://docs.python.org/3/builtins/stdtypes.html#set)

```pycon
>>> sorted(candidate_surnames("Alice Smith & Bob Jones"))
['jones', 'smith']
>>> sorted(candidate_surnames("Sander van der Linden"))
['linden']
```

### citeget.names.normalize_name(text)

Fold *text* to lowercase ASCII alphanumerics plus spaces, for matching.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> normalize_name("Émile Durkheim")
'emile durkheim'
```

### citeget.names.split_author_chunks(authors)

Split an authors string into one chunk per author, cleaned of role markers.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> split_author_chunks("Tufte, Edward R. (author);Krasny, Dmitry (author)")
['Tufte, Edward R.', 'Krasny, Dmitry']
>>> split_author_chunks("Chris Voss & Tahl Raz")
['Chris Voss', 'Tahl Raz']
>>> split_author_chunks("Brian Christian, Tom Griffiths")
['Brian Christian', 'Tom Griffiths']
```

### citeget.names.surname_of(chunk)

Extract the surname from a single author *chunk*, preserving its casing.

If the chunk contains a comma, the surname is everything before it
(libgen’s `"Surname, Given"` form). Otherwise it is the last token that
is not an initial.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> surname_of("Moore, Geoffrey A.")
'Moore'
>>> surname_of("Edward R. Tufte")
'Tufte'
>>> surname_of("van der Linden, Sander")
'van der Linden'
>>> surname_of("Martin Luther King Jr.")
'King'
>>> surname_of("Moore G.A.")
'Moore'
```

### citeget.names.surnames(authors)

Surnames of every author in *authors*, in order, casing preserved.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> surnames("Tufte, Edward R. (author);Krasny, Dmitry (author)")
['Tufte', 'Krasny']
>>> surnames("Chris Voss & Tahl Raz")
['Voss', 'Raz']
```
