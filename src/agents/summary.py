import json
from src.core.state import ReviewState
from src.tools.llm_client import call_llm
from src.agents import parse_agent_json

PROMPT_TEMPLATE = """
请作为首席技术架构师，汇总以下各个独立专家 Agent 对代码变更的审查结果。
请你仔细阅读每个专家的发现，并输出以下严格合法的 JSON 格式（注意：如果字符串内有换行，请使用 \\n 转义，不要输出原生换行符）：
{
    "final_risk_level": "LOW", // 取所有专家中发现的最高风险等级 (只能是 LOW, MEDIUM, HIGH 之一)
    "summary_report": "简短的中文综合分析总结",
    "final_comment": "适合直接作为 GitLab MR 评论的 Markdown 内容，包含所有具体发现"
}

专家审查结果：
{reviews_json}
"""

def summary_agent(state: ReviewState):
    reviews = state.get("reviews", [])
    reviews_str = json.dumps(reviews, ensure_ascii=False, indent=2)
    prompt = PROMPT_TEMPLATE.replace("{reviews_json}", reviews_str)
    
    response_text = call_llm(prompt, agent_name="summary")
    print("\n--- SUMMARY RAW LLM RESPONSE ---")
    print(response_text)
    print("--------------------------------\n")
    result = parse_agent_json(response_text, "summary")
    
    # 强制兜底
    final_risk = result.get("final_risk_level", "MEDIUM")
    if final_risk not in ["LOW", "MEDIUM", "HIGH"]:
        final_risk = "MEDIUM"
        
    return {
        "final_risk_level": final_risk,
        "summary_report": result.get("summary_report", "分析报告生成失败"),
        "final_comment": result.get("final_comment", "评论生成失败")
    }
