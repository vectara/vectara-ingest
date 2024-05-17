import logging
from core.crawler import Crawler
import os
import pandas as pd

import whisper
from pytube import Playlist, YouTube
from moviepy.editor import VideoFileClip

class YtCrawler(Crawler):

    def merge_segments(self, segments, max_gap_seconds=1.0):
        """Merge segments based on a maximum gap in seconds."""
        merged = []
        current_text = []
        current_start, current_end = segments[0][0], segments[0][1]

        def to_seconds(time_str):
            h, m, s = map(float, time_str.split(':'))
            return h * 3600 + m * 60 + s

        for segment in segments:
            if to_seconds(segment['start']) - to_seconds(current_end) <= max_gap_seconds:
                current_text.append(segment['text'])
                current_end = segment['end']
            else:
                merged.append((current_start, current_end, " ".join(current_text)))
                current_text = [segment['text']]
                current_start, current_end = segment['start'], segment['end']

        if current_text:
            merged.append((current_start, current_end, " ".join(current_text)))

        return [{'start': start, 'end': end, 'text': text} for start, end, text in merged]

    def crawl(self) -> None:
        playlist_url = self.cfg.yt_crawler.playlist_url
        whisper_model = self.cfg.yt_crawler.get("whisper_model", "base")
        logging.info(f"indexing videos from playlist {playlist_url}")
    

        playlist = Playlist(playlist_url)

        download_path = "./downloads"
        model = whisper.load_model(whisper_model)

        for video in playlist.videos:
            # Download the video
            yt = YouTube(video.watch_url)
            stream = yt.streams.get_highest_resolution()
            stream.download(download_path)

            video = VideoFileClip(os.path.join(download_path, stream.default_filename))
            audio_filename = os.path.join(download_path, f"{stream.default_filename}.mp3")
            video.audio.write_audiofile(audio_filename)

            # transcribe
            result = model.transcribe(audio_filename, temperature=0)
            logging.info(f"DEBUG segments before = {len(result['segments'])}")
            segments = self.merge_segments(result['segments'], max_gap_seconds=0.5)
            logging.info(f"DEBUG segments after = {len(segments)}")

            # Index into Vectara
            self.indexer.index_segments(
                doc_id = video.video_id,
                texts = [segment['text'] for segment in segments],
                metadatas = [{
                    'start': segment['start'],
                    'end': segment['end'],
                    'url': f"{video.watch_url}&t={int(segment['start'])}s"
                } for segment in segments],
                doc_metadata = {'url': video.watch_url },
                doc_title = video.title
            )

