"""Scaffold smoke tests.

These exist to catch the obvious "I broke import wiring" failures
before pushing. As views land, real per-service tests join them
under `tests/test_<service>.py`.
"""

from src import config


def test_load_config_reads_env(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://example.aito.app")
    monkeypatch.setenv("AITO_API_KEY", "test-key")
    monkeypatch.delenv("PUBLIC_DEMO", raising=False)

    cfg = config.load_config(use_dotenv=False)

    assert cfg.aito_api_url == "https://example.aito.app"
    assert cfg.aito_api_key == "test-key"
    assert cfg.public_demo is False


def test_load_config_strips_trailing_slash(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://example.aito.app/")
    monkeypatch.setenv("AITO_API_KEY", "test-key")
    cfg = config.load_config(use_dotenv=False)
    assert cfg.aito_api_url == "https://example.aito.app"


def test_load_config_raises_when_credentials_missing(monkeypatch):
    monkeypatch.delenv("AITO_API_URL", raising=False)
    monkeypatch.delenv("AITO_API_KEY", raising=False)
    try:
        config.load_config(use_dotenv=False)
    except ValueError as exc:
        assert "AITO_API_URL" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_public_demo_flag_truthy(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://example.aito.app")
    monkeypatch.setenv("AITO_API_KEY", "test-key")
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    cfg = config.load_config(use_dotenv=False)
    assert cfg.public_demo is True
