"""Audita candidatos Git sem publicar, stage, commit ou expor os valores encontrados."""

import argparse
import csv
import json
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

PROJECT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "openai_like_key": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"),
    "github_like_token": re.compile(
        r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b"
    ),
    "aws_like_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "session_credential": re.compile(
        r"""["'](?:session_token|access_token)["']\s*:\s*["'][A-Za-z0-9_-]{43}["']"""
    ),
}
PROBES = (
    ".env",
    ".env.production",
    "token.key",
    "data/raw/products.csv",
    "data/raw/políticas_da_loja.pdf",
    "data/emporio.sqlite3",
    "logs/debug.log",
)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=PROJECT, capture_output=True, check=False)


def checked_git(*args: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    result = git(*args)
    if result.returncode not in allowed:
        raise ValueError("git_command_failed")
    return result


def candidates() -> list[Path]:
    result = checked_git("ls-files", "--cached", "--others", "--exclude-standard", "-z")
    return sorted({Path(name.decode()) for name in result.stdout.split(b"\0") if name})


def customer_fingerprints(raw_dir: Path) -> dict[str, set[str]]:
    matches = [path for path in raw_dir.glob("*.csv") if path.name.endswith("customers.csv")]
    values = {"customer_email": set(), "customer_name": set(), "customer_phone": set()}
    for path in matches:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                values["customer_email"].add(row["email"].casefold())
                values["customer_name"].add(row["name"].casefold())
                values["customer_phone"].add(re.sub(r"\D", "", row["phone"]))
    return values


def inspect_text(path: str, text: str, fingerprints: dict[str, set[str]]) -> list[dict]:
    """Relata somente arquivo/linha/tipo. Nunca inclui token ou PII correspondente."""
    findings = []
    for code, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            findings.append(
                {"file": path, "line": text.count("\n", 0, match.start()) + 1, "code": code}
            )
    if path == ".env.example":
        for number, line in enumerate(text.splitlines(), start=1):
            key, sep, value = line.partition("=")
            if (
                sep
                and not key.startswith("#")
                and key.endswith(("API_KEY", "_TOKEN", "PASSWORD", "SECRET"))
                and value.strip()
            ):
                findings.append({"file": path, "line": number, "code": "nonempty_example_secret"})
    lowered = text.casefold()
    for code in ("customer_email", "customer_name"):
        if any(len(value) >= 6 and value in lowered for value in fingerprints.get(code, ())):
            findings.append({"file": path, "code": code})
    # Cada número conhecido é buscado sem consumir ID/extensão que venha depois.
    if any(
        value.isdigit()
        and len(value) >= 10
        and re.search(
            r"(?<!\d)" + r"[\s()./-]{0,4}".join(value) + r"(?!\d)",
            text,
        )
        for value in fingerprints.get("customer_phone", ())
    ):
        findings.append({"file": path, "code": "customer_phone"})
    return findings


def restricted(path: Path) -> bool:
    return (
        path.name.startswith(".env")
        and path.name != ".env.example"
        or path.parts[:2] in (("data", "raw"), ("data", "derived"))
        or any(part in (".aws", ".codex", ".agents", "logs") for part in path.parts)
        or path.suffix.lower() in (".pdf", ".sqlite", ".sqlite3", ".db", ".key", ".pem", ".log")
    )


def remote_issue(value: str) -> str | None:
    remote = urlsplit(value)
    if remote.password:
        return "credential_in_remote_url"
    if remote.scheme in ("http", "https") and remote.username:
        return "remote_http_userinfo_requires_review"
    # Usuário de transporte SSH não é uma credencial secreta.
    return None


def inspect_index(texts: dict[Path, str], fingerprints: dict, findings: list[dict]) -> int:
    scanned = 0
    entries = checked_git("ls-files", "--stage", "-z").stdout.split(b"\0")
    for entry in entries:
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, oid, stage = metadata.split()
        relative = Path(name.decode())
        issue = (
            "restricted_publication_candidate"
            if restricted(relative)
            else "unmerged_index_requires_review"
            if stage != b"0"
            else "staged_symlink_requires_review"
            if mode == b"120000"
            else "unsupported_index_mode"
            if mode not in (b"100644", b"100755")
            else None
        )
        if issue:
            findings.append({"file": relative.as_posix(), "source": "git_index", "code": issue})
            continue
        # Ler o objeto exato do índice, sem textconv, filtros ou conteúdo do worktree.
        blob = checked_git("cat-file", "blob", oid.decode()).stdout
        try:
            text = blob.decode("utf-8")
        except UnicodeError:
            findings.append(
                {
                    "file": relative.as_posix(),
                    "source": "git_index",
                    "code": "unscanned_binary_or_unreadable",
                }
            )
            continue
        scanned += 1
        if texts.get(relative) != text:
            findings.extend(
                {**item, "source": "git_index"}
                for item in inspect_text(relative.as_posix(), text, fingerprints)
            )
    return scanned


def audit(output: Path) -> dict:
    paths = candidates()
    fingerprints = customer_fingerprints(PROJECT / "data/raw")
    findings = []
    scanned = 0
    texts = {}
    for relative in paths:
        path = PROJECT / relative
        if restricted(relative):
            findings.append(
                {"file": relative.as_posix(), "code": "restricted_publication_candidate"}
            )
            continue
        if path.is_symlink():
            findings.append({"file": relative.as_posix(), "code": "symlink_requires_review"})
            continue
        if path.absolute() == output.absolute():
            continue  # Só o relatório exato; aliases já foram validados acima.
        if not path.is_file():
            findings.append({"file": relative.as_posix(), "code": "missing_candidate"})
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            findings.append({"file": relative.as_posix(), "code": "unscanned_binary_or_unreadable"})
            continue
        scanned += 1
        texts[relative] = text
        findings.extend(inspect_text(relative.as_posix(), text, fingerprints))
    index_scanned = inspect_index(texts, fingerprints, findings)
    probes = {
        probe: checked_git(
            "check-ignore", "--no-index", "--quiet", probe, allowed=(0, 1)
        ).returncode
        == 0
        for probe in PROBES
    }
    for probe, ignored in probes.items():
        if not ignored:
            findings.append({"file": probe, "code": "missing_ignore_rule"})
    remotes = checked_git(
        "config", "--get-regexp", r"^remote\..*\.url$", allowed=(0, 1)
    ).stdout.decode()
    remote_values = [line.partition(" ")[2] for line in remotes.splitlines()]
    for value in remote_values:
        if issue := remote_issue(value):
            findings.append({"code": issue})
    commits = checked_git("rev-list", "--all", "--count")
    tracked = checked_git("ls-files", "-z")
    return {
        "auditor_version": "1.2",
        "audited_at_utc": datetime.now(UTC).isoformat(),
        "scope": "git_index_blobs_and_worktree_candidates",
        "candidate_count": len(paths),
        "text_files_scanned": scanned,
        "index_text_files_scanned": index_scanned,
        "self_report_excluded": True,
        "findings": findings,
        "technical_scan_passed": not findings,
        "protected_probes": probes,
        "customer_fingerprint_check": "performed_locally"
        if any(fingerprints.values())
        else "raw_data_absent",
        "fingerprints_or_matching_values_exported": False,
        "tracked_files": len([name for name in tracked.stdout.split(b"\0") if name]),
        "git_commits": int(commits.stdout or 0),
        "remote_configured": bool(remote_values),
        "annex_redistribution_permission": "not_documented_in_workspace",
        "publication_authorized": False,
        "publication_attempted": False,
        "limits": [
            "heuristic_secret_patterns",
            "no_external_permission_or_deadline_confirmation",
            "no_complete_secret_history_audit_when_history_is_absent",
        ],
    }


def write_report(output: Path, report: dict) -> None:
    if output.is_symlink():
        raise ValueError("unsafe_audit_output")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".audit-stage-", dir=output.parent) as temporary:
        staged = Path(temporary) / "report.json"
        staged.write_bytes(
            (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        # Substitui a entrada sem escrever no inode de um eventual hard link.
        staged.replace(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "docs/publication_audit.json")
    args = parser.parse_args()
    output = args.output.parent.resolve() / args.output.name
    if output.suffix != ".json" or (
        output.is_relative_to(PROJECT) and not output.is_relative_to(PROJECT / "docs")
    ):
        parser.error("unsafe_audit_output")
    try:
        if output.is_symlink():
            raise ValueError("unsafe_audit_output")
        report = audit(output)
        write_report(output, report)
        print(
            json.dumps(
                {
                    "technical_scan_passed": report["technical_scan_passed"],
                    "findings": len(report["findings"]),
                    "publication_authorized": False,
                }
            )
        )
        return 0 if report["technical_scan_passed"] else 1
    except Exception:
        print('{"error":"publication_audit_unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
