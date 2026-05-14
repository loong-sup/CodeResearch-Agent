# CodeResearch Agent

CodeResearch Agent 是一个面向代码库和项目文档的智能问答与深度研究系统。它支持上传源码仓库压缩包、单文件或 Markdown 文档，自动建立检索索引，并结合大模型、RAG 检索和可选 Web 搜索回答代码实现位置、调用链路、配置来源、模块职责和错误定位等问题。

## 功能特性

- 代码库问答：围绕已上传仓库回答“功能在哪里实现”“接口调用流程是什么”等问题。
- 项目索引：支持上传 `.zip` 项目压缩包，也支持上传单个代码或文档文件。
- RAG 检索：基于 Elasticsearch 和本地知识库召回相关代码片段与文档片段。
- 深度研究：通过多步骤 Agent 进行代码库分析，并记录运行过程和中间步骤。
- Web 搜索：可选接入 Serper 获取实时网页搜索结果，补充外部信息。
- 会话历史：保存会话、消息、引用片段和推荐追问。
- 前后端分离：后端使用 FastAPI，前端使用 React、TypeScript、Vite 和 Ant Design。

## 技术栈

| 模块 | 技术 |
| --- | --- |
| 前端 | React 18, TypeScript, Vite, Ant Design, Axios, Valtio |
| 后端 | FastAPI, Uvicorn, SQLAlchemy |
| 检索与存储 | Elasticsearch, PostgreSQL, ChromaDB |
| 大模型 | 阿里云百炼 DashScope |
| 搜索 | Serper API |
| 部署 | Docker Compose |

## 目录结构

```text
.
├── backend/
│   ├── app/                    # FastAPI 应用、路由、服务、检索和 Agent 逻辑
│   ├── docker-compose.yml      # 后端完整 Docker Compose 配置
│   ├── docker-compose-base.yml # 仅启动 PostgreSQL 和 Elasticsearch
│   └── init.sql                # 数据库初始化脚本
├── frontend/
│   ├── src/                    # React 前端源码
│   ├── package.json
│   └── vite.config.ts
└── README.md
```

## 环境要求

- Docker 和 Docker Compose
- Python 3.11
- Node.js 18 或更高版本
- npm
- DashScope API Key
- Serper API Key，可选，仅在启用 Web 搜索时需要

## 环境变量

后端常用变量：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
SERPER_API_KEY=your_serper_api_key
DATABASE_URL=postgresql://postgres:pg123456@localhost:5432/gsk
ES_URL=http://localhost:9200
ES_PORT=9200
ELASTIC_PASSWORD=your_elasticsearch_password
STACK_VERSION=8.11.3
MEM_LIMIT=1073741824
TIMEZONE=Asia/Shanghai
```

前端常用变量：

```env
VITE_API_BASE=http://127.0.0.1:8000
VITE_TITLE=CodeResearch Agent
```

## 快速启动

### 方式一：Docker Compose 启动后端依赖和 API

进入后端目录：

```bash
cd backend
```

确认 `backend/.env.docker` 已配置好数据库、Elasticsearch 和 API Key 后启动：

```bash
docker compose up -d --build
```

查看服务状态：

```bash
docker compose ps
```

查看 API 服务日志：

```bash
docker compose logs -f ai_search
```

后端默认运行在：

```text
http://127.0.0.1:8000
```

### 方式二：本地开发启动后端

先启动 PostgreSQL 和 Elasticsearch：

```bash
cd backend
docker compose -f docker-compose-base.yml up -d
```

创建 Python 环境并安装依赖：

```bash
cd app
conda create -n coderesearch-agent python=3.11
conda activate coderesearch-agent
python -m pip install -r requirements.txt
```

启动 FastAPI：

```bash
python app_main.py
```

### 启动前端

新开终端进入前端目录：

```bash
cd frontend
npm install
npm run dev
```

前端开发服务默认运行在：

```text
http://127.0.0.1:5173
```

## 基本使用

1. 打开前端页面。
2. 进入“代码仓库”页面，上传项目 `.zip` 压缩包或单个项目文档。
3. 等待索引完成后，回到问答页面。
4. 输入代码库相关问题，例如：

```text
这个功能在哪里实现？
某个接口的请求入口和处理流程是什么？
AuthService 在哪里定义，又在哪里被调用？
这个配置项是从哪里读取并生效的？
这个错误信息是从哪段代码抛出来的？
```

## 主要接口

创建会话：

```bash
curl -X POST http://127.0.0.1:8000/create_session
```

上传单文件：

```bash
curl -X POST "http://127.0.0.1:8000/upload_files/?session_id=default" \
  -F "files=@README.md"
```

上传项目压缩包：

```bash
curl -X POST "http://127.0.0.1:8000/upload_project_archive/?session_id=default" \
  -F "archive=@project.zip"
```

代码库问答：

```bash
curl -N -X POST "http://127.0.0.1:8000/ai_search/?session_id=default" \
  -H "Content-Type: application/json" \
  -d '{"message":"这个项目的登录接口在哪里实现？","web_search":false}'
```

深度研究：

```bash
curl -N -X POST "http://127.0.0.1:8000/deep_research/?session_id=default" \
  -H "Content-Type: application/json" \
  -d '{"message":"分析这个项目的整体架构和核心模块职责","web_search":false}'
```

获取已上传仓库列表：

```bash
curl http://127.0.0.1:8000/get_files/
```

## 开发命令

前端：

```bash
cd frontend
npm run dev
npm run build
npm run lint
```

后端：

```bash
cd backend/app
python app_main.py
```

Docker：

```bash
cd backend
docker compose up -d --build
docker compose logs -f ai_search
docker compose down
```

## 说明

当前项目中的用户身份逻辑仍以默认用户 `1` 为主，适合本地原型验证和二次开发。若用于多人环境或公开部署，需要补齐认证授权、密钥管理、上传文件安全限制和生产级配置。
