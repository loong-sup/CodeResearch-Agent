import json
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any


OVERVIEW_KEYWORDS = (
    "有什么内容",
    "有哪些内容",
    "代码库里面有什么",
    "仓库里面有什么",
    "项目里面有什么",
    "整体结构",
    "目录结构",
    "项目结构",
    "代码结构",
    "整体内容",
    "主要内容",
    "模块组成",
    "有哪些模块",
    "包含什么",
    "项目概览",
    "仓库概览",
)


def is_repository_overview_query(query: str | None) -> bool:
    text = (query or "").strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in OVERVIEW_KEYWORDS)


def _parse_json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _top_level(path: str) -> str:
    pure_path = PurePosixPath(path)
    if len(pure_path.parts) > 1:
        return pure_path.parts[0]
    return "."


def _path_depth(path: str) -> int:
    return max(len(PurePosixPath(path).parts), 1)


def build_repository_overview_evidence(
    repositories: list[dict[str, Any]],
    *,
    max_files: int = 40,
    max_symbols: int = 30,
) -> list[dict[str, Any]]:
    evidence = []
    for repo in repositories or []:
        metadata = _parse_json(repo.get("metadata_json")) or {}
        structure = metadata.get("structure_index") or {}
        files = [item for item in structure.get("files", []) if isinstance(item, dict)]
        symbols = [item for item in structure.get("symbols", []) if isinstance(item, dict)]
        language_stats = _parse_json(repo.get("language_stats")) or {}

        dir_counter = Counter(_top_level(item.get("file_path", "")) for item in files if item.get("file_path"))
        kind_counter = Counter(item.get("kind") or "unknown" for item in files)
        language_counter = Counter()
        for item in files:
            language = item.get("language")
            if language:
                language_counter[language] += item.get("chunk_count") or 1
        if language_stats:
            language_counter.update(language_stats)

        by_directory = defaultdict(list)
        for item in sorted(files, key=lambda x: (_top_level(x.get("file_path", "")), _path_depth(x.get("file_path", "")), x.get("file_path", ""))):
            directory = _top_level(item.get("file_path", ""))
            if len(by_directory[directory]) < 8:
                by_directory[directory].append(
                    {
                        "file_path": item.get("file_path"),
                        "language": item.get("language"),
                        "kind": item.get("kind"),
                        "chunk_count": item.get("chunk_count"),
                    }
                )

        selected_files = []
        for directory, items in by_directory.items():
            selected_files.extend(items)
            if len(selected_files) >= max_files:
                break

        selected_symbols = [
            {
                "symbol": item.get("symbol"),
                "kind": item.get("kind"),
                "file_path": item.get("file_path"),
                "language": item.get("language"),
                "start_line": item.get("start_line"),
                "end_line": item.get("end_line"),
            }
            for item in symbols[:max_symbols]
        ]

        evidence.append(
            {
                "type": "repository_overview",
                "repository_id": repo.get("id") or repo.get("repository_id"),
                "repository_name": repo.get("name") or repo.get("repository_name"),
                "repository_type": repo.get("type") or repo.get("repository_type"),
                "status": repo.get("status"),
                "file_count": repo.get("file_count") or structure.get("file_count") or len(files),
                "indexed_chunks": repo.get("indexed_chunks"),
                "symbol_count": structure.get("symbol_count") or len(symbols),
                "top_directories": [
                    {"name": name, "file_count": count}
                    for name, count in dir_counter.most_common(12)
                ],
                "file_kinds": dict(kind_counter.most_common()),
                "languages": dict(language_counter.most_common(12)),
                "representative_files": selected_files[:max_files],
                "representative_symbols": selected_symbols,
            }
        )
    return evidence
