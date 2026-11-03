"""Verifica configuração e execução instalada, sem rede nem anexos."""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest import MonkeyPatch

from app.config import Settings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    """Evita depender de um .env ou da configuração do desenvolvedor."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EMPORIO_ENVIRONMENT", raising=False)


def test_default_settings() -> None:
    assert Settings().environment == "development"


def test_environment_overrides_dotenv(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("EMPORIO_ENVIRONMENT=production\n", encoding="utf-8")
    assert Settings().environment == "production"

    monkeypatch.setenv("EMPORIO_ENVIRONMENT", "test")
    assert Settings().environment == "test"


def test_invalid_environment_is_rejected(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EMPORIO_ENVIRONMENT", "invalid")
    with pytest.raises(ValidationError):
        Settings()


def test_installed_application_starts(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("EMPORIO_ENVIRONMENT", "test")
    result = subprocess.run(
        [sys.executable, "-m", "app.main"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=10,
    )
    assert result.stdout.strip() == "Empório da Música | ambiente: test | fase: 01"
    assert result.stderr == ""
