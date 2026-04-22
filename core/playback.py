import time
from urllib.parse import quote

import streamlit as st

from config import MUSIC_DIR
from core.file_utils import parse_lrc_file
from core.server import ensure_media_server
from state.session import log_debug_event


def get_effective_current_time() -> float:
    current_time = float(st.session_state.get("current_time", 0.0))
    if not bool(st.session_state.get("is_playing", False)):
        return max(0.0, current_time)

    playback_started_at = st.session_state.get("playback_started_at")
    if playback_started_at is None:
        return max(0.0, current_time)

    return max(0.0, time.time() - float(playback_started_at))


def refresh_playback_time() -> float:
    effective_time = get_effective_current_time()
    st.session_state["current_time"] = effective_time
    return effective_time


def build_song_payload(song_title: str) -> tuple[dict[str, object] | None, str | None]:
    song_dir = MUSIC_DIR / song_title
    no_vocals_path = song_dir / "no_vocals.mp3"
    if not no_vocals_path.exists():
        return None, f"Missing instrumental file for '{song_title}': no_vocals.mp3"

    media_server_base_url = ensure_media_server()
    encoded_song_title = quote(song_title, safe="")
    audio_url = f"{media_server_base_url}/{encoded_song_title}/no_vocals.mp3"
    lyrics = parse_lrc_file(song_dir / "song.lrc")

    return {
        "title": song_title,
        "audioUrl": audio_url,
        "lyrics": lyrics,
    }, None


def queue_player_command(
    command: str,
    song_payload: dict[str, object] | None = None,
    open_window: bool = False,
    current_time: float | None = None,
) -> None:
    next_id = int(st.session_state.get("player_command_id", 0)) + 1
    command_time = float(st.session_state.get("current_time", 0.0)) if current_time is None else float(current_time)
    command_payload = {
        "id": next_id,
        "command": command,
        "song": song_payload,
        "openWindow": open_window,
        "currentTime": max(0.0, command_time),
    }
    st.session_state["player_command_id"] = next_id
    st.session_state["player_command"] = command_payload
    st.session_state["last_sent_command"] = {
        "id": next_id,
        "command": command,
        "song": song_payload.get("title") if isinstance(song_payload, dict) else None,
        "openWindow": open_window,
        "currentTime": max(0.0, command_time),
        "ts": time.time(),
    }
    log_debug_event(
        "queue_player_command",
        id=next_id,
        command=command,
        song=command_payload.get("song", {}).get("title") if isinstance(command_payload.get("song"), dict) else None,
        open_window=open_window,
        current_time=max(0.0, command_time),
    )


def play_song_at_index(index: int) -> None:
    queue: list[str] = st.session_state.get("queue", [])
    if index < 0 or index >= len(queue):
        st.warning("No song available at that queue position.")
        log_debug_event("play_song_at_index_invalid", index=index, queue_size=len(queue))
        return

    song_title = queue[index]
    payload, error = build_song_payload(song_title)
    if error:
        st.error(error)
        log_debug_event("play_song_at_index_payload_error", index=index, song_title=song_title, error=error)
        return

    # Remove song from queue when it starts playing
    new_queue = [s for i, s in enumerate(queue) if i != index]
    st.session_state["queue"] = new_queue
    
    st.session_state["playback_index"] = -1
    st.session_state["current_song"] = song_title
    st.session_state["is_playing"] = True
    st.session_state["current_time"] = 0.0
    st.session_state["playback_started_at"] = time.time()
    st.session_state["audio_render_nonce"] = int(st.session_state.get("audio_render_nonce", 0)) + 1
    log_debug_event("play_song_at_index", index=index, song_title=song_title, removed_from_queue=True)
    queue_player_command("load_and_play", song_payload=payload, open_window=True, current_time=0.0)


def play_action() -> None:
    queue: list[str] = st.session_state.get("queue", [])
    current_index = int(st.session_state.get("playback_index", -1))
    current_song = st.session_state.get("current_song")
    is_playing = bool(st.session_state.get("is_playing", False))
    
    # Allow resuming even if queue is empty (last song was removed when played)
    if not queue and not current_song:
        st.warning("Queue is empty. Add songs first.")
        log_debug_event("play_action_empty_queue")
        return

    if current_song and not is_playing:
        resume_time = refresh_playback_time()
        st.session_state["is_playing"] = True
        st.session_state["playback_started_at"] = time.time() - resume_time
        st.session_state["audio_render_nonce"] = int(st.session_state.get("audio_render_nonce", 0)) + 1
        log_debug_event("play_action_resume", current_index=current_index, current_song=current_song)
       
        payload = None
        if st.session_state.get("current_song"):
            payload = build_song_payload(st.session_state.get("current_song"))[0]
        queue_player_command("play", song_payload=payload, current_time=resume_time)
        return

    if current_song and is_playing:
        st.toast("Song is already playing.")
        log_debug_event("play_action_already_playing", current_index=current_index, current_song=current_song)
        return

    play_song_at_index(0)


def pause_action() -> None:
    if not st.session_state.get("current_song"):
        st.warning("No song is currently selected for playback.")
        log_debug_event("pause_action_no_song")
        return

    pause_time = refresh_playback_time()
    st.session_state["is_playing"] = False
    st.session_state["playback_started_at"] = None
    st.session_state["audio_render_nonce"] = int(st.session_state.get("audio_render_nonce", 0)) + 1
    
    payload = None
    if st.session_state.get("current_song"):
        payload = build_song_payload(st.session_state.get("current_song"))[0]
    
    log_debug_event("pause_action", current_song=st.session_state.get("current_song"), pause_time=pause_time)
    queue_player_command("pause", song_payload=payload, current_time=pause_time)


def next_action() -> None:
    queue: list[str] = st.session_state.get("queue", [])
    if not queue:
        st.warning("Queue is empty. Add songs first.")
        log_debug_event("next_action_empty_queue")
        return

    current_index = int(st.session_state.get("playback_index", -1))
    next_index = current_index + 1
    if current_index < 0:
        next_index = 0

    if next_index >= len(queue):
        st.info("You reached the end of the queue.")
        log_debug_event("next_action_end_of_queue", current_index=current_index, next_index=next_index, queue_size=len(queue))
        return

    log_debug_event("next_action", current_index=current_index, next_index=next_index, queue_size=len(queue))
    play_song_at_index(next_index)


def add_song_to_queue(song_title: str) -> None:
    queue: list[str] = st.session_state.get("queue", [])
    if song_title in queue:
        st.toast(f"'{song_title}' is already in the queue.")
        return

    st.session_state["queue"] = queue + [song_title]
    st.toast(f"Added '{song_title}' to the queue.")


def move_queue_item(queue: list[str], from_index: int, to_index: int) -> list[str]:
    updated = queue.copy()
    item = updated.pop(from_index)
    updated.insert(to_index, item)
    return updated
