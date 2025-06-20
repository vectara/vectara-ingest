import logging
logger = logging.getLogger(__name__)
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

def merge_subtitles(subtitles, threshold=0.5, max_duration=30.0):
    """
    Merge subtitles into sentences based on a timing threshold, ensuring no single subtitle lasts more than max_duration.

    Parameters:
    subtitles (list): A list of dictionaries with 'start', 'end', and 'text' fields.
    threshold (float): The maximum gap (in seconds) between subtitles to merge them.
    max_duration (float): The maximum duration (in seconds) for a single merged subtitle.

    Returns:
    list: A list of merged subtitles as dictionaries with 'start', 'end', and 'text' fields.
    """
    if not subtitles:
        return []

    merged_subtitles = []
    current_subtitle = subtitles[0]

    for i in range(1, len(subtitles)):
        next_subtitle = subtitles[i]
        duration = current_subtitle['end'] - current_subtitle['start']
        next_duration = next_subtitle['end'] - current_subtitle['start']

        # Check if the next subtitle starts within the threshold after the current subtitle ends
        if next_subtitle['start'] - current_subtitle['end'] <= threshold and next_duration <= max_duration:
            # Merge the subtitles
            current_subtitle['text'] += " " + next_subtitle['text']
            current_subtitle['end'] = next_subtitle['end']
        else:
            # If the merged subtitle exceeds the max_duration, split it
            if duration > max_duration:
                split_subtitle = {
                    'start': current_subtitle['start'],
                    'end': current_subtitle['start'] + max_duration,
                    'text': current_subtitle['text'][:len(current_subtitle['text']) // 2]  # Approximate split
                }
                merged_subtitles.append(split_subtitle)
                current_subtitle = {
                    'start': split_subtitle['end'],
                    'end': current_subtitle['end'],
                    'text': current_subtitle['text'][len(current_subtitle['text']) // 2:]
                }
            else:
                # Add the current subtitle to the merged list and start a new one
                merged_subtitles.append(current_subtitle)
                current_subtitle = next_subtitle

    # Add the last subtitle
    duration = current_subtitle['end'] - current_subtitle['start']
    if duration > max_duration:
        split_subtitle = {
            'start': current_subtitle['start'],
            'end': current_subtitle['start'] + max_duration,
            'text': current_subtitle['text'][:len(current_subtitle['text']) // 2]
        }
        merged_subtitles.append(split_subtitle)
        current_subtitle = {
            'start': split_subtitle['end'],
            'end': current_subtitle['end'],
            'text': current_subtitle['text'][len(current_subtitle['text']) // 2:]
        }
    merged_subtitles.append(current_subtitle)
    return merged_subtitles

class YtCrawler(Crawler):

    def crawl(self) -> None:
        playlist_url = self.cfg.yt_crawler.playlist_url
        whisper_model = self.cfg.vectara.get("whisper_model", "base")

        playlist = Playlist(playlist_url)

        download_path = "./downloads"
        model = None

        # Index the main playlist information
        main_doc = {
            'id': playlist.playlist_id,
            'title': playlist.title,
            'metadata': {'url': playlist.playlist_url},
        }
        try:
            main_doc['sections'].append({'text': playlist.description})
        except Exception as e:
            logger.info(f"Can't index description of playlist {playlist.title}, skipping")

        self.indexer.index_document(main_doc)

        num_videos = self.cfg.yt_crawler.get("num_videos", None)
        videos_list = playlist.videos[:num_videos] if num_videos else playlist.videos
        logger.info(f"indexing content of {num_videos} (out of {len(playlist.videos)}) videos from playlist {playlist_url}")
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
                logger.info(f"Downloaded subtitles for video {video.title}, total duration is {sum([st['end'] - st['start'] for st in subtitles]):.2f} seconds")

            except TranscriptsDisabled:
                logger.info(f"Transcribing captions for video {video.title} with Whisper model of size {whisper_model} (this may take a while)")
                try:
                    stream = yt.streams.get_highest_resolution()
                    stream.download(download_path)
                except Exception as e:
                    logger.info(f"Can't download video {video.title} with id {video.video_id}, e={e}")
                    continue

                audio_filename = os.path.join(download_path, "audio_file.mp3")
                audio = AudioSegment.from_file(os.path.join(download_path, f"{stream.default_filename}"))
                audio.export(audio_filename, format="mp3")

                # transcribe
                if model is None:
                    model = whisper.load_model(whisper_model)
                result = model.transcribe(audio_filename, temperature=0)
                subtitles = result['segments']

            except Exception as e:
                logger.info(f"Can't process video {video.title} with id {video.video_id}, e={e}")
                continue

            # Merge subtitles if required
            if self.cfg.yt_crawler.get("merge_subtitles_gap", None):
                cur_size = len(subtitles)
                subtitles = merge_subtitles(subtitles,
                                            threshold=float(self.cfg.yt_crawler.merge_subtitles_gap),
                                            max_duration=float(self.cfg.yt_crawler.get("max_subtitle_duration", 30.0)))
                logger.info(f"Merged {cur_size} subtitles into {len(subtitles)}")

            # Restore puncutation
            subtitles_doc = {
                'id': video.video_id,
                'title': video.title,
                'metadata': {'url': video.watch_url},
                'sections': [
                    {
                        'text': st['text'],
                        'metadata': {
                            'start': st['start'],
                            'end': st['end'],
                            'url': f"{video.watch_url}&t={st['start']}s",
                        },
                    } for st in subtitles
                ]
            }
            # Index into Vectara
            self.indexer.index_document(subtitles_doc)
            logger.info(f"Indexed {len(subtitles)} subtitles for video {video.title}")
