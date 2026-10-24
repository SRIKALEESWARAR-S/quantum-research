import json, os, re, time, datetime, requests, feedparser
R = os.path.dirname(os.path.abspath(__file__))
def rd(p): return open(os.path.join(R, p), encoding="utf-8").read()
SRC = json.loads(rd("sources.json"))
SYS = rd("prompts/system.txt")
P = {k: rd(f"prompts/{k}.txt") for k in ("news", "quantum", "kids")}
DB = json.loads(rd("data.json"))
seen = {i["id"] for i in DB["items"]}
KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
MAX = int(os.getenv("MAX_NEW", 6))

def ask(k, e):
    body = re.sub("<[^>]+>", "", e.get("summary", ""))[:3000]
    payload = {"system_instruction": {"parts": [{"text": SYS}]},
        "contents": [{"parts": [{"text": f"{P[k]}\n\nTITLE: {e.title}\nSOURCE: {e.link}\nTEXT: {body}"}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3}}
    for n in range(4):
        r = requests.post(URL, headers={"x-goog-api-key": KEY}, json=payload, timeout=90)
        if r.status_code == 429:
            time.sleep(30 * (n + 1)); continue  # free-tier rate limit: wait and retry
        r.raise_for_status()
        t = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        time.sleep(7)  # stay under free-tier requests per minute
        return json.loads(re.sub(r"^```(json)?|```$", "", t.strip()).strip())
    raise RuntimeError("rate limited")

new = 0
for tab, urls in SRC.items():
    for u in urls:
        f = feedparser.parse(u)
        for e in f.entries:
            if new >= MAX: break
            if e.link in seen: continue
            try:
                it = {"id": e.link, "date": datetime.date.today().isoformat(),
                      "title": e.title, "source": f.feed.get("title", u), "url": e.link}
                if tab == "news": it["news"] = ask("news", e)
                else: it["quantum"] = ask("quantum", e); it["kids"] = ask("kids", e)
                DB["items"].append(it); seen.add(e.link); new += 1
            except Exception as ex:
                print("skip", e.link, ex)
# items are only ever appended, never deleted: this is the archive
json.dump(DB, open(os.path.join(R, "data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("added", new)
