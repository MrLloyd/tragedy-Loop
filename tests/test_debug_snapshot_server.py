from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from ui.debug_snapshot_server import ReadOnlyDebugSnapshotServer


def test_read_only_debug_snapshot_server_serves_snapshot_and_rejects_writes() -> None:
    server = ReadOnlyDebugSnapshotServer(lambda: {"status": "ok", "value": 42})
    server.start()
    if not server.is_running:
        pytest.skip(f"local TCP sockets are unavailable: {server.start_error}")
    try:
        with urlopen(server.snapshot_url) as response:
            payload = json.loads(response.read().decode("utf-8"))
        assert payload["value"] == 42

        request = Request(
            server.snapshot_url,
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            urlopen(request)
        except HTTPError as exc:
            assert exc.code == 405
            error_payload = json.loads(exc.read().decode("utf-8"))
            assert error_payload["error"] == "read_only"
        else:
            raise AssertionError("expected POST to be rejected")
    finally:
        server.close()
