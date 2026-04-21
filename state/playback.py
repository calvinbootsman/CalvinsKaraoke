import streamlit as st


def sync_playback_with_queue() -> None:
    queue: list[str] = st.session_state.get("queue", [])
    current_song = st.session_state.get("current_song")
    current_index = int(st.session_state.get("playback_index", -1))

    if not queue:
        st.session_state["playback_index"] = -1
        st.session_state["current_song"] = None
        st.session_state["is_playing"] = False
        return

    if current_song not in queue:
        st.session_state["playback_index"] = -1
        st.session_state["current_song"] = None
        st.session_state["is_playing"] = False
        return

    if current_index >= len(queue):
        st.session_state["playback_index"] = queue.index(current_song)
