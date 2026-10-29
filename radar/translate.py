"""Traducción al español.

- Argos Translate, local y sin claves ni límites, para la mayoría de los idiomas.
- MyMemory (API gratuita, sin cuenta) para el amhárico, que Argos no tiene. Su cupo
  gratuito es chico (unos 5.000 caracteres por día), así que solo se usa para títulos.

Las traducciones se guardan en un caché para que cada texto se traduzca una sola vez.
Si Argos no está instalado (por ejemplo, en una prueba local), las noticias quedan
en su idioma original y se intentan traducir en la próxima corrida.
"""
import hashlib
import html
import logging
import re
import time

import requests

log = logging.getLogger(__name__)

TARGET = "es"
ARGOS_LANGS = {"ar", "he", "de", "fr", "hi", "bn", "zh", "ja"}
MYMEMORY_LANGS = {"am"}
TRANSLATE_LANGS = ARGOS_LANGS | MYMEMORY_LANGS
MYMEMORY_URL = "https://api.mymemory.translated.net/get"
MYMEMORY_MAX_CHARS = 450  # el servicio acepta hasta 500 bytes por pedido
PIVOT = "en"
CACHE_TTL_DAYS = 14

_EN_WORDS = re.compile(r"\b(the|and|of|to|in|is|for|with|has|have|was|were|that|from|after)\b", re.IGNORECASE)
_ES_WORDS = re.compile(r"\b(el|la|los|las|de|del|y|en|que|con|por|para|un|una|se|tras)\b", re.IGNORECASE)
_SPACED_QUOTES = re.compile(r'"\s+([^"]*?)\s+"')
_SENTENCE_SPLIT = re.compile(r"((?<=[.;:!?])\s+|\s*,\s+)")


def looks_english(text):
    """True si el texto parece haber quedado en inglés (le faltó el paso inglés → español)."""
    return bool(text) and len(_EN_WORDS.findall(text)) > len(_ES_WORDS.findall(text))


def tidy(text):
    """Arregla detalles de formato que deja el traductor."""
    text = html.unescape(text)
    text = _SPACED_QUOTES.sub(r'"\1"', text)
    return re.sub(r"\s+([,.;:!?])", r"\1", text).strip()


def _key(lang, text):
    return f"{lang}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:20]}"


class Translator:
    def __init__(self, cache):
        self.cache = cache
        self.now = int(time.time())
        self.models = None
        self.unavailable = None
        self.translated = 0
        self.mymemory_off = None

    def _load(self):
        """Instala (si falta) y carga los modelos de idioma necesarios."""
        if self.models is not None or self.unavailable:
            return
        try:
            import argostranslate.package
            import argostranslate.translate
        except ImportError:
            self.unavailable = "Argos Translate no está instalado"
            log.warning(self.unavailable)
            return

        installed = {(p.from_code, p.to_code) for p in argostranslate.package.get_installed_packages()}
        wanted = {(PIVOT, TARGET)} | {(lang, TARGET) for lang in ARGOS_LANGS} \
            | {(lang, PIVOT) for lang in ARGOS_LANGS}
        if wanted - installed:
            argostranslate.package.update_package_index()
            available = {(p.from_code, p.to_code): p for p in argostranslate.package.get_available_packages()}
            for pair in sorted(wanted - installed):
                if pair in available:
                    log.info("Instalando modelo %s→%s", *pair)
                    argostranslate.package.install_from_path(available[pair].download())
                    installed.add(pair)

        # Solo modelos directos (sin composiciones automáticas): el paso por inglés se hace a mano.
        languages = {lang.code: lang for lang in argostranslate.translate.get_installed_languages()}
        self.models = {}
        for source, target in installed:
            if source in languages and target in languages:
                self.models[(source, target)] = languages[source].get_translation(languages[target])

    def _run(self, text, source, target):
        return self.models[(source, target)].translate(text)

    def _to_spanish(self, lang, text):
        if (lang, TARGET) in self.models:
            result = self._run(text, lang, TARGET)
        else:
            result = self._run(self._run(text, lang, PIVOT), PIVOT, TARGET)
        if looks_english(result):
            result = self._run(result, PIVOT, TARGET)
        if looks_english(result):
            # Con textos largos el modelo inglés→español a veces devuelve el texto sin traducir:
            # último intento, frase por frase.
            # split con grupo de captura: las posiciones impares son los separadores originales.
            parts = _SENTENCE_SPLIT.split(result)
            result = "".join(p if i % 2 or not p.strip() else self._run(p, PIVOT, TARGET).rstrip(".,")
                             + ("." if p.endswith(".") else "")
                             for i, p in enumerate(parts))
        return tidy(result)

    def _mymemory(self, lang, text):
        if self.mymemory_off:
            return None
        text = text[:MYMEMORY_MAX_CHARS]
        try:
            response = requests.get(MYMEMORY_URL, params={"q": text, "langpair": f"{lang}|{TARGET}"}, timeout=20)
            data = response.json()
        except (requests.RequestException, ValueError) as exc:
            self.mymemory_off = f"MyMemory no respondió ({type(exc).__name__})"
            return None
        result = (data.get("responseData") or {}).get("translatedText") or ""
        if data.get("quotaFinished") or str(data.get("responseStatus")) != "200" or "MYMEMORY WARNING" in result:
            self.mymemory_off = "se agotó el cupo diario gratuito de MyMemory"
            log.info(self.mymemory_off)
            return None
        return tidy(result)

    def translate(self, lang, text):
        """Traduce un texto. Devuelve None si no se pudo (queda para otra corrida)."""
        if not text:
            return ""
        key = _key(lang, text)
        hit = self.cache.get(key)
        if hit and not looks_english(hit["es"]):
            hit["used"] = self.now
            return tidy(hit["es"])
        if lang in MYMEMORY_LANGS:
            result = self._mymemory(lang, text)
            if result:
                self.cache[key] = {"es": result, "used": self.now}
                self.translated += 1
            return result
        if self.unavailable:
            return tidy(hit["es"]) if hit else None
        self._load()
        if not self.models or (PIVOT, TARGET) not in self.models:
            return None
        try:
            result = self._to_spanish(lang, text)
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
