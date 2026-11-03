"""Detectores retornam só tipos/localização; testes não contêm credenciais reais."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("release_audit", "scripts/audit_release.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize(
    "value,code",
    [
        ("sk-" + "a" * 32, "openai_like_key"),
        ("ghp_" + "b" * 36, "github_like_token"),
        ("AKIA" + "C" * 16, "aws_like_key"),
        ("-----BEGIN " + "PRIVATE KEY-----", "private_key"),
    ],
)
def test_secret_detector_never_exports_matching_value(value, code):
    findings = audit.inspect_text("candidate.txt", value, {})
    assert any(item["code"] == code for item in findings)
    assert value not in json.dumps(findings)


def test_token_limit_is_not_a_credential_and_env_secret_must_be_empty():
    assert audit.inspect_text(".env.example", "EMPORIO_LLM_MAX_OUTPUT_TOKENS=1200", {}) == []
    assert audit.inspect_text(".env.example", "EMPORIO_LLM_API_KEY=", {}) == []
    result = audit.inspect_text(".env.example", "EMPORIO_LLM_API_KEY=unit-test-only", {})
    assert result[0]["code"] == "nonempty_example_secret"
    assert "unit-test-only" not in json.dumps(result)


def test_pii_fingerprints_and_session_tokens_are_not_exported():
    text = "Pessoa de teste pessoa@example.invalid (11) 99999-0000"
    fingerprints = {
        "customer_email": {"pessoa@example.invalid"},
        "customer_name": {"pessoa de teste"},
        "customer_phone": {"11999990000"},
    }
    findings = audit.inspect_text("example.txt", text, fingerprints)
    assert {item["code"] for item in findings} == set(fingerprints)
    assert "pessoa" not in json.dumps(findings).lower()
    token = "a" * 43
    result = audit.inspect_text("example.json", json.dumps({"session_token": token}), {})
    assert result[0]["code"] == "session_credential" and token not in json.dumps(result)


@pytest.mark.parametrize(
    "filename", [".env", "data/raw/products.csv", "data/local.sqlite3", "logs/a.log"]
)
def test_restricted_paths_are_blocked_even_if_tracked(filename):
    assert audit.restricted(Path(filename))
    assert not audit.restricted(Path(".env.example"))
    assert not audit.restricted(Path("data/samples/customers.csv"))


@pytest.mark.parametrize(
    "text", ["(11) 99999-0000 12", "11999990000 / 12", "+55 (11) 99999-0000 12"]
)
def test_phone_lookup_does_not_consume_following_id(text):
    findings = audit.inspect_text("synthetic.txt", text, {"customer_phone": {"11999990000"}})
    assert {item["code"] for item in findings} == {"customer_phone"}
    assert "99999" not in json.dumps(findings)


@pytest.fixture
def audit_repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], capture_output=True, check=True)
    (root / ".gitignore").write_bytes(Path(".gitignore").read_bytes())
    (root / "README.md").write_text("Synthetic release")
    monkeypatch.setattr(audit, "PROJECT", root)
    return root


@pytest.mark.parametrize(
    "remote", ["ssh://git@example.invalid/store.git", "git@example.invalid:store.git"]
)
def test_normal_ssh_remote_is_not_a_secret(audit_repo, remote):
    subprocess.run(
        ["git", "-C", str(audit_repo), "config", "remote.origin.url", remote],
        capture_output=True,
        check=True,
    )
    report = audit.audit(audit_repo / "docs/report.json")
    assert report["remote_configured"] and report["technical_scan_passed"]


def test_remote_password_is_reported_without_value(audit_repo):
    value = "https://git:PRIVATE_REVIEW_SECRET@example.invalid/store.git"
    subprocess.run(
        ["git", "-C", str(audit_repo), "config", "remote.origin.url", value],
        capture_output=True,
        check=True,
    )
    report = audit.audit(audit_repo / "docs/report.json")
    assert not report["technical_scan_passed"]
    assert {item["code"] for item in report["findings"]} == {"credential_in_remote_url"}
    assert "PRIVATE_REVIEW_SECRET" not in json.dumps(report)


@pytest.mark.parametrize("operation", ["rev-list", "config", "check-ignore", "ls-files"])
def test_git_failures_abort_audit_instead_of_approving(audit_repo, monkeypatch, operation):
    original = audit.git

    def fail(*args):
        if args[0] == operation:
            return subprocess.CompletedProcess(args, 128, b"", b"PRIVATE_REVIEW_SECRET")
        return original(*args)

    monkeypatch.setattr(audit, "git", fail)
    with pytest.raises(ValueError, match="^git_command_failed$"):
        audit.audit(audit_repo / "docs/report.json")


def test_failed_cli_audit_preserves_previous_report_and_hides_error(
    audit_repo, monkeypatch, capsys
):
    output = audit_repo / "docs/report.json"
    output.parent.mkdir()
    output.write_text("previous verified evidence")
    original = audit.git

    def fail(*args):
        if args[0] == "rev-list":
            return subprocess.CompletedProcess(args, 128, b"", b"PRIVATE_REVIEW_SECRET")
        return original(*args)

    monkeypatch.setattr(audit, "git", fail)
    monkeypatch.setattr("sys.argv", ["audit_release.py", "--output", str(output)])
    assert audit.main() == 2
    assert output.read_text() == "previous verified evidence"
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"error": "publication_audit_unavailable"}
    assert "PRIVATE_REVIEW_SECRET" not in captured.out + captured.err


@pytest.mark.parametrize("name", [".env", "alias.md"])
def test_report_alias_cannot_skip_restricted_or_symlink_checks(audit_repo, name):
    output = audit_repo / "docs/report.json"
    output.parent.mkdir()
    output.write_text("{}")
    (audit_repo / name).symlink_to(output)
    if name == ".env":
        subprocess.run(
            ["git", "-C", str(audit_repo), "add", "-f", name], capture_output=True, check=True
        )
    report = audit.audit(output)
    assert not report["technical_scan_passed"]
    assert any(item.get("file") == name for item in report["findings"])


def test_atomic_report_does_not_modify_hardlinked_source(tmp_path):
    original = tmp_path / "source.csv"
    original.write_bytes(b"immutable synthetic source")
    output = tmp_path / "audit.json"
    os.link(original, output)
    audit.write_report(output, {"technical_scan_passed": True})
    assert original.read_bytes() == b"immutable synthetic source"
    assert json.loads(output.read_text())["technical_scan_passed"]


def test_report_writer_rejects_symlink(tmp_path):
    original = tmp_path / "source.json"
    original.write_text("immutable synthetic source")
    output = tmp_path / "audit.json"
    output.symlink_to(original)
    with pytest.raises(ValueError, match="unsafe_audit_output"):
        audit.write_report(output, {})
    assert original.read_text() == "immutable synthetic source"


@pytest.mark.parametrize("filename", ["README.md", "docs/report.json"])
def test_staged_secret_is_detected_when_worktree_is_clean(audit_repo, filename):
    path = audit_repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = "sk-" + "a" * 32
    path.write_text(secret)
    subprocess.run(["git", "-C", str(audit_repo), "add", filename], capture_output=True, check=True)
    path.write_text("safe working tree")
    report = audit.audit(audit_repo / "docs/report.json")
    assert not report["technical_scan_passed"]
    assert report["index_text_files_scanned"] == 1
    assert any(
        item["code"] == "openai_like_key" and item["source"] == "git_index"
        for item in report["findings"]
    )
    assert secret not in json.dumps(report)


def test_staged_symlink_is_detected_even_if_worktree_became_regular(audit_repo):
    target = audit_repo / "README.md"
    alias = audit_repo / "alias.md"
    alias.symlink_to(target)
    subprocess.run(
        ["git", "-C", str(audit_repo), "add", "alias.md"], capture_output=True, check=True
    )
    alias.unlink()
    alias.write_text("safe working tree")
    report = audit.audit(audit_repo / "docs/report.json")
    assert not report["technical_scan_passed"]
    assert any(item["code"] == "staged_symlink_requires_review" for item in report["findings"])


def test_index_blob_failure_aborts_audit(audit_repo, monkeypatch):
    subprocess.run(
        ["git", "-C", str(audit_repo), "add", "README.md"], capture_output=True, check=True
    )
    original = audit.git

    def fail(*args):
        if args[0] == "cat-file":
            return subprocess.CompletedProcess(args, 128, b"", b"PRIVATE_REVIEW_SECRET")
        return original(*args)

    monkeypatch.setattr(audit, "git", fail)
    with pytest.raises(ValueError, match="git_command_failed"):
        audit.audit(audit_repo / "docs/report.json")
