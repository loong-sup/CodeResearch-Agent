import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi import HTTPException

from service import code_generation


class CodeGenerationEndToEndTests(unittest.TestCase):
    @patch("service.code_generation.update_session_name")
    @patch("service.code_generation.write_chat_to_db")
    @patch("service.code_generation.get_generation_model", return_value="model")
    @patch("service.code_generation.get_generation_client")
    @patch("service.code_generation.get_user_history_questions", return_value="之前的问题")
    @patch(
        "service.code_generation.retrieve_content",
        return_value=[
            {
                "id": 1,
                "chunk_id": "chunk-1",
                "repository_id": "repo-1",
                "file_path": "src/app.ts",
                "start_line": 10,
                "end_line": 20,
                "citation": "src/app.ts:10-20",
                "citation_display": "[src/app.ts:10-20]",
                "content_with_weight": "export function existing() {}",
            }
        ],
    )
    @patch("service.code_generation.bind_session_repository")
    @patch(
        "service.code_generation.resolve_repository_context",
        return_value=[{"id": "repo-1", "name": "demo", "type": "project", "status": "ready"}],
    )
    @patch("service.code_generation.verify_user_knowledgebase", return_value=True)
    def test_generation_flow_with_repository_selection_streams_citations(
        self,
        _verify,
        _resolve,
        _bind,
        _retrieve,
        _history,
        get_generation_client,
        _get_generation_model,
        _write_chat_to_db,
        _update_session_name,
    ):
        content_chunk = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    finish_reason=None,
                    delta=SimpleNamespace(
                        content="```typescript\nexport function generated() {}\n```\n[src/app.ts:10-20]"
                    ),
                )
            ]
        )
        stop_chunk = SimpleNamespace(
            choices=[SimpleNamespace(finish_reason="stop", delta=SimpleNamespace())]
        )
        client = Mock()
        client.chat.completions.create.return_value = [content_chunk, stop_chunk]
        get_generation_client.return_value = client

        prepared = code_generation.prepare_code_generation(
            user_id="1",
            session_id="session",
            question="Generate a TypeScript helper",
            language="TypeScript",
            explicit_repository_ids=["repo-1"],
            db=Mock(),
        )

        events = list(
            code_generation.stream_code_generation(
                session_id="session",
                question="Generate a TypeScript helper",
                language_label=prepared["language_label"],
                fence_label=prepared["fence_label"],
                final_prompt=prepared["final_prompt"],
                references=prepared["references"],
                repository_context=prepared["repositories"],
                user_id="1",
            )
        )
        joined = "".join(events)

        self.assertIn('"generation_language": "TypeScript"', joined)
        self.assertIn('"repository_context"', joined)
        self.assertIn('"citations"', joined)
        self.assertIn("```typescript", joined)
        self.assertIn("[src/app.ts:10-20]", joined)

    def test_unsupported_language_fails_before_generation_flow(self):
        with self.assertRaises(HTTPException):
            code_generation.prepare_code_generation(
                user_id="1",
                session_id="session",
                question="Generate code",
                language="Rust",
                explicit_repository_ids=None,
                db=Mock(),
            )


if __name__ == "__main__":
    unittest.main()
