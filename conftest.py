"""Root conftest.py — adds repo root to sys.path so 'shared' is importable."""

import sys
from pathlib import Path

# Add repo root so that 'import shared' works without installing the package
sys.path.insert(0, str(Path(__file__).parent))
