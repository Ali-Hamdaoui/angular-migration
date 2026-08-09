from contextlib import contextmanager

from starlette.requests import Request

from app.api.routes import transformation


def test_transformation_status_is_explicitly_absent_before_g06(monkeypatch):
    class Session:
        def scalar(self, _query):
            return None

    @contextmanager
    def scope():
        yield Session()

    monkeypatch.setattr(transformation, "session_scope", scope)
    monkeypatch.setattr(transformation, "authorize_run", lambda *_args: None)
    request = Request(
        {"type": "http", "method": "GET", "path": "/api/v1/runs/run-1/transformation", "headers": []}
    )

    response = transformation.get_transformation("run-1", request, actor="operator")

    assert response.status_code == 404
    assert b"TRANSFORMATION_NOT_FOUND" in response.body
