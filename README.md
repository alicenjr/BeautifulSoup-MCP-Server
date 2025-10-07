## Setup

1. Install uv (recommended) or use pip.
2. Install dependencies:

```bash
uv sync
# or
pip install -r requirements.txt  # if you export one
```

3. Install Playwright browsers (one-time):

```bash
python -m playwright install --with-deps
```

## Usage

Run the MCP server locally:

```bash
python min.py
```

Available tools:
- `scrape(url, db_path?, table_name?)`: scrape a Flipkart listing/product URL and store results in SQLite.
- `db_query(db_path?, table_name?, limit?, order_by?, name_contains?)`: query recent rows.

Example scrape call (conceptually):

```bash
mcp call scrape '{"url": "https://www.flipkart.com/search?q=iphone"}'
```

SQLite output defaults to `flipkart.db`, table `scraped_items`.

