import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.knowledgebase_operations import (
    bind_session_repository,
    create_repository,
    delete_legacy_knowledgebase,
    delete_repository_record,
    get_repository_by_id,
    get_repository_by_name,
    list_legacy_knowledgebases,
    list_repositories,
    list_repository_candidates,
    resolve_default_repository,
    update_repository,
)
from service.core.file_parse import execute_insert_process
from service.core.rag.app.code_repo import CODE_EXTENSIONS, CONFIG_EXTENSIONS, DOC_EXTENSIONS
from service.core.rag.utils.es_conn import ESConnection


@dataclass
class RepositoryDeleteResult:
    found: bool
    repository_id: Optional[str] = None
    chunks_deleted: int = 0
    files_deleted: int = 0
    metadata_deleted: bool = False
    legacy_rows_deleted: int = 0
    messages_marked: int = 0
def _infer_repository_type(name: str, is_archive: bool = False) -> str:
    if is_archive:
        return "code"
    suffix = Path(name).suffix.lower()
    if suffix in DOC_EXTENSIONS:
        return "doc"
    if suffix in CODE_EXTENSIONS or suffix in CONFIG_EXTENSIONS:
        return "code"
    return "doc"


def _delete_local_paths(*paths: Optional[str]) -> int:
    deleted = 0
    seen = set()
    for raw_path in paths:
        if not raw_path:
            continue
        path = os.path.abspath(raw_path)
        if path in seen or not os.path.exists(path):
            continue
        seen.add(path)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            deleted += 1
        elif os.path.isfile(path):
            os.remove(path)
            deleted += 1
    return deleted


def _mark_repository_deleted_in_messages(db: Session, repository_id: str) -> int:
    rows = db.execute(
        text(
            """
            SELECT message_id, documents
            FROM messages
            WHERE documents IS NOT NULL
            """
        )
    ).fetchall()
    updated = 0
    for row in rows:
        documents_raw = row.documents
        if not documents_raw:
            continue
        try:
            documents = json.loads(documents_raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(documents, list):
            continue
        changed = False
        for item in documents:
            if isinstance(item, dict) and item.get("repository_id") == repository_id:
                item["repository_deleted"] = True
                changed = True
        if not changed:
            continue
        db.execute(
            text(
                """
                UPDATE messages
                SET documents = :documents, updated_at = CURRENT_TIMESTAMP
                WHERE message_id = :message_id
                """
            ),
            {"documents": json.dumps(documents, ensure_ascii=False), "message_id": row.message_id},
        )
        updated += 1
    return updated


def create_repository_from_source(
    *,
    db: Session,
    user_id: str,
    name: str,
    source_path: str,
    storage_path: str,
    session_id: Optional[str] = None,
    root_path: Optional[str] = None,
    archive_path: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    is_archive: bool = False,
) -> dict[str, Any]:
    repository_type = _infer_repository_type(name, is_archive=is_archive)
    repository = create_repository(
        user_id=user_id,
        name=name,
        repository_type=repository_type,
        index_name=user_id,
        storage_path=storage_path,
        root_path=root_path,
        archive_path=archive_path,
        status="indexing",
        metadata=metadata,
        db=db,
    )
    repository_id = repository["id"]
    try:
        indexing = execute_insert_process(
            source_path,
            name,
            repository_id=repository_id,
            user_id=user_id,
            index_name=user_id,
        )
        merged_metadata = dict(metadata or {})
        merged_metadata.update(
            {
                "doc_ids": indexing.doc_ids,
                "source_path": source_path,
                "root_path": root_path or source_path,
                "structure_index": indexing.structure_index,
            }
        )
        update_repository(
            repository_id,
            user_id,
            status="ready",
            file_count=indexing.file_count,
            indexed_chunks=indexing.indexed_chunks,
            language_stats=indexing.language_stats,
            metadata=merged_metadata,
            db=db,
        )
        if session_id:
            bind_session_repository(user_id, session_id, repository_id, db=db)
        return get_repository_by_id(user_id, repository_id, db=db) or {"id": repository_id}
    except Exception:
        update_repository(repository_id, user_id, status="error", db=db)
        raise


def list_user_repositories(user_id: str, db: Optional[Session] = None) -> list[dict[str, Any]]:
    repositories = list_repositories(user_id, db=db)
    if repositories:
        return repositories
    return list_legacy_knowledgebases(user_id, db=db)


def resolve_repository_context(
    *,
    user_id: str,
    session_id: Optional[str] = None,
    explicit_repository_ids: Optional[list[str]] = None,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    if explicit_repository_ids:
        for repository_id in explicit_repository_ids:
            repository = get_repository_by_id(user_id, repository_id, db=db)
            if repository:
                repositories.append(repository)
    else:
        repository = resolve_default_repository(user_id, session_id=session_id, db=db)
        if repository:
            repositories.append(repository)
    return repositories


def delete_repository_by_name(user_id: str, file_name: str, db: Session) -> RepositoryDeleteResult:
    repository = get_repository_by_name(user_id, file_name, db=db)
    if repository is None:
        legacy_rows_deleted = delete_legacy_knowledgebase(user_id, file_name, db=db)
        return RepositoryDeleteResult(
            found=legacy_rows_deleted > 0,
            legacy_rows_deleted=legacy_rows_deleted,
            metadata_deleted=legacy_rows_deleted > 0,
        )

    es = ESConnection()
    chunks_deleted = es.delete_by_metadata(repository["index_name"], {"repository_id": repository["id"]})
    messages_marked = _mark_repository_deleted_in_messages(db, repository["id"])
    files_deleted = _delete_local_paths(
        repository.get("storage_path"),
        repository.get("root_path"),
        repository.get("archive_path"),
    )
    delete_repository_record(user_id, repository["id"], db=db)
    legacy_rows_deleted = delete_legacy_knowledgebase(user_id, file_name, db=db)
    return RepositoryDeleteResult(
        found=True,
        repository_id=repository["id"],
        chunks_deleted=chunks_deleted,
        files_deleted=files_deleted,
        metadata_deleted=True,
        legacy_rows_deleted=legacy_rows_deleted,
        messages_marked=messages_marked,
    )


def recommend_repository_candidates(
    *,
    user_id: str,
    question: str,
    session_id: Optional[str] = None,
    limit: int = 5,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    return list_repository_candidates(user_id, question=question, session_id=session_id, limit=limit, db=db)
