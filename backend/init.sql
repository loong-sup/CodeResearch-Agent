
CREATE EXTENSION IF NOT EXISTS pgcrypto;
-- 创建 users 表
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- 创建会话表
CREATE TABLE IF NOT EXISTS sessions (
    session_id VARCHAR(16) PRIMARY KEY,
    session_name VARCHAR(255) NOT NULL,  
    user_id VARCHAR(255) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_created_at  ON sessions(created_at);

-- 创建 messages 表
CREATE TABLE IF NOT EXISTS messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(16) NOT NULL,
    user_question TEXT NOT NULL,
    model_answer TEXT NOT NULL,
    documents  TEXT,  -- 修改为 jsonb 类型
    recommended_questions TEXT,  
    think TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at);

-- 创建知识库表
CREATE TABLE IF NOT EXISTS knowledgebases (
    id SERIAL PRIMARY KEY,  -- 主键，自增
    user_id VARCHAR(255) NOT NULL,       -- 用户 ID
    file_name VARCHAR(255) NOT NULL,     -- 文件名称
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- 创建时间
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP  -- 更新时间
);

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_knowledgebases_user_id ON knowledgebases(user_id);
CREATE INDEX IF NOT EXISTS idx_knowledgebases_created_at ON knowledgebases(created_at);

-- 创建仓库级知识库表
CREATE TABLE IF NOT EXISTS repositories (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(32) NOT NULL DEFAULT 'doc',
    status VARCHAR(32) NOT NULL DEFAULT 'ready',
    index_name VARCHAR(255) NOT NULL,
    storage_path TEXT NOT NULL,
    root_path TEXT,
    archive_path TEXT,
    file_count INTEGER NOT NULL DEFAULT 0,
    indexed_chunks INTEGER NOT NULL DEFAULT 0,
    language_stats TEXT,
    metadata_json TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_repositories_user_id ON repositories(user_id);
CREATE INDEX IF NOT EXISTS idx_repositories_updated_at ON repositories(updated_at);

-- 创建会话与仓库绑定表，用于默认知识库解析
CREATE TABLE IF NOT EXISTS session_repository_contexts (
    session_id VARCHAR(16) PRIMARY KEY,
    user_id VARCHAR(255) NOT NULL,
    repository_id VARCHAR(64) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_session_repository_contexts_user_id
ON session_repository_contexts(user_id);

-- 创建 Agent 运行轨迹表
CREATE TABLE IF NOT EXISTS agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(16) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    user_question TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'running',
    repository_context TEXT,
    final_answer TEXT,
    final_evidence TEXT,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_runs_session_id ON agent_runs(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_runs_user_id ON agent_runs(user_id);

-- 创建 Agent 步骤表，记录 plan/tool/reflection/final answer
CREATE TABLE IF NOT EXISTS agent_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    step_type VARCHAR(32) NOT NULL,
    tool_name VARCHAR(128),
    input_json TEXT,
    output_json TEXT,
    error TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agent_steps_run_id ON agent_steps(run_id);
