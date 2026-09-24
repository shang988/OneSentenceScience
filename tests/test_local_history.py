import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from onesentencescience.local_history import ChatStorage, StorageError


CHAT_ID = "12345678-1234-4234-8234-123456789abc"


class LocalHistoryTests(unittest.TestCase):
    def test_selected_folder_saves_loads_and_omits_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = ChatStorage()
            with patch("onesentencescience.local_history.choose_directory",
                       return_value=Path(directory)):
                self.assertTrue(storage.select())
            chat = {
                "format": "onesentencescience-chat", "version": 1,
                "id": CHAT_ID, "title": "散步时更容易谈心",
                "created_at": "2026-09-24T00:00:00Z",
                "updated_at": "2026-09-24T00:00:00Z",
                "model_config": {"api_key": "must-not-be-saved"},
                "turns": [{
                    "observation": "散步时更容易谈心。",
                    "created_at": "2026-09-24T00:00:00Z",
                    "report": {
                        "observation": "散步时更容易谈心。",
                        "phenomenon": "散步与谈心有关。",
                        "research_question": "散步与自我表达有关吗？",
                        "search_queries": ["walking self disclosure"],
                        "result": {"verdict": "insufficient", "conclusion": "证据不足。",
                                   "claims": [], "other_explanations": [],
                                   "limitations": [], "next_step": "继续查找资料。"},
                        "sources": [], "method_note": "摘要分析。",
                        "api_key": "must-not-be-saved",
                    },
                }],
            }
            storage.save(chat)
            saved_file = Path(directory) / f"OneSentenceScience-{CHAT_ID}.json"
            self.assertTrue(saved_file.exists())
            self.assertNotIn("must-not-be-saved", saved_file.read_text(encoding="utf-8"))
            self.assertEqual(storage.load(CHAT_ID)["turns"][0]["report"]["result"]
                             ["conclusion"], "证据不足。")
            self.assertEqual(storage.list_chats()[0]["turn_count"], 1)

    def test_chat_id_cannot_escape_selected_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = ChatStorage()
            storage.directory = Path(directory)
            with self.assertRaises(StorageError):
                storage.load("../secrets")


if __name__ == "__main__":
    unittest.main()
