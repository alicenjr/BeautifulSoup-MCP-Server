## flipkart-scraper-mcp

Lightweight HTML scraper using Requests + BeautifulSoup with a small SQLite store and an MCP server (via `fastmcp`) exposing scraping and read APIs.

This project does not use Playwright. It performs fast, static HTML fetches suitable for simple pages and list pagination.

---

### Features
- **MCP tools**: health check, quick title fetch, multi-page scrape with storage, and read access to scraped text
- **SQLite storage** with normalized tables for pages, text content, headings, links, and images
- **Simple pagination**: use `{page}` placeholder or an automatic `?page=` query parameter

---

### Requirements
- Python >= 3.13
- Windows, macOS, or Linux

Dependencies (see `pyproject.toml`):
- `requests`
- `beautifulsoup4`
- `lxml`
- `fastmcp`

---

### Installation
Using uv (recommended):
```bash
uv sync
```

Or using pip:
```bash
pip install -e .
# or, if not using an editable install:
pip install -r <(uv export --format requirements-txt)  # optional if you export
```

---

### Running
Interactive CLI mode (scrape pages, then optionally start the server):
```bash
python min.py
```

Non-interactive MCP server mode:
```bash
python min.py --server
```

The default SQLite database path is `flipkart.db` in the project root.

---

### Available MCP Tools
The MCP server (from `min.py`) registers the following tools:

1) `health_check`
   - Returns a basic success payload to verify the server is running.

2) `fetch_page_title`
   - Input: `{ "url": string }`
   - Fetches a single URL and returns `{ ok, title, url, status_code }`.

3) `scrape_pages_store_sqlite`
   - Input: `{ "url": string, "num_pages"?: number }`
   - Behavior:
     - If `url` includes `{page}`, it is replaced with page numbers starting at 1.
     - Otherwise a `page` query parameter is added/replaced.
   - Returns: summary `{ ok, pages_scraped, errors, results[] }` and stores data into SQLite.

4) `read_page_text`
   - Input: `{ "page_id"?: number, "contains"?: string, "limit"?: number, "offset"?: number }`
   - Read-only access to the `page_text` table. Returns `{ ok, rows, count }`.

---

### Example Calls (conceptual)
Fetch a quick title:
```bash
mcp call fetch_page_title '{"url": "https://example.com"}'
```

Scrape multiple pages using a placeholder:
```bash
mcp call scrape_pages_store_sqlite '{"url": "https://example.com/list?page={page}", "num_pages": 3}'
```

Scrape when the site already uses a `?page=` query:
```bash
mcp call scrape_pages_store_sqlite '{"url": "https://example.com/list?q=phones", "num_pages": 2}'
```

Query stored text content containing a keyword (latest first):
```bash
mcp call read_page_text '{"contains": "iphone", "limit": 20}'
```

---

### Database Schema
On first run, the following tables are created in `flipkart.db`:

- `pages`
  - `id` INTEGER PRIMARY KEY
  - `url` TEXT UNIQUE
  - `status_code` INTEGER
  - `title` TEXT
  - `meta_description` TEXT
  - `meta_keywords` TEXT
  - `fetched_at` TEXT (UTC ISO8601)

- `page_text`
  - `id` INTEGER PRIMARY KEY
  - `page_id` INTEGER REFERENCES `pages(id)`
  - `content` TEXT

- `headings`
  - `id` INTEGER PRIMARY KEY
  - `page_id` INTEGER REFERENCES `pages(id)`
  - `level` TEXT  (e.g., `h1`..`h6`)
  - `text` TEXT

- `links`
  - `id` INTEGER PRIMARY KEY
  - `page_id` INTEGER REFERENCES `pages(id)`
  - `href` TEXT
  - `text` TEXT

- `images`
  - `id` INTEGER PRIMARY KEY
  - `page_id` INTEGER REFERENCES `pages(id)`
  - `src` TEXT
  - `alt` TEXT

---

### Notes and Limitations
- Designed for static HTML. Sites requiring JS rendering may return limited content.
- Keep reasonable request timeouts and respect target sites' robots and rate limits.
- The database file path is fixed to `flipkart.db` in the current implementation.

---

### Development
Run with auto-reload or your preferred debugger. Code entrypoint is `min.py`. The FastMCP app name is `test-scraper`.

