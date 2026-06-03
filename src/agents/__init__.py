import json
import re

def parse_agent_json(text: str, agent_name: str) -> dict:
    """提取 markdown JSON 并解析，如果失败则返回 fallback 数据"""
    try:
        # 尝试提取 markdown
        text = text.strip()
        if not (text.startswith("{") and text.endswith("}")):
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
            if match:
                text = match.group(1).strip()
        return json.loads(text, strict=False)
    except Exception as e:
        print(f"JSON Parse Error: {e}")
        return {
            "agent": agent_name,
            "issues": [],
            "risk": "MEDIUM",
            "error": "Failed to parse JSON"
        }
