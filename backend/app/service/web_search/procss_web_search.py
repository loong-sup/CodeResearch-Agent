from service.web_search.web_search import serper_search, process_search_results
import chromadb
from typing import List
from service.core.rag.nlp.model import generate_embedding

# 初始化 ChromaDB 客户端（内存模式）
chroma_client = chromadb.Client()

# 自定义嵌入函数类（适配 ChromaDB）
class CustomEmbeddingFunction:
    def __init__(self):
        pass

    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        for text in input:
            embedding = generate_embedding(text)
            if embedding is not None:
                # 确保返回的是列表格式
                if isinstance(embedding, list):
                    embeddings.append(embedding)
                else:
                    # 如果是其他格式（如numpy数组），转换为列表
                    embeddings.append(embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding))
            else:
                # 如果生成失败，返回一个全零向量
                embeddings.append([0.0] * 1024)  # 假设维度为 1024
        return embeddings
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        return self.__call__(texts)
    
    def embed_query(self, input: str) -> List[float]:
        """嵌入单个查询文本"""
        embedding = generate_embedding(input)
        if embedding is not None:
            # 确保返回的是列表格式
            if isinstance(embedding, list):
                return embedding
            else:
                # 如果是其他格式（如numpy数组），转换为列表
                return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        else:
            # 如果生成失败，返回一个全零向量
            return [0.0] * 1024  # 假设维度为 1024

# 初始化 ChromaDB 客户端（内存模式）
chroma_client = chromadb.Client()

def store_and_query_snippets(question: str, top_k: int = 5):
    """
    将 snippets 存储到 ChromaDB，并与 question 计算相似度，返回前 top_k 条最相关的结果。

    参数:
        snippets (List[Dict]): 包含 title, url, content 的 snippets 列表
        question (str): 查询问题
        top_k (int): 返回的最相关结果数量，默认为 5

    返回:
        List[Dict]: 最相关的前 top_k 条结果，包含 title, url, content
    """
    # 创建自定义嵌入函数实例
    custom_embedding_fn = CustomEmbeddingFunction()

    search_results = serper_search(question)
    snippets, related_questions = process_search_results(search_results)

    # 创建一个临时集合（collection），使用自定义嵌入函数
    # 先检查集合是否已存在，如果存在则删除
    try:
        existing_collection = chroma_client.get_collection(name="temp_snippets")
        chroma_client.delete_collection(name="temp_snippets")
    except:
        # 集合不存在，继续创建
        pass
    
    collection = chroma_client.create_collection(name="temp_snippets", embedding_function=custom_embedding_fn)

    # 将 snippets 存储到 ChromaDB
    for idx, snippet in enumerate(snippets):
        collection.add(
            documents=[snippet["content"]],  # 存储 content 作为文档
            metadatas=[{"title": snippet["title"], "url": snippet["url"]}],  # 存储元数据
            ids=[str(idx)]  # 唯一 ID
        )

    # 使用 question 查询最相关的结果
    results = collection.query(
        query_texts=[question],  # 查询问题
        n_results=top_k  # 返回前 top_k 条结果
    )

    # 解析查询结果
    top_snippets = []
    for i in range(len(results["ids"][0])):
        snippet_id = results["ids"][0][i]
        content = results["documents"][0][i]
        metadata = results["metadatas"][0][i]
        top_snippets.append({
            "title": metadata["title"],
            "url": metadata["url"],
            "content": content
        })

    # 删除临时集合，释放内存
    chroma_client.delete_collection(name="temp_snippets")

    return top_snippets, related_questions

