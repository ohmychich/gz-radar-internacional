"""Prueba una lista de feeds candidatos con el mismo código que usa el radar.

Uso:  python -m tools.probar_feeds tools/candidatos.txt > tools/resultado-prueba.txt
Cada línea del resultado: estado, cantidad de noticias, URL y el primer título.
"""
import concurrent.futures as cf
import sys

from radar.feeds import _describe_error, fetch_url, parse_feed


def probe(url):
    try:
        items, _ = parse_feed(fetch_url(url), {"id": "x", "name": "x", "lang": "x"})
        mark = "OK " if items else "VACÍO"
        title = items[0]["title"][:70] if items else ""
        return f"{mark} {len(items):3d} {url} | {title}"
    except Exception as exc:  # noqa: BLE001
        return f"ERROR   0 {url} | {_describe_error(exc)}"


def main(path):
    urls = [line.strip() for line in open(path, encoding="utf-8")
            if line.strip() and not line.startswith("#")]
    with cf.ThreadPoolExecutor(16) as pool:
        for line in pool.map(probe, urls):
            print(line, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
