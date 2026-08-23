"""XLSX Basic helpers — private utilities and advanced sheet operations."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

from shared.file_utils import hint_for_error, resolve_path, sheet_names_hint
from shared.live_edit import notify_reload
from shared.platform_utils import open_file
from shared.progress import fail, info, ok
from shared.version_control import snapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Address validation helpers (used by engine.py)
# ---------------------------------------------------------------------------

_CELL_RE = re.compile(r"^[A-Z]{1,3}\d+$")
_RANGE_RE = re.compile(r"^[A-Z]{1,3}\d+:[A-Z]{1,3}\d+$")


def _validate_cell(address: str) -> bool:
    return bool(_CELL_RE.match(address.upper()))


def _validate_range(address: str) -> bool:
    return bool(_RANGE_RE.match(address.upper()))


def _last_cell(ws: Any) -> str:
    """Return the Excel address of the last used cell in the worksheet."""
    col_letter = get_column_letter(ws.max_column) if ws.max_column else "A"
    row = ws.max_row or 1
    return f"{col_letter}{row}"


def _cell_count_for_range(range_address: str) -> int:
    """Return number of cells in an A1:C5 style range address."""
    top, bot = range_address.upper().split(":")
    top_col = re.sub(r"\d", "", top)
    top_row = int(re.sub(r"[A-Z]", "", top))
    bot_col = re.sub(r"\d", "", bot)
    bot_row = int(re.sub(r"[A-Z]", "", bot))
    cols = column_index_from_string(bot_col) - column_index_from_string(top_col) + 1
    rows = bot_row - top_row + 1
    return cols * rows


# ---------------------------------------------------------------------------
# Advanced sheet operations
# ---------------------------------------------------------------------------


def sort_sheet(
    file_path: str,
    sheet_name: str,
    column: str,
    ascending: bool = True,
    has_header: bool = True,
    open_after: bool = False,
) -> dict[str, Any]:
    """Sort all rows in a sheet by the values in a given column."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    path: Path | None = None
    try:
        col_upper = column.upper()
        try:
            col_idx = column_index_from_string(col_upper) - 1
        except Exception:
            progress.append(fail(f"Invalid column letter: {column}"))
            return {
                "success": False,
                "error": f"Invalid column letter: {column}",
                "hint": "Use a single column letter like 'A', 'B', or 'C'.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        if not path.exists():
            progress.append(fail("File not found", str(path)))
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "hint": "Check that file_path is absolute and the file exists.",
                "progress": progress,
                "token_estimate": 20,
            }

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        wb = openpyxl.load_workbook(str(path))
        if sheet_name not in wb.sheetnames:
            available_sheets = list(wb.sheetnames)
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": sheet_names_hint(available_sheets),
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]

        # Read all rows as lists of cell values
        all_rows = [[cell.value for cell in row] for row in ws.iter_rows()]

        if not all_rows:
            progress.append(info("Sheet is empty — nothing to sort"))
            wb.close()
            return {
                "success": True,
                "op": "sort_sheet",
                "sheet": sheet_name,
                "rows_sorted": 0,
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        if has_header:
            data_rows = all_rows[1:]
        else:
            data_rows = all_rows

        # Sort: None values sink to bottom
        sorted_rows = sorted(
            data_rows,
            key=lambda r: (r[col_idx] is None, r[col_idx]),
            reverse=not ascending,
        )

        # Write back cell by cell
        start_row = 2 if has_header else 1
        for r_offset, row_vals in enumerate(sorted_rows):
            for c_offset, val in enumerate(row_vals):
                ws.cell(row=start_row + r_offset, column=c_offset + 1, value=val)

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "sort_sheet",
            "sheet": sheet_name,
            "column": col_upper,
            "ascending": ascending,
            "rows_sorted": len(sorted_rows),
            "backup": backup,
            "progress": progress,
        }
        result["token_estimate"] = len(str(result)) // 4
        return result

    except Exception as e:
        progress.append(fail(str(e)))
        return {
            "success": False,
            "error": str(e),
            "hint": hint_for_error(e, path),
            "backup": backup,
            "progress": progress,
            "token_estimate": 15,
        }


def rename_sheet(
    file_path: str,
    old_name: str,
    new_name: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Rename a worksheet tab from old_name to new_name."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    path: Path | None = None
    try:
        if not new_name:
            progress.append(fail("new_name cannot be empty"))
            return {
                "success": False,
                "error": "new_name cannot be empty",
                "hint": "Provide a non-empty name for the sheet.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        if not path.exists():
            progress.append(fail("File not found", str(path)))
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "hint": "Check that file_path is absolute and the file exists.",
                "progress": progress,
                "token_estimate": 20,
            }

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        wb = openpyxl.load_workbook(str(path))
        if old_name not in wb.sheetnames:
            available_sheets = list(wb.sheetnames)
            progress.append(fail(f"Sheet '{old_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{old_name}' not found",
                "hint": sheet_names_hint(available_sheets),
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }
        if new_name in wb.sheetnames:
            progress.append(fail(f"Sheet '{new_name}' already exists"))
            return {
                "success": False,
                "error": f"Sheet '{new_name}' already exists",
                "hint": "Choose a different name or delete the existing sheet first.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        wb[old_name].title = new_name
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"Renamed sheet '{old_name}' → '{new_name}'"))
        result: dict[str, Any] = {
            "success": True,
            "op": "rename_sheet",
            "old_name": old_name,
            "new_name": new_name,
            "backup": backup,
            "progress": progress,
        }
        result["token_estimate"] = len(str(result)) // 4
        return result

    except Exception as e:
        progress.append(fail(str(e)))
        return {
            "success": False,
            "error": str(e),
            "hint": hint_for_error(e, path),
            "backup": backup,
            "progress": progress,
            "token_estimate": 15,
        }


def find_duplicates(
    file_path: str,
    sheet_name: str,
    column: str,
    has_header: bool = True,
) -> dict[str, Any]:
    """Find duplicate values in a column. Returns rows where a value repeats."""
    progress: list[dict[str, Any]] = []
    try:
        col_upper = column.upper()
        try:
            col_idx = column_index_from_string(col_upper)
        except Exception:
            progress.append(fail(f"Invalid column letter: {column}"))
            return {
                "success": False,
                "error": f"Invalid column letter: {column}",
                "hint": "Use a single column letter like 'A', 'B', or 'C'.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        if not path.exists():
            progress.append(fail("File not found", str(path)))
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "hint": "Check that file_path is absolute and the file exists.",
                "progress": progress,
                "token_estimate": 20,
            }

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        if sheet_name not in wb.sheetnames:
            available_sheets = list(wb.sheetnames)
            wb.close()
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": sheet_names_hint(available_sheets),
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]

        # Collect (value, row_number) pairs from the target column
        value_rows: dict[Any, list[int]] = {}
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if has_header and row_idx == 1:
                continue
            if col_idx - 1 < len(row):
                val = row[col_idx - 1]
                if val is not None:
                    value_rows.setdefault(val, []).append(row_idx)

        wb.close()

        # Keep only values that appear more than once
        duplicates = [{"value": v, "rows": rows} for v, rows in value_rows.items() if len(rows) > 1]

        truncated = False
        if len(duplicates) > 100:
            duplicates = duplicates[:100]
            truncated = True

        progress.append(
            ok(
                f"Found {len(duplicates)} duplicate value(s) in column {col_upper}",
                sheet_name,
            )
        )
        result: dict[str, Any] = {
            "success": True,
            "sheet": sheet_name,
            "column": col_upper,
            "duplicate_count": len(duplicates),
            "duplicates": duplicates,
            "truncated": truncated,
            "progress": progress,
        }
        result["token_estimate"] = len(str(result)) // 4
        return result

    except Exception as e:
        progress.append(fail(str(e)))
        return {
            "success": False,
            "error": str(e),
            "hint": "Check that file_path points to a valid .xlsx file.",
            "progress": progress,
            "token_estimate": 15,
        }


def copy_sheet(
    file_path: str,
    source_sheet: str,
    new_sheet_name: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Copy a worksheet within the same workbook to a new sheet name."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    path: Path | None = None
    try:
        if not new_sheet_name:
            progress.append(fail("new_sheet_name cannot be empty"))
            return {
                "success": False,
                "error": "new_sheet_name cannot be empty",
                "hint": "Provide a non-empty name for the copied sheet.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        if not path.exists():
            progress.append(fail("File not found", str(path)))
            return {
                "success": False,
                "error": f"File not found: {file_path}",
                "hint": "Check that file_path is absolute and the file exists.",
                "progress": progress,
                "token_estimate": 20,
            }

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        wb = openpyxl.load_workbook(str(path))
        if source_sheet not in wb.sheetnames:
            available_sheets = list(wb.sheetnames)
            progress.append(fail(f"Sheet '{source_sheet}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{source_sheet}' not found",
                "hint": sheet_names_hint(available_sheets),
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }
        if new_sheet_name in wb.sheetnames:
            progress.append(fail(f"Sheet '{new_sheet_name}' already exists"))
            return {
                "success": False,
                "error": f"Sheet '{new_sheet_name}' already exists",
                "hint": "Choose a different name or delete the existing sheet first.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        source_ws = wb[source_sheet]
        copied_ws = wb.copy_worksheet(source_ws)
        copied_ws.title = new_sheet_name

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"Copied '{source_sheet}' → '{new_sheet_name}'"))
        result: dict[str, Any] = {
            "success": True,
            "op": "copy_sheet",
            "source_sheet": source_sheet,
            "new_sheet_name": new_sheet_name,
            "backup": backup,
            "progress": progress,
        }
        result["token_estimate"] = len(str(result)) // 4
        return result

    except Exception as e:
        progress.append(fail(str(e)))
        return {
            "success": False,
            "error": str(e),
            "hint": hint_for_error(e, path),
            "backup": backup,
            "progress": progress,
            "token_estimate": 15,
        }
