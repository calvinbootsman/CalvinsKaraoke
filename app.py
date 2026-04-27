import streamlit as st
import time
from config import MUSIC_DIR
from core.file_utils import (
    filter_songs_by_query,
    find_downloaded_audio,
    is_youtube_url,
    list_saved_music,
)
from core.playback import get_effective_current_time
from core.playback import next_action
from core.processing import download_audio, get_lyrics, get_song_title, separate_audio_into_stems, extract_audio_torchcrepe
from state.playback import sync_playback_with_queue
from state.session import (
    hydrate_session_from_runtime_state,
    initialize_playback_state,
    initialize_queue_state,
    log_debug_event,
    persist_runtime_state,
)
from ui.panels import (
    render_debug_panel,
    render_live_search_input,
    render_queue_panel,
    render_saved_music_panel,
    show_fading_info,
    show_fading_success,
)
from ui.bridge import render_player_bridge
from ui.player import render_overview_player

st.set_page_config(layout="wide", page_title="Calvin's Karaoke")
st.title("Calvin's Karaoke")

MUSIC_DIR.mkdir(exist_ok=True)
hydrate_session_from_runtime_state()
initialize_queue_state()
initialize_playback_state()
sync_playback_with_queue()

main_col, queue_col = st.columns([0.7, 0.3], gap="large")

with main_col:
    youtube_url = st.text_input(
        "YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=U3ZGRsbBH94",
    )

    process_clicked = st.button("Process")

    if process_clicked:
        if not youtube_url.strip():
            st.warning("Please enter a YouTube URL.")
        elif not is_youtube_url(youtube_url):
            st.warning("Please enter a valid YouTube video URL.")
        else:
            try:
                song_title = get_song_title(youtube_url)
                song_dir = MUSIC_DIR / song_title
                song_dir.mkdir(parents=True, exist_ok=True)
                st.write(f"Song: {song_title}")

                audio_path = find_downloaded_audio(song_dir)
                if audio_path is None:
                    audio_path = download_audio(youtube_url, song_dir)
                    show_fading_success("Audio downloaded.")
                else:
                    show_fading_info("Audio already exists. Skipping download.")

                vocals_path = song_dir / "vocals.mp3"
                no_vocals_path = song_dir / "no_vocals.mp3"
                if not vocals_path.exists() or not no_vocals_path.exists():
                    separate_audio_into_stems(audio_path, song_dir)
                    show_fading_success("Audio separated into vocals and no-vocals.")
                else:
                    show_fading_info("Stems already exist. Skipping separation.")

                notes_path = song_dir / "extracted_f0.csv"
                if not notes_path.exists():
                    extract_audio_torchcrepe(audio_path, song_dir)
                    show_fading_success("Audio processed with TorchCrepe for pitch extraction.")
                else:
                    show_fading_info("TorchCrepe output already exists. Skipping pitch extraction.")

                if not (song_dir / "song.lrc").exists():
                    get_lyrics(song_dir, song_title)
                    show_fading_success("Lyrics saved.")
                else:
                    show_fading_info("Lyrics already exist. Skipping lyrics fetch.")
                

            except Exception as error:
                st.error(f"Processing failed: {error}")

    render_overview_player()

    render_debug_panel()

    st.subheader("Saved music")
    saved_songs = list_saved_music(MUSIC_DIR)
    if not saved_songs:
        st.write("No saved songs yet.")
    else:
        search_query = render_live_search_input()
        filtered_songs = filter_songs_by_query(saved_songs, search_query)
        render_saved_music_panel(filtered_songs)

with queue_col:
    render_queue_panel()

render_player_bridge()
persist_runtime_state()
