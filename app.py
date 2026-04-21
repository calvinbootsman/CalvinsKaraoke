import streamlit as st

from config import MUSIC_DIR
from core.file_utils import (
    filter_songs_by_query,
    find_downloaded_audio,
    is_youtube_url,
    list_saved_music,
)
from core.playback import next_action, pause_action, play_action
from core.processing import download_audio, get_lyrics, get_song_title, separate_audio_into_stems
from state.playback import sync_playback_with_queue
from state.session import (
    hydrate_session_from_runtime_state,
    initialize_playback_state,
    initialize_queue_state,
    persist_runtime_state,
)
from ui.bridge import render_player_bridge
from ui.panels import (
    render_debug_panel,
    render_live_search_input,
    render_queue_panel,
    render_saved_music_panel,
    show_fading_info,
    show_fading_success,
)

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

                if not (song_dir / "song.lrc").exists():
                    get_lyrics(song_dir, song_title)
                    show_fading_success("Lyrics saved.")
                else:
                    show_fading_info("Lyrics already exist. Skipping lyrics fetch.")
            except Exception as error:
                st.error(f"Processing failed: {error}")

    st.subheader("Playback controls")
    now_playing = st.session_state.get("current_song")
    if now_playing:
        status = "Playing" if st.session_state.get("is_playing") else "Paused"
        st.info(f"Now playing: {now_playing} ({status})")
    else:
        st.info("Now playing: Nothing yet")

    control_col_play, control_col_pause, control_col_next = st.columns(3)
    with control_col_play:
        if st.button("Play", use_container_width=True):
            play_action()
    with control_col_pause:
        if st.button("Pause", use_container_width=True):
            pause_action()
    with control_col_next:
        if st.button("Next song", use_container_width=True):
            next_action()

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
