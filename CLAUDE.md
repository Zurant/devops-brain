# Claude Code / AI Developer Guidelines

## 0. 交互行为准则（最高优先级）
1. **中文优先**：所有回答使用中文，所有生成的文档、注释、commit message 均使用中文。
2. **先建议，再写代码**：每次收到任务后，先给出分析和建议，经人工确认后再生成或修改代码。禁止未经确认直接动手写。
3. **禁止未经验证直接给出最终实现**：任何方案都必须先由人工审核，不得跳过验证环节一步到位。

## 1. Project Context
This is **DevOps Brain**, a Multi-Agent Code Review system using LangGraph and FastAPI. 
Target: Internal GitLab Merge Requests.

**LiteLLM Model definitions:**
- 开发/测试 (快速分类): `openai/gemini-3.5-flash` (通过 new-api 代理)
- 复杂推理 (专家审核): `openai/deepseek-chat` (或其它强力模型)
- 代理基础地址：从 `.env` 中的 `NEW_API_BASE_URL` 读取 (对应 litellm 的 `api_base`)。这样可避免模型参数猜测错误。

## 2. Tech Stack & Strict Rules
- **LangGraph**: Use `StateGraph`. State must ALWAYS strictly follow `src/core/state.py`. Do NOT alter the state schema without explicit permission.
- **FastAPI**: Used for GitLab webhooks and the HITL manual approval endpoint.
- **SQLite**: Use LangGraph's built-in `SqliteSaver` (or `MemorySaver` for testing) for checkpointing (interrupt/resume). **NO Postgres/Redis**.
- **Strictly No ORMs**: Do not introduce SQLAlchemy or similar heavy frameworks.
- **Testing First**: Use `tests/fixtures/mock_mr_payload.json` for offline testing. Do not call the real GitLab API until the local graph flow is perfect.

## 3. Development Plan
**完整的分阶段开发计划在 `docs/dev-plan.md`**，那是唯一权威的开发计划文档。

**如何判断当前进度**：阅读 `docs/dev-plan.md`，对照其中的目录结构检查哪些文件已存在、哪些还未创建，从而推断当前所处阶段。不要依赖任何硬编码的进度标记。

**核心规则**：
- 必须按 Phase 顺序执行，严禁跨阶段开发。
- 每个 Phase 末尾有明确的 **Done When** 判定条件（包含具体的命令和测试用例）。
- 达到判定条件后**必须停止**，等待人工审核后才能进入下一阶段。

## 4. Useful Commands
- Install dependencies: `poetry install`
- Run dev server: `poetry run uvicorn src.api.server:app --reload`
