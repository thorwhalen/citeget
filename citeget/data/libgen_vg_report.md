# Comprehensive Automation Report: Libgen (libgen.vg) Search & Download Flow

## 1. Overview of the Two-Page Flow

The automation workflow consists of two pages:

**Page 1 — Search Results Page** (`/index.php`): Displays a table of results with metadata columns and mirror links.

**Page 2 — Mirror/Download Page** (`/ads.php`): An intermediate page with a prominent "GET" link that triggers the actual file download via `/get.php`.

---

## 2. Search Results Page (`/index.php`)

### 2.1 URL Construction

The search is performed via a `GET` request to `index.php`. The URL you provided decodes to these query parameters:

| Parameter | Value(s) | Meaning |
|---|---|---|
| `req` | `Scattering number in graphs` | The search query (space-separated, `+` encoded) |
| `columns[]` | `t`, `a`, `s`, `y`, `p`, `i` | Search in fields: Title, Author, Series, Year, Publisher, ISBN |
| `objects[]` | `f`, `e`, `s`, `a`, `p`, `w` | Search in objects: Files, Editions, Series, Authors, Publishers, Works |
| `topics[]` | `a` | Search topic: Scientific Articles (other values: `l`=Libgen, `c`=Comics, `f`=Fiction, `m`=Magazines, `r`=Fiction RUS, `s`=Standards) |
| `res` | `25` | Results per page (options: 25, 50, 100) |
| `filesuns` | `all` | Seach in files filter (options: `all`, sorted only, unsorted only) |

An automation script can construct the URL directly without needing to interact with the form. For example:
```
https://libgen.vg/index.php?req={query}&columns[]=t&columns[]=a&columns[]=s&columns[]=y&columns[]=p&columns[]=i&objects[]=f&objects[]=e&objects[]=s&objects[]=a&objects[]=p&objects[]=w&topics[]={topic}&res=25&filesuns=all
```

### 2.2 Page DOM Structure

The page body has this top-level structure:
- `NAV.navbar` — top navigation bar
- `FORM#formlibgen.card` — the search form
- `UL.nav.nav-tabs` — result category tabs (Files, Editions, Series, Authors, Publishers, Works, JSON)
- `TABLE#tablelibgen.table.table-striped` — **the main results table** (this is the key element)
- Bottom nav, modals (Donate, About, DMCA)

The critical element for automation is `table#tablelibgen`.

### 2.3 Results Table Structure

The table has the ID `tablelibgen` and uses Bootstrap classes `table table-striped`. It has 9 columns:

| Column Index | Header Text | Content Description |
|---|---|---|
| 0 | ID / Time add. / Title / Series | Combined cell containing: series name (link to `series.php`), volume/issue info (link to `edition.php`), page range, **article title** (link to `edition.php`), DOI, and an internal ID badge |
| 1 | Author(s) | Semicolon-separated author names as plain text |
| 2 | Publisher | Publisher name (often empty for articles) |
| 3 | Year | Year and month (e.g. "2001 March", "2019 July") |
| 4 | Language | Language string (e.g. "English") |
| 5 | Pages | Page count (often "0" for articles) |
| 6 | Size | File size as a link to `/file.php?id=<ID>` (e.g. "75 kB", "400 kB", "2 MB") |
| 7 | Ext. | File extension (e.g. "pdf") |
| 8 | Mirrors | Five mirror links: Libgen, Sci-Hub, Randombook, libgen.pw, Anna's arch |

**Key observation**: Column 0 is a "compound cell" — it bundles the series, volume, page range, title, and DOI all in one `<td>`. The article **title** can be extracted by finding the link whose text does NOT start with a date pattern and does NOT start with "DOI:". Specifically, inside column 0, the links are structured as:
1. Series name → links to `series.php?id=<ID>`
2. Volume/issue/date → links to `edition.php?id=<ID>`
3. **Article title** → links to `edition.php?id=<ID>` (this is the one you want)
4. DOI → links to `edition.php?id=<ID>`, text starts with "DOI:"

For this search, all 5 result rows returned data, and all 5 had identical mirror structures (5 mirrors each). The tab counts showed "Files 5" and "Editions 8" — the default view is the "Files" tab.

### 2.4 Mirror Links Pattern

Every result row (in the "Mirrors" column, index 8) has exactly 5 links:

| Mirror | URL Pattern | Notes |
|---|---|---|
| **Libgen** | `/ads.php?md5=<MD5>&downloadname=<DOI_OR_ID>` | Internal — leads to the download page (Page 2) |
| Sci-Hub | `http://sci-hub.ru/<DOI>` | External |
| Randombook | `https://randombook.org/book/<MD5>` | External |
| libgen.pw | `https://libgen.pw/book/<MD5>` | External |
| Anna's arch | `https://en.annas-archive.gl/md5/<MD5>?r=<TOKEN>` | External |

The **first mirror is always "Libgen"** and always uses the `/ads.php` path with `md5` and `downloadname` parameters. The MD5 hash is the universal identifier across all mirrors for a given file.

### 2.5 Pagination

For this search (5 results, limit 25), no pagination links were present. The script should check for pagination elements if more results are expected — but none were observed in this case, so the pagination selector is unknown and may need investigation for larger result sets.

### 2.6 JSON API

There is a JSON tab link visible in the tab bar that points to `/json.php?object=f&ids=<COMMA_SEPARATED_FILE_IDS>`. This could be a valuable alternative to HTML scraping — the script could potentially call this API directly to get structured metadata. The "OTHERS" menu also has a standalone `json.php` API link and a `batchsearchindex.php` for batch searching.

---

## 3. Download Page (`/ads.php`)

### 3.1 URL Pattern

```
/ads.php?md5=<32-char-MD5-hash>&downloadname=<URL-encoded-DOI-or-identifier>
```

Example: `/ads.php?md5=1a756e62437f1a16721998aac817e172&downloadname=10.1002/1097-0037(200103)37:2%3C102::aid-net5%3E3.0.co;2-s`

### 3.2 Page DOM Structure

The page body has:
- `NAV.navbar` — same top nav as search page
- `TABLE#main` — the main content table (4 rows total)
- Bottom nav and modals

The `TABLE#main` layout:
- **Row 0**: Contains the **GET download link** — this is the critical element
- **Row 1**: Metadata display (Title, Series, Author, Publisher, Year, ISBN) plus a cover image thumbnail and a BibTeX textarea
- **Row 2**: Reserved area
- **Row 3**: External search links (WorldCat, Goodreads, AbeBooks)

### 3.3 The GET Download Button

This is the critical automation target. Structure:
- It is an `<a>` tag containing an `<h2>` element with text "GET"
- It has a large green background (visually prominent)
- **CSS Selector**: `a[href*="get.php"]` or equivalently `#main a h2` then `.parentElement`
- **URL Pattern**: `get.php?md5=<MD5_HASH>&key=<16-CHAR-SESSION-KEY>`

The `key` parameter is a 16-character alphanumeric string that appears to be a **session-based or time-based token** — it is likely generated server-side when the `/ads.php` page loads and may be single-use or time-limited. This means the script **cannot skip the ads.php page** and go directly to `get.php` — it must first load `/ads.php`, parse the GET link's href to extract the key, and then navigate to or request the `get.php` URL.

### 3.4 Metadata on Download Page

The download page displays structured metadata as plain text:
- Title, Series, Author(s), Publisher, Year, ISBN
- A BibTeX-formatted citation in a `<textarea>`
- A small cover image

### 3.5 Ads

The page loads ad scripts from `inopportunefable.com`. These inject iframes and run A/B testing via cookies. For a headless browser automation, these can be ignored or blocked entirely (e.g., using Playwright's route interception to block ad domains). They should not interfere with the download flow.

---

## 4. Recommended Automation Architecture (Playwright/Python)

### 4.1 Suggested Flow

```
1. Construct search URL from keywords + parameters
2. Navigate to search results page
3. Wait for table#tablelibgen to load
4. Parse result rows, extract metadata from each row
5. Apply user-defined matching logic to metadata
6. If match found: extract the "Libgen" mirror href from column 8 (first <a> in the mirrors cell)
7. Navigate to the /ads.php page
8. Wait for the GET link (a[href*="get.php"]) to appear
9. Extract the full href (contains the session key)
10. Use the get.php URL to download the file
```

### 4.2 Key Selectors for Playwright

| Purpose | Selector | Notes |
|---|---|---|
| Results table | `#tablelibgen` | Unique ID, reliable |
| Data rows | `#tablelibgen tr:nth-child(n+2)` | Skip header (row 0) |
| Title cell | `#tablelibgen tr td:nth-child(1)` | Compound cell — parse inner links |
| Authors cell | `#tablelibgen tr td:nth-child(2)` | Plain text, semicolon-separated |
| Publisher cell | `#tablelibgen tr td:nth-child(3)` | |
| Year cell | `#tablelibgen tr td:nth-child(4)` | Format: "YYYY Month" or "YYYY Month Day" |
| Language cell | `#tablelibgen tr td:nth-child(5)` | |
| Size cell | `#tablelibgen tr td:nth-child(7)` | Contains link to file.php |
| Extension cell | `#tablelibgen tr td:nth-child(8)` | |
| Mirrors cell | `#tablelibgen tr td:nth-child(9)` | |
| First mirror (Libgen) | `#tablelibgen tr td:nth-child(9) a:first-child` | Always "Libgen" |
| GET download button | `a[href*="get.php"]` | On the ads.php page, inside `#main` |
| BibTeX textarea | `#main textarea` | On the ads.php page |

### 4.3 Extracting the Article Title from Column 0

Column 0 is the trickiest to parse. It contains multiple links. The article title is the link whose `href` starts with `edition.php` and whose text content does **not** match a date/volume pattern (like "2001-mar vol. 37 iss. 2") and does **not** start with "DOI:". A reliable approach:

```python
title_cell = row.query_selector('td:nth-child(1)')
links = title_cell.query_selector_all('a')
for link in links:
    href = link.get_attribute('href') or ''
    text = link.text_content().strip()
    if href.startswith('edition.php') and not text.startswith('DOI:') and not re.match(r'\d{4}-', text):
        article_title = text
        break
```

The DOI can be extracted similarly (find the link whose text starts with "DOI:").

### 4.4 Important Considerations

**Session key on GET link**: The `get.php` URL includes a `key` parameter that is generated when `ads.php` loads. You must load the ads.php page in the browser context first, then extract the key. A direct HTTP request to `get.php` without a valid key will likely fail.

**Ad blocking**: Consider blocking `inopportunefable.com` via Playwright's `page.route()` to speed up page loads and avoid unwanted script execution.

**Rate limiting**: The site shows "Users online" counts (10,000+), suggesting it's public and high-traffic. Still, add reasonable delays between requests to avoid being blocked.

**No pagination observed**: For searches with many results, investigate what pagination looks like. The `res` parameter controls results per page (25/50/100). Setting it to 100 reduces the need for pagination.

**JSON API alternative**: The `/json.php?object=f&ids=<IDS>` endpoint could provide structured data without HTML parsing. Investigating this API could simplify the metadata extraction step significantly.

**`file.php` direct download**: Each result's Size column links to `/file.php?id=<FILE_ID>`. This might be another download path worth investigating — if it serves files directly, it could bypass the ads.php intermediary. However, the `get.php` path via `ads.php` is the documented "Libgen mirror" flow.

**Content-Disposition header**: When the script finally requests the `get.php` URL, it should check the `Content-Disposition` response header for the actual filename and use that when saving the file.

**Topics parameter is critical**: In this search, `topics[]=a` selected "Scientific Articles." For books, you'd use `topics[]=l` (Libgen). This dramatically affects result types.