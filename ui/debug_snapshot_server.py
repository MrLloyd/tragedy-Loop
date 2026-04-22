from __future__ import annotations

import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class ReadOnlyDebugSnapshotServer:
    """本地只读调试快照 HTTP 出口。"""

    def __init__(
        self,
        snapshot_provider: Callable[[], dict[str, Any]],
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        self._snapshot_provider = snapshot_provider
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._start_error: str = ""

    @property
    def base_url(self) -> str:
        if self._server is None:
            return ""
        host, port = self._server.server_address[:2]
        return f"http://{host}:{port}"

    @property
    def snapshot_url(self) -> str:
        base_url = self.base_url
        return f"{base_url}/snapshot" if base_url else ""

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def start_error(self) -> str:
        return self._start_error

    def start(self) -> None:
        if self._server is not None:
            return

        provider = self._snapshot_provider

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._write_json(HTTPStatus.OK, {"status": "ok"})
                    return
                if self.path == "/":
                    self._write_json(
                        HTTPStatus.OK,
                        {
                            "status": "ok",
                            "snapshot_url": "/snapshot",
                            "health_url": "/health",
                        },
                    )
                    return
                if self.path == "/snapshot":
                    try:
                        payload = provider()
                    except Exception as exc:
                        self._write_json(
                            HTTPStatus.INTERNAL_SERVER_ERROR,
                            {"error": str(exc)},
                        )
                        return
                    self._write_json(HTTPStatus.OK, payload)
                    return
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                self._write_json(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    {"error": "read_only"},
                )

            def do_PUT(self) -> None:  # noqa: N802
                self.do_POST()

            def do_DELETE(self) -> None:  # noqa: N802
                self.do_POST()

            def log_message(self, format: str, *args: object) -> None:
                return

            def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
                body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
                self.send_response(status.value)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self._start_error = ""
        try:
            self._server = ThreadingHTTPServer((self._host, self._port), _Handler)
        except OSError as exc:
            self._start_error = str(exc)
            self._server = None
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="debug-snapshot-server",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._server = None
        self._thread = None
