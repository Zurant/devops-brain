from src.models import ReviewPackage, ReviewPlan, ReviewTask
from src.services.diff_analyzer import save_diff_analysis
from src.services.review_planner import build_review_plan, save_review_plan
from tests.test_approval_api import build_test_session


def make_plan(diff: str):
    session_factory = build_test_session()
    db = session_factory()
    task = ReviewTask(thread_id="planner-thread", project_id="1234", mr_iid="42", status="running")
    db.add(task)
    db.commit()
    db.refresh(task)
    diff_files = save_diff_analysis(db, task, diff)
    draft = build_review_plan(diff_files)
    db.close()
    return draft


def test_business_change_uses_quality_and_architecture():
    draft = make_plan(
        """# File: src/order/service.py
@@ -1 +1,2 @@
+def create_order():
+    return repository.save()
"""
    )

    assert draft.mr_type == "small_change"
    assert draft.approval_policy == "auto_allowed"
    assert draft.package_count == 1
    assert draft.packages[0].selected_agents == ["architecture", "quality"]


def test_security_change_selects_security_agent_and_forces_human():
    draft = make_plan(
        """# File: src/auth.py
@@ -1 +1,3 @@
+password = request.json()["password"]
+token = create_jwt(password)
+return token
"""
    )

    assert draft.mr_type == "security_sensitive"
    assert draft.approval_policy == "force_human"
    assert draft.packages[0].package_key == "risk_domain:security"
    assert draft.packages[0].selected_agents == ["quality", "security"]
    assert draft.packages[0].requires_human is True


def test_database_change_selects_architecture_and_quality():
    draft = make_plan(
        """# File: migrations/versions/0009_add_order_status.sql
@@ -0,0 +1,2 @@
+ALTER TABLE orders ADD COLUMN status text;
+CREATE INDEX idx_orders_status ON orders(status);
"""
    )

    assert draft.mr_type == "database_change"
    assert draft.approval_policy == "force_human"
    assert draft.packages[0].package_key == "risk_domain:database"
    assert draft.packages[0].selected_agents == ["architecture", "quality"]


def test_large_mr_splits_by_directory_and_requires_human():
    diff = "\n\n".join(
        f"# File: src/module_{index}/service.py\n@@ -1 +1,51 @@\n" + "\n".join(f"+line_{line}" for line in range(51))
        for index in range(21)
    )

    draft = make_plan(diff)

    assert draft.mr_type == "large_mr"
    assert draft.review_strategy == "split_by_directory_and_risk"
    assert draft.approval_policy == "force_human"
    assert draft.package_count == 1
    assert draft.packages[0].package_key == "directory:src"
    assert draft.packages[0].requires_human is True


def test_save_review_plan_replaces_existing_plan_and_packages():
    session_factory = build_test_session()
    db = session_factory()
    task = ReviewTask(thread_id="save-plan-thread", project_id="1234", mr_iid="42", status="running")
    db.add(task)
    db.commit()
    db.refresh(task)

    save_diff_analysis(db, task, "# File: src/a.py\n@@ -1 +1 @@\n-old\n+new")
    save_review_plan(db, task)
    save_review_plan(db, task)

    plans = db.query(ReviewPlan).filter_by(task_id=task.id).all()
    packages = db.query(ReviewPackage).filter_by(task_id=task.id).all()
    assert len(plans) == 1
    assert len(packages) == 1
    assert plans[0].package_count == 1
    assert packages[0].file_paths == ["src/a.py"]
    db.close()
