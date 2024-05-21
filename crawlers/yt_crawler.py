import logging
from core.crawler import Crawler
import os
import json

from pytube import Playlist, YouTube
from pydub import AudioSegment

from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled

import whisper

def time_to_seconds(time_str):
    hours, minutes, seconds = time_str.split(':')
    seconds, milliseconds = seconds.split('.')
    total_seconds = int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000
    return total_seconds

class YtCrawler(Crawler):

    def crawl(self) -> None:
        playlist_url = self.cfg.yt_crawler.playlist_url
        whisper_model = self.cfg.yt_crawler.get("whisper_model", "base")
    
        playlist = Playlist(playlist_url)

        download_path = "./downloads"
        model = None

        # Index the main playlist information
        main_doc = {
            'documentId': playlist.playlist_id,
            'title': playlist.title,
            'metadataJson': json.dumps({'url': playlist.playlist_url}),
        }
        try:
            main_doc['section'].append({'text': playlist.description})
        except Exception as e:
            logging.info(f"Can't index description of playlist {playlist.title}, skipping")

        self.indexer.index_document(main_doc)

        num_videos = self.cfg.yt_crawler.get("num_videos", None)
        videos_list = playlist.videos[:num_videos] if num_videos else playlist.videos
        logging.info(f"indexing content of {num_videos} (out of {len(playlist.videos)}) videos from playlist {playlist_url}")
        for video in videos_list:
            yt = YouTube(video.watch_url)
            try:
                transcript = YouTubeTranscriptApi.get_transcript(video.video_id, languages=['en'])
                subtitles = [
                    {
                        'start': segment['start'],
                        'end': segment['start'] + segment['duration'],
                        'text': segment['text']
                    }
                    for segment in transcript
                ]
                logging.info(f"Downloaded subtitles for video {video.title}, total duration is {sum([st['end'] - st['start'] for st in subtitles]):.2f} seconds")

            except TranscriptsDisabled:
                logging.info(f"Transcribing captions for video {video.title} with Whisper model of size {whisper_model} (this may take a while)")
                if model is None:
                    model = whisper.load_model(whisper_model)
                try:
                    stream = yt.streams.get_highest_resolution()
                    stream.download(download_path)
                except Exception as e:
                    logging.info(f"Can't download video {video.title} with id {video.video_id}, e={e}")
                    continue

                audio_filename = os.path.join(download_path, f"audio_file.mp3")
                audio = AudioSegment.from_file(os.path.join(download_path, f"{stream.default_filename}"))
                audio.export(audio_filename, format="mp3")

                # transcribe
                result = model.transcribe(audio_filename, temperature=0)
                subtitles = result['segments']
            
            except Exception as e:
                logging.info(f"Can't process video {video.title} with id {video.video_id}, e={e}")
                continue

            
            # Restore puncutation            
            subtitles_doc = {
                'documentId': video.video_id,
                'title': video.title,
                'metadataJson': json.dumps({'url': video.watch_url}),
                'section': [
                    { 
                        'text': st['text'],
                        'metadataJson': json.dumps({
                            'start': st['start'], 
                            'end': st['end'],
                            'url': f"{video.watch_url}&t={st['start']}s",
                        }),
                    } for st in subtitles
                ]
            }
            # Index into Vectara
            self.indexer.index_document(subtitles_doc)
            logging.info(f"Indexed {len(subtitles)} subtitles for video {video.title}")
