#!/usr/bin/env python3
"""
Compress MP4 videos for FPP playback.
Reduces file size while maintaining acceptable quality for TV display.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional


def compress_video(input_path: Path, output_path: Path, crf: int = 23, preset: str = 'medium') -> bool:
    """
    Compress a video file using H.264.

    Args:
        input_path: Path to input video
        output_path: Path to output video
        crf: Constant Rate Factor (18-28, lower = better quality, 23 is default)
        preset: Encoding speed preset (ultrafast, fast, medium, slow, veryslow)

    Returns:
        True if successful, False otherwise
    """
    command = [
        'ffmpeg',
        '-i', str(input_path),
        '-vcodec', 'libx264',
        '-crf', str(crf),
        '-preset', preset,
        '-acodec', 'aac',
        '-b:a', '128k',  # Audio bitrate (sufficient for FM broadcast quality)
        '-movflags', '+faststart',  # Enable progressive streaming
        '-y',  # Overwrite output file
        str(output_path)
    ]

    print(f"Compressing: {input_path.name}")
    print(f"  → {output_path}")

    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode == 0:
            # Calculate compression ratio
            original_size = input_path.stat().st_size
            compressed_size = output_path.stat().st_size
            ratio = (1 - compressed_size / original_size) * 100

            print(f"  ✓ Reduced by {ratio:.1f}% ({original_size/1024/1024:.1f}MB → {compressed_size/1024/1024:.1f}MB)")
            return True
        else:
            print(f"  ✗ Error: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Exception: {e}")
        return False


def main():
    """Compress all videos in output directory."""
    # Configuration
    input_dir = Path('output_test')  # Change this to your output directory
    output_dir = Path('output_compressed')

    # Compression settings
    # CRF: 18 = visually lossless, 23 = default (good), 26-28 = acceptable for TV/web
    # Based on existing compressed files: ~17-22% size reduction
    crf = 27
    # Preset: faster = bigger file, slower = smaller file (medium is good balance)
    preset = 'medium'

    # Create output directory if it doesn't exist
    output_dir.mkdir(exist_ok=True)

    # Find all MP4 files
    video_files = sorted(input_dir.glob('*.mp4'))

    if not video_files:
        print(f"No MP4 files found in {input_dir}")
        return

    print(f"Found {len(video_files)} videos to compress")
    print(f"Settings: CRF={crf}, Preset={preset}")
    print("=" * 70)

    successful = 0
    failed = 0
    skipped = 0

    for video_file in video_files:
        output_file = output_dir / video_file.name

        # Skip if output already exists
        if output_file.exists():
            print(f"Skipping (exists): {video_file.name}")
            skipped += 1
            continue

        if compress_video(video_file, output_file, crf, preset):
            successful += 1
        else:
            failed += 1

        print()

    print("=" * 70)
    print(f"Summary:")
    print(f"  ✓ Compressed: {successful}")
    print(f"  ✗ Failed: {failed}")
    print(f"  ⊘ Skipped: {skipped}")


if __name__ == '__main__':
    main()
