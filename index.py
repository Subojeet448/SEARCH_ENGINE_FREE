"""
UltraSearch Backend — 8 Search Methods, No API Key Required
=============================================================
1. DuckDuckGo HTML scrape
2. DuckDuckGo Lite scrape
3. Bing HTML scrape
4. Yahoo HTML scrape
5. Google HTML scrape (with headers)
6. Wikipedia API (free)
7. RSS Feed reading
8. Direct URL scraping
"""

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx
import asyncio
from bs4 import BeautifulSoup
import urllib.parse
import re
import xml.etree.ElementTree as ET
import json
import os

app = FastAPI(title="UltraSearch", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Headers to mimic a real browser ──────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
}

TIMEOUT = 12


def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', text or "").strip()


def make_result(title, url, snippet, source, icon):
    return {
        "title": clean(title)[:200],
        "url": url,
        "snippet": clean(snippet)[:400],
        "source": source,
        "icon": icon,
        "display_url": url[:80] if url else ""
    }


# ── 1. DuckDuckGo HTML ───────────────────────────────────────────────────────
async def ddg_html(query: str, limit: int):
    results = []
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}&kl=us-en"
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            for item in soup.select(".result__body")[:limit]:
                a = item.select_one(".result__title a")
                snip = item.select_one(".result__snippet")
                if not a:
                    continue
                href = a.get("href", "")
                if "uddg=" in href:
                    href = urllib.parse.unquote(
                        urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [href])[0]
                    )
                results.append(make_result(
                    a.get_text(), href,
                    snip.get_text() if snip else "",
                    "DuckDuckGo", "🦆"
                ))
    except Exception as e:
        print(f"DDG HTML error: {e}")
    return results


# ── 2. DuckDuckGo Lite ───────────────────────────────────────────────────────
async def ddg_lite(query: str, limit: int):
    results = []
    try:
        url = f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}"
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            links = soup.find_all("a", class_="result-link")
            snippets = soup.find_all("td", class_="result-snippet")
            for i, a in enumerate(links[:limit]):
                href = a.get("href", "")
                if href.startswith("//"):
                    href = "https:" + href
                snip = snippets[i].get_text() if i < len(snippets) else ""
                results.append(make_result(a.get_text(), href, snip, "DDG Lite", "🦆"))
    except Exception as e:
        print(f"DDG Lite error: {e}")
    return results


# ── 3. Bing HTML Scrape ──────────────────────────────────────────────────────
async def bing_scrape(query: str, limit: int):
    results = []
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={limit}"
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            for item in soup.select(".b_algo")[:limit]:
                a = item.select_one("h2 a")
                snip = item.select_one(".b_caption p") or item.select_one(".b_algoSlug")
                if not a:
                    continue
                results.append(make_result(
                    a.get_text(), a.get("href", ""),
                    snip.get_text() if snip else "",
                    "Bing", "🔵"
                ))
    except Exception as e:
        print(f"Bing error: {e}")
    return results


# ── 4. Yahoo HTML Scrape ─────────────────────────────────────────────────────
async def yahoo_scrape(query: str, limit: int):
    results = []
    try:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(query)}&n={limit}"
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            for item in soup.select(".algo-sr, .dd.algo")[:limit]:
                a = item.select_one("h3 a") or item.select_one("h2 a")
                snip = item.select_one(".compText p") or item.select_one("p")
                if not a:
                    continue
                href = a.get("href", "")
                # Unwrap Yahoo redirect
                if "yahoo.com/url" in href:
                    try:
                        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                        href = parsed.get("url", [href])[0]
                    except:
                        pass
                results.append(make_result(
                    a.get_text(), href,
                    snip.get_text() if snip else "",
                    "Yahoo", "🟣"
                ))
    except Exception as e:
        print(f"Yahoo error: {e}")
    return results


# ── 5. Google HTML Scrape ────────────────────────────────────────────────────
async def google_scrape(query: str, limit: int):
    results = []
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={limit}&hl=en"
        google_headers = {**HEADERS, "Referer": "https://www.google.com/"}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=google_headers)
            soup = BeautifulSoup(r.text, "html.parser")
            # Try multiple selectors (Google changes layout often)
            items = soup.select("div.g") or soup.select("[data-sokoban-container]") or soup.select(".tF2Cxc")
            for item in items[:limit]:
                a = item.select_one("a[href^='http']") or item.select_one("a[href^='/url']")
                h3 = item.select_one("h3")
                snip_el = item.select_one(".VwiC3b") or item.select_one(".st") or item.select_one("span.aCOpRe")
                if not a or not h3:
                    continue
                href = a.get("href", "")
                if href.startswith("/url?"):
                    href = urllib.parse.unquote(
                        urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("q", [href])[0]
                    )
                if not href.startswith("http"):
                    continue
                results.append(make_result(
                    h3.get_text(), href,
                    snip_el.get_text() if snip_el else "",
                    "Google", "🔴"
                ))
    except Exception as e:
        print(f"Google error: {e}")
    return results


# ── 6. Wikipedia Search API (completely free, official) ──────────────────────
async def wikipedia_search(query: str, limit: int):
    results = []
    try:
        url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&srlimit={min(limit,5)}&format=json&srprop=snippet|titlesnippet"
        )
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, headers={"User-Agent": "UltraSearch/2.0"})
            data = r.json()
            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                snip = BeautifulSoup(item.get("snippet", ""), "html.parser").get_text()
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append(make_result(f"📖 {title}", page_url, snip, "Wikipedia", "📖"))
    except Exception as e:
        print(f"Wikipedia error: {e}")
    return results


# ── 7. RSS Feed Search ───────────────────────────────────────────────────────
RSS_FEEDS = [
    ("BBC News", "http://feeds.bbci.co.uk/news/rss.xml", "📰"),
    ("Reuters", "https://feeds.reuters.com/reuters/topNews", "📰"),
    ("TechCrunch", "https://techcrunch.com/feed/", "💻"),
    ("Hacker News", "https://news.ycombinator.com/rss", "🤖"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "🔬"),
    ("Ars Technica", "http://feeds.arstechnica.com/arstechnica/index", "🧪"),
]

async def rss_search(query: str, limit: int):
    results = []
    keywords = query.lower().split()

    async def fetch_feed(name, feed_url, icon):
        feed_results = []
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r = await c.get(feed_url, headers={"User-Agent": "UltraSearch/2.0"})
                root = ET.fromstring(r.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}

                # RSS format
                items = root.findall(".//item")
                # Atom format fallback
                if not items:
                    items = root.findall(".//atom:entry", ns)

                for item in items:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description") or item.find("summary")
                    if title_el is None:
                        continue

                    title_text = title_el.text or ""
                    desc_text = desc_el.text if desc_el is not None else ""
                    link_text = link_el.text if link_el is not None else (link_el.get("href","") if link_el is not None else "")

                    combined = (title_text + " " + desc_text).lower()
                    if any(kw in combined for kw in keywords):
                        snip = BeautifulSoup(desc_text or "", "html.parser").get_text()[:300]
                        feed_results.append(make_result(
                            title_text, link_text, snip,
                            f"RSS:{name}", icon
                        ))
        except:
            pass
        return feed_results

    tasks = [fetch_feed(n, u, i) for n, u, i in RSS_FEEDS]
    all_results = await asyncio.gather(*tasks)
    for r in all_results:
        results.extend(r)
    return results[:limit]


# ── 8. Direct Website Scrape ─────────────────────────────────────────────────
async def direct_scrape(url: str):
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url, headers=HEADERS)
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            title = soup.title.string.strip() if soup.title else url
            meta = soup.find("meta", attrs={"name": "description"})
            meta_desc = meta.get("content", "") if meta else ""
            paras = " ".join(p.get_text() for p in soup.find_all("p")[:8])
            text = clean(meta_desc or paras)[:500]
            headings = [h.get_text(strip=True) for h in soup.find_all(["h1","h2","h3"])[:5]]
            return {
                "title": title,
                "url": url,
                "snippet": text,
                "headings": headings,
                "source": "DirectScrape",
                "icon": "🕷️"
            }
    except Exception as e:
        return {"error": str(e)}


# ── MAIN SEARCH API ──────────────────────────────────────────────────────────
@app.get("/api/search")
async def search(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=30),
    engines: str = Query("all", description="Comma-separated engines or 'all'"),
):
    if not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)

    active = engines.lower().split(",") if engines != "all" else [
        "ddg", "bing", "yahoo", "google", "wikipedia", "rss"
    ]

    tasks = {}
    if "ddg" in active or "duckduckgo" in active:
        tasks["ddg"] = ddg_html(q, limit)
    if "bing" in active:
        tasks["bing"] = bing_scrape(q, limit)
    if "yahoo" in active:
        tasks["yahoo"] = yahoo_scrape(q, limit)
    if "google" in active:
        tasks["google"] = google_scrape(q, limit)
    if "wikipedia" in active or "wiki" in active:
        tasks["wikipedia"] = wikipedia_search(q, limit)
    if "rss" in active:
        tasks["rss"] = rss_search(q, limit)

    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    all_results = []
    engine_stats = {}

    for key, result in zip(tasks.keys(), gathered):
        if isinstance(result, list):
            engine_stats[key] = len(result)
            all_results.extend(result)
        else:
            engine_stats[key] = 0

    # If all engines returned nothing, try DDG Lite as last resort
    if not all_results:
        all_results = await ddg_lite(q, limit)
        engine_stats["ddg_lite"] = len(all_results)

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for r in all_results:
        url = r.get("url", "").rstrip("/")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique.append(r)

    return {
        "query": q,
        "total": len(unique),
        "engines_used": engine_stats,
        "results": unique[:limit * 2],  # return up to 2x for variety
    }


# ── DIRECT SCRAPE API ────────────────────────────────────────────────────────
@app.get("/api/scrape")
async def scrape_url(url: str = Query(...)):
    return await direct_scrape(url)


# ── WIKIPEDIA SUMMARY ────────────────────────────────────────────────────────
@app.get("/api/wiki")
async def wiki_summary(q: str = Query(...)):
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, headers={"User-Agent": "UltraSearch/2.0"})
            data = r.json()
            return {
                "title": data.get("title"),
                "summary": data.get("extract"),
                "url": data.get("content_urls", {}).get("desktop", {}).get("page"),
                "thumbnail": data.get("thumbnail", {}).get("source"),
            }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── HEALTH ───────────────────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0",
        "engines": ["DuckDuckGo", "Bing", "Yahoo", "Google", "Wikipedia", "RSS", "DirectScrape"],
        "api_keys_needed": False
    }


# ── SERVE FRONTEND ───────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def frontend():
    path = os.path.join(os.path.dirname(__file__), "..", "static", "index.html")
    with open(path) as f:
        return f.read()
