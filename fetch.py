import json, os, re, time, datetime, requests, feedparser
R = os.path.dirname(os.path.abspath(__file__))
UA = "QuantumLearn/1.0 (open-science education project)"
# Only reuse journal papers whose license allows adaptation (CC BY, CC BY-SA, CC0)
OK = re.compile(r"/licenses/by(-sa)?/|/publicdomain/zero/")

def rd(p): return open(os.path.join(R, p), encoding="utf-8").read()
def clean(t): return re.sub(r"\s+", " ", re.sub("<[^>]+>", " ", t or "")).strip()
def lic(u):
    m = re.search(r"licenses/([a-z\-]+)/([\d.]+)", u)
    return f"CC {m.group(1).upper()} {m.group(2)}" if m else "CC0"
def names(a):
    a = [x for x in a if x]
    return ", ".join(a[:3]) + (" et al." if len(a) > 3 else "")
def rr(lists):  # round-robin so no single source uses all the slots
    out = []
    for i in range(max([len(l) for l in lists], default=0)):
        for l in lists:
            if i < len(l): out.append(l[i])
    return out

def feed_items(s):
    out = []
    parsed = feedparser.parse(s["url"], agent=UA)
    if getattr(parsed, "bozo", False): print("feed warning", s["name"], getattr(parsed, "bozo_exception", ""))
    for e in parsed.entries:
        link = re.sub(r"v\d+$", "", e.link) if "arxiv.org" in e.link else e.link
        au = names([a.get("name") for a in e.get("authors", [])])
        out.append({"id": link, "url": link, "title": clean(e.title), "text": clean(e.get("summary", "")),
                    "source": s["name"], "credit": " · ".join(x for x in [au, s["name"], s.get("note")] if x)})
    return out

def oa_abs(doi):  # fallback: OpenAlex abstract (CC0 metadata)
    try:
        r = requests.get(f"https://api.openalex.org/works/doi:{doi}", params={"select": "abstract_inverted_index"}, headers={"User-Agent": UA}, timeout=30)
        idx = r.json().get("abstract_inverted_index") or {}
        return " ".join(w for _, w in sorted((p, w) for w, ps in idx.items() for p in ps))
    except Exception:
        return ""

def journal_items(s):
    r = requests.get(f"https://api.crossref.org/journals/{s['issn']}/works", headers={"User-Agent": UA}, timeout=60,
        params={"sort": "created", "order": "desc", "rows": 10, "mailto": os.getenv("CONTACT_EMAIL", ""),
                "select": "DOI,title,abstract,author,license,URL,created"})
    out = []
    for w in r.json().get("message", {}).get("items", []):
        ok = [l["URL"] for l in w.get("license", []) if OK.search(l.get("URL", ""))]
        if not ok or not w.get("title"):
            print("skip (license/title)", w.get("DOI")); continue
        au = names([f"{a.get('given','')} {a.get('family','')}".strip() for a in w.get("author", [])])
        link = "https://doi.org/" + w["DOI"]
        out.append({"id": link, "url": link, "doi": w["DOI"], "title": clean(w["title"][0]), "text": clean(w.get("abstract")),
                    "source": s["name"], "journal": f"{s['name']}, {w['created']['date-parts'][0][0]}",
                    "credit": " · ".join(x for x in [au, s["name"], lic(ok[0])] if x)})
    return out

def ask(k, c, key, model, P, SYS):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"system_instruction": {"parts": [{"text": SYS}]},
        "contents": [{"parts": [{"text": f"{P[k]}\n\nTITLE: {c['title']}\nSOURCE: {c['url']}\nTEXT: {c['text'][:3000]}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}
    for n in range(4):
        r = requests.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=90)
        if r.status_code == 429:
            time.sleep(30 * (n + 1)); continue  # free-tier rate limit: wait and retry
        if not r.ok:
            # Include the API response body in Actions logs; it usually explains invalid keys,
            # disabled APIs, unavailable models, quota exhaustion, or malformed requests.
            raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:1200]}")
        body = r.json()
        candidates = body.get("candidates") or []
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {json.dumps(body)[:1200]}")
        content = candidates[0].get("content", {})
        parts = content.get("parts") or []
        t = next((p.get("text") for p in parts if p.get("text")), "")
        if not t:
            raise RuntimeError(f"Gemini returned no text: {json.dumps(body)[:1200]}")
        time.sleep(7)  # modest rate-limit pacing
        result = json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", t.strip(), flags=re.I).strip())
        if not isinstance(result, dict) or not isinstance(result.get("en"), dict) or not isinstance(result.get("ta"), dict):
            raise RuntimeError("Gemini response JSON must contain en and ta objects")
        return result
    raise RuntimeError("rate limited")

def main():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it in repository Settings > Secrets and variables > Actions.")
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    per_tab = max(1, int(os.getenv("MAX_NEW", 4)))
    print(f"Starting refresh; model={model}; max_new_per_tab={per_tab}")
    SRC = json.loads(rd("sources.json")); SYS = rd("prompts/system.txt")
    P = {k: rd(f"prompts/{k}.txt") for k in ("news", "quantum", "kids")}
    DB = json.loads(rd("data.json"))
    if not isinstance(DB, dict) or not isinstance(DB.get("items"), list):
        raise RuntimeError("data.json must be a JSON object with an items array")
    seen = {i["id"] for i in DB["items"] if isinstance(i, dict) and i.get("id")}
    print(f"Existing archive items: {len(seen)}")
    total = 0
    for tab in ("news", "quantum"):
        lists = []
        for s in SRC[tab].get("feeds", []):
            try: lists.append([c for c in feed_items(s) if c["id"] not in seen])
            except Exception as ex: print("feed failed", s["name"], ex)
        for s in SRC[tab].get("journals", []):
            try: lists.append([c for c in journal_items(s) if c["id"] not in seen])
            except Exception as ex: print("journal failed", s["name"], ex)
        print(f"{tab}: source candidate counts={[len(x) for x in lists]}, unique unseen={sum(len(x) for x in lists)}")
        n = 0
        for c in rr(lists):
            if n >= per_tab: break
            try:
                if len(c["text"]) < 80 and c.get("doi"): c["text"] = oa_abs(c["doi"])
                if len(c["text"]) < 80: print("skip (no abstract)", c["id"]); continue
                it = {"id": c["id"], "date": datetime.date.today().isoformat(), "title": c["title"],
                      "source": c["source"], "url": c["url"], "credit": c["credit"]}
                if tab == "news":
                    it["news"] = ask("news", c, key, model, P, SYS)
                    if c.get("journal"):
                        for l in ("en", "ta"): it["news"].setdefault(l, {})["journal"] = c["journal"]
                else:
                    it["quantum"] = ask("quantum", c, key, model, P, SYS)
                    it["kids"] = ask("kids", c, key, model, P, SYS)
                DB["items"].append(it); seen.add(c["id"]); n += 1; total += 1
            except Exception as ex:
                print("ERROR processing item", c.get("id", "(no id)"), repr(ex))
    # Items are only ever appended, never deleted: this is the archive.
    target = os.path.join(R, "data.json")
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(DB, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(tmp, target)
    print(f"Refresh complete: added={total}; archive_total={len(DB['items'])}")

if __name__ == "__main__":
    main()
