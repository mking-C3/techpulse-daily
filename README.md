# RSS Aggregator — Static Site

A fully automated, zero-maintenance content aggregation website.

- **Python** fetches RSS feeds and generates static HTML
- **GitHub Actions** runs the pipeline every 6 hours and auto-commits
- **Cloudflare Pages** deploys on every commit automatically
- **Google AdSense** auto-ads (add your publisher ID to go live)

---

## How it works

```
Every 6 hours
     │
     ▼
GitHub Actions
  └─ pip install
  └─ python fetch_and_build.py
       ├─ Fetch RSS feeds
       ├─ Deduplicate via seen_urls.json
       ├─ Persist to articles.json
       └─ Generate output/ (HTML + sitemap + robots.txt)
  └─ git commit & push (only if new content)
     │
     ▼
Cloudflare Pages auto-deploys output/
```

---

## Setup (one-time, ~10 minutes)

### 1. Fork this repository

Click **Fork** on GitHub. Your fork is what GitHub Actions and Cloudflare Pages will use.

### 2. Edit `config.yaml`

Open `config.yaml` and fill in:

| Field | What to change |
|---|---|
| `site.name` | Your site's display name |
| `site.tagline` | Short description shown on the homepage |
| `site.base_url` | Your Cloudflare Pages URL (e.g. `https://my-site.pages.dev`) — update this after step 4 |
| `site.adsense_publisher_id` | Your AdSense publisher ID (e.g. `ca-pub-1234567890`) — fill in after AdSense approval |
| `feeds` | Add/remove RSS feed entries (category + url) |
| `settings.*` | Tune post limits and pagination |

Add as many feeds as you like. Use the same `category` label on multiple feeds to group them.

### 3. Enable GitHub Actions write permissions

1. Go to your fork → **Settings** → **Actions** → **General**
2. Under **Workflow permissions**, select **Read and write permissions**
3. Click **Save**

This allows the Actions bot to commit the generated HTML back to the repo.

### 4. Connect Cloudflare Pages

1. Log in to [Cloudflare Dashboard](https://dash.cloudflare.com)
2. Go to **Workers & Pages** → **Create application** → **Pages** → **Connect to Git**
3. Select your forked repository and click **Begin setup**
4. Configure the build:
   - **Production branch:** `main`
   - **Build command:** *(leave empty)*
   - **Build output directory:** `output`
5. Click **Save and Deploy**

After the first deploy, copy your `*.pages.dev` URL and paste it into `config.yaml` → `site.base_url`.

### 5. Trigger the first build

Go to your fork → **Actions** → **Fetch Feeds & Build Site** → **Run workflow**.

This does the initial fetch and commits `output/`, which triggers a Cloudflare Pages deploy.

### 6. (Optional) Add Google AdSense

1. Apply at [Google AdSense](https://www.google.com/adsense/)
2. Once approved, copy your publisher ID (`ca-pub-XXXXXXXXXX`)
3. Paste it into `config.yaml` → `site.adsense_publisher_id`
4. Commit — the next build will insert the AdSense script tag and an auto-ad unit

The AdSense script is only injected when the publisher ID is set to a real value (not the placeholder).

---

## File reference

```
.
├── config.yaml              ← THE ONLY FILE YOU NEED TO EDIT
├── fetch_and_build.py       ← Core script (fetch + build)
├── requirements.txt         ← Python dependencies
├── seen_urls.json           ← Deduplication state (auto-managed)
├── articles.json            ← Article store (auto-managed)
├── output/                  ← Generated site (auto-managed, served by CF Pages)
│   ├── index.html
│   ├── page-2.html          ← Homepage pagination
│   ├── sitemap.xml
│   ├── robots.txt
│   └── category/
│       └── {slug}/
│           ├── index.html
│           └── page-2.html  ← Category pagination
└── .github/
    └── workflows/
        └── build.yml        ← GitHub Actions workflow
```

---

## Customising feeds

Add a feed to `config.yaml`:

```yaml
feeds:
  - category: "Cybersecurity"
    url: "https://feeds.feedburner.com/TheHackersNews"
```

Remove a feed by deleting its entry. Existing articles from that feed stay in the store unless you clear `articles.json`.

To start completely fresh (e.g. after changing the site topic):

```bash
echo '[]' > seen_urls.json
echo '[]' > articles.json
```

Then push and run the workflow.

---

## Running locally

```bash
pip install -r requirements.txt
python fetch_and_build.py
# Open output/index.html in a browser
```

---

## Copyright notice

This site **never copies full article text**. Each card shows only:
- Headline
- Source name
- Publication date
- A short excerpt (≤ 120 words, configurable)
- A "Read full article" link to the original source

This is the standard aggregator/news-reader model. If a publisher objects to inclusion, remove their feed from `config.yaml`.
