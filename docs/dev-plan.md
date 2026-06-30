# DevOps Brain — MVP 详细开发计划

> **本文档是 MVP 阶段的权威计划。** MVP 阶段必须按阶段顺序执行，完成当前阶段的 Done When 判定后，才能进入下一阶段。企业化落地阶段的 PostgreSQL、异步任务、审批历史、审计日志、权限模型等规划见 `docs/enterprise-plan.md`。

## 当前结论

- **MVP 功能主链路：已完成。** 当前代码已经跑通「Webhook 触发 -> 多 Agent 并行审查 -> Summary 风险汇总 -> HIGH 风险 HITL 审批 -> Approve/Modify 回写评论、Reject 结束流程」。
- **MVP 自动化测试：已通过。** 当前基线命令为 `poetry run pytest tests -v`。
- **MVP 验收材料：待补齐。** 真实 GitLab 回写截图、Langfuse 后台截图、面试话术文档仍需补充。
- **企业化阶段：尚未开始。** 后续不再受 MVP 阶段“不引入 ORM/Redis/PostgreSQL”的早期约束限制。

## 项目目录结构 (最终形态)

```
devops-brain/
├── CLAUDE.md                          # AI 助手行为准则
├── README.md                          # 项目介绍
├── pyproject.toml                     # 依赖管理
├── .env                               # 环境变量 (不入库)
├── .env.example                       # 环境变量模板
├── docs/
│   ├── dev-plan.md                    # MVP 阶段计划
│   └── enterprise-plan.md             # 企业化落地阶段计划
├── src/
│   ├── __init__.py
│   ├── core/                          # 编排引擎核心
│   │   ├── __init__.py
│   │   ├── state.py                   # ✅ 已完成 — 全局状态定义
│   │   └── workflow.py                # LangGraph StateGraph 定义
│   ├── agents/                        # Agent 实现
│   │   ├── __init__.py
│   │   ├── orchestrator.py            # 调度节点 (入口)
│   │   ├── quality.py                 # 代码质量审查
│   │   ├── security.py                # 安全审计
│   │   ├── architecture.py            # 架构合规
│   │   └── summary.py                 # 汇总与风险评级
│   ├── tools/                         # Agent 可调用的外部工具
│   │   ├── __init__.py
│   │   ├── gitlab_client.py           # GitLab API 封装
│   │   └── llm_client.py             # LiteLLM 统一调用封装
│   ├── api/                           # FastAPI 服务
│   │   ├── __init__.py
│   │   ├── server.py                  # FastAPI 入口
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── webhook.py             # POST /api/webhook
│   │       └── approval.py            # POST /api/resume + GET /api/pending
│   └── static/                        # 极简前端
│       └── approval.html              # HITL 审批页面 (纯 HTML/JS)
├── tests/
│   ├── __init__.py
│   ├── fixtures/
│   │   └── mock_mr_payload.json       # ✅ 已完成 — 模拟 MR Webhook 数据
│   ├── test_graph_basic.py            # Phase 1 验证测试
│   └── test_agents.py                 # Phase 2 验证测试
└── .gitignore
```

---

## Phase 1: 基础设施与编排骨架

**目标**：搭建 FastAPI 服务 + LangGraph 空图，用 Dummy 节点跑通完整的「触发 → 并行 → 汇总 → 中断 → 恢复」流程。

### 1.0 项目初始化
- 确认 `pyproject.toml` 已创建（✅ 已完成）
- 执行 `poetry install` 安装所有依赖
- 确认 `.env` 文件已正确配置（✅ 已完成）
- 创建 `.gitignore`（至少包含 `.env`、`__pycache__/`、`*.db`）

### 1.1 创建 `src/__init__.py` ✅ 已完成
空文件，初始化顶层包。

### 1.2 创建 `src/tools/llm_client.py` ✅ 已完成
封装 LiteLLM 调用，统一读取 `.env` 配置：
```python
import litellm

def call_llm(prompt: str, model: str = None) -> str:
    """
    统一的 LLM 调用入口。
    - model: 默认从 .env 的 MODEL_NAME 读取
    - api_base: 从 .env 的 NEW_API_BASE_URL 读取
    - api_key: 从 .env 的 NEW_API_KEY 读取
    必须使用 litellm.completion()，model 参数格式为 "openai/{model_name}"。
    """
```

**容错机制（必须实现）**：
- LLM 调用失败时 **retry 1 次**（间隔 2 秒）。
- 仍然失败则返回 **fallback 结果**：`{"agent": "<agent_name>", "issues": [], "risk": "MEDIUM", "error": "LLM call failed"}`。
- 绝对不允许因为单次 LLM 调用失败而导致整个 graph 崩溃。

### 1.3 创建 `src/core/workflow.py` ✅ 已完成
这是 LangGraph 图的核心定义文件。关键要求：

- 使用 `StateGraph(ReviewState)` 构建图。
- **入口节点 (orchestrator)**：初始化所有 Optional 字段为默认值（防 KeyError），解析 diff。
- **三个并行审查节点 (quality / security / architecture)**：Phase 1 阶段只需返回 mock 数据，例如 `{"agent": "quality", "issues": [], "risk": "LOW"}`。
- **汇总节点 (summary)**：Phase 1 只做简单逻辑 — 取 reviews 中所有 Agent 的最高 risk 等级作为 `final_risk_level`，不调用 LLM。
- **HITL 判断边**：条件路由 — 如果 `final_risk_level == "HIGH"` 则走向 `human_review` 节点；否则走向 `END`。
- **human_review 节点**：调用 `interrupt()`，暂停图执行。
- **Checkpointer**：使用 `SqliteSaver`（而非 MemorySaver），因为 `GET /api/pending` 需要持久化查询能力。
- **Pending 索引**：在 `server.py` 中维护一个内存级的 `pending_reviews: dict[str, dict]`，当 graph 执行触发 interrupt 时，将 `thread_id` 及相关元数据（mr_url、risk_level 等）写入此 dict；resume 后移除。`GET /api/pending` 直接读取此 dict 返回。

图的拓扑结构：
```
orchestrator → [quality, security, architecture] (并行) → summary → 条件判断
                                                                      ├── HIGH → human_review (interrupt) → END
                                                                      └── else → END
```

### 1.4 创建 `src/api/server.py` ✅ 已完成
FastAPI 基础服务：
- 加载 `.env` (使用 `python-dotenv`)
- 挂载 `src/static/` 目录为静态文件
- 引入路由模块

### 1.5 创建 `src/api/routes/webhook.py` ✅ 已完成
```
POST /api/webhook
```
- 接收 GitLab MR Webhook JSON (或 mock payload)
- 从 payload 中提取 `mr_id`, `project_id`, `diff_content`, `mr_url`
- 生成唯一 `thread_id`
- 调用 `graph.invoke(initial_state, config={"configurable": {"thread_id": thread_id}})`
- 返回执行结果或中断状态

### 1.6 创建 `src/api/routes/approval.py` ✅ 已完成
```
POST /api/resume
```
- 接收 `thread_id` 和 `decision` (approve/reject/modify)
- 调用 `graph.invoke(Command(resume=decision), config={"configurable": {"thread_id": thread_id}})`
- 返回恢复后的执行结果

```
GET /api/pending
```
- 返回当前所有处于 `interrupt` 状态的待审批任务列表

### 1.7 创建 `tests/test_graph_basic.py` ✅ 已完成
编写最基础的图运转测试：
- 测试用例 1：输入低风险 diff → 图直接走到 END，不触发 interrupt
- 测试用例 2：输入高风险 diff → 图在 human_review 节点中断，resume 后走到 END

### Phase 1 Done When
```bash
# 1. 图编译不报错
python -c "from src.core.workflow import graph; print('Graph compiled OK')"

# 2. 基础测试通过
pytest tests/test_graph_basic.py -v
```
**达到以上标准后必须停止，等待人工审核后再进入 Phase 2。**

---

## Phase 2: Agent 开发与 Mock 数据

**目标**：将 Phase 1 中 quality / security / architecture 三个 Dummy 节点替换为真正调用 LLM 的 Agent。**注意：summary 节点在本阶段保持 mock 逻辑（取 reviews 最高 risk），Phase 3 才替换为 LLM 驱动。**

### 2.1 创建 `src/agents/orchestrator.py` ✅ 已完成
- 解析 `mock_mr_payload.json` 格式的 Webhook 数据
- 从 `changes` 数组中提取所有 diff 内容，拼接为完整的 `diff_content`
- 初始化 `ReviewState` 中所有字段的默认值

### 2.2 创建 `src/agents/quality.py` ✅ 已完成
- 调用 `llm_client.call_llm()` 分析代码质量
- Prompt 关注点：代码异味、圈复杂度、命名规范、重复代码
- 输出必须严格为 `{"agent": "quality", "issues": [...], "risk": "LOW|MEDIUM|HIGH"}` 格式
- 将结果追加到 `state["reviews"]`

### 2.3 创建 `src/agents/security.py` ✅ 已完成
- Prompt 关注点：SQL 注入、XSS、密钥泄露、不安全的依赖
- 输出格式同上，`agent` 字段为 `"security"`

### 2.4 创建 `src/agents/architecture.py` ✅ 已完成
- Prompt 关注点：SOLID 原则、分层违规、过度耦合
- 输出格式同上，`agent` 字段为 `"architecture"`

### 2.5 更新 `src/core/workflow.py` ✅ 已完成
- 将 quality / security / architecture 三个 Dummy 节点替换为真实的 Agent 函数调用
- **summary 节点保持 Phase 1 的 mock 逻辑不变**

### 2.6 创建 `tests/test_agents.py` ✅ 已完成
测试必须分为两层：

**单元测试（自动化，必须通过）**：
- Mock 掉 `call_llm`，注入预设的 LLM 返回值
- 验证每个 Agent 的输出格式符合预期 schema：`{"agent": str, "issues": list, "risk": str}`
- 验证 `risk` 字段只能是 `"LOW"` / `"MEDIUM"` / `"HIGH"` 之一
- 验证 LLM 调用失败时 fallback 机制正常工作

**集成测试（手动执行，不纳入 CI）**：
- 使用 `tests/fixtures/mock_mr_payload.json` 中自带的 SQL 注入样本
- 调用真实 LLM，验证 Security Agent 能检测出该漏洞
- 在 `tests/test_agents_integration.py` 中编写，文件名带 `integration` 以区分

### Phase 2 Done When
```bash
# 1. 单元测试全部通过（mock LLM，验证格式和容错）
pytest tests/test_agents.py -v

# 2. 集成测试手动跑一次（真实 LLM，验证检测能力）
python -m pytest tests/test_agents_integration.py -v -s
# 人工确认 Security Agent 的输出中包含对 SQL 注入的告警
```
**达到以上标准后必须停止，等待人工审核后再进入 Phase 3。**

---

## Phase 3: 汇总决策与 HITL 审批界面

**目标**：开发 Summary Agent 生成最终报告，并提供一个可视化的 Web 审批界面。

### 3.1 创建 `src/agents/summary.py`
- 读取 `state["reviews"]` 中所有 Agent 的输出
- 调用 LLM 进行综合分析：去重、冲突检测、风险汇总
- 输出：`final_risk_level` (取所有 Agent 中最高的风险等级)、`summary_report` (结构化的分析报告)、`final_comment` (适合直接贴到 GitLab MR 的 Markdown 格式评论)

### 3.2 创建 `src/static/approval.html`
极简的纯 HTML/JS 审批页面，由 FastAPI 直接 serve：
- 页面加载时调用 `GET /api/pending` 获取待审批列表
- 展示每条待审批的 `summary_report` 和 `final_risk_level`
- 提供 MR 链接 (`mr_url`) 可跳转到 GitLab 查看原始代码
- 提供 Approve / Reject 按钮，点击后调用 `POST /api/resume`
- 操作结果实时反馈

### 3.3 创建 `src/tools/gitlab_client.py`
封装 GitLab V4 API：
- `get_mr_changes(project_id, mr_iid)` — 获取 MR 的 diff (真实模式)
- `post_mr_comment(project_id, mr_iid, comment)` — 将审查结果回写为 MR 评论
- 通过 `.env` 中的 `ENV` 变量切换 mock/prod 模式：
  - `ENV=mock` → 读取 fixture 文件，打印 comment 到终端
  - `ENV=prod` → 真实调用 GitLab API

### Phase 3 Done When
```bash
# 1. 启动服务
poetry run uvicorn src.api.server:app --reload

# 2. 用 curl 模拟 webhook 触发
curl -X POST http://localhost:8000/api/webhook \
  -H "Content-Type: application/json" \
  -d @tests/fixtures/mock_mr_payload.json

# 3. 打开浏览器访问 http://localhost:8000/static/approval.html
# 能看到待审批项，点击 Approve 后流程正常结束

# 4. 确认 final_comment 被正确生成（mock 模式下打印到终端）
```
**达到以上标准后必须停止，等待人工审核后再进入 Phase 4。**

---

## Phase 4: 真实集成与可观测性

**目标**：接入真实 GitLab Webhook，接入 LangFuse 追踪，完善文档。

### 4.1 GitLab Webhook 真实联调
- [x] 在内网 GitLab 的目标项目中配置 Webhook，指向 `http://<本机IP>:8000/api/webhook`
- [x] 触发事件选择 `Merge Request events`
- [x] 创建一个测试 MR，验证整个流程端到端跑通

### 4.2 接入 LangFuse
- [x] 在 `src/tools/llm_client.py` 中集成 LangFuse 的回调
- [x] 每次 LLM 调用自动上报 trace（输入 prompt、输出结果、耗时、token 数）
- [x] 在 LangFuse 后台验证能看到完整的调用链路图

### 4.3 完善文档
- [x] 更新 `README.md`：补充完整的架构图、截图、演示步骤
- [x] 编写面试话术要点（可放在 `docs/interview-notes.md`）

### Phase 4 Done When
- [x] mock GitLab MR 触发后，Agent 审查结果可回写为 mock MR Comment
- [x] HIGH 风险结果可以进入审批页，并支持 Approve / Modify / Reject
- [x] 自动化测试通过：`poetry run pytest tests -v`
- [ ] 真实 GitLab MR 触发后，Agent 审查结果自动回写为 MR Comment，并补充截图
- [ ] LangFuse 后台能看到完整的 Agent 调用链路，并补充截图
- [ ] 编写面试话术要点：`docs/interview-notes.md`

---

## MVP 后续说明

MVP 阶段到此收口。后续企业化落地能力不继续追加在本文档中，统一进入 `docs/enterprise-plan.md` 管理，包括：

- PostgreSQL 数据持久化
- SQLAlchemy / Alembic 数据模型与迁移
- Redis / Celery 异步任务执行
- 审批历史与审计日志
- 任务工作台与任务详情页
- GitLab 回写记录与失败重试
- 多用户权限与操作人身份
- 历史审查经验库与 pgvector/RAG

---

## 附录：关键技术决策速查

| 决策项 | 结论 | 理由 |
|--------|------|------|
| 编排框架 | LangGraph StateGraph | 原生 interrupt/resume，不造轮子 |
| LLM 调用 | LiteLLM + `openai/` 前缀 | 走 new-api 代理，兼容 OpenAI 协议 |
| LLM 容错 | retry 1 次 + fallback 兜底 | 防止单次 LLM 失败炸掉整个 graph |
| 状态存储 | SqliteSaver（全程使用） | 支持 pending 查询，个人项目不需要分布式 |
| Pending 索引 | server.py 内存 dict | SqliteSaver 无 list_threads API，手动维护索引 |
| 并行 Agent 状态合并 | `Annotated[List, merge_reviews]` reducer | 防并行写入覆盖 |
| Mock 策略 | `ENV` 环境变量切换 mock/prod | fixture 文件 + print 替代真实 API |
| 测试分层 | 单元测试 mock LLM / 集成测试真实 LLM | LLM 输出不确定，格式验证与能力验证分离 |
| 前端 | 纯 HTML/JS，FastAPI serve 静态文件 | 极简，不引入前端框架 |
| GitLab 版本 | 14.6.1 (V4 API) | 已验证 |
| new-api 协议 | OpenAI 兼容 | 已验证 |
