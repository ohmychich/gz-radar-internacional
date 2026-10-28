import sys, feedparser, requests, concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (compatible; gz-radar-internacional/1.0; +https://github.com/ohmychich/gz-radar-internacional)"}
urls=[l.strip() for l in open(sys.argv[1]) if l.strip() and not l.startswith('#')]
def probe(u):
    try:
        r=requests.get(u,headers=UA,timeout=20)
        f=feedparser.parse(r.content)
        n=len(f.entries); t=f.entries[0].get('title','')[:60] if n else ''
        return f"{r.status_code} {n:3d} {u}  | {t}"
    except Exception as e: return f"ERR {u} {type(e).__name__}"
with cf.ThreadPoolExecutor(12) as ex:
    for line in ex.map(probe,urls): print(line)
