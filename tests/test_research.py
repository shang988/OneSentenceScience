import unittest
from unittest.mock import patch

from onesentencescience.research import (
    ResearchError,
    analyze,
    call_model,
    model_settings,
    reconstruct_abstract,
    search_papers,
)


PAPER = {
    "id": "https://openalex.org/W123456789",
    "title": "Walking and conversational self-disclosure",
    "publication_year": 2022,
    "doi": "https://doi.org/10.1234/example",
    "abstract_inverted_index": {
        "Walking": [0], "was": [1], "associated": [2], "with": [3],
        "greater": [4], "self-disclosure": [5], "during": [6], "conversation": [7],
        "in": [8], "one": [9], "small": [10], "sample": [11], ".": [12],
        "The": [13], "study": [14], "did": [15], "not": [16],
        "establish": [17], "a": [18], "causal": [19], "effect": [20],
        "and": [21], "further": [22], "research": [23], "is": [24],
        "needed": [25], "before": [26], "generalizing": [27], "the": [28],
        "finding": [29], "to": [30], "other": [31], "contexts": [32],
    },
}


class FakeModel:
    def __init__(self, invented_citation=False):
        self.calls = 0
        self.invented_citation = invented_citation
        self.first_messages = None

    def __call__(self, messages, max_tokens=1200):
        self.calls += 1
        if self.calls == 1:
            self.first_messages = messages
            return {
                "phenomenon": "和朋友散步时似乎更容易谈起心事。",
                "research_question": "散步与谈话中的自我表达是否有关？",
                "search_queries": ["walking conversational self disclosure"],
            }
        return {
            "verdict": "initial_support",
            "conclusion": "一项研究提示散步与更多的自我表达有关，但无法证明因果关系。",
            "claims": [{"text": "散步与更多的自我表达相关。",
                        "source_ids": ["S99" if self.invented_citation else "S1"]}],
            "other_explanations": ["朋友关系也可能影响谈话深度。"],
            "limitations": ["摘要无法展示研究的全部细节。"],
            "next_step": "阅读全文并核对研究方法。",
        }


class ResearchTests(unittest.TestCase):
    def test_reconstructs_openalex_abstract(self):
        self.assertEqual(reconstruct_abstract({"help": [2, 0], "can": [1]}),
                         "help can help")

    def test_search_deduplicates_and_preserves_verified_url(self):
        def fetcher(url, timeout=25):
            self.assertIn("api.openalex.org/works", url)
            return {"results": [PAPER, PAPER]}

        papers = search_papers(["walking conversational self disclosure"], fetcher=fetcher)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["id"], "S1")
        self.assertEqual(papers[0]["url"], "https://doi.org/10.1234/example")

    def test_a_plain_sentence_can_produce_a_cited_conditional_answer(self):
        model = FakeModel()
        paper = search_papers(["walking conversational self disclosure"],
                              fetcher=lambda url, timeout=25: {"results": [PAPER]})[0]
        result = analyze("我发现和朋友一起散步时，比坐下来聊天更容易谈起心事。",
                         model=model, search=lambda queries: [paper])
        self.assertEqual(model.calls, 2)
        self.assertEqual(result["result"]["verdict"], "initial_support")
        self.assertEqual(result["result"]["claims"][0]["source_ids"], ["S1"])
        self.assertNotIn("abstract", result["sources"][0])

    def test_fabricated_reference_cannot_support_a_conclusion(self):
        model = FakeModel(invented_citation=True)
        paper = search_papers(["walking conversational self disclosure"],
                              fetcher=lambda url, timeout=25: {"results": [PAPER]})[0]
        result = analyze("我发现和朋友一起散步时，比坐下来聊天更容易谈起心事。",
                         model=model, search=lambda queries: [paper])
        self.assertEqual(result["result"]["verdict"], "insufficient")
        self.assertEqual(result["result"]["claims"], [])
        self.assertNotIn("一项研究提示", result["result"]["conclusion"])

    def test_short_input_is_rejected_before_external_calls(self):
        with self.assertRaises(ResearchError) as error:
            analyze("有点怪", model=FakeModel(), search=lambda queries: [])
        self.assertEqual(error.exception.status, 400)

    def test_page_model_settings_reject_remote_plain_http(self):
        config = {"base_url": "https://api.openai.com/v1",
                  "model": "gpt-4.1-mini", "api_key": "test-key"}
        self.assertEqual(model_settings(config),
                         ("https://api.openai.com/v1", "gpt-4.1-mini", "test-key"))
        config["base_url"] = "http://example.com/v1"
        with self.assertRaises(ResearchError) as error:
            model_settings(config)
        self.assertEqual(error.exception.status, 400)

    def test_page_key_is_used_for_one_model_request(self):
        config = {"base_url": "https://api.openai.com/v1",
                  "model": "gpt-4.1-mini", "api_key": "test-key"}
        with patch("onesentencescience.research.fetch_json", return_value={
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }) as fetcher:
            self.assertEqual(call_model([{"role": "user", "content": "test"}], config=config),
                             {"ok": True})
        self.assertEqual(fetcher.call_args.kwargs["headers"]["Authorization"],
                         "Bearer test-key")
        self.assertEqual(fetcher.call_args.args[0],
                         "https://api.openai.com/v1/chat/completions")

    def test_followup_uses_previous_turn_only_as_context(self):
        model = FakeModel()
        paper = search_papers(["walking conversational self disclosure"],
                              fetcher=lambda url, timeout=25: {"results": [PAPER]})[0]
        analyze("为什么？", model=model, search=lambda queries: [paper],
                history=[{"observation": "和朋友散步更容易谈心。",
                          "research_question": "散步与自我表达是否有关？",
                          "conclusion": "只有初步线索。"}])
        self.assertIn("和朋友散步更容易谈心。", model.first_messages[1]["content"])
        self.assertIn("为什么？", model.first_messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
