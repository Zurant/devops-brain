import os
import httpx

def get_mr_changes(project_id: str, mr_iid: str) -> str:
    """获取 MR 的真实 Diff 变更"""
    if os.getenv("ENV") == "mock":
        return "def mock_diff():\n    pass"
    
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
