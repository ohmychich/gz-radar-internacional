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

    def check(self, title, topics, regions=None, lang="en", source=SOURCE, summary="", relevant=True):
        got_topics, got_regions, got_relevant = self.c.classify(item(title, summary, lang), source)
        self.assertEqual(got_relevant, relevant, title)
        for topic in topics:
            self.assertIn(topic, got_topics, title)
        if regions is not None:
            self.assertEqual(got_regions, sorted(regions), title)
        return got_topics

    def test_several_topics(self):
        topics = self.check("Saudi Aramco prices $5bn sukuk as Gulf issuers rush to debt markets",
                            ["economia", "energia"], ["medio_oriente"])
        self.assertLessEqual(len(topics), 3)
        self.check("Sudan war and inflation leave families struggling in Khartoum",
                   ["conflictos", "economia"], ["africa"])

    def test_price_headlines_lose_economy(self):
        self.check("Stocks rise as Dow closes higher", [], relevant=False)
        self.check("Wall Street cierra con alzas: el Merval sube 3%", [], lang="es", relevant=False)

    def test_tech(self):
        self.check("OpenAI unveils new model as Nvidia chip demand soars", ["tech"])
        self.check("La IA generativa llega a los bancos africanos", ["tech"], ["africa"], lang="es")

    def test_politics_conflicts_society(self):
        self.check("Sudan ceasefire talks resume in Jeddah", ["conflictos", "politica"], ["africa"])
        self.check("Egypt hosts Gaza truce talks", ["conflictos", "politica"], ["africa", "medio_oriente"])
        self.check("Ebola outbreak spreads in eastern Congo", ["sociedad"], ["africa"])
        self.check("DRC cobalt exports hit record as lithium demand grows", ["energia", "economia"], ["africa"])

    def test_other_languages(self):
        self.check("Le Mali et le Niger quittent la Cédéao", ["politica"], ["africa"], lang="fr")
        self.check("EZB senkt den Leitzins erneut", ["economia"], lang="de")
        self.check("وقف إطلاق النار في غزة", ["conflictos"], ["medio_oriente"], lang="ar")
        self.check("בנק ישראל הותיר את הריבית ללא שינוי", ["economia"], ["medio_oriente"], lang="he")

    def test_case_sensitive_acronyms(self):
        # "ai" en francés (j'ai) no es IA.
        self.check("J'ai vu un film", [], lang="fr", relevant=False)

    def test_feed_hints(self):
        tech_feed = dict(SOURCE, topic="tech")
        self.check("A new release from the lab", ["tech"], source=tech_feed)

    def test_african_feeds_always_count(self):
        africa_feed = dict(SOURCE, region="africa")
        self.check("Community leaders meet farmers", [], ["africa"], source=africa_feed)
        # Salvo deportes.
        self.check("Super Eagles striker scores hat-trick", [], source=africa_feed, relevant=False)

    def test_regional_feed_needs_more_than_its_region(self):
        me_feed = dict(SOURCE, region="medio_oriente")
        self.check("Manchester United: why managers fail to succeed Ferguson", [], source=me_feed, relevant=False)
        self.check("Gulf ministers meet in Riyadh", ["politica"], ["medio_oriente"], source=me_feed)

    def test_sports_are_out_even_with_a_country(self):
        self.check("Morocco beat Egypt in AFCON semi-final", [], relevant=False)
        self.check("كرة القدم: المنتخب المصري يفوز", [], lang="ar", relevant=False)

    def test_west_bank_is_not_a_bank(self):
        topics = self.check("Palestinians in the West Bank see little hope in Israeli vote",
                            ["politica"], ["medio_oriente"])
        self.assertNotIn("economia", topics)

    def test_irrelevant(self):
        self.check("Local bakery wins award for best croissant", [], relevant=False)


class ConfigTest(unittest.TestCase):
    def test_feeds_yaml(self):
        sources = yaml.safe_load((ROOT / "config" / "feeds.yaml").read_text(encoding="utf-8"))["sources"]
        ids = [s["id"] for s in sources]
        self.assertEqual(len(ids), len(set(ids)), "hay ids repetidos")
        for source in sources:
            self.assertIn(source["lang"], {"es", "en", "ar", "he", "de", "fr", "hi", "bn", "zh", "ja", "am"}, source["id"])
            self.assertIn(source.get("topic"), {None, *RULES["topics"]}, source["id"])
            self.assertIn(source.get("region"), {None, *RULES["regions"]}, source["id"])
            self.assertTrue(source["urls"], source["id"])
            for url in source["urls"]:
                self.assertTrue(url.startswith(("https://", "http://")), url)


class CleanTextTest(unittest.TestCase):
    def test_double_escaped_entities(self):
        from radar.feeds import clean_text
        self.assertEqual(clean_text("&amp;quot;Ma&amp;#039;aden&amp;quot; <b>names</b> chair"), '"Ma\'aden" names chair')


class TranslateHelpersTest(unittest.TestCase):
    def test_detects_text_left_in_english(self):
        from radar.translate import looks_english
        self.assertTrue(looks_english("Divergent results of the companies have prompted investors to re-evaluate"))
        self.assertFalse(looks_english("Los resultados de las empresas llevaron a los inversores a reevaluar"))

    def test_tidy(self):
        from radar.translate import tidy
        self.assertEqual(tidy('Resultados de " Alphabet " y " Microsoft " , hoy'), 'Resultados de "Alphabet" y "Microsoft", hoy')


class MyMemoryTest(unittest.TestCase):
    def _translator(self, payload):
        from unittest import mock
        from radar import translate
        t = translate.Translator({})
        response = mock.Mock()
        response.json.return_value = payload
        patcher = mock.patch.object(translate.requests, "get", return_value=response)
        self.addCleanup(patcher.stop)
        return t, patcher.start()

    def test_amharic_uses_mymemory_and_cache(self):
        t, get = self._translator({"responseStatus": 200, "responseData": {"translatedText": "Etiopía y Egipto hablan de la represa"}})
        self.assertEqual(t.translate("am", "ኢትዮጵያ እና ግብፅ"), "Etiopía y Egipto hablan de la represa")
        self.assertEqual(t.translate("am", "ኢትዮጵያ እና ግብፅ"), "Etiopía y Egipto hablan de la represa")
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["langpair"], "am|es")

    def test_quota_exhausted_stops_for_the_run(self):
        t, get = self._translator({"responseStatus": 429, "quotaFinished": True,
                                   "responseData": {"translatedText": "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS"}})
        self.assertIsNone(t.translate("am", "ሰላም"))
        self.assertIsNone(t.translate("am", "ሌላ"))
        self.assertEqual(get.call_count, 1)
        self.assertIn("cupo", t.mymemory_off)


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
