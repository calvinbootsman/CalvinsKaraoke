#%%
from pathlib import Path

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import medfilt

from core.processing import extract_audio_torchcrepe


            
music_dir = Path("music")
song_dirs = [d for d in music_dir.iterdir() if d.is_dir()]

for song_dir in song_dirs:
    audio_path = song_dir / "vocals.mp3"

    def prog_cb(msg: str, progress: float | None = None):
        print(f"{msg} ({progress:.1%} complete)" if progress is not None else msg)    
    extract_audio_torchcrepe(audio_path, song_dir, progress_cb=prog_cb)
    
    print(f"Finished processing {song_dir.name}")
    pitch_file = song_dir / "pitch.csv"

    times, f0, voiced_probs = np.loadtxt(pitch_file, delimiter=",", skiprows=1, unpack=True)
    confidence_threshold = 0.05  # Must be 75% confident it's a sung note

    strict_f0 = np.copy(f0)
    strict_f0[voiced_probs < confidence_threshold] = np.nan

    smoothed_f0 = medfilt(strict_f0, kernel_size=15)

    midi_continuous = librosa.hz_to_midi(smoothed_f0)
    midi_quantized = np.round(midi_continuous)

    quantized_f0 = librosa.midi_to_hz(midi_quantized)

    # --- Plotting the difference ---
    # plt.figure(figsize=(12, 6))

    # # Plot the raw, noisy pitch in light gray
    # plt.plot(times, f0, label='Raw Pitch', color='lightgray', alpha=0.7, linewidth=1)

    # # Plot the straight, karaoke-ready lines in red
    # plt.plot(times, quantized_f0, label='Karaoke Blocks (Quantized)', color='red', linewidth=3)

    # plt.title('Raw Pitch vs. Karaoke-Ready Quantized Pitch')
    # plt.xlabel('Time [s]')
    # plt.ylabel('Frequency [Hz] (Log Scale)')
    # plt.ylim(librosa.note_to_hz('C2'), librosa.note_to_hz('C6'))
    # plt.xlim(0, 10)
    # plt.yscale('log') # Log scale keeps visual distance between notes equal
    # plt.legend(loc='upper right')
    # plt.show()

#%%
# from core.file_utils import search_alternative_lyrics

# song_title = "Sleep Token - Blood Sport (from the room below)"
# alternatives = search_alternative_lyrics(song_title)
# print(f"Alternative lyrics for '{song_title}':")
# for alt in alternatives:
#     print(f"- {alt}")