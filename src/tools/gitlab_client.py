import os
import json
from pathlib import Path
import httpx

def extract_diff_from_payload(payload: dict) -> str:
    """从 GitLab MR Webhook payload 中提取 diff 内容"""
    changes = payload.get("changes") or []
    diffs = []
    for change in changes:
        diff = change.get("diff", "")
        if not diff:
            continue
        path = change.get("new_path") or change.get("old_path") or "unknown"
        diffs.append(f"# File: {path}\n{diff}")
    return "\n\n".join(diffs)

def _load_mock_fixture_diff() -> str:
    """mock 模式下读取本地 fixture，保证离线 Demo 使用真实样例 diff"""
    fixture_path = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "mock_mr_payload.json"
    with fixture_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    return extract_diff_from_payload(payload)

def get_mr_changes(project_id: str, mr_iid: str, payload: dict | None = None) -> str:
    """获取 MR 的真实 Diff 变更"""
    if payload:
        diff = extract_diff_from_payload(payload)
        if diff:
            return diff

    if os.getenv("ENV") == "mock":
        return _load_mock_fixture_diff()
    
    url = f"{os.getenv('GITLAB_URL')}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes"
    headers = {"PRIVATE-TOKEN": os.getenv("GITLAB_TOKEN")}
    response = httpx.get(url, headers=headers)
    response.raise_for_status()
    
    changes = response.json().get("changes", [])
    diffs = [c.get("diff", "") for c in changes]
    return "\n".join(diffs)

def post_mr_comment(project_id: str, mr_iid: str, comment: str) -> bool:
    """向真实的 GitLab MR 发送评论"""
    if os.getenv("ENV", "mock") == "mock":
        print(f"\n[MOCK] 成功将评论发送至 GitLab MR ({project_id}/{mr_iid}):")
        print(comment)
        print("="*40)
        return True
    
    url = f"{os.getenv('GITLAB_URL')}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
    headers = {"PRIVATE-TOKEN": os.getenv("GITLAB_TOKEN")}
    response = httpx.post(url, headers=headers, json={"body": comment})
    response.raise_for_status()
    return True
