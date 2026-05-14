# ES Repository Maintenance

这个脚本用于解决代码知识库从旧索引体系迁移到 `repository_id` 体系后，常见的三类问题：

1. 旧脏索引仍然残留在用户共享 ES 索引中
2. repository 元数据和 ES 中的 chunk 不一致
3. 需要对代码仓库重新建索引，以适配新的代码知识库问答

脚本位置：

```bash
backend/scripts/es_repository_maintenance.py
```

## 设计原则

当前代码知识库的正确索引策略是：

- 每个用户使用一个共享 ES 索引，索引名为 `user_id`
- 每个 chunk 必须带上这些关键元数据：
  - `repository_id`
  - `kb_id`
  - `user_id`
  - `doc_id`
  - `file_path_kwd`
  - `symbol_kwd`
  - `language_kwd`
  - `chunk_kind_kwd`
- 问答检索必须按 `repository_id` 过滤，而不是对用户的整个索引做全量搜索

因此，旧数据里这些情况都属于脏数据：

- 缺少 `repository_id`
- 缺少 `kb_id`
- `repository_id != kb_id`
- `repository_id` 在数据库中已不存在
- `user_id` 字段缺失或与当前用户不匹配

## 1. 核查索引

先看当前用户索引里到底有哪些脏数据：

```bash
cd backend
python scripts/es_repository_maintenance.py audit --user-id 1
```

如果希望看到每类问题的样本 chunk：

```bash
python scripts/es_repository_maintenance.py audit --user-id 1 --sample-size 5
```

这个命令会输出：

- ES 总 chunk 数
- 每类脏数据的数量
- orphan repository id 列表
- 每个 repository 的健康状态，包括：
  - `source_exists`
  - `parser_supported`
  - `db_indexed_chunks`
  - `es_docs`
  - `drift`
  - `recommendation`

其中 `recommendation` 的典型含义是：

- `healthy`: 当前仓库索引状态正常
- `rebuild_required_empty_index`: 仓库存在，但 ES 中没有对应 chunk
- `rebuild_recommended_chunk_drift`: DB 记录的 chunk 数和 ES 实际数不一致，建议重建
- `rebuild_required_status_error`: 仓库元数据状态已是 `error`
- `source_missing_reupload_or_fix_path`: 仓库源路径丢失，需要重新上传或修正路径
- `source_not_supported_check_root_path`: 指向的根路径不适合代码解析，需要检查 `root_path`

## 2. 清理旧脏索引

先 dry-run 看会删掉多少：

```bash
python scripts/es_repository_maintenance.py cleanup --user-id 1
```

确认无误后再真正执行：

```bash
python scripts/es_repository_maintenance.py cleanup --user-id 1 --apply
```

这个清理会删除：

- 没有 `repository_id` 的旧 chunk
- 没有 `kb_id` 的旧 chunk
- `repository_id != kb_id` 的不一致 chunk
- `repository_id` 已不在 `repositories` 表中的 orphan chunk
- `user_id` 不匹配当前用户索引的 chunk

这个步骤的目标是把“历史混入的脏 chunk”先从用户共享索引里移除，避免它们继续污染后续代码问答。

## 3. 重建单个代码库

如果你只想重建某个 repository：

```bash
python scripts/es_repository_maintenance.py rebuild --user-id 1 --repository-id <repository_id>
```

如果你只知道仓库名：

```bash
python scripts/es_repository_maintenance.py rebuild --user-id 1 --repository-name MODULAR-RAG-MCP-SERVER
```

上面两条默认是 dry-run，只打印计划，不真正执行。

真正执行时加 `--apply`：

```bash
python scripts/es_repository_maintenance.py rebuild --user-id 1 --repository-name MODULAR-RAG-MCP-SERVER --apply
```

## 4. 重建全部代码库

```bash
python scripts/es_repository_maintenance.py rebuild --user-id 1 --all --apply
```

如果你希望先清掉旧脏数据，再统一重建：

```bash
python scripts/es_repository_maintenance.py rebuild --user-id 1 --all --clean-dirty-first --apply
```

## 针对代码知识库的正确重建策略

为了让 ES 向量索引真正适配代码问答，而不是只做普通文档检索，重建时必须满足下面这套策略：

1. repository 对应的 `source_path` / `root_path` 必须指向真实源码根目录，而不是错误的中间目录。
1. 每个 chunk 必须重新通过 `code_repo.py` 的代码解析流程生成，而不是复用旧 ES 文档。
1. 每个 chunk 必须重新写入这些元数据：
   - `repository_id`
   - `kb_id`
   - `user_id`
   - `doc_id`
   - `file_path_kwd`
   - `symbol_kwd`
   - `language_kwd`
   - `chunk_kind_kwd`
1. 检索时必须按 `repository_id` 过滤，只在当前代码库内做向量 + 关键词混合召回。

这套策略对应你现在项目的实现就是：

- 共享用户索引：`index_name = user_id`
- 代码库隔离键：`repository_id`
- 检索过滤字段：`kb_id / repository_id`
- 代码解析入口：`backend/app/service/core/rag/app/code_repo.py`
- 索引写入入口：`backend/app/service/core/file_parse.py`

也就是说，正确的“重建”不是简单把 zip 再传一次，而是：

- 清掉这个用户索引里的历史脏 chunk
- 确认 repository 指向的 `root_path` 是正确源码目录
- 基于新的 `repository_id` 重新解析 + 重新向量化 + 重新写入 ES

## 推荐操作顺序

针对你现在这种“回答命中错误旧文件”的情况，推荐顺序是：

```bash
cd backend
python scripts/es_repository_maintenance.py audit --user-id 1 --sample-size 5
python scripts/es_repository_maintenance.py cleanup --user-id 1 --apply
python scripts/es_repository_maintenance.py rebuild --user-id 1 --repository-name MODULAR-RAG-MCP-SERVER --apply
python scripts/es_repository_maintenance.py audit --user-id 1 --sample-size 3
```

如果第一次 `audit` 里看到：

- `orphan_repository_ids` 不为空
- `missing_repository_id > 0`
- `kb_repository_mismatch > 0`
- `recommendation = rebuild_recommended_chunk_drift`

那说明当前 ES 用户索引里确实混有历史脏数据，必须先 `cleanup` 再 `rebuild`。

## 为什么这样重建更适合代码知识库

这个重建方式会从 repository 对应的真实源码根目录重新解析，而不是沿用旧索引里的残留 chunk，因此更适合代码问答场景：

- 会重新提取 `file_path_kwd`
- 会重新提取 `symbol_kwd`
- 会重新提取 `language_kwd`
- 会重新提取 `chunk_kind_kwd`
- 每个 chunk 会重新绑定正确的 `repository_id`
- 每个 repository 的 `indexed_chunks`、`language_stats`、`doc_ids` 也会同步刷新

这样在问“某个类在哪里实现”“某个配置从哪里生效”“某个调用链在哪”时，检索才能稳定落在正确代码库，而不是混入旧索引残留。

## 适配你当前项目的建议

对你这个项目，最稳妥的策略是：

1. 只保留新的 `repositories` 体系，不再让 legacy `knowledgebases` 参与选库。
1. 每次上传 zip 后，都确保前端选择的是后端返回的真实 `repository_id`。
1. 一旦发现回答引用了明显不属于当前仓库的文件，优先执行：

```bash
python scripts/es_repository_maintenance.py audit --user-id 1 --sample-size 5
python scripts/es_repository_maintenance.py cleanup --user-id 1 --apply
python scripts/es_repository_maintenance.py rebuild --user-id 1 --repository-name MODULAR-RAG-MCP-SERVER --apply
```

1. 重建完成后，再到聊天页重新发起问题，不要继续复用已经带有错误上下文的旧会话结果。

## 注意

- 该脚本假定你的 PostgreSQL 和 Elasticsearch 都已经正常启动
- `cleanup --apply` 会直接删除 ES 文档，执行前建议先跑 `audit`
- `rebuild --apply` 会先删除该 repository 旧 chunk，再重新入库
- 如果 repository 的 `source_path` / `root_path` 在磁盘上已经不存在，重建会失败并把 repository 状态标记为 `error`
