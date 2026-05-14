from fastapi import APIRouter, Body, Depends, UploadFile, File, HTTPException, Query, status
import uuid
from schemas.chat import ChatRequest
from fastapi.responses import StreamingResponse
import os
import shutil
import zipfile
from pathlib import Path
from dotenv import load_dotenv
from typing import List
from service.core.api.utils.file_utils import get_project_base_directory
from database.knowledgebase_operations import bind_session_repository, get_user_history_questions
from service.core.retrieval import retrieve_content
from service.core.chat import (
    get_chat_completion,
    generate_recommended_questions,
    get_general_chat_completion,
    stream_memory_answer,
    stream_plain_answer,
)
from utils import logger
from typing import List, Optional
from database.knowledgebase_operations import verify_user_knowledgebase
from service.agent.agent import final_answer
from sqlalchemy.orm import Session
from service.repository_service import create_repository_from_source, resolve_repository_context
from service.repository_overview import build_repository_overview_evidence, is_repository_overview_query
from utils.database import get_db
from utils.prompt import CodebaseAnswerPrompt, GeneralAnswerPrompt
from utils.query_intent import QueryIntent, chitchat_answer, classify_query_intent
import json

# 加载 .env 文件
load_dotenv()

router = APIRouter()


def _ensure_storage_dir(session_id: str):
    storage_dir = os.path.join(get_project_base_directory(), "storage/file")
    os.makedirs(storage_dir, exist_ok=True)
    session_dir = os.path.join(storage_dir, session_id)
    os.makedirs(session_dir, exist_ok=True)
    return storage_dir, session_dir


def _safe_extract_zip(zip_path: str, extract_dir: str):
    root = Path(extract_dir).resolve()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            member_path = Path(extract_dir, member.filename).resolve()
            if not str(member_path).startswith(str(root)):
                raise ValueError("zip archive contains invalid paths")
        archive.extractall(extract_dir)


def _detect_repo_root(extract_dir: str):
    children = [entry for entry in os.scandir(extract_dir) if entry.name != "__MACOSX"]
    if len(children) == 1 and children[0].is_dir():
        return children[0].path
    return extract_dir



##################################
# 创建一个新的对话 Session
##################################

@router.post("/create_session")
async def create_session(
    # credentials: JwtAuthorizationCredentials = Security(access_security),
):
    try:
        user_id = "1"
        # user_id = credentials.subject.get("user_id")
        # if not user_id:
        #     raise HTTPException(status_code=401, detail="Invalid authentication credentials")

        session_id = str(uuid.uuid4()).replace("-", "")[:16]

        return {
            "session_id": session_id,
            "status": "success",
            "message": "Session created successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    
@router.post("/upload_files/")
async def upload_files(
    session_id: Optional[str] = Query(None),
    files: List[UploadFile] = File(...),
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    if session_id is None:
        session_id = "default"  # 设置默认值
    storage_dir, session_dir = _ensure_storage_dir(session_id)
    
    try:
        user_id = "1"
        uploaded_repositories = []

        for file in files:
            file_name = file.filename or "uploaded_file"
            file_path = os.path.join(session_dir, file_name)
            
            # 保存文件到本地
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())
            
            repository = create_repository_from_source(
                db=db,
                user_id=user_id,
                name=file_name,
                source_path=file_path,
                storage_path=file_path,
                root_path=file_path,
                session_id=session_id,
                metadata={
                    "upload_kind": "single_file",
                    "session_id": session_id,
                },
            )
            uploaded_repositories.append(
                {
                    "repository_id": repository["id"],
                    "repository_name": repository["name"],
                    "indexed_chunks": repository.get("indexed_chunks", 0),
                }
            )
            logger.info("数据插入代码知识库")

        db.commit()

        return {
            "status": "success",
            "message": "文件解析成功",
            "repositories": uploaded_repositories,
        }
    
    except Exception as e:
        db.rollback()
        logger.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/upload_project_archive/")
async def upload_project_archive(
    session_id: Optional[str] = Query(None),
    archive: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    if session_id is None:
        session_id = "default"
    storage_dir, session_dir = _ensure_storage_dir(session_id)

    try:
        user_id = "1"
        archive_name = archive.filename or "project.zip"
        if not archive_name.lower().endswith(".zip"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .zip archives are supported for project uploads",
            )

        archive_path = os.path.join(session_dir, archive_name)
        with open(archive_path, "wb") as buffer:
            buffer.write(await archive.read())

        repo_name = Path(archive_name).stem
        extract_dir = os.path.join(session_dir, repo_name)
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)

        _safe_extract_zip(archive_path, extract_dir)
        repo_root = _detect_repo_root(extract_dir)
        repository = create_repository_from_source(
            db=db,
            user_id=user_id,
            name=repo_name,
            source_path=repo_root,
            storage_path=extract_dir,
            root_path=repo_root,
            archive_path=archive_path,
            session_id=session_id,
            metadata={
                "upload_kind": "project_archive",
                "archive_name": archive_name,
                "session_id": session_id,
            },
            is_archive=True,
        )
        db.commit()

        return {
            "status": "success",
            "message": "项目目录解析成功",
            "repo_name": repo_name,
            "repo_root": repo_root,
            "indexed_chunks": repository.get("indexed_chunks", 0),
            "repository_id": repository["id"],
            "archive_path": f"{storage_dir}/{session_id}/{archive_name}",
        }

    except HTTPException as e:
        raise e
    except zipfile.BadZipFile as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid zip archive: {str(e)}",
        )
    except Exception as e:
        db.rollback()
        logger.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/ai_search/")
async def ai_search(
    session_id: str = Query(...),
    request: ChatRequest = Body(..., description="User message"),
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    try:
        user_id = '1'
        
        question = request.message
        query_intent = classify_query_intent(question)
        explicit_repository_ids = request.repository_ids or (
            [request.repository_id] if request.repository_id else None
        )

        if query_intent == QueryIntent.CHITCHAT:
            return StreamingResponse(
                stream_plain_answer(
                    session_id=session_id,
                    question=question,
                    answer=chitchat_answer(question),
                    user_id=user_id,
                ),
                media_type="text/event-stream",
            )

        if query_intent == QueryIntent.MEMORY:
            return StreamingResponse(
                stream_memory_answer(
                    session_id=session_id,
                    question=question,
                    user_id=user_id,
                ),
                media_type="text/event-stream",
            )

        if query_intent == QueryIntent.GENERAL:
            snippets = []
            if request.web_search:
                try:
                    from service.web_search.web_search import process_search_results, serper_search

                    search_results = serper_search(question)
                    snippets, _ = process_search_results(search_results)
                except Exception as e:
                    logger.warning(f"web search failed: {e}")
            history_questions = get_user_history_questions(session_id)
            final_prompt = GeneralAnswerPrompt % (
                json.dumps(snippets, ensure_ascii=False, indent=2),
                history_questions,
                question,
            )
            return StreamingResponse(
                get_general_chat_completion(
                    session_id=session_id,
                    question=question,
                    user_id=user_id,
                    final_prompt=final_prompt,
                    snippets=snippets,
                ),
                media_type="text/event-stream",
            )

        
        # 验证用户是否有自己的知识库
        has_knowledgebase = verify_user_knowledgebase(user_id)
        
        references = []
        resolved_repositories = []
        if has_knowledgebase:
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
            repository_ids = [repo["id"] for repo in resolved_repositories] or None
            if session_id and repository_ids:
                bind_session_repository(user_id, session_id, repository_ids[0], db=db)
                db.commit()
            overview_evidence = (
                build_repository_overview_evidence(resolved_repositories)
                if is_repository_overview_query(question)
                else []
            )
            references = overview_evidence + retrieve_content(user_id, question, repository_ids=repository_ids)
            repository_by_id = {repo["id"]: repo for repo in resolved_repositories}
            for reference in references:
                repo = repository_by_id.get(reference.get("repository_id"))
                if repo:
                    reference["repository_name"] = repo.get("name")
                    reference["repository_type"] = repo.get("type")
            print("知识库查询结果：\n")
            print(references)
        else:
            # 如果用户没有知识库，跳过知识库查询，继续执行其他逻辑
            print("知识库未找到相关查询结果：\n")
            pass

        # 历史上下文
        # 查询 messages 表中对应 session_id 的消息
        history_questions = get_user_history_questions(session_id)

        print("历史问题：\n")
        print(history_questions)

        snippets = []
        if request.web_search:
            try:
                from service.web_search.web_search import process_search_results, serper_search

                search_results = serper_search(question)
                snippets, _ = process_search_results(search_results)
            except Exception as e:
                logger.warning(f"web search failed: {e}")

        try:
            related_questions = generate_recommended_questions(question, references)
        except Exception as e:
            logger.warning(f"recommended question generation failed: {e}")
            related_questions = []
        final_reference_payload = {
            "repository_snippets": references,
            "web_search": snippets,
        }
        final_reference = json.dumps(final_reference_payload, ensure_ascii=False, indent=2)

        # 大模型生成
        final_prompt = CodebaseAnswerPrompt % (final_reference, history_questions, question)
        
        print(final_prompt)

        # 返回流式响应
        return StreamingResponse(
            get_chat_completion(
                session_id,
                question,
                references,
                user_id,
                final_prompt,
                related_questions,
                snippets,
                repository_context=resolved_repositories,
                include_web_search=request.web_search,
                include_media=request.include_media,
            ),
            media_type="text/event-stream"
        )

    
    except HTTPException as e:
        # 捕获 HTTPException 并重新抛出，保持状态码和详情
        raise e
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/deep_research/")
async def deep_research(
    session_id: str = Query(...),
    request: ChatRequest = Body(..., description="User message"),
    # credentials: JwtAuthorizationCredentials = Security(access_security),
    db: Session = Depends(get_db),
):
    try:
        user_id = "1"
        question = request.message
        query_intent = classify_query_intent(question)
        if query_intent == QueryIntent.MEMORY:
            return StreamingResponse(
                stream_memory_answer(
                    session_id=session_id,
                    question=question,
                    user_id=user_id,
                ),
                media_type="text/event-stream",
            )

        if query_intent in (QueryIntent.CHITCHAT, QueryIntent.GENERAL):
            return StreamingResponse(
                final_answer(
                    question,
                    user_id=user_id,
                    repository_ids=None,
                    repository_context=[],
                    session_id=session_id,
                    allow_web_search=request.web_search,
                    persist_history=True,
                ),
                media_type="text/event-stream"
            )

        explicit_repository_ids = request.repository_ids or (
            [request.repository_id] if request.repository_id else None
        )
        resolved_repositories = []

        if verify_user_knowledgebase(user_id):
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

            repository_ids = [repo["id"] for repo in resolved_repositories] or None
            if session_id and repository_ids:
                bind_session_repository(user_id, session_id, repository_ids[0], db=db)
                db.commit()
        else:
            repository_ids = None

        print("处理问题：")
        print(question)
        return StreamingResponse(
            final_answer(
                question,
                user_id=user_id,
                repository_ids=repository_ids,
                repository_context=resolved_repositories,
                session_id=session_id,
                allow_web_search=request.web_search,
                persist_history=True,
            ),
            media_type="text/event-stream"
        )

    
    except HTTPException as e:
        # 捕获 HTTPException 并重新抛出，保持状态码和详情
        raise e
    except Exception as e:
        logger.exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
