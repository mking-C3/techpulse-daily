#!/usr/bin/env python3
"""
fetch_and_build.py
==================
1. Loads config.yaml
2. Fetches configured RSS feeds, skipping already-seen URLs
3. Persists new articles to articles.json and seen URLs to seen_urls.json
4. Generates a complete static HTML website under output/
   - Paginated homepage (all categories)
   - Paginated per-category pages
   - sitemap.xml + robots.txt

Run locally:
    python fetch_and_build.py

Safe to run repeatedly — fully idempotent.
"""

import html as _html
import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import yaml
from jinja2 import Environment, BaseLoader
from markupsafe import Markup

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT        = Path(__file__).parent
OUTPUT      = ROOT / "output"
SEEN_FILE   = ROOT / "seen_urls.json"
STORE_FILE  = ROOT / "articles.json"
CONFIG_FILE = ROOT / "config.yaml"

FETCH_TIMEOUT = 20   # seconds per feed


# ===========================================================================
# I/O helpers
# ===========================================================================

def load_config() -> dict:
    with open(CONFIG_FILE, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_seen() -> set:
    if SEEN_FILE.exists():
        raw = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
        return set(raw) if isinstance(raw, list) else set()
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(
        json.dumps(sorted(seen), indent=2), encoding="utf-8"
    )


def _json_serial(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not JSON-serializable: {type(obj)}")


def load_store() -> list:
    """Load persisted articles, rehydrating ISO-string dates."""
    if not STORE_FILE.exists():
        return []
    rows = json.loads(STORE_FILE.read_text(encoding="utf-8"))
    for row in rows:
        if isinstance(row.get("date"), str):
            try:
                row["date"] = datetime.fromisoformat(row["date"])
            except ValueError:
                row["date"] = datetime.now(timezone.utc)
    return rows


def save_store(articles: list) -> None:
    STORE_FILE.write_text(
        json.dumps(articles, default=_json_serial, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ===========================================================================
# Text utilities
# ===========================================================================

def strip_html(text: str) -> str:
    """Remove all HTML tags, decode entities, collapse whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = _html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def truncate_words(text: str, n: int) -> str:
    words = text.split()
    return text if len(words) <= n else " ".join(words[:n]) + "\u2026"


def parse_date(entry) -> datetime:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(timezone.utc)


def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or "misc"


# ===========================================================================
# Feed fetching
# ===========================================================================

def fetch_new_articles(config: dict, seen: set) -> tuple:
    """
    Fetch all configured RSS feeds.
    Returns (new_articles_list, new_urls_set).
    Only articles whose URLs are not in `seen` are returned.
    """
    feeds_cfg  = config.get("feeds", [])
    max_per    = config["settings"]["max_posts_per_feed"]
    word_limit = config["settings"]["summary_word_limit"]

    new_articles: list = []
    new_seen:     set  = set()

    for feed_cfg in feeds_cfg:
        category = feed_cfg["category"]
        url      = feed_cfg["url"]
        print(f"  Fetching: {url}")

        old_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(FETCH_TIMEOUT)
            feed = feedparser.parse(url)
        except Exception as exc:
            print(f"    WARN: could not fetch feed: {exc}")
            continue
        finally:
            socket.setdefaulttimeout(old_timeout)

        if feed.bozo and not feed.entries:
            print(f"    WARN: empty or malformed feed, skipping.")
            continue

        source = (feed.feed.get("title") or url).strip()
        count  = 0

        for entry in feed.entries:
            if count >= max_per:
                break

            link = (entry.get("link") or "").strip()
            if not link or link in seen or link in new_seen:
                continue

            title = strip_html(entry.get("title") or "Untitled")

            raw_body = (
                entry.get("summary")
                or entry.get("description")
                or (entry.content[0].value if getattr(entry, "content", None) else "")
                or ""
            )
            summary  = truncate_words(strip_html(raw_body), word_limit)
            pub_date = parse_date(entry)
            cat_slug = slugify(category)

            new_articles.append({
                "title":         title,
                "url":           link,
                "summary":       summary,
                "source":        source,
                "category":      category,
                "category_slug": cat_slug,
                "date":          pub_date,
                "date_str":      pub_date.strftime("%b %d, %Y"),
            })
            new_seen.add(link)
            count += 1

    return new_articles, new_seen


# ===========================================================================
# CSS (inlined into every page — one HTTP request, instant paint)
# ===========================================================================

CSS = """\
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}

:root{
  --brand:#1a1a2e;
  --accent:#0369a1;
  --bg:#f0f4f8;
  --card:#ffffff;
  --text:#1e293b;
  --muted:#64748b;
  --border:#e2e8f0;
  --radius:10px;
}

body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6;font-size:16px;
}

a{color:inherit;text-decoration:none}
a:hover{text-decoration:underline}

/* ── Nav ── */
nav{
  background:var(--brand);position:sticky;top:0;z-index:100;
  box-shadow:0 2px 8px rgba(0,0,0,.3);
}
.nav-inner{
  max-width:1200px;margin:0 auto;padding:0 1rem;
  display:flex;align-items:center;flex-wrap:wrap;
  gap:.35rem 1.4rem;min-height:54px;
}
.nav-brand{font-size:1.1rem;font-weight:700;color:#e2e8f0;white-space:nowrap}
.nav-links{display:flex;flex-wrap:wrap;gap:.2rem .8rem;list-style:none}
.nav-links a{color:#94a3b8;font-size:.83rem;padding:.2rem 0;transition:color .15s}
.nav-links a:hover,.nav-links a.active{color:#fff;text-decoration:none}

/* ── Layout ── */
.container{max-width:1200px;margin:0 auto;padding:1.5rem 1rem}
.page-header{margin-bottom:1.4rem;padding-bottom:.9rem;border-bottom:2px solid var(--border)}
.page-header h1{font-size:1.65rem;color:var(--brand)}
.page-header p{color:var(--muted);margin-top:.25rem;font-size:.93rem}

/* ── Grid ── */
.grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(288px,1fr));
  gap:1.2rem;
}

/* ── Card ── */
.card{
  background:var(--card);border-radius:var(--radius);padding:1.15rem;
  box-shadow:0 1px 4px rgba(0,0,0,.07);
  display:flex;flex-direction:column;
  transition:transform .15s,box-shadow .15s;
}
.card:hover{transform:translateY(-2px);box-shadow:0 5px 16px rgba(0,0,0,.11)}

.card-meta{
  display:flex;align-items:center;flex-wrap:wrap;
  gap:.3rem;margin-bottom:.5rem;
}
.badge{
  font-size:.67rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  background:#e0f2fe;color:#0369a1;padding:.1rem .42rem;border-radius:999px;
}
.card-source{font-size:.77rem;color:var(--muted)}
.card-date{font-size:.77rem;color:#94a3b8;margin-left:auto}

.card h2{font-size:.95rem;line-height:1.45;margin-bottom:.4rem}
.card h2 a:hover{color:var(--accent)}

.card-summary{font-size:.84rem;color:#4b5563;flex:1;margin-bottom:.65rem}

.read-more{
  font-size:.79rem;font-weight:600;color:var(--accent);
  display:inline-flex;align-items:center;gap:.2rem;margin-top:auto;
}
.read-more:hover{color:#0284c7;text-decoration:none}

/* ── Pagination ── */
.pagination{
  display:flex;flex-wrap:wrap;justify-content:center;
  gap:.4rem;margin-top:2rem;
}
.pagination a,.pagination span{
  display:inline-flex;align-items:center;justify-content:center;
  min-width:2.2rem;height:2.2rem;padding:0 .65rem;
  border-radius:6px;font-size:.84rem;
  border:1px solid var(--border);background:var(--card);color:#374151;
}
.pagination a:hover{background:#f1f5f9;text-decoration:none}
.pagination .cur{background:var(--brand);color:#fff;border-color:var(--brand)}

/* ── Ad ── */
.ad-slot{margin:1.6rem auto;text-align:center}

/* ── Empty ── */
.empty{text-align:center;color:#94a3b8;padding:3rem 1rem;font-size:.95rem}

/* ── Footer ── */
footer{
  background:var(--brand);color:#64748b;text-align:center;
  padding:1rem;font-size:.77rem;margin-top:3rem;
}
footer a{color:#94a3b8}

/* ── Responsive ── */
@media(max-width:640px){
  .nav-brand{font-size:.97rem}
  .grid{grid-template-columns:1fr}
  .page-header h1{font-size:1.3rem}
}
"""


# ===========================================================================
# Jinja2 templates
# ===========================================================================

# The outer page shell — receives: title, description, canonical, heading,
# subheading, grid (Markup), pagination (Markup), active, css, site_name,
# tagline, adsense_id, categories, year.
PAGE_TMPL = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{{ title }}</title>
  <meta name="description" content="{{ description }}">
  <link rel="canonical" href="{{ canonical }}">
  <link rel="sitemap" type="application/xml" title="Sitemap" href="/sitemap.xml">
  {% if adsense_id %}<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={{ adsense_id }}" crossorigin="anonymous"></script>{% endif %}
  <style>{{ css }}</style>
</head>
<body>

<nav aria-label="Main navigation">
  <div class="nav-inner">
    <a class="nav-brand" href="/">{{ site_name }}</a>
    <ul class="nav-links">
      <li><a href="/"{% if active == 'home' %} class="active" aria-current="page"{% endif %}>All</a></li>
      {% for cat in categories %}
      <li><a href="/category/{{ cat.slug }}/"{% if active == cat.slug %} class="active" aria-current="page"{% endif %}>{{ cat.name }}</a></li>
      {% endfor %}
    </ul>
  </div>
</nav>

<main class="container">
  <div class="page-header">
    <h1>{{ heading }}</h1>
    {% if subheading %}<p>{{ subheading }}</p>{% endif %}
  </div>

  {% if adsense_id %}
  <div class="ad-slot">
    <ins class="adsbygoogle" style="display:block" data-ad-client="{{ adsense_id }}" data-ad-format="auto" data-full-width-responsive="true"></ins>
    <script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>
  </div>
  {% endif %}

  {{ grid }}
  {{ pagination }}
</main>

<footer>
  <p>&copy; {{ year }} <strong>{{ site_name }}</strong> &mdash;
  Headlines link to original publishers. We do not reproduce full articles. &nbsp;|&nbsp;
  <a href="/sitemap.xml">Sitemap</a></p>
</footer>

</body>
</html>\
"""

# The article grid — receives: articles list.
GRID_TMPL = """\
<div class="grid">
{% for a in articles %}
  <article class="card">
    <div class="card-meta">
      <span class="badge">{{ a.category }}</span>
      <span class="card-source">{{ a.source }}</span>
      <time class="card-date" datetime="{{ a.date_iso }}">{{ a.date_str }}</time>
    </div>
    <h2><a href="{{ a.url }}" target="_blank" rel="noopener noreferrer nofollow">{{ a.title }}</a></h2>
    {% if a.summary %}<p class="card-summary">{{ a.summary }}</p>{% endif %}
    <a class="read-more" href="{{ a.url }}" target="_blank" rel="noopener noreferrer nofollow">Read full article &#x2192;</a>
  </article>
{% else %}
  <p class="empty">No articles yet &mdash; check back soon.</p>
{% endfor %}
</div>\
"""


# ===========================================================================
# Site builder
# ===========================================================================

def paginate(items: list, per_page: int) -> list:
    """Split items into pages; always returns at least one (possibly empty) page."""
    if not items:
        return [[]]
    return [items[i : i + per_page] for i in range(0, len(items), per_page)]


def page_href(base: str, n: int) -> str:
    """
    Root-relative href for page n (1-indexed).
    Page 1 → base (e.g. '/' or '/category/tech/')
    Page 2 → base + 'page-2.html'
    """
    return base if n == 1 else f"{base.rstrip('/')}/page-{n}.html"


def render_pagination(base: str, current: int, total: int) -> str:
    if total <= 1:
        return ""
    parts = ['<nav class="pagination" aria-label="Page navigation">']
    if current > 1:
        parts.append(f'<a href="{page_href(base, current - 1)}">&lsaquo; Prev</a>')
    for p in range(1, total + 1):
        if p == current:
            parts.append(f'<span class="cur" aria-current="page">{p}</span>')
        else:
            parts.append(f'<a href="{page_href(base, p)}">{p}</a>')
    if current < total:
        parts.append(f'<a href="{page_href(base, current + 1)}">Next &rsaquo;</a>')
    parts.append("</nav>")
    return "\n".join(parts)


def build_site(config: dict, articles: list) -> None:
    site     = config["site"]
    per_page = config["settings"]["posts_per_page"]
    base_url = site["base_url"].rstrip("/")

    # Only activate AdSense once the publisher ID is filled in
    raw_pub   = site.get("adsense_publisher_id", "")
    adsense   = raw_pub if raw_pub and "XXXXX" not in raw_pub else ""

    year = datetime.now().year

    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / "category").mkdir(exist_ok=True)

    # Build ordered unique category list (preserves first-seen order)
    seen_slugs: set  = set()
    categories: list = []
    for a in articles:
        slug = a["category_slug"]
        if slug not in seen_slugs:
            categories.append({"name": a["category"], "slug": slug})
            seen_slugs.add(slug)

    # Stamp ISO date for <time datetime="…">
    for a in articles:
        d = a.get("date")
        a["date_iso"] = d.date().isoformat() if isinstance(d, datetime) else ""

    env       = Environment(loader=BaseLoader(), autoescape=True)
    page_tmpl = env.from_string(PAGE_TMPL)
    grid_tmpl = env.from_string(GRID_TMPL)

    def write_page(
        path: Path, *,
        title: str, desc: str, canonical: str,
        heading: str, subheading: str,
        grid_html: str, pagination_html: str,
        active: str,
    ) -> None:
        html_out = page_tmpl.render(
            title      = title,
            description= desc,
            canonical  = canonical,
            heading    = heading,
            subheading = subheading,
            grid       = Markup(grid_html),
            pagination = Markup(pagination_html),
            active     = active,
            css        = Markup(CSS),
            site_name  = site["name"],
            categories = categories,
            adsense_id = adsense,
            year       = year,
        )
        path.write_text(html_out, encoding="utf-8")
        print(f"  wrote {path.relative_to(ROOT)}")

    # ------------------------------------------------------------------
    # Homepage (all articles, newest first)
    # ------------------------------------------------------------------
    home_pages = paginate(articles, per_page)
    for pn, batch in enumerate(home_pages, 1):
        write_page(
            OUTPUT / ("index.html" if pn == 1 else f"page-{pn}.html"),
            title      = site["name"] if pn == 1 else f"{site['name']} \u2014 Page {pn}",
            desc       = site["tagline"],
            canonical  = (base_url + "/") if pn == 1 else f"{base_url}/page-{pn}.html",
            heading    = site["name"],
            subheading = site["tagline"],
            grid_html  = grid_tmpl.render(articles=batch),
            pagination_html = render_pagination("/", pn, len(home_pages)),
            active     = "home",
        )

    # ------------------------------------------------------------------
    # Category pages
    # ------------------------------------------------------------------
    for cat in categories:
        cat_arts = [a for a in articles if a["category_slug"] == cat["slug"]]
        cat_dir  = OUTPUT / "category" / cat["slug"]
        cat_dir.mkdir(parents=True, exist_ok=True)
        cat_base = f"/category/{cat['slug']}/"

        cat_pages = paginate(cat_arts, per_page)
        for pn, batch in enumerate(cat_pages, 1):
            write_page(
                cat_dir / ("index.html" if pn == 1 else f"page-{pn}.html"),
                title      = (f"{cat['name']} News" if pn == 1
                               else f"{cat['name']} \u2014 Page {pn}"),
                desc       = f"Latest {cat['name']} news aggregated from across the web.",
                canonical  = (f"{base_url}{cat_base}" if pn == 1
                               else f"{base_url}{cat_base}page-{pn}.html"),
                heading    = cat["name"],
                subheading = f"Latest {cat['name']} news from across the web.",
                grid_html  = grid_tmpl.render(articles=batch),
                pagination_html = render_pagination(cat_base, pn, len(cat_pages)),
                active     = cat["slug"],
            )

    # ------------------------------------------------------------------
    # sitemap.xml
    # ------------------------------------------------------------------
    today = datetime.now().strftime("%Y-%m-%d")
    locs  = [
        f"  <url><loc>{base_url}/</loc>"
        f"<lastmod>{today}</lastmod><changefreq>always</changefreq>"
        f"<priority>1.0</priority></url>"
    ]
    for cat in categories:
        locs.append(
            f"  <url><loc>{base_url}/category/{cat['slug']}/</loc>"
            f"<lastmod>{today}</lastmod><changefreq>always</changefreq>"
            f"<priority>0.8</priority></url>"
        )

    sitemap = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(locs) + "\n"
        "</urlset>\n"
    )
    (OUTPUT / "sitemap.xml").write_text(sitemap, encoding="utf-8")
    print("  wrote output/sitemap.xml")

    # ------------------------------------------------------------------
    # robots.txt
    # ------------------------------------------------------------------
    (OUTPUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {base_url}/sitemap.xml\n",
        encoding="utf-8",
    )
    print("  wrote output/robots.txt")

    n_cat = len(categories)
    n_art = len(articles)
    print(f"\nBuild complete: {n_art} articles across {n_cat} categories.")


# ===========================================================================
# Entry point
# ===========================================================================

def main() -> None:
    print("=" * 60)
    print("RSS Aggregator — fetch & build")
    print("=" * 60)

    print("\n[1/4] Loading config …")
    config = load_config()

    print("\n[2/4] Loading persisted state …")
    seen   = load_seen()
    stored = load_store()
    print(f"      {len(stored)} articles stored, {len(seen)} URLs seen.")

    print("\n[3/4] Fetching feeds …")
    new_articles, new_urls = fetch_new_articles(config, seen)
    print(f"      {len(new_articles)} new articles found.")

    if new_articles:
        seen |= new_urls
        max_total = config["settings"].get("max_total_articles", 1000)
        merged = new_articles + stored           # newest first
        merged = merged[:max_total]              # trim oldest
        save_seen(seen)
        save_store(merged)
        print(f"      Store updated: {len(merged)} total articles.")
    else:
        merged = stored
        print("      Nothing new — rebuilding site from existing store.")

    print("\n[4/4] Building static site …")
    build_site(config, merged)


if __name__ == "__main__":
    main()
