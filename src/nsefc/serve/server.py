"""The local server: Python standard library only.

* Binds to 127.0.0.1 only; if the port is busy, tries the next ones and reports the one used.
* ``/api/v1/*`` comes from ``data/api/v1/`` as JSON with ``Cache-Control: no-store``.
* Any other path that names a file in the prebuilt app is served with an explicit MIME type
  (Windows registry MIME types are unreliable); hashed assets are cached for a year.
* Every other path returns ``index.html`` so the app's own routes (/stocks/SCOM) work.
* Paths that would leave their root folder are refused.
"""

from __future__ import annotations

import contextlib
import errno
import os
import threading
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from nsefc.storage import UnsafePathError, safe_join

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
    ),
}


class LocalServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second server bind a port that is already in use, so a
    # busy port would go unnoticed; turn it off there.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


class NoResultsError(RuntimeError):
    """``data/api/v1/status.json`` does not exist yet."""


class Handler(BaseHTTPRequestHandler):
    server_version = "nsefc"
    sys_version = ""

    def __init__(
        self, *args: object, api_root: Path, app_root: Path, quiet: bool, **kwargs: object
    ) -> None:
        self.api_root = api_root
        self.app_root = app_root
        self.quiet = quiet
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]

    def log_message(self, format: str, *args: object) -> None:
        if not self.quiet:
            super().log_message(format, *args)

    def _send(
        self, status: HTTPStatus, body: bytes, content_type: str, cache: str, head: bool
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def _not_found(self, head: bool, message: str = "not found") -> None:
        body = ('{"error":{"code":"NOT_FOUND","message":"' + message + '"}}').encode("utf-8")
        self._send(HTTPStatus.NOT_FOUND, body, MIME[".json"], "no-store", head)

    def _handle(self, head: bool) -> None:
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/api/v1/") or path == "/api/v1":
            relative = path[len("/api/v1/") :]
            try:
                file = safe_join(self.api_root, relative)
            except UnsafePathError:
                self._not_found(head, "invalid path")
                return
            if not file.is_file() or file.suffix != ".json":
                self._not_found(head)
                return
            self._send(HTTPStatus.OK, file.read_bytes(), MIME[".json"], "no-store", head)
            return
        relative = path.lstrip("/")
        target: Path | None = None
        if relative:
            try:
                candidate = safe_join(self.app_root, relative)
            except UnsafePathError:
                self._not_found(head, "invalid path")
                return
            if candidate.is_file():
                target = candidate
        if target is None:
            target = self.app_root / "index.html"
            if not target.is_file():
                self._send(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    b"web app not built",
                    MIME[".txt"],
                    "no-store",
                    head,
                )
                return
        hashed = "/assets/" in path
        cache = "public, max-age=31536000, immutable" if hashed else "no-cache"
        self._send(
            HTTPStatus.OK,
            target.read_bytes(),
            MIME.get(target.suffix.lower(), "application/octet-stream"),
            cache,
            head,
        )

    def do_GET(self) -> None:
        self._handle(head=False)

    def do_HEAD(self) -> None:
        self._handle(head=True)


@dataclass(slots=True)
class Server:
    httpd: LocalServer
    url: str

    def serve_forever(self) -> None:
        try:
            self.httpd.serve_forever()
        finally:
            self.httpd.server_close()

    def start_in_thread(self) -> threading.Thread:
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return thread

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()


def make_server(
    api_root: Path,
    app_root: Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    port_tries: int = 10,
    quiet: bool = True,
) -> Server:
    if not (api_root / "status.json").is_file():
        raise NoResultsError("No results yet. Run `uv run nsefc run` first.")
    handler = partial(Handler, api_root=api_root, app_root=app_root, quiet=quiet)
    last_error: OSError | None = None
    for candidate in range(port, port + max(1, port_tries) + 1):
        try:
            httpd = LocalServer((host, candidate), handler)
        except OSError as exc:
            busy = {
                errno.EADDRINUSE,
                errno.EACCES,
                getattr(errno, "WSAEADDRINUSE", -1),
                getattr(errno, "WSAEACCES", -1),
            }
            if exc.errno in busy or getattr(exc, "winerror", None) in (10048, 10013):
                last_error = exc
                continue
            raise
        return Server(httpd, f"http://{host}:{httpd.server_address[1]}")
    # Every port in the range is busy or reserved (Windows reserves blocks for Hyper-V, WSL
    # and Docker): let the operating system choose a free one.
    try:
        httpd = LocalServer((host, 0), handler)
    except OSError as exc:
        raise OSError(
            f"ports {port} to {port + port_tries} are busy and no free port was found: "
            f"{last_error}; try --port"
        ) from exc
    return Server(httpd, f"http://{host}:{httpd.server_address[1]}")


def open_browser(url: str, opener: Callable[[str], bool] = webbrowser.open) -> None:
    # A missing or broken browser must never stop the server.
    with contextlib.suppress(Exception):
        opener(url)
