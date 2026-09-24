"""User-selected local JSON conversation storage."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from uuid import UUID


PREFIX = "OneSentenceScience-"
MAX_FILE_BYTES = 3_000_000


class StorageError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def choose_directory() -> Path | None:
    """Ask the local operating system for a folder; never accept a path from HTTP."""
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        try:
            selected = filedialog.askdirectory(
                parent=root, mustexist=True, title="选择 OneSentenceScience 聊天文件夹")
        finally:
            root.destroy()
    except Exception as exc:
        raise StorageError("无法打开系统文件夹选择窗口；请改用浏览器导入或下载 JSON。", 503) from exc
    return Path(selected).resolve() if selected else None


def _short(value, length: int) -> str:
    return value[:length] if isinstance(value, str) else ""


def _string_list(value, limit: int, length: int) -> list[str]:
    return [_short(item, length) for item in value[:limit] if isinstance(item, str)] \
        if isinstance(value, list) else []


def _valid_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except ValueError:
        return False


def _clean_report(raw: dict) -> dict:
    if not isinstance(raw, dict) or not isinstance(raw.get("result"), dict):
        raise StorageError("聊天文件格式不正确。")
    result = raw["result"]
    claims = []
    for item in result.get("claims", [])[:3] if isinstance(result.get("claims"), list) else []:
        if isinstance(item, dict):
            claims.append({"text": _short(item.get("text"), 360),
                           "source_ids": _string_list(item.get("source_ids"), 7, 12)})
    sources = []
    for item in raw.get("sources", [])[:7] if isinstance(raw.get("sources"), list) else []:
        if isinstance(item, dict):
            sources.append({"id": _short(item.get("id"), 12),
                            "title": _short(item.get("title"), 240),
                            "year": item.get("year") if isinstance(item.get("year"), int) else None,
                            "url": _short(item.get("url"), 500),
                            "openalex_url": _short(item.get("openalex_url"), 500)})
    verdict = result.get("verdict")
    if not isinstance(verdict, str) or verdict not in {
            "initial_support", "mixed", "insufficient"}:
        verdict = "insufficient"
    return {
        "observation": _short(raw.get("observation"), 500),
        "phenomenon": _short(raw.get("phenomenon"), 220),
        "research_question": _short(raw.get("research_question"), 220),
        "search_queries": _string_list(raw.get("search_queries"), 2, 90),
        "result": {
            "verdict": verdict,
            "conclusion": _short(result.get("conclusion"), 420),
            "claims": claims,
            "other_explanations": _string_list(result.get("other_explanations"), 3, 220),
            "limitations": _string_list(result.get("limitations"), 3, 220),
            "next_step": _short(result.get("next_step"), 300),
        },
        "sources": sources,
        "method_note": _short(raw.get("method_note"), 500),
    }


def clean_chat(raw: dict) -> dict:
    """Keep only public report fields, so credentials cannot enter saved files."""
    if (not isinstance(raw, dict) or raw.get("format") != "onesentencescience-chat" or
            raw.get("version") != 1 or not _valid_id(raw.get("id")) or
            not isinstance(raw.get("turns"), list) or len(raw["turns"]) > 100):
        raise StorageError("聊天文件格式不正确。")
    turns = []
    for item in raw["turns"]:
        if not isinstance(item, dict):
            raise StorageError("聊天文件格式不正确。")
        turns.append({"observation": _short(item.get("observation"), 500),
                      "created_at": _short(item.get("created_at"), 40),
                      "report": _clean_report(item.get("report"))})
    return {"format": "onesentencescience-chat", "version": 1, "id": raw["id"],
            "title": _short(raw.get("title"), 60),
            "created_at": _short(raw.get("created_at"), 40),
            "updated_at": _short(raw.get("updated_at"), 40),
            "turns": turns}


class ChatStorage:
    def __init__(self):
        self.directory: Path | None = None
        self.picker = None
        self.lock = threading.RLock()
        self.picker_lock = threading.Lock()

    def select(self) -> bool:
        if not self.picker_lock.acquire(blocking=False):
            raise StorageError("文件夹选择窗口已经打开。", 409)
        try:
            directory = (self.picker or choose_directory)()
            if directory is None:
                return False
            if not directory.is_dir():
                raise StorageError("所选文件夹无法读取。")
            with self.lock:
                self.directory = directory
            return True
        finally:
            self.picker_lock.release()

    def _folder(self) -> Path:
        with self.lock:
            directory = self.directory
        if directory is None:
            raise StorageError("请先选择聊天文件夹。", 409)
        return directory

    def folder_name(self) -> str | None:
        with self.lock:
            return self.directory.name if self.directory else None

    def _path(self, chat_id: str) -> Path:
        if not _valid_id(chat_id):
            raise StorageError("聊天编号无效。", 400)
        return self._folder() / f"{PREFIX}{chat_id}.json"

    def load(self, chat_id: str) -> dict:
        path = self._path(chat_id)
        if path.is_symlink() or not path.is_file():
            raise StorageError("找不到这段聊天。", 404)
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                raise StorageError("聊天文件过大。", 413)
            raw = json.loads(path.read_text(encoding="utf-8"))
            chat = clean_chat(raw)
            if chat["id"] != chat_id:
                raise StorageError("聊天文件编号不一致。", 400)
            return chat
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError("聊天文件无法读取。", 400) from exc

    def list_chats(self) -> list[dict]:
        directory = self._folder()
        chats = []
        try:
            paths = directory.glob(f"{PREFIX}*.json")
            for path in paths:
                if len(chats) >= 200:
                    break
                chat_id = path.name[len(PREFIX):-5]
                if not _valid_id(chat_id) or path.is_symlink():
                    continue
                try:
                    chat = self.load(chat_id)
                except StorageError:
                    continue
                chats.append({"id": chat["id"], "title": chat["title"],
                              "created_at": chat["created_at"],
                              "updated_at": chat["updated_at"],
                              "turn_count": len(chat["turns"])})
        except OSError as exc:
            raise StorageError("无法列出聊天文件。", 500) from exc
        chats.sort(key=lambda chat: chat["updated_at"], reverse=True)
        return chats

    def save(self, raw: dict) -> dict:
        chat = clean_chat(raw)
        path = self._path(chat["id"])
        content = json.dumps(chat, ensure_ascii=False, indent=2).encode("utf-8")
        if len(content) > MAX_FILE_BYTES:
            raise StorageError("聊天文件过大。", 413)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                    mode="wb", dir=path.parent, prefix=".OneSentenceScience-",
                    suffix=".tmp", delete=False) as temp:
                temp_path = Path(temp.name)
                temp.write(content)
            os.replace(temp_path, path)
        except OSError as exc:
            raise StorageError("聊天文件保存失败，请检查文件夹权限。", 500) from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
        return {"id": chat["id"], "turn_count": len(chat["turns"])}
