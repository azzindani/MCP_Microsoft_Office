"""Validate patch op arrays before applying them to documents."""

import re
from typing import Any

MAX_OPS_PER_BATCH = 50

# Required fields per op type
_OP_REQUIRED_FIELDS: dict[str, list[str]] = {
    # DOCX ops
    "replace_text": ["match", "new_text"],
    "insert_after": ["match", "new_text"],
    "delete_paragraph": ["match"],
    "replace_table_cell": ["table_index", "row", "col", "new_text"],
    # XLSX ops
    "set_cell": ["sheet", "cell", "value"],
    "set_formula": ["sheet", "cell", "formula"],
    "set_conditional_format": ["sheet", "range", "rule", "value", "color"],
    # PPTX ops
    "set_text": ["slide_index", "shape_name", "new_text"],
    "add_slide": ["after_index", "layout", "title"],
}

# Regex for DOCX section addresses: §1, §1.2, §1.p4, §1.t0, §1.t0.r3.c1, p47
_DOCX_ADDRESS_RE = re.compile(r"^(§\d+(\.\d+)*(\.p\d+|\.t\d+(\.\w+)*)?|p\d+)$")

# Regex for Excel cell notation: A1, B5, Z100, AA1
_XLSX_ADDRESS_RE = re.compile(r"^[A-Z]{1,3}\d+$")

# Regex for PPTX addresses: slide[N]/shape[name] or slide[N]/shape[name]/pN
_PPTX_ADDRESS_RE = re.compile(r"^slide\[\d+\]/shape\[.+\](/p\d+)?$")


def validate_ops(ops: Any, allowed_ops: list[str]) -> tuple[bool, str]:
    """
    Validate a patch op array before applying.

    Returns (True, "") on valid.
    Returns (False, error_message) on invalid.
    """
    if not isinstance(ops, list):
        return False, f"ops must be a list, got {type(ops).__name__}"

    if len(ops) > MAX_OPS_PER_BATCH:
        return (
            False,
            f"Too many ops: {len(ops)}. Maximum is {MAX_OPS_PER_BATCH} per batch.",
        )

    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            return False, f"ops[{i}] must be a dict, got {type(op).__name__}"

        if "op" not in op:
            return False, f"ops[{i}] missing required 'op' key"

        op_name = op["op"]
        if op_name not in allowed_ops:
            return (
                False,
                f"ops[{i}]: unknown op '{op_name}'. Allowed: {allowed_ops}",
            )

        # Check required fields for known op types
        required = _OP_REQUIRED_FIELDS.get(op_name, [])
        for field in required:
            if field not in op:
                return (
                    False,
                    f"ops[{i}] ({op_name}): missing required field '{field}'",
                )

        # Validate formula starts with =
        if op_name == "set_formula":
            formula = op.get("formula", "")
            if not isinstance(formula, str) or not formula.startswith("="):
                return (
                    False,
                    f"ops[{i}] (set_formula): formula must start with '=', got '{formula}'",
                )

        # Validate cell address format for XLSX ops
        if op_name in ("set_cell", "set_formula", "set_conditional_format"):
            cell = op.get("cell") or op.get("range", "")
            if cell and not _is_valid_xlsx_address(cell):
                return (
                    False,
                    f"ops[{i}] ({op_name}): invalid cell/range address '{cell}'",
                )

    return True, ""


def validate_docx_address(address: str) -> bool:
    """Return True if address matches DOCX section address format."""
    return bool(_DOCX_ADDRESS_RE.match(address))


def validate_xlsx_address(address: str) -> bool:
    """Return True if address matches Excel cell or range notation."""
    return _is_valid_xlsx_address(address)


def validate_pptx_address(address: str) -> bool:
    """Return True if address matches PPTX shape address format."""
    return bool(_PPTX_ADDRESS_RE.match(address))


def _is_valid_xlsx_address(address: str) -> bool:
    """Check single cell (A1) or range (A1:B5) notation."""
    if ":" in address:
        parts = address.split(":")
        if len(parts) != 2:
            return False
        return all(_XLSX_ADDRESS_RE.match(p) for p in parts)
    return bool(_XLSX_ADDRESS_RE.match(address))
