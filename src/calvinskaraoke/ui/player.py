import json

import streamlit as st

from core.playback import (
    build_song_payload,
    next_action,
    stop_action,
    toggle_play_pause_action,
)


def _format_time(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    minutes, secs = divmod(total_seconds, 60)
    return f"{minutes:02d}:{secs:02d}"


def _render_live_time_label(initial_time: float, is_playing: bool, song_title: str) -> None:
    st.iframe(
        f'''
        <div id="liveMainTime" style="color:#9ca3af;font-size:0.85rem;margin:2px 0 8px 0;">Current time: 00:00</div>
        <script>
            const timeEl = document.getElementById('liveMainTime');
            const playing = {str(is_playing).lower()};
            const baseTime = Number({float(initial_time)} || 0);
            const startedAt = Date.now();
            const songTitle = {json.dumps(song_title)};
            const playbackStateKey = 'karaoke-main-player-state';

            function formatTime(seconds) {{
                const total = Math.max(0, Math.floor(Number(seconds || 0)));
                const minutes = Math.floor(total / 60);
                const secs = total % 60;
                return String(minutes).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
            }}

            function update() {{
                let displayTime = null;
                try {{
                    const raw = localStorage.getItem(playbackStateKey);
                    if (raw) {{
                        const parsed = JSON.parse(raw);
                        if (parsed && parsed.songTitle === songTitle && Number.isFinite(Number(parsed.currentTime))) {{
                            displayTime = Number(parsed.currentTime);
                        }}
                    }}
                }} catch (error) {{
                }}

                if (displayTime === null) {{
                    const elapsed = playing ? ((Date.now() - startedAt) / 1000) : 0;
                    displayTime = baseTime + elapsed;
                }}

                timeEl.textContent = 'Current time: ' + formatTime(displayTime);
            }}

            update();
            setInterval(update, 200);
        </script>
        ''',
        height=24,
    )


def render_overview_player() -> None:
    st.subheader("Playback controls")

    current_song = st.session_state.get("current_song")
    is_playing = bool(st.session_state.get("is_playing", False))
    queue = st.session_state.get("queue", [])
    committed_time = float(st.session_state.get("current_time", 0.0))

    if current_song:
        status = "Playing" if is_playing else "Paused"
        st.info(f"Now playing: {current_song} ({status})")
    else:
        st.info("Now playing: Nothing yet")

    if current_song:
        _render_live_time_label(committed_time, is_playing, str(current_song))

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
        if current_song or queue:
            if st.button("Stop", use_container_width=True, key="stop_button"):
                stop_action()
                st.rerun()

    with control_cols[2]:
        if current_song or queue:
            if st.button("Next Song", use_container_width=True):
                next_action()
                st.rerun()

    # Main page audio player stays anchored to committed Streamlit playback state.
    # The popup remains command-driven through the bridge.

  # ... (Keep your python variables and button logic at the top exactly as they are) ...

    if current_song:
        song_payload, error = build_song_payload(str(current_song))
        if error:
            st.warning(error)
            return

        instrumental_url = song_payload.get("instrumentalUrl") if isinstance(song_payload, dict) else None
        vocals_url = song_payload.get("vocalsUrl") if isinstance(song_payload, dict) else None
        song_title = str(current_song)
        song_payload_json = json.dumps(song_payload)
        
        if not instrumental_url:
            st.warning("Missing playable instrumental URL for current song.")
            return
        
        vocals_vol_default = '100' if vocals_url else '0'
        
        # 1. THE STATIC AUDIO PLAYER
        # Notice we removed all Python variables that change during playback (like nonces and is_playing).
        # This guarantees Streamlit NEVER destroys the iframe while a song is loaded.
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
                <div style="flex: 1;">
                    <label style="display: block; color: #cbd5e1; font-size: 0.85rem; margin-bottom: 4px;">Tick Threshold</label>
                    <input type="range" id="confidenceVol" min="0" max="100" value="50" style="width: 100%;">
                    <span id="confidenceVolValue" style="color: #a1a1aa; font-size: 0.85rem;">50%</span>
                </div>
            </div>
            <input type="range" id="seekBar" min="0" max="100" value="0" style="width: 100%; cursor: pointer; margin-bottom: 12px;">
            <span id="currentTimeDisplay" style="color: #cbd5e1; font-size: 0.9rem; display: block; margin-bottom: 12px;">00:00</span>
            
            <audio id="instrumentalAudio" src="{instrumental_url}" preload="auto" crossorigin="anonymous" style="display: none;"></audio>
            {'<audio id="vocalsAudio" src="' + vocals_url + '" preload="auto" crossorigin="anonymous" style="display: none;"></audio>' if vocals_url else ''}
        </div>
        
        <script>
            const instrumentalAudio = document.getElementById('instrumentalAudio');
            const vocalsAudio = document.getElementById('vocalsAudio');
            const seekBar = document.getElementById('seekBar');
            const currentTimeDisplay = document.getElementById('currentTimeDisplay');
            const instrumentalVol = document.getElementById('instrumentalVol');
            const vocalsVol = document.getElementById('vocalsVol');
            const confidenceVol = document.getElementById('confidenceVol');
            const confidenceVolValue = document.getElementById('confidenceVolValue');
            
            const songTitle = {json.dumps(song_title)};
            const songPayload = {song_payload_json};
            const playbackStateKey = 'karaoke-main-player-state';
            const commandKey = 'karaoke-streamlit-cmd';
            
            function updateVolumeDisplay() {{
                const instVol = instrumentalVol.value / 100;
                const vocVol = vocalsAudio ? (vocalsVol.value / 100) : 0;
                
                if (audioCtx && instrumentalGain) {{
                    instrumentalGain.gain.value = instVol;
                    if (vocalsGain) vocalsGain.gain.value = vocVol;
                }} else {{
                    instrumentalAudio.volume = instVol;
                    if (vocalsAudio) vocalsAudio.volume = vocVol;
                }}
                
                instrumentalVolValue.textContent = instrumentalVol.value + '%';
                if (vocalsAudio) vocalsVolValue.textContent = vocalsVol.value + '%';
            }}

            let audioCtx = null;
            let instrumentalGain = null;
            let vocalsGain = null;

            function initWebAudio() {{
                if (audioCtx) return;
                try {{
                    const AudioContext = window.AudioContext || window.webkitAudioContext;
                    audioCtx = new AudioContext();

                    const instSource = audioCtx.createMediaElementSource(instrumentalAudio);
                    instrumentalGain = audioCtx.createGain();
                    instSource.connect(instrumentalGain);
                    instrumentalGain.connect(audioCtx.destination);

                    if (vocalsAudio) {{
                        const vocSource = audioCtx.createMediaElementSource(vocalsAudio);
                        vocalsGain = audioCtx.createGain();
                        vocSource.connect(vocalsGain);
                        vocalsGain.connect(audioCtx.destination);
                    }}
                    updateVolumeDisplay(); 
                }} catch (e) {{}}
            }}

            let lastHandledActionNonce = 0;
            let lastHandledTimeNonce = 0;
            let isSeeking = false;
            let lastBridgeSyncSentAt = 0;

            function postToBridge(command, timeSeconds, force = false) {{
                const now = Date.now();
                if (!force && (now - lastBridgeSyncSentAt) < 250) return;
                lastBridgeSyncSentAt = now;
                const confThreshold = confidenceVol ? (confidenceVol.value / 100) : 0.5;
                const payload = {{ command, song: songPayload, currentTime: Math.max(0, Number(timeSeconds || 0)), isPlaying: !instrumentalAudio.paused, ts: now, confidenceThreshold: confThreshold }};
                try {{
                    if (!window.parent || !window.parent.document) return;
                    const iframes = window.parent.document.querySelectorAll('iframe');
                    for (const frame of iframes) {{
                        const src = String(frame.getAttribute('src') || '');
                        if (!src.includes('_karaoke_bridge.html')) continue;
                        if (!frame.contentWindow) continue;
                        frame.contentWindow.postMessage({{ type: 'karaoke-main-command', payload }}, '*');
                    }}
                }} catch (error) {{}}
            }}

            function pushStateToPopup(timeSeconds) {{
                try {{
                    const confThreshold = confidenceVol ? (confidenceVol.value / 100) : 0.5;
                    localStorage.setItem(playbackStateKey, JSON.stringify({{
                        songTitle, currentTime: Math.max(0, Number(timeSeconds || 0)), isPlaying: !instrumentalAudio.paused, ts: Date.now(), confidenceThreshold: confThreshold
                    }}));
                }} catch (error) {{}}
            }}

            function updateTimeDisplay() {{
                const currentTime = instrumentalAudio.currentTime;
                const total = Math.max(0, Math.floor(currentTime || 0));
                currentTimeDisplay.textContent = String(Math.floor(total / 60)).padStart(2, '0') + ':' + String(total % 60).padStart(2, '0');
                if (instrumentalAudio.duration > 0 && !isNaN(instrumentalAudio.duration)) {{
                    seekBar.max = String(instrumentalAudio.duration);
                }}
                seekBar.value = String(currentTime);
            }}

            function triggerPlay() {{
                initWebAudio();
                if (audioCtx && audioCtx.state === 'suspended') {{
                    audioCtx.resume();
                }}
                instrumentalAudio.play().catch(e => console.warn("Autoplay blocked. Need interaction inside iframe.", e));
                if (vocalsAudio) vocalsAudio.play().catch(e => {{}});
            }}

            window.addEventListener('storage', (e) => {{
                if (e.key === commandKey && e.newValue) {{
                    try {{
                        const cmd = JSON.parse(e.newValue);
                        
                        if (cmd.time_nonce > lastHandledTimeNonce) {{
                            lastHandledTimeNonce = cmd.time_nonce;
                            instrumentalAudio.currentTime = cmd.time;
                            if (vocalsAudio) vocalsAudio.currentTime = cmd.time;
                        }}
                        
                        if (cmd.action_nonce > lastHandledActionNonce) {{
                            lastHandledActionNonce = cmd.action_nonce;
                            if (cmd.is_playing) {{
                                triggerPlay();
                            }} else {{
                                instrumentalAudio.pause();
                                if (vocalsAudio) vocalsAudio.pause();
                            }}
                        }}
                    }} catch (err) {{}}
                }}
            }});

            try {{
                const bootCmdRaw = localStorage.getItem(commandKey);
                if (bootCmdRaw) {{
                    const bootCmd = JSON.parse(bootCmdRaw);
                    lastHandledActionNonce = bootCmd.action_nonce;
                    lastHandledTimeNonce = bootCmd.time_nonce;
                    instrumentalAudio.currentTime = bootCmd.time;
                    if (bootCmd.is_playing) {{
                        triggerPlay();
                    }}
                }}
            }} catch(e) {{}}

            seekBar.addEventListener('input', () => isSeeking = true);
            seekBar.addEventListener('change', () => {{
                isSeeking = false;
                instrumentalAudio.currentTime = seekBar.value;
                if (vocalsAudio) vocalsAudio.currentTime = seekBar.value;
                pushStateToPopup(seekBar.value);
                postToBridge('seek', seekBar.value, true);
            }});

            instrumentalAudio.addEventListener('timeupdate', () => {{
                if (isSeeking) return;
                updateTimeDisplay();
                pushStateToPopup(instrumentalAudio.currentTime);
                postToBridge('sync', instrumentalAudio.currentTime, false);
                
                if (vocalsAudio) {{
                    const drift = Math.abs(vocalsAudio.currentTime - instrumentalAudio.currentTime);
                    if (drift > 0.1) {{
                        vocalsAudio.currentTime = instrumentalAudio.currentTime;
                    }}
                }}
            }});

            instrumentalAudio.addEventListener('play', () => {{
                pushStateToPopup(instrumentalAudio.currentTime);
                postToBridge('play', instrumentalAudio.currentTime, true);
            }});

            instrumentalAudio.addEventListener('pause', () => {{
                pushStateToPopup(instrumentalAudio.currentTime);
                postToBridge('pause', instrumentalAudio.currentTime, true);
            }});
            
            instrumentalVol.addEventListener('input', () => {{
                initWebAudio(); 
                updateVolumeDisplay();
            }});
            if (vocalsAudio) vocalsVol.addEventListener('input', () => {{
                initWebAudio();
                updateVolumeDisplay();
            }});
            if (confidenceVol) confidenceVol.addEventListener('input', () => {{
                confidenceVolValue.textContent = confidenceVol.value + '%';
                pushStateToPopup(instrumentalAudio.currentTime);
                postToBridge('sync_conf', instrumentalAudio.currentTime, true);
            }});
            updateVolumeDisplay();

        </script>
        '''
        st.iframe(player_html, height=200)

        # 2. THE INVISIBLE COMMAND INJECTOR
        # This block contains the changing variables. It re-renders on every button click 
        # and secretly updates localStorage, which triggers the listener in the static player above.
        cmd_payload = {
            "action_nonce": int(st.session_state.get("action_nonce", 0)),
            "time_nonce": int(st.session_state.get("time_override_nonce", 0)),
            "is_playing": bool(st.session_state.get("is_playing", False)),
            "time": float(st.session_state.get("current_time", 0.0))
        }
        
        injector_html = f'''
        <script>
            localStorage.setItem('karaoke-streamlit-cmd', JSON.stringify({json.dumps(cmd_payload)}));
        </script>
        '''

        st.iframe(injector_html, height=1)

    elif queue:
        st.caption("Press Play to start the first song in queue.")    
        
    # with st.expander("🔍 Server State Debugger", expanded=True):
    #     st.json({
    #         "action_nonce": st.session_state.get("action_nonce", 0),
    #         "time_override_nonce": st.session_state.get("time_override_nonce", 0),
    #         "is_playing": st.session_state.get("is_playing", False),
    #         "last_action_ts": st.session_state.get("last_action_ts", 0),
    #         "current_song": str(current_song) if current_song else None
    #     })
