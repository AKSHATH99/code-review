import unittest
from unittest import mock

from app.lexical_search import (
    LexicalIndexNotReadyError,
    _BM25_CACHE,
    build_lexical_index,
    search_lexical,
    tokenize,
)

REPO = "owner/repo"


def make_chunk(file_path="src/app.js", content="", **overrides):
    chunk = {
        "file_path": file_path,
        "chunk_id": f"{file_path}@1-1",
        "chunk_type": "text",
        "language": "javascript",
        "symbol": None,
        "symbol_type": None,
        "parent_symbol": None,
        "json_path": None,
        "start_line": 1,
        "end_line": 1,
        "content": content,
    }
    chunk.update(overrides)
    return chunk


class TokenizeTests(unittest.TestCase):
    def test_camel_case_keeps_whole_and_parts(self):
        self.assertEqual(
            tokenize("handleContactSubmit"),
            ["handlecontactsubmit", "handle", "contact", "submit"],
        )

    def test_pascal_case(self):
        self.assertEqual(
            tokenize("ContactForm"), ["contactform", "contact", "form"]
        )

    def test_snake_case(self):
        self.assertEqual(
            tokenize("handle_contact_submit"), ["handle", "contact", "submit"]
        )

    def test_kebab_case(self):
        self.assertEqual(tokenize("nav-bar-item"), ["nav", "bar", "item"])

    def test_file_path_and_extension(self):
        self.assertEqual(
            tokenize("src/components/Navbar.jsx"),
            ["src", "components", "navbar", "jsx"],
        )

    def test_json_path(self):
        self.assertEqual(
            tokenize("$.settings.contactForm.submitLabel"),
            [
                "settings",
                "contactform",
                "contact",
                "form",
                "submitlabel",
                "submit",
                "label",
            ],
        )

    def test_short_identifiers_are_kept(self):
        self.assertEqual(tokenize("id js db ui"), ["id", "js", "db", "ui"])

    def test_acronym_boundary(self):
        self.assertEqual(
            tokenize("HTTPServer"), ["httpserver", "http", "server"]
        )

    def test_uppercase_normalized(self):
        self.assertEqual(tokenize("SUBMIT"), ["submit"])

    def test_punctuation_only(self):
        self.assertEqual(tokenize("() => { ... !? }"), [])


class LexicalSearchTests(unittest.TestCase):
    def setUp(self):
        _BM25_CACHE.clear()

    def tearDown(self):
        _BM25_CACHE.clear()

    def test_exact_identifier_ranks_first(self):
        chunks = [
            make_chunk(
                "src/utils/format.js",
                "function formatDate(value) { return value; }",
                symbol="formatDate",
            ),
            make_chunk(
                "src/forms/contact.js",
                "function handleContactSubmit() {}",
                symbol="handleContactSubmit",
            ),
            make_chunk("src/db.js", "function openDatabase() {}"),
        ]
        build_lexical_index(REPO, chunks)

        total, results = search_lexical(REPO, "handleContactSubmit")

        self.assertEqual(total, 3)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["file_path"], "src/forms/contact.js")
        self.assertGreater(results[0]["bm25_score"], 0)

    def test_filename_query(self):
        chunks = [
            make_chunk(
                "src/components/Navbar.jsx",
                "export default function Navbar() { return null; }",
            ),
            make_chunk(
                "src/components/Footer.jsx",
                "export default function Footer() { return null; }",
            ),
            make_chunk("src/utils/format.js", "function formatDate(value) {}"),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "Navbar.jsx")

        self.assertEqual(results[0]["file_path"], "src/components/Navbar.jsx")

    def test_camel_case_full_identifier_and_parts(self):
        chunks = [
            make_chunk(
                "src/forms/contact.js",
                "function handleContactSubmit() {}",
                symbol="handleContactSubmit",
            ),
            make_chunk("src/db.js", "function openDatabase() {}"),
        ]
        build_lexical_index(REPO, chunks)

        for query in ("handleContactSubmit", "submit", "handle contact"):
            with self.subTest(query=query):
                _, results = search_lexical(REPO, query)
                self.assertEqual(
                    results[0]["file_path"], "src/forms/contact.js"
                )

    def test_snake_case_full_identifier_and_parts(self):
        chunks = [
            make_chunk(
                "src/forms.py",
                "def handle_contact_submit(request):\n    pass",
                language="python",
            ),
            make_chunk("src/db.py", "def open_database():\n    pass"),
        ]
        build_lexical_index(REPO, chunks)

        for query in ("handle_contact_submit", "contact", "handleContactSubmit"):
            with self.subTest(query=query):
                _, results = search_lexical(REPO, query)
                self.assertEqual(results[0]["file_path"], "src/forms.py")

    def test_conceptual_keyword_search(self):
        chunks = [
            make_chunk(
                "src/contact.js",
                "// Handles the contact form submission\n"
                "function onContactFormSubmit(event) {\n"
                "  event.preventDefault();\n"
                "  sendContactRequest(new FormData(event.target));\n"
                "}",
                symbol="onContactFormSubmit",
            ),
            make_chunk(
                "src/migrations/0001.sql",
                "ALTER TABLE users ADD COLUMN created_at TIMESTAMP;",
            ),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "contact form submission")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["file_path"], "src/contact.js")

    def test_json_path_is_searchable(self):
        chunks = [
            make_chunk(
                "package.json",
                '{"scripts": {"build": "vite build"}}',
                language="json",
                json_path="$.scripts.build",
            ),
            make_chunk("README.md", "Installation instructions."),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "scripts.build")

        self.assertEqual(results[0]["file_path"], "package.json")

    def test_missing_and_null_metadata(self):
        chunks = [
            {"file_path": "src/a.js", "content": "function alpha() {}"},
            make_chunk("src/b.js", "function beta() {}"),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "alpha")

        self.assertEqual(results[0]["file_path"], "src/a.js")

    def test_empty_repository(self):
        build_lexical_index(REPO, [])

        self.assertEqual(search_lexical(REPO, "anything"), (0, []))

    def test_empty_query(self):
        build_lexical_index(REPO, [make_chunk(content="function alpha() {}")])

        self.assertEqual(search_lexical(REPO, ""), (1, []))
        self.assertEqual(search_lexical(REPO, "   "), (1, []))

    def test_punctuation_only_query(self):
        build_lexical_index(REPO, [make_chunk(content="function alpha() {}")])

        self.assertEqual(search_lexical(REPO, "!!! ??? () => {}"), (1, []))

    def test_repository_without_tokenizable_content(self):
        build_lexical_index(REPO, [make_chunk(content="!!! ???")])

        self.assertEqual(search_lexical(REPO, "anything"), (1, []))

    def test_index_not_found(self):
        with self.assertRaises(LexicalIndexNotReadyError):
            search_lexical("owner/missing", "anything")

    def test_non_positive_limit(self):
        build_lexical_index(REPO, [make_chunk(content="function alpha() {}")])

        self.assertEqual(search_lexical(REPO, "alpha", limit=0), (1, []))
        self.assertEqual(search_lexical(REPO, "alpha", limit=-3), (1, []))

    def test_repository_isolation(self):
        build_lexical_index(
            "owner/alpha", [make_chunk("src/alpha.js", "function zebra() {}")]
        )
        build_lexical_index(
            "owner/beta", [make_chunk("src/beta.js", "function quokka() {}")]
        )

        self.assertEqual(search_lexical("owner/alpha", "quokka"), (1, []))
        self.assertEqual(search_lexical("owner/beta", "zebra"), (1, []))

        _, alpha_results = search_lexical("owner/alpha", "zebra")
        _, beta_results = search_lexical("owner/beta", "quokka")
        self.assertEqual(alpha_results[0]["file_path"], "src/alpha.js")
        self.assertEqual(beta_results[0]["file_path"], "src/beta.js")

    def test_ranking_prefers_distinctive_term_density(self):
        chunks = [
            make_chunk(
                "src/nav.jsx",
                'function Navbar() { return <nav className="navbar">'
                "GitScope</nav>; }",
            ),
            make_chunk(
                "src/footer.jsx",
                "function Footer() { return <footer>Copyright</footer>; }",
            ),
            make_chunk(
                "src/nav-extra.jsx",
                "navbar navbar navbar menu menu toggle toggle toggle",
            ),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "navbar menu toggle")

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["file_path"], "src/nav-extra.jsx")
        self.assertEqual(results[1]["file_path"], "src/nav.jsx")
        self.assertGreater(
            results[0]["bm25_score"], results[1]["bm25_score"]
        )

    def test_limit_respected(self):
        chunks = [
            make_chunk("src/sparse.js", "widget among many other words here"),
            make_chunk("src/dense.js", "widget widget widget"),
            make_chunk("src/a.js", "function alpha() {}"),
            make_chunk("src/b.js", "function beta() {}"),
            make_chunk("src/c.js", "function gamma() {}"),
        ]
        build_lexical_index(REPO, chunks)

        total, results = search_lexical(REPO, "widget", limit=1)

        self.assertEqual(total, 5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["file_path"], "src/dense.js")

    def test_alignment_with_duplicate_chunk_index(self):
        chunks = [
            make_chunk("src/one.js", "function first() {}", chunk_index=0),
            make_chunk("src/two.js", "function second() {}", chunk_index=0),
        ]
        build_lexical_index(REPO, chunks)

        _, results = search_lexical(REPO, "second")

        self.assertEqual(results[0]["file_path"], "src/two.js")
        self.assertEqual(results[0]["chunk_index"], 0)

    def test_original_metadata_preserved(self):
        chunk = make_chunk(
            "src/forms/contact.js",
            "function handleSubmit() {}",
            chunk_index=0,
            symbol="handleSubmit",
            symbol_type="function_declaration",
            parent_symbol="ContactForm",
            start_line=5,
            end_line=12,
        )
        build_lexical_index(REPO, [chunk])

        _, results = search_lexical(REPO, "handleSubmit")

        result = results[0]
        self.assertIn("bm25_score", result)
        self.assertEqual(
            {key: value for key, value in result.items() if key != "bm25_score"},
            chunk,
        )

    def test_rebuild_replaces_previous_index(self):
        build_lexical_index(REPO, [make_chunk("src/old.js", "function legacy() {}")])
        build_lexical_index(REPO, [make_chunk("src/new.js", "function modern() {}")])

        self.assertEqual(search_lexical(REPO, "legacy"), (1, []))
        _, results = search_lexical(REPO, "modern")
        self.assertEqual(results[0]["file_path"], "src/new.js")

    def test_failed_rebuild_drops_stale_index(self):
        build_lexical_index(REPO, [make_chunk(content="function legacy() {}")])

        with mock.patch(
            "app.lexical_search.BM25Okapi", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                build_lexical_index(REPO, [make_chunk(content="function modern() {}")])

        with self.assertRaises(LexicalIndexNotReadyError):
            search_lexical(REPO, "legacy")


if __name__ == "__main__":
    unittest.main()