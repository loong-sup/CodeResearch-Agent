import json
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from utils.database import get_db
from fastapi import HTTPException
from utils import logger
from service.web_search.web_search import serper_images, serper_videos
from database.knowledgebase_operations import get_session_memory
from service.model_config import get_fast_generation_model, get_generation_client, get_generation_model


def build_citations_payload(retrieved_content):
    citations = []
    for ref in retrieved_content or []:
        citation = ref.get("citation")
        if not citation:
            continue
        citations.append({
            "id": ref.get("id"),
            "chunk_id": ref.get("chunk_id"),
            "citation": citation,
            "citation_display": ref.get("citation_display", f"[{citation}]"),
            "file_path": ref.get("file_path"),
            "start_line": ref.get("start_line"),
            "end_line": ref.get("end_line"),
            "symbol": ref.get("symbol", ""),
            "language": ref.get("language", ""),
            "chunk_kind": ref.get("chunk_kind", ""),
            "repository_id": ref.get("repository_id"),
            "preview": ref.get("content_with_weight", "")[:240],
        })
    return citations


def _sse_message(payload):
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def build_memory_answer(question: str, memory: list[dict]):
    if not memory:
        return "当前会话还没有可用的历史记录。"

    normalized = (question or "").strip()
    user_questions = [item.get("user_question", "") for item in memory if item.get("user_question")]

    if any(token in normalized for token in ("最开始", "一开始", "开始", "第一个", "第一条")):
        return f"你在当前会话最开始问的是：{user_questions[0]}"

    if any(token in normalized for token in ("上一个", "上一条", "刚才", "最近", "前一个")):
        return f"你上一个问题是：{user_questions[-1]}"

    if any(token in normalized for token in ("总结", "概括", "回顾", "聊了什么", "问过什么", "哪些问题")):
        lines = ["当前会话里你问过这些问题："]
        for index, user_question in enumerate(user_questions, start=1):
            lines.append(f"{index}. {user_question}")
        return "\n".join(lines)

    return f"我记得当前会话最近的问题是：{user_questions[-1]}"


def stream_memory_answer(
    session_id: str,
    question: str,
    user_id: str,
    persist_history: bool = True,
):
    try:
        memory = get_session_memory(session_id, limit=20)
        answer = build_memory_answer(question, memory)
    except Exception as e:
        logger.warning(f"failed to read session memory: {e}")
        answer = "读取当前会话历史时失败了，请稍后再试。"

    yield _sse_message({
        "role": "assistant",
        "content": answer,
        "thinking": False,
        "answer_scope": "memory",
    })
    yield "event: end\ndata: [DONE]\n\n"

    if persist_history:
        try:
            write_chat_to_db(session_id, question, answer, [], [], "")
            update_session_name(session_id, question, user_id)
        except Exception as e:
            logger.warning(f"failed to persist memory answer: {e}")


def stream_plain_answer(
    session_id: str,
    question: str,
    answer: str,
    user_id: str,
    persist_history: bool = True,
):
    message = {
        "role": "assistant",
        "content": answer,
        "thinking": False,
        "answer_scope": "chitchat",
    }
    yield _sse_message(message)
    yield "event: end\ndata: [DONE]\n\n"
    if persist_history:
        try:
            write_chat_to_db(session_id, question, answer, [], [], "")
            update_session_name(session_id, question, user_id)
        except Exception as e:
            logger.warning(f"failed to persist plain answer: {e}")


def get_general_chat_completion(
    session_id,
    question,
    user_id,
    final_prompt,
    snippets=None,
    persist_history=True,
):
    model_answer = ""
    think = ""
    try:
        if snippets:
            yield _sse_message({"web_search": snippets, "answer_scope": "general"})

        client = get_generation_client(timeout=60)
        completion = client.chat.completions.create(
            model=get_generation_model(),
            messages=[{"role": "user", "content": final_prompt}],
            stream=True,
        )

        for chunk in completion:
            if chunk.choices[0].finish_reason == "stop":
                if persist_history:
                    try:
                        write_chat_to_db(session_id, question, model_answer, [], [], think)
                        update_session_name(session_id, question, user_id)
                    except Exception as e:
                        logger.warning(f"failed to persist general answer: {e}")
                yield "event: end\ndata: [DONE]\n\n"
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
                    "answer_scope": "general",
                })
            elif reasoning_content:
                think += reasoning_content
                yield _sse_message({
                    "role": "assistant",
                    "content": reasoning_content,
                    "thinking": True,
                    "answer_scope": "general",
                })
    except Exception as e:
        logger.warning(f"general answer generation failed: {e}")
        fallback = (
            "这个问题不属于当前代码库的实现、调用链或配置范围。"
            "当前通用回答生成暂时不可用；如果你希望我基于代码库分析，请补充具体文件、接口、函数、报错或模块名称。"
        )
        if not model_answer:
            yield _sse_message({
                "role": "assistant",
                "content": fallback,
                "thinking": False,
                "answer_scope": "fallback",
            })
            model_answer = fallback
            if persist_history:
                try:
                    write_chat_to_db(session_id, question, model_answer, [], [], think)
                    update_session_name(session_id, question, user_id)
                except Exception as persist_error:
                    logger.warning(f"failed to persist fallback answer: {persist_error}")
        yield "event: end\ndata: [DONE]\n\n"


def generate_recommended_questions(user_question, retrieved_content):
    """
    根据用户提问和检索到的内容生成推荐问题。

    :param user_question: 用户提问
    :param retrieved_content: 检索到的内容
    :return: 推荐问题列表
    """
    # 示例：基于用户提问和检索内容生成推荐问题

    # 判断 contents 是否为空
    is_code_context = any(isinstance(ref, dict) and ref.get("file_path") for ref in retrieved_content or [])

    if not retrieved_content:
        formatted_references = "知识库没有找到相关内容, 请结合你自己的知识回答"
    else:
        # 格式化参考内容
        if is_code_context:
            formatted_references = "\n".join([
                f"[{ref['id']}] {ref.get('citation', '')}\n{ref['content_with_weight']}"
                for ref in retrieved_content
            ])
        else:
            formatted_references = "\n".join([f"[{ref['id']}] {ref['content_with_weight']}" for ref in retrieved_content])

   # 构造提示词
    prompt = f"""
    请根据以下用户提问和检索到的内容，生成 3 个相关的推荐问题：
    用户提问：{user_question}
    检索内容：{formatted_references}

    要求：
    1. 每个问题以“问题X：”开头，X 为问题编号。
    2. 每个问题后面紧跟具体问题内容。
    3. 返回一个 JSON 对象，包含一个字段 "recommended_questions"，值为问题列表。
    4. 如果检索内容是代码库片段，推荐问题应聚焦于调用链、文件职责、符号实现、配置来源或测试覆盖。

    输出格式示例：
    {{
      "recommended_questions": [
        "问题1：具体问题内容1",
        "问题2：具体问题内容2",
        "问题3：具体问题内容3"
      ]
    }}
    
    请严格按照上述格式返回 JSON 对象。
    """
    
    try:
        client = get_generation_client(timeout=30)
        completion = client.chat.completions.create(
            model=get_fast_generation_model(),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            stream=False,
        )
    except Exception as e:
        logger.warning(f"recommended question generation failed: {e}")
        return []

    # 提取生成的推荐问题
    if completion.choices:
        response = completion.choices[0].message.content
        try:
            # 解析 JSON 响应
            response_json = json.loads(response)
            recommended_questions = response_json.get("recommended_questions")
            print("推荐的问题：\n")
            print(recommended_questions)
            return recommended_questions
        except json.JSONDecodeError:
            print("Failed to parse JSON response.")
            return []
    return []

def generate_session_name(user_question):
    prompt = f"""
    请根据以下用户提问，生成一个简洁且具有代表性的会话名称：
    用户提问：{user_question}

    要求：
    1. 会话名称应简洁明了，能够概括用户提问的主题。
    2. 返回一个 JSON 对象，包含一个字段 "session_name"，值为生成的会话名称。

    输出格式示例：
    {{
      "session_name": "会话名称内容"
    }}

    请严格按照上述格式返回 JSON 对象。
    """
    
    # 调用大模型生成会话名称
    try:
        client = get_generation_client()
        completion = client.chat.completions.create(
            model=get_fast_generation_model(),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            stream=False,
        )

        # 提取生成的会话名称
        if completion.choices:
            response = completion.choices[0].message.content
            try:
                # 解析 JSON 响应
                response_json = json.loads(response)
                session_name = response_json.get("session_name")
                print("生成的会话名称：\n")
                print(session_name)
                return session_name
            except json.JSONDecodeError:
                print("Failed to parse JSON response.")
                return user_question
    except Exception as e:
        print(f"An error occurred: {e}")
        return user_question


def write_chat_to_db(session_id: str, user_question: str, model_answer: str, retrieval_content, recommended_questions, think ):
    """
    将对话数据写入数据库。

    :param session_id: 会话 ID
    :param user_question: 用户问题
    :param model_answer: 大模型的回答
    :param retrieval_content: 检索内容
    """
    db = next(get_db())  # 获取数据库会话
    try:
        documents_json = json.dumps(retrieval_content, ensure_ascii=False)

        db.execute(
            text(
                """
                INSERT INTO messages (session_id, user_question, model_answer, documents, recommended_questions, think )
                VALUES (:session_id, :user_question, :model_answer, :documents, :recommended_questions, :think)
                """
            ),
            {
                "session_id": session_id,
                "user_question": user_question,
                "model_answer": model_answer,
                "documents": documents_json,
                "recommended_questions": recommended_questions,
                "think": think,
            }
        )
        db.commit()
        logger.info("对话数据插入成功。。。")
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to write to database: {str(e)}"
        )
    finally:
        db.close()

def update_session_name(session_id: str, question: str, user_id: str):
    """
    根据 session_id 查数据库的表 sessions，有的话直接跳过，没有的话先生成 session_name，再插入。

    :param session_id: 会话 ID
    :param user_id: 用户 ID
    """
    db = next(get_db())  # 获取数据库会话
    try:
        # 查询 sessions 表中是否存在该 session_id
        query_result = db.execute(
            text("SELECT session_name FROM sessions WHERE session_id = :session_id"),
            {"session_id": session_id}
        ).fetchone()

        if query_result:
            # 如果查到了，直接跳过
            logger.info(f"Session {session_id} already exists, skipping.")
        else:
            if question:
                session_name = generate_session_name(question)
                db.execute(
                    text(
                        """
                        INSERT INTO sessions (session_id, user_id, session_name)
                        VALUES (:session_id, :user_id, :session_name)
                        """
                    ),
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "session_name": session_name
                    }
                )
                db.commit()
                logger.info("会话数据插入成功。。。")
                print(f"New session {session_id} inserted with name: {session_name}")
            else:
                print(f"Failed to retrieve question for session {session_id}, skipping insertion.")
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Database operation failed: {str(e)}"
        )
    finally:
        db.close()

def get_chat_completion(
    session_id,
    question,
    retrieved_content,
    user_id,
    final_prompt,
    related_questions,
    snippets,
    repository_context=None,
    include_web_search=True,
    include_media=True,
):
    """
    获取流式聊天完成结果，并按照指定格式输出。

    :param session_id: 会话 ID（可选，如需区分不同会话可传入）
    :param question: 用户问题
    :return: 流式输出的生成器，每个元素为符合 SSE 格式的字符串
    """

    try:
        # 初始化 OpenAI 客户端
        # 返回知识库检索内容
        message = {
            "documents": retrieved_content,
        }
        json_message = json.dumps(message)
        yield f"event: message\ndata: {json_message}\n\n"

        citations = build_citations_payload(retrieved_content)
        if citations:
            message = {
                "citations": citations,
            }
            json_message = json.dumps(message)
            yield f"event: message\ndata: {json_message}\n\n"

        if repository_context:
            message = {
                "repository_context": [
                    {
                        "repository_id": repo.get("id"),
                        "repository_name": repo.get("name"),
                        "repository_type": repo.get("type"),
                        "status": repo.get("status"),
                    }
                    for repo in repository_context
                ]
            }
            json_message = json.dumps(message)
            yield f"event: message\ndata: {json_message}\n\n"

        if include_web_search:
            message = {
                "web_search": snippets,
            }
            json_message = json.dumps(message)
            yield f"event: message\ndata: {json_message}\n\n"

        # 初始化 OpenAI 客户端。放在首批 SSE 事件之后，避免模型连接慢时前端完全无响应。
        client = get_generation_client(timeout=60)

        # 创建聊天完成请求
        completion = client.chat.completions.create(
            model=get_generation_model(),
            messages=[
                {"role": "user", "content": final_prompt}
            ],
            stream=True,
        )

        # 处理流式响应
        model_answer = ""  # 用于存储大模型的回答
        think = "" # 用于存储思考过程
        for chunk in completion:
            # print("原始 chunk 数据:", chunk)
            if chunk.choices[0].finish_reason == "stop":
                # 返回推荐问题
                message = {
                    "recommended_questions": related_questions,
                }
                json_message = json.dumps(message)
                yield f"event: message\ndata: {json_message}\n\n"

                if include_media:
                    image_results = serper_images(q=question, hl="zh-cn")
                    video_results = serper_videos(q=question, hl="zh-cn")
                    message = {
                        "image_results": image_results,
                    }
                    json_message = json.dumps(message)
                    yield f"event: message\ndata: {json_message}\n\n"
                    message = {
                        "video_results": video_results,
                    }
                    json_message = json.dumps(message)
                    yield f"event: message\ndata: {json_message}\n\n"

                # 结束时发送 [DONE] 事件
                yield "event: end\ndata: [DONE]\n\n"
                # 将对话数据写入数据库
                print("最终回答：\n")
                print(model_answer)
                try:
                    write_chat_to_db(session_id, question, model_answer, retrieved_content, related_questions, think)
                    update_session_name(session_id, question, user_id)
                except Exception as persist_error:
                    logger.warning(f"failed to persist codebase answer: {persist_error}")
                break
            else:
                # 实时输出消息
                delta = chunk.choices[0].delta
                if delta.content:
                    model_answer += delta.content  # 累加大模型的回答
                    message = {
                        "role": "assistant",
                        "content": delta.content,
                        "thinking": False,
                    }
                    json_message = json.dumps(message)
                    yield f"event: message\ndata: {json_message}\n\n"
                else :
                    reasoning_content = getattr(delta, "reasoning_content", "") or ""
                    if not reasoning_content:
                        continue
                    think += reasoning_content
                    message = {
                        "role": "assistant",
                        "content": reasoning_content,
                        "thinking": True,
                    }
                    json_message = json.dumps(message)
                    yield f"event: message\ndata: {json_message}\n\n"

    except Exception as e:
        # 发生错误时返回错误信息
        error_message = {
            "role": "error",
            "content": str(e)
        }
        json_error_message = json.dumps(error_message)
        yield f"event: error\ndata: {json_error_message}\n\n"
        yield "event: end\ndata: [DONE]\n\n"
