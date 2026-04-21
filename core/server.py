import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from config import MUSIC_DIR

_MEDIA_SERVER: ThreadingHTTPServer | None = None
_MEDIA_SERVER_THREAD: threading.Thread | None = None
_SERVER_LOCK = threading.Lock()


class QuietMediaRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        del format, args

    def log_error(self, format: str, *args: object) -> None:
        del format, args

    def copyfile(self, source, outputfile) -> None:
        try:
            super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError):
            pass


def ensure_media_server() -> str:
    global _MEDIA_SERVER, _MEDIA_SERVER_THREAD

    with _SERVER_LOCK:
        if _MEDIA_SERVER is None:
            handler_cls = partial(QuietMediaRequestHandler, directory=str(MUSIC_DIR.resolve()))
            _MEDIA_SERVER = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
            _MEDIA_SERVER_THREAD = threading.Thread(target=_MEDIA_SERVER.serve_forever, daemon=True)
            _MEDIA_SERVER_THREAD.start()

    return f"http://127.0.0.1:{_MEDIA_SERVER.server_port}"
