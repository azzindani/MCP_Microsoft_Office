"""Document diff engine — paragraph, cell, and shape-level comparison."""

import difflib
from typing import Any

from .file_utils import scrub_repr

MAX_CHANGED_CELLS = 500


def diff_docx(path_a: str, path_b: str) -> dict[str, Any]:
    """
    Compare two .docx files at paragraph level.

    Returns structured diff with added, removed, changed paragraphs.
    """
    try:
        from docx import Document  # type: ignore[import-untyped]

        doc_a = Document(path_a)
        doc_b = Document(path_b)

        paras_a = [{"index": i, "text": p.text, "style": p.style.name} for i, p in enumerate(doc_a.paragraphs)]  # type: ignore[reportOptionalMemberAccess]
        paras_b = [{"index": i, "text": p.text, "style": p.style.name} for i, p in enumerate(doc_b.paragraphs)]  # type: ignore[reportOptionalMemberAccess]

        texts_a = [p["text"] for p in paras_a]
        texts_b = [p["text"] for p in paras_b]

        matcher = difflib.SequenceMatcher(None, texts_a, texts_b, autojunk=False)

        changes: list[dict[str, Any]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            changes.append(
                {
                    "type": tag,
                    "a_range": [i1, i2],
                    "b_range": [j1, j2],
                    "a_text": texts_a[i1:i2],
                    "b_text": texts_b[j1:j2],
                }
            )

        summary = _summarise_docx_diff(changes, len(paras_a), len(paras_b))

        return {
            "success": True,
            "file_a": path_a,
            "file_b": path_b,
            "paragraph_count_a": len(paras_a),
            "paragraph_count_b": len(paras_b),
            "changes": changes,
            "change_count": len(changes),
            "summary": summary,
        }
    except Exception as e:
        return {
            "success": False,
            "error": scrub_repr(e),
            "hint": "Check that both paths point to valid .docx files.",
        }


def diff_xlsx(path_a: str, path_b: str, sheet_name: str | None = None) -> dict[str, Any]:
    """
    Compare two .xlsx files at cell level.

    Returns structured diff with changed cells by sheet.
    If sheet_name provided, only diff that sheet.
    """
    try:
        import openpyxl  # type: ignore[import-untyped]

        wb_a = openpyxl.load_workbook(path_a, data_only=True)
        wb_b = openpyxl.load_workbook(path_b, data_only=True)

        sheets_a = set(wb_a.sheetnames)
        sheets_b = set(wb_b.sheetnames)

        result: dict[str, Any] = {
            "success": True,
            "added_sheets": list(sheets_b - sheets_a),
            "removed_sheets": list(sheets_a - sheets_b),
            "sheet_diffs": {},
        }

        common = sheets_a & sheets_b
        if sheet_name:
            common = {sheet_name} if sheet_name in common else set()

        total_changes = 0
        truncated = False

        for name in sorted(common):
            ws_a = wb_a[name]
            ws_b = wb_b[name]
            changed_cells: list[dict[str, Any]] = []

            # Collect all cell coordinates from both sheets
            all_coords: set[str] = set()
            for row in ws_a.iter_rows():
                for cell in row:
                    all_coords.add(cell.coordinate)
            for row in ws_b.iter_rows():
                for cell in row:
                    all_coords.add(cell.coordinate)

            for coord in sorted(all_coords):
                val_a = ws_a[coord].value if coord in ws_a else None  # type: ignore[reportOperatorIssue]
                val_b = ws_b[coord].value if coord in ws_b else None  # type: ignore[reportOperatorIssue]
                if val_a != val_b:
                    changed_cells.append({"cell": coord, "old": val_a, "new": val_b})
                    total_changes += 1
                    if total_changes >= MAX_CHANGED_CELLS:
                        truncated = True
                        break

            if changed_cells:
                result["sheet_diffs"][name] = {
                    "changed_cells": changed_cells,
                    "change_count": len(changed_cells),
                }
            if truncated:
                break

        if truncated:
            result["truncated"] = True
            result["total_changes_approx"] = f">{MAX_CHANGED_CELLS}"

        result["summary"] = _summarise_xlsx_diff(result)
        return result

    except Exception as e:
        return {
            "success": False,
            "error": scrub_repr(e),
            "hint": "Check that both paths point to valid .xlsx files.",
        }


def diff_pptx(path_a: str, path_b: str) -> dict[str, Any]:
    """
    Compare two .pptx files at shape-text level.

    Returns structured diff with changed text per slide per shape.
    """
    try:
        from pptx import Presentation  # type: ignore[import-untyped]

        prs_a = Presentation(path_a)
        prs_b = Presentation(path_b)

        count_a = len(prs_a.slides)
        count_b = len(prs_b.slides)

        changes: list[dict[str, Any]] = []
        for i, (slide_a, slide_b) in enumerate(zip(prs_a.slides, prs_b.slides)):
            shapes_a = {s.name: s.text_frame.text for s in slide_a.shapes if s.has_text_frame}  # type: ignore[reportAttributeAccessIssue]
            shapes_b = {s.name: s.text_frame.text for s in slide_b.shapes if s.has_text_frame}  # type: ignore[reportAttributeAccessIssue]

            all_names = set(shapes_a) | set(shapes_b)
            for name in sorted(all_names):
                t_a = shapes_a.get(name)
                t_b = shapes_b.get(name)
                if t_a != t_b:
                    changes.append(
                        {
                            "slide_index": i,
                            "shape_name": name,
                            "old_text": t_a,
                            "new_text": t_b,
                        }
                    )

        summary = _summarise_pptx_diff(changes, count_a, count_b)

        return {
            "success": True,
            "slide_count_a": count_a,
            "slide_count_b": count_b,
            "slide_count_changed": count_a != count_b,
            "text_changes": changes,
            "change_count": len(changes),
            "summary": summary,
        }
    except Exception as e:
        return {
            "success": False,
            "error": scrub_repr(e),
            "hint": "Check that both paths point to valid .pptx files.",
        }


def format_diff_as_text(diff: dict[str, Any]) -> str:
    """Format a diff dict as a human-readable unified-diff-style string."""
    lines: list[str] = []

    if not diff.get("success"):
        return f"Diff failed: {diff.get('error', 'unknown error')}"

    summary = diff.get("summary", "")
    if summary:
        lines.append(summary)
        lines.append("")

    # DOCX diff
    if "paragraph_count_a" in diff:
        for change in diff.get("changes", []):
            for text in change.get("a_text", []):
                lines.append(f"- {text[:120]}")
            for text in change.get("b_text", []):
                lines.append(f"+ {text[:120]}")

    # XLSX diff
    if "sheet_diffs" in diff:
        for sheet, sdata in diff["sheet_diffs"].items():
            lines.append(f"Sheet: {sheet}")
            for c in sdata.get("changed_cells", []):
                lines.append(f"  {c['cell']}: {c['old']!r} → {c['new']!r}")

    # PPTX diff
    if "text_changes" in diff:
        for change in diff["text_changes"]:
            lines.append(f"Slide {change['slide_index']} / {change['shape_name']}:")
            old = (change["old_text"] or "")[:80]
            new = (change["new_text"] or "")[:80]
            lines.append(f"  - {old}")
            lines.append(f"  + {new}")

    return "\n".join(lines)


def _summarise_docx_diff(changes: list[dict[str, Any]], count_a: int, count_b: int) -> str:
    if not changes:
        return "No changes detected."
    n_changed = sum(1 for c in changes if c["type"] == "replace")
    n_added = sum(1 for c in changes if c["type"] == "insert")
    n_deleted = sum(1 for c in changes if c["type"] == "delete")
    parts = []
    if n_changed:
        parts.append(f"{n_changed} paragraph{'s' if n_changed != 1 else ''} changed")
    if n_added:
        parts.append(f"{n_added} paragraph{'s' if n_added != 1 else ''} added")
    if n_deleted:
        parts.append(f"{n_deleted} paragraph{'s' if n_deleted != 1 else ''} deleted")
    return ". ".join(parts) + "."


def _summarise_xlsx_diff(result: dict[str, Any]) -> str:
    sheet_diffs = result.get("sheet_diffs", {})
    added = result.get("added_sheets", [])
    removed = result.get("removed_sheets", [])
    parts = []
    total = sum(v["change_count"] for v in sheet_diffs.values())
    if total:
        parts.append(f"{total} cell{'s' if total != 1 else ''} changed")
    if added:
        parts.append(f"{len(added)} sheet{'s' if len(added) != 1 else ''} added")
    if removed:
        parts.append(f"{len(removed)} sheet{'s' if len(removed) != 1 else ''} removed")
    if result.get("truncated"):
        parts.append("(truncated at 500 changes)")
    return ". ".join(parts) + "." if parts else "No changes detected."


def _summarise_pptx_diff(changes: list[dict[str, Any]], count_a: int, count_b: int) -> str:
    if not changes and count_a == count_b:
        return "No changes detected."
    parts = []
    if changes:
        parts.append(f"{len(changes)} shape text{'s' if len(changes) != 1 else ''} changed")
    if count_a != count_b:
        diff = count_b - count_a
        parts.append(f"Slide count changed: {count_a} → {count_b} ({'added' if diff > 0 else 'removed'} {abs(diff)})")
    return ". ".join(parts) + "."
