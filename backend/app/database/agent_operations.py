import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from utils.database import get_db


_SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS agent_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        session_id VARCHAR(16) NOT NULL,
        user_id VARCHAR(255) NOT NULL,
        user_question TEXT NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'running',
        repository_context TEXT,
        final_answer TEXT,
        final_evidence TEXT,
        error TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id ON agent_runs(user_id)",
    """
    CREATE TABLE IF NOT EXISTS agent_steps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        run_id UUID NOT NULL,
        step_type VARCHAR(32) NOT NULL,
        tool_name VARCHAR(128),
        input_json TEXT,
        output_json TEXT,
        error TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_agent_steps_run_id ON agent_steps(run_id)",
]


def _json_dumps(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def ensure_agent_schema(db: Optional[Session] = None) -> None:
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
        raise RuntimeError(f"Failed to ensure agent schema: {str(e)}")
    finally:
        if owns_db:
            db.close()


def create_agent_run(
    *,
    session_id: str,
    user_id: str,
    user_question: str,
    repository_context: Optional[list[dict[str, Any]]] = None,
    db: Optional[Session] = None,
) -> str:
    owns_db = db is None
    db = db or next(get_db())
    ensure_agent_schema(db)
    try:
        row = db.execute(
            text(
                """
                INSERT INTO agent_runs (
                    session_id, user_id, user_question, status, repository_context
                )
                VALUES (
                    :session_id, :user_id, :user_question, 'running', :repository_context
                )
                RETURNING id
                """
            ),
            {
                "session_id": session_id,
                "user_id": user_id,
                "user_question": user_question,
                "repository_context": _json_dumps(repository_context or []),
            },
        ).fetchone()
        if owns_db:
            db.commit()
        return str(row.id)
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to create agent run: {str(e)}")
    finally:
        if owns_db:
            db.close()


def save_agent_step(
    *,
    run_id: str,
    step_type: str,
    tool_name: Optional[str] = None,
    input_payload: Any = None,
    output_payload: Any = None,
    error: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    owns_db = db is None
    db = db or next(get_db())
    ensure_agent_schema(db)
    try:
        db.execute(
            text(
                """
                INSERT INTO agent_steps (
                    run_id, step_type, tool_name, input_json, output_json, error
                )
                VALUES (
                    :run_id, :step_type, :tool_name, :input_json, :output_json, :error
                )
                """
            ),
            {
                "run_id": run_id,
                "step_type": step_type,
                "tool_name": tool_name,
                "input_json": _json_dumps(input_payload),
                "output_json": _json_dumps(output_payload),
                "error": error,
            },
        )
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to save agent step: {str(e)}")
    finally:
        if owns_db:
            db.close()


def finish_agent_run(
    *,
    run_id: str,
    status: str,
    final_answer: Optional[str] = None,
    final_evidence: Any = None,
    error: Optional[str] = None,
    db: Optional[Session] = None,
) -> None:
    owns_db = db is None
    db = db or next(get_db())
    ensure_agent_schema(db)
    try:
        db.execute(
            text(
                """
                UPDATE agent_runs
                SET status = :status,
                    final_answer = :final_answer,
                    final_evidence = :final_evidence,
                    error = :error,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :run_id
                """
            ),
            {
                "run_id": run_id,
                "status": status,
                "final_answer": final_answer,
                "final_evidence": _json_dumps(final_evidence),
                "error": error,
            },
        )
        if owns_db:
            db.commit()
    except SQLAlchemyError as e:
        if owns_db:
            db.rollback()
        raise RuntimeError(f"Failed to finish agent run: {str(e)}")
    finally:
        if owns_db:
            db.close()
