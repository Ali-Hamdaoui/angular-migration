"""Tests for F28 retrieval benchmark."""

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.main import app
from app.repositories.retrieval_benchmark_models import RetrievalBenchmarkModel
from app.repositories.session import session_scope
from app.services.retrieval_benchmark_fixtures import benchmark_fixture_set, build_fixture_workspace
from app.services.retrieval_benchmark_service import RetrievalBenchmarkError, RetrievalBenchmarkService

client = TestClient(app)


def _root() -> Path:
    root = Path("/tmp") / f"bench-{uuid4().hex[:8]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def test_fixture_set_spans_11_to_21():
    cases = benchmark_fixture_set()
    majors = {case.source_major for case in cases}
    assert majors == set(range(11, 21))
    assert len(cases) >= 27  # 3 kinds x 10 majors


def test_fixture_generation_is_deterministic():
    root = _root()
    cases = benchmark_fixture_set()
    first = build_fixture_workspace(root, cases[0])
    second = build_fixture_workspace(root, cases[0])
    for relative in ("app.component.ts", "app.component.html", "data.service.ts"):
        assert (first / relative).read_text() == (second / relative).read_text()


def test_benchmark_run_records_quality_and_latency():
    root = _root()
    service = RetrievalBenchmarkService()
    report = service.run_benchmark(workspace_root=root)
    assert report.deterministic is True
    assert report.mean_precision >= 0.0
    assert report.mean_recall >= 0.0
    assert 0.0 <= report.mean_f1 <= 1.0
    assert report.p95_latency_ms >= 0.0
    assert report.checksum.startswith("sha256:")
    assert report.case_results
    for result in report.case_results:
        assert 0.0 <= result.precision <= 1.0
        assert 0.0 <= result.recall <= 1.0
        assert result.budget_utilization <= 1.0
        assert result.retrieved_files


def test_benchmark_report_is_reproducible():
    root = _root()
    service = RetrievalBenchmarkService()
    first = service.run_benchmark(workspace_root=root)
    second = service.run_benchmark(workspace_root=root)
    assert first.checksum == second.checksum
    assert first.mean_precision == second.mean_precision
    assert first.case_results[0].retrieved_files == second.case_results[0].retrieved_files


def test_benchmark_precision_and_recall_against_ground_truth():
    from app.domain.retrieval_benchmark import RetrievalBenchmarkCase

    root = _root()
    case = RetrievalBenchmarkCase(
        case_id="fixture-15-component", fixture_kind="component", source_major=15,
        symbols=("App15Component", "Data15Service", "broken"),
        template_selectors=("app-15",),
        budget=6000,
        relevant_files=("app.component.ts", "app.component.html", "data.service.ts", "app.module.ts"),
    )
    service = RetrievalBenchmarkService()
    result = service._run_case(root, case)
    assert result.precision == 1.0  # every retrieved file is relevant
    assert result.recall == 1.0  # all relevant files retrieved
    assert result.f1 == 1.0
    assert set(result.retrieved_files) == {"app.component.ts", "app.component.html", "data.service.ts", "app.module.ts"}


def test_benchmark_missing_root_raises():
    service = RetrievalBenchmarkService()
    try:
        service.run_benchmark(workspace_root=Path("/tmp/does-not-exist-bench"))
        assert False, "expected WORKSPACE_ROOT_MISSING"
    except RetrievalBenchmarkError as exc:
        assert exc.code == "WORKSPACE_ROOT_MISSING"


def test_persist_and_get_report():
    root = _root()
    service = RetrievalBenchmarkService()
    report = service.run_benchmark(workspace_root=root)
    persisted = service.persist_report(report)
    with session_scope() as session:
        from sqlalchemy import select

        row = session.scalar(select(RetrievalBenchmarkModel).where(RetrievalBenchmarkModel.id == persisted.id))
        assert row is not None
        assert row.checksum == report.checksum
        assert row.fixture_set == "11-to-21"
        assert len(row.case_results) == len(report.case_results)


def test_persist_is_idempotent_by_id():
    root = _root()
    service = RetrievalBenchmarkService()
    report = service.run_benchmark(workspace_root=root)
    first = service.persist_report(report)
    again = service.persist_report(report)
    assert again.id == first.id
    with session_scope() as session:
        from sqlalchemy import select

        count = len(session.scalars(select(RetrievalBenchmarkModel)).all())
        assert count == 1


def test_api_run_and_list():
    from app.core.config import get_settings

    get_settings.cache_clear()
    allowed = get_settings().allowed_source_roots[0] if get_settings().allowed_source_roots else Path("/tmp")
    root = allowed / "overnight-v2" / f"F28-api-{uuid4().hex[:6]}"
    root.mkdir(parents=True, exist_ok=True)
    response = client.post("/retrieval-benchmark/run", json={"workspace_root": str(root)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["fixture_set"] == "11-to-21"
    assert body["checksum"].startswith("sha256:")
    assert body["mean_precision"] >= 0.0
    assert body["case_results"]

    listed = client.get("/retrieval-benchmark")
    assert listed.status_code == 200
    assert any(b["benchmark_id"] == body["benchmark_id"] for b in listed.json()["benchmarks"])

    fetched = client.get(f"/retrieval-benchmark/{body['benchmark_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["checksum"] == body["checksum"]
