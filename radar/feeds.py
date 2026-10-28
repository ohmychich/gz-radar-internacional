"""Descarga y normalización de los feeds RSS/Atom."""
import calendar
import concurrent.futures as cf
import hashlib
import html
import re
import time

import feedparser
import requests

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 gz-radar-internacional/1.0 "
    "(+https://github.com/ohmychich/gz-radar-internacional)"
)
TIMEOUT = 25
SUMMARY_MAX = 400

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(value):
    """Quita HTML y espacios sobrantes."""
    text = html.unescape(_TAG_RE.sub(" ", value or ""))
    return _WS_RE.sub(" ", text).strip()


def truncate(text, limit=SUMMARY_MAX):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + "…"


def item_id(link, title):
    return hashlib.sha1((link or title).encode("utf-8")).hexdigest()[:16]


def _entry_timestamp(entry):
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            return calendar.timegm(parsed)
    return None


def parse_feed(content, source):
    """Convierte el contenido de un feed en una lista de noticias normalizadas."""
    parsed = feedparser.parse(content)
    now = int(time.time())
    items = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        link = (entry.get("link") or "").strip()
        if not title or not link:
            continue
        summary = clean_text(entry.get("summary") or entry.get("description"))
        if summary == title:
            summary = ""
        published = _entry_timestamp(entry) or now
        items.append({
            "id": item_id(link, title),
            "source_id": source["id"],
            "source": source["name"],
            "lang": source["lang"],
            "title": title,
            "summary": truncate(summary),
            "link": link,
            # Algunos feeds traen fechas futuras por error de zona horaria.
            "published": min(published, now),
        })
    return items, parsed


def fetch_url(url):
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.content


def fetch_all(sources, workers=16):
    """Descarga todos los feeds en paralelo.

    Devuelve (noticias, estado), donde estado tiene una entrada por URL.
    """
    jobs = [(source, url) for source in sources for url in source["urls"]]
    items, status = [], []

    def run(job):
        source, url = job
        started = time.time()
        entry = {"source_id": source["id"], "source": source["name"], "lang": source["lang"], "url": url}
        try:
            parsed_items, parsed = parse_feed(fetch_url(url), source)
            if not parsed_items and parsed.bozo:
                raise ValueError(f"no es un feed válido ({type(parsed.bozo_exception).__name__})")
            entry.update(ok=bool(parsed_items), items=len(parsed_items),
                         error=None if parsed_items else "el feed no trajo noticias")
        except Exception as exc:  # noqa: BLE001 - se informa cualquier falla en el reporte
            parsed_items = []
            entry.update(ok=False, items=0, error=_describe_error(exc))
        entry["seconds"] = round(time.time() - started, 1)
        return parsed_items, entry

    with cf.ThreadPoolExecutor(workers) as pool:
        for parsed_items, entry in pool.map(run, jobs):
            items.extend(parsed_items)
            status.append(entry)
    return items, status


def _describe_error(exc):
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "tiempo de espera agotado"
    if isinstance(exc, requests.ConnectionError):
        return "no se pudo conectar"
    return str(exc)[:200] or type(exc).__name__
