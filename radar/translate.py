"""Traducción local al español con Argos Translate (sin claves ni límites).

Las traducciones se guardan en un caché para que cada texto se traduzca una sola vez.
Si Argos no está instalado (por ejemplo, en una prueba local), las noticias quedan
en su idioma original y se intentan traducir en la próxima corrida.
"""
import hashlib
import html
import logging
import time

log = logging.getLogger(__name__)

TARGET = "es"
TRANSLATE_LANGS = {"ar", "he", "de", "fr"}
PIVOT = "en"
CACHE_TTL_DAYS = 14


def _key(lang, text):
    return f"{lang}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:20]}"


class Translator:
    def __init__(self, cache):
        self.cache = cache
        self.now = int(time.time())
        self.engine = None
        self.unavailable = None
        self.translated = 0

    def _load(self, langs):
        """Instala (si falta) y carga los modelos de idioma necesarios."""
        if self.engine or self.unavailable:
            return
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError:
            self.unavailable = "Argos Translate no está instalado"
            log.warning(self.unavailable)
            return

        installed = {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}
        wanted = set()
        for lang in langs:
            wanted |= {(lang, TARGET), (lang, PIVOT), (PIVOT, TARGET)}
        missing = wanted - installed
        if missing:
            argostranslate.package.update_package_index()
            available = {(p.from_code, p.to_code): p for p in argostranslate.package.get_available_packages()}
            for lang in langs:
                # Preferimos el par directo; si no existe, pasamos por inglés.
                pairs = [(lang, TARGET)] if (lang, TARGET) in available else [(lang, PIVOT), (PIVOT, TARGET)]
                for pair in pairs:
                    if pair not in installed and pair in available:
                        log.info("Instalando modelo %s→%s", *pair)
                        argostranslate.package.install_from_path(available[pair].download())
                        installed.add(pair)
        self.engine = argostranslate.translate

    def translate(self, lang, text):
        """Traduce un texto. Devuelve None si no se pudo (queda para otra corrida)."""
        if not text:
            return ""
        key = _key(lang, text)
        hit = self.cache.get(key)
        if hit:
            hit["used"] = self.now
            return html.unescape(hit["es"])
        if self.unavailable:
            return None
        self._load(TRANSLATE_LANGS)
        if not self.engine:
            return None
        try:
            result = html.unescape(self.engine.translate(text, lang, TARGET))
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo traducir (%s): %s", lang, exc)
            return None
        self.cache[key] = {"es": result, "used": self.now}
        self.translated += 1
        return result

    def prune(self):
        limit = self.now - CACHE_TTL_DAYS * 86400
        for key in [k for k, v in self.cache.items() if v.get("used", 0) < limit]:
            del self.cache[key]
