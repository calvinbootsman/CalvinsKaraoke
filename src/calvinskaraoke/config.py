from pathlib import Path

MUSIC_DIR = Path("./data/music")
DEMUX_MODEL = "mdx_extra"
DEMUX_OUTPUT_ROOT = Path("./data/separated") / DEMUX_MODEL
VALID_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".webm", ".wav", ".flac", ".ogg", ".aac"}
MAX_DEBUG_EVENTS = 40
DEBUG_ENABLED = False
