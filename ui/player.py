import streamlit as st
import streamlit.components.v1 as components

from core.playback import (
    build_song_payload,
    get_effective_current_time,
    next_action,
    stop_action,
    toggle_play_pause_action,
)


def _format_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def _render_live_time_label(initial_time: float, is_playing: bool) -> None:
    components.html(
        f'''
        <div id="liveMainTime" style="color:#9ca3af;font-size:0.85rem;margin:2px 0 8px 0;">Current time: 00:00</div>
        <script>
            const timeEl = document.getElementById('liveMainTime');
            const playing = {str(is_playing).lower()};
            const baseTime = Number({float(initial_time)} || 0);
            const startedAt = Date.now();

            function formatTime(seconds) {{
                const total = Math.max(0, Math.floor(Number(seconds || 0)));
                const minutes = Math.floor(total / 60);
                const secs = total % 60;
                return String(minutes).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            }}

            function update() {{
                const elapsed = playing ? ((Date.now() - startedAt) / 1000) : 0;
                timeEl.textContent = 'Current time: ' + formatTime(baseTime + elapsed);
            }}

            update();
            if (playing) setInterval(update, 250);
        </script>
        ''',
        height=24,
    )


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
        _render_live_time_label(effective_time, is_playing)

    control_cols = st.columns(3)

    with control_cols[0]:
        if current_song or queue:
            if st.button(
                "Pause" if is_playing else "Play",
                use_container_width=True,
                type="primary",
                key="play_pause_toggle",
            ):
                toggle_play_pause_action()
                st.rerun()

    with control_cols[1]:
        if current_song:
            if st.button("Stop", use_container_width=True, key="stop_button"):
                stop_action()
                st.rerun()

    with control_cols[2]:
        if current_song or queue:
            if st.button("Next Song", use_container_width=True):
                next_action()
                st.rerun()

    # Main page audio player is controlled from Streamlit state on rerun.
    # The popup remains command-driven through the bridge.
    
    if current_song:
        song_payload, error = build_song_payload(str(current_song))
        if error:
            st.warning(error)
            return

        instrumental_url = song_payload.get("instrumentalUrl") if isinstance(song_payload, dict) else None
        vocals_url = song_payload.get("vocalsUrl") if isinstance(song_payload, dict) else None
        
        if not instrumental_url:
            st.warning("Missing playable instrumental URL for current song.")
            return
        
        # Pre-compute volume default
        vocals_vol_default = '100' if vocals_url else '0'
        
        # Height needs to account for both player and button
        player_html = f'''
        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.35); border-radius: 10px; padding: 16px; margin-bottom: 16px;">
            <div style="display: flex; gap: 16px; margin-bottom: 12px;">
                <div style="flex: 1;">
                    <label style="display: block; color: #cbd5e1; font-size: 0.85rem; margin-bottom: 4px;">Instrumental Volume</label>
                    <input type="range" id="instrumentalVol" min="0" max="100" value="100" style="width: 100%;">
                    <span id="instrumentalVolValue" style="color: #a1a1aa; font-size: 0.85rem;">100%</span>
                </div>
                <div style="flex: 1;">
                    <label style="display: block; color: #cbd5e1; font-size: 0.85rem; margin-bottom: 4px;">Vocals Volume</label>
                    <input type="range" id="vocalsVol" min="0" max="100" value="{vocals_vol_default}" style="width: 100%;">
                    <span id="vocalsVolValue" style="color: #a1a1aa; font-size: 0.85rem;">{vocals_vol_default}%</span>
                </div>
            </div>
            <input type="range" id="seekBar" min="0" max="100" value="0" style="width: 100%; cursor: pointer; margin-bottom: 12px;">
            <span id="currentTimeDisplay" style="color: #cbd5e1; font-size: 0.9rem; display: block; margin-bottom: 12px;">00:00</span>
            <audio id="instrumentalAudio" src="{instrumental_url}" preload="auto" style="display: none;"></audio>
            {'<audio id="vocalsAudio" src="' + vocals_url + '" preload="auto" style="display: none;"></audio>' if vocals_url else ''}
        </div>
        
        <script>
            const instrumentalAudio = document.getElementById('instrumentalAudio');
            const vocalsAudio = document.getElementById('vocalsAudio');
            const seekBar = document.getElementById('seekBar');
            const currentTimeDisplay = document.getElementById('currentTimeDisplay');
            const instrumentalVol = document.getElementById('instrumentalVol');
            const vocalsVol = document.getElementById('vocalsVol');
            const instrumentalVolValue = document.getElementById('instrumentalVolValue');
            const vocalsVolValue = document.getElementById('vocalsVolValue');
            const initialServerTime = Number({float(effective_time)} || 0);
            const initialServerIsPlaying = {str(is_playing).lower()};
            let isSeeking = false;

            instrumentalAudio.volume = instrumentalVol.value / 100;
            if (vocalsAudio) vocalsAudio.volume = vocalsVol.value / 100;

            function updateVolumeDisplay() {{
                instrumentalAudio.volume = instrumentalVol.value / 100;
                instrumentalVolValue.textContent = instrumentalVol.value + '%';
                if (vocalsAudio) {{
                    vocalsAudio.volume = vocalsVol.value / 100;
                    vocalsVolValue.textContent = vocalsVol.value + '%';
                }}
            }}

            function formatTime(seconds) {{
                const total = Math.max(0, Math.floor(seconds || 0));
                const minutes = Math.floor(total / 60);
                const secs = total % 60;
                return String(minutes).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            }}

            function updateTimeDisplay() {{
                const currentTime = instrumentalAudio.currentTime;
                const duration = instrumentalAudio.duration;
                currentTimeDisplay.textContent = formatTime(currentTime);
                if (duration > 0 && !isNaN(duration)) {{
                    seekBar.value = (currentTime / duration) * 100;
                }}
            }}

            function syncAudio(time) {{
                instrumentalAudio.currentTime = time;
                if (vocalsAudio) vocalsAudio.currentTime = time;
            }}

            instrumentalVol.addEventListener('input', updateVolumeDisplay);
            vocalsVol.addEventListener('input', updateVolumeDisplay);

            seekBar.addEventListener('input', () => isSeeking = true);
            seekBar.addEventListener('change', () => {{
                isSeeking = false;
                const duration = instrumentalAudio.duration;
                if (duration > 0 && !isNaN(duration)) {{
                    const seekTime = (seekBar.value / 100) * duration;
                    syncAudio(seekTime);
                }}
            }});

            instrumentalAudio.addEventListener('timeupdate', () => {{
                if (!isSeeking) {{
                    updateTimeDisplay();
                    if (vocalsAudio) {{
                        if (Math.abs(vocalsAudio.currentTime - instrumentalAudio.currentTime) > 0.1) {{
                            vocalsAudio.currentTime = instrumentalAudio.currentTime;
                        }}
                    }}
                }}
            }});

            if (vocalsAudio) {{
                vocalsAudio.addEventListener('timeupdate', () => {{
                    if (!isSeeking && Math.abs(vocalsAudio.currentTime - instrumentalAudio.currentTime) > 0.1) {{
                        vocalsAudio.currentTime = instrumentalAudio.currentTime;
                    }}
                }});
            }}

            instrumentalAudio.addEventListener('ended', () => {{
                instrumentalAudio.currentTime = 0;
                seekBar.value = 0;
                if (vocalsAudio) vocalsAudio.currentTime = 0;
            }});
            if (vocalsAudio) vocalsAudio.addEventListener('ended', () => {{
                vocalsAudio.currentTime = 0;
            }});

            updateVolumeDisplay();
            updateTimeDisplay();

            syncAudio(initialServerTime);

            if (initialServerIsPlaying) {{
                instrumentalAudio.play().catch(() => {{}});
                if (vocalsAudio) vocalsAudio.play().catch(() => {{}});
            }}
        </script>
        '''
        
        components.html(player_html, height=200)
    elif queue:
        st.caption("Press Play to start the first song in queue.")
