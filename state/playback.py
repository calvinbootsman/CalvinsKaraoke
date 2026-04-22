import streamlit as st


def sync_playback_with_queue() -> None:
    queue: list[str] = st.session_state.get("queue", [])
    current_song = st.session_state.get("current_song")
    current_index = int(st.session_state.get("playback_index", -1))
    is_playing = bool(st.session_state.get("is_playing", False))
    
    # Clear playback state only if queue is empty, no current song, and nothing is playing
    # This preserves the current_song when paused with an empty queue
    if not queue and not current_song and not is_playing:
        st.session_state["playback_index"] = -1
        st.session_state["current_song"] = None
        st.session_state["is_playing"] = False
        st.session_state["current_time"] = 0.0
        st.session_state["playback_started_at"] = None
        return
    
    # Sync playback_index if it's out of range
    if current_index >= len(queue) and current_song:
        if current_song in queue:
            st.session_state["playback_index"] = queue.index(current_song)
        else:
            # Current song not in queue (was removed when played) - reset index
            st.session_state["playback_index"] = -1
