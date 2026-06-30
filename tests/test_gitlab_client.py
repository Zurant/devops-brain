import json

from src.tools.gitlab_client import extract_diff_from_payload, get_mr_changes


def test_extract_diff_from_payload_includes_file_path_and_diff():
    payload = {
        "changes": [
            {
                "new_path": "src/api.py",
                "diff": "@@ -1 +1 @@\n-print('old')\n+print('new')",
            }
        ]
    }

    diff = extract_diff_from_payload(payload)

    assert "# File: src/api.py" in diff
    assert "+print('new')" in diff


def test_get_mr_changes_prefers_payload_diff(monkeypatch):
    monkeypatch.setenv("ENV", "mock")
    payload = {
        "changes": [
            {
                "new_path": "src/service.py",
                "diff": "+return db.query(f'SELECT * FROM users WHERE id = {user_id}')",
            }
        ]
    }

    diff = get_mr_changes("1234", "42", payload=payload)

    assert "src/service.py" in diff
    assert "SELECT * FROM users" in diff


def test_get_mr_changes_mock_mode_reads_fixture(monkeypatch):
    monkeypatch.setenv("ENV", "mock")

    diff = get_mr_changes("1234", "42")

    assert "src/api.py" in diff
    assert "SELECT * FROM users WHERE id" in diff
