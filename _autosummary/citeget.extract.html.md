# citeget.extract

Composable reference extraction from documents.

An **extractor** is any `Callable[[str], list[Reference]]`.  This module
provides a registry of named extractors, a regex-based factory for creating
new ones, and composition helpers (`chain`, `merge`) for combining them.

The main entry point is [`extract_references()`](#citeget.extract.extract_references), which runs the default
extraction chain (or a caller-specified extractor) and returns an
[`ExtractionResult`](#citeget.extract.ExtractionResult).

Usage:

```default
from citeget.extract import extract_references

result = extract_references(document_text)
for ref in result.references:
    print(ref.number, ref.title)

# Custom extractor
from citeget.extract import regex_extractor, register
my_ext = regex_extractor(section_patterns=(r"(?mi)^REFERENCES\s*$",))
register("ieee", my_ext)

# Compose
from citeget.extract import chain
combined = chain(my_ext, extract_references)
```

### Functions

| [`ai_extractor`](#citeget.extract.ai_extractor)(text)                           | Placeholder extractor that signals AI extraction is needed.         |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------|
| [`chain`](#citeget.extract.chain)(\*extractors)                          | Try *extractors* in order, return the first non-empty result.       |
| [`extract_references`](#citeget.extract.extract_references)(text, \*[, extractor])    | Extract references from document text.                              |
| [`get_extractor`](#citeget.extract.get_extractor)(name)                          | Retrieve a registered extractor by name.                            |
| [`list_extractors`](#citeget.extract.list_extractors)()                            | Return names of all registered extractors.                          |
| [`load_extractors`](#citeget.extract.load_extractors)(path)                        | Load extractors from a JSON file and register them.                 |
| [`markdown_link_extractor`](#citeget.extract.markdown_link_extractor)(\*[, context_chars]) | Create an extractor that treats every `[name](url)` as a reference. |
| [`merge`](#citeget.extract.merge)(\*extractors)                          | Run all *extractors*, deduplicate by reference number.              |
| [`regex_extractor`](#citeget.extract.regex_extractor)(\*[, section_patterns, ...]) | Create an extractor from regex patterns.                            |
| [`register`](#citeget.extract.register)(name, extractor)                    | Register a named extractor.                                         |
| [`save_extractors`](#citeget.extract.save_extractors)(path, \*[, names])           | Save regex-based extractors to a JSON file.                         |

### Classes

| [`ExtractionResult`](#citeget.extract.ExtractionResult)(references[, ...])   | Result of extracting references from text.   |
|----------------------------------------------------------------------------------------|----------------------------------------------|
| [`Extractor`](#citeget.extract.Extractor)(\*args, \*\*kwargs)         | Any callable: `(str) -> list[Reference]`.    |

### Exceptions

| [`AIExtractionRequested`](#citeget.extract.AIExtractionRequested)   | Signal that AI-based extraction should be used.   |
|--------------------------------------------------------------------------|---------------------------------------------------|

### *exception* citeget.extract.AIExtractionRequested

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

Signal that AI-based extraction should be used.

Not an error — a control-flow signal caught by the CLI or agent layer.

### *class* citeget.extract.ExtractionResult(references, extractor_name='', confidence='unknown')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Result of extracting references from text.

### *class* citeget.extract.Extractor(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Any callable: `(str) -> list[Reference]`.

### citeget.extract.ai_extractor(text)

Placeholder extractor that signals AI extraction is needed.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Reference`](citeget.acquire_references.html.md#citeget.acquire_references.Reference)]

### citeget.extract.chain(\*extractors)

Try *extractors* in order, return the first non-empty result.

* **Return type:**
  [`Extractor`](#citeget.extract.Extractor)

### citeget.extract.extract_references(text, , extractor=None)

Extract references from document text.

* **Parameters:**
  * **text** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Full document text.
  * **extractor** ([`Extractor`](#citeget.extract.Extractor) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – An [`Extractor`](#citeget.extract.Extractor) callable, a registered extractor
    name (`str`), or `None` to use the `"default"` chain.
* **Return type:**
  [`ExtractionResult`](#citeget.extract.ExtractionResult)
* **Returns:**
  [`ExtractionResult`](#citeget.extract.ExtractionResult) with parsed references and metadata.
* **Raises:**
  * [**AIExtractionRequested**](#citeget.extract.AIExtractionRequested) – If the `"ai"` extractor is selected.
  * [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If a string name is not in the registry.

### citeget.extract.get_extractor(name)

Retrieve a registered extractor by name.

* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If *name* is not registered.
* **Return type:**
  [`Extractor`](#citeget.extract.Extractor)

### citeget.extract.list_extractors()

Return names of all registered extractors.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.extract.load_extractors(path)

Load extractors from a JSON file and register them.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Names of the extractors that were loaded and registered.

### citeget.extract.markdown_link_extractor(, context_chars=200)

Create an extractor that treats every `[name](url)` as a reference.

Each markdown hyperlink becomes a `Reference` with:

- `title` ← the link text (*name*)
- `url` ← the link target
- `raw` ← the surrounding context (up to *context_chars* around the link)
- `source_text` ← same context, preserving original formatting
- `year` ← extracted from context if a 4-digit year is nearby
- `authors` ← extracted from context if text before the link looks
  like an author list (heuristic: comma-separated capitalised words)

* **Parameters:**
  **context_chars** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – How many characters of surrounding text to capture
  on each side of the link.
* **Return type:**
  [`Extractor`](#citeget.extract.Extractor)

### citeget.extract.merge(\*extractors)

Run all *extractors*, deduplicate by reference number.

Fields from earlier extractors take priority; later ones fill blanks.

* **Return type:**
  [`Extractor`](#citeget.extract.Extractor)

### citeget.extract.regex_extractor(, section_patterns=('(?mi)^#{1,3}\\\\\\\\s\*(references|bibliography|works\\\\\\\\s+cited|literature)\\\\\\\\s\*$',), entry_pattern='^\\\\\\\\s\*\\\\\\\\[(\\\\\\\\d+)\\\\\\\\]', stop_pattern='(?m)^#{1,3}\\\\\\\\s+\\\\\\\\S', whole_document_fallback=True)

Create an extractor from regex patterns.

* **Parameters:**
  * **section_patterns** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]) – Regexes to find the start of a references section.
    Tried in order; first match wins.  Pass `()` to skip header
    detection entirely.
  * **entry_pattern** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Regex matching the start of a reference entry.
    Must have group(1) capturing the reference number.
  * **stop_pattern** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Regex signalling the end of the section (e.g. a new
    heading).  `None` means extract to end of text.
  * **whole_document_fallback** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If no section header is found, scan the
    whole document for *entry_pattern* matches.
* **Return type:**
  [`Extractor`](#citeget.extract.Extractor)

### citeget.extract.register(name, extractor)

Register a named extractor.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.extract.save_extractors(path, , names=None)

Save regex-based extractors to a JSON file.

Only extractors whose underlying callable carries a `_config` dict
(i.e. those created via [`regex_extractor()`](#citeget.extract.regex_extractor)) can be serialised.
Built-in names (`default`, `ai`) are skipped.

* **Parameters:**
  * **path** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – JSON file to write.
  * **names** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Extractor names to save.  `None` saves all serialisable ones.
* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)
