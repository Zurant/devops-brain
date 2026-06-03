import json
import re

def parse_agent_json(text: str, agent_name: str) -> dict:
    """提取 markdown JSON 并解析，如果失败则返回 fallback 数据"""
    try:
        # 尝试提取 markdown 代码块中的内容
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            text = match.group(1)
        return json.loads(text.strip())
    except Exception:
        return {
            "agent": agent_name,
            "issues": [],
            "risk": "MEDIUM",
            "error": "Failed to parse JSON"
        }
