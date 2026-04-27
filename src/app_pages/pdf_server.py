import os
import socket
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Any

from loguru import logger


class _SecuredHandler(SimpleHTTPRequestHandler):
    serve_dir: str = ""

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, directory=self.serve_dir, **kwargs)

    def translate_path(self, path: str) -> str:
        translated = super().translate_path(path)
        real_serve = os.path.realpath(self.serve_dir)
        real_translated = os.path.realpath(translated)
        if (
            not real_translated.startswith(real_serve + os.sep)
            and real_translated != real_serve
        ):
            return os.path.join(real_serve, "___forbidden___")
        return translated

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug(f"[pdf-server] {format % args}")


class PdfServer:
    def __init__(self, base_url: str, port: int, serve_dir: str) -> None:
        self.base_url = base_url
        self.port = port
        self.serve_dir = serve_dir


def _find_available_port(start: int = 8502, max_tries: int = 10) -> int:
    for port in range(start, start + max_tries):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    msg = f"No available port in range {start}-{start + max_tries - 1}"
    raise RuntimeError(msg)


def start_pdf_server(serve_dir: str) -> PdfServer:
    port = _find_available_port()
    _SecuredHandler.serve_dir = serve_dir
    server = HTTPServer(("127.0.0.1", port), _SecuredHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://localhost:{port}"
    logger.info(f"[pdf-server] Serving {serve_dir} on {base_url}")
    return PdfServer(base_url=base_url, port=port, serve_dir=serve_dir)
