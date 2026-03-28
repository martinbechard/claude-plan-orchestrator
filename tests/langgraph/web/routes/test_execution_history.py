# tests/langgraph/web/routes/test_execution_history.py
# Unit tests for the execution history API endpoints (D6).
# Design: docs/plans/2026-03-28-71-execution-history-redesign-design.md

"""Unit tests for langgraph_pipeline.web.routes.execution_history.

Tests the JSON API endpoint GET /api/execution-tree/{run_id} and the HTML
page shell GET /execution-history/{run_id}. Uses FastAPI TestClient with
a temp-dir SQLite-backed TracingProxy.
"""

import json
import uuid

import pytest
from fastapi.testclient import TestClient

import langgraph_pipeline.web.proxy as proxy_module
from langgraph_pipeline.web.proxy import TracingProxy
from langgraph_pipeline.web.server import create_app

# ─── Constants ────────────────────────────────────────────────────────────────

HTTP_OK = 200
HTTP_NOT_FOUND = 404

# Generate unique run IDs per test session to avoid collisions.
ROOT_RUN_ID = str(uuid.uuid4())
CHILD_RUN_ID_1 = str(uuid.uuid4())
CHILD_RUN_ID_2 = str(uuid.uuid4())
GRANDCHILD_RUN_ID = str(uuid.uuid4())


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def proxy(tmp_path):
    """Create a TracingProxy backed by a temp-dir SQLite DB."""
    db_path = str(tmp_path / "test-traces.db")
    return TracingProxy({"db_path": db_path, "forward_to_langsmith": False})


@pytest.fixture()
def client(tmp_path, proxy):
    """FastAPI TestClient with proxy singleton wired to the test DB."""
    old = proxy_module._proxy_instance
    proxy_module._proxy_instance = proxy
    app = create_app(config={
        "web": {"proxy": {"db_path": str(tmp_path / "test-traces.db")}},
    })
    # Restore our fixture proxy after create_app replaces the singleton
    proxy_module._proxy_instance = proxy
    yield TestClient(app)
    proxy_module._proxy_instance = old


def _record_run(
    proxy: TracingProxy,
    run_id: str,
    parent_run_id: str = None,
    name: str = "test-node",
    metadata: dict = None,
    start_time: str = "2026-03-28T10:00:00",
    end_time: str = "2026-03-28T10:01:00",
    model: str = "",
    inputs: dict = None,
    outputs: dict = None,
    error: str = None,
) -> None:
    """Helper to insert a trace row into the test DB."""
    proxy.record_run(
        run_id=run_id,
        parent_run_id=parent_run_id,
        name=name,
        inputs=inputs,
        outputs=outputs,
        metadata=metadata,
        error=error,
        start_time=start_time,
        end_time=end_time,
    )
    if model:
        proxy.propagate_model_to_root(run_id, model)


def _seed_tree(proxy: TracingProxy) -> None:
    """Seed a three-level tree: root -> 2 children -> 1 grandchild."""
    _record_run(proxy, ROOT_RUN_ID, name="LangGraph")
    _record_run(
        proxy, CHILD_RUN_ID_1,
        parent_run_id=ROOT_RUN_ID,
        name="intake",
        start_time="2026-03-28T10:00:01",
        end_time="2026-03-28T10:02:30",
        metadata={"item_slug": "71-redesign", "total_cost_usd": 0.045},
    )
    _record_run(
        proxy, CHILD_RUN_ID_2,
        parent_run_id=ROOT_RUN_ID,
        name="execute_task",
        start_time="2026-03-28T10:02:31",
        end_time="2026-03-28T10:05:00",
        metadata={
            "total_cost_usd": 0.0,
            "input_tokens": 15000,
            "output_tokens": 4500,
        },
    )
    _record_run(
        proxy, GRANDCHILD_RUN_ID,
        parent_run_id=CHILD_RUN_ID_2,
        name="agent_session",
        start_time="2026-03-28T10:02:32",
        end_time="2026-03-28T10:04:59",
        model="claude-sonnet-4-6",
        metadata={"total_cost_usd": 0.123, "input_tokens": 12000, "output_tokens": 3800},
    )


# ─── HTML Page Shell Tests ───────────────────────────────────────────────────


class TestExecutionHistoryPage:
    """Tests for GET /execution-history/{run_id}."""

    def test_returns_html_page(self, client, proxy):
        """The page shell returns 200 with the run_id embedded."""
        _record_run(proxy, ROOT_RUN_ID, name="LangGraph")
        resp = client.get(f"/execution-history/{ROOT_RUN_ID}")
        assert resp.status_code == HTTP_OK
        assert "text/html" in resp.headers["content-type"]
        assert ROOT_RUN_ID[:8] in resp.text

    def test_returns_404_for_missing_run(self, client):
        """A non-existent run_id returns 404."""
        missing_id = str(uuid.uuid4())
        resp = client.get(f"/execution-history/{missing_id}")
        assert resp.status_code == HTTP_NOT_FOUND

    def test_returns_404_when_proxy_disabled(self, tmp_path):
        """When the proxy is None, the endpoint returns 404."""
        old = proxy_module._proxy_instance
        proxy_module._proxy_instance = None
        try:
            app = create_app(config=None)
            # create_app inits a proxy, so force it None
            proxy_module._proxy_instance = None
            test_client = TestClient(app, raise_server_exceptions=False)
            resp = test_client.get(f"/execution-history/{str(uuid.uuid4())}")
            assert resp.status_code == HTTP_NOT_FOUND
        finally:
            proxy_module._proxy_instance = old


# ─── JSON API Tests ──────────────────────────────────────────────────────────


class TestExecutionTreeAPI:
    """Tests for GET /api/execution-tree/{run_id}."""

    def test_returns_tree_structure(self, client, proxy):
        """The API returns a tree with the correct nesting structure."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        assert resp.status_code == HTTP_OK
        data = resp.json()

        assert data["run_id"] == ROOT_RUN_ID
        tree = data["tree"]
        assert len(tree) == 2  # two direct children of root

    def test_node_fields_present(self, client, proxy):
        """Each tree node includes all required D6 fields."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()
        node = data["tree"][0]

        required_fields = [
            "run_id", "name", "display_name", "node_type", "status",
            "duration", "cost", "model", "token_count",
            "inputs_json", "outputs_json", "metadata_json", "children",
        ]
        for field_name in required_fields:
            assert field_name in node, f"Missing field: {field_name}"

    def test_nested_children(self, client, proxy):
        """The grandchild appears nested under its parent in the tree."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        # Find the execute_task node (parent of grandchild)
        execute_node = next(
            n for n in data["tree"] if n["name"] == "execute_task"
        )
        assert len(execute_node["children"]) == 1
        grandchild = execute_node["children"][0]
        assert grandchild["run_id"] == GRANDCHILD_RUN_ID
        assert grandchild["name"] == "agent_session"

    def test_cost_aggregation(self, client, proxy):
        """Parent node cost includes child cost (D4 aggregation)."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        execute_node = next(
            n for n in data["tree"] if n["name"] == "execute_task"
        )
        # execute_task has own cost 0.0, grandchild has cost 0.123
        assert execute_node["cost"] == pytest.approx(0.123, abs=0.001)

    def test_token_count_from_metadata(self, client, proxy):
        """Nodes with token metadata report correct token_count."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        execute_node = next(
            n for n in data["tree"] if n["name"] == "execute_task"
        )
        # execute_task has input_tokens=15000, output_tokens=4500
        assert execute_node["token_count"] == 19500

        grandchild = execute_node["children"][0]
        # grandchild has input_tokens=12000, output_tokens=3800
        assert grandchild["token_count"] == 15800

    def test_display_name_resolution(self, client, proxy):
        """Nodes resolve display_name via D2 three-tier fallback."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        intake_node = next(
            n for n in data["tree"] if n["name"] == "intake"
        )
        # intake has metadata item_slug "71-redesign", but name is "intake"
        # which is a valid non-LangGraph name, so display_name = "intake"
        assert intake_node["display_name"] == "intake"

    def test_node_status(self, client, proxy):
        """Completed nodes have status 'success'."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        for node in data["tree"]:
            assert node["status"] == "success"

    def test_empty_tree_for_root_only(self, client, proxy):
        """A root with no children returns an empty tree array."""
        lone_run_id = str(uuid.uuid4())
        _record_run(proxy, lone_run_id, name="lonely-root")
        resp = client.get(f"/api/execution-tree/{lone_run_id}")
        data = resp.json()

        assert data["run_id"] == lone_run_id
        assert data["tree"] == []

    def test_returns_404_for_missing_run(self, client):
        """A non-existent run_id returns 404."""
        missing_id = str(uuid.uuid4())
        resp = client.get(f"/api/execution-tree/{missing_id}")
        assert resp.status_code == HTTP_NOT_FOUND

    def test_duration_populated(self, client, proxy):
        """Nodes with start/end times have non-zero duration."""
        _seed_tree(proxy)
        resp = client.get(f"/api/execution-tree/{ROOT_RUN_ID}")
        data = resp.json()

        intake_node = next(
            n for n in data["tree"] if n["name"] == "intake"
        )
        # intake: 10:00:01 to 10:02:30 = 149 seconds
        assert intake_node["duration"] == pytest.approx(149.0, abs=1.0)

    def test_model_field(self, client, proxy):
        """Agent nodes carry the model field when set in the DB."""
        model_root_id = str(uuid.uuid4())
        model_child_id = str(uuid.uuid4())
        _record_run(proxy, model_root_id, name="root-with-model")
        _record_run(
            proxy, model_child_id,
            parent_run_id=model_root_id,
            name="llm-call",
        )
        # Directly set the model column on the child via SQL
        with proxy._connect() as conn:
            conn.execute(
                "UPDATE traces SET model = ? WHERE run_id = ?",
                ["claude-sonnet-4-6", model_child_id],
            )
        resp = client.get(f"/api/execution-tree/{model_root_id}")
        data = resp.json()

        child_node = data["tree"][0]
        assert child_node["model"] == "claude-sonnet-4-6"

    def test_error_node_status(self, client, proxy):
        """A node with an error field has status 'error'."""
        error_root_id = str(uuid.uuid4())
        error_child_id = str(uuid.uuid4())
        _record_run(proxy, error_root_id, name="error-root")
        _record_run(
            proxy, error_child_id,
            parent_run_id=error_root_id,
            name="failing-step",
            error="Something broke",
            end_time="2026-03-28T10:01:00",
        )
        resp = client.get(f"/api/execution-tree/{error_root_id}")
        data = resp.json()
        assert data["tree"][0]["status"] == "error"
