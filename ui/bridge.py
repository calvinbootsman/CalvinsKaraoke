import json
from pathlib import Path

import streamlit as st

from config import MUSIC_DIR
from core.server import ensure_media_server
from state.session import log_debug_event

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _read_template(name: str) -> str:
    return (TEMPLATES_DIR / name).read_text(encoding="utf-8")


def render_player_bridge() -> None:
    command_payload = st.session_state.get("player_command")
    command_json = json.dumps(command_payload)
    media_server_base_url = ensure_media_server()
    player_url = f"{media_server_base_url}/_karaoke_player.html"

    player_html = _read_template("player.html")

    command_file = MUSIC_DIR / "_karaoke_command.json"
    command_file_payload = command_payload if isinstance(command_payload, dict) else {}
    command_file.write_text(json.dumps(command_file_payload), encoding="utf-8")

    bridge_template = _read_template("bridge.html")
    bridge_html = (
        bridge_template
        .replace("__COMMAND_JSON__", command_json)
        .replace("__PLAYER_URL_JSON__", json.dumps(player_url))
    )

    player_file = MUSIC_DIR / "_karaoke_player.html"
    player_file.write_text(player_html, encoding="utf-8")

    bridge_file = MUSIC_DIR / "_karaoke_bridge.html"
    bridge_file.write_text(bridge_html, encoding="utf-8")

    command_id = int(st.session_state.get("player_command_id", 0))
    bridge_url = f"{media_server_base_url}/_karaoke_bridge.html?cb={command_id}"
    st.iframe(bridge_url, height=1)
    # st.session_state["player_command"] = None
    if command_payload:
        log_debug_event(
            "render_player_bridge_command",
            id=command_payload.get("id"),
            command=command_payload.get("command"),
            open_window=command_payload.get("openWindow"),
        )
