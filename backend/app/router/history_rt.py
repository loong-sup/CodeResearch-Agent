from fastapi import APIRouter, Depends, HTTPException, Query, Security
from sqlalchemy.orm import Session
from utils.database import get_db
from schemas.message import FilestResponse , RepositoryCandidateResponse, SessionListResponse, SessionResponse, DeleteFileRequest
from fastapi_jwt import JwtAuthorizationCredentials
from service.auth import access_security
from typing import List
from sqlalchemy import text

from database.agent_operations import ensure_agent_schema
from service.repository_service import delete_repository_by_name, list_user_repositories, recommend_repository_candidates

router = APIRouter()

############################
#   获取文档列表
############################

@router.get("/get_files/", response_model=List[FilestResponse])
async def get_documents_by_user_id(
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db)
):
    try:
        user_id = "1"
        result = list_user_repositories(user_id, db=db)
        if not result:
            return []

        documents = [
            FilestResponse(
                user_id=row["user_id"],
                file_name=row.get("name", row.get("file_name", "")),
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
                repository_id=row.get("repository_id")
                or (str(row.get("id")) if row.get("name") and row.get("id") is not None else None),
                repository_type=row.get("type"),
                status=row.get("status"),
                indexed_chunks=row.get("indexed_chunks"),
            )
            for row in result
        ]

        return documents

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 删除文件接口
@router.delete("/delete_file/", status_code=200)
async def delete_file_by_name(
    file_name: str,  # 用户传入的文件名称
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db)
):
    try:
        user_id = "1"
        delete_result = delete_repository_by_name(user_id, file_name, db)
        db.commit()
        if not delete_result.found:
            raise HTTPException(status_code=404, detail="File not found")
        return {
            "message": "File deleted successfully",
            "repository_id": delete_result.repository_id,
            "chunks_deleted": delete_result.chunks_deleted,
            "files_deleted": delete_result.files_deleted,
            "metadata_deleted": delete_result.metadata_deleted,
            "messages_marked": delete_result.messages_marked,
        }

    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        # 捕获异常并返回 500 错误
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/get_messages/")
async def get_messages_by_session_id(
    session_id: str,
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db)
):
    try:
        user_id = "1"

        # 查询 messages 表中对应 session_id 的消息
        messages_data = db.execute(
            text("SELECT message_id, session_id, user_question, model_answer, documents, recommended_questions, think, created_at FROM messages WHERE session_id = :session_id"),
            {"session_id": session_id}
        ).fetchall()

        # 构造返回数据
        messages = []
        for message in messages_data:
            # 清理 recommended_questions 字符串
            recommended_questions = []
            if message.recommended_questions:
                recommended_questions_str = message.recommended_questions.strip('{}"')
                recommended_questions = [q.strip() for q in recommended_questions_str.split(",") if q.strip()]
            messages.append(
                {
                    "message_id": message.message_id,
                    "session_id": message.session_id,
                    "user_question": message.user_question,
                    "model_answer":message.model_answer,
                    "documents" : message.documents,
                    "recommended_questions" : recommended_questions,
                    "think" : message.think,
                    "created_at": message.created_at.strftime("%Y-%m-%d %H:%M:%S")
                }
            )

        return messages

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve messages: {str(e)}"
        )
    
@router.get("/get_sessions/", response_model=SessionListResponse)
async def get_sessions_by_user_id(
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db)
):
    try:
        user_id = "1"


        # 查询 sessions 表中对应 user_id 的所有会话
        sessions_data = db.execute(
            text("SELECT * FROM sessions WHERE user_id = :user_id"),
            {"user_id": user_id}
        ).fetchall()

        # 构造返回数据
        sessions = []
        for session in sessions_data:
            sessions.append(
                SessionResponse(
                    session_id=session.session_id,
                    session_name=session.session_name,
                    user_id=session.user_id,
                    created_at=session.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    updated_at=session.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                )
            )

        return {"user_id": user_id, "sessions": sessions}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/get_repository_candidates/", response_model=List[RepositoryCandidateResponse])
async def get_repository_candidates(
    question: str = Query(...),
    session_id: str | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        user_id = "1"
        return recommend_repository_candidates(
            user_id=user_id,
            question=question,
            session_id=session_id,
            db=db,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_agent_runs/")
async def get_agent_runs(
    session_id: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        user_id = "1"
        ensure_agent_schema(db)
        rows = db.execute(
            text(
                """
                SELECT id, session_id, user_id, user_question, status, final_answer,
                       final_evidence, error, created_at, updated_at
                FROM agent_runs
                WHERE session_id = :session_id AND user_id = :user_id
                ORDER BY created_at DESC
                """
            ),
            {"session_id": session_id, "user_id": user_id},
        ).fetchall()
        return [
            {
                "id": str(row.id),
                "session_id": row.session_id,
                "user_id": row.user_id,
                "user_question": row.user_question,
                "status": row.status,
                "final_answer": row.final_answer,
                "final_evidence": row.final_evidence,
                "error": row.error,
                "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "updated_at": row.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/get_agent_steps/")
async def get_agent_steps(
    run_id: str = Query(...),
    db: Session = Depends(get_db),
):
    try:
        ensure_agent_schema(db)
        rows = db.execute(
            text(
                """
                SELECT id, run_id, step_type, tool_name, input_json, output_json, error, created_at
                FROM agent_steps
                WHERE run_id = :run_id
                ORDER BY created_at ASC
                """
            ),
            {"run_id": run_id},
        ).fetchall()
        return [
            {
                "id": str(row.id),
                "run_id": str(row.run_id),
                "step_type": row.step_type,
                "tool_name": row.tool_name,
                "input_json": row.input_json,
                "output_json": row.output_json,
                "error": row.error,
                "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
