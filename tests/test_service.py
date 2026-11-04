"""The service API without a real model: endpoints, headers, validation, FAULT_INJECT."""
import importlib
import json
import os

import pytest
from fastapi.testclient import TestClient

os.environ.update(MODEL_URI="s3://models/v1", MODEL_VERSION="v1",
                  S3_ENDPOINT="http://localhost:1", MAX_NEW_TOKENS="64")


class FakeStudent:
    def __init__(self, raw):
        self.raw = raw

    def raw_output(self, text):
        return self.raw


@pytest.fixture
def app_module(monkeypatch):
    import app
    importlib.reload(app)
    monkeypatch.setattr(app, "load_in_background", lambda: None)  # no download in tests
    return app


GOOD = json.dumps({"intent": "weather_query", "date": None, "time": None, "place": "london"})


def test_not_ready_until_model_loaded(app_module):
    client = TestClient(app_module.app)
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 503
    app_module.state["student"] = FakeStudent(GOOD)
    assert client.get("/readyz").status_code == 200


def test_parse_returns_only_the_object_with_headers(app_module):
    app_module.state["student"] = FakeStudent(GOOD)
    r = TestClient(app_module.app).post("/parse", json={"text": "weather in london"})
    assert r.status_code == 200
    assert r.json() == json.loads(GOOD)
    assert r.headers["X-Model-Version"] == "v1" and r.headers["X-Served-By"]


@pytest.mark.parametrize("raw", ['{"intent": "weather_query"', GOOD.replace("weather_query", "music"),
                                 '{"intent": "alarm_set", "date": null, "time": null}'])
def test_invalid_output_gives_500(app_module, raw):
    app_module.state["student"] = FakeStudent(raw)
    r = TestClient(app_module.app).post("/parse", json={"text": "x"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_fault_inject(app_module, monkeypatch):
    app_module.state["student"] = FakeStudent(GOOD)
    monkeypatch.setenv("FAULT_INJECT", "1")
    r = TestClient(app_module.app).post("/parse", json={"text": "weather in london"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}
