import os
import requests
from bs4 import BeautifulSoup

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8,de;q=0.7,fr;q=0.6",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

HEADERS_GOOGLEBOT = {
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

HEADERS = HEADERS_BROWSER

MIN_WORDS = 100


def _parse_soup(soup):
    for tag in soup(["script", "style", "noscript", "svg", "path", "link", "meta"]):
        tag.decompose()

    for el in soup.find_all(attrs={"class": lambda c: c and any(
        kw in " ".join(c).lower() if isinstance(c, list) else kw in c.lower()
        for kw in ["cookie", "consent", "gdpr", "cc-banner", "onetrust", "cookiebot"]
    )}):
        el.decompose()

    for el in soup.find_all(attrs={"id": lambda i: i and any(
        kw in i.lower()
        for kw in ["cookie", "consent", "gdpr", "onetrust", "cookiebot"]
    )}):
        el.decompose()

    meta_title = ""
    title_tag = soup.find("title")
    if title_tag:
        meta_title = title_tag.get_text(strip=True)

    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": "description"})
    if desc_tag:
        meta_desc = desc_tag.get("content", "")

    headings = []
    for h in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        t = h.get_text(strip=True)
        if t:
            headings.append(t)

    body = soup.get_text(separator=" ", strip=True)
    combined = " ".join([meta_title, meta_desc, " ".join(headings), body])

    return {
        "meta_title": meta_title,
        "meta_description": meta_desc,
        "headings": " ".join(headings),
        "body": body,
        "combined": combined,
        "word_count": len(body.split()),
    }


def _scrape_firecrawl(url):
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY not set")

    from firecrawl import FirecrawlApp
    app = FirecrawlApp(api_key=api_key)

    doc = app.scrape(url, formats=["html", "markdown"], wait_for=5000)

    final_url = ""
    if doc.metadata:
        final_url = doc.metadata.url or ""

    redirect_warning = ""
    if final_url and final_url.rstrip("/") != url.rstrip("/"):
        from urllib.parse import urlparse
        orig_domain = urlparse(url).netloc
        final_domain = urlparse(final_url).netloc
        if orig_domain != final_domain:
            redirect_warning = f"Redirected from {url} to {final_url}"

    html_content = doc.html or ""
    markdown_content = doc.markdown or ""

    meta_title = ""
    meta_desc = ""
    if doc.metadata:
        meta_title = doc.metadata.title or ""
        meta_desc = doc.metadata.description or ""

    parsed = None
    if html_content:
        soup = BeautifulSoup(html_content, "html.parser")
        parsed = _parse_soup(soup)
        if meta_title:
            parsed["meta_title"] = meta_title
        if meta_desc:
            parsed["meta_description"] = meta_desc
        parsed["combined"] = " ".join([
            parsed["meta_title"],
            parsed["meta_description"],
            parsed["headings"],
            parsed["body"],
        ])
    elif markdown_content:
        body = markdown_content
        combined = " ".join([meta_title, meta_desc, body])
        parsed = {
            "meta_title": meta_title,
            "meta_description": meta_desc,
            "headings": "",
            "body": body,
            "combined": combined,
            "word_count": len(body.split()),
        }

    if not parsed:
        raise RuntimeError("Firecrawl returned no content")

    if redirect_warning and parsed["word_count"] < MIN_WORDS:
        raise RuntimeError(
            f"{redirect_warning} — only {parsed['word_count']} words found. "
            "The site may have moved. Try uploading the HTML file or pasting text instead."
        )

    if redirect_warning:
        parsed["redirect_warning"] = redirect_warning

    return parsed


def _scrape_static(url):
    session = requests.Session()
    session.headers.update(HEADERS_BROWSER)
    resp = session.get(url, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_soup(soup)


def _scrape_googlebot(url):
    session = requests.Session()
    session.headers.update(HEADERS_GOOGLEBOT)
    resp = session.get(url, timeout=20, allow_redirects=True)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _parse_soup(soup)


def _scrape_playwright(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=HEADERS["User-Agent"],
            locale="en-US",
            extra_http_headers={
                "Accept-Language": HEADERS["Accept-Language"],
            },
        )
        page = ctx.new_page()
        page.goto(url, timeout=30000, wait_until="networkidle")
        content = page.content()
        browser.close()
    soup = BeautifulSoup(content, "html.parser")
    return _parse_soup(soup)


def parse_html_bytes(html_bytes, url="manual"):
    empty = {
        "meta_title": "", "meta_description": "",
        "headings": "", "body": "", "combined": "", "word_count": 0,
    }
    try:
        soup = BeautifulSoup(html_bytes, "html.parser")
        result = _parse_soup(soup)
        return {**result, "url": url, "error": None}
    except Exception as e:
        return {**empty, "url": url, "error": str(e)}


def firecrawl_available():
    return bool(os.environ.get("FIRECRAWL_API_KEY", ""))


def _best_result(results):
    if not results:
        return None
    return max(results, key=lambda r: r.get("word_count", 0))


def scrape_url(url, use_firecrawl=True):
    empty = {
        "meta_title": "",
        "meta_description": "",
        "headings": "",
        "body": "",
        "combined": "",
        "word_count": 0,
    }

    attempts = []
    errors = []

    if use_firecrawl and firecrawl_available():
        try:
            result = _scrape_firecrawl(url)
            result = {**result, "url": url, "error": None, "method": "firecrawl"}
            if result["word_count"] >= MIN_WORDS:
                return result
            attempts.append(result)
        except Exception as e:
            errors.append(f"Firecrawl: {e}")

    try:
        result = _scrape_googlebot(url)
        result = {**result, "url": url, "error": None, "method": "googlebot"}
        if result["word_count"] >= MIN_WORDS:
            return result
        attempts.append(result)
    except Exception as e:
        errors.append(f"Googlebot: {e}")

    try:
        result = _scrape_static(url)
        result = {**result, "url": url, "error": None, "method": "static"}
        if result["word_count"] >= MIN_WORDS:
            return result
        attempts.append(result)
    except Exception as e:
        errors.append(f"Static: {e}")

    try:
        result = _scrape_playwright(url)
        result = {**result, "url": url, "error": None, "method": "playwright"}
        if result["word_count"] >= MIN_WORDS:
            return result
        attempts.append(result)
    except Exception as e:
        errors.append(f"Playwright: {e}")

    best = _best_result(attempts)
    if best:
        return best

    return {**empty, "url": url, "error": f"All methods failed — {' | '.join(errors)}", "method": "none"}
