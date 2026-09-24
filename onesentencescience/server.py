"""Minimal local HTTP server for OneSentenceScience."""

from __future__ import annotations

import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .local_history import ChatStorage, StorageError, choose_directory
from .research import ResearchError, analyze, model_is_configured


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
MAX_ANALYZE_BYTES = 80_000
MAX_SAVE_BYTES = 3_100_000
HISTORY = ChatStorage()


class Handler(BaseHTTPRequestHandler):
    server_version = "OneSentenceScience/0.2"

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        ))
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _trusted_api_request(self) -> bool:
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        local_hosts = {f"127.0.0.1:{self.server.server_port}",
                       f"localhost:{self.server.server_port}"}
        return (host in local_hosts and
                (not origin or origin in {f"http://{name}" for name in local_hosts}) and
                self.headers.get("X-OneSentenceScience") == "1")

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "configured": model_is_configured(),
                             "version": __version__})
            return
        if path == "/api/storage" or path.startswith("/api/storage/chat/"):
            if not self._trusted_api_request():
                self._json(403, {"error": "请求来源不被允许。"})
                return
            try:
                if path == "/api/storage":
                    name = HISTORY.folder_name()
                    data = {"selected": bool(name), "folder_name": name,
                            "chats": HISTORY.list_chats() if name else []}
                else:
                    data = HISTORY.load(path.removeprefix("/api/storage/chat/"))
            except StorageError as exc:
                self._json(exc.status, {"error": str(exc)})
                return
            self._json(200, data)
            return
        if path not in STATIC_FILES:
            self._json(404, {"error": "页面不存在。"})
            return
        filename, content_type = STATIC_FILES[path]
        try:
            content = (STATIC_DIR / filename).read_bytes()
        except OSError:
            self._json(500, {"error": "网页文件暂时无法读取。"})
            return
        self._send(200, content, content_type)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        if path not in {"/api/analyze", "/api/storage/select", "/api/storage/save"}:
            self._json(404, {"error": "接口不存在。"})
            return
        if (not self._trusted_api_request() or
                self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                != "application/json"):
            self._json(403, {"error": "请求来源不被允许。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        max_bytes = MAX_SAVE_BYTES if path == "/api/storage/save" else MAX_ANALYZE_BYTES
        if not 1 <= length <= max_bytes:
            self._json(413, {"error": "输入内容过长或为空。"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json(400, {"error": "输入格式不正确。"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"error": "输入格式不正确。"})
            return
        if path == "/api/storage/select":
            try:
                selected = HISTORY.select()
                name = HISTORY.folder_name()
                data = {"selected": selected, "folder_name": name,
                        "chats": HISTORY.list_chats() if selected else []}
            except StorageError as exc:
                self._json(exc.status, {"error": str(exc)})
                return
            self._json(200, data)
            return
        if path == "/api/storage/save":
            try:
                data = HISTORY.save(payload)
            except StorageError as exc:
                self._json(exc.status, {"error": str(exc)})
                return
            self._json(200, data)
            return
        try:
            result = analyze(payload.get("observation"),
                             model_config=payload.get("model_config"),
                             history=payload.get("history"))
        except ResearchError as exc:
            self._json(exc.status, {"error": str(exc)})
            return
        except Exception:
            self._json(500, {"error": "分析时发生意外错误，请稍后再试。"})
            return
        self._json(200, result)


def main() -> None:
    try:
        port = int(os.getenv("PORT", "8765"))
    except ValueError as exc:
        raise SystemExit("PORT 必须是数字。") from exc
    if not 1 <= port <= 65535:
        raise SystemExit("PORT 必须在 1 到 65535 之间。")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    picker_requests: queue.Queue = queue.Queue()

    def pick_on_main_thread():
        request = {"event": threading.Event(), "directory": None, "error": None}
        picker_requests.put(request)
        request["event"].wait()
        if request["error"]:
            raise request["error"]
        return request["directory"]

    HISTORY.picker = pick_on_main_thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    print(f"OneSentenceScience 已启动：http://127.0.0.1:{port}", flush=True)
    if not model_is_configured():
        print("提示：可以在网页填写模型密钥；也可按 README 配置本机环境变量。", flush=True)
    try:
        while True:
            try:
                request = picker_requests.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                request["directory"] = choose_directory()
            except Exception as exc:
                request["error"] = exc
            finally:
                request["event"].set()
    except KeyboardInterrupt:
        pass
    finally:
        HISTORY.picker = None
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2)


if __name__ == "__main__":
    main()
