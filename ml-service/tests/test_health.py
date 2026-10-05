import json

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


def _client(settings: Settings) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_health_without_models(tmp_path):
    response = _client(Settings(model_dir=tmp_path / "missing")).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UP"
    assert body["explanation_provider"] == "template"
    assert body["models"] == []


def test_health_lists_exported_model_cards(tmp_path):
    card_dir = tmp_path / "news_sentiment" / "1"
    card_dir.mkdir(parents=True)
    (card_dir / "model_card.json").write_text(json.dumps({"name": "news_sentiment", "version": "1"}))
    (tmp_path / "broken" / "1").mkdir(parents=True)
    (tmp_path / "broken" / "1" / "model_card.json").write_text("{not json")

    body = _client(Settings(model_dir=tmp_path)).get("/health").json()

    assert body["models"] == [{"name": "news_sentiment", "version": "1"}]
