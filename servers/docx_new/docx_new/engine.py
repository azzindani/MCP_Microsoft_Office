"""DOCX New engine — create Word documents from scratch, no MCP imports."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

# Allow imports from repo root (shared/)
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.file_utils import embed_content  # noqa: E402
from shared.platform_utils import open_file, resolve_output_path  # noqa: E402
from shared.progress import fail, info, ok, warn  # noqa: E402

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _token_estimate(obj: Any) -> int:
    return len(str(obj)) // 4


def _count_occurrences(doc: Any, needle: str) -> int:
    """Count paragraphs (incl. table cells) containing needle.

    docxedit.replace_string() has no return statement (always None), so
    callers must count occurrences themselves before/independent of calling it.
    """
    n = sum(1 for p in doc.paragraphs if needle in p.text)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                n += sum(1 for p in cell.paragraphs if needle in p.text)
    return n


def _ensure_parent(path: Path) -> None:
    """Create parent directories if they do not exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def _open_if_requested(path: Path, open_after: bool, progress: list[dict[str, Any]]) -> None:
    if open_after:
        open_file(path)
        progress.append(ok(f"Opened {path.name} in default app"))


def _err(progress: list[dict[str, Any]], error: str, hint: str) -> dict[str, Any]:
    return {
        "success": False,
        "error": error,
        "hint": hint,
        "progress": progress,
        "token_estimate": _token_estimate(progress),
    }


# ---------------------------------------------------------------------------
# Public engine functions
# ---------------------------------------------------------------------------


def create_document(output_path: str, open_after: bool = True, return_content: bool = False) -> dict[str, Any]:
    """Create a blank Word document and save to output_path."""
    progress: list[dict[str, Any]] = []
    try:
        from docx import Document  # type: ignore[import-untyped]

        path = resolve_output_path(output_path, "document.docx")
        _ensure_parent(path)
        progress.append(info("Creating blank document", path.name))

        doc = Document()
        doc.save(str(path))
        progress.append(ok(f"Saved {path.name}", str(path.parent)))

        _open_if_requested(path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "create_document",
            "output": str(path),
            "output_name": path.name,
            "progress": progress,
        }
        embed_content(result, path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("create_document failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Check that output_path is a valid writable path ending in .docx.",
        )


def create_from_text(
    output_path: str,
    paragraphs: list[dict[str, Any]],
    open_after: bool = True,
    return_content: bool = False,
) -> dict[str, Any]:
    """Create a Word document from a list of {text, style} paragraph dicts."""
    progress: list[dict[str, Any]] = []
    try:
        from docx import Document  # type: ignore[import-untyped]

        if not isinstance(paragraphs, list):
            progress.append(fail("paragraphs must be a list of dicts"))
            return _err(
                progress,
                "paragraphs must be a list",
                'Pass a list like [{"text": "Hello", "style": "Normal"}].',
            )

        path = resolve_output_path(output_path, "document.docx")
        _ensure_parent(path)
        progress.append(info(f"Creating document from {len(paragraphs)} paragraphs", path.name))

        doc = Document()
        added = 0
        for item in paragraphs:
            text = item.get("text", "") if isinstance(item, dict) else str(item)
            style = item.get("style", "Normal") if isinstance(item, dict) else "Normal"
            if not style:
                style = "Normal"
            try:
                doc.add_paragraph(text, style=style)
            except KeyError:
                # Style not found — fall back to Normal
                progress.append(warn(f"Style '{style}' not found, using Normal"))
                doc.add_paragraph(text, style="Normal")
            added += 1

        doc.save(str(path))
        progress.append(ok(f"Saved {path.name}", f"{added} paragraphs written"))

        _open_if_requested(path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "create_from_text",
            "output": str(path),
            "output_name": path.name,
            "paragraph_count": added,
            "progress": progress,
        }
        embed_content(result, path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("create_from_text failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Ensure paragraphs is a list of dicts with 'text' and optional 'style' keys.",
        )


def create_from_sections(
    output_path: str,
    title: str,
    sections: list[dict[str, Any]],
    open_after: bool = True,
    return_content: bool = False,
) -> dict[str, Any]:
    """Create a structured document from a title and list of {heading, body} sections."""
    progress: list[dict[str, Any]] = []
    try:
        from docx import Document  # type: ignore[import-untyped]

        if not isinstance(sections, list):
            progress.append(fail("sections must be a list of dicts"))
            return _err(
                progress,
                "sections must be a list",
                'Pass a list like [{"heading": "Intro", "body": "Text here"}].',
            )

        path = resolve_output_path(output_path, "document.docx")
        _ensure_parent(path)
        progress.append(info("Creating structured document", path.name))

        doc = Document()

        # Title as Heading 1
        doc.add_paragraph(title, style="Heading 1")
        progress.append(ok(f"Added title: {title[:40]}"))

        section_count = 0
        for sec in sections:
            heading = sec.get("heading", "") if isinstance(sec, dict) else ""
            body = sec.get("body", "") if isinstance(sec, dict) else str(sec)
            if heading:
                doc.add_paragraph(heading, style="Heading 2")
            if body:
                doc.add_paragraph(body, style="Normal")
            section_count += 1

        doc.save(str(path))
        progress.append(ok(f"Saved {path.name}", f"{section_count} sections written"))

        _open_if_requested(path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "create_from_sections",
            "output": str(path),
            "output_name": path.name,
            "section_count": section_count,
            "progress": progress,
        }
        embed_content(result, path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("create_from_sections failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Ensure sections is a list of dicts with 'heading' and 'body' keys.",
        )


def create_from_template(
    template_path: str,
    output_path: str,
    substitutions: dict[str, str],
    open_after: bool = True,
    return_content: bool = False,
) -> dict[str, Any]:
    """Copy a .docx template, apply text substitutions, save to output_path."""
    progress: list[dict[str, Any]] = []
    try:
        import shutil

        import docxedit  # type: ignore[import-untyped]
        from docx import Document  # type: ignore[import-untyped]

        tpl_path = Path(template_path).resolve()
        if not tpl_path.exists():
            progress.append(fail("Template not found", str(tpl_path)))
            return _err(
                progress,
                f"File not found: {template_path}",
                "Check that template_path is an absolute path to an existing .docx file.",
            )
        if tpl_path.suffix.lower() != ".docx":
            progress.append(fail("Template is not a .docx file", tpl_path.suffix))
            return _err(
                progress,
                f"Expected .docx file, got {tpl_path.suffix}",
                "Use the correct server for this file type.",
            )

        out_path = resolve_output_path(output_path, "document.docx")
        _ensure_parent(out_path)

        progress.append(ok(f"Opened template {tpl_path.name}"))

        # Copy template to output location first
        shutil.copy2(str(tpl_path), str(out_path))

        # Open the copy and apply substitutions using run-level editing
        doc = Document(str(out_path))

        if not isinstance(substitutions, dict):
            progress.append(fail("substitutions must be a dict"))
            return _err(
                progress,
                "substitutions must be a dict",
                'Pass a dict like {"PLACEHOLDER": "replacement value"}.',
            )

        applied = 0
        for old_str, new_str in substitutions.items():
            old_s = str(old_str)
            new_s = str(new_str)
            # docxedit.replace_string operates on runs — never assigns .text directly
            count = _count_occurrences(doc, old_s)
            docxedit.replace_string(doc, old_s, new_s)
            if count:
                progress.append(
                    ok(
                        f"Replaced '{old_s}' → '{new_s}'",
                        f"{count} occurrence{'s' if count != 1 else ''}",
                    )
                )
                applied += count
            else:
                progress.append(warn(f"Placeholder '{old_s}' not found in template"))

        doc.save(str(out_path))
        progress.append(ok(f"Saved {out_path.name}", f"{applied} total substitutions"))

        _open_if_requested(out_path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "create_from_template",
            "output": str(out_path),
            "output_name": out_path.name,
            "substitutions_applied": applied,
            "progress": progress,
        }
        embed_content(result, out_path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("create_from_template failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Check that template_path points to a valid .docx file and substitutions is a dict.",
        )


def create_letter(
    output_path: str,
    from_name: str,
    to_name: str,
    subject: str,
    body: str,
    open_after: bool = True,
    return_content: bool = False,
) -> dict[str, Any]:
    """Create a formatted business letter .docx."""
    progress: list[dict[str, Any]] = []
    try:
        from docx import Document  # type: ignore[import-untyped]

        path = resolve_output_path(output_path, "document.docx")
        _ensure_parent(path)
        progress.append(info("Creating business letter", path.name))

        doc = Document()

        # Sender name
        sender_para = doc.add_paragraph()
        sender_run = sender_para.add_run(from_name)
        sender_run.bold = True

        # Blank line
        doc.add_paragraph()

        # Recipient
        doc.add_paragraph(f"To: {to_name}")

        # Blank line
        doc.add_paragraph()

        # Subject line — bold
        subject_para = doc.add_paragraph()
        subject_run = subject_para.add_run(f"Subject: {subject}")
        subject_run.bold = True

        # Blank line
        doc.add_paragraph()

        # Body paragraphs — split on newlines
        body_paras = body.split("\n")
        for line in body_paras:
            doc.add_paragraph(line)

        # Blank line before closing
        doc.add_paragraph()

        # Closing with sender name
        closing_para = doc.add_paragraph()
        closing_para.add_run("Sincerely,")
        doc.add_paragraph()
        sign_para = doc.add_paragraph()
        sign_run = sign_para.add_run(from_name)
        sign_run.bold = True

        doc.save(str(path))
        progress.append(ok(f"Saved {path.name}", f"From: {from_name} | To: {to_name}"))

        _open_if_requested(path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "create_letter",
            "output": str(path),
            "output_name": path.name,
            "from_name": from_name,
            "to_name": to_name,
            "subject": subject,
            "progress": progress,
        }
        embed_content(result, path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("create_letter failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Check that output_path is a valid writable path ending in .docx.",
        )


def merge_documents(
    file_paths: list,
    output_path: str,
    add_page_break: bool = True,
    open_after: bool = True,
    return_content: bool = False,
) -> dict[str, Any]:
    """Merge multiple .docx files into one document."""
    progress: list[dict[str, Any]] = []
    try:
        import copy

        from docx import Document  # type: ignore[import-untyped]
        from docx.oxml import OxmlElement  # type: ignore[import-untyped]
        from docx.oxml.ns import qn  # type: ignore[import-untyped]

        if not isinstance(file_paths, list) or len(file_paths) == 0:
            progress.append(fail("file_paths must be a non-empty list"))
            return _err(
                progress,
                "file_paths must be a non-empty list",
                "Pass a list of absolute paths to .docx files.",
            )

        out_path = resolve_output_path(output_path, "document.docx")
        if out_path.suffix.lower() != ".docx":
            progress.append(fail("output_path must end in .docx", out_path.suffix))
            return _err(
                progress,
                f"Expected .docx output_path, got {out_path.suffix}",
                "Set output_path to a path ending in .docx.",
            )

        # Validate all source files up front
        resolved: list[Path] = []
        for fp in file_paths:
            p = Path(str(fp)).resolve()
            if not p.exists():
                progress.append(fail("File not found", str(p)))
                return _err(
                    progress,
                    f"File not found: {fp}",
                    "Check that all file_paths exist and are accessible.",
                )
            if p.suffix.lower() != ".docx":
                progress.append(fail("Not a .docx file", p.suffix))
                return _err(
                    progress,
                    f"Expected .docx file, got {p.suffix}",
                    "All file_paths must point to .docx files.",
                )
            resolved.append(p)

        _ensure_parent(out_path)
        progress.append(info(f"Merging {len(resolved)} documents", out_path.name))

        base_doc = Document()
        # Remove the default empty paragraph python-docx adds to a new document
        for para in base_doc.paragraphs:
            p_elem = para._element
            p_elem.getparent().remove(p_elem)

        for idx, src_path in enumerate(resolved):
            src_doc = Document(str(src_path))

            if add_page_break and idx > 0:
                page_para = base_doc.add_paragraph()
                run = page_para.add_run()
                break_elem = OxmlElement("w:br")
                break_elem.set(qn("w:type"), "page")
                run._r.append(break_elem)
                progress.append(info(f"Added page break before {src_path.name}"))

            for para in src_doc.paragraphs:
                new_para = copy.deepcopy(para._element)
                base_doc.element.body.append(new_para)

            progress.append(ok(f"Merged {src_path.name}"))

        base_doc.save(str(out_path))
        progress.append(ok(f"Saved {out_path.name}", f"{len(resolved)} documents merged"))

        _open_if_requested(out_path, open_after, progress)

        result: dict[str, Any] = {
            "success": True,
            "op": "merge_documents",
            "output": str(out_path),
            "output_name": out_path.name,
            "merged_count": len(resolved),
            "progress": progress,
        }
        embed_content(result, out_path, return_content)
        result["token_estimate"] = _token_estimate(result)
        return result
    except Exception as exc:
        logger.warning("merge_documents failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Check that all file_paths are valid .docx files and output_path is writable.",
        )


def batch_create_from_template(
    template_path: str,
    data_list: list,
    output_dir: str,
    filename_key: str = "",
    open_after: bool = False,
) -> dict[str, Any]:
    """Generate N .docx files from a template + list of {key:value} dicts."""
    progress: list[dict[str, Any]] = []
    try:
        import shutil

        import docxedit  # type: ignore[import-untyped]
        from docx import Document  # type: ignore[import-untyped]

        tpl_path = Path(template_path).resolve()
        if not tpl_path.exists():
            progress.append(fail("Template not found", str(tpl_path)))
            return _err(
                progress,
                f"File not found: {template_path}",
                "Check that template_path is an absolute path to an existing .docx file.",
            )
        if tpl_path.suffix.lower() != ".docx":
            progress.append(fail("Template is not a .docx file", tpl_path.suffix))
            return _err(
                progress,
                f"Expected .docx file, got {tpl_path.suffix}",
                "Use the correct server for this file type.",
            )

        if not isinstance(data_list, list) or len(data_list) == 0:
            progress.append(fail("data_list must be a non-empty list"))
            return _err(
                progress,
                "data_list must be a non-empty list of dicts",
                'Pass a list like [{"NAME": "Alice", "DATE": "April 1"}].',
            )

        out_dir = resolve_output_path(output_dir, "documents")
        out_dir.mkdir(parents=True, exist_ok=True)
        progress.append(info(f"Generating {len(data_list)} documents", str(out_dir)))

        created_files: list[str] = []

        for idx, data_dict in enumerate(data_list):
            if not isinstance(data_dict, dict):
                progress.append(warn(f"Item {idx} is not a dict, skipping"))
                continue

            # Determine output filename
            if filename_key and filename_key in data_dict:
                stem = str(data_dict[filename_key])
            else:
                stem = f"document_{idx + 1:03d}"

            out_file = out_dir / f"{stem}.docx"

            # Copy template to output location
            shutil.copy2(str(tpl_path), str(out_file))

            # Open copy and apply substitutions using run-level editing
            doc = Document(str(out_file))
            for key, value in data_dict.items():
                placeholder = "{{" + str(key) + "}}"
                docxedit.replace_string(doc, placeholder, str(value))

            doc.save(str(out_file))
            created_files.append(out_file.name)
            progress.append(ok(f"Created {out_file.name}"))

            if open_after:
                open_file(out_file)

        progress.append(ok("Batch complete", f"{len(created_files)} of {len(data_list)} created"))

        return {
            "success": True,
            "op": "batch_create",
            "output_dir": str(out_dir),
            "created_count": len(created_files),
            "files": created_files,
            "progress": progress,
            "token_estimate": _token_estimate(progress),
        }
    except Exception as exc:
        logger.warning("batch_create_from_template failed: %s", exc)
        progress.append(fail(str(exc)))
        return _err(
            progress,
            str(exc),
            "Check template_path, output_dir permissions, and that data_list is a list of dicts.",
        )
