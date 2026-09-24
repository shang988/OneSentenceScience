"""Minimal local HTTP server for OneSentenceScience."""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from . import __version__
from .research import ResearchError, analyze, model_is_configured


STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}


class Handler(BaseHTTPRequestHandler):
    server_version = "OneSentenceScience/0.1"

    def _send(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", (
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "base-uri 'none'; form-action 'self'"
        ))
        if content_type.startswith("application/json"):
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, data: dict) -> None:
        self._send(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "configured": model_is_configured(),
                             "version": __version__})
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
        if urlsplit(self.path).path != "/api/analyze":
            self._json(404, {"error": "接口不存在。"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 1 <= length <= 4096:
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
        try:
            result = analyze(payload.get("observation"))
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
    print(f"OneSentenceScience 已启动：http://127.0.0.1:{port}", flush=True)
    if not model_is_configured():
        print("提示：请按 README 配置 LLM_BASE_URL 和 LLM_MODEL。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
