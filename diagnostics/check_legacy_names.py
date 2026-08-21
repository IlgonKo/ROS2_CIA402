"""Fail when legacy product names appear outside documented compatibility areas."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER_PATH = Path(__file__).relative_to(PROJECT_ROOT).as_posix()

FULLY_ALLOWED_FILES = {
    "docs/worklog.md",
    "docs/tasks/td/TD-003-axis-server-naming.md",
    "docs/tasks/td/TD-019-project-path-migration.md",
    "docs/tasks/td/TD-020-legacy-runtime-identifiers.md",
    CHECKER_PATH,
}

ALLOWED_IDENTIFIERS = (
    "ros-cia402-axis-server.service",
)

ALLOWED_LINES = {
    "docs/remaining_tasks.md": (
        re.compile(r"^### TD-003 ", re.IGNORECASE),
        re.compile(r"^- 요약:.*Axis Server", re.IGNORECASE),
        re.compile(r"^- 상세:.*TD-003-axis-server-naming", re.IGNORECASE),
    ),
}

LEGACY_NAME = re.compile(r"\baxis[ _-]server\b", re.IGNORECASE)


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [path for path in result.stdout.splitlines() if path]


def _is_allowed_line(relative_path: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in ALLOWED_LINES.get(relative_path, ()))


def find_legacy_names() -> list[str]:
    violations: list[str] = []
    for relative_path in _tracked_files():
        normalized_path = relative_path.replace("\\", "/")
        if normalized_path in FULLY_ALLOWED_FILES:
            continue

        path = PROJECT_ROOT / relative_path
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for line_number, line in enumerate(content.splitlines(), start=1):
            candidate = line
            for identifier in ALLOWED_IDENTIFIERS:
                candidate = re.sub(re.escape(identifier), "", candidate, flags=re.IGNORECASE)
            if LEGACY_NAME.search(candidate) and not _is_allowed_line(normalized_path, line):
                violations.append(f"{normalized_path}:{line_number}: {line.strip()}")
    return violations


def main() -> int:
    violations = find_legacy_names()
    if violations:
        print("Legacy Motion Server naming violations:")
        for violation in violations:
            print(f"  {violation}")
        return 1
    print("Legacy Motion Server naming check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
