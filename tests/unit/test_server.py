"""The local server (§15.5): standard library, 127.0.0.1, JSON API, SPA fallback, no escapes."""

from __future__ import annotations

import http.client
import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from nsefc.serve import NoResultsError, make_server, open_browser
from nsefc.serve.server import Server


@pytest.fixture
def roots(tmp_path: Path) -> tuple[Path, Path]:
    api, app = tmp_path / "api" / "v1", tmp_path / "web"
    (api / "r" / "x").mkdir(parents=True)
    (api / "status.json").write_text('{"release_id": "x"}', encoding="utf-8")
    (api / "r" / "x" / "stocks.json").write_text('{"items": []}', encoding="utf-8")
    (app / "assets").mkdir(parents=True)
    (app / "index.html").write_text("<!doctype html><div id=root></div>", encoding="utf-8")
    (app / "assets" / "index-abc.js").write_text("console.log(1)", encoding="utf-8")
    (app / "assets" / "index-abc.css").write_text("body{}", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    return api, app


@pytest.fixture
def server(roots: tuple[Path, Path]) -> Iterator[Server]:
    srv = make_server(*roots, port=0, port_tries=1)
    srv.start_in_thread()
    yield srv
    srv.stop()


def get(server: Server, path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    host, port = server.url.removeprefix("http://").split(":")
    conn = http.client.HTTPConnection(host, int(port), timeout=5)
    conn.request(method, path)  # the path is sent as is, without normalisation
    response = conn.getresponse()
    body = response.read()
    headers = {k.lower(): v for k, v in response.getheaders()}
    conn.close()
    return response.status, headers, body


def test_binds_to_localhost_only(server: Server) -> None:
    assert server.url.startswith("http://127.0.0.1:")


def test_api_files_are_json_and_never_cached(server: Server) -> None:
    status, headers, body = get(server, "/api/v1/status.json")
    assert status == 200 and json.loads(body) == {"release_id": "x"}
    assert headers["content-type"] == "application/json; charset=utf-8"
    assert headers["cache-control"] == "no-store"
    assert get(server, "/api/v1/r/x/stocks.json")[0] == 200


def test_unknown_api_paths_are_404_json(server: Server) -> None:
    status, _headers, body = get(server, "/api/v1/r/x/missing.json")
    assert status == 404 and json.loads(body)["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/../../secret.txt",
        "/api/v1/..%2f..%2fsecret.txt",
        "/../secret.txt",
        "/assets/../../secret.txt",
    ],
)
def test_path_traversal_is_refused(server: Server, path: str) -> None:
    status, _headers, body = get(server, path)
    assert b"do not serve" not in body
    assert status in (404, 200)  # 200 only for the app's index.html fallback
    if status == 200:
        assert body.startswith(b"<!doctype html>")


def test_app_routes_fall_back_to_index(server: Server) -> None:
    for path in ("/", "/stocks/SCOM", "/about"):
        status, headers, body = get(server, path)
        assert status == 200 and body.startswith(b"<!doctype html>")
        assert headers["content-type"] == "text/html; charset=utf-8"
        assert headers["cache-control"] == "no-cache"


def test_assets_have_explicit_types_and_long_caching(server: Server) -> None:
    status, headers, _ = get(server, "/assets/index-abc.js")
    assert status == 200 and headers["content-type"] == "text/javascript; charset=utf-8"
    assert "immutable" in headers["cache-control"]
    assert get(server, "/assets/index-abc.css")[1]["content-type"] == "text/css; charset=utf-8"


def test_security_headers_and_head(server: Server) -> None:
    status, headers, body = get(server, "/api/v1/status.json", method="HEAD")
    assert status == 200 and body == b""
    assert headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]


def test_no_results_yet(tmp_path: Path) -> None:
    with pytest.raises(NoResultsError, match="nsefc run"):
        make_server(tmp_path / "api", tmp_path / "web")


def test_a_busy_port_moves_to_the_next(roots: tuple[Path, Path]) -> None:
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy = blocker.getsockname()[1]
    try:
        srv = make_server(*roots, port=busy, port_tries=10)
        try:
            assert not srv.url.endswith(f":{busy}")
        finally:
            srv.httpd.server_close()
    finally:
        blocker.close()


def test_a_missing_browser_never_stops_the_server() -> None:
    def broken(_url: str) -> bool:
        raise RuntimeError("no browser")

    open_browser("http://127.0.0.1:1", opener=broken)
