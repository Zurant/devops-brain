import os

def get_mr_changes(project_id: str, mr_iid: str) -> str:
    """获取 MR 的 Diff 变更"""
    if os.getenv("ENV") == "mock":
        return "def mock_diff():\n    pass"
    
    # Prod TODO:
    # url = f"{os.getenv('GITLAB_URL')}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/changes"
    return "def mock_diff():\n    pass"

def post_mr_comment(project_id: str, mr_iid: str, comment: str) -> bool:
    """向 GitLab MR 发送评论"""
    if os.getenv("ENV", "mock") == "mock":
        print(f"\n[MOCK] 成功将评论发送至 GitLab MR ({project_id}/{mr_iid}):")
        print(comment)
        print("="*40)
        return True
    
    # Prod TODO:
    # import httpx
    # url = f"{os.getenv('GITLAB_URL')}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
    # headers = {"PRIVATE-TOKEN": os.getenv("GITLAB_TOKEN")}
    # httpx.post(url, headers=headers, json={"body": comment})
    return True
