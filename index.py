"""
UltraSearch Backend — Fixed for Vercel
Uses SearXNG public instances (free, no API key) + Wikipedia + RSS
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
import random

app = FastAPI(title="UltraSearch", version="3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 15

# ── SearXNG Public Instances (free, open, no key needed) ─────────────────────
SEARXNG_INSTANCES = [
    "https://searx.be",
    "https://search.bus-hit.me",
    "https://searxng.site",
    "https://search.hbubli.cc",
    "https://searx.tiekoetter.com",
    "https://search.smnz.de",
    "https://searx.fmac.xyz",
    "https://search.datura.network",
]


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


# ── SearXNG Search (tries multiple instances) ─────────────────────────────────
async def searxng_search(query: str, limit: int, engines: str = "google,bing,duckduckgo"):
    results = []
    instances = random.sample(SEARXNG_INSTANCES, min(3, len(SEARXNG_INSTANCES)))

    for instance in instances:
        try:
            url = f"{instance}/search"
            params = {
                "q": query,
                "format": "json",
                "engines": engines,
                "language": "en",
                "time_range": "",
                "safesearch": "0",
                "pageno": "1",
            }
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as c:
                r = await c.get(url, params=params, headers=HEADERS)
                if r.status_code != 200:
                    continue
                data = r.json()
                for item in data.get("results", [])[:limit]:
                    source_engines = item.get("engines", ["searxng"])
                    icon = "🔍"
                    if "google" in str(source_engines): icon = "🔴"
                    elif "bing" in str(source_engines): icon = "🔵"
                    elif "duckduckgo" in str(source_engines): icon = "🦆"
                    elif "yahoo" in str(source_engines): icon = "🟣"

                    results.append(make_result(
                        item.get("title", ""),
                        item.get("url", ""),
                        item.get("content", ""),
                        f"SearXNG ({', '.join(source_engines[:2])})",
                        icon
                    ))
                if results:
                    break  # Got results, stop trying instances
        except Exception as e:
            print(f"SearXNG {instance} error: {e}")
            continue

    return results


# ── Wikipedia Search ──────────────────────────────────────────────────────────
async def wikipedia_search(query: str, limit: int):
    results = []
    try:
        url = (
            f"https://en.wikipedia.org/w/api.php"
            f"?action=query&list=search&srsearch={urllib.parse.quote(query)}"
            f"&srlimit={min(limit, 5)}&format=json&srprop=snippet"
        )
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(url, headers={"User-Agent": "UltraSearch/3.0"})
            data = r.json()
            for item in data.get("query", {}).get("search", []):
                title = item.get("title", "")
                snip = BeautifulSoup(item.get("snippet", ""), "html.parser").get_text()
                page_url = f"https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}"
                results.append(make_result(f"📖 {title}", page_url, snip, "Wikipedia", "📖"))
    except Exception as e:
        print(f"Wikipedia error: {e}")
    return results


# ── RSS Feed Search ───────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("BBC News", "https://feeds.bbci.co.uk/news/rss.xml", "📰"),
    ("TechCrunch", "https://techcrunch.com/feed/", "💻"),
    ("Hacker News", "https://news.ycombinator.com/rss", "🤖"),
    ("The Verge", "https://www.theverge.com/rss/index.xml", "🔬"),
    ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", "🧪"),
]


async def rss_search(query: str, limit: int):
    results = []
    keywords = query.lower().split()

    async def fetch_feed(name, feed_url, icon):
        feed_results = []
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=True) as c:
                r = await c.get(feed_url, headers={"User-Agent": "UltraSearch/3.0"})
                root = ET.fromstring(r.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                items = root.findall(".//item") or root.findall(".//atom:entry", ns)
                for item in items:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description") or item.find("summary")
                    if title_el is None:
                        continue
                    title_text = title_el.text or ""
                    desc_text = desc_el.text if desc_el is not None else ""
                    link_text = link_el.text if link_el is not None else ""
                    if not link_text and link_el is not None:
                        link_text = link_el.get("href", "")
                    combined = (title_text + " " + desc_text).lower()
                    if any(kw in combined for kw in keywords):
                        snip = BeautifulSoup(desc_text or "", "html.parser").get_text()[:300]
                        feed_results.append(make_result(title_text, link_text, snip, f"RSS:{name}", icon))
        except Exception as e:
            print(f"RSS {name} error: {e}")
        return feed_results

    tasks = [fetch_feed(n, u, i) for n, u, i in RSS_FEEDS]
    all_results = await asyncio.gather(*tasks)
    for r in all_results:
        results.extend(r)
    return results[:limit]


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
  .toggle-row { display: flex; gap: 8px; flex-wrap: wrap; justify-content: center; margin-top: 14px; }
  .toggle-btn { padding: 6px 14px; border-radius: 20px; border: 1px solid #2a2a4a; background: #1a1a2e; color: #aaa; font-size: 0.8rem; cursor: pointer; transition: all 0.2s; user-select: none; }
  .toggle-btn.active { background: #7c3aed22; border-color: #7c3aed; color: #a78bfa; }
  .container { max-width: 800px; margin: 30px auto; padding: 0 20px; }
  .stats { color: #666; font-size: 0.85rem; margin-bottom: 20px; padding: 10px 14px; background: #1a1a1a; border-radius: 8px; border: 1px solid #2a2a2a; }
  .result { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px; padding: 18px 20px; margin-bottom: 14px; transition: border 0.2s; }
  .result:hover { border-color: #7c3aed55; }
  .result-source { font-size: 0.75rem; color: #666; margin-bottom: 6px; }
  .result-title a { color: #60a5fa; font-size: 1.05rem; font-weight: 600; text-decoration: none; }
  .result-title a:hover { text-decoration: underline; }
  .result-url { font-size: 0.78rem; color: #4a7c59; margin: 4px 0 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .result-snippet { color: #aaa; font-size: 0.88rem; line-height: 1.55; }
  .loading { text-align: center; padding: 60px; color: #666; }
  .spinner { width: 40px; height: 40px; border: 3px solid #2a2a4a; border-top-color: #7c3aed; border-radius: 50%; animation: spin 0.8s linear infinite; margin: 0 auto 16px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .empty { text-align: center; padding: 60px; color: #555; font-size: 1.1rem; }
  .error { text-align: center; padding: 40px; color: #f87171; }
</style>
</head>
<body>
<div class="header">
  <h1>🔍 UltraSearch</h1>
  <p>Multi-engine search · No API key needed · Powered by SearXNG + Wikipedia + RSS</p>
  <div class="search-box">
    <input id="q" type="text" placeholder="Search anything..." onkeydown="if(event.key==='Enter')doSearch()"/>
    <button onclick="doSearch()">Search</button>
  </div>
  <div class="toggle-row">
    <span class="toggle-btn active" data-e="searxng">🔍 Web (Google/Bing/DDG)</span>
    <span class="toggle-btn active" data-e="wikipedia">📖 Wikipedia</span>
    <span class="toggle-btn active" data-e="rss">📰 RSS News</span>
  </div>
</div>
<div class="container" id="results"></div>

<script>
document.querySelectorAll('.toggle-btn').forEach(btn => {
  btn.addEventListener('click', () => btn.classList.toggle('active'));
});

async function doSearch() {
  const q = document.getElementById('q').value.trim();
  if (!q) return;
  const active = [...document.querySelectorAll('.toggle-btn.active')].map(e => e.dataset.e).join(',');
  if (!active) { alert('At least one engine select karo!'); return; }
  const res = document.getElementById('results');
  res.innerHTML = '<div class="loading"><div class="spinner"></div>Searching...</div>';
  try {
    const r = await fetch('/api/search?q=' + encodeURIComponent(q) + '&engines=' + active + '&limit=15');
    const data = await r.json();
    if (data.error) { res.innerHTML = '<div class="error">❌ ' + data.error + '</div>'; return; }
    if (!data.results || !data.results.length) {
      res.innerHTML = '<div class="empty">😕 No results found. Try different keywords or enable more engines.</div>';
      return;
    }
    const engineInfo = Object.entries(data.engines_used).map(([k,v]) => `${k}: ${v}`).join(' · ');
    const statsHtml = '<div class="stats">✅ ' + data.total + ' results &nbsp;|&nbsp; ' + engineInfo + '</div>';
    const items = data.results.map(r => `
      <div class="result">
        <div class="result-source">${r.icon} ${r.source}</div>
        <div class="result-title"><a href="${r.url}" target="_blank" rel="noopener noreferrer">${r.title || 'No title'}</a></div>
        <div class="result-url">${r.display_url}</div>
        <div class="result-snippet">${r.snippet || '<em style="color:#555">No description available</em>'}</div>
      </div>`).join('');
    res.innerHTML = statsHtml + items;
  } catch(e) {
    res.innerHTML = '<div class="error">❌ Network error: ' + e.message + '</div>';
  }
}
</script>
</body>
</html>"""


# ── ROUTES ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def frontend():
    return FRONTEND_HTML


@app.get("/api/search")
async def search(
    q: str = Query(...),
    limit: int = Query(15, ge=1, le=30),
    engines: str = Query("searxng,wikipedia,rss"),
):
    if not q.strip():
        return JSONResponse({"error": "Query required"}, status_code=400)

    active = [e.strip() for e in engines.lower().split(",")]
    tasks = {}

    if "searxng" in active or "all" in active:
        tasks["searxng"] = searxng_search(q, limit)
    if "wikipedia" in active or "wiki" in active or "all" in active:
        tasks["wikipedia"] = wikipedia_search(q, limit)
    if "rss" in active or "all" in active:
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
            print(f"Engine {key} exception: {result}")

    # Deduplicate
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


@app.get("/api/wiki")
async def wiki_summary(q: str = Query(...)):
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(q)}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url, headers={"User-Agent": "UltraSearch/3.0"})
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
        "version": "3.0",
        "engines": ["SearXNG (Google+Bing+DDG)", "Wikipedia", "RSS"],
        "api_keys_needed": False,
        "note": "Uses SearXNG public instances for web search"
    }
