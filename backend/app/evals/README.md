# CodeResearch Agent 评估方案

这个目录用于评估当前项目的代码知识库 Agent。新版方案不再只看“回答像不像”，而是把 Agent 的关键链路拆开评估：

1. 代码库检索是否找到正确文件
2. 回答是否带代码引用
3. 网络搜索是否真的被调用，并能和代码证据融合
4. 多轮会话/记忆问题是否能回答
5. 是否避免“请提供某目录源码”这类证据缺失话术
6. 流式接口是否稳定返回答案、引用和结束信号

## 文件说明

`agent_eval_suite.v2.json`
新版评估集，覆盖代码实现、工具注册、网络搜索融合、记忆、多轮上下文和 README 依赖回归。

`codebase_agent_golden_set.example.json`
旧版基础样例，适合继续扩充单轮代码问答 case。

`../scripts/run_agent_eval.py`
端到端评估脚本，会调用 `deep_research` 或 `ai_search` 接口，解析 SSE 输出并生成 JSON 报告。

## 评估指标

基础指标：

- `has_answer`: 是否生成了最终答案。
- `latency_seconds`: 单轮端到端耗时。
- `documents_count`: 后端返回的证据文档数量。
- `citations_count`: 后端返回的代码引用数量。
- `score`: 当前 case 的规则平均分。

代码库指标：

- `has_citations`: 需要引用时，是否真的返回引用。
- `expected_file_path_recall`: 期望代码文件是否被 `documents/citations` 命中。
- `expected_citation_recall`: 期望引用片段是否被命中。
- `must_include_recall`: 答案是否包含关键事实。
- `must_not_include_pass`: 答案是否避开明确错误内容。
- `failure_phrase_pass`: 是否避开“证据不足、请提供目录”等失败话术。

网络搜索指标：

- `web_search_called_pass`: 要求联网时，是否真的走了网络搜索链路或返回搜索状态。
- `web_search_has_results_pass`: 要求联网时，是否获得了搜索结果。
- `web_must_include_recall`: 网络结果中是否包含期望外部知识，例如 `Model Context Protocol`、`Serper`。

记忆指标：

- `memory_answer_recall`: 多轮场景下，答案是否能召回前文问题或对话主题。

## 数据集格式

单轮 case：

```json
{
  "id": "code_mcp_server_impl",
  "question": "请说明这个项目里的 MCP Server 是怎么实现的。",
  "repository_ids": [],
  "web_search": false,
  "expected_file_paths": [
    "src/mcp_server/protocol_handler.py",
    "src/mcp_server/server.py"
  ],
  "must_include": ["create_mcp_server", "ProtocolHandler", "tools/list", "tools/call"],
  "must_not_include": ["请提供 src/mcp_server"],
  "require_citations": true,
  "forbid_failure_phrases": true,
  "tags": ["code_first", "mcp"]
}
```

多轮 case：

```json
{
  "id": "memory_previous_question",
  "repository_ids": [],
  "web_search": false,
  "turns": [
    {
      "message": "请解释 src/mcp_server/protocol_handler.py 的作用。",
      "expected_file_paths": ["src/mcp_server/protocol_handler.py"],
      "require_citations": true
    },
    {
      "message": "我上一个问题是什么？",
      "require_memory": true,
      "memory_must_include": ["src/mcp_server/protocol_handler.py"]
    }
  ]
}
```

## 如何运行

先启动后端服务，然后执行：

```bash
cd backend/app
python scripts/run_agent_eval.py \
  --dataset evals/agent_eval_suite.v2.json \
  --endpoint deep_research \
  --base-url http://127.0.0.1:8000 \
  --output evals/reports/deep_research_v2_report.json
```

对比普通搜索链路：

```bash
cd backend/app
python scripts/run_agent_eval.py \
  --dataset evals/agent_eval_suite.v2.json \
  --endpoint ai_search \
  --base-url http://127.0.0.1:8000 \
  --output evals/reports/ai_search_v2_report.json
```

## 建议验收门槛

第一阶段可以用下面的阈值作为回归门禁：

- `has_answer >= 0.98`
- `has_citations >= 0.90`
- `expected_file_path_recall >= 0.75`
- `must_include_recall >= 0.80`
- `failure_phrase_pass >= 0.95`
- `web_search_called_pass = 1.0`，仅针对要求联网的 case
- `web_search_has_results_pass >= 0.80`，仅针对要求联网的 case
- `memory_answer_recall >= 0.80`，仅针对记忆 case

## 人工评估维度

自动评估只能做回归防线。每次改 Agent 流程、Prompt、检索策略、网络搜索策略后，建议抽样人工打分：

- 正确性：结论是否正确。
- 忠实度：结论是否被代码引用或网络来源支撑。
- 完整性：是否回答了用户真正的问题。
- 可读性：是否能帮助用户理解代码执行过程，而不是复述 README。
- 工具使用合理性：需要联网时是否联网，不需要联网时是否坚持代码优先。

每项 1-5 分，低于 4 分的样本应补进 `agent_eval_suite.v2.json` 作为回归 case。
