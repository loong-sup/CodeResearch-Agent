# Agent 评估方案

这个目录提供一套贴合当前项目实现的 `agent` 评测方案，重点覆盖 `deep_research` 和 `ai_search` 两条链路。

## 为什么这样设计

当前项目里的 agent 本质上是一个“代码库问答 + 检索增强生成”系统，核心链路包括：

1. 仓库上下文解析与绑定
2. 检索召回
3. `deep_research` 下的 `plan -> retrieval -> reflection -> final answer`
4. 流式输出 `documents`、`citations`、`thinking`、最终回答
5. 会话与结果落库

因此，评估不能只看“答得像不像”，还要分层看：

1. 检索是否找对文件和证据
2. 回答是否引用了正确上下文
3. 回答是否覆盖了关键事实
4. 端到端时延和稳定性是否可接受

## 目录说明

1. `codebase_agent_golden_set.example.json`
   一个黄金评测集样例，你可以按同样结构扩充到 30-100 条。
2. `../scripts/run_agent_eval.py`
   批量调用后端接口并产出评测报告。

## 推荐的评估层次

### 1. 离线自动评估

适合每次改检索、Prompt、引用格式、模型配置后跑一次。

建议重点看这些指标：

1. `has_answer`
   是否生成了有效答案。
2. `has_citations`
   当题目要求引用时，是否真的返回了引用。
3. `expected_file_path_recall`
   题目标注的目标文件，是否被 agent 的 `documents/citations` 命中。
4. `expected_citation_recall`
   如果你已经细化到具体引用片段，可直接检查召回率。
5. `must_include_recall`
   答案是否覆盖了关键术语或关键结论。
6. `must_not_include_pass`
   是否避免了明显错误结论。
7. `latency_seconds`
   端到端耗时。

### 2. 人工审查

自动规则适合做回归，但不能完全替代人工判断。建议每次从评测集中抽 10 条看下面 4 项：

1. 结论是否忠实于代码证据
2. 引用是否真的支撑结论
3. 是否回答了用户真正的问题
4. 是否存在“看起来合理但代码里没有”的幻觉

建议使用 1-5 分打分，分别对：

1. 正确性
2. 忠实度
3. 完整性
4. 可读性

### 3. 在线抽样评估

项目当前已经把 `model_answer`、`documents`、`recommended_questions`、`think` 写入数据库，可以从真实会话中每周抽样：

1. 高价值问题
2. 用户追问次数多的问题
3. 无引用或低引用的问题
4. 失败或报错的问题

## 推荐的数据集构成

第一版建议先做 30 条，按下面比例构建：

1. 文件职责类：8 条
2. 调用链类：8 条
3. 配置来源类：6 条
4. 数据流/落库类：4 条
5. 异常与边界类：4 条

如果后续更关注销售业务 agent，而不是代码问答 agent，再单独补“业务知识正确性”数据集，不要和代码库问答集混在一起。

## 数据集字段说明

每条 case 支持以下字段：

```json
{
  "id": "mcp_001",
  "question": "query_knowledge_hub 工具的主要输入参数有哪些？",
  "repository_ids": [],
  "expected_file_paths": [
    "src/mcp_server/tools/query_knowledge_hub.py"
  ],
  "expected_citations": [],
  "must_include": ["query_knowledge_hub", "query", "top_k", "collection"],
  "must_not_include": [],
  "require_citations": true,
  "tags": ["mcp", "tool_schema"]
}
```

字段含义：

1. `expected_file_paths`
   期望命中的文件路径，可用于衡量检索质量。
2. `expected_citations`
   如果你希望更严格，可以标到具体引用片段，例如 `src/mcp_server/tools/query_knowledge_hub.py:49-68`。
3. `must_include`
   期望答案中出现的关键词或关键结论。
4. `must_not_include`
   明确不该出现的错误关键词。
5. `require_citations`
   是否要求 agent 提供引用。

## 如何执行

先启动后端服务，再运行：

```bash
cd backend/app
python scripts/run_agent_eval.py \
  --dataset evals/codebase_agent_golden_set.example.json \
  --endpoint deep_research \
  --base-url http://127.0.0.1:8000 \
  --output evals/reports/deep_research_report.json
```

如果你想拿 `ai_search` 做基线对比：

```bash
cd backend/app
python scripts/run_agent_eval.py \
  --dataset evals/codebase_agent_golden_set.example.json \
  --endpoint ai_search \
  --base-url http://127.0.0.1:8000 \
  --output evals/reports/ai_search_report.json
```

## 建议的验收门槛

第一版可以先用下面的经验阈值：

1. `has_answer >= 0.98`
2. `has_citations >= 0.90`
3. `expected_file_path_recall >= 0.75`
4. `must_include_recall >= 0.80`
5. `must_not_include_pass >= 0.95`
6. `p95 latency_seconds` 不超过你当前可接受的交互时延

如果 `deep_research` 在 `expected_file_path_recall` 和 `must_include_recall` 上持续优于 `ai_search`，就说明多阶段 agent 设计是有收益的。

## 后续可扩展方向

这套方案目前是“零额外依赖”的规则评估版，适合作为第一层回归防线。后续你可以继续扩展：

1. 增加 `LLM-as-Judge`，评估忠实度和完整度
2. 增加基于历史消息表的线上样本回放
3. 对 `plan`、`reflection` 中间动作单独统计成功率
4. 把报告接到 CI，做变更前后对比
