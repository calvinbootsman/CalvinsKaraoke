import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from config import MUSIC_DIR

_MEDIA_SERVER: ThreadingHTTPServer | None = None
_MEDIA_SERVER_THREAD: threading.Thread | None = None
_SERVER_LOCK = threading.Lock()


class QuietMediaRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        # Inject the CORS header so Web Audio API can read the files!
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

    def send_head(self):
        import os
        path = self.translate_path(self.path)
        f = None
        try:
            f = open(path, 'rb')
        except OSError:
            self.send_error(404, "File not found")
            return None
            
        ctype = self.guess_type(path)
        fs = os.fstat(f.fileno())
        size = int(fs.st_size)
        
        range_header = self.headers.get("Range", "")
        if range_header.startswith("bytes="):
            ranges = range_header.replace("bytes=", "").split("-")
            start = int(ranges[0]) if ranges[0] else 0
            end = int(ranges[1]) if len(ranges) > 1 and ranges[1] else size - 1
            length = end - start + 1

            self.send_response(206)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Content-Length", str(length))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            
            f.seek(start)
            self.range_limit = length
            return f

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(size))
        self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
        self.end_headers()
        self.range_limit = size
        return f

    def copyfile(self, source, outputfile) -> None:
        try:
            if hasattr(self, 'range_limit'):
                left = self.range_limit
                while left > 0:
                    chunk_size = min(64 * 1024, left)
                    buf = source.read(chunk_size)
                    if not buf:
                        break
                    outputfile.write(buf)
                    left -= len(buf)
            else:
                super().copyfile(source, outputfile)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, format: str, *args: object) -> None:
        pass

    def log_error(self, format: str, *args: object) -> None:
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


