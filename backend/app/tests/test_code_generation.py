import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from service import code_generation


class CodeGenerationTests(unittest.TestCase):
    def test_supported_language_acceptance(self):
        language = code_generation.normalize_generation_language("Python")

        self.assertEqual(language["label"], "Python")
        self.assertEqual(language["fence"], "python")

    def test_cpp_language_uses_cpp_fence(self):
        language = code_generation.normalize_generation_language("C++")

        self.assertEqual(language["label"], "C++")
        self.assertEqual(language["fence"], "cpp")

    def test_unsupported_language_rejected_before_model_use(self):
        with self.assertRaises(HTTPException) as raised:
            code_generation.normalize_generation_language("Rust")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Unsupported code generation language", raised.exception.detail)

    @patch("service.code_generation.verify_user_knowledgebase", return_value=True)
    @patch("service.code_generation.resolve_repository_context", return_value=[])
    def test_unavailable_repository_rejected(self, _resolve, _verify):
        with self.assertRaises(HTTPException) as raised:
            code_generation.resolve_generation_repositories(
                user_id="1",
                session_id="session",
                explicit_repository_ids=["missing"],
                db=Mock(),
            )

        self.assertEqual(raised.exception.status_code, 400)
        self.assertIn("Selected repository is unavailable", raised.exception.detail)

    @patch("service.code_generation.verify_user_knowledgebase", return_value=True)
    @patch(
        "service.code_generation.resolve_repository_context",
        return_value=[{"id": "repo-1", "name": "demo", "type": "project", "status": "ready"}],
    )
    @patch("service.code_generation.bind_session_repository")
    def test_repository_context_resolution_binds_session(
        self,
        bind_session_repository,
        _resolve,
        _verify,
    ):
        db = Mock()

        repositories = code_generation.resolve_generation_repositories(
            user_id="1",
            session_id="session",
            explicit_repository_ids=["repo-1"],
            db=db,
        )

        self.assertEqual(repositories[0]["id"], "repo-1")
        bind_session_repository.assert_called_once_with("1", "session", "repo-1", db=db)
        db.commit.assert_called_once()

    @patch(
        "service.code_generation.retrieve_content",
        return_value=[{"repository_id": "repo-1", "content_with_weight": "def main(): pass"}],
    )
    def test_relevant_snippet_retrieval_adds_repository_metadata(self, _retrieve):
        references = code_generation.retrieve_generation_snippets(
            user_id="1",
            question="generate a main function",
            repositories=[{"id": "repo-1", "name": "demo", "type": "project"}],
        )

        self.assertEqual(references[0]["repository_name"], "demo")
        self.assertEqual(references[0]["repository_type"], "project")

    def test_prompt_construction_contains_output_format_and_safety_rules(self):
        prompt = code_generation.build_code_generation_prompt(
            question="Add a service",
            language_label="TypeScript",
            fence_label="typescript",
            references=[
                {
                    "file_path": "src/service.ts",
                    "start_line": 1,
                    "end_line": 5,
                    "content_with_weight": "export function run() {}",
                }
            ],
            repository_context=[{"id": "repo-1", "name": "demo"}],
            history_questions="Previous question",
        )

        self.assertIn("TypeScript", prompt)
        self.assertIn("typescript", prompt)
        self.assertIn("Do not claim that code was compiled", prompt)
        self.assertIn("Use fenced markdown code blocks", prompt)
        self.assertIn("[file_path:startLine-endLine]", prompt)
        self.assertIn("current repository evidence is insufficient", prompt)

    def test_prompt_construction_serializes_repository_datetimes(self):
        prompt = code_generation.build_code_generation_prompt(
            question="Add a service",
            language_label="Python",
            fence_label="python",
            references=[],
            repository_context=[
                {
                    "id": "repo-1",
                    "name": "demo",
                    "type": "project",
                    "status": "ready",
                    "created_at": datetime(2026, 6, 18, 13, 50, 0),
                }
            ],
            history_questions="",
        )

        self.assertIn('"repository_id": "repo-1"', prompt)
        self.assertNotIn("created_at", prompt)

    @patch("service.code_generation.get_user_history_questions", return_value="Previous question")
    @patch("service.code_generation.retrieve_generation_snippets", return_value=[])
    @patch("service.code_generation.resolve_generation_repositories", return_value=[])
    def test_prepare_generation_reads_history_and_builds_prompt(
        self,
        _resolve,
        _retrieve,
        get_user_history_questions,
    ):
        result = code_generation.prepare_code_generation(
            user_id="1",
            session_id="session",
            question="write code",
            language="Java",
            explicit_repository_ids=None,
            db=Mock(),
        )

        get_user_history_questions.assert_called_once_with("session")
        self.assertEqual(result["language_label"], "Java")
        self.assertIn("Previous question", result["final_prompt"])

    @patch("service.code_generation.update_session_name")
    @patch("service.code_generation.write_chat_to_db")
    @patch("service.code_generation.get_generation_model", return_value="model")
    @patch("service.code_generation.get_generation_client")
    def test_model_streaming_handoff_uses_sse_shape(
        self,
        get_generation_client,
        _get_generation_model,
        write_chat_to_db,
        _update_session_name,
    ):
        content_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(content="```python\nprint('ok')\n```"),
                )
            ]
        )
        stop_chunk = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace())]
        )
        client = Mock()
        client.chat.completions.create.return_value = [content_chunk, stop_chunk]
        get_generation_client.return_value = client

        events = list(
            code_generation.stream_code_generation(
                session_id="session",
                question="write code",
                language_label="Python",
                fence_label="python",
                final_prompt="prompt",
                references=[],
                repository_context=[],
                user_id="1",
            )
        )

        self.assertTrue(events[0].startswith("event: message"))
        self.assertIn('"generation_language": "Python"', events[0])
        self.assertIn("```python", "".join(events))
        self.assertTrue(events[-1].startswith("event: end"))
        write_chat_to_db.assert_called_once()

    def test_streamed_references_are_json_payloads(self):
        payload = code_generation._sse_message({"documents": [{"id": 1}]})
        data = payload.split("data: ", 1)[1].strip()

        self.assertEqual(json.loads(data)["documents"][0]["id"], 1)


if __name__ == "__main__":
    unittest.main()
