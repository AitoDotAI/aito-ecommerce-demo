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


def test_explicit_env_var_wins_over_dotenv(monkeypatch, tmp_path):
    # The 2026-09-20 incident: a loader run with AITO_API_URL pointing at
    # localhost had it silently replaced by the file's production URL.
    monkeypatch.setattr(config, "_PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "AITO_API_URL=https://shared.aito.ai/db/aito-ecommerce-demo\n"
        "AITO_API_KEY=file-key\n")
    monkeypatch.setenv("AITO_API_URL", "http://localhost:8080")
    monkeypatch.setenv("AITO_API_KEY", "")  # blank counts as unset

    cfg = config.load_config()

    assert cfg.aito_api_url == "http://localhost:8080"
    assert cfg.aito_api_key == "file-key"


def test_do_script_lets_explicit_env_win_over_dotenv_files(tmp_path):
    """`./do` sources .env and .env.local itself, before Python runs."""
    import os
    import subprocess
    from pathlib import Path

    do = (Path(__file__).resolve().parent.parent / "do").read_text()
    helper = do[do.index("_source_env_files() {"):]
    helper = helper[:helper.index("\n}\n") + 3]
    (tmp_path / "base").write_text("AITO_API_URL=https://prod\nAITO_API_KEY=base-key\nX=base\n")
    (tmp_path / "local").write_text("X=local\n")
    script = helper + '_source_env_files "$1/base" "$1/local" "$1/missing"\n' \
        'echo "$AITO_API_URL $AITO_API_KEY $X"\n'
    env = {k: v for k, v in os.environ.items() if k not in ("AITO_API_URL", "X")}
    env.update(AITO_API_URL="http://localhost:8080", AITO_API_KEY="")

    out = subprocess.run(["bash", "-euo", "pipefail", "-c", script, "_", str(tmp_path)],
                         env=env, capture_output=True, text=True, check=True).stdout

    assert out.split() == ["http://localhost:8080", "base-key", "local"]


def test_public_demo_flag_truthy(monkeypatch):
    monkeypatch.setenv("AITO_API_URL", "https://example.aito.app")
    monkeypatch.setenv("AITO_API_KEY", "test-key")
    monkeypatch.setenv("PUBLIC_DEMO", "1")
    cfg = config.load_config(use_dotenv=False)
    assert cfg.public_demo is True


# ── Provenance: /version ─────────────────────────────────────────────


def test_build_info_prefers_build_sha_and_reports_it_as_pinned(monkeypatch):
    """BUILD_SHA is authoritative — a deployed image has no `.git`.

    `pinned` exists so a reader does not have to infer provenance from a
    null sha: false means the build cannot say where it came from, which
    on a deployment is itself the finding.
    """
    from src import build_info as bi

    bi.build_info.cache_clear()
    monkeypatch.setenv("BUILD_SHA", "abc123def4567890")
    info = bi.build_info()
    assert info["sha"] == "abc123def456"       # truncated to 12
    assert info["source"] == "BUILD_SHA"
    assert info["dirty"] is None               # unknowable from a sha alone
    bi.build_info.cache_clear()


def test_build_info_falls_back_to_git_for_local_dev(monkeypatch):
    """The fallback is for a working tree, and must never raise."""
    from src import build_info as bi

    bi.build_info.cache_clear()
    monkeypatch.delenv("BUILD_SHA", raising=False)
    info = bi.build_info()
    assert info["source"] in ("git", "unknown")
    if info["source"] == "git":
        assert info["sha"] and len(info["sha"]) == 12
    bi.build_info.cache_clear()
