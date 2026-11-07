import unittest
from unittest import mock

from fastapi.testclient import TestClient

from app.hybrid_search import reciprocal_rank_fusion, search_hybrid
from app.lexical_search import LexicalIndexNotReadyError
from app.main import app
from app.search import EmbeddingsNotReadyError

REPO = "owner/repo"
REPO_URL = "https://github.com/owner/repo"


def make_result(file_path, start_line=1, end_line=10, content="code", **extra):
    result = {
        "file_path": file_path,
        "chunk_index": 0,
        "start_line": start_line,
        "end_line": end_line,
        "content": content,
    }
    result.update(extra)
    return result


A = make_result("src/a.js", content="function alpha() {}")
B = make_result("src/b.js", content="function beta() {}")
C = make_result("src/c.js", content="function gamma() {}")
D = make_result("src/d.js", content="function delta() {}")


def by_path(results):
    return {result["file_path"]: result for result in results}


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_chunk_in_both_systems_outranks_singletons(self):
        fused = reciprocal_rank_fusion([A, B, C], [B, A, D])

        self.assertEqual(len(fused), 4)
        entries = by_path(fused)
        self.assertEqual(
            {r["file_path"] for r in fused[:2]},
            {"src/a.js", "src/b.js"},
        )
        self.assertEqual(
            {r["file_path"] for r in fused[2:]},
            {"src/c.js", "src/d.js"},
        )
        self.assertAlmostEqual(entries["src/a.js"]["rrf_score"], 1 / 61 + 1 / 62)
        self.assertAlmostEqual(entries["src/b.js"]["rrf_score"], 1 / 62 + 1 / 61)
        self.assertAlmostEqual(entries["src/c.js"]["rrf_score"], 1 / 63)
        self.assertAlmostEqual(entries["src/d.js"]["rrf_score"], 1 / 63)
        self.assertEqual(
            entries["src/a.js"]["retrieved_by"], ["semantic", "bm25"]
        )
        self.assertEqual(
            entries["src/b.js"]["retrieved_by"], ["semantic", "bm25"]
        )
        self.assertEqual(entries["src/c.js"]["retrieved_by"], ["semantic"])
        self.assertEqual(entries["src/d.js"]["retrieved_by"], ["bm25"])

    def test_identical_rankings(self):
        fused = reciprocal_rank_fusion([A, B, C], [A, B, C])

        self.assertEqual(
            [r["file_path"] for r in fused],
            ["src/a.js", "src/b.js", "src/c.js"],
        )
        for rank, entry in enumerate(fused, start=1):
            self.assertAlmostEqual(entry["rrf_score"], 2 / (60 + rank))
            self.assertEqual(entry["retrieved_by"], ["semantic", "bm25"])

    def test_different_rankings(self):
        fused = reciprocal_rank_fusion([A, B, C], [C, B, A])

        self.assertEqual(
            [r["file_path"] for r in fused],
            ["src/a.js", "src/c.js", "src/b.js"],
        )
        entries = by_path(fused)
        self.assertAlmostEqual(entries["src/a.js"]["rrf_score"], 1 / 61 + 1 / 63)
        self.assertAlmostEqual(entries["src/b.js"]["rrf_score"], 2 / 62)
        self.assertGreater(
            entries["src/a.js"]["rrf_score"], entries["src/b.js"]["rrf_score"]
        )

    def test_custom_k_and_one_based_ranks(self):
        fused = reciprocal_rank_fusion([A], [A], k=0)

        self.assertAlmostEqual(fused[0]["rrf_score"], 2.0)

    def test_no_overlapping_results(self):
        fused = reciprocal_rank_fusion([A, B], [C, D])

        self.assertEqual(len(fused), 4)
        entries = by_path(fused)
        self.assertAlmostEqual(entries["src/a.js"]["rrf_score"], 1 / 61)
        self.assertAlmostEqual(entries["src/b.js"]["rrf_score"], 1 / 62)
        self.assertAlmostEqual(entries["src/c.js"]["rrf_score"], 1 / 61)
        self.assertAlmostEqual(entries["src/d.js"]["rrf_score"], 1 / 62)
        self.assertEqual(entries["src/a.js"]["retrieved_by"], ["semantic"])
        self.assertEqual(entries["src/c.js"]["retrieved_by"], ["bm25"])
        self.assertGreater(fused[0]["rrf_score"], fused[2]["rrf_score"])

    def test_duplicate_chunks_merge_metadata_and_scores(self):
        semantic = make_result("src/a.js", similarity=0.9)
        lexical = make_result(
            "src/a.js", bm25_score=2.5, symbol="alpha", chunk_id="src/a.js@1-10"
        )

        fused = reciprocal_rank_fusion([semantic], [lexical])

        self.assertEqual(len(fused), 1)
        entry = fused[0]
        self.assertAlmostEqual(entry["rrf_score"], 2 / 61)
        self.assertEqual(entry["retrieved_by"], ["semantic", "bm25"])
        self.assertEqual(entry["similarity"], 0.9)
        self.assertEqual(entry["bm25_score"], 2.5)
        self.assertEqual(entry["symbol"], "alpha")
        self.assertEqual(entry["content"], semantic["content"])

    def test_identity_includes_file_path_and_lines(self):
        other_line = make_result("src/a.js", start_line=11, end_line=20)
        other_file = make_result("src/b.js", chunk_index=0)

        fused = reciprocal_rank_fusion([A, other_line, other_file], [])

        self.assertEqual(len(fused), 3)

    def test_empty_results(self):
        self.assertEqual(reciprocal_rank_fusion([], []), [])

        only_semantic = reciprocal_rank_fusion([A], [])
        self.assertEqual(len(only_semantic), 1)
        self.assertEqual(only_semantic[0]["retrieved_by"], ["semantic"])

        only_lexical = reciprocal_rank_fusion([], [A])
        self.assertEqual(len(only_lexical), 1)
        self.assertEqual(only_lexical[0]["retrieved_by"], ["bm25"])

    def test_raw_scores_do_not_affect_rrf(self):
        high = make_result("src/a.js", similarity=0.99, bm25_score=100.0)
        low = make_result("src/b.js", similarity=0.01, bm25_score=0.1)

        fused = reciprocal_rank_fusion([high, low], [])

        self.assertAlmostEqual(fused[0]["rrf_score"], 1 / 61)
        self.assertAlmostEqual(fused[1]["rrf_score"], 1 / 62)


class SearchHybridTests(unittest.TestCase):
    def test_calls_both_systems_and_fuses(self):
        with (
            mock.patch(
                "app.hybrid_search.search_chunks", return_value=(7, [A, B])
            ) as semantic,
            mock.patch(
                "app.hybrid_search.search_lexical", return_value=(7, [B, C])
            ) as lexical,
        ):
            total, results = search_hybrid(REPO, "query")

        semantic.assert_called_once_with(REPO, "query", limit=15)
        lexical.assert_called_once_with(REPO, "query", limit=15)
        self.assertEqual(total, 7)
        self.assertEqual(
            [r["file_path"] for r in results],
            ["src/b.js", "src/a.js", "src/c.js"],
        )
        self.assertEqual(results[0]["retrieved_by"], ["semantic", "bm25"])

    def test_limit_applied_to_fused_results(self):
        with (
            mock.patch(
                "app.hybrid_search.search_chunks", return_value=(3, [A, B, C])
            ),
            mock.patch(
                "app.hybrid_search.search_lexical", return_value=(3, [A, B, C])
            ),
        ):
            _, two = search_hybrid(REPO, "query", limit=2)
            _, zero = search_hybrid(REPO, "query", limit=0)
            _, negative = search_hybrid(REPO, "query", limit=-1)

        self.assertEqual(len(two), 2)
        self.assertEqual(zero, [])
        self.assertEqual(negative, [])

    def test_one_system_empty(self):
        with (
            mock.patch(
                "app.hybrid_search.search_chunks", return_value=(5, [])
            ),
            mock.patch(
                "app.hybrid_search.search_lexical", return_value=(5, [A])
            ),
        ):
            total, results = search_hybrid(REPO, "query")

        self.assertEqual(total, 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["retrieved_by"], ["bm25"])

    def test_both_systems_empty(self):
        with (
            mock.patch(
                "app.hybrid_search.search_chunks", return_value=(5, [])
            ),
            mock.patch(
                "app.hybrid_search.search_lexical", return_value=(5, [])
            ),
        ):
            self.assertEqual(search_hybrid(REPO, "query"), (5, []))

    def test_repository_isolation(self):
        repo_a = make_result("src/only_a.js")
        repo_b = make_result("src/only_b.js")

        def semantic(repository, query, limit):
            return (1, [repo_a]) if repository == "owner/a" else (1, [repo_b])

        def lexical(repository, query, limit):
            return (1, [repo_a]) if repository == "owner/a" else (1, [repo_b])

        with (
            mock.patch(
                "app.hybrid_search.search_chunks", side_effect=semantic
            ) as semantic_mock,
            mock.patch(
                "app.hybrid_search.search_lexical", side_effect=lexical
            ) as lexical_mock,
        ):
            _, results_a = search_hybrid("owner/a", "query")
            _, results_b = search_hybrid("owner/b", "query")

        self.assertEqual(
            [r["file_path"] for r in results_a], ["src/only_a.js"]
        )
        self.assertEqual(
            [r["file_path"] for r in results_b], ["src/only_b.js"]
        )
        self.assertEqual(
            semantic_mock.call_args_list,
            [
                mock.call("owner/a", "query", limit=15),
                mock.call("owner/b", "query", limit=15),
            ],
        )
        self.assertEqual(
            lexical_mock.call_args_list,
            [
                mock.call("owner/a", "query", limit=15),
                mock.call("owner/b", "query", limit=15),
            ],
        )

    def test_not_ready_errors_propagate(self):
        with (
            mock.patch(
                "app.hybrid_search.search_chunks",
                side_effect=EmbeddingsNotReadyError("no embeddings"),
            ),
            mock.patch("app.hybrid_search.search_lexical"),
        ):
            with self.assertRaises(EmbeddingsNotReadyError):
                search_hybrid(REPO, "query")

        with (
            mock.patch(
                "app.hybrid_search.search_chunks", return_value=(1, [A])
            ),
            mock.patch(
                "app.hybrid_search.search_lexical",
                side_effect=LexicalIndexNotReadyError("no index"),
            ),
        ):
            with self.assertRaises(LexicalIndexNotReadyError):
                search_hybrid(REPO, "query")


class QuestionAnsweringTests(unittest.TestCase):
    def test_qa_uses_hybrid_retrieval(self):
        from app import qa

        fused = [
            {
                **A,
                "rrf_score": 2 / 61,
                "retrieved_by": ["semantic", "bm25"],
            }
        ]
        with (
            mock.patch(
                "app.qa.search_hybrid", return_value=(3, fused)
            ) as hybrid,
            mock.patch("app.qa.provider_name", return_value="ollama"),
            mock.patch("app.qa.get_model_name", return_value="test-model"),
            mock.patch("app.qa.send_message", return_value="42") as send,
        ):
            response = qa.answer_repository_question(REPO, "What is alpha?")

        hybrid.assert_called_once_with(REPO, "What is alpha?", limit=15)
        self.assertEqual(response["sources"], fused)
        self.assertEqual(response["total_chunks"], 3)
        self.assertEqual(response["answer"], "42")
        self.assertEqual(response["provider"], "ollama")
        self.assertEqual(response["model"], "test-model")
        prompt = send.call_args.args[0]
        self.assertIn("src/a.js", prompt)
        self.assertIn("function alpha() {}", prompt)
        self.assertIn("What is alpha?", prompt)


class SearchEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_semantic_endpoint_still_uses_semantic_search(self):
        result = {**A, "similarity": 0.9}
        with (
            mock.patch(
                "app.routes.repositories.search_chunks",
                return_value=(1, [result]),
            ) as semantic,
            mock.patch("app.routes.repositories.search_hybrid") as hybrid,
        ):
            response = self.client.post(
                "/repositories/search",
                json={"repo_url": REPO_URL, "query": "hello"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["repository"], REPO)
        self.assertEqual(body["results"], [result])
        semantic.assert_called_once_with(REPO, "hello")
        hybrid.assert_not_called()

    def test_hybrid_endpoint(self):
        result = {**A, "rrf_score": 2 / 61, "retrieved_by": ["semantic", "bm25"]}
        with mock.patch(
            "app.routes.repositories.search_hybrid", return_value=(1, [result])
        ) as hybrid:
            response = self.client.post(
                "/repositories/search/hybrid",
                json={"repo_url": REPO_URL, "query": "hello"},
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["repository"], REPO)
        self.assertEqual(body["query"], "hello")
        self.assertEqual(body["total_chunks"], 1)
        self.assertEqual(body["results"], [result])
        hybrid.assert_called_once_with(REPO, "hello")

    def test_hybrid_endpoint_maps_not_ready_to_409(self):
        for error in (
            EmbeddingsNotReadyError("no embeddings"),
            LexicalIndexNotReadyError("no index"),
        ):
            with self.subTest(error=type(error).__name__):
                with mock.patch(
                    "app.routes.repositories.search_hybrid", side_effect=error
                ):
                    response = self.client.post(
                        "/repositories/search/hybrid",
                        json={"repo_url": REPO_URL, "query": "hello"},
                    )
                self.assertEqual(response.status_code, 409)

    def test_hybrid_endpoint_rejects_empty_query(self):
        response = self.client.post(
            "/repositories/search/hybrid",
            json={"repo_url": REPO_URL, "query": "   "},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()