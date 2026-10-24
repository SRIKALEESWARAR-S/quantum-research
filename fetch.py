#!/usr/bin/env python3
"""Build Quantum Learn's archive from public JSON/XML search APIs (no RSS required).

Primary sources: GDELT news API, OpenAlex, Crossref, and arXiv's Atom API.
Optional: Google Programmable Search JSON API when both CSE secrets are configured.
"""
from __future__ import annotations
import datetime as dt
import html
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from urllib.parse import quote
import requests

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "data.json"
USER_AGENT = "QuantumLearn/2.0 (open research education; contact configured in CONTACT_EMAIL)"
TIMEOUT = 25
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, application/atom+xml, application/xml, */*"})
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()
MAX_PER_SOURCE = max(3, min(30, int(os.getenv("MAX_PER_SOURCE", "12"))))
MAX_TOTAL_NEW = max(5, min(100, int(os.getenv("MAX_TOTAL_NEW", "40"))))


def clean(value: Any) -> str:
    if not value:
        return ""
    text = html.unescape(re.sub(r"<[^>]+>", " ", str(value)))
    return re.sub(r"\s+", " ", text).strip()


def get_json(url: str, params: dict | None = None) -> dict:
    response = SESSION.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


def get_text(url: str, params: dict | None = None) -> str:
    response = SESSION.get(url, params=params, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def authors(items: list[dict] | None) -> str:
    names = []
    for item in (items or [])[:4]:
        name = clean(item.get("author") or item.get("name") or item.get("family") or "")
        if item.get("given") and item.get("family"):
            name = clean(f"{item['given']} {item['family']}")
        if name:
            names.append(name)
    return ", ".join(names) + (" et al." if len(items or []) > 4 else "")


def record(title: str, url: str, summary: str, source: str, category: str, date: str = "", author: str = "") -> dict | None:
    title, url, summary = clean(title), clean(url), clean(summary)
    if not title or not url.startswith(("https://", "http://")):
        return None
    if len(title) < 8:
        return None
    raw_date = str(date or "").strip()
    # Normalize ISO dates, Crossref partial dates, and GDELT timestamps.
    if re.fullmatch(r"\d{8}T\d{6}Z", raw_date):
        raw_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    elif re.fullmatch(r"\d{4}-\d{2}", raw_date):
        raw_date += "-01"
    elif re.fullmatch(r"\d{4}", raw_date):
        raw_date += "-01-01"
    parsed_date = raw_date[:10] if raw_date else TODAY
    try:
        dt.date.fromisoformat(parsed_date)
    except ValueError:
        parsed_date = TODAY
    return {
        "id": url.rstrip("/"), "title": title, "url": url, "summary": summary[:1800],
        "source": source, "category": category, "date": parsed_date, "author": author,
        "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    }


def fetch_gdelt() -> list[dict]:
    """GDELT article-list JSON API; no feed parser or key required."""
    data = get_json("https://api.gdeltproject.org/api/v2/doc/doc", {
        "query": '(quantum OR physics OR science OR technology) (research OR discovery OR study)',
        "mode": "ArtList", "format": "json", "sort": "DateDesc", "maxrecords": MAX_PER_SOURCE,
        "timespan": "7d", "sourcelang": "english"
    })
    out = []
    for a in data.get("articles", []):
        item = record(a.get("title", ""), a.get("url", ""), a.get("seendate", ""),
                      a.get("domain", "Science news"), "news", a.get("seendate", ""))
        if item:
            item["summary"] = "News article discovered through GDELT. Open the publisher's page for the full story."
            out.append(item)
    return out


def fetch_openalex() -> list[dict]:
    """OpenAlex works API returns searchable scholarly metadata and abstracts."""
    data = get_json("https://api.openalex.org/works", {
        "search": "quantum computing quantum physics quantum information",
        "filter": "from_publication_date:2023-01-01,type:article|preprint",
        "sort": "publication_date:desc", "per-page": MAX_PER_SOURCE,
        "select": "id,doi,title,publication_date,authorships,primary_location,open_access,abstract_inverted_index"
    })
    out = []
    for w in data.get("results", []):
        loc = w.get("primary_location") or {}
        source_obj = loc.get("source") or {}
        doi = w.get("doi") or ""
        url = doi if doi.startswith("http") else (loc.get("landing_page_url") or w.get("id", ""))
        inv = w.get("abstract_inverted_index") or {}
        words = sorted((pos, word) for word, positions in inv.items() for pos in positions)
        abstract = " ".join(word for _, word in words)
        auth = authors([{"name": (a.get("author") or {}).get("display_name", "")} for a in w.get("authorships", [])])
        item = record(w.get("title", ""), url, abstract, source_obj.get("display_name") or "OpenAlex", "research", w.get("publication_date", ""), auth)
        if item:
            item["doi"] = doi
            item["open_access"] = bool((w.get("open_access") or {}).get("is_oa"))
            out.append(item)
    return out


def fetch_crossref() -> list[dict]:
    """Crossref REST API; works even when a publisher does not expose an RSS feed."""
    email = os.getenv("CONTACT_EMAIL", "")
    params = {
        "query.bibliographic": "quantum computing quantum information quantum physics",
        "filter": "from-pub-date:2023-01-01", "sort": "published", "order": "desc",
        "rows": MAX_PER_SOURCE,
        "select": "DOI,title,abstract,author,published,URL,type,container-title"
    }
    if email:
        params["mailto"] = email
    data = get_json("https://api.crossref.org/works", params)
    out = []
    for w in data.get("message", {}).get("items", []):
        doi = w.get("DOI", "")
        url = w.get("URL") or ("https://doi.org/" + doi if doi else "")
        date_parts = (w.get("published") or {}).get("date-parts", [[]])[0]
        date = "-".join(str(x).zfill(2) if i else str(x) for i, x in enumerate(date_parts)) if date_parts else ""
        journal = (w.get("container-title") or ["Crossref"])[0]
        item = record((w.get("title") or [""])[0], url, w.get("abstract", ""), journal, "research", date, authors(w.get("author")))
        if item:
            item["doi"] = doi
            out.append(item)
    return out


def fetch_arxiv() -> list[dict]:
    """arXiv search API (Atom XML), not an RSS subscription feed."""
    xml = get_text("https://export.arxiv.org/api/query", {
        "search_query": '(cat:quant-ph) OR (all:"quantum computing") OR (all:"quantum information")',
        "start": 0, "max_results": MAX_PER_SOURCE, "sortBy": "submittedDate", "sortOrder": "descending"
    })
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    out = []
    for e in root.findall("a:entry", ns):
        link = next((x.attrib.get("href", "") for x in e.findall("a:link", ns) if x.attrib.get("rel") == "alternate"), "")
        title = clean(e.findtext("a:title", default="", namespaces=ns))
        abstract = clean(e.findtext("a:summary", default="", namespaces=ns))
        published = e.findtext("a:published", default="", namespaces=ns)[:10]
        au = authors([{"name": clean(x.findtext("a:name", default="", namespaces=ns))} for x in e.findall("a:author", ns)])
        item = record(title, link, abstract, "arXiv", "preprint", published, au)
        if item:
            item["note"] = "Preprint; not necessarily peer reviewed."
            out.append(item)
    return out


def fetch_google_cse() -> list[dict]:
    """Optional official Google Programmable Search JSON API; never scrape Google HTML."""
    key, cx = os.getenv("GOOGLE_CSE_API_KEY", "").strip(), os.getenv("GOOGLE_CSE_ID", "").strip()
    if not key or not cx:
        print("Google CSE skipped: optional GOOGLE_CSE_API_KEY / GOOGLE_CSE_ID secrets not configured.")
        return []
    data = get_json("https://www.googleapis.com/customsearch/v1", {
        "key": key, "cx": cx, "q": "quantum science research physics", "num": min(10, MAX_PER_SOURCE), "dateRestrict": "d7"
    })
    return [x for x in (record(a.get("title", ""), a.get("link", ""), a.get("snippet", ""),
                                    a.get("displayLink", "Google Search"), "news", TODAY) for a in data.get("items", [])) if x]


SOURCES = [("GDELT news API", fetch_gdelt), ("OpenAlex", fetch_openalex),
           ("Crossref", fetch_crossref), ("arXiv API", fetch_arxiv)]
if os.getenv("GOOGLE_CSE_API_KEY", "").strip() and os.getenv("GOOGLE_CSE_ID", "").strip():
    SOURCES.append(("Google Programmable Search", fetch_google_cse))


def main() -> None:
    try:
        db = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        db = {"version": 2, "updated_at": None, "items": []}
    if not isinstance(db, dict) or not isinstance(db.get("items"), list):
        raise RuntimeError("data.json must contain an object with an items array")
    old = {str(x.get("id")): x for x in db["items"] if isinstance(x, dict) and x.get("id")}
    print(f"Starting Quantum Learn refresh; existing items={len(old)}; max new={MAX_TOTAL_NEW}")
    candidates: list[dict] = []
    successful_sources = 0
    for name, fn in SOURCES:
        try:
            found = fn()
            successful_sources += 1
            print(f"{name}: {len(found)} records")
            candidates.extend(found)
        except Exception as exc:
            print(f"WARNING: {name} failed: {type(exc).__name__}: {exc}")
    # Prefer newest items, deduplicate by canonical URL, and keep prior archive entries.
    unique: dict[str, dict] = {}
    for x in candidates:
        key = x["id"].rstrip("/")
        if key not in unique:
            unique[key] = x
        elif len(x.get("summary", "")) > len(unique[key].get("summary", "")):
            unique[key] = x
    fresh = [x for x in unique.values() if x["id"] not in old]
    fresh.sort(key=lambda x: x.get("date", ""), reverse=True)
    fresh = fresh[:MAX_TOTAL_NEW]
    # Keep the archive bounded; retain newest entries and any starter resources.
    merged = {**old, **{x["id"]: x for x in fresh}}
    items = sorted(merged.values(), key=lambda x: x.get("date", ""), reverse=True)[:500]
    db = {"version": 2, "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "items": items,
          "refresh": {"sources_succeeded": successful_sources, "sources_total": len(SOURCES), "new_items": len(fresh)}}
    tmp = DATA_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(db, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(DATA_FILE)
    print(f"Refresh finished: new={len(fresh)}, total={len(items)}, source fetchers completed={successful_sources}/{len(SOURCES)}")
    if successful_sources == 0:
        raise RuntimeError("All data source requests failed; existing archive was preserved. See warnings above.")
    if not items:
        raise RuntimeError("No items were collected. Check network access and source API responses.")

if __name__ == "__main__":
    main()
