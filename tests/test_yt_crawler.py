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



class _UnreadableTitle:
    """A pytubefix video whose lazily-fetched `title` raises -- what bot
    detection does to every video in a blocked run."""

    def __init__(self, video_id):
        self.video_id = video_id
        self.watch_url = f"https://www.youtube.com/watch?v={video_id}"

    @property
    def title(self):
        raise RuntimeError(f"{self.video_id} This request was detected as a bot")


class TestYtUnreadableTitle(unittest.TestCase):

    def _crawl(self, video, transcript_api):
        playlist = MagicMock()
        playlist.playlist_id = "PL1"
        playlist.title = "My playlist"
        playlist.description = "A playlist about testing"
        playlist.playlist_url = "https://youtube.com/playlist?list=PL1"
        playlist.videos = [video]

        crawler = YtCrawler.__new__(YtCrawler)
        crawler.cfg = OmegaConf.create({
            "yt_crawler": {"playlist_url": playlist.playlist_url},
            "vectara": {},
        })
        crawler.indexer = MagicMock()

        with patch("crawlers.yt_crawler.Playlist", return_value=playlist), \
             patch("crawlers.yt_crawler.YouTube", return_value=MagicMock()), \
             patch("crawlers.yt_crawler.YouTubeTranscriptApi", transcript_api):
            crawler.crawl()
        return [c.args[0] for c in crawler.indexer.index_document.call_args_list]

    def test_unreadable_title_skips_video_instead_of_aborting(self):
        # Regression: the error handlers logged `video.title`, which pytubefix
        # fetches over the network. Bot detection made it raise *inside* the
        # `except` block, so `continue` never ran and one bad video aborted the
        # whole crawl (exit 1) instead of being skipped.
        api = MagicMock()
        api.get_transcript.side_effect = RuntimeError("no transcript")
        docs = self._crawl(_UnreadableTitle("abc123"), api)
        self.assertEqual(len(docs), 1, "only the playlist doc should be indexed")

    def test_video_is_indexed_when_only_the_title_is_unavailable(self):
        # The transcript comes from youtube_transcript_api, not pytubefix, so a
        # title that can't be fetched must not cost us the transcript.
        api = MagicMock()
        api.get_transcript.return_value = [{"start": 0.0, "duration": 1.5, "text": "hello"}]
        docs = self._crawl(_UnreadableTitle("abc123"), api)
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[1]["id"], "abc123")
        self.assertEqual(docs[1]["title"], "abc123")
        self.assertEqual(docs[1]["sections"][0]["text"], "hello")


if __name__ == "__main__":
    unittest.main()
