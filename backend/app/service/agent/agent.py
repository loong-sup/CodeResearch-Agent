import json
import re

from database.agent_operations import create_agent_run, finish_agent_run, save_agent_step
from database.knowledgebase_operations import get_session_memory
from service.agent.tools import tool_registry
from service.core.chat import build_memory_answer, update_session_name, write_chat_to_db
from service.core.retrieval import (
    retrieve_content,
    retrieve_exact_filename_content,
    retrieve_supporting_file_docs,
)
from service.repository_overview import build_repository_overview_evidence, is_repository_overview_query
from service.model_config import get_fast_generation_model, get_generation_client, get_generation_model
from utils.query_intent import QueryIntent, chitchat_answer, classify_query_intent_detail


MIN_PROMPT_LENGTH = 2
MAX_PLAN_PROMPTS = 3
MAX_REFLECTION_PROMPTS = 2
PER_PROMPT_RESULT_LIMIT = 4
FINAL_EVIDENCE_LIMIT = 8
FILE_ROLE_HINT_KEYWORDS = ("作用", "做什么", "入口", "启动", "用途", "职责")
SUPPORTING_DOC_HINT_TOKENS = ("readme", "architecture", "design", "spec", "guide", "reference", "manual")
EXPLICIT_WEB_HINT_TOKENS = ("网络", "网上", "联网", "搜索", "最新", "官方", "文档", "资料", "外部")
EXTERNAL_CONCEPT_HINT_TOKENS = (
    "mcp",
    "model context protocol",
    "rag",
    "fastapi",
    "streamingresponse",
    "sse",
    "openai",
    "dashscope",
    "elasticsearch",
    "serper",
    "docker",
    "react",
    "vite",
    "antd",
)
CODE_CONCEPT_QUERY_HINTS = {
    "mcp": [
        "mcp_server",
        "protocol_handler",
        "create_mcp_server",
        "register_tool",
        "tools/list",
        "tools/call",
        "run_stdio_server",
    ],
    "mcp server": [
        "src/mcp_server",
        "protocol_handler",
        "create_mcp_server",
        "server.py",
        "tools/list",
        "tools/call",
    ],
    "网络搜索": [
        "web_search",
        "serper_search",
        "process_search_results",
        "SERPER_API_KEY",
    ],
}
DOC_FILE_SUFFIXES = (".md", ".markdown", ".rst", ".txt")
CODE_FILE_SUFFIXES = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".php",
    ".sh",
    ".sql",
)


def extract_json_content(input_str: str | None):
    if not input_str:
        return None
    pattern = r"(\[[\s\S]*\])"
    match = re.search(pattern, input_str)
    return match.group(1) if match else None


def middle_json_model(prompt: str):
    client = get_generation_client(timeout=30)
    completion = client.chat.completions.create(
        model=get_generation_model(),
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
        if isinstance(search_results, dict) and search_results.get("message"):
            raise RuntimeError(str(search_results.get("message")))
        snippets, related_questions = process_search_results(search_results)
        return snippets
    except Exception as e:
        print(f"网络搜索失败: {e}")
        raise


def is_web_search_action(action: dict):
    return action.get("action_name") == "网络搜索"


def split_web_search_actions(actions: list[dict]):
    code_actions = []
    web_actions = []
    for action in actions:
        if is_web_search_action(action):
            web_actions.append(action)
        else:
            code_actions.append(action)
    return code_actions, web_actions


def extract_external_terms_from_evidence(evidence: list[dict], limit=6):
    terms = []
    seen = set()
    patterns = (
        r"^\s*import\s+([A-Za-z_][A-Za-z0-9_\.]*)",
        r"^\s*from\s+([A-Za-z_][A-Za-z0-9_\.]*)\s+import",
        r"^\s*(?:from|import)\s+['\"]([^'\"]+)['\"]",
        r"require\(['\"]([^'\"]+)['\"]\)",
    )
    for item in evidence:
        content = item.get("content_with_weight") or ""
        for pattern in patterns:
            for match in re.findall(pattern, content, flags=re.MULTILINE):
                root = match.split(".")[0].split("/")[0].strip()
                if not root or root.startswith("_") or root in seen:
                    continue
                if root in {"os", "sys", "re", "json", "time", "datetime", "typing", "pathlib", "uuid"}:
                    continue
                seen.add(root)
                terms.append(root)
                if len(terms) >= limit:
                    return terms
    return terms


def should_use_web_search(user_query, code_evidence, planned_web_actions, allow_web_search=True):
    if not allow_web_search:
        return False
    text = (user_query or "").lower()
    if any(token in text for token in EXPLICIT_WEB_HINT_TOKENS):
        return True
    if planned_web_actions:
        return True
    if any(token in text for token in EXTERNAL_CONCEPT_HINT_TOKENS):
        return True
    if count_high_quality_evidence([{"结果": code_evidence}]) < 2:
        return True
    return bool(extract_external_terms_from_evidence(code_evidence, limit=1))


def build_web_search_queries(user_query, code_evidence, planned_web_actions):
    queries = []
    seen = set()

    for action in planned_web_actions:
        prompt = (action.get("prompt") or "").strip()
        if prompt and prompt not in seen:
            seen.add(prompt)
            queries.append(prompt)

    terms = extract_external_terms_from_evidence(code_evidence)
    if terms:
        query = f"{user_query} {' '.join(terms[:4])} official docs"
    else:
        query = f"{user_query} official docs"
    if query not in seen:
        queries.append(query)

    return queries[:3]


def build_web_search_memory(user_query, code_evidence=None, planned_web_actions=None, allow_web_search=True):
    if not allow_web_search:
        return [], {"enabled": False, "queries": [], "error": "网络搜索开关未开启"}
    code_evidence = code_evidence or []
    planned_web_actions = planned_web_actions or []
    queries = build_web_search_queries(user_query, code_evidence, planned_web_actions)
    if not queries:
        return [], {"enabled": True, "queries": [], "error": "未生成有效的网络搜索查询"}

    all_snippets = []
    errors = []
    seen_urls = set()
    for query in queries:
        try:
            snippets = web_search_answer(query)
        except Exception as e:
            errors.append(f"{query}: {str(e)}")
            continue
        if not isinstance(snippets, list):
            continue
        for snippet in snippets:
            url = snippet.get("url") if isinstance(snippet, dict) else None
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            enriched = dict(snippet)
            enriched["query"] = query
            all_snippets.append(enriched)
            if len(all_snippets) >= 8:
                break
        if len(all_snippets) >= 8:
            break

    status = {
        "enabled": True,
        "queries": queries,
        "result_count": len(all_snippets),
        "error": "; ".join(errors[:2]) if errors and not all_snippets else "",
    }
    if not all_snippets:
        return [], status
    return [
        {
            "提问": " / ".join(queries),
            "结果": all_snippets,
            "action_name": "网络搜索",
            "source_stage": "web_search",
        }
    ], status


def build_web_context_for_prompt(web_evidence, web_status):
    if web_evidence:
        return web_evidence
    if web_status and web_status.get("enabled"):
        return [
            {
                "type": "web_search_status",
                "queries": web_status.get("queries", []),
                "error": web_status.get("error") or "网络搜索未返回可用结果",
            }
        ]
    return []


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


def is_doc_reference(item: dict):
    file_path = (item.get("file_path") or "").lower()
    return file_path.endswith(DOC_FILE_SUFFIXES) or any(
        token in file_path for token in SUPPORTING_DOC_HINT_TOKENS
    )


def is_code_reference(item: dict):
    file_path = (item.get("file_path") or "").lower()
    language = (item.get("language") or "").lower()
    return file_path.endswith(CODE_FILE_SUFFIXES) or language in {
        "python",
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "c",
        "cpp",
        "php",
        "shell",
        "sql",
    }


def parse_metadata_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    return {}


def resolve_candidate_file_paths(filename: str, repository_by_id: dict[str, dict] | None):
    if not filename or not repository_by_id:
        return []
    normalized = filename.strip().strip("`'\"").replace("\\", "/").lower()
    candidates = []
    seen = set()
    for repo in repository_by_id.values():
        metadata = parse_metadata_json(repo.get("metadata_json"))
        files = (metadata.get("structure_index") or {}).get("files", [])
        for file_item in files:
            file_path = str(file_item.get("file_path") or "").replace("\\", "/")
            if not file_path:
                continue
            lowered = file_path.lower()
            if lowered == normalized or lowered.endswith(f"/{normalized}") or lowered.split("/")[-1] == normalized:
                if file_path in seen:
                    continue
                seen.add(file_path)
                candidates.append(file_path)
    candidates.sort(key=lambda path: (path.count("/"), path))
    return candidates


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


def build_exact_file_memory(user_query, user_id, repository_ids, repository_by_id):
    memory = []
    for filename in extract_target_filenames(user_query)[:2]:
        candidate_paths = resolve_candidate_file_paths(filename, repository_by_id)
        search_paths = candidate_paths or [filename]
        exact_results = []
        seen_chunks = set()
        for path in search_paths[:4]:
            path_results = retrieve_exact_filename_content(
                user_id=user_id,
                filename=path,
                repository_ids=repository_ids,
                page_size=PER_PROMPT_RESULT_LIMIT * 2,
            )
            for result in path_results:
                key = result.get("chunk_id") or result.get("citation")
                if key in seen_chunks:
                    continue
                seen_chunks.add(key)
                exact_results.append(result)
        exact_results = enrich_references(exact_results, repository_by_id=repository_by_id)
        code_results = [item for item in exact_results if is_code_reference(item)]
        if code_results:
            exact_results = code_results
        exact_results = select_relevant_results(exact_results, limit=PER_PROMPT_RESULT_LIMIT)
        if exact_results:
            memory.append(
                {
                    "提问": f"{filename} 精确文件召回：{', '.join(search_paths[:4])}",
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
            supporting_docs = [item for item in supporting_docs if is_doc_reference(item)]
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


def build_concept_code_memory(user_query, user_id, repository_ids, repository_by_id):
    text = (user_query or "").lower()
    hints = []
    for key, values in CODE_CONCEPT_QUERY_HINTS.items():
        if key in text:
            hints.extend(values)
    if not hints:
        return []

    expanded_query = f"{user_query} {' '.join(dict.fromkeys(hints))}"
    results = retrieve_content(
        user_id=user_id,
        question=expanded_query,
        repository_ids=repository_ids,
        page_size=PER_PROMPT_RESULT_LIMIT * 4,
    )
    results = enrich_references(results, repository_by_id=repository_by_id)
    code_results = [item for item in results if is_code_reference(item)]
    selected = select_relevant_results(code_results or results, limit=PER_PROMPT_RESULT_LIMIT)
    if not selected:
        return []

    return [
        {
            "提问": f"代码概念召回：{expanded_query}",
            "结果": selected,
            "action_name": "代码索引检索",
            "source_stage": "concept_code",
        }
    ]


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
        haystack = " ".join(
            str(item.get(key, ""))
            for key in ("file_path", "symbol", "content_with_weight")
        ).lower()
        concept_bonus = 0
        if any(token in haystack for token in ("mcp_server", "protocol_handler", "create_mcp_server")):
            concept_bonus += 5
        if "src/" in haystack:
            concept_bonus += 1
        return (
            concept_bonus,
            4 if is_code_reference(item) else 0,
            3 if item.get("citation") else 0,
            2 if item.get("file_path") else 0,
            1 if item.get("symbol") else 0,
            -1 if is_doc_reference(item) else 0,
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
            if item.get("type") == "repository_overview":
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


def build_final_prompt(user_query, repository_context, code_evidence, web_evidence=None, session_memory=None):
    repo_context_text = json.dumps(format_repository_context(repository_context), ensure_ascii=False, indent=2)
    code_evidence_text = json.dumps(code_evidence, ensure_ascii=False, indent=2)
    web_evidence_text = json.dumps(web_evidence or [], ensure_ascii=False, indent=2)
    session_memory_text = json.dumps(session_memory or [], ensure_ascii=False, indent=2)
    return f"""
你是一个资深代码库问答助手。请基于当前代码库上下文和证据，直接回答用户问题。

回答要求：
1. 先直接回答用户问题，不要先复述“第几个参考内容”。
2. 只根据证据中的仓库路径、文件路径和片段做结论，不要编造。
3. 重要结论必须使用内联引用，格式为 [文件路径:起始行-结束行]。
4. 如果存在同名文件或多仓库上下文，先说明当前结论对应的仓库/路径。
5. 如果证据不足，明确说明缺少哪些信息。
6. 如果证据里包含 .py/.js/.ts 等代码文件，优先解释代码实现，不要用 README 或项目文档替代代码证据。
7. 网络证据只能用于解释外部概念、第三方库、协议标准、官方背景或验证判断；不允许用网络证据替代本项目代码证据。
8. 如果代码证据和网络证据不一致，以代码证据为准，并说明“本项目实际实现是……”。
9. 回答中要清楚区分“本项目代码实现”和“外部资料补充”。代码实现结论必须引用代码路径；外部资料可以说明来源标题或 URL。
10. 如果网络证据非空，必须在回答中加入“外部资料补充”小节，说明网络资料补充了什么；如果网络搜索失败或无结果，也要说明“本次网络搜索未获得可用结果”，不要假装已经联网验证。
11. 对“某个文件实现了哪些功能/怎么运行/调用链是什么”这类问题，按这个结构回答：
   - 文件定位：说明文件路径、它在项目中的角色。
   - 入口与主流程：按执行顺序解释 import、初始化、主要函数/类、条件分支、外部调用。
   - 关键函数/类：列出名称、职责、输入输出或副作用。
   - 数据流/控制流：说明数据从哪里来、经过哪些处理、最后到哪里。
   - 可继续追问：给出 2-3 个基于真实代码符号的追问方向。
12. 可以引用很短的代码标识符或函数名，但不要大段复述代码。
13. 语言保持工程分析风格，不要使用销售或营销语言。
14. 如果代码证据包含 type=repository_overview，把它当作仓库地图来总结：先说整体组成，再说主要目录/语言/代表文件/可继续追问的问题。仓库地图本身不需要行号引用；涉及具体实现细节时才使用文件行号引用。

当前代码库上下文：
{repo_context_text}

最近会话记忆：
{session_memory_text}

代码库证据：
{code_evidence_text}

网络证据：
{web_evidence_text}

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
    def log_stage(stage: str):
        print(f"[deep_research] {stage}: {user_query}")

    try:
        log_stage("start")
        intent_result = classify_query_intent_detail(user_query)
        query_intent = intent_result.intent
        print(
            "[deep_research] intent: "
            f"intent={intent_result.intent}, "
            f"confidence={intent_result.confidence:.2f}, "
            f"signals={intent_result.signals}, "
            f"secondary={intent_result.secondary}"
        )
        if query_intent == QueryIntent.CHITCHAT:
            log_stage("chitchat")
            model_answer = chitchat_answer(user_query)
            message = {
                "role": "assistant",
                "content": model_answer,
                "thinking": False,
                "answer_scope": "chitchat",
            }
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: [DONE]\n\n"
            if persist_history and session_id:
                try:
                    write_chat_to_db(session_id, user_query, model_answer, [], [], "")
                    update_session_name(session_id, user_query, user_id)
                except Exception as persist_error:
                    print(f"failed to persist chitchat answer: {persist_error}")
            return

        if query_intent == QueryIntent.MEMORY:
            log_stage("memory")
            session_memory = get_session_memory(session_id, limit=20) if session_id else []
            model_answer = build_memory_answer(user_query, session_memory)
            message = {
                "role": "assistant",
                "content": model_answer,
                "thinking": False,
                "answer_scope": "memory",
            }
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: [DONE]\n\n"
            if persist_history and session_id:
                try:
                    write_chat_to_db(session_id, user_query, model_answer, [], [], "")
                    update_session_name(session_id, user_query, user_id)
                except Exception as persist_error:
                    print(f"failed to persist memory answer: {persist_error}")
            return

        if query_intent == QueryIntent.GENERAL:
            log_stage("general")
            model_answer = (
                "这个问题看起来不属于当前代码库的实现、调用链或配置范围。"
                "我可以回答通用问题；如果你希望我基于当前仓库分析，请补充具体文件、接口、函数、报错或模块名称。"
            )
            message = {
                "role": "assistant",
                "content": model_answer,
                "thinking": False,
                "answer_scope": "general",
            }
            yield f"event: message\ndata: {json.dumps(message, ensure_ascii=False)}\n\n"
            yield "event: end\ndata: [DONE]\n\n"
            if persist_history and session_id:
                try:
                    write_chat_to_db(session_id, user_query, model_answer, [], [], "")
                    update_session_name(session_id, user_query, user_id)
                except Exception as persist_error:
                    print(f"failed to persist general answer: {persist_error}")
            return

        client = get_generation_client(timeout=60)
        repository_context = repository_context or []
        repository_by_id = {
            item.get("id") or item.get("repository_id"): item
            for item in repository_context
            if isinstance(item, dict)
        }
        formatted_repository_context = format_repository_context(repository_context)
        session_memory = get_session_memory(session_id) if session_id else []
        memory_global = []
        planned_web_actions = []

        if is_repository_overview_query(user_query):
            overview_evidence = build_repository_overview_evidence(repository_context)
            if overview_evidence:
                memory_global.append(
                    {
                        "提问": "仓库结构概览",
                        "结果": overview_evidence,
                        "action_name": "代码结构检索",
                        "source_stage": "overview",
                    }
                )
                if run_id:
                    save_agent_step(
                        run_id=run_id,
                        step_type="tool_call",
                        tool_name="仓库结构概览",
                        input_payload={"query": user_query},
                        output_payload=overview_evidence,
                    )

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

        concept_code_memory = build_concept_code_memory(
            user_query=user_query,
            user_id=user_id,
            repository_ids=repository_ids,
            repository_by_id=repository_by_id,
        )
        if concept_code_memory:
            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="tool_call",
                    tool_name="代码概念召回",
                    input_payload={"query": user_query},
                    output_payload=concept_code_memory,
                )
            for update in send_agent_updates(
                [
                    {
                        "action_name": item.get("action_name", "代码索引检索"),
                        "prompt": item.get("提问", ""),
                    }
                    for item in concept_code_memory
                ]
            ):
                yield update
            memory_global.extend(concept_code_memory)

        log_stage("plan_start")
        action_tool = agent_plan(user_query)
        log_stage("plan_done")
        print("action_tool")
        print(action_tool)

        actions = adjust_format(action_tool)
        actions, web_actions = split_web_search_actions(actions)
        planned_web_actions.extend(web_actions)
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

        log_stage("retrieval_start")
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
        log_stage("retrieval_done")

        if should_run_reflection(user_query, memory_global):
            log_stage("reflection_start")
            action_reflect = reflection(user_query, build_final_evidence(memory_global, limit=4))
            log_stage("reflection_done")
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
                reflect_actions, reflect_web_actions = split_web_search_actions(reflect_actions)
                planned_web_actions.extend(reflect_web_actions)
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

        code_evidence = build_final_evidence(memory_global, limit=FINAL_EVIDENCE_LIMIT)
        web_evidence = []
        web_status = {}
        if should_use_web_search(
            user_query,
            code_evidence,
            planned_web_actions,
            allow_web_search=allow_web_search,
        ):
            log_stage("web_search_start")
            web_search_memory, web_status = build_web_search_memory(
                user_query,
                code_evidence=code_evidence,
                planned_web_actions=planned_web_actions,
                allow_web_search=allow_web_search,
            )
            log_stage("web_search_done")
            if web_search_memory:
                web_evidence = web_search_memory[0].get("结果", [])
                yield f"event: message\ndata: {json.dumps({'web_search': web_evidence}, ensure_ascii=False)}\n\n"
            else:
                yield f"event: message\ndata: {json.dumps({'web_search_status': web_status}, ensure_ascii=False)}\n\n"
            if run_id:
                save_agent_step(
                    run_id=run_id,
                    step_type="tool_call",
                    tool_name="网络搜索",
                    input_payload={"query": user_query, "planned_actions": planned_web_actions},
                    output_payload={"status": web_status, "results": web_evidence},
                    error=web_status.get("error") or None,
                )

        final_evidence = code_evidence
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

        final_prompt = build_final_prompt(
            user_query,
            repository_context,
            code_evidence,
            web_evidence=build_web_context_for_prompt(web_evidence, web_status),
            session_memory=session_memory,
        )
        if run_id:
            save_agent_step(
                run_id=run_id,
                step_type="final_prompt",
                input_payload={"query": user_query},
                output_payload={
                    "prompt": final_prompt,
                    "code_evidence_count": len(code_evidence),
                    "web_evidence_count": len(web_evidence),
                },
            )
        print(final_prompt)
        print("-" * 130)

        log_stage("final_model_start")
        completion = client.chat.completions.create(
            model=get_fast_generation_model(),
            messages=[{"role": "user", "content": final_prompt}],
            stream=True,
        )

        print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")
        completed = False
        for chunk in completion:
            if chunk.choices[0].finish_reason == "stop":
                completed = True
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
                yield "event: end\ndata: [DONE]\n\n"
                if persist_history and session_id:
                    try:
                        write_chat_to_db(session_id, user_query, model_answer, final_evidence, [], think)
                        update_session_name(session_id, user_query, user_id)
                    except Exception as persist_error:
                        print(f"failed to persist deep research answer: {persist_error}")
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
        if not completed:
            yield "event: end\ndata: [DONE]\n\n"
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
        yield "event: end\ndata: [DONE]\n\n"
