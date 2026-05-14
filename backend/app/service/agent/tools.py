import json
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from service.core.retrieval import (
    retrieve_content,
    retrieve_exact_filename_content,
    retrieve_supporting_file_docs,
)

DOC_SUFFIXES = (".md", ".markdown", ".rst", ".txt")


@dataclass
class ToolResult:
    tool_name: str
    success: bool
    observations: Any
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_memory_result(self):
        return self.observations if self.success else f"{self.tool_name}执行失败: {self.error}"

    def to_log_payload(self):
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "observations": self.observations,
            "error": self.error,
            "metadata": self.metadata,
        }


class AgentTool:
    name: str = ""
    description: str = ""

    def run(
        self,
        *,
        query: str,
        user_id: str,
        repository_ids: Optional[list[str]] = None,
        repository_by_id: Optional[dict[str, dict]] = None,
        repository_context: Optional[list[dict]] = None,
        allow_web_search: bool = True,
        limit: int = 4,
    ) -> ToolResult:
        raise NotImplementedError


def _enrich_references(references: list[dict], repository_by_id: Optional[dict[str, dict]] = None):
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


def _is_doc_reference(item: dict):
    file_path = (item.get("file_path") or "").lower()
    return file_path.endswith(DOC_SUFFIXES) or any(
        token in file_path for token in ("readme", "architecture", "design", "spec", "guide", "manual")
    )


def _prefer_code_references(references: list[dict], limit: int):
    code_refs = [item for item in references if isinstance(item, dict) and not _is_doc_reference(item)]
    return (code_refs or references)[:limit]


class CodeIndexSearchTool(AgentTool):
    name = "代码索引检索"
    description = "从代码和配置 chunk 索引中检索实现、调用、配置、符号相关证据。"

    def run(self, *, query, user_id, repository_ids=None, repository_by_id=None, limit=4, **kwargs):
        result = retrieve_content(user_id, query, repository_ids=repository_ids, page_size=limit * 2)
        result = _prefer_code_references(result, limit)
        return ToolResult(
            tool_name=self.name,
            success=True,
            observations=_enrich_references(result, repository_by_id=repository_by_id),
        )


class ProjectDocSearchTool(AgentTool):
    name = "项目文档检索"
    description = "优先检索 README、设计说明、指南和项目文档。"

    def run(self, *, query, user_id, repository_ids=None, repository_by_id=None, limit=4, **kwargs):
        result = retrieve_content(user_id, f"{query} README architecture design guide", repository_ids=repository_ids, page_size=limit * 2)
        docs = []
        for item in result:
            file_path = (item.get("file_path") or "").lower()
            if file_path.endswith((".md", ".markdown", ".rst", ".txt")) or any(
                token in file_path for token in ("readme", "architecture", "design", "spec", "guide", "manual")
            ):
                docs.append(item)
        if not docs:
            docs = result[:limit]
        return ToolResult(
            tool_name=self.name,
            success=True,
            observations=_enrich_references(docs[:limit], repository_by_id=repository_by_id),
        )


class ExactFileRecallTool(AgentTool):
    name = "精确文件召回"
    description = "当问题中出现明确文件名时，按文件名直接召回对应内容。"

    def run(self, *, query, user_id, repository_ids=None, repository_by_id=None, limit=4, **kwargs):
        result = retrieve_exact_filename_content(
            user_id=user_id,
            filename=query,
            repository_ids=repository_ids,
            page_size=limit,
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            observations=_enrich_references(result, repository_by_id=repository_by_id),
        )


class SupportingFileDocsTool(AgentTool):
    name = "辅助文档召回"
    description = "围绕指定文件名召回 README/文档中的解释信息。"

    def run(self, *, query, user_id, repository_ids=None, repository_by_id=None, limit=4, **kwargs):
        filename, _, question = query.partition(" ")
        result = retrieve_supporting_file_docs(
            user_id=user_id,
            filename=filename,
            question=question or query,
            repository_ids=repository_ids,
            page_size=limit,
        )
        return ToolResult(
            tool_name=self.name,
            success=True,
            observations=_enrich_references(result, repository_by_id=repository_by_id),
        )


class WebSearchTool(AgentTool):
    name = "网络搜索"
    description = "仓库证据不足且允许联网时，用 Serper 查询外部资料。"

    def run(self, *, query, allow_web_search=True, **kwargs):
        if not allow_web_search:
            return ToolResult(
                tool_name=self.name,
                success=False,
                observations=[],
                error="网络搜索已被当前请求关闭",
            )
        try:
            from service.web_search.web_search import process_search_results, serper_search

            search_results = serper_search(query)
            snippets, _ = process_search_results(search_results)
            return ToolResult(tool_name=self.name, success=True, observations=snippets)
        except Exception as e:
            return ToolResult(tool_name=self.name, success=False, observations=[], error=str(e))


class CodeStructureSearchTool(AgentTool):
    name = "代码结构检索"
    description = "从仓库元数据中的文件树和符号摘要里检索结构线索。"

    def run(self, *, query, repository_context=None, limit=8, **kwargs):
        tokens = [token.lower() for token in query.replace("/", " ").replace(".", " ").split() if token.strip()]
        observations = []
        for repo in repository_context or []:
            metadata = repo.get("metadata_json")
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except json.JSONDecodeError:
                    metadata = {}
            structure = (metadata or {}).get("structure_index") or {}
            for file_item in structure.get("files", []):
                haystack = " ".join(
                    str(file_item.get(key, ""))
                    for key in ("file_path", "language", "kind")
                ).lower()
                if not tokens or any(token in haystack for token in tokens):
                    observations.append({
                        "repository_id": repo.get("id"),
                        "repository_name": repo.get("name"),
                        "type": "file",
                        **file_item,
                    })
            for symbol in structure.get("symbols", []):
                haystack = " ".join(
                    str(symbol.get(key, ""))
                    for key in ("symbol", "kind", "file_path", "language")
                ).lower()
                if not tokens or any(token in haystack for token in tokens):
                    observations.append({
                        "repository_id": repo.get("id"),
                        "repository_name": repo.get("name"),
                        "type": "symbol",
                        **symbol,
                    })
            if len(observations) >= limit:
                break
        return ToolResult(tool_name=self.name, success=True, observations=observations[:limit])


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[AgentTool]:
        return self._tools.get(name)

    def run(self, name: str, **kwargs) -> ToolResult:
        tool = self.get(name)
        if tool is None:
            return ToolResult(tool_name=name, success=False, observations=[], error=f"未知工具: {name}")
        return tool.run(**kwargs)


tool_registry = ToolRegistry()
for _tool in (
    CodeIndexSearchTool(),
    ProjectDocSearchTool(),
    ExactFileRecallTool(),
    SupportingFileDocsTool(),
    WebSearchTool(),
    CodeStructureSearchTool(),
):
    tool_registry.register(_tool)
