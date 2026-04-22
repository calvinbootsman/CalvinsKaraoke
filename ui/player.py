import streamlit as st

from core.playback import (
    build_song_payload,
    get_effective_current_time,
    next_action,
    pause_action,
    play_action,
)


def _format_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def render_overview_player() -> None:
    st.subheader("Playback controls")

    current_song = st.session_state.get("current_song")
    is_playing = bool(st.session_state.get("is_playing", False))
    queue = st.session_state.get("queue", [])

    effective_time = get_effective_current_time()
    st.session_state["current_time"] = effective_time
    if current_song:
        status = "Playing" if is_playing else "Paused"
        st.info(f"Now playing: {current_song} ({status})")
    else:
        st.info("Now playing: Nothing yet")

    if current_song:
        st.caption(f"Current time: {_format_time(effective_time)}")

    toggle_label = "Play"
    if current_song and is_playing:
        toggle_label = "Pause"
    elif current_song and not is_playing:
        toggle_label = "Resume"

    if toggle_label == "Play":
        st.markdown(
            "<div style='padding:6px 10px;border-radius:8px;background:#14532d;color:#dcfce7;display:inline-block;margin-bottom:8px;'>Play mode</div>",
            unsafe_allow_html=True,
        )
    elif toggle_label == "Pause":
        st.markdown(
            "<div style='padding:6px 10px;border-radius:8px;background:#7f1d1d;color:#fee2e2;display:inline-block;margin-bottom:8px;'>Pause mode</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<div style='padding:6px 10px;border-radius:8px;background:#78350f;color:#fef3c7;display:inline-block;margin-bottom:8px;'>Resume mode</div>",
            unsafe_allow_html=True,
        )

    control_col_toggle, control_col_next = st.columns(2)
    with control_col_toggle:
        if st.button(toggle_label, use_container_width=True, type="primary"):
            if current_song and is_playing:
                pause_action()
            else:
                play_action()
            st.rerun()

    with control_col_next:
        if st.button("Next song", use_container_width=True):
            next_action()
            st.rerun()

    if current_song:
        song_payload, error = build_song_payload(str(current_song))
        if error:
            st.warning(error)
            return

        audio_url = song_payload.get("audioUrl") if isinstance(song_payload, dict) else None
        if not audio_url:
            st.warning("Missing playable audio URL for current song.")
            return

        render_nonce = int(st.session_state.get("audio_render_nonce", 0))
        st.audio(
            str(audio_url),
            format="audio/mp3",
            start_time=max(0, int(effective_time)),
            autoplay=is_playing,
            # key=f"overview-audio-{current_song}-{render_nonce}",
        )
    elif queue:
        st.caption("Press Play to start the first song in queue.")
