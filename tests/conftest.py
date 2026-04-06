"""Shared pytest fixtures for office-mcp tests."""

import shutil
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def contract_simple_path() -> Path:
    return FIXTURES_DIR / "contract_simple.docx"


@pytest.fixture
def contract_complex_path() -> Path:
    return FIXTURES_DIR / "contract_complex.docx"


@pytest.fixture
def report_tables_path() -> Path:
    return FIXTURES_DIR / "report_tables.docx"


@pytest.fixture
def budget_simple_path() -> Path:
    return FIXTURES_DIR / "budget_simple.xlsx"


@pytest.fixture
def budget_formulas_path() -> Path:
    return FIXTURES_DIR / "budget_formulas.xlsx"


@pytest.fixture
def dashboard_path() -> Path:
    return FIXTURES_DIR / "dashboard.xlsx"


@pytest.fixture
def deck_simple_path() -> Path:
    return FIXTURES_DIR / "deck_simple.pptx"


@pytest.fixture
def deck_images_path() -> Path:
    return FIXTURES_DIR / "deck_images.pptx"


@pytest.fixture
def tmp_docx(tmp_path: Path, contract_simple_path: Path) -> Path:
    """Copy of contract_simple.docx in a temp directory."""
    target = tmp_path / "contract_simple.docx"
    shutil.copy(contract_simple_path, target)
    return target


@pytest.fixture
def tmp_complex_docx(tmp_path: Path, contract_complex_path: Path) -> Path:
    """Copy of contract_complex.docx in a temp directory."""
    target = tmp_path / "contract_complex.docx"
    shutil.copy(contract_complex_path, target)
    return target


@pytest.fixture
def tmp_xlsx(tmp_path: Path, budget_simple_path: Path) -> Path:
    """Copy of budget_simple.xlsx in a temp directory."""
    target = tmp_path / "budget_simple.xlsx"
    shutil.copy(budget_simple_path, target)
    return target


@pytest.fixture
def tmp_pptx(tmp_path: Path, deck_simple_path: Path) -> Path:
    """Copy of deck_simple.pptx in a temp directory."""
    target = tmp_path / "deck_simple.pptx"
    shutil.copy(deck_simple_path, target)
    return target
