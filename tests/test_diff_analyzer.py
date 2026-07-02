from src.models import ReviewDiffFile, ReviewTask
from src.services.diff_analyzer import analyze_diff, save_diff_analysis, summarize_diff_analysis
from tests.test_approval_api import build_test_session


def test_analyze_diff_extracts_file_metrics_and_risk_domains():
    diff = """# File: src/api/auth.py
@@ -1,2 +1,4 @@
 from fastapi import APIRouter
+password = request.json()["password"]
+token = create_jwt(password)
-old_handler()
"""

    files = analyze_diff(diff)

    assert len(files) == 1
    item = files[0]
    assert item.file_path == "src/api/auth.py"
    assert item.language == "python"
    assert item.extension == ".py"
    assert item.directory == "src/api"
    assert item.change_type == "modified"
    assert item.additions == 2
    assert item.deletions == 1
    assert item.total_changes == 3
    assert "api" in item.risk_domains
    assert "security" in item.risk_domains


def test_analyze_diff_recognizes_database_and_config_changes():
    diff = """# File: migrations/versions/0008_add_user_table.sql
@@ -0,0 +1,2 @@
+ALTER TABLE users ADD COLUMN password_hash text;
+CREATE INDEX idx_users_email ON users(email);

# File: docker-compose.yml
@@ -1 +1,2 @@
+services:
+  postgres:
"""

    files = analyze_diff(diff)
    summary = summarize_diff_analysis(files)

    assert len(files) == 2
    assert files[0].language == "sql"
    assert "database" in files[0].risk_domains
    assert files[1].language == "yaml"
    assert "ci_cd" in files[1].risk_domains
    assert "configuration" in files[1].risk_domains
    assert summary["file_count"] == 2
    assert summary["total_additions"] == 4
    assert summary["risk_domains"] == ["ci_cd", "configuration", "database", "security"]


def test_save_diff_analysis_replaces_existing_rows():
    session_factory = build_test_session()
    db = session_factory()
    task = ReviewTask(thread_id="diff-thread", project_id="1234", mr_iid="42", status="running")
    db.add(task)
    db.commit()
    db.refresh(task)

    save_diff_analysis(db, task, "# File: src/old.py\n@@ -1 +1 @@\n-old\n+new")
    save_diff_analysis(db, task, "# File: src/new.py\n@@ -1 +1 @@\n-old\n+new")

    rows = db.query(ReviewDiffFile).filter_by(task_id=task.id).all()
    assert len(rows) == 1
    assert rows[0].file_path == "src/new.py"
    assert rows[0].analysis_metadata["mr_summary"]["file_count"] == 1
    db.close()
