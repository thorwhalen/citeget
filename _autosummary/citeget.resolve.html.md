# citeget.resolve

Composable download and URL-resolution for academic references.

The acquisition pipeline has three layers:

- **UrlResolver** `(Reference) -> list[str]` — turn citation info into
  candidate download URLs (URL rewriting, DOI lookup, search APIs).
- **Downloader** `(url, filepath) -> bool` — fetch a URL, validate the
  content, save to disk.
- **AcquisitionStrategy** `(Reference, Path) -> Optional[str]` — a complete
  unit that combines resolvers and downloaders (or does its own thing, like
  libgen’s playwright-based search+download).

## Extension semantics

The `filepath` argument to downloaders and strategies is **advisory**: it
tells them where you intend the final file to live. They *may* write to a
neighbouring path with a different extension when the downloaded content is
not a PDF (e.g. EPUB, MOBI, DjVu). Callers should use the final path
reported by the strategy rather than assuming the `.pdf` target was
written. The higher-level [`citeget.acquire_references.acquire_reference()`](citeget.acquire_references.html.md#citeget.acquire_references.acquire_reference)
function handles this finalisation — and the hard rule “no `.pdf` extension
on non-PDF content” — automatically.

The factory [`resolve_and_download()`](#citeget.resolve.resolve_and_download) wires a resolver to a downloader.
[`chain()`](#citeget.resolve.chain) composes strategies (try first, fall back to second).

Usage:

```default
from citeget.resolve import resolve_reference

# Zero-config: tries all built-in strategies in order
path = resolve_reference(ref, Path("paper.pdf"))

# Custom chain
from citeget.resolve import chain, STRATEGIES
my = chain(STRATEGIES["direct"], STRATEGIES["arxiv_search"])
resolve_reference(ref, filepath, strategy=my)

# Add a repository rule
from citeget.resolve import url_rewriter, BUILTIN_URL_RULES, register_resolver
rules = {**BUILTIN_URL_RULES, "myrepo.org": lambda u: u.replace("/view/", "/dl/")}
register_resolver("my_rewriter", url_rewriter(rules=rules))
```

### Functions

| [`arxiv_search_resolver`](#citeget.resolve.arxiv_search_resolver)()                          | Search the arxiv API by author + title, return PDF URLs.                                                             |
|---------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------|
| [`chain`](#citeget.resolve.chain)(\*strategies)                              | Try *strategies* in order, return the first success.                                                                 |
| [`chain_resolvers`](#citeget.resolve.chain_resolvers)(\*resolvers)                     | Concatenate URL lists from multiple resolvers (deduped, order-preserving).                                           |
| [`doi_resolver`](#citeget.resolve.doi_resolver)(\*[, email])                        | Resolve via DOI: Crossref lookup → Unpaywall (open access) → Sci-Hub.                                                |
| [`get_downloader`](#citeget.resolve.get_downloader)(name)                             | Retrieve a registered downloader by name.                                                                            |
| [`get_resolver`](#citeget.resolve.get_resolver)(name)                               | Retrieve a registered resolver by name.                                                                              |
| [`get_strategy`](#citeget.resolve.get_strategy)(name)                               | Retrieve a registered strategy by name.                                                                              |
| [`libgen_strategy`](#citeget.resolve.libgen_strategy)(\*[, topics, timeout])           | Wrap the existing libgen search+download as an [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy). |
| [`list_downloaders`](#citeget.resolve.list_downloaders)()                               | Return names of all registered downloaders.                                                                          |
| [`list_resolvers`](#citeget.resolve.list_resolvers)()                                 | Return names of all registered resolvers.                                                                            |
| [`list_strategies`](#citeget.resolve.list_strategies)()                                | Return names of all registered strategies.                                                                           |
| [`register_downloader`](#citeget.resolve.register_downloader)(name, downloader)            | Register a named downloader.                                                                                         |
| [`register_resolver`](#citeget.resolve.register_resolver)(name, resolver)                | Register a named URL resolver.                                                                                       |
| [`register_strategy`](#citeget.resolve.register_strategy)(name, strategy)                | Register a named acquisition strategy.                                                                               |
| [`resolve_and_download`](#citeget.resolve.resolve_and_download)(resolver, \*[, downloader]) | Create a strategy that resolves URLs then tries to download each.                                                    |
| [`resolve_reference`](#citeget.resolve.resolve_reference)(ref, filepath, \*[, strategy]) | Resolve and download a single reference.                                                                             |
| [`scihub_strategy`](#citeget.resolve.scihub_strategy)()                                | Wrap the existing Sci-Hub/DOI download as an [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy).   |
| [`semantic_scholar_resolver`](#citeget.resolve.semantic_scholar_resolver)()                      | Query the Semantic Scholar API for open-access PDF links.                                                            |
| [`url_rewriter`](#citeget.resolve.url_rewriter)(\*[, rules])                        | Create a resolver that rewrites known repository URLs to direct PDFs.                                                |
| [`with_logging`](#citeget.resolve.with_logging)(strategy, \*[, name, log_entries])  | Wrap a strategy to append a log entry on each call.                                                                  |

### Classes

| [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)(\*args, \*\*kwargs)   | Complete acquire-one-reference unit.               |
|--------------------------------------------------------------------------------------------|----------------------------------------------------|
| [`Downloader`](#citeget.resolve.Downloader)(\*args, \*\*kwargs)            | Fetch *url*, validate content, save to *filepath*. |
| [`UrlResolver`](#citeget.resolve.UrlResolver)(\*args, \*\*kwargs)           | Turn a `Reference` into candidate download URLs.   |

### *class* citeget.resolve.AcquisitionStrategy(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Complete acquire-one-reference unit.

`filepath` is advisory — the returned path may differ in extension
from what was passed in (see module docstring).

Returns the filepath string on success, `None` on failure.

### *class* citeget.resolve.Downloader(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Fetch *url*, validate content, save to *filepath*.

`filepath` is advisory — the actual written path may have a different
extension reflecting the real content format (see module docstring).

Returns `True` on success.

### *class* citeget.resolve.UrlResolver(\*args, \*\*kwargs)

Bases: [`Protocol`](https://docs.python.org/3/library/typing.html#typing.Protocol)

Turn a `Reference` into candidate download URLs.

### citeget.resolve.arxiv_search_resolver()

Search the arxiv API by author + title, return PDF URLs.

* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.chain(\*strategies)

Try *strategies* in order, return the first success.

* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)

### citeget.resolve.chain_resolvers(\*resolvers)

Concatenate URL lists from multiple resolvers (deduped, order-preserving).

* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.doi_resolver(, email='')

Resolve via DOI: Crossref lookup → Unpaywall (open access) → Sci-Hub.

* **Parameters:**
  **email** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Email for the Unpaywall API (optional; skipped if empty).
* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.get_downloader(name)

Retrieve a registered downloader by name.

* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If *name* is not registered.
* **Return type:**
  [`Downloader`](#citeget.resolve.Downloader)

### citeget.resolve.get_resolver(name)

Retrieve a registered resolver by name.

* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If *name* is not registered.
* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.get_strategy(name)

Retrieve a registered strategy by name.

* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If *name* is not registered.
* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)

### citeget.resolve.libgen_strategy(, topics=('articles', 'books'), timeout=30000)

Wrap the existing libgen search+download as an [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy).

This is a self-contained strategy (not a resolver+downloader pair) because
libgen requires playwright-based browser automation for both search and
download.

* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)

### citeget.resolve.list_downloaders()

Return names of all registered downloaders.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.resolve.list_resolvers()

Return names of all registered resolvers.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.resolve.list_strategies()

Return names of all registered strategies.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### citeget.resolve.register_downloader(name, downloader)

Register a named downloader.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.resolve.register_resolver(name, resolver)

Register a named URL resolver.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.resolve.register_strategy(name, strategy)

Register a named acquisition strategy.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### citeget.resolve.resolve_and_download(resolver, , downloader=None)

Create a strategy that resolves URLs then tries to download each.

* **Parameters:**
  * **resolver** ([`UrlResolver`](#citeget.resolve.UrlResolver) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – A [`UrlResolver`](#citeget.resolve.UrlResolver) callable or registered name.
  * **downloader** ([`Downloader`](#citeget.resolve.Downloader) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – A [`Downloader`](#citeget.resolve.Downloader) callable or registered name.
    `None` uses the `"pdf"` downloader.
* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)

### citeget.resolve.resolve_reference(ref, filepath, , strategy=None)

Resolve and download a single reference.

* **Parameters:**
  * **ref** ([`Reference`](citeget.acquire_references.html.md#citeget.acquire_references.Reference)) – The reference to acquire.
  * **filepath** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)) – Target file path for the download.
  * **strategy** ([`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – An [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy) callable, a registered
    strategy name (`str`), or `None` to use `"default"`.
* **Return type:**
  [`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
* **Returns:**
  Filepath string on success, `None` on failure.
* **Raises:**
  [**KeyError**](https://docs.python.org/3/builtins/exceptions.html#KeyError) – If a string name is not in the registry.

### citeget.resolve.scihub_strategy()

Wrap the existing Sci-Hub/DOI download as an [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy).

* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)

### citeget.resolve.semantic_scholar_resolver()

Query the Semantic Scholar API for open-access PDF links.

* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.url_rewriter(, rules=None)

Create a resolver that rewrites known repository URLs to direct PDFs.

* **Parameters:**
  **rules** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – Domain-substring → transform mapping.
  `None` uses `BUILTIN_URL_RULES`.
* **Return type:**
  [`UrlResolver`](#citeget.resolve.UrlResolver)

### citeget.resolve.with_logging(strategy, , name='', log_entries=None)

Wrap a strategy to append a log entry on each call.

* **Parameters:**
  * **strategy** ([`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)) – The strategy to wrap.
  * **name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Label for log entries.
  * **log_entries** ([`list`](https://docs.python.org/3/builtins/stdtypes.html#list) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – List to append dicts to (mutated in place).
* **Return type:**
  [`AcquisitionStrategy`](#citeget.resolve.AcquisitionStrategy)
