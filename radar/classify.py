"""Clasificación por reglas: tema (una columna) y regiones de foco."""
import re

TOPIC_PRIORITY = ["mercados", "tech", "geopolitica"]
_NON_LATIN = re.compile(r"[֐-׿؀-ۿ]")


def _compile_keyword(keyword):
    """Convierte una palabra clave de temas.yaml en una expresión regular."""
    keyword = str(keyword)
    flags = re.IGNORECASE
    if keyword.startswith("="):
        keyword, flags = keyword[1:], 0
    if _NON_LATIN.search(keyword):
        # Árabe y hebreo: los prefijos (ال, ו, ה, ב...) van pegados a la palabra.
        return re.compile(re.escape(keyword))
    prefix = keyword.endswith("*")
    body = re.escape(keyword.rstrip("*"))
    end = r"\w*" if prefix else r"(?!\w)"
    return re.compile(rf"(?<!\w){body}{end}", flags)


def _compile_group(group):
    patterns = []
    for keywords in group["keywords"].values():
        patterns.extend(_compile_keyword(k) for k in keywords)
    return patterns


class Classifier:
    def __init__(self, rules):
        self.topics = {name: _compile_group(t) for name, t in rules["topics"].items()}
        self.regions = {name: _compile_group(r) for name, r in rules["regions"].items()}
        self.exclude = [re.compile(p, re.IGNORECASE)
                        for p in rules["topics"]["mercados"].get("exclude", [])]

    @staticmethod
    def _score(patterns, text):
        return sum(1 for p in patterns if p.search(text))

    def classify(self, item, source):
        """Devuelve (tema, regiones). El tema es None si la noticia no entra en ninguna columna."""
        text = " ".join(filter(None, [
            item["title"], item.get("summary"),
            item.get("title_es"), item.get("summary_es"),
        ]))

        text_regions = [name for name, patterns in self.regions.items() if self._score(patterns, text)]
        regions = list(text_regions)
        if source.get("region") and source["region"] not in regions:
            regions.append(source["region"])

        scores = {name: self._score(patterns, text) for name, patterns in self.topics.items()}
        if source.get("topic"):
            # El tema del feed suma, pero no se impone si el texto habla de otra cosa.
            scores[source["topic"]] += 1

        headline = " ".join(filter(None, [item["title"], item.get("title_es")]))
        if any(p.search(headline) for p in self.exclude):
            scores["mercados"] = 0

        best = max(scores.values())
        if best > 0:
            # Desempate: primero el tema del feed, después el orden de prioridad.
            tied = [t for t in TOPIC_PRIORITY if scores[t] == best]
            topic = source.get("topic") if source.get("topic") in tied else tied[0]
        elif text_regions:
            # Menciona un país o actor de la región aunque no tenga palabras de ningún tema.
            # La región del feed sola no alcanza: así no entran deportes o ciencia de un medio regional.
            topic = "geopolitica"
        else:
            topic = None
        return topic, sorted(regions)
