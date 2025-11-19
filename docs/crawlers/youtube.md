# YouTube Crawler

The YouTube crawler indexes video content from YouTube playlists by extracting transcripts and captions, with optional speech-to-text transcription using Whisper AI for videos without captions.

## Overview

- **Crawler Type**: `yt`
- **Authentication**: None required (public playlists)
- **Data Source**: YouTube.com playlists and videos
- **Transcript Support**: Built-in and generated captions
- **Speech Recognition**: OpenAI Whisper for caption-less videos
- **Subtitle Processing**: Intelligent merging and timestamping
- **Content**: Video transcripts with linked timestamps
- **Segment Extraction**: Automatic caption-based segmentation

## Use Cases

- Index educational video content for discovery
- Create searchable video transcript repositories
- Build knowledge bases from course playlists
- Archive video lectures and presentations
- Generate searchable transcripts from video content
- Create timestamped content for navigation
- Build AI training datasets from video transcripts
- Make video content searchable and accessible

## Configuration

### Basic Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: youtube-transcripts

crawling:
  crawler_type: yt

yt_crawler:
  # YouTube playlist URL
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx"
```

### Advanced Configuration

```yaml
vectara:
  endpoint: api.vectara.io
  corpus_key: youtube-lectures
  reindex: false
  verbose: true

crawling:
  crawler_type: yt

yt_crawler:
  # YouTube playlist URL
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx"

  # Limit number of videos to process
  num_videos: 50

  # Whisper model size for transcription
  whisper_model: "base"  # tiny, base, small, medium, large

  # Merge subtitles for better readability
  merge_subtitles_gap: 0.5  # Gap threshold in seconds

  # Maximum duration for merged subtitle
  max_subtitle_duration: 30.0  # Seconds

metadata:
  source: youtube
  category: educational
```

## Configuration Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `playlist_url` | string | Yes | - | YouTube playlist URL |
| `num_videos` | int | No | All | Maximum number of videos to index |
| `whisper_model` | string | No | `base` | Whisper model size (tiny, base, small, medium, large) |
| `merge_subtitles_gap` | float | No | - | Gap threshold for subtitle merging (seconds) |
| `max_subtitle_duration` | float | No | `30.0` | Maximum duration for merged subtitles (seconds) |

## How It Works

### Transcript Extraction Process

1. **Playlist Loading**: Retrieves playlist metadata and video list
2. **Playlist Indexing**: Indexes main playlist document with description
3. **Video Processing**: Processes each video:
   - **Transcript Available**: Downloads YouTube captions
   - **No Captions**: Downloads video and transcribes with Whisper
4. **Subtitle Processing**: Merges subtitles if configured
5. **Document Creation**: Creates document with timestamped segments
6. **Indexing**: Uploads to Vectara with segment metadata

### Caption Retrieval

The crawler attempts to fetch captions in this order:

1. **Built-in Captions**: YouTube's auto-generated or user-provided captions (fastest)
2. **Whisper Transcription**: If no captions available, downloads video and transcribes

### Whisper Transcription

When captions aren't available:

1. **Video Download**: Downloads highest resolution video stream
2. **Audio Extraction**: Extracts audio as MP3
3. **Transcription**: Processes with Whisper model
4. **Segmentation**: Generates timing information automatically

## Whisper Models

Choose model based on accuracy vs. speed tradeoff:

| Model | Size | Speed | Accuracy | VRAM |
|-------|------|-------|----------|------|
| `tiny` | 39M | Very Fast | Lower | 1GB |
| `base` | 74M | Fast | Good | 1GB |
| `small` | 244M | Medium | Better | 2GB |
| `medium` | 769M | Slower | Very Good | 5GB |
| `large` | 1.5B | Slowest | Best | 10GB |

**Recommendations**:
- `base` - Good balance, recommended for most uses
- `small` - Better accuracy for important content
- `large` - Maximum accuracy for critical material
- `tiny` - When resources are very limited

```yaml
yt_crawler:
  whisper_model: "base"  # Default: good balance
```

## Subtitle Merging

### Purpose

Merge adjacent subtitles into longer segments for better readability:

```yaml
yt_crawler:
  merge_subtitles_gap: 0.5          # Gap threshold (0.5 seconds)
  max_subtitle_duration: 30.0       # Max length (30 seconds)
```

### Parameters

- **merge_subtitles_gap**: Maximum gap (in seconds) between subtitles to merge them
  - `0.5` - Aggressive merging (join if gap < 0.5s)
  - `2.0` - Conservative merging (join if gap < 2s)

- **max_subtitle_duration**: Maximum length of merged subtitle
  - `30.0` - Default, good for most videos
  - `60.0` - Longer segments for technical content
  - `10.0` - Shorter segments for content mixing

### Without Merging

```yaml
# Don't merge subtitles (use original segments)
yt_crawler:
  playlist_url: "..."
  # Don't specify merge_subtitles_gap
```

### With Merging

```yaml
# Merge subtitles for better readability
yt_crawler:
  merge_subtitles_gap: 0.5
  max_subtitle_duration: 30.0
```

## Metadata Captured

### Playlist Document

- **Title**: Playlist name
- **URL**: Playlist URL
- **Description**: Playlist description

### Video Documents

Each video indexed contains:

- **Video ID**: YouTube video ID
- **Title**: Video title
- **URL**: Video watch URL
- **Segments**: Timestamped subtitle/caption segments

### Segment Metadata

Each segment includes:

- **Text**: Subtitle/caption text
- **Start Time**: Start timestamp (seconds)
- **End Time**: End timestamp (seconds)
- **Timestamped URL**: Watch URL with time parameter (e.g., `?t=120s`)

## Examples

### Educational Course Playlist

```yaml
vectara:
  corpus_key: cs-course

crawling:
  crawler_type: yt

yt_crawler:
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx"
  num_videos: 50
  whisper_model: "base"
  merge_subtitles_gap: 0.5
  max_subtitle_duration: 30.0

metadata:
  source: youtube
  category: education
  course: computer-science
  institution: university
```

### Tech Conference Talks

```yaml
yt_crawler:
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxx"
  num_videos: 100
  whisper_model: "small"  # Better accuracy for technical content
  merge_subtitles_gap: 1.0

metadata:
  source: youtube
  category: conference
  domain: technology
  content_type: talks
```

### Music Production Tutorials

```yaml
yt_crawler:
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxx"
  whisper_model: "medium"  # Better accuracy for audio terminology
  merge_subtitles_gap: 0.5

metadata:
  source: youtube
  category: tutorials
  domain: music-production
```

### Language Learning Content

```yaml
yt_crawler:
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxx"
  num_videos: 200
  whisper_model: "small"
  merge_subtitles_gap: 2.0  # Longer gaps for natural speech flow

metadata:
  source: youtube
  category: language-learning
  language: spanish
```

### Data Science Lectures

```yaml
yt_crawler:
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxx"
  num_videos: 40
  whisper_model: "medium"
  merge_subtitles_gap: 0.5
  max_subtitle_duration: 45.0  # Longer segments for technical content

metadata:
  source: youtube
  category: data-science
  domain: machine-learning
  institution: stanford
```

## Extracting Playlist URLs

### From Browser

1. Visit playlist on YouTube
2. Copy URL from address bar
3. Paste into config:
   ```
   https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx
   ```

### URL Format

Valid playlist URLs:
```
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx
https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx&other=params
```

## Troubleshooting

### Playlist Not Found

**Issue**: `Playlist not found` error

**Solutions**:
1. Verify URL is correct
2. Check playlist is public (not private/unlisted)
3. Copy URL directly from browser:
   ```bash
   # Go to YouTube, click playlist
   # Copy address bar URL
   ```

### No Videos Indexed

**Issue**: Crawler runs but no videos indexed

**Solutions**:
1. Verify playlist has public videos
2. Check `num_videos` isn't set to 0
3. Enable verbose logging:
   ```yaml
   vectara:
     verbose: true
   ```

### Transcripts Not Found

**Issue**: Videos indexed but with minimal content

**Solutions**:
1. Some videos may have captions disabled
2. For those videos, Whisper will transcribe
3. Check Whisper is installed:
   ```bash
   pip install openai-whisper
   ```

### Slow Processing (Whisper Transcription)

**Issue**: Crawler is very slow

**Cause**: Videos without captions require transcription

**Solutions**:
1. Use faster Whisper model:
   ```yaml
   whisper_model: "tiny"  # Faster
   ```
2. Reduce number of videos:
   ```yaml
   num_videos: 10  # Start small
   ```
3. Process in batches with separate configs

### Out of Memory During Transcription

**Issue**: Process killed when transcribing

**Solutions**:
1. Use smaller Whisper model:
   ```yaml
   whisper_model: "tiny"  # Uses less memory
   ```
2. Process fewer videos:
   ```yaml
   num_videos: 5  # Smaller batch
   ```
3. Ensure sufficient disk space for downloads

### Download Failures

**Issue**: Videos fail to download

**Solutions**:
1. Check internet connection
2. Verify video is available/public
3. Some videos may block downloads
4. Increase timeout:
   ```yaml
   vectara:
     timeout: 180
   ```

### Subtitle Merging Issues

**Issue**: Subtitles merged incorrectly

**Solutions**:
1. Adjust gap threshold:
   ```yaml
   merge_subtitles_gap: 1.0  # Less aggressive
   ```
2. Increase max duration:
   ```yaml
   max_subtitle_duration: 60.0  # Allow longer
   ```
3. Disable merging to inspect original segments

### GPU Out of Memory (Whisper)

**Issue**: CUDA out of memory error

**Solutions**:
1. Use CPU-based processing:
   ```bash
   export CUDA_VISIBLE_DEVICES=""  # Disable GPU
   ```
2. Use smaller model:
   ```yaml
   whisper_model: "tiny"
   ```

## Best Practices

### 1. Start with Public Playlists

Test configuration with small, public playlist:

```yaml
num_videos: 5  # Test first
```

### 2. Choose Appropriate Whisper Model

```yaml
# Most cases: good balance
whisper_model: "base"

# High accuracy needed: slower
whisper_model: "medium"

# Speed critical: faster
whisper_model: "tiny"
```

### 3. Enable Subtitle Merging for Better Readability

```yaml
merge_subtitles_gap: 0.5
max_subtitle_duration: 30.0
```

### 4. Set Reasonable Video Limits

```yaml
# Start small
num_videos: 10

# Scale up after validation
num_videos: 100
```

### 5. Use Descriptive Metadata

```yaml
metadata:
  source: youtube
  course: machine-learning
  institution: university
  language: en
```

### 6. Monitor Progress

```yaml
vectara:
  verbose: true
```

Watch logs for transcription progress.

### 7. Handle Large Playlists

For playlists with 100+ videos:

```yaml
# Option 1: Process all
num_videos: null  # All videos

# Option 2: Batch processing
# Create multiple configs for different ranges
```

### 8. Schedule Periodic Updates

For playlists that update:

```bash
# Weekly at 2 AM
0 2 * * 0 cd /path && bash run.sh config/yt.yaml default
```

## Running the Crawler

### Create Your Configuration

```bash
vim config/youtube-course.yaml
```

### Run the Crawler

```bash
# Single run
bash run.sh config/youtube-course.yaml default

# Monitor progress
docker logs -f vingest
```

### First Run Tips

1. Start with small playlist (5-10 videos)
2. Monitor logs for any issues
3. Verify transcripts are captured correctly
4. Expand to larger playlists

## Complete Example

```yaml
# Complete YouTube crawler configuration
vectara:
  endpoint: api.vectara.io
  corpus_key: youtube-edu
  reindex: false
  verbose: true
  timeout: 300  # 5 minutes for large videos

doc_processing:
  model: openai
  model_name: gpt-4o

crawling:
  crawler_type: yt

yt_crawler:
  # YouTube playlist URL
  playlist_url: "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxx"

  # Process first 100 videos
  num_videos: 100

  # Whisper model for transcription
  whisper_model: "base"

  # Merge adjacent subtitles
  merge_subtitles_gap: 0.5

  # Maximum merged subtitle duration
  max_subtitle_duration: 30.0

metadata:
  source: youtube
  category: education
  course: machine-learning
  institution: stanford
  content_type: lectures
  language: en
```

Save as `config/youtube-course.yaml` and run:

```bash
bash run.sh config/youtube-course.yaml default
```

## Performance Considerations

### Without Transcription

- Videos with captions: ~30 seconds per video
- Depends on: Internet speed, caption length, Vectara upload time

### With Transcription (No Captions)

- Video download: 1-5 minutes (depends on length and quality)
- Transcription: Varies by model
  - `tiny`: Very fast (100 min video ~1 minute)
  - `base`: Fast (100 min video ~5 minutes)
  - `small`: Medium (100 min video ~10 minutes)
  - `medium`: Slower (100 min video ~30 minutes)
- Total per video: 5-40 minutes

### Optimization

- Use `tiny` or `base` for speed
- Process playlists during off-peak hours
- Start with subset of videos
- Monitor system resources

## Related Documentation

- [Base Configuration](../configuration-base.md) - Common settings for all crawlers
- [Document Processing](../doc-processing.md) - Content processing options
- [Deployment](../deployment/docker.md) - Running in production
- [Getting Started](../getting-started.md) - Initial setup guide

## External Resources

- [YouTube](https://www.youtube.com) - Video platform
- [OpenAI Whisper](https://github.com/openai/whisper) - Speech recognition
- [pytube Documentation](https://pytube.io/) - YouTube download library
- [youtube-transcript-api](https://github.com/jderose9/youtube-transcript-api) - Caption extraction
