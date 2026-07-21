import sys
import importlib.machinery
import unittest
from unittest.mock import MagicMock, patch

# yt_crawler imports several heavy/optional media deps; stub them all.
for mod in ["cairosvg", "whisper", "pdf2image", "pytubefix", "pydub",
            "youtube_transcript_api"]:
    sys.modules.setdefault(mod, MagicMock())


class _TranscriptsDisabled(Exception):
    pass


_yt_errors = MagicMock()
_yt_errors.TranscriptsDisabled = _TranscriptsDisabled
sys.modules.setdefault("youtube_transcript_api._errors", _yt_errors)

_playwright_mock = MagicMock()
_playwright_mock.__spec__ = importlib.machinery.ModuleSpec("playwright", None)
sys.modules.setdefault("playwright", _playwright_mock)
sys.modules.setdefault("playwright.sync_api", MagicMock())

from omegaconf import OmegaConf

from crawlers.yt_crawler import YtCrawler


class TestYtPlaylistDoc(unittest.TestCase):

    def test_playlist_description_is_indexed(self):
        # Regression: main_doc had no 'sections' key, so appending the playlist
        # description always raised KeyError and the description was never indexed.
        playlist = MagicMock()
        playlist.playlist_id = "PL1"
        playlist.title = "My playlist"
        playlist.description = "A playlist about testing"
        playlist.playlist_url = "https://youtube.com/playlist?list=PL1"
        playlist.videos = []

        crawler = YtCrawler.__new__(YtCrawler)
        crawler.cfg = OmegaConf.create({
            "yt_crawler": {"playlist_url": playlist.playlist_url},
            "vectara": {},
        })
        crawler.indexer = MagicMock()

        with patch("crawlers.yt_crawler.Playlist", return_value=playlist):
            crawler.crawl()

        main_doc = crawler.indexer.index_document.call_args_list[0].args[0]
        self.assertEqual(main_doc["sections"],
                         [{"text": "A playlist about testing"}])


if __name__ == "__main__":
    unittest.main()
