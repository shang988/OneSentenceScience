import unittest

from onesentencescience.research import (
    ResearchError,
    analyze,
    reconstruct_abstract,
    search_papers,
)


PAPER = {
    "id": "https://openalex.org/W123456789",
    "title": "Overtime and workplace helping behavior",
    "publication_year": 2022,
    "doi": "https://doi.org/10.1234/example",
    "abstract_inverted_index": {
        "Overtime": [0], "was": [1], "associated": [2], "with": [3],
        "lower": [4], "helping": [5], "behavior": [6], "in": [7],
        "one": [8], "workplace": [9], "sample": [10], ".": [11],
        "The": [12], "study": [13], "did": [14], "not": [15],
        "establish": [16], "a": [17], "causal": [18], "effect": [19],
        "and": [20], "further": [21], "research": [22], "is": [23],
        "needed": [24], "before": [25], "generalizing": [26], "the": [27],
        "finding": [28], "to": [29], "other": [30], "contexts": [31],
    },
}


class FakeModel:
    def __init__(self, invented_citation=False):
        self.calls = 0
        self.invented_citation = invented_citation

    def __call__(self, messages, max_tokens=1200):
        self.calls += 1
        if self.calls == 1:
            return {
                "phenomenon": "连续加班后，同事似乎更少互相帮忙。",
                "research_question": "加班时间与工作中的互助行为是否有关？",
                "search_queries": ["overtime workplace helping behavior"],
            }
        return {
            "verdict": "initial_support",
            "conclusion": "一项研究提示加班与互助减少有关，但无法证明因果关系。",
            "claims": [{"text": "加班与较少的互助行为相关。",
                        "source_ids": ["S99" if self.invented_citation else "S1"]}],
            "other_explanations": ["工作压力也可能影响互助。"],
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

        papers = search_papers(["overtime workplace helping behavior"], fetcher=fetcher)
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["id"], "S1")
        self.assertEqual(papers[0]["url"], "https://doi.org/10.1234/example")

    def test_a_plain_sentence_can_produce_a_cited_conditional_answer(self):
        model = FakeModel()
        paper = search_papers(["overtime workplace helping behavior"],
                              fetcher=lambda url, timeout=25: {"results": [PAPER]})[0]
        result = analyze("工地连续加班后，大家似乎更不愿意互相帮忙。",
                         model=model, search=lambda queries: [paper])
        self.assertEqual(model.calls, 2)
        self.assertEqual(result["result"]["verdict"], "initial_support")
        self.assertEqual(result["result"]["claims"][0]["source_ids"], ["S1"])
        self.assertNotIn("abstract", result["sources"][0])

    def test_fabricated_reference_cannot_support_a_conclusion(self):
        model = FakeModel(invented_citation=True)
        paper = search_papers(["overtime workplace helping behavior"],
                              fetcher=lambda url, timeout=25: {"results": [PAPER]})[0]
        result = analyze("工地连续加班后，大家似乎更不愿意互相帮忙。",
                         model=model, search=lambda queries: [paper])
        self.assertEqual(result["result"]["verdict"], "insufficient")
        self.assertEqual(result["result"]["claims"], [])
        self.assertNotIn("一项研究提示", result["result"]["conclusion"])

    def test_short_input_is_rejected_before_external_calls(self):
        with self.assertRaises(ResearchError) as error:
            analyze("有点怪", model=FakeModel(), search=lambda queries: [])
        self.assertEqual(error.exception.status, 400)


if __name__ == "__main__":
    unittest.main()
