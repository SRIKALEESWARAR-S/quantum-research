# Quantum Learn — Reworked

A lightweight, static science-learning site whose archive is updated by GitHub Actions. **RSS feeds are not required.** The refresh script uses public search/data APIs and degrades gracefully if one provider is unavailable.

## Data sources

- **GDELT DOC API** — recent science/technology news article metadata; no key required.
- **OpenAlex Works API** — scholarly paper metadata and abstracts where available; no key required.
- **Crossref REST API** — publication metadata and abstracts where available; no key required.
- **arXiv search API** — recent quantum-physics preprints (Atom XML API, not an RSS feed); no key required.
- **Google Programmable Search JSON API (optional)** — official Google search results endpoint. It is not HTML scraping and requires `GOOGLE_CSE_API_KEY` and `GOOGLE_CSE_ID` GitHub Actions secrets. Google Programmable Search has its own setup, quotas, and billing/eligibility rules; it is not required for the site to work.

## Run locally

Requires Python 3.10+.

```bash
python -m pip install -r requirements.txt
python fetch.py
```

The first run may take a minute because the script queries several public APIs. It writes valid JSON to `data.json`, keeps existing archive entries, deduplicates by URL, and prints a per-source success/failure line. If an API is temporarily unavailable, other sources can still populate the archive. If every source fails and there is no existing data, the script exits with an error instead of claiming a successful empty refresh.

Optional environment variables:

- `CONTACT_EMAIL`: contact email for polite Crossref/OpenAlex use.
- `GOOGLE_CSE_API_KEY`: Google Programmable Search JSON API key.
- `GOOGLE_CSE_ID`: Programmable Search Engine ID (`cx`).
- `MAX_PER_SOURCE`: records to request per source (3–30; default 12).
- `MAX_TOTAL_NEW`: max new records to add per refresh (5–100; default 40).

## Deploy on GitHub Pages

1. Upload the contents of this folder to the **root of a GitHub repository**. The `.github/workflows/refresh.yml` file must be preserved.
2. In **Settings → Pages**, select **Deploy from a branch** and choose your deployment branch and `/ (root)`.
3. Open **Actions → Refresh Quantum Learn data → Run workflow** to run it once immediately.
4. Open the workflow logs and check each source count. The workflow runs every six hours after that.
5. If the workflow cannot push commits, open **Settings → Actions → General → Workflow permissions** and allow read/write repository permissions.

The workflow commits only when `data.json` changes. The push-trigger excludes the workflow's own data-only commit, avoiding an endless run loop.

## Google search: what to use

Do **not** scrape Google result pages directly. They are unstable, can block automation, and may violate service terms. If Google search results are important, use the official Programmable Search JSON API with the two optional secrets above. For a no-key setup, GDELT + OpenAlex + Crossref + arXiv is the default and avoids depending on a single provider.

## Notes

- Search APIs return metadata and snippets/abstracts, not necessarily full article text. The site should link readers to the original publisher or paper.
- News search results can include unrelated stories; review and tune the query if needed.
- arXiv items are preprints and may not be peer reviewed.
- Public API availability, rate limits, and search coverage can change. The script logs failures and is designed not to silently report a successful empty archive.
