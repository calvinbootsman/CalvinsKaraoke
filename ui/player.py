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

    # Status indicator
    if current_song:
        status = "Playing" if is_playing else "Paused"
        st.markdown(
            f"<div style='padding:6px 10px;border-radius:8px;background:#{'14532d' if is_playing else '7f1d1d'};color:#{'dcfce7' if is_playing else 'fee2e2'};display:inline-block;margin-bottom:8px;'>{status} mode</div>",
            unsafe_allow_html=True,
        )

    # Dual audio player with volume controls
    st.subheader("Audio Playback")
    
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
        
        # Create dual audio player HTML/JS
        vocals_vol_default = '100' if vocals_url else '0'

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
            <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px;">
                <button id="playBtn" style="padding: 8px 16px; background: #14532d; color: #dcfce7; border: none; border-radius: 6px; cursor: pointer; font-weight: bold;">Play</button>
                <button id="pauseBtn" style="padding: 8px 16px; background: #7f1d1d; color: #fee2e2; border: none; border-radius: 6px; cursor: pointer; font-weight: bold;">Pause</button>
                <button id="stopBtn" style="padding: 8px 16px; background: #78350f; color: #fef3c7; border: none; border-radius: 6px; cursor: pointer; font-weight: bold;">Stop</button>

                <span id="currentTimeDisplay" style="color: #cbd5e1; font-size: 0.9rem; margin-left: auto;">00:00</span>
            </div>
            <input type="range" id="seekBar" min="0" max="100" value="0" style="width: 100%; cursor: pointer;">
            <audio id="instrumentalAudio" src="{instrumental_url}" preload="auto" style="display: none;"></audio>
            {'<audio id="vocalsAudio" src="' + vocals_url + '" preload="auto" style="display: none;"></audio>' if vocals_url else ''}
        </div>
        
        <script>
            const instrumentalAudio = document.getElementById('instrumentalAudio');
            const vocalsAudio = document.getElementById('vocalsAudio');
            const playBtn = document.getElementById('playBtn');
            const pauseBtn = document.getElementById('pauseBtn');
            const stopBtn = document.getElementById('stopBtn');
            const seekBar = document.getElementById('seekBar');
            const currentTimeDisplay = document.getElementById('currentTimeDisplay');
            const instrumentalVol = document.getElementById('instrumentalVol');
            const vocalsVol = document.getElementById('vocalsVol');
            const instrumentalVolValue = document.getElementById('instrumentalVolValue');
            const vocalsVolValue = document.getElementById('vocalsVolValue');

            let isSeeking = false;
            
            // Set initial volumes
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
            
            function play() {{
                const currentTime = {effective_time};
                syncAudio(currentTime);
                instrumentalAudio.play().catch(e => console.error('Play error:', e));
                if (vocalsAudio) vocalsAudio.play().catch(e => console.error('Vocals play error:', e));
            }}
            
            function pause() {{
                instrumentalAudio.pause();
                if (vocalsAudio) vocalsAudio.pause();
            }}
            
            function stop() {{
                instrumentalAudio.pause();
                instrumentalAudio.currentTime = 0;
                if (vocalsAudio) {{
                    vocalsAudio.pause();
                    vocalsAudio.currentTime = 0;
                }}
                currentTimeDisplay.textContent = '00:00';
                seekBar.value = 0;
            }}
            
            // Event listeners
            instrumentalVol.addEventListener('input', updateVolumeDisplay);
            vocalsVol.addEventListener('input', updateVolumeDisplay);
            
            playBtn.addEventListener('click', play);
            pauseBtn.addEventListener('click', pause);
            stopBtn.addEventListener('click', stop);
            
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
                        // Keep vocals in sync
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
            
            instrumentalAudio.addEventListener('ended', stop);
            if (vocalsAudio) vocalsAudio.addEventListener('ended', stop);
            

            
            // Initialize
            updateVolumeDisplay();
            updateTimeDisplay();
            
            // Autoplay if needed
            {'play();' if is_playing else ''}
            
            // Start sync now if already playing
            if (!instrumentalAudio.paused) startSync();
        </script>
        '''
        
        import streamlit.components.v1 as components
        components.html(player_html, height=180)
        
        # Next button
        if st.button("Next Song", use_container_width=True):
            next_action()
            st.rerun()
    elif queue:
        st.caption("Press Play to start the first song in queue.")
