import shutil
import subprocess
import sys
import re
from pathlib import Path
from typing import Callable, Optional

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


def download_audio(url: str, song_dir: Path, progress_cb: Optional[Callable[[str, Optional[float]], None]] = None) -> Path:
    def hook(d):
        if progress_cb and d['status'] == 'downloading':
            try:
                downloaded = d.get('downloaded_bytes', 0)
                total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
                if total > 0:
                    pct = downloaded / total
                    progress_cb(f"Downloading... {d.get('_percent_str', '').strip()}", pct)
            except Exception:
                pass

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(song_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [hook] if progress_cb else [],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    downloaded_audio = find_downloaded_audio(song_dir)
    if downloaded_audio is None:
        raise FileNotFoundError("No audio file found after download.")
    return downloaded_audio


def separate_audio_into_stems(audio_path: Path, song_dir: Path, progress_cb: Optional[Callable[[str, Optional[float]], None]] = None) -> None:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    demucs_base_output_dir = DEMUX_OUTPUT_ROOT.parent
    cmd = [
        sys.executable,
        "-m",
        "demucs.separate",
        "--device",
        device,
        "--out",
        str(demucs_base_output_dir),
        "--mp3",
        "--two-stems",
        "vocals",
        "-n",
        DEMUX_MODEL,
        str(audio_path),
    ]

    if progress_cb:
        progress_cb("Starting stem separation...", 0.0)

    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding="utf-8")
    if process.stderr:
        expected_passes = 1
        current_pass = 0
        last_pct = 0.0

        for line in process.stderr:
            if progress_cb:
                m_bag = re.search(r'bag of (\d+) models', line)
                if m_bag:
                    expected_passes = int(m_bag.group(1))

                match = re.search(r'(\d+)%', line)
                if match:
                    pct = int(match.group(1)) / 100.0

                    if pct < last_pct and last_pct > 0.8:
                        current_pass += 1
                    last_pct = pct

                    actual_expected = max(expected_passes, current_pass + 1)
                    overall_progress = min(1.0, (current_pass + pct) / actual_expected)

                    progress_cb(
                        f"Separating stems (pass {current_pass+1}/{actual_expected})... {match.group(1)}%",
                        overall_progress
                    )

    process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"Demucs process failed with return code {process.returncode}")

    candidate_dirs = [
        DEMUX_OUTPUT_ROOT / audio_path.stem,
        Path("separated") / DEMUX_MODEL / audio_path.stem,  # Legacy/default Demucs output path.
    ]
    vocals_src = None
    no_vocals_src = None

    for candidate_dir in candidate_dirs:
        candidate_vocals = candidate_dir / "vocals.mp3"
        candidate_no_vocals = candidate_dir / "no_vocals.mp3"
        if candidate_vocals.exists() and candidate_no_vocals.exists():
            vocals_src = candidate_vocals
            no_vocals_src = candidate_no_vocals
            break

    if vocals_src is None or no_vocals_src is None:
        searched = "\n".join(str(path) for path in candidate_dirs)
        raise FileNotFoundError(
            "Demucs did not generate expected stem files. Searched:\n"
            f"{searched}"
        )

    shutil.copy2(vocals_src, song_dir / "vocals.mp3")
    shutil.copy2(no_vocals_src, song_dir / "no_vocals.mp3")


def get_lyrics(song_dir: Path, song_title: str, progress_cb: Optional[Callable[[str, Optional[float]], None]] = None) -> None:
    song_path = song_dir / "song.lrc"
    if song_path.exists():
        return

    vocals_path = song_dir / "vocals.mp3"
    whisper_text = ""
    whisper_segments = []

    if vocals_path.exists():
        if progress_cb:
            progress_cb("Loading Whisper model...", 0.1)
        import whisper
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = whisper.load_model("base", device=device)
        
        if progress_cb:
            progress_cb("Transcribing vocals to verify lyrics...", 0.3)
        result = model.transcribe(str(vocals_path), language="en")
        whisper_text = result["text"].lower()
        whisper_segments = result["segments"]

    from libs.syncedlyrics.syncedlyrics.providers import Musixmatch, Lrclib, NetEase, Megalobiz, Genius
    providers = [Musixmatch(), Lrclib(), NetEase(), Megalobiz(), Genius()]
    best_lrc = None
    best_ratio = -1.0
    
    import re
    import difflib
    
    for i, provider in enumerate(providers):
        if progress_cb:
            progress_cb(f"Checking provider {provider.__class__.__name__}...", 0.5 + (0.1 * min(i, 4)))
        
        try:
            lrc_result = provider.get_lrc(song_title)
            if not lrc_result:
                continue
                
            from libs.syncedlyrics.syncedlyrics.utils import TargetType
            lrc_text = str(lrc_result)
            if hasattr(lrc_result, 'to_str'):
                lrc_text = lrc_result.to_str(TargetType.PREFER_SYNCED)
            elif isinstance(lrc_result, str):
                lrc_text = lrc_result

            if not lrc_text:
                continue

            if not re.search(r"[\[<]\d+:\d+(?:\.\d+)?[\]>]", lrc_text):
                continue

            lrc_plain = re.sub(r"[\[<]\d+:\d+(?:\.\d+)?[\]>]", "", lrc_text)
            lrc_plain = " ".join(lrc_plain.split()).lower()
            
            if not whisper_text:
                best_lrc = lrc_text
                break
                
            whisper_plain = " ".join(whisper_text.split())
            ratio = difflib.SequenceMatcher(None, lrc_plain, whisper_plain).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_lrc = lrc_text
                with open("lyrics_debug.txt", "a", encoding="utf-8") as f:
                    f.write(f"Provider: {provider.__class__.__name__} | Global Ratio: {ratio}\n")
                
            if ratio > 0.85:
                break
                
        except Exception as e:
            continue
            
    if best_lrc:
        with open("lyrics_debug.txt", "a", encoding="utf-8") as f:
            f.write(f"\nEvaluating offset. Best global textual ratio was: {best_ratio}\n")
            
        if whisper_segments:
            lrc_entries = []
            for line in best_lrc.splitlines():
                matches = list(re.finditer(r"[\[<](\d+):(\d+(?:\.\d+)?)[\]>]", line))
                if matches:
                    text = line[matches[-1].end():].strip()
                    for m in matches:
                        t_sec = int(m.group(1)) * 60 + float(m.group(2))
                        lrc_entries.append((t_sec, text))
            
            best_overall_ratio = 0
            offset = None
            
            for wh_seg in whisper_segments:
                wh_text = re.sub(r'[^a-z ]', '', wh_seg["text"].lower()).strip()
                wh_words = wh_text.split()
                if len(wh_words) < 3: 
                    continue
                
                for lrc_time, lrc_text in lrc_entries:
                    l_text = re.sub(r'[^a-z ]', '', lrc_text.lower()).strip()
                    if len(l_text.split()) < 3: 
                        continue
                        
                    if l_text in wh_text or wh_text in l_text:
                        r = 1.0
                    else:
                        r = difflib.SequenceMatcher(None, wh_text, l_text).ratio()
                        
                    if r > best_overall_ratio:
                        best_overall_ratio = r
                        offset = wh_seg["start"] - lrc_time
                        
            with open("lyrics_debug.txt", "a", encoding="utf-8") as f:
                f.write(f"Line match check | Best Line Ratio: {best_overall_ratio} | Computed Offset: {offset}\n")
                        
            if offset is not None and abs(offset) > 1.0 and best_overall_ratio >= 0.4:
                if progress_cb:
                    progress_cb(f"Applying auto-offset ({offset:.2f}s)...", 0.9)
                
                def shift_match(m):
                    open_bracket = m.group(1)
                    mm = int(m.group(2))
                    ss = float(m.group(3))
                    close_bracket = m.group(4)
                    time_sec = (mm * 60) + ss + offset
                    time_sec = max(0.0, time_sec)
                    new_mm = int(time_sec // 60)
                    new_ss = time_sec % 60
                    return f"{open_bracket}{new_mm:02d}:{new_ss:05.2f}{close_bracket}"
                    
                best_lrc = re.sub(r"([\[<])(\d+):(\d+(?:\.\d+)?)([\]>])", shift_match, best_lrc)
            else:
                with open("lyrics_debug.txt", "a", encoding="utf-8") as f:
                    f.write("Offset NOT applied (ratio < 0.4 or drift < 1.0s).\n")

        song_path.write_text(best_lrc or "", encoding="utf-8")

def extract_audio_torchcrepe(audio_path: Path, song_dir: Path, progress_cb: Optional[Callable[[str, Optional[float]], None]] = None):
    if progress_cb:
        progress_cb("Loading audio (CREPE models)...", 0.05)
    # 1. Load Audio (CREPE models expect exactly 16kHz)
    y, sr = librosa.load(audio_path, sr=16000, mono=True)
    
    # Convert numpy array to PyTorch tensor and add a batch dimension: shape (1, T)
    audio_tensor = torch.tensor(y).unsqueeze(0)
    
    # Automatically use GPU if available, otherwise CPU
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    
    if progress_cb:
        progress_cb("Extracting pitch using torchcrepe...", 0.3)
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
    
    # Generator chunks for memory and progress? For now, we just pass since predicting takes the bulk, 
    # but since it's viterbi decoding it doesn't give a callback easily. We just output a mid-point task update.
    
    # Move tensors back to CPU, remove batch dimension, convert to numpy
    f0 = pitch.squeeze().cpu().numpy()
    confidence = periodicity.squeeze().cpu().numpy()
    
    # Generate time stamps
    times = librosa.frames_to_time(np.arange(len(f0)), sr=16000, hop_length=hop_length)
    
    if progress_cb:
        progress_cb("Filtering unvoiced frames...", 0.8)
    # 3. Filter out unvoiced frames based on confidence
    confidence_threshold = 0.5 
    f0_filtered = np.where(confidence > confidence_threshold, f0, np.nan)
    
    if progress_cb:
        progress_cb("Applying safe smoothing...", 0.85)
    # 4. Safe Smoothing
    f0_series = pd.Series(f0_filtered)
    smoothed_f0 = f0_series.rolling(window=15, min_periods=1, center=True).median().values
    
    # 5. Safe Quantization
    if progress_cb:
        progress_cb("Applying safe quantization...", 0.90)
    quantized_f0 = np.full_like(smoothed_f0, np.nan)
    valid_idx = ~np.isnan(smoothed_f0) 
    
    if np.any(valid_idx):
        midi_continuous = librosa.hz_to_midi(smoothed_f0[valid_idx])
        midi_quantized = np.round(midi_continuous)
        quantized_f0[valid_idx] = librosa.midi_to_hz(midi_quantized)
    
    # 6. Save Data
    if progress_cb:
        progress_cb("Saving pitch data...", 0.95)
    combined = np.column_stack((times, quantized_f0, confidence))
    np.savetxt(
        song_dir / "pitch.csv", 
        combined, 
        delimiter=",", 
        header="time,frequency,confidence", 
        comments="",
        fmt='%f' 
    )
