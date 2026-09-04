"""Целевая версия Python задана в одном месте — X-01.

Расхождение `.python-version`, образа в `apps/api/Dockerfile` и версии в CI — ровно тот
класс багов, ради которого заведена `make ci-target`: локальный прогон зелёный, CI красный,
а прод собирается третьей версией. Держать это на внимательности бессмысленно.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
PYTHON_VERSION_FILE = REPO_ROOT / ".python-version"
API_DOCKERFILE = REPO_ROOT / "apps" / "api" / "Dockerfile"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def target_version() -> str:
    return PYTHON_VERSION_FILE.read_text(encoding="utf-8").strip()


def test_version_file_holds_a_version() -> None:
    assert re.fullmatch(r"\d+\.\d+(\.\d+)?", target_version())


def test_api_image_uses_the_target_version() -> None:
    dockerfile = API_DOCKERFILE.read_text(encoding="utf-8")

    found = re.search(r"^FROM python:([\d.]+)-slim", dockerfile, re.M)

    assert found is not None, "apps/api/Dockerfile больше не начинается с FROM python:<версия>-slim"
    assert found.group(1) == target_version()


def test_ci_reads_the_version_from_the_file() -> None:
    """Литерал версии в workflow — тихое расхождение с .python-version через полгода."""
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "python-version-file: .python-version" in workflow
    assert not re.search(r"^\s*python-version:\s*[\"']?\d", workflow, re.M)
