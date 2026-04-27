import streamlit as st
import time
import threading
from streamlit.runtime.scriptrunner import add_script_run_ctx
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

if "bg_tasks" not in st.session_state:
    st.session_state.bg_tasks = {}

@st.fragment(run_every="1s")
def render_progress_panel():
    to_remove = []
    for title, task in st.session_state.bg_tasks.items():
        state = task.get("state")
        msg = task.get("msg")
        if state == "running":
            st.info(f"⏳ **Processing '{title}'**: {msg}")
        elif state == "done":
            show_fading_success(f"Finished processing {title}")
            to_remove.append(title)
        elif state == "error":
            st.error(f"Failed to process '{title}': {msg}")
            if st.button("Dismiss", key=f"dismiss_err_{title}"):
                to_remove.append(title)
    
    for t in to_remove:
        del st.session_state.bg_tasks[t]
        st.rerun()

main_col, queue_col = st.columns([0.7, 0.3], gap="large")

with main_col:
    youtube_url = st.text_input(
        "YouTube video URL",
        placeholder="https://www.youtube.com/watch?v=U3ZGRsbBH94",
    )

    process_clicked = st.button("Process")

    render_progress_panel()

    if process_clicked:
        if not youtube_url.strip():
            st.warning("Please enter a YouTube URL.")
        elif not is_youtube_url(youtube_url):
            st.warning("Please enter a valid YouTube video URL.")
        else:
            def process_song_background(url):
                title_for_task = "Initializing..."
                try:
                    song_title = get_song_title(url)
                    title_for_task = song_title
                    st.session_state.bg_tasks[song_title] = {"state": "running", "msg": "Parsed title..."}

                    song_dir = MUSIC_DIR / song_title
                    song_dir.mkdir(parents=True, exist_ok=True)

                    audio_path = find_downloaded_audio(song_dir)
                    if audio_path is None:
                        st.session_state.bg_tasks[song_title]["msg"] = "Downloading audio..."
                        audio_path = download_audio(url, song_dir)
                    else:
                        st.session_state.bg_tasks[song_title]["msg"] = "Audio exists, validating..."

                    vocals_path = song_dir / "vocals.mp3"
                    no_vocals_path = song_dir / "no_vocals.mp3"
                    if not vocals_path.exists() or not no_vocals_path.exists():
                        st.session_state.bg_tasks[song_title]["msg"] = "Separating audio into stems (vocals and instrumental)..."
                        separate_audio_into_stems(audio_path, song_dir)

                    notes_path = song_dir / "extracted_f0.csv"
                    if not notes_path.exists():
                        st.session_state.bg_tasks[song_title]["msg"] = "Extracting pitch (this may take a bit)..."
                        extract_audio_torchcrepe(audio_path, song_dir)

                    if not (song_dir / "song.lrc").exists():
                        st.session_state.bg_tasks[song_title]["msg"] = "Fetching lyrics..."
                        get_lyrics(song_dir, song_title)
                    
                    st.session_state.bg_tasks[song_title]["state"] = "done"
                    st.session_state.bg_tasks[song_title]["msg"] = "Complete"

                except Exception as error:
                    if title_for_task not in st.session_state.bg_tasks:
                        st.session_state.bg_tasks[title_for_task] = {}
                    st.session_state.bg_tasks[title_for_task]["state"] = "error"
                    st.session_state.bg_tasks[title_for_task]["msg"] = str(error)

            # Pre-register a generic task to display immediate loading before getting the actual title inside thread
            # Avoid overwriting if they click multiple times fast for the same, but they have no title yet
            t_id = f"fetch_{time.time()}"
            st.session_state.bg_tasks[t_id] = {"state": "running", "msg": "Fetching YouTube metadata..."}
            
            def thread_wrapper(url, fallback_id):
                try:
                    process_song_background(url)
                finally:
                    # Once title is known and added, remove the generic initial task
                    if fallback_id in st.session_state.bg_tasks:
                        del st.session_state.bg_tasks[fallback_id]

            t = threading.Thread(target=thread_wrapper, args=(youtube_url, t_id))
            add_script_run_ctx(t)
            t.start()

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
