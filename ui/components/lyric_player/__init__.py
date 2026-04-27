import streamlit.components.v1 as components
from pathlib import Path

# Create the component
_component_dir = Path(__file__).parent
_lyric_player_func = components.declare_component("lyric_player", path=str(_component_dir))

def lyric_player(song_title: str, audio_url: str, lyrics: list, key=None):
    """
    Renders the custom lyric player component.
    """
    return _lyric_player_func(
        song_title=song_title,
        audio_url=audio_url,
        lyrics=lyrics,
        key=key,
        default=None
    )
