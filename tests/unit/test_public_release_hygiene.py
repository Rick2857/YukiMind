"""Guards against committing common private runtime files and live credentials."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
PRIVATE_DIRECTORY_NAMES = {
    "napcat-data",
    "napcat-config",
    "napcat-plugins",
    "snowluma-data",
    "snowluma-qq-config",
    "snowluma-qq-data",
    "snowluma-extra-accounts",
}
PRIVATE_FILE_NAMES = {".env", ".mcp.json"}
PRIVATE_SUFFIXES = {".db", ".db-shm", ".db-wal", ".key", ".pem"}
PRIVATE_BACKUP_PATTERN = re.compile(r"\.bak(?:$|[-.])", re.IGNORECASE)
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"gh" + rb"[pousr]_[A-Za-z0-9]{36,}"),
    re.compile(rb"xox" + rb"[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(rb"AK" + rb"IA[0-9A-Z]{16}"),
    re.compile(rb"sk" + rb"-(?:proj-)?[A-Za-z0-9]{20,}"),
)


def _tracked_files() -> list[PurePosixPath]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    tracked: list[PurePosixPath] = []
    for item in result.stdout.split(b"\0"):
        if not item:
            continue
        path = PurePosixPath(item.decode())
        if (ROOT / Path(*path.parts)).is_file():
            tracked.append(path)
    return tracked


def test_tracked_tree_excludes_private_runtime_files_and_live_credentials() -> None:
    tracked = _tracked_files()
    assert all(
        PRIVATE_BACKUP_PATTERN.search(name)
        for name in (".env.bak", ".env.bak-20260912-204200", "docker-compose.yml.bak.old")
    )
    unsafe_paths = [
        str(path)
        for path in tracked
        if path.name.lower() in PRIVATE_FILE_NAMES
        or any(part.lower() in PRIVATE_DIRECTORY_NAMES for part in path.parts)
        or any(path.name.lower().endswith(suffix) for suffix in PRIVATE_SUFFIXES)
        or PRIVATE_BACKUP_PATTERN.search(path.name)
        or "qrcode" in path.name.lower()
    ]
    assert not unsafe_paths, f"private runtime paths are tracked: {unsafe_paths}"

    matches: list[str] = []
    for path in tracked:
        data = (ROOT / Path(*path.parts)).read_bytes()
        if any(pattern.search(data) for pattern in SECRET_PATTERNS):
            matches.append(str(path))
    assert not matches, f"possible live credentials found in tracked files: {matches}"
