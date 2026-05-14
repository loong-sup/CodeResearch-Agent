import json
import uuid
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from utils.database import get_db

_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id VARCHAR(64) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        name VARCHAR(255) NOT NULL,
        type VARCHAR(32) NOT NULL DEFAULT 'doc',
        status VARCHAR(32) NOT NULL DEFAULT 'ready',
        index_name VARCHAR(255) NOT NULL,
        storage_path TEXT NOT NULL,
        root_path TEXT,
        archive_path TEXT,
        file_count INTEGER NOT NULL DEFAULT 0,
        indexed_chunks INTEGER NOT NULL DEFAULT 0,
        language_stats TEXT,
        metadata_json TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_repositories_user_id ON repositories(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_repositories_updated_at ON repositories(updated_at)",
    """
    CREATE TABLE IF NOT EXISTS session_repository_contexts (
        session_id VARCHAR(16) PRIMARY KEY,
        user_id VARCHAR(255) NOT NULL,
        repository_id VARCHAR(64) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_session_repository_contexts_user_id
    ON session_repository_contexts(user_id)
    """,
]


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row._mapping) if row is not None else {}


def _maybe_json_dumps(value: Optional[dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def ensure_repository_schema(db: Optional[Session] = None):
    owns_db = db is None
    db = db or next(get_db())
    try:
        for statement in _SCHEMA_STATEMENTS:
            db.execute(text(statement))
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to ensure repository schema: {str(e)}")
    finally:
        if owns_db:
            db.close()


def insert_knowledgebase(user_id: str, file_name: str):
    db = next(get_db())
    try:
        db.execute(
            text(
                """
                INSERT INTO knowledgebases (user_id, file_name)
                VALUES (:user_id, :file_name)
                """
            ),
            {"user_id": user_id, "file_name": file_name},
        )
        db.commit()
    except SQLAlchemyError as e:
        db.rollback()
        raise RuntimeError(f"Failed to insert into knowledgebases: {str(e)}")
    finally:
        db.close()


def create_repository(
    user_id: str,
    name: str,
    repository_type: str,
    index_name: str,
    storage_path: str,
    root_path: Optional[str] = None,
    archive_path: Optional[str] = None,
    status: str = "indexing",
    metadata: Optional[dict[str, Any]] = None,
    file_count: int = 0,
    indexed_chunks: int = 0,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    repository_id = uuid.uuid4().hex
    try:
        db.execute(
            text(
                """
                INSERT INTO repositories (
                    id, user_id, name, type, status, index_name, storage_path,
                    root_path, archive_path, file_count, indexed_chunks, language_stats, metadata_json
                )
                VALUES (
                    :id, :user_id, :name, :type, :status, :index_name, :storage_path,
                    :root_path, :archive_path, :file_count, :indexed_chunks, :language_stats, :metadata_json
                )
                """
            ),
            {
                "id": repository_id,
                "user_id": user_id,
                "name": name,
                "type": repository_type,
                "status": status,
                "index_name": index_name,
                "storage_path": storage_path,
                "root_path": root_path,
                "archive_path": archive_path,
                "file_count": file_count,
                "indexed_chunks": indexed_chunks,
                "language_stats": None,
                "metadata_json": _maybe_json_dumps(metadata),
            },
        )
        if owns_db:
            db.commit()
        return get_repository_by_id(user_id, repository_id, db=db) or {"id": repository_id}
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to create repository metadata: {str(e)}")
    finally:
        if owns_db:
            db.close()


def update_repository(
    repository_id: str,
    user_id: str,
    *,
    name: Optional[str] = None,
    status: Optional[str] = None,
    file_count: Optional[int] = None,
    indexed_chunks: Optional[int] = None,
    language_stats: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
    root_path: Optional[str] = None,
    archive_path: Optional[str] = None,
    storage_path: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    assignments = ["updated_at = CURRENT_TIMESTAMP"]
    params: dict[str, Any] = {"repository_id": repository_id, "user_id": user_id}
    updates = {
        "name": name,
        "status": status,
        "file_count": file_count,
        "indexed_chunks": indexed_chunks,
        "root_path": root_path,
        "archive_path": archive_path,
        "storage_path": storage_path,
    }
    for key, value in updates.items():
        if value is not None:
            assignments.append(f"{key} = :{key}")
            params[key] = value
    if language_stats is not None:
        assignments.append("language_stats = :language_stats")
        params["language_stats"] = json.dumps(language_stats, ensure_ascii=False)
    if metadata is not None:
        assignments.append("metadata_json = :metadata_json")
        params["metadata_json"] = json.dumps(metadata, ensure_ascii=False)
    try:
        db.execute(
            text(
                f"""
                UPDATE repositories
                SET {", ".join(assignments)}
                WHERE id = :repository_id AND user_id = :user_id
                """
            ),
            params,
        )
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to update repository metadata: {str(e)}")
    finally:
        if owns_db:
            db.close()


def list_repositories(user_id: str, db: Optional[Session] = None) -> list[dict[str, Any]]:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        rows = db.execute(
            text(
                """
                SELECT *
                FROM repositories
                WHERE user_id = :user_id
                ORDER BY updated_at DESC, created_at DESC
                """
            ),
            {"user_id": user_id},
        ).fetchall()
        return [_row_to_dict(row) for row in rows]
    finally:
        if owns_db:
            db.close()


def list_legacy_knowledgebases(user_id: str, db: Optional[Session] = None) -> list[dict[str, Any]]:
    owns_db = db is None
    db = db or next(get_db())
    try:
        rows = db.execute(
            text(
                """
                SELECT id, user_id, file_name, created_at, updated_at
                FROM knowledgebases
                WHERE user_id = :user_id
                ORDER BY updated_at DESC, created_at DESC
                """
            ),
            {"user_id": user_id},
        ).fetchall()
        records = []
        for row in rows:
            record = _row_to_dict(row)
            record["repository_id"] = None
            record["type"] = "legacy"
            record["status"] = "legacy"
            record["indexed_chunks"] = None
            records.append(record)
        return records
    finally:
        if owns_db:
            db.close()


def get_repository_by_id(user_id: str, repository_id: str, db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        row = db.execute(
            text(
                """
                SELECT *
                FROM repositories
                WHERE user_id = :user_id AND id = :repository_id
                LIMIT 1
                """
            ),
            {"user_id": user_id, "repository_id": repository_id},
        ).fetchone()
        return _row_to_dict(row) or None
    finally:
        if owns_db:
            db.close()


def get_repository_by_name(user_id: str, name: str, db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        row = db.execute(
            text(
                """
                SELECT *
                FROM repositories
                WHERE user_id = :user_id AND name = :name
                ORDER BY updated_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id, "name": name},
        ).fetchone()
        return _row_to_dict(row) or None
    finally:
        if owns_db:
            db.close()


def delete_repository_record(user_id: str, repository_id: str, db: Optional[Session] = None) -> None:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        db.execute(
            text("DELETE FROM repositories WHERE user_id = :user_id AND id = :repository_id"),
            {"user_id": user_id, "repository_id": repository_id},
        )
        db.execute(
            text("DELETE FROM session_repository_contexts WHERE repository_id = :repository_id"),
            {"repository_id": repository_id},
        )
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to delete repository metadata: {str(e)}")
    finally:
        if owns_db:
            db.close()


def delete_legacy_knowledgebase(user_id: str, file_name: str, db: Optional[Session] = None) -> int:
    owns_db = db is None
    db = db or next(get_db())
    try:
        result = db.execute(
            text(
                """
                DELETE FROM knowledgebases
                WHERE user_id = :user_id AND file_name = :file_name
                """
            ),
            {"user_id": user_id, "file_name": file_name},
        )
        if owns_db:
            db.commit()
        return result.rowcount or 0
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to delete legacy knowledgebase: {str(e)}")
    finally:
        if owns_db:
            db.close()


def bind_session_repository(user_id: str, session_id: str, repository_id: str, db: Optional[Session] = None) -> None:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        db.execute(
            text(
                """
                INSERT INTO session_repository_contexts (session_id, user_id, repository_id)
                VALUES (:session_id, :user_id, :repository_id)
                ON CONFLICT (session_id)
                DO UPDATE SET
                    repository_id = EXCLUDED.repository_id,
                    user_id = EXCLUDED.user_id,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "repository_id": repository_id,
            },
        )
        db.execute(
            text(
                """
                UPDATE repositories
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = :repository_id AND user_id = :user_id
                """
            ),
            {"repository_id": repository_id, "user_id": user_id},
        )
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to bind session repository: {str(e)}")
    finally:
        if owns_db:
            db.close()


def resolve_default_repository(user_id: str, session_id: Optional[str] = None, db: Optional[Session] = None) -> Optional[dict[str, Any]]:
    owns_db = db is None
    db = db or next(get_db())
    ensure_repository_schema(db)
    try:
        if session_id:
            row = db.execute(
                text(
                    """
                    SELECT r.*
                    FROM session_repository_contexts src
                    JOIN repositories r ON r.id = src.repository_id
                    WHERE src.user_id = :user_id AND src.session_id = :session_id
                    LIMIT 1
                    """
                ),
                {"user_id": user_id, "session_id": session_id},
            ).fetchone()
            if row is not None:
                return _row_to_dict(row)

        rows = list_repositories(user_id, db=db)
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]
        return rows[0]
    finally:
        if owns_db:
            db.close()


def list_repository_candidates(
    user_id: str,
    question: str = "",
    session_id: Optional[str] = None,
    limit: int = 5,
    db: Optional[Session] = None,
) -> list[dict[str, Any]]:
    repositories = list_repositories(user_id, db=db)
    if not repositories:
        return []

    keywords = [token.lower() for token in question.split() if token.strip()]
    session_default = resolve_default_repository(user_id, session_id=session_id, db=db) if session_id else None
    candidates = []
    for repo in repositories:
        score = 0.0
        reasons = []
        if session_default and repo["id"] == session_default["id"]:
            score += 3.0
            reasons.append("当前会话最近使用")
        if len(repositories) == 1:
            score += 2.0
            reasons.append("当前用户只有一个可用代码库")
        name = (repo.get("name") or "").lower()
        metadata_blob = " ".join(
            filter(
                None,
                [
                    name,
                    repo.get("type") or "",
                    repo.get("language_stats") or "",
                    repo.get("metadata_json") or "",
                ],
            )
        ).lower()
        for keyword in keywords:
            if keyword in name:
                score += 1.5
                reasons.append(f"问题命中仓库名: {keyword}")
            elif keyword in metadata_blob:
                score += 0.5
                reasons.append(f"问题命中仓库元数据: {keyword}")
        if not reasons:
            reasons.append("按最近更新时间兜底推荐")
        candidates.append(
            {
                "repository_id": repo["id"],
                "repository_name": repo["name"],
                "repository_type": repo["type"],
                "score": score,
                "reason": "；".join(dict.fromkeys(reasons)),
            }
        )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


def verify_user_knowledgebase(user_id: str):
    db = next(get_db())
    try:
        ensure_repository_schema(db)
        query_result = db.execute(
            text("SELECT id FROM repositories WHERE user_id = :user_id LIMIT 1"),
            {"user_id": user_id},
        ).fetchone()
        if query_result:
            return True
        legacy_result = db.execute(
            text("SELECT id FROM knowledgebases WHERE user_id = :user_id LIMIT 1"),
            {"user_id": user_id},
        ).fetchone()
        return legacy_result is not None
    except SQLAlchemyError as e:
        raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")
    finally:
        db.close()


def get_user_history_questions(session_id: str):
    db = next(get_db())
    try:
        messages_data = db.execute(
            text("SELECT user_question FROM messages WHERE session_id = :session_id"),
            {"session_id": session_id},
        ).fetchall()
        return [message.user_question for message in messages_data]
    except SQLAlchemyError as e:
        raise RuntimeError(f"Failed to fetch history questions: {str(e)}")
    finally:
        db.close()


def get_session_memory(session_id: str, limit: int = 6):
    db = next(get_db())
    try:
        rows = db.execute(
            text(
                """
                SELECT user_question, model_answer, documents, recommended_questions, think, created_at
                FROM messages
                WHERE session_id = :session_id
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"session_id": session_id, "limit": limit},
        ).fetchall()
        memory = []
        for row in reversed(rows):
            documents = []
            if row.documents:
                try:
                    documents = json.loads(row.documents)
                except (json.JSONDecodeError, TypeError):
                    documents = []
            memory.append(
                {
                    "user_question": row.user_question,
                    "model_answer": row.model_answer,
                    "documents": documents[:3] if isinstance(documents, list) else [],
                    "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        return memory
    except SQLAlchemyError as e:
        raise RuntimeError(f"Failed to fetch session memory: {str(e)}")
    finally:
        db.close()
