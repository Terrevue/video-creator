import configparser
import os
import subprocess
import random
from tinytag import TinyTag
import tempfile


def write_text_to_tempfile(text):
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as tmpfile:
        tmpfile.write(text)
        return tmpfile.name


def get_script_name():
    return os.path.splitext(os.path.basename(__file__))[0]


def get_audio_length(mp3_path):
    audio = TinyTag.get(mp3_path)
    return audio.duration


def get_drawtext_filter(attrs, metadata, temp_files):
    drawtext_parts = []
    for key, value in attrs.items():
        if key == "text":
            parsed_text = value.format(**metadata)
            textfile_path = write_text_to_tempfile(parsed_text)
            temp_files.append(textfile_path)
            drawtext_parts.append(f"textfile='{textfile_path}'")
        else:
            drawtext_parts.append(f"{key}='{value}'")
    return "drawtext=" + ":".join(drawtext_parts)


config = configparser.ConfigParser()
config_path = f"{get_script_name()}.cfg"
config.read(config_path)

# Paths and output configurations
mp3_directory = config["Paths"]["mp3_directory"]
mp4_directory = config["Paths"]["mp4_directory"]
mp4_prefix = config["Paths"].get("mp4_prefix", "")
output_prefix = config["Output"].get("file_prefix", "")
output_length = config["Output"]["output_length"]
output_directory = config["Output"].get("output_directory", mp3_directory)
output_exists_behavior = config["Output"].get("output_exists", "overwrite")

# Create the output directory if it doesn't exist
if not os.path.exists(output_directory):
    os.makedirs(output_directory)

scale = config["Output"].get(
    "scale", "1280:720"
)  # Default to 1280x720 if not specified

print(f"Reading configuration from {config_path}")
print(f"MP3 directory: {mp3_directory}")
print(f"MP4 directory: {mp4_directory}")

# Processing files
mp3_files = [f for f in os.listdir(mp3_directory) if f.endswith(".mp3")]
mp4_files = [
    f
    for f in os.listdir(mp4_directory)
    if f.endswith(".mp4") and f.startswith(mp4_prefix)
]

print(f"Found {len(mp3_files)} MP3 files and {len(mp4_files)} MP4 files")

temp_files = []

# Shuffle the MP4 files list
random.shuffle(mp4_files)
mp4_index = 0

for mp3_file in mp3_files:
    mp3_path = os.path.join(mp3_directory, mp3_file)
    audio_length = (
        get_audio_length(mp3_path) if output_length == "mp3" else output_length
    )
    # selected_mp4 = random.choice(mp4_files) if mp4_files else None

    # Select an MP4 file
    selected_mp4 = mp4_files[mp4_index] if mp4_files else None
    mp4_index += 1

    print(f"Processing {mp3_file} with {selected_mp4}")

    # If we've used all MP4 files, reshuffle and reset the index
    if mp4_index >= len(mp4_files):
        random.shuffle(mp4_files)
        mp4_index = 0

    if selected_mp4:
        input_path = os.path.join(mp4_directory, selected_mp4)
        output_filename = f"{output_prefix}{os.path.splitext(mp3_file)[0]}.mp4"
        output_path = os.path.join(output_directory, output_filename)

        # Check if the output file already exists
        if os.path.exists(output_path):
            if output_exists_behavior == "skip":
                print(f"Skipping {mp3_file} as output file already exists.")
                continue  # Skip this file and move to the next one

        tag = TinyTag.get(mp3_path)
        metadata = {
            key: getattr(tag, key, "") for key in dir(tag) if not key.startswith("_")
        }

        ffmpeg_filters = [
            get_drawtext_filter(
                {attr: config[section][attr] for attr in config[section]},
                metadata,
                temp_files,
            )
            for section in config.sections()
            if section.startswith("Line")
        ]

        ffmpeg_vf_option = f"scale={scale}, " + ", ".join(ffmpeg_filters)

        command = [
            "ffmpeg",
            "-y",
            "-v",
            "warning",
            "-stats",
            "-stream_loop",
            "-1",
            "-i",
            input_path,  # MP4 file path
        ]

        if output_length == "mp3":
            command.extend(
                ["-i", mp3_path, "-c:a", "aac"]
            )  # Add MP3 file path and audio codec

        command.extend(
            ["-vf", ffmpeg_vf_option, "-c:v", "libx264", "-t", str(audio_length)]
        )

        if output_length == "mp3":
            command.append("-shortest")
            # Add the following commands to ensure the mp3 audio is mapped "-map", "0:v:0", "-map", "1:a:0"
            command.extend(["-map", "0:v:0", "-map", "1:a:0"])

        command.append(output_path)

        # print(" ".join(command))

        subprocess.run(command)
        print(f"Processed {mp3_file}, output to {output_path}")

        # Clean up temporary files
        for file_path in temp_files:
            os.remove(file_path)

        temp_files.clear()
