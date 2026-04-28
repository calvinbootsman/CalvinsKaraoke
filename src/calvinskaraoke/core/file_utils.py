import re
from difflib import SequenceMatcher
from pathlib import Path

from libs.syncedlyrics.syncedlyrics import search
from config import VALID_AUDIO_EXTENSIONS


def sanitize_title(title: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.rstrip(".") or "Unknown title"


def is_youtube_url(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def find_downloaded_audio(song_dir: Path) -> Path | None:
    for file_path in song_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in VALID_AUDIO_EXTENSIONS:
            if file_path.name not in {"vocals.mp3", "no_vocals.mp3"}:
                return file_path
    return None


def list_saved_music(music_dir: Path) -> list[Path]:
    if not music_dir.exists():
        return []
    return sorted([p for p in music_dir.iterdir() if p.is_dir()], key=lambda p: p.name.lower())


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def fuzzy_score(query: str, candidate: str) -> float:
    query_norm = normalize_text(query)
    candidate_norm = normalize_text(candidate)
    if not query_norm or not candidate_norm:
        return 0.0

    if query_norm in candidate_norm:
        return 1.0

    full_ratio = SequenceMatcher(None, query_norm, candidate_norm).ratio()
    query_tokens = query_norm.split()
    candidate_tokens = candidate_norm.split()
    token_ratio = 0.0
    if query_tokens and candidate_tokens:
        token_ratio = max(
            SequenceMatcher(None, q, c).ratio()
            for q in query_tokens
            for c in candidate_tokens
        )

    return max(full_ratio, token_ratio)


def filter_songs_by_query(saved_songs: list[Path], query: str, min_score: float = 0.55) -> list[Path]:
    query = query.strip()
    if not query:
        return saved_songs

    scored = [(song, fuzzy_score(query, song.name)) for song in saved_songs]
    matched = [item for item in scored if item[1] >= min_score]
    matched.sort(key=lambda item: item[1], reverse=True)
    return [song for song, _ in matched]


def list_available_files(song_dir: Path) -> list[str]:
    files: list[str] = []

    source_file = find_downloaded_audio(song_dir)
    if source_file is not None:
        files.append(f"Source audio ({source_file.name})")

    if (song_dir / "vocals.mp3").exists():
        files.append("vocals.mp3")

    if (song_dir / "no_vocals.mp3").exists():
        files.append("no_vocals.mp3")

    if (song_dir / "song.lrc").exists():
        files.append("song.lrc")

    return files


def parse_lrc_file(lrc_path: Path) -> list[dict[str, float | str]]:
    if not lrc_path.exists():
        return []

    parsed: list[dict[str, float | str]] = []
    for raw_line in lrc_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        matches = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", raw_line)
        lyric = re.sub(r"\[(\d+):(\d+(?:\.\d+)?)\]", "", raw_line).strip()
        if not matches or not lyric:
            continue

        for minute_text, second_text in matches:
            total_seconds = (int(minute_text) * 60) + float(second_text)
            parsed.append({"time": total_seconds, "text": lyric})

    return sorted(parsed, key=lambda item: float(item["time"]))


def search_alternative_lyrics(song_title: str) -> list[str]:
    """Search for alternative synchronized lyrics using syncedlyrics library.
    
    Returns a list of LRC formatted strings found.
    """
    lrc_list = []
    providers_to_check = ["Musixmatch", "Lrclib", "NetEase", "Megalobiz"]
    print(f"Searching for alternative lyrics for '{song_title}'...")
    try:
        for provider in providers_to_check:
            try:
                print('trying provider', provider)
                lrc = search(song_title, providers=[provider])
                if lrc:
                    lrc_list.append(lrc)
            except Exception:
                continue
        print(f"Found {len(lrc_list)} alternative lyrics for '{song_title}'.")
        return lrc_list
    except Exception:
        print(f"Error occurred while searching for alternative lyrics for '{song_title}'.")
        return []


def apply_offset_to_lrc(lrc_text: str, offset_seconds: float) -> str:
    if offset_seconds == 0.0 or not lrc_text:
        return lrc_text
        
    def shift_time(match):
        mins = int(match.group(1))
        secs = float(match.group(2))
        total_secs = (mins * 60) + secs + offset_seconds
        
        # Prevent negative timestamps if the user pushes it too far early
        if total_secs < 0:
            total_secs = 0.0 
            
        new_mins = int(total_secs // 60)
        new_secs = total_secs % 60
        # Format back to [mm:ss.xx]
        return f"[{new_mins:02d}:{new_secs:05.2f}]"
        
    # Matches standard LRC time tags like [01:23.45] or [01:23]
    return re.sub(r"\[(\d{2,}):(\d{2}(?:\.\d+)?)\]", shift_time, lrc_text)