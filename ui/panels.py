import json
import importlib
import time
from pathlib import Path
from urllib.parse import quote
import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx
from st_keyup import st_keyup

from core.file_utils import *
from core.playback import add_song_to_queue, move_queue_item
from core.server import ensure_media_server
from core.processing import separate_audio_into_stems, extract_audio_torchcrepe, get_lyrics
from config import DEBUG_ENABLED

sort_items = getattr(importlib.import_module("streamlit_sortables"), "sort_items")
from ui.components.lyric_player import lyric_player


def parse_lrc_file_from_text(lrc_text: str) -> list[dict[str, float | str]]:
    """Parse LRC format text from a string."""
    import re
    
    if not lrc_text:
        return []

    parsed: list[dict[str, float | str]] = []
    for raw_line in lrc_text.splitlines():
        matches = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw_line)
        lyric = re.sub(r"\[(\d+):(\d+(?:\.\d+)?)\]", "", raw_line).strip()
        if not matches or not lyric:
            continue

        for minute_text, second_text in matches:
            total_seconds = (int(minute_text) * 60) + float(second_text)
            parsed.append({"time": total_seconds, "text": lyric})

    return sorted(parsed, key=lambda item: float(item["time"]))


def render_live_search_input() -> str:
    if st_keyup is not None:
        return st_keyup(
            "Search saved songs",
            placeholder="Try exact or approximate titles",
            key="saved_songs_search_keyup",
        )

    st.caption("Install st-keyup for live key-by-key search updates.")
    return st.text_input(
        "Search saved songs",
        placeholder="Try exact or approximate titles",
        key="saved_songs_search_fallback",
    )


def show_fading_success(message: str, duration_seconds: int = 5) -> None:
    del duration_seconds
    st.toast(message)


def show_fading_info(message: str, duration_seconds: int = 5) -> None:
    del duration_seconds
    st.toast(message)


def render_debug_panel() -> None:
    if not DEBUG_ENABLED:
        return
    
    with st.expander("Playback debug", expanded=False):
        st.write(
            {
                "current_song": st.session_state.get("current_song"),
                "playback_index": st.session_state.get("playback_index"),
                "is_playing": st.session_state.get("is_playing"),
                "current_time": round(float(st.session_state.get("current_time", 0.0)), 2),
                "queue_size": len(st.session_state.get("queue", [])),
            }
        )

        last_sent_command = st.session_state.get("last_sent_command")
        if last_sent_command:
            st.write("Last sent command:")
            st.write(last_sent_command)

        events = list(st.session_state.get("debug_events", []))
        if events:
            st.write("Recent events:")
            for entry in reversed(events[-15:]):
                event_time = time.strftime("%H:%M:%S", time.localtime(float(entry.get("ts", 0))))
                st.write(f"{event_time} | {entry.get('event')} | {entry.get('data')}")
        else:
            st.caption("No debug events yet.")


def render_queue_panel() -> None:
    st.subheader("Song queue")
    queue: list[str] = st.session_state.get("queue", [])

    if not queue:
        st.caption("Queue is empty. Add songs from Saved music.")
        return

    if sort_items is None:
        st.caption("Install streamlit-sortables for drag-and-drop reordering.")
    else:
        sortable_style = """
        .sortable-component.vertical {
            background: #0e1117;
            border: 1px solid #41444b;
            border-bottom: 1px solid #6b7280;
            border-radius: 10px;
            box-shadow: inset 0 -1px 0 #6b7280;
            padding: 10px;
        }
        .sortable-item,
        .sortable-item:hover {
            background: #131720;
            color: #f9fafb;
            border: 1px solid #4b5563;
            border-radius: 8px;
            font-weight: 600;
            height: auto !important;
            min-height: 36px;
            line-height: 1.2;
            display: flex;
            align-items: center;
            padding: 8px 10px;
            margin: 10px 10px;
            box-sizing: border-box;
        }
        .sortable-item.dragging {
            height: auto !important;
            min-height: 36px;
        }
        """
        reordered_queue = sort_items(
            list(queue),
            header="Drag songs to reorder",
            direction="vertical",
            custom_style=sortable_style,
        )
        if isinstance(reordered_queue, list) and reordered_queue:
            st.session_state["queue"] = reordered_queue
            queue = reordered_queue

    st.space()
    for index, song_title in enumerate(queue):
        col_title, col_up, col_down, col_remove = st.columns([0.5, 0.12, 0.12, 0.26])

        with col_title:
            st.write(f"{index + 1}. {song_title}")

        with col_up:
            if st.button("↑", key=f"queue-up-{song_title}", disabled=index == 0):
                st.session_state["queue"] = move_queue_item(queue, index, index - 1)
                st.rerun()
        with col_down:
            if st.button("↓", key=f"queue-down-{song_title}", disabled=index == len(queue) - 1):
                st.session_state["queue"] = move_queue_item(queue, index, index + 1)
                st.rerun()

        with col_remove:
            if st.button("Remove", key=f"queue-remove-{song_title}"):
                st.session_state["queue"] = [item for item in queue if item != song_title]
                show_fading_success(f"Removed '{song_title}' from the queue.")
                st.rerun()

def render_saved_music_panel(filtered_songs: list) -> None:
    if not filtered_songs:
        show_fading_info("No songs matched your search.")
        st.caption("Tip: try fewer words or a rough spelling.")
        return

    media_server_base_url = ensure_media_server()

    for song_dir in filtered_songs:
        available_files = list_available_files(song_dir)
        col_expand, col_add = st.columns([0.75, 0.25])
        with col_expand:
            with st.container():
                with st.expander(song_dir.name):
                    original_audio = find_downloaded_audio(song_dir)
                    song_path = song_dir / "song.lrc"
                    
                    # Initialize session state for alternative lyrics
                    session_key_alt_lyrics = f"alt_lyrics_{song_dir.name}"
                    session_key_selected_lyrics = f"selected_lyrics_{song_dir.name}"
                    
                    if session_key_alt_lyrics not in st.session_state:
                        st.session_state[session_key_alt_lyrics] = []
                    if session_key_selected_lyrics not in st.session_state:
                        st.session_state[session_key_selected_lyrics] = "Current (song.lrc)"
                    
                    search_query = st.text_input(
                        "Edit song title for search:",
                        value=song_dir.name,
                        key=f"search-title-input-{song_dir.name}"
                    )

                    search_col1, search_col2 = st.columns([0.5, 0.5])
                    with search_col1:
                        if st.button("🔍 Search alternative lyrics", key=f"search-lyrics-{song_dir.name}"):
                            with st.spinner("Searching for alternative lyrics..."):
                                alt_lyrics_found = search_alternative_lyrics(search_query)
                                st.session_state[session_key_alt_lyrics] = alt_lyrics_found
                                show_fading_success(f"Found {len(alt_lyrics_found)} alternative lyric(s).")
                    
                    with search_col2:
                        if st.session_state[session_key_alt_lyrics]:
                            st.caption(f"✓ {len(st.session_state[session_key_alt_lyrics])} found")
                    
                    # Dropdown to select which lyrics to display
                    if st.session_state[session_key_alt_lyrics]:
                        options = ["Current (song.lrc)"] + [f"Alternative #{i+1}" for i in range(len(st.session_state[session_key_alt_lyrics]))]
                        selected_option = st.selectbox(
                            "Select lyrics to preview:",
                            options,
                            index=0,
                            key=f"lyric-select-{song_dir.name}"
                        )
                        st.session_state[session_key_selected_lyrics] = selected_option
                    else:
                        selected_option = "Current (song.lrc)"

                    # --- NEW OFFSET & PARSING LOGIC ---
                    
                    # 1. Fetch the raw text of the selected lyric
                    if selected_option == "Current (song.lrc)":
                        raw_lrc_text = song_path.read_text(encoding="utf-8") if song_path.exists() else ""
                    else:
                        alt_index = int(selected_option.split("#")[1]) - 1
                        raw_lrc_text = st.session_state[session_key_alt_lyrics][alt_index]

                    # 2. Render the offset bar (slider)
                    lyric_offset = st.slider(
                        "⏱️ Lyrics Offset (seconds): negative pulls lyrics earlier, positive pushes them later",
                        min_value=-30.0, 
                        max_value=30.0, 
                        value=0.0, 
                        step=0.5,
                        key=f"offset-{song_dir.name}"
                    )

                    # 3. Apply the time shift to the raw text
                    adjusted_lrc_text = apply_offset_to_lrc(raw_lrc_text, lyric_offset)
                    
                    # 4. Parse the shifted text for the live preview
                    display_lyrics = parse_lrc_file_from_text(adjusted_lrc_text)

                    # 5. Show save button if changing lyrics OR changing the offset
                    if selected_option != "Current (song.lrc)" or lyric_offset != 0.0:
                        if st.button("💾 Save as Current Lyrics", key=f"save-lyric-{song_dir.name}", type="primary"):
                            song_path.write_text(adjusted_lrc_text or "", encoding="utf-8")
                            show_fading_success("Lyrics saved successfully!")
                            
                            st.session_state[session_key_alt_lyrics] = []
                            st.session_state[session_key_selected_lyrics] = "Current (song.lrc)"
                            st.rerun()
                    # ----------------------------------
                    
                    if original_audio is not None:
                        encoded_song_title = quote(song_dir.name, safe="")
                        audio_url = f"{media_server_base_url}/{encoded_song_title}/{quote(original_audio.name, safe='')}"
                        lyric_player(
                            song_title=song_dir.name,
                            audio_url=audio_url,
                            lyrics=display_lyrics,
                            key=f"lyric-player-{song_dir.name}"
                        )
                    else:
                        st.caption("No original audio file found yet.")

                    st.write("File Status & Regeneration:")
                    
                    has_stems = (song_dir / "vocals.mp3").exists() and (song_dir / "no_vocals.mp3").exists()
                    has_pitch = (song_dir / "pitch.csv").exists()
                    has_lyrics = (song_dir / "song.lrc").exists()
                    
                    c1, c2 = st.columns([0.7, 0.3])
                    c1.write(f"- stems (vocals/no_vocals): {'✅' if has_stems else '❌ missing'}")
                    
                    tid_stems = f"{song_dir.name} (stems)"
                    task_stems = st.session_state.get("bg_tasks", {}).get(tid_stems)
                    
                    if task_stems and task_stems["state"] == "running":
                        c2.progress(max(0.0, min(1.0, float(task_stems.get("progress", 0.0)))), text=task_stems.get("msg", "Processing..."))
                    elif task_stems and task_stems["state"] == "error":
                        c2.error(f"Failed: {task_stems.get('msg', 'Error')}")
                        
                    if not has_stems and original_audio and (not task_stems or task_stems["state"] != "running"):
                        if c2.button("Reprocess", key=f"reprocess-stems-{song_dir.name}"):
                            if "bg_tasks" not in st.session_state: st.session_state.bg_tasks = {}
                            tid = f"{song_dir.name} (stems)"
                            st.session_state.bg_tasks[tid] = {"state": "running", "msg": "Separating audio..."}
                            def worker_stems(audio_file, s_dir, task_id):
                                def cb(msg: str, progress: float | None = None):
                                    if task_id in st.session_state.bg_tasks:
                                        st.session_state.bg_tasks[task_id]["msg"] = msg
                                        if progress is not None:
                                            st.session_state.bg_tasks[task_id]["progress"] = progress
                                try:
                                    separate_audio_into_stems(audio_file, s_dir, progress_cb=cb)
                                    st.session_state.bg_tasks[task_id]["state"] = "done"
                                except Exception as e:
                                    st.session_state.bg_tasks[task_id]["state"] = "error"
                                    st.session_state.bg_tasks[task_id]["msg"] = str(e)
                            t = threading.Thread(target=worker_stems, args=(original_audio, song_dir, tid))
                            add_script_run_ctx(t)
                            t.start()
                            st.rerun()

                    c1, c2 = st.columns([0.7, 0.3])
                    c1.write(f"- pitch.csv: {'✅' if has_pitch else '❌ missing'}")
                    
                    tid_pitch = f"{song_dir.name} (pitch)"
                    task_pitch = st.session_state.get("bg_tasks", {}).get(tid_pitch)
                    
                    if task_pitch and task_pitch["state"] == "running":
                        c2.progress(max(0.0, min(1.0, float(task_pitch.get("progress", 0.0)))), text=task_pitch.get("msg", "Processing..."))
                    elif task_pitch and task_pitch["state"] == "error":
                        c2.error(f"Failed: {task_pitch.get('msg', 'Error')}")

                    if not has_pitch and original_audio and (not task_pitch or task_pitch["state"] != "running"):
                        if c2.button("Reprocess", key=f"reprocess-pitch-{song_dir.name}"):
                            if "bg_tasks" not in st.session_state: st.session_state.bg_tasks = {}
                            tid = f"{song_dir.name} (pitch)"
                            st.session_state.bg_tasks[tid] = {"state": "running", "msg": "Extracting pitch..."}
                            def worker_pitch(audio_file, s_dir, task_id):
                                def cb(msg: str, progress: float | None = None):
                                    if task_id in st.session_state.bg_tasks:
                                        st.session_state.bg_tasks[task_id]["msg"] = msg
                                        if progress is not None:
                                            st.session_state.bg_tasks[task_id]["progress"] = progress
                                try:
                                    vocals_path = s_dir / "vocals.mp3"
                                    print(f"Worker pitch: audio_file={audio_file}, vocals_path={vocals_path}, s_dir={s_dir}")
                                    extract_audio_torchcrepe(vocals_path, s_dir, progress_cb=cb)
                                    st.session_state.bg_tasks[task_id]["state"] = "done"
                                except Exception as e:
                                    st.session_state.bg_tasks[task_id]["state"] = "error"
                                    st.session_state.bg_tasks[task_id]["msg"] = str(e)
                            t = threading.Thread(target=worker_pitch, args=(original_audio, song_dir, tid))
                            add_script_run_ctx(t)
                            t.start()
                            st.rerun()

                    c1, c2 = st.columns([0.7, 0.3])
                    c1.write(f"- song.lrc: {'✅' if has_lyrics else '❌ missing'}")
                    
                    tid_lyrics = f"{song_dir.name} (lyrics)"
                    task_lyrics = st.session_state.get("bg_tasks", {}).get(tid_lyrics)

                    if task_lyrics and task_lyrics["state"] == "running":
                        c2.progress(max(0.0, min(1.0, float(task_lyrics.get("progress", 0.0)))), text=task_lyrics.get("msg", "Processing..."))
                    elif task_lyrics and task_lyrics["state"] == "error":
                        c2.error(f"Failed: {task_lyrics.get('msg', 'Error')}")

                    if not has_lyrics and (not task_lyrics or task_lyrics["state"] != "running"):
                        if c2.button("Reprocess", key=f"reprocess-lyrics-{song_dir.name}"):
                            if "bg_tasks" not in st.session_state: st.session_state.bg_tasks = {}
                            tid = f"{song_dir.name} (lyrics)"
                            st.session_state.bg_tasks[tid] = {"state": "running", "msg": "Fetching lyrics..."}
                            def worker_lyrics(s_dir, task_id):
                                try:
                                    get_lyrics(s_dir, s_dir.name)
                                    st.session_state.bg_tasks[task_id]["state"] = "done"
                                except Exception as e:
                                    st.session_state.bg_tasks[task_id]["state"] = "error"
                                    st.session_state.bg_tasks[task_id]["msg"] = str(e)
                            t = threading.Thread(target=worker_lyrics, args=(song_dir, tid))
                            add_script_run_ctx(t)
                            t.start()
                            st.rerun()
        with col_add:
            if st.button("Add to queue", key=f"add-{song_dir.name}"):
                add_song_to_queue(song_dir.name)

    has_running_tasks = any(t.get("state") == "running" for t in st.session_state.get("bg_tasks", {}).values())
    if has_running_tasks:
        time.sleep(1)
        st.rerun()