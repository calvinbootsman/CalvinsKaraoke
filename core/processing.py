import shutil
from pathlib import Path

import demucs.separate
from libs.syncedlyrics.syncedlyrics import search
import torch
import yt_dlp

from config import DEMUX_MODEL, DEMUX_OUTPUT_ROOT
from core.file_utils import find_downloaded_audio, sanitize_title

import librosa
import numpy as np
from scipy.signal import medfilt
import pandas as pd
import torchcrepe

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

    lrc_text = search(song_title)
    song_path.write_text(lrc_text or "", encoding="utf-8")

def extract_audio_torchcrepe(audio_path: Path, song_dir: Path):
    # 1. Load Audio (CREPE models expect exactly 16kHz)
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    
    # Convert numpy array to PyTorch tensor and add a batch dimension: shape (1, T)
    audio_tensor = torch.tensor(y).unsqueeze(0)
    
    # Automatically use GPU if available, otherwise CPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    # 2. Extract Pitch using Torchcrepe
    # 10ms step size at 16kHz = 160 samples per hop
    hop_length = int(16000 / 100) 
    fmin = librosa.note_to_hz('E2')
    fmax = librosa.note_to_hz('G5')
    
    # Torchcrepe uses Viterbi decoding by default to prevent octave drops
    pitch, periodicity = torchcrepe.predict(
        audio_tensor,
        sample_rate=16000,
        hop_length=hop_length,
        fmin=fmin,
        fmax=fmax,
        model='full', # Use 'tiny' if 'full' is too slow
        batch_size=2048,
        device=device,
        return_periodicity=True # This gives us the confidence score
    )
    
    # Move tensors back to CPU, remove batch dimension, convert to numpy
    f0 = pitch.squeeze().cpu().numpy()
    confidence = periodicity.squeeze().cpu().numpy()
    
    # Generate time stamps
    times = librosa.frames_to_time(np.arange(len(f0)), sr=16000, hop_length=hop_length)
    
    # 3. Filter out unvoiced frames based on confidence
    confidence_threshold = 0.5 
    f0_filtered = np.where(confidence > confidence_threshold, f0, np.nan)
    
    # 4. Safe Smoothing
    f0_series = pd.Series(f0_filtered)
    smoothed_f0 = f0_series.rolling(window=15, min_periods=1, center=True).median().values
    
    # 5. Safe Quantization
    quantized_f0 = np.full_like(smoothed_f0, np.nan)
    valid_idx = ~np.isnan(smoothed_f0) 
    
    if np.any(valid_idx):
        midi_continuous = librosa.hz_to_midi(smoothed_f0[valid_idx])
        midi_quantized = np.round(midi_continuous)
        quantized_f0[valid_idx] = librosa.midi_to_hz(midi_quantized)
    
    # 6. Save Data
    combined = np.column_stack((times, quantized_f0, confidence))
    np.savetxt(
        song_dir / "pitch.csv", 
        combined, 
        delimiter=",", 
        header="time,frequency,confidence", 
        comments="",
        fmt='%f' 
    )
