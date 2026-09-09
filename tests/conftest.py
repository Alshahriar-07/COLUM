"""Shared pytest fixtures for COLUM tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure the project root is importable when running pytest from anywhere.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"
