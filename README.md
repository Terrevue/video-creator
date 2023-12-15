
# MP4-MP3 Video Creator

## Overview
This project provides a Python script that automates the process of creating videos by overlaying text on MP4 files and syncing them with MP3 audio tracks. It is designed for users who need to pair visual content with audio tracks, such as for music videos, presentations, or digital signage.

## Features
- Automatically pairs MP4 video files with MP3 audio tracks.
- Supports text overlay on videos with customizable attributes.
- Configurable output settings, including video scale and output path.
- Option to replace or skip existing output files.
- Randomized selection of MP4 files to ensure varied usage.

## Installation

### Prerequisites
- Python 3.x
- FFmpeg
- TinyTag (Python library)

### Setup
1. Clone the repository:
   ```sh
   git clone https://github.com/Terrevue/video-creator.git
   cd video-creator
   ```

2. Install the required Python package:
   ```sh
   pip install tinytag
   ```

## Usage

### Configuration
1. Modify the `config.cfg` file to set the input paths, output settings, and text overlay attributes.

2. Structure of `config.cfg`:
   - `[Paths]`: Directory paths for MP3 and MP4 files.
   - `[Output]`: Output video settings, including scale and duration.
   - `[LineX]`: Text overlay settings where X is a unique identifier for each text line.

### Running the Script
Execute the script with the following command:
```sh
python3 video_creator.py
```

The script will process the MP3 files in the specified directory, overlay text on the chosen MP4 files, and synchronize them with the audio tracks.

## Contributing
Contributions to this project are welcome! Please fork the repository and submit a pull request with your changes.

## License
This project is licensed under the [MIT License](LICENSE).

## Acknowledgements
- FFmpeg: https://ffmpeg.org
- TinyTag: https://github.com/devsnd/tinytag


