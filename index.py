"""
UltraSearch Backend — 8 Search Methods, No API Key Required
=============================================================
"""

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from bs4 import BeautifulSoup
import urllib.parse
import re
import xml.etree.ElementTree as ET
import os

app = FastAPI(title="UltraSearch", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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


async def google_scrape(query: str, limit: int):
    results = []
    try:
        url = f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={limit}&hl=en"
        google_headers = {**HEADERS, "Referer": "https://www.google.com/"}
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
            r = await c.get(url, headers=google_headers)
            soup = BeautifulSoup(r.text, "html.parser")
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
                items = root.findall(".//item")
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
                    link_text = link_el.text if link_el is not None else ""
                    combined = (title_text + " " + desc_text).lower()
                    if any(kw in combined for kw in keywords):
                        snip = BeautifulSoup(desc_text or "", "html.parser").get_text()[:300]
                        feed_results.append(make_result(title_text, link_text, snip, f"RSS:{name}", icon))
        except:
            pass
        return feed_results

    tasks = [fetch_feed(n, u, i) for n, u, i in RSS_FEEDS]
    all_results = await asyncio.gather(*tasks)
    for r in all_results:
        results.extend(r)
    return results[:limit]


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
            headings = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])[:5]]
            return {"title": title, "url": url, "snippet": text, "headings": headings, "source": "DirectScrape", "icon": "🕷️"}
    except Exception as e:
        return {"error": str(e)}


# ── FRONTEND HTML ─────────────────────────────────────────────────────────────
FRONTEND_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>UltraSearch</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f0f0f; color: #e0e0e0; min-height: 100vh; }
  .header { background: linear-gradient(135deg, #1a1a2e, #16213e); padding: 40px 20px 30px; text-align: center; border-bottom: 1px solid #2a2a4a; }
  .header h1 { font-size: 2.5rem; font-weight: 800; background: linear-gradient(90deg, #7c3aed, #2563eb, #06b6d4); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
  .header p { color: #888; margin-top: 6px; font-size: 0.9rem; }
  .search-box { display: flex; gap: 10px; max-width: 700px; margin: 24px auto 0; }
  .search-box input { flex: 1; padding: 14px 20px; border-radius: 12px; border: 2px solid #2a2a4a; background: #1a1a2e; color: #fff; font-size: 1rem; outline: none; transition: border 0.2s; }
  .search-box input:focus { border-color: #7c3aed; }
  .search-box button { padding: 14px 28px; border-radius: 12px; border: none; background: linear-gradient(135deg, #7c3aed, #2563eb); color: #fff; font-size: 1rem; font-weight: 600; cursor: pointer; transition: opacity 0.2s; }
  .search-box button:hover { opacity: 0.85; }
  .engines { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 14px; }
  .engine-btn { padding: 6px 14px; border-radius: 20px; border: 1px solid #2a2a4a; background: #1a1a2e; color: #aaa; font-size: 0.8rem; cursor: pointer; transition: all 0.2s; }
  .engine-btn.active { background: #7c3aed22; border-color: #7c3aed; color: #a78bfa; }
  .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
  .stats { color: #666; font-size: 0.85rem; margin-bottom: 20px; }
  .result { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 18px 20px; margin-bottom: 14px; transition: border 0.2s; }
  .result:hover { border-color: #7c3aed44; }
  .result-source { font-size: 0.75rem; color: #666; margin-bottom: 6px; }
  .result-title a { color: #60a5fa; font-size: 1.05rem; font-weight: 600; text-decoration: none; }
  .result-title a:hover { text-decoration: underline; }
  .result-url { font-size: 0.78rem; color: #4a7c59; margin: 4px 0 8px; }
  .result-snippet { color: #aaa; font-size: 0.88rem; line-height: 1.5; }
  .loading { text-align: center; padding: 60px; color: #666; }
  .spinner { width: 40px; height: 40px; border: 3px solid #2a2a4a; border-top-color: #7c3aed; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { text-align: center; padding: 60px; color: #555; }
</style>
</head>
<body>
<div class="header">
  <h1>🔍 UltraSearch</h1>
  <p>8 search engines · No API key needed</p>
  <div class="search-box">
    <input id="q" type="text" placeholder="Search anything..." onkeydown="if(event.key==='Enter')search()"/>
    <button onclick="search()">Search</button>
  </div>
  <div class="engines" id="engines">
    <span class="engine-btn active" data-e="ddg" onclick="toggleEngine(this)">🦆 DuckDuckGo</span>
    <span class="engine-btn active" data-e="bing" onclick="toggleEngine(this)">🔵 Bing</span>
    <span class="engine-btn active" data-e="yahoo" onclick="toggleEngine(this)">🟣 Yahoo</span>
    <span class="engine-btn active" data-e="google" onclick="toggleEngine(this)">🔴 Google</span>
    <span class="engine-btn active" data-e="wikipedia" onclick="toggleEngine(this)">📖 Wikipedia</span>
    <span class="engine-btn active" data-e="rss" onclick="toggleEngine(this)">📰 RSS</span>
  </div>
</div>
<div class="container" id="results"></div>

<script>
function toggleEngine(el) { el.classList.toggle('active'); }

async function search() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const active = [...document.querySelectorAll('.engine-btn.active')].map(e => e.dataset.e).join(',');
  const res = document.getElementById('results');
  res.innerHTML = '<div class="loading"><div class="spinner"></div>Searching across engines...</div>';
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&engines=${active}&limit=15`);
    const data = await r.json();
    if (!data.results || !data.results.length) {
      res.innerHTML = '<div class="empty">😕 No results found. Try different keywords.</div>';
      return;
    }
    const statsHtml = `<div class="stats">Found ${data.total} results from: ${Object.entries(data.engines_used).map(([k,v])=>`${k}(${v})`).join(', ')}</div>`;
    const items = data.results.map(r => `
      <div class="result">
        <div class="result-source">${r.icon} ${r.source}</div>
        <div class="result-title"><a href="${r.url}" target="_blank" rel="noopener">${r.title || 'No title'}</a></div>
        <div class="result-url">${r.display_url}</div>
        <div class="result-snippet">${r.snippet || ''}</div>
      </div>`).join('');
    res.innerHTML = statsHtml + items;
  } catch(e) {
    res.innerHTML = `<div class="empty">❌ Error: ${e.message}</div>`;
  }
}
</script>
</body>
</html>"""


# ── ROUTES ───────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def frontend():
    return FRONTEND_HTML


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

    if not all_results:
        all_results = await ddg_lite(q, limit)
        engine_stats["ddg_lite"] = len(all_results)

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
        "results": unique[:limit * 2],
    }


@app.get("/api/scrape")
async def scrape_url(url: str = Query(...)):
    return await direct_scrape(url)


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


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "2.0",
        "engines": ["DuckDuckGo", "Bing", "Yahoo", "Google", "Wikipedia", "RSS", "DirectScrape"],
        "api_keys_needed": False
    }
