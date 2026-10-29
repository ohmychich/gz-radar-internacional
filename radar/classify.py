"""Clasificación por reglas: temas (pueden ser varios) y regiones de foco."""
import re

MAX_TOPICS = 3
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
        self.topic_order = list(rules["topics"])
        self.topics = {name: _compile_group(t) for name, t in rules["topics"].items()}
        self.regions = {name: _compile_group(r) for name, r in rules["regions"].items()}
        self.price_headlines = [re.compile(p, re.IGNORECASE)
                                for p in rules["topics"]["economia"].get("exclude", [])]
        self.off_topic = [re.compile(p, re.IGNORECASE) for p in rules.get("exclude_headlines", [])]

    @staticmethod
    def _score(patterns, text):
        return sum(1 for p in patterns if p.search(text))

    def classify(self, item, source):
        """Devuelve (temas, regiones, relevante).

        relevante es False si la noticia no tiene que entrar al radar.
        """
        text = " ".join(filter(None, [
            item["title"], item.get("summary"),
            item.get("title_es"), item.get("summary_es"),
        ]))
        headline = " ".join(filter(None, [item["title"], item.get("title_es")]))
        if any(p.search(headline) for p in self.off_topic):
            return [], [], False

        text_regions = [name for name, patterns in self.regions.items() if self._score(patterns, text)]
        regions = list(text_regions)
        if source.get("region") and source["region"] not in regions:
            regions.append(source["region"])

        scores = {name: self._score(patterns, text) for name, patterns in self.topics.items()}
        if any(p.search(headline) for p in self.price_headlines):
            scores["economia"] = 0
        topics = sorted((t for t in self.topic_order if scores[t] > 0),
                        key=lambda t: (-scores[t], self.topic_order.index(t)))[:MAX_TOPICS]
        if not topics and source.get("topic"):
            topics = [source["topic"]]

        # Entra si tiene algún tema o menciona un país/actor de África o Medio Oriente.
        # Los medios africanos entran siempre (salvo deportes y espectáculos): son el foco del radar.
        relevant = bool(topics or text_regions or source.get("region") == "africa")
        return topics, sorted(regions), relevant
