import json
import importlib
import time
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from st_keyup import st_keyup

from core.file_utils import find_downloaded_audio, list_available_files, parse_lrc_file
from core.playback import add_song_to_queue, move_queue_item
from core.server import ensure_media_server
from config import DEBUG_ENABLED

sort_items = getattr(importlib.import_module("streamlit_sortables"), "sort_items")
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
SHARED_LYRICS_JS = (TEMPLATES_DIR / "shared_lyrics.js").read_text(encoding="utf-8")


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


def _build_song_preview_html(song_title: str, audio_url: str, lyrics: list[dict[str, float | str]]) -> str:
    lyrics_json = json.dumps([
        {
            "time": float(line.get("time", 0.0)),
            "text": str(line.get("text", "")),
        }
        for line in lyrics
    ])

    return f'''
    <div style="background: rgba(15, 23, 42, 0.82); border: 1px solid rgba(148, 163, 184, 0.32); border-radius: 12px; padding: 14px; margin-top: 10px; font-family: 'Source Sans Pro', 'Segoe UI', sans-serif;">
        <div style="display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <div style="min-width: 0;">
                <div style="color: #e5e7eb; font-size: 0.95rem; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{song_title}</div>
                <div style="color: #94a3b8; font-size: 0.8rem;">Original audio preview and synced lyrics</div>
            </div>
            <div id="previewTime" style="color: #cbd5e1; font-size: 0.88rem; font-variant-numeric: tabular-nums;">00:00</div>
        </div>

        <audio id="previewAudio" src="{audio_url}" controls preload="metadata" style="width: 100%; margin-bottom: 12px;"></audio>

        <div id="previewLyrics" style="max-height: 13.5em; overflow: hidden; border: 1px solid rgba(100, 116, 139, 0.35); border-radius: 10px; background: rgba(2, 6, 23, 0.7); padding: 12px;"></div>
    </div>

    <style>
        .line {{
            opacity: 0.45;
            transition: all 0.2s ease;
            margin: 3px 0;
            font-size: 1rem;
            line-height: 1.45;
            color: #cbd5e1;
        }}
        .line.active {{
            opacity: 1;
            color: #fde68a;
            transform: translateX(4px);
            font-weight: 700;
        }}
    </style>

    <script>
        {SHARED_LYRICS_JS}

        const audioEl = document.getElementById('previewAudio');
        const lyricsEl = document.getElementById('previewLyrics');
        const timeEl = document.getElementById('previewTime');
        const lyricRows = {lyrics_json};
        const lyricWindow = window.createKaraokeLyricWindow({{
            lyricsEl,
            visibleLines: 6,
            lineClassName: 'line',
            activeClassName: 'active',
            emptyMessage: 'No synced lyrics found for this song.',
            smoothScroll: false,
        }});

        function formatTime(seconds) {{
            const total = Math.max(0, Math.floor(Number(seconds || 0)));
            const minutes = Math.floor(total / 60);
            const secs = total % 60;
            return String(minutes).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
        }}

        audioEl.addEventListener('timeupdate', () => {{
            timeEl.textContent = formatTime(audioEl.currentTime);
            lyricWindow.highlight(audioEl.currentTime);
        }});

        audioEl.addEventListener('loadedmetadata', () => {{
            timeEl.textContent = formatTime(audioEl.currentTime);
            lyricWindow.setRows(lyricRows);
            lyricWindow.highlight(audioEl.currentTime);
        }});

        audioEl.addEventListener('play', () => {{
            lyricWindow.highlight(audioEl.currentTime);
        }});

        lyricWindow.setRows(lyricRows);
        lyricWindow.highlight(audioEl.currentTime || 0);
    </script>
    '''


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
                    lyrics = parse_lrc_file(song_dir / "song.lrc")
                    if original_audio is not None:
                        encoded_song_title = quote(song_dir.name, safe="")
                        audio_url = f"{media_server_base_url}/{encoded_song_title}/{quote(original_audio.name, safe='')}"
                        st.iframe(
                            _build_song_preview_html(song_dir.name, audio_url, lyrics),
                            height=360,
                        )
                    else:
                        st.caption("No original audio file found yet.")

                    if available_files:
                        st.write("Available files:")
                        for file_name in available_files:
                            st.write(f"- {file_name}")
                    else:
                        st.write("No generated files found yet.")
        with col_add:
            if st.button("Add to queue", key=f"add-{song_dir.name}"):
                add_song_to_queue(song_dir.name)
