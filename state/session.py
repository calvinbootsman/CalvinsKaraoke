import threading
import time

import streamlit as st

from config import MAX_DEBUG_EVENTS


@st.cache_resource
def get_runtime_state_container() -> dict[str, object]:
    return {
        "lock": threading.Lock(),
        "state": {
            "queue": [],
            "playback_index": -1,
            "current_song": None,
            "is_playing": False,
            "current_time": 0.0,
            "playback_started_at": None,
            "audio_render_nonce": 0,
            "player_command_id": 0,
            "last_sent_command": None,
        },
    }


def initialize_queue_state() -> None:
    if "queue" not in st.session_state:
        st.session_state["queue"] = []

    normalized_queue: list[str] = []
    for item in st.session_state.get("queue", []):
        normalized_queue.append(str(item))
    st.session_state["queue"] = normalized_queue


def initialize_playback_state() -> None:
    st.session_state.setdefault("playback_index", -1)
    st.session_state.setdefault("current_song", None)
    st.session_state.setdefault("is_playing", False)
    st.session_state.setdefault("current_time", 0.0)
    st.session_state.setdefault("playback_started_at", None)
    st.session_state.setdefault("audio_render_nonce", 0)
    st.session_state.setdefault("player_command_id", 0)
    st.session_state.setdefault("player_command", None)
    st.session_state.setdefault("last_sent_command", None)
    st.session_state.setdefault("debug_events", [])


def hydrate_session_from_runtime_state() -> None:
    if st.session_state.get("_runtime_hydrated", False):
        return

    container = get_runtime_state_container()
    runtime_lock = container["lock"]
    runtime_state = container["state"]

    with runtime_lock:
        runtime_queue = list(runtime_state.get("queue", []))
        runtime_playback_index = int(runtime_state.get("playback_index", -1))
        runtime_current_song = runtime_state.get("current_song")
        runtime_is_playing = bool(runtime_state.get("is_playing", False))
        runtime_current_time = float(runtime_state.get("current_time", 0.0))
        runtime_playback_started_at = runtime_state.get("playback_started_at")
        runtime_audio_render_nonce = int(runtime_state.get("audio_render_nonce", 0))
        runtime_command_id = int(runtime_state.get("player_command_id", 0))
        runtime_last_sent_command = runtime_state.get("last_sent_command")

    st.session_state["queue"] = runtime_queue
    st.session_state["playback_index"] = runtime_playback_index
    st.session_state["current_song"] = runtime_current_song
    st.session_state["is_playing"] = runtime_is_playing
    st.session_state["current_time"] = runtime_current_time
    st.session_state["playback_started_at"] = runtime_playback_started_at
    st.session_state["audio_render_nonce"] = runtime_audio_render_nonce
    st.session_state["player_command_id"] = runtime_command_id
    st.session_state["last_sent_command"] = runtime_last_sent_command
    st.session_state["_runtime_hydrated"] = True


def persist_runtime_state() -> None:
    container = get_runtime_state_container()
    runtime_lock = container["lock"]
    runtime_state = container["state"]

    with runtime_lock:
        runtime_state["queue"] = list(st.session_state.get("queue", []))
        runtime_state["playback_index"] = int(st.session_state.get("playback_index", -1))
        runtime_state["current_song"] = st.session_state.get("current_song")
        runtime_state["is_playing"] = bool(st.session_state.get("is_playing", False))
        runtime_state["current_time"] = float(st.session_state.get("current_time", 0.0))
        runtime_state["playback_started_at"] = st.session_state.get("playback_started_at")
        runtime_state["audio_render_nonce"] = int(st.session_state.get("audio_render_nonce", 0))
        runtime_state["player_command_id"] = int(st.session_state.get("player_command_id", 0))
        runtime_state["last_sent_command"] = st.session_state.get("last_sent_command")


def log_debug_event(event: str, **data: object) -> None:
    events = list(st.session_state.get("debug_events", []))
    events.append({
        "ts": time.time(),
        "event": event,
        "data": data,
    })
    st.session_state["debug_events"] = events[-MAX_DEBUG_EVENTS:]
