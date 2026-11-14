"""remove_boilerplate on a site with pages in several languages.

goose3 and justext decide what is boilerplate by counting stopwords, so each page must
be extracted with its own language's stoplist. Before the fix the Indexer detected the
language of the first page only and reused it for every page, so on a site whose first
page was English every German/French/Spanish/Japanese/Korean page came back empty.
Japanese also crashed justext (no Japanese stoplist) and French used the English one.
"""

import importlib.machinery
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

# Heavy native deps that the import chain touches.
for _mod in ["cairosvg", "whisper", "pdf2image"]:
    sys.modules.setdefault(_mod, MagicMock())
_pw_mock = MagicMock()
_pw_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _pw_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

import justext  # noqa: E402
from omegaconf import OmegaConf  # noqa: E402

from core.extract import get_article_content, language_stopwords_JusText  # noqa: E402
from core.indexer import Indexer  # noqa: E402

NAV = "<nav><a href='/'>Navtoken home</a> | <a href='/p'>Products</a></nav>"
FOOTER = "<footer>Foottoken 2026 Example Inc. All rights reserved.</footer>"

# One paragraph per language, each carrying its own content token. The Japanese one is
# over 200 characters: justext has no Japanese stoplist, and in its language-independent
# mode only paragraphs longer than length_high (200) count as content.
PARAGRAPHS = {
    "en": "Our storage platform keeps files safe across sites and clouds. The token "
          "Englavor appears in this paragraph. It scales to billions of files and gives "
          "you real-time analytics on how your data is used, so you can plan capacity.",
    "de": "Unsere Speicherplattform schützt Ihre Dateien über alle Standorte und Clouds "
          "hinweg. Das Token Deutravin steht in diesem Absatz. Sie skaliert auf Milliarden "
          "von Dateien und liefert Ihnen Echtzeit-Analysen darüber, wie Ihre Daten genutzt "
          "werden, damit Sie die Kapazität mit Sicherheit planen können.",
    "fr": "Notre plateforme de stockage protège vos fichiers sur tous les sites et dans "
          "tous les clouds. Le jeton Franquelis se trouve dans ce paragraphe. Elle passe à "
          "l'échelle de milliards de fichiers et vous donne des analyses en temps réel sur "
          "l'utilisation de vos données, pour que vous puissiez planifier la capacité.",
    "ja": "当社のストレージプラットフォームは、すべての拠点とクラウドにわたってファイルを保護します。"
          "この段落にはトークン Japorinth が含まれています。数十億のファイルまで拡張でき、"
          "データの使用状況をリアルタイムで分析できるため、自信を持って容量を計画できます。"
          "管理者は単一の画面からすべてのクラスタを監視し、使用量の傾向を把握して、"
          "将来の需要に備えた計画を立てることができます。"
          "導入も簡単で、既存の環境をそのまま活用しながら、段階的に移行を進められます。",
    "ko": "저희 스토리지 플랫폼은 모든 사이트와 클라우드에서 파일을 안전하게 보호합니다. "
          "이 단락에는 토큰 Korvalent가 포함되어 있습니다. 수십억 개의 파일로 확장되며 데이터 "
          "사용 방식에 대한 실시간 분석을 제공하므로 자신 있게 용량을 계획할 수 있습니다.",
}
TOKENS = {"en": "Englavor", "de": "Deutravin", "fr": "Franquelis", "ja": "Japorinth",
          "ko": "Korvalent"}


def _page(lang):
    body = "".join(f"<p>{PARAGRAPHS[lang]}</p>" for _ in range(3))
    return (f"<html><head><title>{lang}</title></head><body>{NAV}"
            f"<article><h1>Title</h1>{body}</article>{FOOTER}</body></html>")


def _url(lang):
    return f"https://example.com/{lang}/page"


class TestStoplists(unittest.TestCase):

    def test_every_mapped_stoplist_exists_in_justext(self):
        available = justext.get_stoplists()
        missing = {code: name for code, name in language_stopwords_JusText.items()
                   if name not in available}
        self.assertEqual(missing, {})

    def test_map_uses_the_codes_langdetect_returns(self):
        import langdetect
        profiles = Path(langdetect.__file__).parent / "profiles"
        codes = {p.name for p in profiles.iterdir()}
        self.assertEqual(set(language_stopwords_JusText) - codes, set())
        # langdetect codes with no matching justext stoplist; these use the
        # language-independent mode. pa: justext's Western_Panjabi is Shahmukhi script,
        # langdetect's pa is Gurmukhi.
        self.assertEqual(codes - set(language_stopwords_JusText),
                         {"ja", "pa", "so", "th", "zh-cn", "zh-tw"})

    def test_dutch_and_norwegian_use_their_stoplists(self):
        self.assertEqual(language_stopwords_JusText["nl"], "Dutch")
        self.assertEqual(language_stopwords_JusText["no"], "Norwegian_Bokmal")

    def test_each_language_keeps_content_and_drops_boilerplate(self):
        for lang, token in TOKENS.items():
            with self.subTest(lang=lang):
                text, _ = get_article_content(_page(lang), _url(lang), lang)
                self.assertIn(token, text)
                self.assertNotIn("Navtoken", text)
                self.assertNotIn("Foottoken", text)

    def test_language_without_a_stoplist_is_not_read_as_english(self):
        # An English stoplist finds no stopwords in German text and drops every paragraph.
        # A language with no mapped stoplist must use justext's language-independent mode.
        text, _ = get_article_content(_page("de"), _url("de"), "xx")
        self.assertIn("Deutravin", text)


class TestDetectLanguage(unittest.TestCase):

    def test_detection_is_deterministic(self):
        # Ambiguous text: unseeded langdetect returns different languages across calls.
        from core.utils import detect_language
        text = "Ons opslagplatform beschermt uw bestanden op alle locaties en in alle clouds."
        self.assertEqual(len({detect_language(text) for _ in range(30)}), 1)


class TestPerPageLanguage(unittest.TestCase):

    def _indexer(self):
        ix = Indexer.__new__(Indexer)
        ix.cfg = OmegaConf.create({"vectara": {"verbose": False}, "doc_processing": {}})
        ix.incremental = False
        ix.add_image_bytes = False
        ix.summarize_images = False
        ix.process_locally = False
        ix.remove_boilerplate = True
        ix.parse_tables = False
        ix.remove_code = False
        ix.extract_metadata = []
        ix.timeout = 90
        ix.last_skip_reason = None
        ix.verbose = False
        ix.model_config = MagicMock()
        ix.file_processor = MagicMock()
        ix.url_triggers_download = MagicMock(return_value=False)
        ix.check_download_or_pdf = MagicMock(return_value={"type": "page"})
        ix.fetch_page_contents = lambda **kw: {
            "url": kw["url"], "html": _page(kw["url"].split("/")[3]),
            "text": PARAGRAPHS[kw["url"].split("/")[3]], "title": "t"}
        ix.index_segments = MagicMock(return_value=True)
        return ix

    def test_each_page_is_extracted_in_its_own_language(self):
        ix = self._indexer()
        for lang, token in TOKENS.items():   # English first, as on most sites
            with self.subTest(lang=lang):
                ix.index_segments.reset_mock()
                self.assertTrue(ix.index_url(_url(lang), metadata={"url": _url(lang)}))
                self.assertIn(token, str(ix.index_segments.call_args))


if __name__ == "__main__":
    unittest.main()
