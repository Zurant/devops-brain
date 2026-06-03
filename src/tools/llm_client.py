import os
import time
import json
import litellm

def call_llm(prompt: str, agent_name: str = "unknown", model: str = None) -> str:
    """
    统一的 LLM 调用入口。
    - model: 默认从 .env 的 MODEL_NAME 读取
    - api_base: 从 .env 的 NEW_API_BASE_URL 读取
    - api_key: 从 .env 的 NEW_API_KEY 读取
    必须使用 litellm.completion()，model 参数格式为 "openai/{model_name}"。
    """
    if model is None:
        model = os.getenv("MODEL_NAME", "gpt-3.5-turbo")
    
    # 确保使用 openai/ 前缀
    if not model.startswith("openai/"):
        model = f"openai/{model}"
        
    api_base = os.getenv("NEW_API_BASE_URL")
    api_key = os.getenv("NEW_API_KEY")

    def _fallback():
        return json.dumps({
            "agent": agent_name,
            "issues": [],
            "risk": "MEDIUM",
            "error": "LLM call failed"
        })

    try:
        response = litellm.completion(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            api_base=api_base,
            api_key=api_key
        )
        return response.choices[0].message.content
    except Exception as e:
        # Retry 1 次
        time.sleep(2)
        try:
            response = litellm.completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                api_base=api_base,
                api_key=api_key
            )
            return response.choices[0].message.content
        except Exception:
            return _fallback()
