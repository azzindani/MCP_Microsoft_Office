"""XLSX Basic engine — pure openpyxl logic, zero MCP imports."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.utils import column_index_from_string

from shared.file_utils import hint_for_error, resolve_path
from shared.live_edit import notify_reload
from shared.platform_utils import get_max_cells, get_max_search_results, open_file
from shared.progress import fail, ok, warn
from shared.version_control import snapshot

from .helpers import _cell_count_for_range, _last_cell, _validate_cell, _validate_range

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def list_sheets(file_path: str) -> dict[str, Any]:
    """Return sheet names and row/col dimensions for every sheet."""
    progress: list[dict[str, Any]] = []
    try:
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
        if path.suffix.lower() not in {".xlsx", ".xlsm"}:
            progress.append(fail(f"Wrong file type: {path.suffix}"))
            return {
                "success": False,
                "error": f"Expected .xlsx file, got {path.suffix}",
                "hint": "Use the correct server for this file type.",
                "progress": progress,
                "token_estimate": 20,
            }

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        sheets = []
        for name in wb.sheetnames:
            ws = wb[name]
            sheets.append(
                {
                    "name": name,
                    "max_row": ws.max_row or 0,
                    "max_col": ws.max_column or 0,
                    "last_cell": _last_cell(ws),
                }
            )
        wb.close()

        progress.append(ok(f"Listed sheets for {path.name}", f"{len(sheets)} sheet(s)"))
        result: dict[str, Any] = {
            "success": True,
            "file": str(path),
            "sheet_count": len(sheets),
            "sheets": sheets,
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


def get_sheet_summary(file_path: str, sheet_name: str) -> dict[str, Any]:
    """Return dimensions, header row, and first-column sample for a sheet."""
    progress: list[dict[str, Any]] = []
    try:
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
            wb.close()
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]
        max_row = ws.max_row or 0
        max_col = ws.max_column or 0
        last_cell = _last_cell(ws)

        # Header row — first row as list of cell dicts
        header_row: list[dict[str, Any]] = []
        first_col_sample: list[Any] = []
        sample_count = 0

        for row_idx, row in enumerate(ws.iter_rows(values_only=False), start=1):
            if row_idx == 1:
                for cell in row:
                    header_row.append({"cell": cell.coordinate, "value": cell.value})
            else:
                # First column sample — up to 5 non-empty values
                if sample_count < 5 and row:
                    first_cell = row[0]
                    if first_cell.value is not None:
                        first_col_sample.append(
                            {"cell": first_cell.coordinate, "value": first_cell.value}
                        )
                        sample_count += 1

        wb.close()

        more_rows = max_row - 1 - sample_count
        if more_rows > 0:
            first_col_sample.append(f"... {more_rows} more rows")

        progress.append(ok(f"Summarised sheet '{sheet_name}'", f"{max_row} rows, {max_col} cols"))
        result: dict[str, Any] = {
            "success": True,
            "sheet": sheet_name,
            "dimensions": {
                "rows": max_row,
                "cols": max_col,
                "last_cell": last_cell,
            },
            "header_row": header_row,
            "first_col_sample": first_col_sample,
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


def read_cell(file_path: str, sheet_name: str, cell_address: str) -> dict[str, Any]:
    """Return value, formula, and data type for a single cell."""
    progress: list[dict[str, Any]] = []
    addr = cell_address.upper()
    try:
        if not _validate_cell(addr):
            progress.append(fail(f"Invalid cell address: {cell_address}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {cell_address}",
                "hint": "Use Excel notation like B5 or C12.",
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

        # Load with data_only=True to get evaluated value
        wb_val = openpyxl.load_workbook(str(path), data_only=True)
        if sheet_name not in wb_val.sheetnames:
            wb_val.close()
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "progress": progress,
                "token_estimate": 15,
            }
        ws_val = wb_val[sheet_name]
        value = ws_val[addr].value
        wb_val.close()

        # Load without data_only to get formula string
        wb_form = openpyxl.load_workbook(str(path), data_only=False)
        ws_form = wb_form[sheet_name]
        raw = ws_form[addr].value
        formula = raw if isinstance(raw, str) and raw.startswith("=") else None
        wb_form.close()

        # Determine type
        if value is None:
            cell_type = "empty"
        elif isinstance(value, bool):
            cell_type = "boolean"
        elif isinstance(value, (int, float)):
            cell_type = "number"
        else:
            cell_type = "string"

        progress.append(ok(f"Read cell {addr}", sheet_name))
        result: dict[str, Any] = {
            "success": True,
            "sheet": sheet_name,
            "cell": addr,
            "value": value,
            "formula": formula,
            "type": cell_type,
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


def read_cell_range(file_path: str, sheet_name: str, range_address: str) -> dict[str, Any]:
    """Return a bounded 2D cell array. Max 200 cells."""
    progress: list[dict[str, Any]] = []
    rng = range_address.upper()
    try:
        if not _validate_range(rng):
            progress.append(fail(f"Invalid range address: {range_address}"))
            return {
                "success": False,
                "error": f"Invalid range address: {range_address}",
                "hint": "Use Excel notation like A1:D10.",
                "progress": progress,
                "token_estimate": 15,
            }

        cell_count = _cell_count_for_range(rng)
        max_cells = get_max_cells()
        if cell_count > max_cells:
            progress.append(fail(f"Range too large: {cell_count} cells"))
            return {
                "success": False,
                "error": f"Range {rng} contains {cell_count} cells (max {max_cells})",
                "hint": f"Split into smaller ranges of {max_cells} cells or fewer.",
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

        # Load both forms for value + formula
        wb_val = openpyxl.load_workbook(str(path), data_only=True)
        if sheet_name not in wb_val.sheetnames:
            wb_val.close()
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "progress": progress,
                "token_estimate": 15,
            }
        ws_val = wb_val[sheet_name]

        wb_form = openpyxl.load_workbook(str(path), data_only=False)
        ws_form = wb_form[sheet_name]

        data: list[list[dict[str, Any]]] = []
        for row_val, row_form in zip(ws_val[rng], ws_form[rng]):
            row_data = []
            for cell_v, cell_f in zip(row_val, row_form):
                raw = cell_f.value
                formula = raw if isinstance(raw, str) and raw.startswith("=") else None
                row_data.append(
                    {
                        "cell": cell_v.coordinate,
                        "value": cell_v.value,
                        "formula": formula,
                    }
                )
            data.append(row_data)

        wb_val.close()
        wb_form.close()

        progress.append(ok(f"Read range {rng}", f"{cell_count} cells from '{sheet_name}'"))
        result: dict[str, Any] = {
            "success": True,
            "sheet": sheet_name,
            "range": rng,
            "cell_count": cell_count,
            "data": data,
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


def search_cells(
    file_path: str,
    sheet_name: str,
    query: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """Scan cell values for text matching query. Returns matching addresses only."""
    progress: list[dict[str, Any]] = []
    try:
        if not query:
            progress.append(fail("Query cannot be empty"))
            return {
                "success": False,
                "error": "query cannot be empty",
                "hint": "Provide a non-empty search string.",
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

        cap = min(max_results, get_max_search_results())

        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
        if sheet_name not in wb.sheetnames:
            wb.close()
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]
        matches: list[dict[str, Any]] = []
        query_lower = query.lower()
        total_scanned = 0

        for row in ws.iter_rows(values_only=False):
            for cell in row:
                total_scanned += 1
                if cell.value is not None and query_lower in str(cell.value).lower():
                    matches.append({"cell": cell.coordinate, "value": cell.value})
                    if len(matches) >= cap:
                        break
            if len(matches) >= cap:
                break

        wb.close()

        truncated = len(matches) >= cap
        progress.append(
            ok(
                f"Found {len(matches)} match(es) for '{query}'",
                f"scanned {total_scanned} cells",
            )
        )
        result: dict[str, Any] = {
            "success": True,
            "sheet": sheet_name,
            "query": query,
            "matches": matches,
            "total_cells_scanned": total_scanned,
            "truncated": truncated,
            "progress": progress,
        }
        if not matches:
            result["hint"] = "Try a different search term or check the sheet name."
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


def set_cell(
    file_path: str, sheet_name: str, cell_address: str, value: Any, open_after: bool = False
) -> dict[str, Any]:
    """Write a value to a single cell by address."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    addr = cell_address.upper()
    try:
        if not _validate_cell(addr):
            progress.append(fail(f"Invalid cell address: {cell_address}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {cell_address}",
                "hint": "Use Excel notation like B5 or C12.",
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
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]
        ws[addr] = value
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "set_cell",
            "sheet": sheet_name,
            "cell": addr,
            "value": value,
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


def set_range(
    file_path: str,
    sheet_name: str,
    start_cell: str,
    data: list[list[Any]],
    open_after: bool = False,
) -> dict[str, Any]:
    """Write a 2D list of values starting at start_cell."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    addr = start_cell.upper()
    try:
        if not _validate_cell(addr):
            progress.append(fail(f"Invalid start cell: {start_cell}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {start_cell}",
                "hint": "Use Excel notation like B5 or C12.",
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
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]

        # Parse start cell into row/col
        col_letter = re.sub(r"\d", "", addr)
        start_row = int(re.sub(r"[A-Z]", "", addr))
        start_col = column_index_from_string(col_letter)

        total_cells = 0
        for r_offset, row_data in enumerate(data):
            for c_offset, val in enumerate(row_data):
                ws.cell(
                    row=start_row + r_offset,
                    column=start_col + c_offset,
                    value=val,
                )
                total_cells += 1

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "set_range",
            "sheet": sheet_name,
            "start_cell": addr,
            "rows_written": len(data),
            "cells_written": total_cells,
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


def insert_row(
    file_path: str, sheet_name: str, row_index: int, open_after: bool = False
) -> dict[str, Any]:
    """Insert an empty row at row_index (1-based), shifting existing rows down."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
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
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]
        ws.insert_rows(row_index)
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "insert_row",
            "sheet": sheet_name,
            "row_index": row_index,
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


def delete_row(
    file_path: str, sheet_name: str, row_index: int, open_after: bool = False
) -> dict[str, Any]:
    """Remove row at row_index (1-based), shifting remaining rows up."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
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
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws = wb[sheet_name]
        max_row = ws.max_row or 0
        if row_index < 1 or row_index > max_row:
            progress.append(fail(f"Row {row_index} out of range", f"sheet has {max_row} rows"))
            return {
                "success": False,
                "error": f"row_index {row_index} out of range (1-{max_row})",
                "hint": "Use list_sheets to get current row count.",
                "backup": backup,
                "progress": progress,
                "token_estimate": 15,
            }

        ws.delete_rows(row_index)
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "delete_row",
            "sheet": sheet_name,
            "row_index": row_index,
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


def add_sheet(file_path: str, sheet_name: str = "", open_after: bool = False) -> dict[str, Any]:
    """Create a new worksheet, optionally with a given name."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
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

        if sheet_name:
            if sheet_name in wb.sheetnames:
                progress.append(warn(f"Sheet '{sheet_name}' already exists"))
                return {
                    "success": False,
                    "error": f"Sheet '{sheet_name}' already exists",
                    "hint": "Choose a different name or delete the existing sheet first.",
                    "backup": backup,
                    "progress": progress,
                    "token_estimate": 15,
                }
            ws = wb.create_sheet(title=sheet_name)
        else:
            ws = wb.create_sheet()
            sheet_name = ws.title

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"Created sheet '{sheet_name}'"))
        result: dict[str, Any] = {
            "success": True,
            "op": "add_sheet",
            "sheet": sheet_name,
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
