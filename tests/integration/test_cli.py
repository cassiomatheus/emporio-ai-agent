"""Executa a CLI instalada como subprocesso, sem chamar provedor real."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.database.ingestion import ingest_dataset


@pytest.fixture
def environment(tmp_path, monkeypatch):
    path = tmp_path / "demo.sqlite3"
    ingest_dataset(Path("data/samples"), path)
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("EMPORIO_") and key != "OPENAI_API_KEY"
    }
    env.update({"EMPORIO_CHAT_DEMO_DATABASE": str(path), "EMPORIO_CHAT_MODE": "real"})
    # Remover env vars não desativa o .env do workspace nos subprocessos.
    monkeypatch.chdir(tmp_path)
    return env


def run(args, env, *, input=None):
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *args],
        env=env,
        input=input,
        text=True,
        capture_output=True,
        timeout=15,
    )


def test_one_shot_cli_with_verified_data(environment):
    result = run(["--offline-demo", "--message", "Mostre o produto 102"], environment)
    assert result.returncode == 0 and "R$ 250,00" in result.stdout
    assert "offline_scripted" in result.stdout and result.stderr == ""


def test_interactive_cli_remembers_product_and_exits(environment):
    result = run(["--offline-demo"], environment, input="Mostre o produto 102\nE no PIX?\n/sair\n")
    assert result.returncode == 0 and "R$ 237,50" in result.stdout
    assert result.stderr == ""


def test_cli_demo_order_is_explicit_and_synthetic_only(environment):
    own = run(["--offline-demo", "--demo-order", "--message", "Consulte pedido 1"], environment)
    assert own.returncode == 0
    assert "R$ 999,90" in own.stdout and "não informa código de rastreamento" in own.stdout
    guest = run(["--offline-demo", "--message", "Consulte pedido 1"], environment)
    assert guest.returncode == 1 and "não autorizado" in guest.stderr
    other = run(["--offline-demo", "--demo-order", "--message", "Consulte pedido 2"], environment)
    assert other.returncode == 1 and "DEMO-TRACK" not in other.stdout
    assert run(["--demo-order", "--message", "Olá"], environment).returncode == 2


@pytest.mark.parametrize("text", [" ", "x" * 2001])
def test_cli_invalid_message_is_safe(environment, text):
    result = run(["--offline-demo", "--message", text], environment)
    assert result.returncode == 2 and "inválida" in result.stderr
    assert result.stderr == "Requisição inválida. Confira os campos e limites.\n"


def test_unconfigured_cli_and_eof_exit_without_traceback(environment):
    missing = run(["--message", "Olá"], environment)
    assert missing.returncode == 2 and "indisponível" in missing.stderr
    assert "Traceback" not in missing.stderr
    eof = run(["--offline-demo"], environment, input="")
    assert eof.returncode == 0


def test_cli_help_is_available_without_llm(environment):
    result = run(["--help"], environment)
    assert result.returncode == 0 and "--offline-demo" in result.stdout
