"""Shared fixtures."""

from __future__ import annotations

import importlib
import os
import sys

import pytest


@pytest.fixture
def app_module(monkeypatch):
    """`src.app`, imported offline: no polling thread or warmup (AITO_SKIP_STARTUP_WARMUP), a placeholder Aito.

    Importing the app loads the repository's dotenv file into `os.environ`; that is undone afterwards, or a later
    test would see another test's configuration (the Ask model name, for one)."""
    saved = dict(os.environ)
    monkeypatch.setenv("AITO_SKIP_STARTUP_WARMUP", "1")
    monkeypatch.setenv("AITO_API_URL", "https://example.invalid")
    monkeypatch.setenv("AITO_API_KEY", "not-a-real-key")
    sys.modules.pop("src.app", None)
    module = importlib.import_module("src.app")
    yield module
    sys.modules.pop("src.app", None)
    os.environ.clear()
    os.environ.update(saved)
