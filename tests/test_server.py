import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from onesentencescience.server import HISTORY, Handler


CHAT_ID = "12345678-1234-4234-8234-123456789abc"


class ServerSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request_status(self, headers):
        request = Request(
            f"http://127.0.0.1:{self.server.server_port}/api/analyze",
            data=json.dumps({"observation": "太短"}).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
        )
        try:
            with urlopen(request, timeout=3) as response:
                return response.status
        except HTTPError as exc:
            return exc.code

    def test_rejects_cross_site_post_before_reading_body(self):
        self.assertEqual(self.request_status({}), 403)
        self.assertEqual(self.request_status({"X-OneSentenceScience": "1",
                                              "Origin": "http://example.com"}), 403)
        self.assertEqual(self.request_status({"X-OneSentenceScience": "1"}), 400)

    def test_selected_folder_api_saves_and_reopens_a_chat(self):
        with tempfile.TemporaryDirectory() as directory:
            HISTORY.directory = Path(directory)
            try:
                chat = {"format": "onesentencescience-chat", "version": 1,
                        "id": CHAT_ID, "title": "散步与谈心",
                        "created_at": "2026-09-24T00:00:00Z",
                        "updated_at": "2026-09-24T00:00:00Z",
                        "turns": [{"observation": "散步时更容易谈心。",
                                   "created_at": "2026-09-24T00:00:00Z",
                                   "report": {"phenomenon": "散步与谈心。",
                                              "research_question": "散步与自我表达有关吗？",
                                              "result": {"verdict": "insufficient",
                                                         "conclusion": "证据不足。",
                                                         "claims": [], "other_explanations": [],
                                                         "limitations": [],
                                                         "next_step": "继续查证。"},
                                              "sources": []}}]}
                base = f"http://127.0.0.1:{self.server.server_port}"
                request = Request(base + "/api/storage/save",
                                  data=json.dumps(chat).encode("utf-8"),
                                  headers={"Content-Type": "application/json",
                                           "X-OneSentenceScience": "1"})
                with urlopen(request, timeout=3) as response:
                    self.assertEqual(response.status, 200)
                for path in ("/api/storage", f"/api/storage/chat/{CHAT_ID}"):
                    request = Request(base + path,
                                      headers={"X-OneSentenceScience": "1"})
                    with urlopen(request, timeout=3) as response:
                        data = json.load(response)
                        self.assertEqual(response.status, 200)
                        self.assertTrue(data)
            finally:
                HISTORY.directory = None


if __name__ == "__main__":
    unittest.main()
