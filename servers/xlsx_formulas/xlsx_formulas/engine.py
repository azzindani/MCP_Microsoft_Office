"""XLSX Formulas engine — pure openpyxl logic, zero MCP imports."""

import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

from shared.file_utils import hint_for_error, resolve_path
from shared.live_edit import notify_reload
from shared.platform_utils import open_file
from shared.progress import fail, ok
from shared.version_control import snapshot

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CELL_RE = re.compile(r"^[A-Z]{1,3}\d+$")
_RANGE_RE = re.compile(r"^[A-Z]{1,3}\d+:[A-Z]{1,3}\d+$")

COLOR_MAP: dict[str, str] = {
    "green": "00FF00",
    "red": "FF0000",
    "yellow": "FFFF00",
    "blue": "0000FF",
}

VALID_RULES = {"greater_than", "less_than", "between", "equal_to"}
VALID_COLORS = set(COLOR_MAP.keys())


def _validate_cell(address: str) -> bool:
    return bool(_CELL_RE.match(address.upper()))


def _validate_range(address: str) -> bool:
    return bool(_RANGE_RE.match(address.upper()))


def _open_wb(path: Path, progress: list[dict[str, Any]]) -> tuple[Any, dict[str, Any] | None]:
    """Load workbook; return (wb, None) on success or (None, error_dict) on fail."""
    if not path.exists():
        progress.append(fail("File not found", str(path)))
        return None, {
            "success": False,
            "error": f"File not found: {path}",
            "hint": "Check that file_path is absolute and the file exists.",
            "progress": progress,
            "token_estimate": 20,
        }
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        progress.append(fail(f"Wrong file type: {path.suffix}"))
        return None, {
            "success": False,
            "error": f"Expected .xlsx file, got {path.suffix}",
            "hint": "Use the correct server for this file type.",
            "progress": progress,
            "token_estimate": 20,
        }
    wb = openpyxl.load_workbook(str(path))
    return wb, None


def _check_sheet(
    wb: Any, sheet_name: str, progress: list[dict[str, Any]], backup: str | None
) -> tuple[Any, dict[str, Any] | None]:
    """Return (ws, None) or (None, error_dict) if sheet missing."""
    if sheet_name not in wb.sheetnames:
        progress.append(fail(f"Sheet '{sheet_name}' not found"))
        return None, {
            "success": False,
            "error": f"Sheet '{sheet_name}' not found",
            "hint": "Use list_sheets to get available sheet names.",
            "backup": backup,
            "progress": progress,
            "token_estimate": 15,
        }
    return wb[sheet_name], None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------


def set_formula(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    formula: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Write a formula string to a cell. Formula must start with '='."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    addr = cell_address.upper()
    try:
        if not formula.startswith("="):
            progress.append(fail("Formula must start with '='", formula))
            return {
                "success": False,
                "error": "Formula must start with '='",
                "hint": "Prefix the formula with '=', e.g. '=SUM(B2:B10)'.",
                "progress": progress,
                "token_estimate": 15,
            }
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
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        ws[addr] = formula
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "set_formula",
            "sheet": sheet_name,
            "cell": addr,
            "formula": formula,
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


def set_named_range(
    file_path: str,
    sheet_name: str,
    range_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Define a named range in the workbook."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        if not range_name.replace("_", "").isalnum():
            progress.append(fail(f"Invalid range name: {range_name}"))
            return {
                "success": False,
                "error": f"Invalid range name: {range_name}",
                "hint": "Range names must be alphanumeric (underscores allowed).",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

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

        attr_text = f"'{sheet_name}'!{range_address}"
        defn = DefinedName(range_name, attr_text=attr_text)
        wb.defined_names[range_name] = defn
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"Defined named range '{range_name}'", attr_text))
        result: dict[str, Any] = {
            "success": True,
            "op": "set_named_range",
            "range_name": range_name,
            "sheet": sheet_name,
            "range_address": range_address,
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


def set_conditional_format(
    file_path: str,
    sheet_name: str,
    range_address: str,
    rule: str,
    value: float,
    color: str,
    value2: float = 0.0,
    open_after: bool = False,
) -> dict[str, Any]:
    """Apply a color-based conditional formatting rule to a range."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        if rule not in VALID_RULES:
            progress.append(fail(f"Unknown rule: {rule}"))
            return {
                "success": False,
                "error": f"Unknown rule: {rule}",
                "hint": f"Allowed rules: {', '.join(sorted(VALID_RULES))}",
                "progress": progress,
                "token_estimate": 15,
            }
        if color not in VALID_COLORS:
            progress.append(fail(f"Unknown color: {color}"))
            return {
                "success": False,
                "error": f"Unknown color: {color}",
                "hint": f"Allowed colors: {', '.join(sorted(VALID_COLORS))}",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        hex_color = COLOR_MAP[color]
        fill = PatternFill(
            start_color=hex_color,
            end_color=hex_color,
            fill_type="solid",
        )

        op_map = {
            "greater_than": "greaterThan",
            "less_than": "lessThan",
            "between": "between",
            "equal_to": "equal",
        }
        operator = op_map[rule]

        if rule == "between":
            rule_obj = CellIsRule(
                operator=operator,
                formula=[str(value), str(value2)],
                fill=fill,
            )
        else:
            rule_obj = CellIsRule(
                operator=operator,
                formula=[str(value)],
                fill=fill,
            )

        ws.conditional_formatting.add(range_address, rule_obj)
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(
            ok(
                f"Applied '{rule}' conditional format",
                f"{range_address} → {color}",
            )
        )
        result: dict[str, Any] = {
            "success": True,
            "op": "set_conditional_format",
            "sheet": sheet_name,
            "range": range_address,
            "rule": rule,
            "value": value,
            "color": color,
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


def set_data_validation(
    file_path: str,
    sheet_name: str,
    range_address: str,
    validation_type: str,
    formula1: str = "",
    formula2: str = "",
    open_after: bool = False,
) -> dict[str, Any]:
    """Add data validation (list, decimal, or whole) to a cell range."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    valid_types = {"list", "decimal", "whole"}
    try:
        if validation_type not in valid_types:
            progress.append(fail(f"Unknown validation type: {validation_type}"))
            return {
                "success": False,
                "error": f"Unknown validation_type: {validation_type}",
                "hint": f"Allowed types: {', '.join(sorted(valid_types))}",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        dv = DataValidation(
            type=validation_type,  # type: ignore[reportArgumentType]
            formula1=formula1 or None,
            formula2=formula2 or None,
            allow_blank=True,
        )
        ws.add_data_validation(dv)
        dv.sqref = range_address

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(
            ok(
                f"Set '{validation_type}' data validation",
                f"{range_address}",
            )
        )
        result: dict[str, Any] = {
            "success": True,
            "op": "set_data_validation",
            "sheet": sheet_name,
            "range": range_address,
            "validation_type": validation_type,
            "formula1": formula1,
            "formula2": formula2,
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


def freeze_panes(
    file_path: str,
    sheet_name: str,
    cell_address: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Freeze rows/columns at cell_address. Empty string to unfreeze."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        addr = cell_address.upper() if cell_address else ""
        if addr and not _validate_cell(addr):
            progress.append(fail(f"Invalid cell address: {cell_address}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {cell_address}",
                "hint": "Use Excel notation like B2. Empty string to unfreeze.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        ws.freeze_panes = addr if addr else None
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        action = f"frozen at {addr}" if addr else "unfrozen"
        progress.append(ok(f"Panes {action}", sheet_name))
        result: dict[str, Any] = {
            "success": True,
            "op": "freeze_panes",
            "sheet": sheet_name,
            "cell_address": addr,
            "frozen": bool(addr),
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


def set_autofilter(
    file_path: str,
    sheet_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Enable AutoFilter on the specified range."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        ws.auto_filter.ref = range_address
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"AutoFilter set on {range_address}", sheet_name))
        result: dict[str, Any] = {
            "success": True,
            "op": "set_autofilter",
            "sheet": sheet_name,
            "range": range_address,
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


def fill_formula_down(
    file_path: str,
    sheet_name: str,
    formula: str,
    start_cell: str,
    end_row: int,
    open_after: bool = False,
) -> dict[str, Any]:
    """Fill formula down from start_cell to end_row, adjusting row references."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        if not formula.startswith("="):
            progress.append(fail("Formula must start with '='", formula))
            return {
                "success": False,
                "error": "Formula must start with '='",
                "hint": "Prefix the formula with '=', e.g. '=B2*C2'.",
                "progress": progress,
                "token_estimate": 15,
            }

        addr = start_cell.upper()
        if not _validate_cell(addr):
            progress.append(fail(f"Invalid start_cell: {start_cell}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {start_cell}",
                "hint": "Use Excel notation like D2 or B5.",
                "progress": progress,
                "token_estimate": 15,
            }

        # Parse column letters and start row from start_cell
        col_match = re.match(r"^([A-Z]+)(\d+)$", addr)
        if not col_match:
            progress.append(fail(f"Cannot parse start_cell: {start_cell}"))
            return {
                "success": False,
                "error": f"Cannot parse cell address: {start_cell}",
                "hint": "Use Excel notation like D2.",
                "progress": progress,
                "token_estimate": 15,
            }
        col_letters = col_match.group(1)
        start_row = int(col_match.group(2))

        if end_row < start_row:
            progress.append(fail(f"end_row {end_row} is before start_row {start_row}"))
            return {
                "success": False,
                "error": f"end_row ({end_row}) must be >= start_row ({start_row})",
                "hint": "end_row is the last row number to fill to.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        # Write formula to each row, adjusting row numbers in cell references
        cells_filled = 0
        for target_row in range(start_row, end_row + 1):
            adjusted = re.sub(
                r"([A-Z]+)(" + str(start_row) + r")\b",
                lambda m, tr=target_row: m.group(1) + str(tr),
                formula,
            )
            ws[f"{col_letters}{target_row}"] = adjusted
            cells_filled += 1

        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(
            ok(
                f"Filled formula down {col_letters}{start_row}:{col_letters}{end_row}",
                f"{cells_filled} cells",
            )
        )
        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "fill_formula_down",
            "sheet": sheet_name,
            "column": col_letters,
            "start_row": start_row,
            "end_row": end_row,
            "cells_filled": cells_filled,
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


def auto_sum(
    file_path: str,
    sheet_name: str,
    data_range: str,
    sum_cell: str,
    function_name: str = "SUM",
    open_after: bool = False,
) -> dict[str, Any]:
    """Write a SUM/AVERAGE/COUNT/MAX/MIN formula for data_range into sum_cell."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    valid_functions = {"SUM", "AVERAGE", "COUNT", "MAX", "MIN"}
    try:
        fn = function_name.upper()
        if fn not in valid_functions:
            progress.append(fail(f"Unknown function: {function_name}"))
            return {
                "success": False,
                "error": f"Unknown function_name: {function_name}",
                "hint": f"Allowed functions: {', '.join(sorted(valid_functions))}",
                "progress": progress,
                "token_estimate": 15,
            }

        if not _validate_range(data_range.upper()):
            progress.append(fail(f"Invalid data_range: {data_range}"))
            return {
                "success": False,
                "error": f"Invalid range address: {data_range}",
                "hint": "Use Excel range notation like B2:B20.",
                "progress": progress,
                "token_estimate": 15,
            }

        addr = sum_cell.upper()
        if not _validate_cell(addr):
            progress.append(fail(f"Invalid sum_cell: {sum_cell}"))
            return {
                "success": False,
                "error": f"Invalid cell address: {sum_cell}",
                "hint": "Use Excel notation like B21.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws, err = _check_sheet(wb, sheet_name, progress, backup)
        if err:
            return err

        formula = f"={fn}({data_range})"
        ws[addr] = formula
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(ok(f"Set {addr} = {formula}", sheet_name))
        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "auto_sum",
            "sheet": sheet_name,
            "sum_cell": addr,
            "formula": formula,
            "data_range": data_range,
            "function_name": fn,
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


def convert_to_values(
    file_path: str,
    sheet_name: str,
    range_address: str,
    open_after: bool = False,
) -> dict[str, Any]:
    """Replace formula cells with their calculated values in a range."""
    progress: list[dict[str, Any]] = []
    backup: str | None = None
    try:
        if not _validate_range(range_address.upper()):
            progress.append(fail(f"Invalid range: {range_address}"))
            return {
                "success": False,
                "error": f"Invalid range address: {range_address}",
                "hint": "Use Excel range notation like B2:D10.",
                "progress": progress,
                "token_estimate": 15,
            }

        path = resolve_path(file_path)
        wb, err = _open_wb(path, progress)
        if err:
            return err

        # Load a second copy with data_only=True to read evaluated values
        wb_values = openpyxl.load_workbook(str(path), data_only=True)

        if sheet_name not in wb.sheetnames:
            progress.append(fail(f"Sheet '{sheet_name}' not found"))
            wb.close()
            wb_values.close()
            return {
                "success": False,
                "error": f"Sheet '{sheet_name}' not found",
                "hint": "Use list_sheets to get available sheet names.",
                "progress": progress,
                "token_estimate": 15,
            }

        backup = snapshot(str(path))
        progress.append(ok("Snapshot saved", Path(backup).name))

        ws = wb[sheet_name]
        ws_values = wb_values[sheet_name]

        converted = 0
        for row in ws_values[range_address.upper()]:
            for cell_v in row:
                coord = cell_v.coordinate
                cell_w = ws[coord]
                # Only replace formula cells (value starts with "=")
                if isinstance(cell_w.value, str) and cell_w.value.startswith("="):
                    cell_w.value = cell_v.value
                    converted += 1

        wb_values.close()
        wb.save(str(path))
        wb.close()
        if open_after:
            open_file(path)

        progress.append(
            ok(
                f"Converted formulas to values in {range_address}",
                f"{converted} formula{'s' if converted != 1 else ''} replaced",
            )
        )
        progress.append(notify_reload(str(path), "xlsx"))
        result: dict[str, Any] = {
            "success": True,
            "op": "convert_to_values",
            "sheet": sheet_name,
            "range": range_address,
            "formulas_converted": converted,
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
