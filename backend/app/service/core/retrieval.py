"""
只是一个适配层，调用底层检索器 dealer.retrieval，从底层返回的大结果里
抽取前端/上层真正需要的字段，并显式支持 repository_id 过滤。
"""
from pathlib import Path

from service.core.rag.nlp.search_v2 import Dealer
from service.core.rag.utils.es_conn import ESConnection
# 创建 ElasticsearchConnection 实例
es_connection = ESConnection()

# 创建 Dealer 实例
dealer = Dealer(dataStore=es_connection)


def _serialize_chunk(chunk: dict, index: int):
    content_with_weight = chunk.get('content_with_weight', 'N/A')
    doc_id = chunk.get('doc_id', 'N/A')
    docnm = chunk.get('docnm_kwd', 'N/A')
    docnm = docnm.split("/")[-1]
    file_path = chunk.get('file_path_kwd', chunk.get('docnm_kwd', 'N/A'))
    start_line = chunk.get('start_line_int', 1)
    end_line = chunk.get('end_line_int', 1)
    language = chunk.get('language_kwd', '')
    symbol = chunk.get('symbol_kwd', '')
    chunk_kind = chunk.get('chunk_kind_kwd', '')
    citation = f"{file_path}:{start_line}-{end_line}"

    return {
        "id": index,
        "chunk_id": chunk.get('chunk_id', chunk.get('id')),
        "document_id": doc_id,
        "document_name": docnm,
        'content_with_weight': content_with_weight,
        "repository_id": chunk.get("repository_id", chunk.get("kb_id")),
        "user_id": chunk.get("user_id"),
        "file_path": file_path,
        "start_line": start_line,
        "end_line": end_line,
        "language": language,
        "symbol": symbol,
        "chunk_kind": chunk_kind,
        "citation": citation,
        "citation_display": f"[{citation}]",
        "citation_key": citation,
    }


def _extract_search_result(search_result):
    extracted_data = []
    for i, chunk_id in enumerate(search_result.ids, start=1):
        chunk = dict(search_result.field.get(chunk_id, {}))
        chunk["id"] = chunk_id
        extracted_data.append(_serialize_chunk(chunk, i))
    return extracted_data


def retrieve_exact_filename_content(
    user_id: str,
    filename: str,
    repository_ids: list[str] | None = None,
    page_size: int = 12,
):
    req = {
        "size": page_size,
        "page": 1,
        "available_int": 1,
        "sort": True,
        "file_paths": [filename],
        "doc_names": [filename],
    }
    search_result = dealer.search(
        req=req,
        idx_names=user_id,
        kb_ids=repository_ids,
        emb_mdl=None,
        highlight=False,
    )
    extracted = _extract_search_result(search_result)
    extracted.sort(key=lambda item: (item.get("file_path", ""), item.get("start_line", 1), item.get("end_line", 1)))
    return extracted


def retrieve_supporting_file_docs(
    user_id: str,
    filename: str,
    question: str,
    repository_ids: list[str] | None = None,
    page_size: int = 8,
):
    query = f"{filename} {question} README 架构 设计 说明 文档"
    results = retrieve_content(
        user_id=user_id,
        question=query,
        repository_ids=repository_ids,
        page_size=page_size,
    )
    supporting = []
    seen = set()
    for item in results:
        file_path = (item.get("file_path") or "").lower()
        suffix = Path(file_path).suffix.lower()
        if suffix not in {".md", ".markdown", ".rst", ".txt"} and not any(
            token in file_path for token in ("readme", "architecture", "design", "spec", "guide", "reference", "manual")
        ):
            continue
        citation = item.get("citation") or item.get("chunk_id")
        if citation in seen:
            continue
        seen.add(citation)
        supporting.append(item)
    return supporting


def retrieve_content(
    user_id: str,
    question: str,
    repository_ids: list[str] | None = None,
    page_size: int = 5,
):

    # 执行搜索
    results = dealer.retrieval(
        question=question,
        embd_mdl=None,
        tenant_ids=user_id,
        kb_ids=repository_ids,
        vector_similarity_weight=0.6,
        page=1,
        page_size=page_size,
    )

    # 提取 chunks 中的信息
    extracted_data = []
    for i, chunk in enumerate(results['chunks'], start=1):
        extracted_data.append(_serialize_chunk(chunk, i))
    return extracted_data


if __name__ == '__main__':
    res = retrieve_content(question="世运电路成长性如何", user_id="test01")
    print(res)
    
    # 将提取的数据写入到文件
    # with open("output.txt", "w", encoding="utf-8") as file:
    #     for data in extracted_data:
    #         file.write(f"content_with_weight: {data['content_with_weight']}\n")
    #         file.write(f"similarity: {data['similarity']}\n")
    #         file.write(f"vector_similarity: {data['vector_similarity']}\n")
    #         file.write(f"term_similarity: {data['term_similarity']}\n")
    #         file.write("\n")
    
    # print("结果已写入到 output.txt 文件中")