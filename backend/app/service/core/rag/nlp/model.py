from openai import OpenAI
from llama_index.core.data_structs import Node
from llama_index.core.schema import NodeWithScore
from llama_index.postprocessor.dashscope_rerank import DashScopeRerank
import numpy as np

import os
from dotenv import load_dotenv
load_dotenv()


def rerank_similarity(query, texts):
    api_key = os.getenv("DASHSCOPE_API_KEY")
    # 创建节点列表
    nodes = [NodeWithScore(node=Node(text=text), score=1.0) for text in texts]

    # 初始化 DashScopeRerank
    dashscope_rerank = DashScopeRerank(top_n=len(texts), api_key=api_key) 

    # 执行重排序
    results = dashscope_rerank.postprocess_nodes(nodes, query_str=query)

    # 提取分数
    scores = [res.score for res in results]
    scores = np.array(scores)

    # 返回分数和一个占位符
    return scores, None

# 知识库和web搜索重拍序
def rerank_results(query, texts):
    api_key = os.getenv("DASHSCOPE_API_KEY")
    
    # 创建节点列表
    nodes = [NodeWithScore(node=Node(text=text), score=1.0) for text in texts]

    # 初始化 DashScopeRerank，设置 top_n 为 5，表示返回 top 5 的结果
    dashscope_rerank = DashScopeRerank(top_n=5, api_key=api_key)

    # 执行重排序
    results = dashscope_rerank.postprocess_nodes(nodes, query_str=query)

    # 提取分数和对应的文本
    top_scores = [res.score for res in results]
    top_texts = [res.node.text for res in results]

    # 将分数转换为 NumPy 数组
    top_scores = np.array(top_scores)

    # 返回 top 5 的分数和对应的文本
    return top_scores, top_texts


def generate_embedding(text: str, api_key: str = None, base_url: str = None, model_name: str = "text-embedding-v3", dimensions: int = 1024, encoding_format: str = "float"):
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"    

    # 初始化 OpenAI 客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    # 调用 OpenAI 的嵌入接口
    try:
        completion = client.embeddings.create(
            model=model_name,
            input=text,
            dimensions=dimensions,
            encoding_format=encoding_format
        )
        embedding = completion.data[0].embedding
        return embedding
    except Exception as e:
        print(f"OpenAI API 请求失败: {e}")
        return None

