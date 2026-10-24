# Quantum Learn

A small, bilingual (English/Tamil) science-learning site for research news, quantum-computing preprints, and kid-friendly explanations.

## Highlights
- Responsive, accessible interface with English/Tamil switching, accent-color controls, month filtering, search, and browser text-to-speech.
- Research summaries retain source links and author/licence credit.
- Automated content refresh using GitHub Actions and the Gemini API.
- Existing archive entries are preserved; refreshes append new items rather than replacing the archive.

## Run locally
The site is static. From this directory, start any local web server, for example:

```bash
python -m http.server 8000
```

Open `http://localhost:8000`. Opening `index.html` directly may prevent `data.json` from loading because browsers restrict local-file fetches.

## Enable automatic updates
1. Push this directory to a GitHub repository.
2. Add a repository Actions secret named `GEMINI_API_KEY`.
3. In **Actions**, run **Refresh Quantum Learn** manually once. The workflow also runs every six hours.
4. Confirm the workflow can commit updates to `data.json`. Keep workflow permissions limited to what is needed.

Optional variables:
- `GEMINI_MODEL`: model name; defaults to `gemini-2.5-flash`.
- `MAX_NEW`: maximum new entries per category on each run; defaults to `4` in `fetch.py` (workflow currently sets `2`).

## Important notes
- AI-generated explanations can be wrong. The interface links to the original source and labels AI summaries.
- arXiv entries are preprints and are not peer reviewed.
- Journal articles are included only when Crossref reports a licence matching the allowlist in `fetch.py` (CC BY, CC BY-SA, or CC0).
- The initial `data.json` archive is empty. It populates after a successful workflow run.
- Never put API keys in HTML, source control, or `data.json`; use GitHub Actions secrets.
