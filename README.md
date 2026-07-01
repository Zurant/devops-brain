# DevOps Brain

面向企业级场景的智能代码审查多 Agent 协作平台。
本项目采用 Human-in-the-Loop (HITL) 设计模式，结合 LangGraph 编排多个专家 Agent，实现自动化的代码分析与人工审批闭环。

## 当前状态

MVP 功能主链路已完成：项目已经可以基于 mock GitLab MR payload 跑通「Webhook 触发 -> 多 Agent 并行审查 -> Summary 风险汇总 -> HIGH 风险人工审批 -> Approve/Modify 回写评论、Reject 结束流程」的闭环。

企业化落地已开始：当前已引入 PostgreSQL + SQLAlchemy + Alembic，新增审查任务、Agent 输出、审批记录三张核心表，并将待审批列表、审批结果、Review History 接入数据库。后续异步任务队列、审计日志、权限模型等规划见 [企业化演进计划](docs/enterprise-plan.md)。

## 🛠️ 重点技术栈
MVP 阶段使用以下技术栈：
- **核心编排**: `langgraph` (必须使用 StateGraph 和 interrupt 机制)
- **大模型调用**: `litellm` (必须通过 `litellm.completion` 统一调用，代理地址配置在 `.env` 中)
- **Web 框架**: `fastapi` + `uvicorn` (用于接收 GitLab Webhook 和提供人工审批接口)
- **数据存储**: `sqlite3` (Python 内置，用于 LangGraph 的 Checkpointer 状态持久化)
- **可观测性**: `langfuse` (必须使用其 Python SDK 追踪 Agent 调用链)

## 🤖 核心架构与多 Agent 协作

本项目的目标场景为**智能代码审查 (Code Review)**，主要对内网 GitLab 的 Merge Request 进行审查。共有 5 个核心 Agent 参与协作：

1. **Orchestrator Agent (调度节点)**：接收 MR Webhook 数据，分发审查任务。
2. **Quality Agent (代码质量专家)**：分析代码异味、圈复杂度。
3. **Security Agent (安全审计专家)**：检查安全漏洞、敏感信息泄露。
4. **Architecture Agent (架构合规专家)**：检查代码是否符合设计模式和规范。
5. **Summary Agent (汇总与决策)**：收集以上输出，进行风险评级。

### 系统流程图

```mermaid
graph LR
    A["GitLab MR\nWebhook"] --> B["Orchestrator\n(调度器)"]

    B --> C["Quality Agent\n代码质量"]
    B --> D["Security Agent\n安全审计"]
    B --> E["Architecture Agent\n架构合规"]

    C --> F["Summary Agent\n汇总决策"]
    D --> F
    E --> F

    F --> G{"风险等级?"}
    G -- "HIGH" --> H["人工审批\n(interrupt)"]
    G -- "LOW/MEDIUM" --> I["回写 GitLab\nComment"]
    H -- "Approve/Modify" --> I
    H -- "Reject" --> J["结束"]
```

> **基础设施**：SQLite Checkpointer（状态持久化） · LangFuse（调用链追踪）

### 工作流与 HITL 机制
工作流由 **LangGraph** 驱动：
- 当 `Summary Agent` 评估出的代码风险等级较高时，图执行会触发 `interrupt`，挂起当前工作流。
- 状态由 **SQLite Checkpointer** 持久化。
- 人类介入并通过 FastAPI 提供的审批端点传入 `resume` 信号（Approve/Modify/Reject）后，工作流唤醒并继续执行。
- Approve 会回写原始 AI 评论；Modify 会回写人工修改后的评论；Reject 会结束流程且不回写普通审查评论。
- 非 HIGH 风险结果会自动通过 GitLab API 回写 Comment 到指定的 Merge Request。

## ⚠️ MVP 阶段开发约束
为了保证 MVP 能够稳定收口，早期阶段遵循以下约束：

1. **避免过早扩展技术栈**：MVP 阶段不引入额外的 ORM、Celery/Redis，状态挂起依赖 LangGraph 原生机制。
2. **状态严格强类型**：所有的共享状态必须在 `src/core/state.py` 中使用 `TypedDict` 或 Pydantic BaseModel 严格定义。
3. **最小代码原则**：每次只写当前步骤需要的代码。不要在一次对话中试图把 5 个 Agent 全写完。
4. **遇事不决先 Mock**：与 GitLab 的交互，务必使用 `tests/fixtures/mock_mr_payload.json` 进行本地测试，保证本地脱机能够跑通完整图流转后，再对接真实 API。
5. **极简前端交互**：HITL 审批流提供一个极简的 Web 审批界面（纯 HTML/JS，由 FastAPI 直接 serve），能直观展示风险结果并提供 Approve/Modify/Reject 按钮。

企业化阶段允许引入 PostgreSQL、SQLAlchemy/Alembic、Redis、Celery、审计日志与权限模型，具体见 [企业化演进计划](docs/enterprise-plan.md)。

## 企业化数据库

默认数据库连接：
```bash
DATABASE_URL="postgresql+psycopg://devops_brain:devops_brain@localhost:5432/devops_brain"
```

生成并检查 PostgreSQL migration SQL：
```bash
poetry run alembic upgrade head --sql
```

连接本地 PostgreSQL 后执行迁移：
```bash
poetry run alembic upgrade head
```

## 内网基础设施部署

当前推荐部署方式：内网服务器只启动基础设施容器，DevOps Brain 服务仍在本地使用 Poetry 启动。

服务器侧使用 [docker-compose.infra.yml](docker-compose.infra.yml)，包含：
- `postgres`：业务库与 Langfuse 元数据库
- `redis`：后续 Celery 队列与 Langfuse 队列依赖
- `langfuse-web` / `langfuse-worker`：Langfuse 私有化部署
- `clickhouse`：Langfuse 事件分析存储
- `minio`：Langfuse 事件文件存储

当前 compose 已尽量使用服务器已有镜像：
- `postgres:15`
- `redis:7`
- `langfuse/langfuse:3`
- `langfuse/langfuse-worker:3`
- `clickhouse/clickhouse-server:latest`
- `minio/minio:latest`

服务器侧部署步骤：
```bash
cp .env.infra.example .env.infra
```

编辑 `.env.infra`，至少替换以下配置：
- `POSTGRES_PASSWORD`
- `NEXTAUTH_SECRET` / `SALT` / `ENCRYPTION_KEY`
- `CLICKHOUSE_PASSWORD`
- `MINIO_ROOT_PASSWORD`
- `LANGFUSE_PUBLIC_URL`

启动：
```bash
ENV_FILE=.env.infra docker compose -f docker-compose.infra.yml up -d
```

查看服务：
```bash
docker compose -f docker-compose.infra.yml ps
docker compose -f docker-compose.infra.yml logs -f langfuse-web
```

服务器侧访问地址：
- Langfuse：`http://服务器IP:3000`
- MinIO Console：`http://服务器IP:9001`

首次启动后，进入 MinIO Console，使用 `.env.infra` 中的 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` 登录，并创建 bucket：
```text
langfuse
```

如果 `.env.infra` 中修改了 `LANGFUSE_S3_EVENT_UPLOAD_BUCKET`，则创建对应名称的 bucket。

本地应用连接服务器基础设施：
```bash
cp .env.local-with-remote-infra.example .env
```

编辑 `.env`，将 `192.168.1.100` 替换为真实服务器 IP，并填入 GitLab、New API、Langfuse key。

首次进入 Langfuse 后创建项目，将项目的 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY` 写回本地 `.env`。

本地执行业务库迁移并启动 API 与审查 Worker：
```bash
poetry run alembic upgrade head
poetry run uvicorn src.api.server:app --reload
poetry run python -m src.queue.worker
```

本地访问：
- DevOps Brain API：`http://127.0.0.1:8000`
- 审批页面：`http://127.0.0.1:8000/static/approval.html`

## 🚀 快速开始

### 1. 环境准备
使用 Poetry 安装依赖：
```bash
poetry install
```

### 2. 环境变量
复制 `.env.example` 为 `.env` 并配置相关密钥（包含 `NEW_API` 及内网 `GITLAB` 凭证）：
```bash
cp .env.example .env
```

### 3. 运行服务

Webhook 审查已改为 Redis/RQ 异步任务。启动本地应用前，需要确认 `.env` 中的 `REDIS_URL` 指向可用 Redis。

终端 1 启动 API：
```bash
poetry run uvicorn src.api.server:app --reload
```

Mock 模式启动：
```bash
ENV=mock poetry run uvicorn src.api.server:app --reload
```

终端 2 启动审查 Worker：
```bash
poetry run python -m src.queue.worker
```

macOS 本地默认使用 RQ `SimpleWorker` 避免 fork 崩溃；Linux 服务器默认使用标准 fork worker。如需手动指定：`RQ_WORKER_MODE=simple` 或 `RQ_WORKER_MODE=fork`。

### 4. 本地自测

图编译检查：
```bash
poetry run python -c "from src.core.workflow import graph; print('Graph compiled OK')"
```

自动化测试：
```bash
poetry run pytest tests -v
```

模拟 GitLab Webhook：
```bash
curl -X POST http://127.0.0.1:8000/api/webhook \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/mock_mr_payload.json
```

接口会快速返回 `queued`，实际 Multi-Agent 审查由 Worker 后台执行：
```json
{
  "status": "queued",
  "thread_id": "...",
  "job_id": "..."
}
```

查看待审批列表：
```bash
curl http://127.0.0.1:8000/api/pending
```

查看审查与审批历史：
```bash
curl http://127.0.0.1:8000/api/history
```

打开审批页面：
```text
http://127.0.0.1:8000/static/approval.html
```

审批语义：
- `Approve (Resume)`：恢复流程并回写 AI 生成的 GitLab 评论。
- `Modify & Submit`：使用页面中人工修改后的评论回写 GitLab。
- `Reject`：恢复并结束流程，不回写普通审查评论。
