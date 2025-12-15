# Video Creator

Automation tool for creating professional overlay videos with animated content, perfect for FPP (Falcon Pi Player) displays, digital signage, or music videos.

## Features

### Core Functionality
- **Automated Video Generation**: Pairs MP4 background videos with MP3 audio tracks
- **Text Overlays**: Customizable text with fonts, colors, borders, and shadows
- **Image Overlays**: Support for PNG/JPG overlays with transparency and scaling
- **Dynamic Content**: MP3 metadata placeholders (`{title}`, `{artist}`) for song information
- **Random Background Selection**: Automatically selects from available background videos

### Advanced Animation System
- **Animation Groups**: Create time-based content that cycles on/off during the video
  - Define groups of overlays that appear/disappear together
  - Set custom durations for each animation group
  - Perfect for alternating between FM frequency info, QR codes, and other content
- **Smooth Transitions**: Fade in/out transitions between animation groups
- **Smart Duration Handling**: Automatically loops or truncates base videos to fit complete animation cycles
- **Enhanced Background Caching**: MD5-based intelligent caching only regenerates when content changes

### Compression & Performance
- **Software Encoding**: H.264 with configurable CRF (18-35) and presets (ultrafast to veryslow)
- **Hardware Encoding**: VideoToolbox support for Mac (3-5x faster encoding)
- **Quality Control**: Fine-tune compression vs. quality balance
- **Batch Processing**: Process all songs or specific files

### Command-Line Interface
- **Custom Config**: `--config` / `-c` to specify configuration file
- **Selective Processing**: `--audio` / `-a` to process specific audio files
- **Force Regeneration**: `--force-regenerate` / `-f` to bypass cache
- **Verbose Mode**: `--verbose` / `-v` for detailed processing information
- **Compression Control**: `--compress` to enable compression via CLI

## Requirements

- Python 3.x
- FFmpeg (with hardware encoding support for VideoToolbox on Mac)
- Python packages:
  - `ffmpeg-python`
  - `tinytag`

## Installation

```bash
# Install Python dependencies
pip install ffmpeg-python tinytag

# Or using uv (modern package manager)
uv pip install ffmpeg-python tinytag
```

## Configuration

### Basic Setup

Edit `video_creator.cfg` to configure paths and overlay settings:

```ini
[Paths]
mp3_directory = /path/to/audio/files
mp4_directory = /path/to/background/videos

[Output]
output_directory = /path/to/output
scale = 1280:720
output_exists = skip  # or 'overwrite'
```

### Text Overlays

Add text overlays with full FFmpeg drawtext parameter support:

```ini
[Line1]
fontfile=/path/to/font.ttf
text=Tune to
fontsize=180
fontcolor=white
bordercolor=black
borderw=5
shadowcolor=black
shadowx=10
shadowy=10
x=(w-text_w)/2
y=(h-text_h)/2
```

**Dynamic Content**: Use `{title}` and `{artist}` placeholders to pull from MP3 metadata.

### Image Overlays

Add logos, QR codes, or other images:

```ini
[Line_Logo]
image=/path/to/logo.png
scale=250:-1  # width:height, -1 for auto
x=10
y=10
```

### Animation Groups

Create time-based animations that cycle content:

```ini
[Animation]
transition = fade
transition_duration = 0.5

# Animation Group 1: FM Frequency (shows for 5 seconds)
[Line_TuneTo]
text=Tune to
fontsize=180
animation_group=fm_display
animation_duration=5

[Line_Frequency]
text=100.1 FM
fontsize=225
animation_group=fm_display
animation_duration=5

# Animation Group 2: QR Code (shows for 5 seconds)
[Line_QR]
image=/path/to/qr-code.png
scale=-1:450
x=(main_w-overlay_w)/2
y=(main_h-overlay_h)/2
animation_group=qr_display
animation_duration=5

# Static overlays (no animation_group = always visible)
[Line_Title]
text={title}
fontsize=60
```

**How it works**: The video will cycle between animation groups:
- 0-5s: Show FM frequency
- 5-10s: Show QR code
- 10-15s: Show FM frequency again
- (repeats for entire video duration)

Static overlays without `animation_group` remain visible throughout.

### Compression

Configure post-processing compression:

```ini
[Compression]
enabled = true
use_hardware = false  # Set to true for VideoToolbox (Mac)

# Software encoding options (use_hardware = false)
crf = 30  # 18-35, higher = more compression
preset = slow  # ultrafast, fast, medium, slow, slower, veryslow

# Hardware encoding options (use_hardware = true)
quality = 65  # 0-100, higher = better quality

audio_bitrate = 128k
output_directory = /path/to/compressed/output
```

**Note**: Hardware encoding is faster but less efficient (larger files for same quality).

## Usage

### Basic Usage

```bash
# Process all audio files
python3 video_creator.py

# Use custom config
python3 video_creator.py --config my_config.cfg

# Process specific songs
python3 video_creator.py --audio "song1.mp3" "song2.mp3"

# Enable compression
python3 video_creator.py --compress

# Verbose output
python3 video_creator.py --verbose

# Force regeneration (bypass cache)
python3 video_creator.py --force-regenerate
```

### Advanced Examples

```bash
# Process one song with custom config, compression, and verbose output
python3 video_creator.py -c custom.cfg -a "song.mp3" --compress -v

# Regenerate all videos with new settings
python3 video_creator.py --force-regenerate --compress
```

## How It Works

### Processing Pipeline

1. **Enhanced Background Creation**:
   - Loads base background video
   - Applies smart duration handling (loops/truncates to fit animation cycles)
   - Renders all text and image overlays with animation timing
   - Caches result with MD5 hash (only regenerates when config/source changes)

2. **Audio Muxing**:
   - Loops enhanced background infinitely
   - Adds MP3 audio track
   - Cuts to audio length using stream copy (fast, no re-encoding)

3. **Optional Compression**:
   - Re-encodes video with H.264 (software or hardware)
   - Adjustable quality/size tradeoff
   - Reports compression ratio

### Smart Duration Handling

The tool automatically handles mismatches between background video length and animation cycles:

- **Base video < cycle**: Loops video to fit at least one complete cycle
- **Base video > cycle**: Truncates to fit complete cycles (avoids partial animations)
- **Perfect match**: Uses as-is

Example: 45-second base video with 10-second animation cycle → truncates to 40 seconds (4 complete cycles)

### Caching System

Enhanced backgrounds are cached as `{base_video}__enh_{content_hash}.mp4`:
- Hash includes MP3 metadata and config settings
- Only regenerates when content or settings change
- Typical speedup: 2s vs 5-10s per video

## FFmpeg Expression Reference

### Text Positioning

- `w` - video width
- `h` - video height
- `text_w` - text width
- `text_h` - text height
- `(w-text_w)/2` - center horizontally
- `h-text_h-20` - 20px from bottom

### Image Positioning

- `main_w` - video width
- `main_h` - video height
- `overlay_w` - image width
- `overlay_h` - image height
- `(main_w-overlay_w)/2` - center horizontally
- `(main_h-overlay_h)/2` - center vertically

## Performance

**Typical processing time** (3-minute song on Apple Silicon):
- Enhanced background rendering: ~5-10 seconds (cached after first run)
- Audio muxing: ~2 seconds (stream copy, no re-encoding)
- Compression (optional): ~10-30 seconds (varies by preset/hardware)

**Hardware acceleration** (Mac with VideoToolbox):
- 3-5x faster compression
- Slightly larger files for same quality
- Use `use_hardware = true` in config

## Troubleshooting

### Text gets cut off at edges
- Add margins to x/y positioning: `x=(w-text_w)/2-10`
- Reduce shadow offset: `shadowx=5, shadowy=5`

### Animation groups not appearing
- Verify `animation_group` and `animation_duration` are set
- Check that duration values allow content to fit in base video
- Use `--verbose` to see animation schedule

### Large compressed file sizes
- Lower `crf` value (30-33 for more compression)
- Use slower preset (`slow` or `slower`)
- Disable hardware encoding (`use_hardware = false`)

### Cache not updating
- Use `--force-regenerate` to bypass cache
- Check that config file was actually saved

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License

GPL-3.0 License - See LICENSE file for details.

## Use Cases

- **Christmas Light Displays**: FM frequency info + QR codes for FPP/xLights shows
- **Digital Signage**: Rotating announcements with background videos
- **Music Videos**: Automated lyric videos with MP3 metadata
- **Event Displays**: Conference/wedding videos with custom overlays
