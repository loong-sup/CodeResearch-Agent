import json
from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.knowledgebase_operations import (
    bind_session_repository,
    get_user_history_questions,
    verify_user_knowledgebase,
)
from service.core.chat import build_citations_payload, write_chat_to_db, update_session_name
from service.core.retrieval import retrieve_content
from service.model_config import get_generation_client, get_generation_model
from service.repository_service import resolve_repository_context
from utils import logger
from utils.prompt import CodeGenerationPrompt


SUPPORTED_CODE_GENERATION_LANGUAGES: dict[str, dict[str, str]] = {
    "c": {"label": "C", "fence": "c"},
    "c++": {"label": "C++", "fence": "cpp"},
    "cpp": {"label": "C++", "fence": "cpp"},
    "python": {"label": "Python", "fence": "python"},
    "typescript": {"label": "TypeScript", "fence": "typescript"},
    "ts": {"label": "TypeScript", "fence": "typescript"},
    "java": {"label": "Java", "fence": "java"},
}

PUBLIC_CODE_GENERATION_LANGUAGES = ["C", "C++", "Python", "TypeScript", "Java"]


def _sse_message(payload: dict[str, Any]) -> str:
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def normalize_generation_language(language: str) -> dict[str, str]:
    normalized = (language or "").strip().lower()
    language_config = SUPPORTED_CODE_GENERATION_LANGUAGES.get(normalized)
    if not language_config:
        supported = ", ".join(PUBLIC_CODE_GENERATION_LANGUAGES)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported code generation language: {language}. Supported languages: {supported}.",
        )
    return language_config


def build_code_generation_prompt(
    *,
    question: str,
    language_label: str,
    fence_label: str,
    references: list[dict[str, Any]],
    repository_context: list[dict[str, Any]],
    history_questions: Any,
) -> str:
    reference_payload = {
        "repository_snippets": references,
        "repository_context": serialize_repository_context(repository_context),
    }
    return CodeGenerationPrompt % (
        language_label,
        fence_label,
        json.dumps(reference_payload, ensure_ascii=False, indent=2, default=str),
        history_questions,
        question,
    )


def serialize_repository_context(
    repositories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "repository_id": repo.get("id"),
            "repository_name": repo.get("name"),
            "repository_type": repo.get("type"),
            "status": repo.get("status"),
        }
        for repo in repositories
    ]


def resolve_generation_repositories(
    *,
    user_id: str,
    session_id: str,
    explicit_repository_ids: Optional[list[str]],
    db: Session,
) -> list[dict[str, Any]]:
    if not verify_user_knowledgebase(user_id):
        return []

    resolved_repositories = resolve_repository_context(
        user_id=user_id,
        session_id=session_id,
        explicit_repository_ids=explicit_repository_ids,
        db=db,
    )
    if explicit_repository_ids and not resolved_repositories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected repository is unavailable. Please re-index the repository and try again.",
        )

    if session_id and resolved_repositories:
        bind_session_repository(user_id, session_id, resolved_repositories[0]["id"], db=db)
        db.commit()

    return resolved_repositories


def retrieve_generation_snippets(
    *,
    user_id: str,
    question: str,
    repositories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not repositories:
        return []

    repository_ids = [repo["id"] for repo in repositories]
    try:
        references = retrieve_content(user_id, question, repository_ids=repository_ids)
    except Exception as e:
        logger.warning(f"code generation snippet retrieval failed: {e}")
        return []
    repository_by_id = {repo["id"]: repo for repo in repositories}
    for reference in references:
        repo = repository_by_id.get(reference.get("repository_id"))
        if repo:
            reference["repository_name"] = repo.get("name")
            reference["repository_type"] = repo.get("type")
    return references


def stream_code_generation(
    *,
    session_id: str,
    question: str,
    language_label: str,
    fence_label: str,
    final_prompt: str,
    references: list[dict[str, Any]],
    repository_context: list[dict[str, Any]],
    user_id: str,
):
    model_answer = ""
    think = ""
    try:
        yield _sse_message({
            "generation_language": language_label,
            "generation_fence": fence_label,
            "answer_scope": "code_generation",
        })

        if references:
            yield _sse_message({"documents": references, "answer_scope": "code_generation"})

        citations = build_citations_payload(references)
        if citations:
            yield _sse_message({"citations": citations, "answer_scope": "code_generation"})

        if repository_context:
            yield _sse_message({
                "repository_context": serialize_repository_context(repository_context),
                "answer_scope": "code_generation",
            })

        client = get_generation_client(timeout=60)
        completion = client.chat.completions.create(
            model=get_generation_model(),
            messages=[{"role": "user", "content": final_prompt}],
            stream=True,
        )

        for chunk in completion:
            if chunk.choices[0].finish_reason == "stop":
                yield "event: end\ndata: [DONE]\n\n"
                try:
                    write_chat_to_db(session_id, question, model_answer, references, [], think)
                    update_session_name(session_id, question, user_id)
                except Exception as persist_error:
                    logger.warning(f"failed to persist code generation answer: {persist_error}")
                break

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            reasoning_content = getattr(delta, "reasoning_content", None)
            if content:
                model_answer += content
                yield _sse_message({
                    "role": "assistant",
                    "content": content,
                    "thinking": False,
                    "answer_scope": "code_generation",
                    "generation_language": language_label,
                })
            elif reasoning_content:
                think += reasoning_content
                yield _sse_message({
                    "role": "assistant",
                    "content": reasoning_content,
                    "thinking": True,
                    "answer_scope": "code_generation",
                    "generation_language": language_label,
                })
    except Exception as e:
        logger.warning(f"code generation failed: {e}")
        yield f"event: error\ndata: {json.dumps({'role': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        yield "event: end\ndata: [DONE]\n\n"


def prepare_code_generation(
    *,
    user_id: str,
    session_id: str,
    question: str,
    language: str,
    explicit_repository_ids: Optional[list[str]],
    db: Session,
) -> dict[str, Any]:
    language_config = normalize_generation_language(language)
    repositories = resolve_generation_repositories(
        user_id=user_id,
        session_id=session_id,
        explicit_repository_ids=explicit_repository_ids,
        db=db,
    )
    references = retrieve_generation_snippets(
        user_id=user_id,
        question=question,
        repositories=repositories,
    )
    history_questions = get_user_history_questions(session_id)
    final_prompt = build_code_generation_prompt(
        question=question,
        language_label=language_config["label"],
        fence_label=language_config["fence"],
        references=references,
        repository_context=repositories,
        history_questions=history_questions,
    )
    return {
        "language_label": language_config["label"],
        "fence_label": language_config["fence"],
        "repositories": repositories,
        "references": references,
        "history_questions": history_questions,
        "final_prompt": final_prompt,
    }
