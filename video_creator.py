import ffmpeg
import configparser
import os
import random
import hashlib
import shutil
import subprocess
import argparse
from pathlib import Path
from tinytag import TinyTag
import tempfile


def write_text_to_tempfile(text):
    """Writes dynamic text to a temporary file for use with FFmpeg."""
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmpfile:
        tmpfile.write(text)
        return tmpfile.name


def parse_metadata(mp3_path):
    """Extracts metadata from an MP3 file using TinyTag."""
    tag = TinyTag.get(mp3_path)
    return {key: getattr(tag, key, "") for key in dir(tag) if not key.startswith("_")}


def get_video_duration(video_path):
    """Get duration of a video file in seconds."""
    probe = ffmpeg.probe(video_path)
    return float(probe['format']['duration'])


def parse_animation_groups(config):
    """
    Parse animation groups from config.
    Returns list of groups with their durations.
    """
    groups = {}

    for section in config.sections():
        if section.startswith('Line'):
            line = dict(config[section])
            if 'animation_group' in line:
                group_name = line['animation_group']
                duration = float(line.get('animation_duration', 5))

                if group_name not in groups:
                    groups[group_name] = {
                        'name': group_name,
                        'duration': duration,
                        'lines': []
                    }
                elif groups[group_name]['duration'] != duration:
                    raise ValueError(
                        f"Animation group '{group_name}' has inconsistent durations: "
                        f"{groups[group_name]['duration']}s vs {duration}s"
                    )

    return list(groups.values())


def calculate_render_strategy(base_video_path, animation_groups):
    """
    Determine optimal rendering strategy based on base video length and animations.

    Returns:
        duration: Target duration for enhanced background
        loop_base: Whether to loop the base video during rendering
        truncate_amount: Seconds to truncate from base video (0 if none)
    """
    base_duration = get_video_duration(base_video_path)

    if not animation_groups:
        # No animations - use base video as-is
        return base_duration, False, 0

    # Calculate animation cycle duration
    cycle_duration = sum(g['duration'] for g in animation_groups)

    # Decision tree:
    if base_duration < cycle_duration:
        # Base video too short - loop it to fit at least one full animation cycle
        print(f"  Base video ({base_duration:.1f}s) < animation cycle ({cycle_duration:.1f}s)")
        print(f"  → Looping base video to {cycle_duration:.1f}s")
        return cycle_duration, True, 0

    elif base_duration > cycle_duration:
        # Base video longer - fit complete animation cycles and truncate remainder
        full_cycles = int(base_duration // cycle_duration)
        target_duration = full_cycles * cycle_duration
        truncated = base_duration - target_duration

        if truncated > 0.1:  # Only report if significant truncation
            print(f"  Base video ({base_duration:.1f}s) → fitting {full_cycles} cycle(s) = {target_duration:.1f}s")
            print(f"  → Truncating last {truncated:.1f}s to avoid partial animation")

        return target_duration, False, truncated

    else:
        # Perfect match!
        print(f"  Base video ({base_duration:.1f}s) = animation cycle ({cycle_duration:.1f}s) ✓")
        return base_duration, False, 0


def build_enable_expression(time_ranges, transition_type='cut', transition_duration=0.5):
    """
    Build FFmpeg enable expression for time ranges with optional transitions.
    time_ranges: [(start, end), (start, end), ...]
    transition_type: 'cut', 'fade'
    transition_duration: seconds for fade in/out
    """
    if not time_ranges:
        return None

    if transition_type == 'cut':
        # Simple on/off
        conditions = [f"between(t,{start},{end})" for start, end in time_ranges]
        return '+'.join(conditions)

    elif transition_type == 'fade':
        # Always visible during time ranges, handled via alpha
        conditions = [f"between(t,{start},{end})" for start, end in time_ranges]
        return '+'.join(conditions)

    return '+'.join([f"between(t,{start},{end})" for start, end in time_ranges])


def build_alpha_expression(time_ranges, transition_duration=0.5):
    """
    Build alpha fade expression for smooth transitions.
    Returns alpha value (0.0 to 1.0) based on time.
    """
    if not time_ranges or transition_duration <= 0:
        return '1'  # Always opaque

    parts = []
    for start, end in time_ranges:
        fade_in_end = start + transition_duration
        fade_out_start = end - transition_duration

        # This segment's alpha calculation
        segment = (
            f"if(between(t,{start},{fade_in_end}),"
            f"(t-{start})/{transition_duration},"  # Fade in
            f"if(between(t,{fade_in_end},{fade_out_start}),"
            f"1,"  # Full opacity
            f"if(between(t,{fade_out_start},{end}),"
            f"({end}-t)/{transition_duration},"  # Fade out
            f"0)))"  # Invisible
        )
        parts.append(segment)

    # Combine all segments with max() to handle any overlaps
    if len(parts) == 1:
        return parts[0]
    else:
        # Build nested max() calls
        result = parts[0]
        for part in parts[1:]:
            result = f"max({result},{part})"
        return result


def calculate_animation_schedule(animation_groups, total_duration):
    """
    Calculate when each animation group should be visible.
    Returns: {group_name: [(start, end), (start, end), ...]}
    """
    if not animation_groups:
        return {}

    schedule = {group['name']: [] for group in animation_groups}

    current_time = 0
    while current_time < total_duration:
        for group in animation_groups:
            start = current_time
            end = min(current_time + group['duration'], total_duration)

            if end > start:  # Only add if there's actual duration
                schedule[group['name']].append((start, end))

            current_time = end

            if current_time >= total_duration:
                break

    return schedule


def parse_config_all_lines(config, metadata):
    """
    Parse ALL lines from config (both static and dynamic).
    Resolves metadata placeholders for dynamic lines.

    Returns: (text_filters, overlay_filters)
    """
    text_filters = []
    overlay_filters = []

    for section in config.sections():
        if section.startswith("Line"):
            attrs = dict(config[section])

            if "text" in attrs:
                # Resolve metadata placeholders
                parsed_text = attrs["text"].format(**metadata)
                textfile_path = write_text_to_tempfile(parsed_text)
                attrs["textfile"] = textfile_path
                del attrs["text"]
                text_filters.append(attrs)

            elif "image" in attrs:
                overlay_filters.append(attrs)

    return text_filters, overlay_filters


def create_enhanced_background(base_video_path, config, metadata, output_scale):
    """
    Apply ALL overlays to base video with animation support.
    Returns: (temp_file_path, duration)
    """
    # Parse animation groups
    animation_groups = parse_animation_groups(config)

    # Get transition settings
    transition_type = config.get('Animation', 'transition', fallback='cut')
    transition_duration = float(config.get('Animation', 'transition_duration', fallback=0.5))

    # Determine render strategy
    target_duration, loop_base, truncate_amount = calculate_render_strategy(
        base_video_path, animation_groups
    )

    # Parse ALL filters (resolving metadata for this song)
    text_filters, overlay_filters = parse_config_all_lines(config, metadata)

    # Build base video stream
    if loop_base:
        # Loop base video to meet animation cycle duration
        base_duration = get_video_duration(base_video_path)
        loop_count = int(target_duration / base_duration) + 1
        video_stream = ffmpeg.input(base_video_path, stream_loop=loop_count - 1)
        video_stream = video_stream.trim(duration=target_duration).setpts('PTS-STARTPTS')
    elif truncate_amount > 0:
        # Truncate to fit complete animation cycles
        video_stream = ffmpeg.input(base_video_path)
        video_stream = video_stream.trim(duration=target_duration).setpts('PTS-STARTPTS')
    else:
        # Perfect fit or no animations
        video_stream = ffmpeg.input(base_video_path)

    # Calculate animation schedule
    if animation_groups:
        schedule = calculate_animation_schedule(animation_groups, target_duration)

        print(f"  Animation schedule:")
        for group_name, time_ranges in schedule.items():
            print(f"    {group_name}: {len(time_ranges)} appearance(s)")

        # Apply enable expressions to filters based on animation groups
        for text_filter in text_filters:
            group = text_filter.get('animation_group')
            if group and group in schedule:
                text_filter['enable'] = build_enable_expression(
                    schedule[group], transition_type, transition_duration
                )

                # Add alpha fade for smooth transitions
                if transition_type == 'fade':
                    text_filter['alpha'] = build_alpha_expression(
                        schedule[group], transition_duration
                    )

                # Remove animation config keys (not FFmpeg params)
                text_filter.pop('animation_group', None)
                text_filter.pop('animation_duration', None)

        for overlay_filter in overlay_filters:
            group = overlay_filter.get('animation_group')
            if group and group in schedule:
                overlay_filter['enable_expr'] = build_enable_expression(
                    schedule[group], transition_type, transition_duration
                )

                # Store alpha expression for overlays (applied later)
                if transition_type == 'fade':
                    overlay_filter['alpha_expr'] = build_alpha_expression(
                        schedule[group], transition_duration
                    )

                # Remove animation config keys
                overlay_filter.pop('animation_group', None)
                overlay_filter.pop('animation_duration', None)

    # Apply all text overlays
    for text_filter in text_filters:
        # Remove animation keys that aren't FFmpeg params
        text_filter.pop('animation_group', None)
        text_filter.pop('animation_duration', None)
        # Add fix_bounds to prevent text clipping
        text_filter['fix_bounds'] = 'true'
        video_stream = video_stream.drawtext(**text_filter)

    # Apply all image overlays
    for overlay in overlay_filters:
        overlay_stream = ffmpeg.input(overlay["image"])

        # Handle scale
        if "scale" in overlay:
            scale_parts = overlay["scale"].split(":")
            width = scale_parts[0]
            height = scale_parts[1] if len(scale_parts) > 1 else -1
            overlay_stream = overlay_stream.filter("scale", width, height)

        # Handle rotate
        if "rotate" in overlay:
            overlay_stream = overlay_stream.filter("rotate", overlay["rotate"])

        # Build overlay params
        overlay_params = {k: overlay[k] for k in ["x", "y"] if k in overlay}

        # Add enable expression if present
        if 'enable_expr' in overlay:
            overlay_params['enable'] = overlay['enable_expr']

        # Add alpha fade if present (use overlay filter's alpha parameter)
        if 'alpha_expr' in overlay:
            overlay_params['format'] = 'yuv420'  # Ensure compatible format
            # Note: overlay filter doesn't support expression-based alpha
            # We'll use enable only for now (cut transitions for images)

        # Remove animation keys
        overlay.pop('animation_group', None)
        overlay.pop('animation_duration', None)
        overlay.pop('enable_expr', None)
        overlay.pop('alpha_expr', None)

        # Add overlay to video
        video_stream = ffmpeg.overlay(video_stream, overlay_stream, **overlay_params)

    # Apply output scaling
    if output_scale:
        scale_parts = output_scale.split(":")
        width = int(scale_parts[0]) if scale_parts[0].isdigit() else -1
        height = int(scale_parts[1]) if len(scale_parts) > 1 and scale_parts[1].isdigit() else -1
        video_stream = video_stream.filter("scale", width, height)

    # Render to temp file (no audio)
    temp_output = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name

    output = video_stream.output(
        temp_output,
        vcodec='libx264',
        crf=23,
        preset='medium',
        **{'an': None}  # No audio
    ).global_args('-v', 'error')

    output.run(overwrite_output=True)

    return temp_output, target_duration


def get_enhanced_bg_path(base_bg_filename, audio_filename, cache_dir='bg_enhanced'):
    """
    Generate deterministic filename for enhanced background.
    Format: {base_bg_name}__enh_{song_hash}.mp4
    """
    Path(cache_dir).mkdir(exist_ok=True)

    # Use hash of song filename to create unique identifier
    song_hash = hashlib.md5(audio_filename.encode()).hexdigest()[:7]

    base_name = Path(base_bg_filename).stem
    enhanced_name = f"{base_name}__enh_{song_hash}.mp4"

    return Path(cache_dir) / enhanced_name


def should_regenerate_enhanced_bg(enhanced_bg_path, base_bg_path, config_path):
    """
    Check if enhanced background needs regeneration.
    """
    if not enhanced_bg_path.exists():
        return True

    enhanced_mtime = enhanced_bg_path.stat().st_mtime
    base_mtime = Path(base_bg_path).stat().st_mtime
    config_mtime = Path(config_path).stat().st_mtime

    if base_mtime > enhanced_mtime:
        print(f"  Base video updated, regenerating...")
        return True

    if config_mtime > enhanced_mtime:
        print(f"  Config changed, regenerating...")
        return True

    return False


def loop_with_audio(enhanced_bg_video, audio_file, output_file):
    """
    Loop the enhanced background video and add audio.
    Fast operation using stream copy.
    """
    cmd = [
        'ffmpeg',
        '-stream_loop', '-1',  # Loop video infinitely
        '-i', enhanced_bg_video,
        '-i', audio_file,
        '-map', '0:v',  # Video from looped background
        '-map', '1:a',  # Audio from MP3
        '-c:v', 'copy',  # NO RE-ENCODING! Just copy
        '-c:a', 'aac',
        '-b:a', '128k',
        '-shortest',  # Stop when audio ends
        '-y',
        output_file,
        '-v', 'error'
    ]

    subprocess.run(cmd, check=True)


def compress_video(input_path, output_path, crf=27, preset='medium', audio_bitrate='128k', use_hardware=False, quality=75):
    """
    Compress a video file using H.264.

    Args:
        input_path: Path to input video
        output_path: Path to output video
        crf: Constant Rate Factor for software encoding (18-28)
        preset: Encoding speed preset for software encoding
        audio_bitrate: Audio bitrate
        use_hardware: Use hardware encoding (VideoToolbox on Mac)
        quality: Quality for hardware encoding (0-100, higher = better)

    Returns: True if successful, compression ratio, original size, compressed size
    """
    if use_hardware:
        # Hardware encoding with VideoToolbox (Mac)
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vcodec', 'h264_videotoolbox',
            '-q:v', str(quality),  # Quality scale for VideoToolbox
            '-acodec', 'aac',
            '-b:a', audio_bitrate,
            '-movflags', '+faststart',
            '-y',
            output_path,
            '-v', 'error'
        ]
    else:
        # Software encoding with libx264
        cmd = [
            'ffmpeg',
            '-i', input_path,
            '-vcodec', 'libx264',
            '-crf', str(crf),
            '-preset', preset,
            '-acodec', 'aac',
            '-b:a', audio_bitrate,
            '-movflags', '+faststart',
            '-y',
            output_path,
            '-v', 'error'
        ]

    try:
        subprocess.run(cmd, check=True)

        # Calculate compression ratio
        original_size = Path(input_path).stat().st_size
        compressed_size = Path(output_path).stat().st_size
        ratio = (1 - compressed_size / original_size) * 100

        return True, ratio, original_size, compressed_size
    except subprocess.CalledProcessError as e:
        return False, 0, 0, 0


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Video Creator - Generate videos with animations for FPP displays',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all songs with default config
  python video_creator.py

  # Use custom config file
  python video_creator.py --config my_config.cfg

  # Process specific song(s)
  python video_creator.py --audio "Turn Up.mp3" "chipmunk.mp3"

  # Force regenerate cached backgrounds
  python video_creator.py --force-regenerate

  # Enable verbose output
  python video_creator.py --verbose

  # Compress output videos
  python video_creator.py --compress
        """
    )
    parser.add_argument(
        '--config', '-c',
        default='video_creator.cfg',
        help='Config file to use (default: video_creator.cfg)'
    )
    parser.add_argument(
        '--audio', '-a',
        nargs='+',
        help='Specific audio file(s) to process (default: all MP3s in directory)'
    )
    parser.add_argument(
        '--force-regenerate', '-f',
        action='store_true',
        help='Force regeneration of enhanced backgrounds (ignore cache)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose debug output'
    )
    parser.add_argument(
        '--compress',
        action='store_true',
        help='Compress output videos after generation'
    )

    args = parser.parse_args()

    # Load configuration
    config_path = args.config
    if not os.path.exists(config_path):
        print(f"Error: Config file '{config_path}' not found")
        return 1

    config = configparser.ConfigParser()
    config.read(config_path)

    if args.verbose:
        print(f"Using config: {config_path}")

    # Get paths from config
    paths = {
        "video_dir": config["Paths"]["mp4_directory"],
        "audio_dir": config["Paths"]["mp3_directory"],
        "output_dir": config["Output"]["output_directory"],
    }

    output_scale = config["Output"].get("scale", None)
    output_exists_action = config["Output"].get("output_exists", "overwrite").lower()

    # Get compression settings
    compress_enabled = args.compress or config.getboolean('Compression', 'enabled', fallback=False)
    compress_use_hardware = config.getboolean('Compression', 'use_hardware', fallback=False)
    compress_crf = int(config.get('Compression', 'crf', fallback=27))
    compress_quality = int(config.get('Compression', 'quality', fallback=75))
    compress_preset = config.get('Compression', 'preset', fallback='medium')
    compress_audio_bitrate = config.get('Compression', 'audio_bitrate', fallback='128k')
    compress_dir = config.get('Compression', 'output_directory', fallback=None)

    # Find video and audio files
    video_files = [f for f in os.listdir(paths["video_dir"]) if f.endswith(".mp4")]

    # Filter audio files if specific ones requested
    if args.audio:
        # Handle both full paths and just filenames
        requested_files = [os.path.basename(f) for f in args.audio]
        all_audio_files = [f for f in os.listdir(paths["audio_dir"]) if f.endswith(".mp3")]
        audio_files = [f for f in all_audio_files if f in requested_files]

        if not audio_files:
            print(f"Error: None of the requested audio files found in {paths['audio_dir']}")
            print(f"Requested: {requested_files}")
            return 1

        if args.verbose:
            print(f"Processing {len(audio_files)} of {len(all_audio_files)} audio files")
    else:
        audio_files = [f for f in os.listdir(paths["audio_dir"]) if f.endswith(".mp3")]

    if not video_files or not audio_files:
        raise FileNotFoundError("No MP4 or MP3 files found in the specified directories.")

    print(f"\nFound {len(video_files)} background video(s) and {len(audio_files)} audio file(s)")
    if compress_enabled:
        if compress_use_hardware:
            print(f"Compression enabled: Hardware encoding (VideoToolbox), Quality={compress_quality}")
        else:
            print(f"Compression enabled: Software encoding (libx264), CRF={compress_crf}, Preset={compress_preset}")
    print("="*70)

    for audio_file in audio_files:
        print(f"\n{'='*70}")
        print(f"Processing: {audio_file}")
        print('='*70)

        # Select random base bg video
        base_bg_filename = random.choice(video_files)
        base_bg_video = os.path.join(paths["video_dir"], base_bg_filename)
        audio_file_path = os.path.join(paths["audio_dir"], audio_file)

        print(f"Selected background: {base_bg_filename}")

        # Output path
        audio_base_name = os.path.splitext(audio_file)[0]
        output_file = os.path.join(paths["output_dir"], f"{audio_base_name}.mp4")

        # Check if output exists
        if os.path.exists(output_file):
            if output_exists_action == "skip":
                print(f"✓ Output exists, skipping...")
                continue
            elif output_exists_action == "overwrite":
                print(f"⚠ Output exists, will overwrite...")

        # Get metadata for this song
        metadata = parse_metadata(audio_file_path)

        # Get cached enhanced background path
        enhanced_bg_path = get_enhanced_bg_path(base_bg_filename, audio_file)

        # Check if we need to regenerate enhanced background
        force_regen = args.force_regenerate
        if force_regen:
            if args.verbose:
                print(f"  Force regenerate enabled")

        if force_regen or should_regenerate_enhanced_bg(enhanced_bg_path, base_bg_video, config_path):
            print(f"\nCreating enhanced background...")
            temp_enhanced_bg, enhanced_duration = create_enhanced_background(
                base_bg_video,
                config,
                metadata,
                output_scale
            )

            # Move to cache
            shutil.move(temp_enhanced_bg, enhanced_bg_path)
            print(f"✓ Enhanced background ready ({enhanced_duration:.1f}s) → {enhanced_bg_path.name}")
        else:
            print(f"✓ Using cached enhanced background: {enhanced_bg_path.name}")

        # Loop enhanced background + add audio
        print(f"\nLooping background with audio...")
        loop_with_audio(str(enhanced_bg_path), audio_file_path, output_file)

        print(f"✓ Complete: {output_file}")

        # Compress if enabled
        if compress_enabled:
            print(f"\nCompressing video...")

            # Determine compressed output path
            if compress_dir:
                Path(compress_dir).mkdir(exist_ok=True)
                compressed_output = os.path.join(compress_dir, f"{audio_base_name}.mp4")
            else:
                # Same directory, different filename
                compressed_output = os.path.join(paths["output_dir"], f"{audio_base_name}_compressed.mp4")

            success, ratio, orig_size, comp_size = compress_video(
                output_file,
                compressed_output,
                compress_crf,
                compress_preset,
                compress_audio_bitrate,
                compress_use_hardware,
                compress_quality
            )

            if success:
                print(f"✓ Compressed: {compressed_output}")
                print(f"  Size reduction: {ratio:.1f}% ({orig_size/1024/1024:.1f}MB → {comp_size/1024/1024:.1f}MB)")
            else:
                print(f"✗ Compression failed")

        print()

    print("="*70)
    print("✓ All videos processed successfully!")
    print("="*70)

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
