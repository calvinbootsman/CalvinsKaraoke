import shutil
from pathlib import Path

import demucs.separate
import syncedlyrics
import torch
import yt_dlp

from config import DEMUX_MODEL, DEMUX_OUTPUT_ROOT
from core.file_utils import find_downloaded_audio, sanitize_title

import librosa
import numpy as np
from scipy.signal import medfilt


def get_song_title(url: str) -> str:
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return sanitize_title(info.get("title", "Unknown title"))


def download_audio(url: str, song_dir: Path) -> Path:
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(song_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    downloaded_audio = find_downloaded_audio(song_dir)
    if downloaded_audio is None:
        raise FileNotFoundError("No audio file found after download.")
    return downloaded_audio


def separate_audio_into_stems(audio_path: Path, song_dir: Path) -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    demucs.separate.main([
        "--device",
        device,
        "--mp3",
        "--two-stems",
        "vocals",
        "-n",
        DEMUX_MODEL,
        str(audio_path),
    ])

    demucs_song_dir = DEMUX_OUTPUT_ROOT / audio_path.stem
    vocals_src = demucs_song_dir / "vocals.mp3"
    no_vocals_src = demucs_song_dir / "no_vocals.mp3"

    if not vocals_src.exists() or not no_vocals_src.exists():
        raise FileNotFoundError("Demucs did not generate expected stem files.")

    shutil.copy2(vocals_src, song_dir / "vocals.mp3")
    shutil.copy2(no_vocals_src, song_dir / "no_vocals.mp3")


def get_lyrics(song_dir: Path, song_title: str) -> None:
    song_path = song_dir / "song.lrc"
    if song_path.exists():
        return

    lrc_text = syncedlyrics.search(song_title)
    song_path.write_text(lrc_text or "", encoding="utf-8")

def extract_audio(audio_path: Path, song_dir: Path):
    y, sr = librosa.load(audio_path, sr=None, mono=True)
    f0, voiced_flag, voiced_probs = librosa.pyin(y, 
                                             fmin=librosa.note_to_hz('C2'), 
                                             fmax=librosa.note_to_hz('C7'))
    
    times = librosa.times_like(f0, sr=sr)

    smoothed_f0 = medfilt(f0, kernel_size=15)

    midi_continuous = librosa.hz_to_midi(smoothed_f0)

    midi_quantized = np.round(midi_continuous)
    quantized_f0 = librosa.midi_to_hz(midi_quantized)

    combined = np.column_stack((times, quantized_f0, voiced_probs))
    np.savetxt(song_dir / "extracted_f0.csv", combined, delimiter=",", header="time,frequency,confidence", comments="")
