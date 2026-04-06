"""XLSX New engine — create Excel workbooks from scratch. Zero MCP imports."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# sys.path bootstrap so 'shared' is importable when run directly
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from shared.platform_utils import open_file
from shared.progress import fail, info, ok, warn

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_parent(path: Path) -> None:
    """Create parent directories if they do not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _token_estimate(obj: Any) -> int:
    return len(str(obj)) // 4


def _write_headers(ws: Any, headers: list[Any]) -> None:
    """Write header row in row 1, bold."""
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)


def _write_rows(ws: Any, rows: list[list[Any]], start_row: int = 2) -> None:
    """Write data rows starting at start_row."""
    for row_idx, row_data in enumerate(rows, start=start_row):
        for col_idx, value in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)


# ---------------------------------------------------------------------------
# Public engine functions
# ---------------------------------------------------------------------------


def create_workbook(
    output_path: str,
    sheet_name: str = "Sheet1",
    open_after: bool = True,
) -> dict[str, Any]:
    """Create a blank Excel workbook with one sheet."""
    progress: list[dict[str, Any]] = []
    try:
        path = Path(output_path).resolve()
        _ensure_parent(path)
        progress.append(info("Creating blank workbook", path.name))

        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            ws = wb.create_sheet()
        ws.title = sheet_name

        wb.save(str(path))
        progress.append(ok(f"Saved {path.name}", f"sheet: {sheet_name}"))

        if open_after:
            open_file(path)
            progress.append(ok("Opened in default application"))

        result: dict[str, Any] = {
            "success": True,
            "op": "create_workbook",
            "output": str(path),
            "output_name": path.name,
            "sheet_name": sheet_name,
            "progress": progress,
        }
        result["token_estimate"] = _token_estimate(result)
        return result

    except Exception as exc:
        progress.append(fail(str(exc)))
        return {
            "success": False,
            "error": str(exc),
            "hint": "Check that output_path is a valid file path and you have write permission.",
            "progress": progress,
            "token_estimate": _token_estimate(progress),
        }


def create_from_data(
    output_path: str,
    sheet_name: str,
    headers: list[Any],
    rows: list[list[Any]],
    open_after: bool = True,
) -> dict[str, Any]:
    """Create an Excel workbook from headers and data rows."""
    progress: list[dict[str, Any]] = []
    try:
        path = Path(output_path).resolve()
        _ensure_parent(path)

        col_count = len(headers)
        row_count = len(rows)
        progress.append(
            info(
                "Creating workbook from data",
                f"{row_count} rows, {col_count} columns",
            )
        )

        wb = openpyxl.Workbook()
        ws = wb.active
        if ws is None:
            ws = wb.create_sheet()
        ws.title = sheet_name

        _write_headers(ws, headers)
        _write_rows(ws, rows, start_row=2)
        progress.append(
            ok(
                f"Wrote {row_count} data rows",
                f"headers in row 1, bold",
            )
        )

        wb.save(str(path))
        progress.append(ok(f"Saved {path.name}"))

        if open_after:
            open_file(path)
            progress.append(ok("Opened in default application"))

        result: dict[str, Any] = {
            "success": True,
            "op": "create_from_data",
            "output": str(path),
            "output_name": path.name,
            "sheet_name": sheet_name,
            "row_count": row_count,
            "column_count": col_count,
            "progress": progress,
        }
        result["token_estimate"] = _token_estimate(result)
        return result

    except Exception as exc:
        progress.append(fail(str(exc)))
        return {
            "success": False,
            "error": str(exc),
            "hint": (
                "Ensure headers is a list of strings and rows is a list of lists. "
                "Check that output_path is writable."
            ),
            "progress": progress,
            "token_estimate": _token_estimate(progress),
        }


def create_report(
    output_path: str,
    title: str,
    sheets: list[dict[str, Any]],
    open_after: bool = True,
) -> dict[str, Any]:
    """Create a multi-sheet Excel workbook with a Cover sheet."""
    progress: list[dict[str, Any]] = []
    try:
        path = Path(output_path).resolve()
        _ensure_parent(path)

        sheet_count = len(sheets)
        progress.append(
            info(
                "Creating multi-sheet report",
                f"{sheet_count} data sheet(s) + Cover",
            )
        )

        wb = openpyxl.Workbook()

        # Cover sheet — reuse the default active sheet
        cover = wb.active
        if cover is None:
            cover = wb.create_sheet()
        cover.title = "Cover"
        cover["A1"] = title
        cover["A1"].font = Font(bold=True, size=16)
        progress.append(ok("Created Cover sheet", title))

        # Data sheets
        for sheet_def in sheets:
            name = sheet_def.get("name", "Sheet")
            headers = sheet_def.get("headers", [])
            rows = sheet_def.get("rows", [])
            ws = wb.create_sheet(title=name)
            _write_headers(ws, headers)
            _write_rows(ws, rows, start_row=2)
            progress.append(
                ok(
                    f"Created sheet '{name}'",
                    f"{len(rows)} rows, {len(headers)} columns",
                )
            )

        wb.save(str(path))
        progress.append(ok(f"Saved {path.name}", f"{sheet_count + 1} sheets total"))

        if open_after:
            open_file(path)
            progress.append(ok("Opened in default application"))

        result: dict[str, Any] = {
            "success": True,
            "op": "create_report",
            "output": str(path),
            "output_name": path.name,
            "title": title,
            "sheets_created": sheet_count + 1,  # includes Cover
            "progress": progress,
        }
        result["token_estimate"] = _token_estimate(result)
        return result

    except Exception as exc:
        progress.append(fail(str(exc)))
        return {
            "success": False,
            "error": str(exc),
            "hint": (
                "sheets must be a list of dicts with 'name', 'headers', and 'rows' keys. "
                "Check that output_path is writable."
            ),
            "progress": progress,
            "token_estimate": _token_estimate(progress),
        }


def create_from_template(
    template_path: str,
    output_path: str,
    replacements: dict[str, Any],
    open_after: bool = True,
) -> dict[str, Any]:
    """Copy a .xlsx template, replace matching cell values, save to output_path."""
    progress: list[dict[str, Any]] = []
    try:
        src = Path(template_path).resolve()
        if not src.exists():
            progress.append(fail(f"Template not found", str(src)))
            return {
                "success": False,
                "error": f"File not found: {src}",
                "hint": "Check that template_path is an absolute path to an existing .xlsx file.",
                "progress": progress,
                "token_estimate": _token_estimate(progress),
            }
        if src.suffix.lower() not in {".xlsx", ".xlsm"}:
            progress.append(fail("Wrong file type", src.suffix))
            return {
                "success": False,
                "error": f"Expected .xlsx file, got {src.suffix}",
                "hint": "template_path must point to a .xlsx or .xlsm file.",
                "progress": progress,
                "token_estimate": _token_estimate(progress),
            }

        dst = Path(output_path).resolve()
        _ensure_parent(dst)

        progress.append(info(f"Loading template", src.name))
        wb = openpyxl.load_workbook(str(src))

        replaced_count = 0
        for sheet in wb.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    if cell.value is not None and cell.value in replacements:
                        cell.value = replacements[cell.value]
                        replaced_count += 1

        progress.append(
            ok(
                f"Replaced {replaced_count} cell value(s)",
                f"{len(replacements)} replacement key(s) searched",
            )
        )

        wb.save(str(dst))
        progress.append(ok(f"Saved {dst.name}"))

        if open_after:
            open_file(dst)
            progress.append(ok("Opened in default application"))

        result: dict[str, Any] = {
            "success": True,
            "op": "create_from_template",
            "template": str(src),
            "output": str(dst),
            "output_name": dst.name,
            "cells_replaced": replaced_count,
            "progress": progress,
        }
        result["token_estimate"] = _token_estimate(result)
        return result

    except Exception as exc:
        progress.append(fail(str(exc)))
        return {
            "success": False,
            "error": str(exc),
            "hint": (
                "Ensure template_path points to a valid .xlsx file and "
                "output_path is a writable destination."
            ),
            "progress": progress,
            "token_estimate": _token_estimate(progress),
        }
