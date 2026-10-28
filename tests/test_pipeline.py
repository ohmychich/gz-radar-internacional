import unittest
from pathlib import Path

import yaml

from radar.classify import Classifier
from radar.feeds import parse_feed
from radar.main import merge

ROOT = Path(__file__).resolve().parent.parent
RULES = yaml.safe_load((ROOT / "config" / "temas.yaml").read_text(encoding="utf-8"))
SOURCE = {"id": "test", "name": "Test", "lang": "en", "urls": []}


def item(title, summary="", lang="en"):
    return {"title": title, "summary": summary, "lang": lang}


class ClassifyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = Classifier(RULES)

    def check(self, title, topic, regions=None, lang="en", source=SOURCE, summary=""):
        got_topic, got_regions = self.c.classify(item(title, summary, lang), source)
        self.assertEqual(got_topic, topic, title)
        if regions is not None:
            self.assertEqual(got_regions, sorted(regions), title)

    def test_markets_information(self):
        self.check("Saudi Aramco prices $5bn sukuk as Gulf issuers rush to debt markets",
                   "mercados", ["medio_oriente"])

    def test_price_headlines_are_discarded(self):
        self.check("Stocks rise as Dow closes higher", None)
        self.check("Wall Street cierra con alzas: el Merval sube 3%", None, lang="es")

    def test_tech(self):
        self.check("OpenAI unveils new model as Nvidia chip demand soars", "tech")
        self.check("La IA generativa llega a los bancos africanos", "tech", ["africa"], lang="es")

    def test_geopolitics_and_regions(self):
        self.check("Sudan ceasefire talks resume in Jeddah", "geopolitica", ["africa"])
        self.check("Egypt hosts Gaza truce talks", "geopolitica", ["africa", "medio_oriente"])

    def test_other_languages(self):
        self.check("Le Mali et le Niger quittent la Cédéao", "geopolitica", ["africa"], lang="fr")
        self.check("EZB senkt den Leitzins erneut", "mercados", lang="de")
        self.check("وقف إطلاق النار في غزة", "geopolitica", ["medio_oriente"], lang="ar")
        self.check("בנק ישראל הותיר את הריבית ללא שינוי", "mercados", ["medio_oriente"], lang="he")

    def test_case_sensitive_acronyms(self):
        # "ai" en francés (j'ai) no es IA.
        self.check("J'ai vu un film", None, lang="fr")

    def test_feed_hints(self):
        tech_feed = dict(SOURCE, topic="tech")
        self.check("A new release from the lab", "tech", source=tech_feed)
        africa_feed = dict(SOURCE, region="africa")
        self.check("Community leaders meet farmers in Kenya", "geopolitica", ["africa"], source=africa_feed)

    def test_regional_feed_needs_more_than_its_region(self):
        me_feed = dict(SOURCE, region="medio_oriente")
        self.check("Manchester United: why managers fail to succeed Ferguson", None, source=me_feed)
        self.check("Gulf ministers meet in Riyadh", "geopolitica", ["medio_oriente"], source=me_feed)

    def test_west_bank_is_not_a_bank(self):
        self.check("Palestinians in the West Bank see little hope in Israeli vote", "geopolitica", ["medio_oriente"])

    def test_irrelevant(self):
        self.check("Local bakery wins award for best croissant", None)


class ConfigTest(unittest.TestCase):
    def test_feeds_yaml(self):
        sources = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text(encoding="utf-8"))["sources"]
        ids = [s["id"] for s in sources]
        self.assertEqual(len(ids), len(set(ids)), "hay ids repetidos")
        for source in sources:
            self.assertIn(source["lang"], {"es", "en", "ar", "he", "de", "fr"}, source["id"])
            self.assertIn(source.get("topic"), {None, *RULES["topics"]}, source["id"])
            self.assertIn(source.get("region"), {None, *RULES["regions"]}, source["id"])
            self.assertTrue(source["urls"], source["id"])
            for url in source["urls"]:
                self.assertTrue(url.startswith("https://"), url)


class CleanTextTest(unittest.TestCase):
    def test_double_escaped_entities(self):
        from radar.feeds import clean_text
        self.assertEqual(clean_text("&amp;quot;Ma&amp;#039;aden&amp;quot; <b>names</b> chair"), '"Ma\'aden" names chair')


class FeedTest(unittest.TestCase):
    def test_parse_and_merge(self):
        content = (ROOT / "tests" / "fixtures" / "sample.xml").read_bytes()
        items, _ = parse_feed(content, SOURCE)
        self.assertEqual(len(items), 5)
        self.assertEqual(items[0]["summary"], "The deal drew strong investor demand.")
        now = items[-1]["published"] + 3600
        merged = merge([], items, now)
        self.assertEqual(len(merged), 5)
        # Repetir la misma descarga no duplica.
        self.assertEqual(len(merge(merged, items, now)), 5)
        # Lo que tiene más de 7 días se descarta.
        self.assertEqual(merge(merged, [], now + 8 * 86400), [])


if __name__ == "__main__":
    unittest.main()
