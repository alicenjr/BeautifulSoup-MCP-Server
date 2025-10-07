from fastmcp import FastMCP
import asyncio
import sys
import sqlite3
from datetime import datetime
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse

app = FastMCP("test-scraper")

DB_PATH = "flipkart.db"

def _init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE,
                status_code INTEGER,
                title TEXT,
                meta_description TEXT,
                meta_keywords TEXT,
                fetched_at TEXT
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS page_text (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                content TEXT,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS headings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                level TEXT,
                text TEXT,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                href TEXT,
                text TEXT,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                src TEXT,
                alt TEXT,
                FOREIGN KEY(page_id) REFERENCES pages(id)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

def _save_page_data(url: str, status_code: int, title: str, meta_description: str, meta_keywords: str, text_content: str, headings: list, links: list, images: list) -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR REPLACE INTO pages (url, status_code, title, meta_description, meta_keywords, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (url, status_code, title, meta_description, meta_keywords, datetime.utcnow().isoformat()),
        )
        # Get page_id (for INSERT OR REPLACE, fetch id by url)
        cur.execute("SELECT id FROM pages WHERE url = ?", (url,))
        row = cur.fetchone()
        page_id = int(row[0]) if row else None

        # Clear existing related rows for idempotency
        if page_id is not None:
            cur.execute("DELETE FROM page_text WHERE page_id = ?", (page_id,))
            cur.execute("DELETE FROM headings WHERE page_id = ?", (page_id,))
            cur.execute("DELETE FROM links WHERE page_id = ?", (page_id,))
            cur.execute("DELETE FROM images WHERE page_id = ?", (page_id,))

        # Insert content
        cur.execute(
            "INSERT INTO page_text (page_id, content) VALUES (?, ?)",
            (page_id, text_content),
        )
        cur.executemany(
            "INSERT INTO headings (page_id, level, text) VALUES (?, ?, ?)",
            [(page_id, level, text) for level, text in headings],
        )
        cur.executemany(
            "INSERT INTO links (page_id, href, text) VALUES (?, ?, ?)",
            [(page_id, href, text) for href, text in links],
        )
        cur.executemany(
            "INSERT INTO images (page_id, src, alt) VALUES (?, ?, ?)",
            [(page_id, src, alt) for src, alt in images],
        )
        conn.commit()
        return page_id if page_id is not None else -1
    finally:
        conn.close()

def _build_paged_url(base_url: str, page_num: int) -> str:
    if "{page}" in base_url:
        return base_url.replace("{page}", str(page_num))
    parsed = urlparse(base_url)
    query = parse_qs(parsed.query)
    query["page"] = [str(page_num)]
    new_query = urlencode(query, doseq=True)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

@app.tool("health_check")
async def ping() -> dict:
    """Health check for the MCP server. Returns a success message if running."""
    return {"status": "success", "message": "MCP server is working"}

@app.tool("fetch_page_title")
async def quick_scrape(url: str) -> dict:
    """Fetch a single URL and return HTTP status and the page <title>."""
    try:
        import requests
        from bs4 import BeautifulSoup
        
        # Quick request with timeout
        response = requests.get(url, timeout=5)
        soup = BeautifulSoup(response.content, 'html.parser')
        title = soup.title.string if soup.title else "No title"
        
        return {
            "ok": True,
            "title": title,
            "url": url,
            "status_code": response.status_code
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def _parse_with_bs4(url: str, html: bytes, status_code: int) -> dict:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    meta_description_tag = soup.find("meta", attrs={"name": "description"})
    meta_keywords_tag = soup.find("meta", attrs={"name": "keywords"})
    meta_description = meta_description_tag.get("content", "").strip() if meta_description_tag else ""
    meta_keywords = meta_keywords_tag.get("content", "").strip() if meta_keywords_tag else ""

    # Text content (basic)
    for script in soup(["script", "style", "noscript"]):
        script.extract()
    text_content = " ".join(part.strip() for part in soup.get_text(separator=" ").split())

    # Headings
    headings = []
    for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        for tag in soup.find_all(level):
            content = tag.get_text(strip=True)
            if content:
                headings.append((level, content))

    # Links
    links = []
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = a.get_text(strip=True)
        if href or text:
            links.append((href, text))

    # Images
    images = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        alt = (img.get("alt") or "").strip()
        if src:
            images.append((src, alt))

    return {
        "url": url,
        "status_code": status_code,
        "title": title,
        "meta_description": meta_description,
        "meta_keywords": meta_keywords,
        "text_content": text_content,
        "headings": headings,
        "links": links,
        "images": images,
    }

def _scrape_page(url: str, timeout: int = 10) -> dict:
    import requests
    try:
        resp = requests.get(url, timeout=timeout)
        parsed = _parse_with_bs4(url, resp.content, resp.status_code)
        page_id = _save_page_data(
            url=parsed["url"],
            status_code=parsed["status_code"],
            title=parsed["title"],
            meta_description=parsed["meta_description"],
            meta_keywords=parsed["meta_keywords"],
            text_content=parsed["text_content"],
            headings=parsed["headings"],
            links=parsed["links"],
            images=parsed["images"],
        )
        return {"ok": True, "page_id": page_id, "title": parsed["title"], "status_code": parsed["status_code"], "url": url}
    except Exception as e:
        return {"ok": False, "error": str(e), "url": url}

def _scrape_multiple_pages(base_url: str, num_pages: int) -> dict:
    _init_db()
    results = []
    pages_scraped = 0
    errors = 0
    for i in range(1, max(1, int(num_pages)) + 1):
        page_url = _build_paged_url(base_url, i)
        res = _scrape_page(page_url)
        results.append(res)
        if res.get("ok"):
            pages_scraped += 1
        else:
            errors += 1
    return {"ok": errors == 0, "pages_scraped": pages_scraped, "errors": errors, "results": results}

@app.tool("scrape_pages_store_sqlite")
async def scrape_site(url: str, num_pages: int = 1) -> dict:
    """Scrape one or multiple pages with BeautifulSoup and store into SQLite.

    If the URL contains '{page}', it will be replaced by page numbers starting at 1.
    Otherwise a 'page' query parameter will be added or replaced.
    """
    try:
        _init_db()
        summary = await asyncio.to_thread(_scrape_multiple_pages, url, int(num_pages))
        return summary
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.tool("read_page_text")
async def read_page_text(page_id: int | None = None, contains: str | None = None, limit: int = 50, offset: int = 0) -> dict:
    """Read-only access to the `page_text` table.

    Parameters:
    - page_id: filter by specific page id (optional)
    - contains: return rows where text content LIKE %contains% (optional)
    - limit: max rows (default 50, max 500)
    - offset: pagination offset
    """
    try:
        _init_db()
        if limit is None:
            limit = 50
        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset or 0))

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            query = "SELECT id, page_id, content FROM page_text"
            clauses = []
            params = []
            if page_id is not None:
                clauses.append("page_id = ?")
                params.append(int(page_id))
            if contains:
                clauses.append("content LIKE ?")
                params.append(f"%{contains}%")
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY id DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cur.execute(query, params)
            rows = cur.fetchall()
            data = [dict(row) for row in rows]
            return {"ok": True, "rows": data, "count": len(data)}
        finally:
            conn.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    try:
        # Non-interactive server mode to avoid blocking Claude MCP
        if "--server" in sys.argv:
            app.run()
            sys.exit(0)

        print("BeautifulSoup Scraper (no Playwright)")
        base_url = input("Enter base URL (use {page} placeholder or leave as-is): ").strip()
        if base_url:
            while True:
                pages_in = input("How many pages to scrape? [default 1]: ").strip()
                if not pages_in:
                    num_pages = 1
                    break
                try:
                    num_pages = max(1, int(pages_in))
                    break
                except ValueError:
                    print("Please enter a valid integer.")
            print(f"Scraping {num_pages} page(s) starting from: {base_url}")
            result = _scrape_multiple_pages(base_url, num_pages)
            print({k: v for k, v in result.items() if k != "results"})
        start_server = input("Start MCP server after scraping? [y/N]: ").strip().lower()
        if start_server == "y":
            app.run()
    except KeyboardInterrupt:
        pass