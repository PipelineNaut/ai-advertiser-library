"""Mirror https://ai-advertiser-course.vercel.app/ 1:1 into ./site.

BFS crawl from the homepage, same-origin only. Preserves URL paths exactly
("/" -> index.html). Discovers links in HTML (href/src/srcset/poster,
meta og:image) and CSS (url(...), @import).
"""
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://ai-advertiser-course.vercel.app"
HOST = urllib.parse.urlparse(BASE).netloc
OUT = Path(__file__).parent / "site"

HTML_ATTR_RE = re.compile(r'(?:href|src|poster|content)\s*=\s*["\']([^"\']+)["\']', re.I)
SRCSET_RE = re.compile(r'srcset\s*=\s*["\']([^"\']+)["\']', re.I)
CSS_URL_RE = re.compile(r'url\(\s*["\']?([^"\')]+)["\']?\s*\)|@import\s+["\']([^"\']+)["\']', re.I)

seen = set()
queue = [BASE + "/"]
failed = []


def local_path(url: str) -> Path:
    p = urllib.parse.urlparse(url).path
    if p.endswith("/") or p == "":
        p += "index.html"
    return OUT / p.lstrip("/")


def enqueue(raw: str, page_url: str):
    raw = raw.strip()
    if not raw or raw.startswith(("#", "data:", "mailto:", "tel:", "javascript:")):
        return
    if any(c.isspace() for c in raw):  # non-URL attr values (e.g. content="COPIED ✓")
        return
    absu = urllib.parse.urljoin(page_url, raw)
    parts = urllib.parse.urlparse(absu)
    if parts.netloc != HOST or parts.scheme not in ("http", "https"):
        return
    clean = parts._replace(query="", fragment="").geturl()
    if clean not in seen:
        seen.add(clean)
        queue.append(clean)


while queue:
    url = queue.pop(0)
    seen.add(url)
    dest = local_path(url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (mirror)"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            ctype = r.headers.get("Content-Type", "")
    except Exception as e:
        failed.append((url, str(e)))
        print(f"FAIL {url}: {e}")
        continue

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    print(f"OK   {url} -> {dest.relative_to(OUT)} ({len(body)} bytes)")

    if "text/html" in ctype or dest.suffix in (".html", ".htm"):
        text = body.decode("utf-8", errors="replace")
        for m in HTML_ATTR_RE.finditer(text):
            enqueue(m.group(1), url)
        for m in SRCSET_RE.finditer(text):
            for cand in m.group(1).split(","):
                enqueue(cand.strip().split()[0] if cand.strip() else "", url)
    elif "css" in ctype or dest.suffix == ".css":
        text = body.decode("utf-8", errors="replace")
        for m in CSS_URL_RE.finditer(text):
            enqueue(m.group(1) or m.group(2) or "", url)
    time.sleep(0.05)

print(f"\nDone: {len(seen) - len(failed)} files saved, {len(failed)} failed")
if failed:
    for u, e in failed:
        print(f"  FAILED: {u} ({e})")
    sys.exit(1)
