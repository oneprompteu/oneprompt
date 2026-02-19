"""Test configuration for monorepo imports."""

from __future__ import annotations

import sys
from pathlib import Path

SDK_SRC = Path(__file__).resolve().parent.parent / "packages" / "oneprompt-sdk"
if SDK_SRC.exists() and str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))
