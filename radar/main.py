"""Corrida completa: descarga, clasifica, traduce y guarda los datos del dashboard.

Uso:  python -m radar.main
"""
import json
import logging
import os
import re
import time
from pathlib import Path

import yaml

from radar.classify import Classifier
from radar.feeds import fetch_all
from radar.translate import TRANSLATE_LANGS, Translator

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config"
DATA = ROOT / "docs" / "data"
NEWS_FILE = DATA / "news.json"
STATUS_FILE = DATA / "feeds-status.json"
CACHE_FILE = DATA / "translations-cache.json"

RETENTION_DAYS = 7
MAX_ITEMS = 4000
# Tope de textos nuevos a traducir por corrida, para que el robot no tarde demasiado.
# Lo que no entra se traduce en la corrida siguiente.
MAX_TRANSLATIONS = int(os.environ.get("RADAR_MAX_TRANSLATIONS", "600"))

log = logging.getLogger("radar")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path, data, pretty=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1 if pretty else None,
                      separators=None if pretty else (",", ":"))
    path.write_text(text + "\n", encoding="utf-8")


def _title_key(item):
    return item["lang"] + ":" + re.sub(r"\W+", " ", item["title"].lower()).strip()[:90]


def merge(previous, fresh, now):
    """Une las noticias guardadas con las nuevas, sin duplicados y dentro del período de retención."""
    cutoff = now - RETENTION_DAYS * 86400
    by_id = {item["id"]: item for item in previous if item["published"] >= cutoff}
    seen_titles = {_title_key(item) for item in by_id.values()}
    for item in fresh:
        if item["published"] < cutoff:
            continue
        if item["id"] in by_id:
            # Ya la teníamos: conservamos traducción y clasificación guardadas.
            continue
        key = _title_key(item)
        if key in seen_titles:
            continue
        seen_titles.add(key)
        item["first_seen"] = now
        by_id[item["id"]] = item
    items = sorted(by_id.values(), key=lambda i: i["published"], reverse=True)
    return items[:MAX_ITEMS]


def update_status(previous, current, now):
    last_ok = {s["url"]: s.get("last_ok") for s in previous.get("feeds", [])}
    for entry in current:
        entry["last_ok"] = now if entry["ok"] else last_ok.get(entry["url"])
    current.sort(key=lambda s: (s["ok"], s["source"]))
    return {
        "updated": now,
        "ok": sum(1 for s in current if s["ok"]),
        "total": len(current),
        "feeds": current,
    }


def run():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = int(time.time())
    sources = yaml.safe_load((CONFIG / "feeds.yaml").read_text(encoding="utf-8"))["sources"]
    rules = yaml.safe_load((CONFIG / "temas.yaml").read_text(encoding="utf-8"))
    by_source = {s["id"]: s for s in sources}
    classifier = Classifier(rules)

    fresh, status = fetch_all(sources)
    log.info("Descargadas %d noticias de %d feeds (%d con error)",
             len(fresh), len(status), sum(1 for s in status if not s["ok"]))

    # Primera clasificación con el texto original: descarta lo que no es de ningún tema.
    kept = []
    for item in fresh:
        source = by_source[item["source_id"]]
        topic, regions = classifier.classify(item, source)
        if topic:
            item["topic"], item["regions"] = topic, regions
            kept.append(item)

    previous = load_json(NEWS_FILE, {}).get("items", [])
    previous = [i for i in previous if i.get("source_id") in by_source]
    items = merge(previous, kept, now)

    translator = Translator(load_json(CACHE_FILE, {}))
    budget = MAX_TRANSLATIONS
    for item in items:
        if item["lang"] not in TRANSLATE_LANGS or item.get("title_es"):
            continue
        if budget <= 0:
            break
        title_es = translator.translate(item["lang"], item["title"])
        summary_es = translator.translate(item["lang"], item["summary"]) if title_es else None
        budget -= 2
        if title_es is None:
            continue
        item["title_es"] = title_es
        if summary_es is not None:
            item["summary_es"] = summary_es
    translator.prune()

    # Clasificación final de todo lo guardado (con traducción, si la hay).
    # Así un cambio en temas.yaml se aplica también a las noticias ya guardadas.
    classified = []
    for item in items:
        topic, regions = classifier.classify(item, by_source[item["source_id"]])
        if topic:
            item["topic"], item["regions"] = topic, regions
            classified.append(item)
    items = classified

    pending = sum(1 for i in items if i["lang"] in TRANSLATE_LANGS and not i.get("title_es"))
    log.info("Traducidos %d textos nuevos; %d noticias esperan traducción", translator.translated, pending)

    topics = {name: t["label"] for name, t in rules["topics"].items()}
    regions = {name: r["label"] for name, r in rules["regions"].items()}
    save_json(NEWS_FILE, {
        "updated": now,
        "topics": topics,
        "regions": regions,
        "translation": {"pending": pending, "engine": "Argos Translate",
                        "unavailable": translator.unavailable},
        "items": items,
    })
    save_json(STATUS_FILE, update_status(load_json(STATUS_FILE, {}), status, now), pretty=True)
    save_json(CACHE_FILE, translator.cache)
    log.info("Guardadas %d noticias", len(items))


if __name__ == "__main__":
    run()
