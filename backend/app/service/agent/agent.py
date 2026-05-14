import json
import os
import re

from openai import OpenAI

from database.agent_operations import create_agent_run, finish_agent_run, save_agent_step
from database.knowledgebase_operations import get_session_memory
from service.agent.tools import tool_registry
from service.core.chat import update_session_name, write_chat_to_db
from service.core.retrieval import (
    retrieve_content,
    retrieve_exact_filename_content,
    retrieve_supporting_file_docs,
)


MIN_PROMPT_LENGTH = 2
MAX_PLAN_PROMPTS = 3
MAX_REFLECTION_PROMPTS = 2
PER_PROMPT_RESULT_LIMIT = 4
FINAL_EVIDENCE_LIMIT = 8
FILE_ROLE_HINT_KEYWORDS = ("作用", "做什么", "入口", "启动", "用途", "职责")
SUPPORTING_DOC_HINT_TOKENS = ("readme", "architecture", "design", "spec", "guide", "reference", "manual")


def extract_json_content(input_str: str | None):
    if not input_str:
        return None
    pattern = r"(\[[\s\S]*\])"
    match = re.search(pattern, input_str)
    return match.group(1) if match else None


def middle_json_model(prompt: str):
    client = OpenAI(
        api_key=os.getenv("DASHSCOPE_API_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    completion = client.chat.completions.create(
        model="qwen-max",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
    )
    return completion.choices[0].message.content


def normalize_action_payload(raw_result):
    json_list = extract_json_content(raw_result)
    try:
        payload = json.loads(json_list or raw_result)
    except Exception:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("actions", "tools", "result", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def enrich_references(references: list[dict], repository_by_id: dict[str, dict] | None = None):
    if not repository_by_id:
        return references
    enriched = []
    for reference in references:
        if not isinstance(reference, dict):
            continue
        repo = repository_by_id.get(reference.get("repository_id"))
        if repo:
            reference = dict(reference)
            reference["repository_name"] = repo.get("name")
            reference["repository_type"] = repo.get("type")
        enriched.append(reference)
    return enriched


def rag(query, user_id="1", repository_ids=None, repository_by_id=None):
    rag_results = retrieve_content(user_id, query, repository_ids=repository_ids)
    return enrich_references(rag_results, repository_by_id=repository_by_id)


def web_search_answer(query):
    try:
        from service.web_search.web_search import process_search_results, serper_search

        search_results = serper_search(query)
        snippets, related_questions = process_search_results(search_results)
        return snippets
    except Exception as e:
        print(f"网络搜索失败: {e}")
        return f"网络搜索暂时不可用，错误信息: {str(e)}"


def agent_plan(query):
    prompt = """
    # 代码库问答 Agent 的 Plan 模块

你是一个代码库问答助手的规划模块。你的任务是：
1. 分析用户查询：{0}
2. 在“代码索引检索”“项目文档检索”“代码结构检索”“网络搜索”四种工具之间做选择
3. 把原始问题拆解成 1-3 个更容易检索的子问题

## 可用工具
1. **代码索引检索**：适合查找函数、类、模块、配置、调用链、错误来源
2. **项目文档检索**：适合查找 README、设计说明、接口文档、使用说明
3. **代码结构检索**：适合快速定位文件树、入口文件、符号名称、模块分布
4. **网络搜索**：仅在仓库内信息明显不足时使用

## 工具选择规则
- 如果问题涉及“某个实现在哪、怎么调用、某个类/函数做了什么、配置从哪里生效”，优先使用**代码索引检索**
- 如果问题涉及“项目背景、模块职责、使用方法、文档说明”，优先使用**项目文档检索**
- 如果问题涉及“有哪些文件、入口在哪、有哪些类/函数、模块怎么分布”，优先使用**代码结构检索**
- 如果问题明显依赖外部资料，才使用**网络搜索**

## prompt 延伸规则
- 子问题必须有助于定位实现、调用链或相关文档
- 优先保留原问题，再补充 1-2 个更具体的检索问题
- 对寒暄、无明确技术内容的问题，返回 None

## 输出格式
你的输出应该是一个 JSON 对象，包含 `actions` 列表；每个项目包含：
1. `action_name`：工具名称（"代码索引检索"、"项目文档检索"、"代码结构检索"或"网络搜索"）
2. `prompts`：问题列表，第一个是原始查询，后面是拆解或延伸的问题
{{
  "actions": [
    {{
      "action_name": "工具名称",
      "prompts": [
        "原始查询",
        "拆解/延伸问题1",
        "拆解/延伸问题2"
      ]
    }}
  ]
}}

只需要输出JSON的部分，前后不要输出任何信息
""".format(query)
    result = middle_json_model(prompt)
    print(result)
    return normalize_action_payload(result)


def extract_target_filenames(query: str):
    matches = re.findall(r"([A-Za-z0-9_./-]+\.[A-Za-z0-9_]+)", query or "")
    cleaned = []
    seen = set()
    for match in matches:
        normalized = match.strip().strip("`'\"")
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def extract_target_filename(query: str):
    filenames = extract_target_filenames(query)
    return filenames[0] if filenames else None


def is_file_role_question(user_query: str):
    return any(keyword in (user_query or "") for keyword in FILE_ROLE_HINT_KEYWORDS)


def maybe_add_file_role_prompts(user_query: str, prompts: list[str]):
    if not user_query or not is_file_role_question(user_query):
        return prompts
    filename = extract_target_filename(user_query)
    if not filename:
        return prompts
    hints = [
        f"{filename} 文件的主要作用是什么",
        f"{filename} 是否是程序入口或启动文件",
        f"{filename} 中的 main 函数或启动逻辑在哪里",
    ]
    for hint in hints:
        if hint not in prompts:
            prompts.append(hint)
    return prompts


def is_supporting_document(item: dict):
    file_path = (item.get("file_path") or "").lower()
    return file_path.endswith((".md", ".markdown", ".rst", ".txt")) or any(
        token in file_path for token in SUPPORTING_DOC_HINT_TOKENS
    )


def build_exact_file_memory(user_query, user_id, repository_ids, repository_by_id):
    memory = []
    for filename in extract_target_filenames(user_query)[:2]:
        exact_results = retrieve_exact_filename_content(
            user_id=user_id,
            filename=filename,
            repository_ids=repository_ids,
            page_size=PER_PROMPT_RESULT_LIMIT * 2,
        )
        exact_results = enrich_references(exact_results, repository_by_id=repository_by_id)
        exact_results = select_relevant_results(exact_results, limit=PER_PROMPT_RESULT_LIMIT)
        if exact_results:
            memory.append(
                {
                    "提问": f"{filename} 精确文件召回",
                    "结果": exact_results,
                    "action_name": "精确文件召回",
                    "source_stage": "exact_file",
                }
            )

        if is_file_role_question(user_query):
            supporting_docs = retrieve_supporting_file_docs(
                user_id=user_id,
                filename=filename,
                question=user_query,
                repository_ids=repository_ids,
                page_size=PER_PROMPT_RESULT_LIMIT * 2,
            )
            supporting_docs = enrich_references(supporting_docs, repository_by_id=repository_by_id)
            supporting_docs = [item for item in supporting_docs if is_supporting_document(item)]
            supporting_docs = select_relevant_results(supporting_docs, limit=PER_PROMPT_RESULT_LIMIT)
            if supporting_docs:
                memory.append(
                    {
                        "提问": f"{filename} 相关文档辅助召回",
                        "结果": supporting_docs,
                        "action_name": "辅助文档召回",
                        "source_stage": "support_doc",
                    }
                )
    return deduplicate_memory_global(memory)


def adjust_format(original_data, max_prompts_per_action=MAX_PLAN_PROMPTS):
    adjusted_data = []
    if not isinstance(original_data, list):
        return adjusted_data

    seen = set()
    for item in original_data:
        if not isinstance(item, dict):
            continue
        action_name = item.get("action_name")
        prompts = item.get("prompts")
        if not isinstance(action_name, str) or not action_name.strip():
            continue
        if isinstance(prompts, str):
            prompts = [prompts]
        elif not isinstance(prompts, list):
            continue

        cleaned_prompts = []
        for prompt in prompts:
            if not isinstance(prompt, str):
                continue
            prompt = prompt.strip()
            if len(prompt) < MIN_PROMPT_LENGTH:
                continue
            if prompt in cleaned_prompts:
                continue
            cleaned_prompts.append(prompt)

        for prompt in cleaned_prompts[:max_prompts_per_action]:
            pair = (action_name, prompt)
            if pair in seen:
                continue
            seen.add(pair)
            adjusted_data.append({"action_name": action_name, "prompt": prompt})

    return adjusted_data


def reflection(user_query, evidence_summary):
    prompt = """
你是一个代码库问答助手的反思模块。你的任务是：
1. 分析用户查询：{0}
2. 基于已有信息，判断是否还需要补充检索

## 目前已有的信息
{1}

## 可用工具
1. **代码索引检索**：查找实现、调用链、配置、错误来源
2. **项目文档检索**：查找 README、设计说明、接口文档
3. **代码结构检索**：查找文件树、入口文件、符号和模块分布
4. **网络搜索**：仅在仓库内证据不足时使用

## 延伸规则
- 最多再扩展 1-2 个简单检索问题
- 如果问题已经有足够证据支撑，返回 None
- 如果选择网络搜索，必须因为本地仓库证据明显不足
- 不要重复已有问题，也不要输出单个字、单个词或无意义片段

## 输出格式
如果不需要补充检索，返回 None。
如果需要补充检索，输出一个 JSON 对象，包含 `actions` 列表；每个项目包含：
1. `action_name`：工具名称（"代码索引检索"、"项目文档检索"、"代码结构检索"或"网络搜索"）
2. `prompts`：问题列表，必须是可直接检索的完整问题
{{
  "actions": [
    {{
      "action_name": "工具名称",
      "prompts": [
        "补充问题1",
        "补充问题2"
      ]
    }}
  ]
}}
""".format(user_query, json.dumps(evidence_summary, ensure_ascii=False, indent=2))
    result = middle_json_model(prompt)
    return normalize_action_payload(result)


def select_relevant_results(result, limit=PER_PROMPT_RESULT_LIMIT):
    if not isinstance(result, list):
        return result

    def score(item):
        if not isinstance(item, dict):
            return -1
        return (
            3 if item.get("citation") else 0,
            2 if item.get("file_path") else 0,
            1 if item.get("symbol") else 0,
            len(item.get("content_with_weight", "")),
        )

    filtered = [item for item in result if isinstance(item, dict)]
    filtered.sort(key=score, reverse=True)
    return filtered[:limit]


def deduplicate_memory_global(memory):
    if not isinstance(memory, list):
        return memory

    seen_content = set()
    deduplicated_memory = []
    for memory_item in memory:
        if not isinstance(memory_item, dict) or "结果" not in memory_item:
            deduplicated_memory.append(memory_item)
            continue

        result = memory_item["结果"]
        if isinstance(result, list):
            deduplicated_result = []
            for item in result:
                if isinstance(item, dict) and item.get("content_with_weight"):
                    content = item["content_with_weight"].strip()
                    if content in seen_content:
                        continue
                    seen_content.add(content)
                    deduplicated_result.append(item)
                elif isinstance(item, dict):
                    deduplicated_result.append(item)

            new_memory_item = dict(memory_item)
            new_memory_item["结果"] = deduplicated_result
            deduplicated_memory.append(new_memory_item)
        else:
            deduplicated_memory.append(memory_item)

    return deduplicated_memory


def build_memory_citations(memory):
    citations = []
    seen = set()
    for memory_item in memory:
        result = memory_item.get("结果", []) if isinstance(memory_item, dict) else []
        if not isinstance(result, list):
            continue
        for item in result:
            if not isinstance(item, dict):
                continue
            citation = item.get("citation")
            if not citation or citation in seen:
                continue
            seen.add(citation)
            citations.append(
                {
                    "id": item.get("id"),
                    "chunk_id": item.get("chunk_id"),
                    "citation": citation,
                    "citation_display": item.get("citation_display", f"[{citation}]"),
                    "file_path": item.get("file_path"),
                    "start_line": item.get("start_line"),
                    "end_line": item.get("end_line"),
                    "symbol": item.get("symbol", ""),
                    "language": item.get("language", ""),
                    "chunk_kind": item.get("chunk_kind", ""),
                    "repository_id": item.get("repository_id"),
                    "preview": item.get("content_with_weight", "")[:240],
                }
            )
    return citations


def build_final_evidence(memory, limit=FINAL_EVIDENCE_LIMIT):
    evidence = []
    seen = set()
    for memory_item in memory:
        if not isinstance(memory_item, dict):
            continue
        question = memory_item.get("提问", "")
        source_stage = memory_item.get("source_stage", "plan")
        action_name = memory_item.get("action_name", "")
        result = memory_item.get("结果", [])
        if not isinstance(result, list):
            continue
        for item in result:
            if not isinstance(item, dict):
                continue
            key = (
                item.get("chunk_id")
                or item.get("citation")
                or item.get("content_with_weight")
                or f"{item.get('file_path', '')}:{item.get('symbol', '')}:{item.get('type', '')}"
            )
            if not key or key in seen:
                continue
            seen.add(key)
            evidence_item = dict(item)
            evidence_item["question"] = question
            evidence_item["source_stage"] = source_stage
            evidence_item["action_name"] = action_name
            evidence.append(evidence_item)
            if len(evidence) >= limit:
                return evidence
    return evidence


def build_citations_from_evidence(evidence):
    return build_memory_citations([{"结果": evidence}])


def count_high_quality_evidence(memory):
    count = 0
    for item in build_final_evidence(memory, limit=FINAL_EVIDENCE_LIMIT):
        if item.get("citation") and item.get("file_path"):
            count += 1
    return count


def should_run_reflection(user_query, memory):
    if not memory:
        return True
    if count_high_quality_evidence(memory) >= 4:
        return False
    return len(user_query.strip()) >= 6


def process_actions(
    actions,
    user_id="1",
    repository_ids=None,
    repository_by_id=None,
    repository_context=None,
    run_id=None,
    allow_web_search=True,
    stage="plan",
    per_prompt_limit=PER_PROMPT_RESULT_LIMIT,
):
    memory = []
    for action in actions:
        action_name = action["action_name"]
        prompt = action["prompt"]

        print(f'正在执行{action_name}: "{prompt}"')
        try:
            tool_name = "项目文档检索" if action_name == "本地文档搜索" else action_name
            tool_result = tool_registry.run(
                tool_name,
                query=prompt,
                user_id=user_id,
                repository_ids=repository_ids,
                repository_by_id=repository_by_id,
                repository_context=repository_context,
                allow_web_search=allow_web_search,
                limit=per_prompt_limit,
            )
            result = tool_result.to_memory_result()
            if isinstance(result, list) and tool_name != "网络搜索":
                result = select_relevant_results(result, limit=per_prompt_limit)

            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="tool_call",
                    tool_name=tool_name,
                    input_payload={"query": prompt, "stage": stage},
                    output_payload=tool_result.to_log_payload(),
                    error=tool_result.error,
                )

            memory_item = {
                "提问": prompt,
                "结果": result,
                "action_name": tool_name,
                "source_stage": stage,
            }
            memory.append(memory_item)

            print(f"提问：{prompt}")
            print(f"结果：{result}")
            print("-------------------")
        except Exception as e:
            print(f"--------{action_name}检索失败，错误详情: {str(e)}-----------")
            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="tool_call",
                    tool_name=action_name,
                    input_payload={"query": prompt, "stage": stage},
                    error=str(e),
                )
            import traceback

            print(f"完整错误堆栈: {traceback.format_exc()}")
            continue

    print("所有执行动作已完成，结果已添加到memory中。")
    total_before = sum(len(item["结果"]) if isinstance(item["结果"], list) else 1 for item in memory)
    deduplicated_memory = deduplicate_memory_global(memory)
    total_after = sum(len(item["结果"]) if isinstance(item["结果"], list) else 1 for item in deduplicated_memory)
    print(f"去重前memory数量: {len(memory)}, 去重后memory数量: {len(deduplicated_memory)}")
    print(f"去重前总结果数量: {total_before}, 去重后总结果数量: {total_after}, 过滤了 {total_before - total_after} 个重复项")
    return deduplicated_memory


def format_repository_context(repository_context):
    if not repository_context:
        return []
    return [
        {
            "repository_id": item.get("id") or item.get("repository_id"),
            "repository_name": item.get("name") or item.get("repository_name"),
            "repository_type": item.get("type") or item.get("repository_type"),
            "status": item.get("status"),
        }
        for item in repository_context
        if isinstance(item, dict)
    ]


def build_final_prompt(user_query, repository_context, final_evidence, session_memory=None):
    repo_context_text = json.dumps(format_repository_context(repository_context), ensure_ascii=False, indent=2)
    evidence_text = json.dumps(final_evidence, ensure_ascii=False, indent=2)
    session_memory_text = json.dumps(session_memory or [], ensure_ascii=False, indent=2)
    return f"""
你是一个资深代码库问答助手。请基于当前代码库上下文和证据，直接回答用户问题。

回答要求：
1. 先直接回答用户问题，不要先复述“第几个参考内容”。
2. 只根据证据中的仓库路径、文件路径和片段做结论，不要编造。
3. 重要结论必须使用内联引用，格式为 [文件路径:起始行-结束行]。
4. 如果存在同名文件或多仓库上下文，先说明当前结论对应的仓库/路径。
5. 如果证据不足，明确说明缺少哪些信息。
6. 语言保持工程分析风格，不要使用销售或营销语言。

当前代码库上下文：
{repo_context_text}

最近会话记忆：
{session_memory_text}

证据：
{evidence_text}

用户问题：
{user_query}
"""


def send_agent_updates(actions):
    for action in actions:
        message = {
            "role": "agent",
            "content": f'正在执行{action["action_name"]}: "{action["prompt"]}"',
        }
        yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"


def final_answer(
    user_query,
    user_id="1",
    repository_ids=None,
    repository_context=None,
    session_id=None,
    allow_web_search=True,
    persist_history=True,
):
    run_id = None
    final_evidence = []
    model_answer = ""
    think = ""
    try:
        client = OpenAI(
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        repository_context = repository_context or []
        repository_by_id = {
            item.get("id") or item.get("repository_id"): item
            for item in repository_context
            if isinstance(item, dict)
        }
        formatted_repository_context = format_repository_context(repository_context)
        session_memory = get_session_memory(session_id) if session_id else []
        memory_global = []

        if session_id:
            run_id = create_agent_run(
                session_id=session_id,
                user_id=user_id,
                user_question=user_query,
                repository_context=formatted_repository_context,
            )
            yield f"event: message\ndata: {json.dumps({'agent_run_id': run_id}, ensure_ascii=False)}\n\n"

        exact_file_memory = build_exact_file_memory(
            user_query=user_query,
            user_id=user_id,
            repository_ids=repository_ids,
            repository_by_id=repository_by_id,
        )
        if exact_file_memory:
            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="tool_call",
                    tool_name="精确文件召回",
                    input_payload={"query": user_query},
                    output_payload=exact_file_memory,
                )
            exact_updates = [
                {
                    "action_name": item.get("action_name", "精确文件召回"),
                    "prompt": item.get("提问", ""),
                }
                for item in exact_file_memory
            ]
            for update in send_agent_updates(exact_updates):
                yield update
            memory_global.extend(exact_file_memory)

        action_tool = agent_plan(user_query)
        print("action_tool")
        print(action_tool)

        actions = adjust_format(action_tool)
        plan_prompts = [action["prompt"] for action in actions]
        plan_prompts = maybe_add_file_role_prompts(user_query, plan_prompts)
        if plan_prompts and not actions:
            actions = [{"action_name": "代码索引检索", "prompt": prompt} for prompt in plan_prompts[:MAX_PLAN_PROMPTS]]
        elif plan_prompts:
            seen_prompts = {action["prompt"] for action in actions}
            for prompt in plan_prompts:
                if len(actions) >= MAX_PLAN_PROMPTS:
                    break
                if prompt in seen_prompts:
                    continue
                actions.append({"action_name": "代码索引检索", "prompt": prompt})
                seen_prompts.add(prompt)

        if not actions:
            actions = [{"action_name": "代码索引检索", "prompt": user_query}]

        if run_id:
            save_agent_step(
                run_id=run_id,
                step_type="plan",
                input_payload={"query": user_query, "allow_web_search": allow_web_search},
                output_payload={"raw_plan": action_tool, "actions": actions},
            )

        for update in send_agent_updates(actions):
            yield update

        memory_global.extend(process_actions(
            actions,
            user_id=user_id,
            repository_ids=repository_ids,
            repository_by_id=repository_by_id,
            repository_context=repository_context,
            run_id=run_id,
            allow_web_search=allow_web_search,
            stage="plan",
        ))

        if should_run_reflection(user_query, memory_global):
            action_reflect = reflection(user_query, build_final_evidence(memory_global, limit=4))
            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="reflection",
                    input_payload={"query": user_query, "evidence": build_final_evidence(memory_global, limit=4)},
                    output_payload=action_reflect,
                )
            if action_reflect:
                print("回顾内容，进行反思...")
                reflect_actions = adjust_format(action_reflect, max_prompts_per_action=MAX_REFLECTION_PROMPTS)
                existing_prompts = {item["提问"] for item in memory_global if isinstance(item, dict)}
                reflect_actions = [action for action in reflect_actions if action["prompt"] not in existing_prompts]
                if reflect_actions:
                    for update in send_agent_updates(reflect_actions):
                        yield update
                    reflection_memory = process_actions(
                        reflect_actions,
                        user_id=user_id,
                        repository_ids=repository_ids,
                        repository_by_id=repository_by_id,
                        repository_context=repository_context,
                        run_id=run_id,
                        allow_web_search=allow_web_search,
                        stage="reflection",
                    )
                    if build_final_evidence(reflection_memory, limit=2):
                        memory_global.extend(reflection_memory)

        final_evidence = build_final_evidence(memory_global, limit=FINAL_EVIDENCE_LIMIT)
        citations = build_citations_from_evidence(final_evidence)

        if formatted_repository_context:
            message = {"repository_context": formatted_repository_context}
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"

        if final_evidence:
            message = {
                "documents": final_evidence,
                "citations": citations,
            }
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
        elif citations:
            message = {"citations": citations}
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"

        final_prompt = build_final_prompt(user_query, repository_context, final_evidence, session_memory=session_memory)
        if run_id:
            save_agent_step(
                run_id=run_id,
                step_type="final_prompt",
                input_payload={"query": user_query},
                output_payload={"prompt": final_prompt, "evidence_count": len(final_evidence)},
            )
        print(final_prompt)
        print("-" * 130)

        completion = client.chat.completions.create(
            model="deepseek-r1",
            messages=[{"role": "user", "content": final_prompt}],
            stream=True,
        )

        print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")
        for chunk in completion:
            if chunk.choices[0].finish_reason == "stop":
                if run_id:
                    save_agent_step(
                        run_id=run_id,
                        step_type="final_answer",
                        input_payload={"query": user_query},
                        output_payload={"answer": model_answer, "think": think},
                    )
                    finish_agent_run(
                        run_id=run_id,
                        status="success",
                        final_answer=model_answer,
                        final_evidence=final_evidence,
                    )
                if persist_history and session_id:
                    write_chat_to_db(session_id, user_query, model_answer, final_evidence, [], think)
                    update_session_name(session_id, user_query, user_id)
                yield "event: end\ndata: [DONE]\n\n"
                break

            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None)
            reasoning_content = getattr(delta, "reasoning_content", None)
            if content:
                model_answer += content
                message = {
                    "role": "assistant",
                    "content": content,
                    "thinking": False,
                }
            elif reasoning_content:
                think += reasoning_content
                message = {
                    "role": "assistant",
                    "content": reasoning_content,
                    "thinking": True,
                }
            else:
                continue
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
    except Exception as e:
        if run_id:
            finish_agent_run(
                run_id=run_id,
                status="error",
                final_answer=model_answer,
                final_evidence=final_evidence,
                error=str(e),
            )
        error_message = {"role": "error", "content": str(e)}
        yield f"event: error\ndata: {json.dumps(error_message, ensure_ascii=False)}\n\n"
