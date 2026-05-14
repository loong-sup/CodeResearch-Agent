import datetime
import os
from dataclasses import dataclass

import xxhash

from service.core.rag.app.code_repo import chunk as code_repo_chunk, supports_path as code_repo_supports_path
from service.core.rag.app.manual import chunk as manual_chunk
from service.core.rag.utils.es_conn import ESConnection
from service.core.rag.nlp.model import generate_embedding

def dummy(prog=None, msg=""):
    pass


def _should_use_code_repo_parser(file_path):
    return code_repo_supports_path(file_path)


def parse(file_path):
    parser = code_repo_chunk if _should_use_code_repo_parser(file_path) else manual_chunk
    result = parser(file_path, callback=dummy)
    return result


@dataclass
class IndexingResult:
    indexed_chunks: int
    file_count: int
    language_stats: dict[str, int]
    doc_ids: list[str]
    structure_index: dict


def _build_chunk_id(item, repository_id, file_name):
    logical_doc_name = item.get("file_path_kwd", file_name)
    start_line = item.get("start_line_int", 1)
    end_line = item.get("end_line_int", 1)
    chunk_kind = item.get("chunk_kind_kwd", "")
    symbol = item.get("symbol_kwd", "")
    content = item.get("content_with_weight", "")
    raw_id = "||".join(
        [
            repository_id,
            logical_doc_name,
            str(start_line),
            str(end_line),
            chunk_kind,
            symbol,
            content,
        ]
    )
    return xxhash.xxh64(raw_id.encode("utf-8")).hexdigest()


def _build_structure_index(documents, max_files=300, max_symbols=500):
    files_by_path = {}
    symbols = []
    for item in documents:
        file_path = item.get("file_path_kwd", item.get("docnm_kwd", ""))
        if not file_path:
            continue
        language = item.get("language_kwd", "")
        chunk_kind = item.get("chunk_kind_kwd", "")
        files_by_path.setdefault(
            file_path,
            {
                "file_path": file_path,
                "language": language,
                "kind": "doc" if language in {"markdown", "rst", "text"} else "code",
                "chunk_count": 0,
            },
        )
        files_by_path[file_path]["chunk_count"] += 1

        symbol = item.get("symbol_kwd", "")
        if symbol and len(symbols) < max_symbols:
            symbols.append(
                {
                    "symbol": symbol,
                    "kind": chunk_kind or "symbol",
                    "file_path": file_path,
                    "language": language,
                    "start_line": item.get("start_line_int", 1),
                    "end_line": item.get("end_line_int", 1),
                }
            )

    files = sorted(files_by_path.values(), key=lambda item: item["file_path"])
    return {
        "files": files[:max_files],
        "symbols": symbols,
        "file_count": len(files_by_path),
        "symbol_count": len(symbols),
    }


def process_item(item, file_name, repository_id, user_id=None):
    """
    处理单条数据
    """
    try:
        # 用仓库+文件位置生成稳定 chunk_id，避免相同内容片段互相覆盖。
        chunck_id = _build_chunk_id(item, repository_id, file_name)

        # 构建数据字典
        d = {
            "id": chunck_id, #ES文档id
            "content_ltks": item["content_ltks"], #chunk正文的标准分词结果
            "content_with_weight": item["content_with_weight"], #主要内容文本，也是后面喂给 LLM 的核心字段
            "content_sm_ltks": item["content_sm_ltks"], #在 content_ltks 基础上再细粒度拆分一次的结果
            "title_sm_tks": item.get("title_sm_tks", ""),
            "file_path_tks": item.get("file_path_tks", ""),
            "file_path_sm_tks": item.get("file_path_sm_tks", ""),
            "symbol_tks": item.get("symbol_tks", ""),
            "symbol_sm_tks": item.get("symbol_sm_tks", ""),
            "chunk_kind_tks": item.get("chunk_kind_tks", ""),
            "important_kwd": [],
            "important_tks": [],
            "question_kwd": [],
            "question_tks": [],
            "create_time": str(datetime.datetime.now()).replace("T", " ")[:19], #可读时间
            "create_timestamp_flt": datetime.datetime.now().timestamp(), #排序/过滤用的浮点时间戳
            "available_int": item.get("available_int", 1),
        }
        #补充文档归属信息
        d["kb_id"] = repository_id
        d["repository_id"] = repository_id
        d["user_id"] = user_id or ""
        d["docnm_kwd"] = item["docnm_kwd"]
        d["title_tks"] = item["title_tks"]
        d["file_path_kwd"] = item.get("file_path_kwd", item["docnm_kwd"])
        d["language_kwd"] = item.get("language_kwd", "")
        d["chunk_kind_kwd"] = item.get("chunk_kind_kwd", "")
        d["symbol_kwd"] = item.get("symbol_kwd", "")
        d["start_line_int"] = item.get("start_line_int", 1)
        d["end_line_int"] = item.get("end_line_int", 1)
        logical_doc_name = item.get("file_path_kwd", file_name)
        d["doc_id"] = xxhash.xxh64(logical_doc_name.encode("utf-8")).hexdigest()
        d["docnm"] = file_name
        
        v = generate_embedding(item["content_with_weight"])
        if not v:
            raise ValueError("embedding generation failed")
        
        # 将嵌入向量存储到字典中
        d["q_%d_vec" % len(v)] = v

        return d

    except Exception as e:
        print(f"process_item error: {e}")
        return None

def execute_insert_process(file_path, file_name, repository_id, user_id, index_name=None):
    """
    执行文档处理和插入 Elasticsearch 的函数
    :param file_path: 文件路径
    :param repository_id: 知识库实例 ID
    :param documents: 要插入的文档列表
    """
    documents = parse(file_path)
    structure_index = _build_structure_index(documents)
    language_stats = {}
    doc_ids = set()
    result = []
    for item in documents:
        language = item.get("language_kwd")
        if language:
            language_stats[language] = language_stats.get(language, 0) + 1
        doc_key = item.get("file_path_kwd", item.get("docnm_kwd"))
        if doc_key:
            doc_ids.add(xxhash.xxh64(doc_key.encode("utf-8")).hexdigest())
        processed_item = process_item(item, file_name, repository_id, user_id=user_id)
        if processed_item is not None:
            result.append(processed_item)

    if not result:
        raise ValueError("no supported content could be indexed")
    
    # 创建 ESConnection 的实例
    es_connection = ESConnection()
    # 通过实例调用 insert 方法，并在写入失败时中断整个索引流程
    insert_errors = es_connection.insert(documents=result, indexName=index_name or user_id)
    if insert_errors:
        preview = "; ".join(insert_errors[:3])
        raise RuntimeError(f"failed to insert chunks into ES: {preview}")
    return IndexingResult(
        indexed_chunks=len(result),
        file_count=max(len(doc_ids), 1),
        language_stats=language_stats,
        doc_ids=sorted(doc_ids),
        structure_index=structure_index,
    )


import json

if __name__ == "__main__":
    file_path = "/mnt/d/wsl/project/gsk-poc/storage/file/【兴证电子】世运电路2023中报点评.pdf"
    session_id = "40e2743ccffa4207"
    output_file = "/mnt/d/wsl/project/gsk-poc/storage/output/result.json"

    # 如果本地文件不存在，则解析文件并保存结果
    if not os.path.exists(output_file):
        documents = parse(file_path)
        
        # 处理每个文档
        result = []
        for item in documents:
            processed_item = process_item(item, file_path, session_id)
            result.append(processed_item)

        # 将结果保存到本地文件
        os.makedirs(os.path.dirname(output_file), exist_ok=True)  # 确保目录存在
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=4)
        print(f"结果已保存到本地文件: {output_file}")
    else:
        # 如果本地文件存在，则从文件中读取结果
        with open(output_file, "r", encoding="utf-8") as f:
            result = json.load(f)
        print(f"从本地文件加载结果: {output_file}")

    # # 打印结果以便检查
    # print("加载的数据内容：")
    # print(json.dumps(result, ensure_ascii=False, indent=4))

    # 创建 ESConnection 的实例
    es_connection = ESConnection()
    # 通过实例调用 insert 方法
    es_connection.insert(documents=result, indexName="世运电路2023中报点评")
