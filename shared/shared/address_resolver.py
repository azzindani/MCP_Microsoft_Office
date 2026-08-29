"""Address parsing and resolution for surgical document access."""

import re
from dataclasses import dataclass, field
from typing import Any


class AddressError(Exception):
    """Raised when an address cannot be resolved to a document node."""


# ─── DOCX ────────────────────────────────────────────────────────────────────


@dataclass
class DocxNode:
    paragraph: Any = None  # docx.text.paragraph.Paragraph
    table: Any = None  # docx.table.Table
    cell: Any = None  # docx.table._Cell
    para_index: int = -1
    table_index: int = -1
    row_index: int = -1
    col_index: int = -1


@dataclass
class SectionInfo:
    address: str
    heading: str
    level: int
    para_range: list[int]  # [start, end] inclusive
    table_count: int = 0
    sub_sections: list[SectionInfo] = field(default_factory=list)


def build_docx_index(doc: Any) -> dict[str, Any]:
    """
    Scan document and build section index from heading paragraphs.

    Returns dict with:
    - address_scheme: "sectioned" or "flat"
    - sections: list of section dicts with address, heading, level, para_range
    - total_paragraphs: int
    """
    paragraphs = doc.paragraphs
    total = len(paragraphs)

    # Find heading paragraphs
    headings: list[tuple[int, int, str]] = []  # (para_index, level, text)
    for i, p in enumerate(paragraphs):
        style_name = p.style.name
        if style_name.startswith("Heading "):
            try:
                level = int(style_name.split()[-1])
                headings.append((i, level, p.text))
            except ValueError, IndexError:
                pass

    if not headings:
        return {
            "address_scheme": "flat",
            "total_paragraphs": total,
            "sections": [],
            "sections_cut_at_heading_level": 1,
            "heading_counts": {},
        }

    # How many headings there are at each level. A section is cut at level 1
    # only, so a document whose headings are a title plus four Heading 2s is
    # one section covering everything -- while get_document_outline lists five
    # headings for the same file. Both are right and they read as a
    # contradiction, so the index says which level it cut on and what it passed
    # over. The scheme is not changed: every existing §N address would move.
    heading_levels: dict[int, int] = {}
    for _, level, _ in headings:
        heading_levels[level] = heading_levels.get(level, 0) + 1

    # Build section list from top-level headings (level 1)
    sections: list[dict[str, Any]] = []
    section_num = 0

    for h_idx, (para_idx, level, text) in enumerate(headings):
        if level != 1:
            continue
        section_num += 1

        # Find end of this section (next level-1 heading or end of doc)
        end_idx = total - 1
        for future_para_idx, future_level, _ in headings[h_idx + 1 :]:
            if future_level == 1:
                end_idx = future_para_idx - 1
                break

        sections.append(
            {
                "address": f"§{section_num}",
                "heading": text,
                "level": level,
                "para_range": [para_idx, end_idx],
                "para_count": end_idx - para_idx + 1,
                "table_count": 0,
            }
        )

    return {
        "address_scheme": "sectioned",
        "total_paragraphs": total,
        "sections": sections,
        "sections_cut_at_heading_level": 1,
        "heading_counts": {str(k): v for k, v in sorted(heading_levels.items())},
    }


# One pattern for the §N / §N.pM / §N.tM notation, because there were two and
# they disagreed. fetch_section_content matched only `^§(\d+)$` while labelling
# every paragraph it returned `§N.pM` -- so the addresses the tool printed were
# addresses it refused, and so was the '§1.p3' its own error message offered as
# the example. resolve_docx_address had parsed the full form correctly all
# along. Anything that reads this notation compiles it from here.
_SECTION_ADDRESS = re.compile(r"^§(\d+)(?:\.(\d+))?(?:\.(p\d+|t\d+))?$")

# What to call the notation when refusing one. Written once for the same reason.
_ADDRESS_FORMS = "Use §N for a section, e.g. '§1', or §N.pM for a paragraph inside one, e.g. '§1.p3'."


def resolve_docx_address(doc: Any, address: str) -> DocxNode:
    """
    Parse address string and return the corresponding document node.

    Supported formats:
    - §N — section N (returns first paragraph)
    - §N.pM — paragraph M within section N
    - pN — absolute paragraph N
    - §N.tM — table M within section N (not yet navigated to cell)

    Raises AddressError if address does not resolve to an existing node.
    """
    paragraphs = doc.paragraphs

    # Absolute paragraph address
    if re.match(r"^p\d+$", address):
        idx = int(address[1:])
        if idx < 0 or idx >= len(paragraphs):
            raise AddressError(f"Paragraph index {idx} out of range (0-{len(paragraphs) - 1})")
        return DocxNode(paragraph=paragraphs[idx], para_index=idx)

    # Section address
    section_match = _SECTION_ADDRESS.match(address)
    if not section_match:
        raise AddressError(f"Invalid address format: '{address}'. Use §N, §N.pM, pN, or slide[N]/shape[name] notation.")

    index_data = build_docx_index(doc)
    sections = index_data.get("sections", [])

    section_num = int(section_match.group(1))
    if section_num < 1 or section_num > len(sections):
        raise AddressError(f"Section §{section_num} not found. Document has {len(sections)} sections.")

    section = sections[section_num - 1]
    para_start, para_end = section["para_range"]

    # §N — return section heading paragraph
    if not section_match.group(3):
        return DocxNode(paragraph=paragraphs[para_start], para_index=para_start)

    # §N.pM — paragraph M within section
    item = section_match.group(3)
    if item.startswith("p"):
        rel_idx = int(item[1:])
        abs_idx = para_start + rel_idx
        if abs_idx > para_end:
            raise AddressError(
                f"Paragraph §{section_num}.p{rel_idx} out of range. Section has {para_end - para_start + 1} paragraphs."
            )
        return DocxNode(paragraph=paragraphs[abs_idx], para_index=abs_idx)

    raise AddressError(f"Cannot resolve address: '{address}'")


def fetch_section_content(doc: Any, address: str) -> dict[str, Any]:
    """Return paragraphs in the addressed section."""
    index_data = build_docx_index(doc)

    if index_data["address_scheme"] == "flat":
        # Flat: address must be pN
        if re.match(r"^p\d+$", address):
            idx = int(address[1:])
            paragraphs = doc.paragraphs
            if 0 <= idx < len(paragraphs):
                p = paragraphs[idx]
                return {
                    "address": address,
                    "heading": p.text[:80],
                    "paragraphs": [
                        {
                            "addr": f"p{idx}",
                            "text": p.text,
                            "style": p.style.name,
                        }
                    ],
                    "tables": [],
                }
        raise AddressError(f"Address '{address}' not valid for flat document. Use pN notation.")

    # Sectioned document
    section_match = _SECTION_ADDRESS.match(address)
    if not section_match:
        # The sibling resolver above already names the notation on a bad
        # address; this one just said the address was invalid. A section number
        # is written with a section sign -- not a character anyone types by
        # accident, and not one a caller can guess: '1', 'p1', 'section:1' and
        # 'Introduction' all arrive here and all got the same bare sentence.
        raise AddressError(f"Invalid section address: '{address}'. {_ADDRESS_FORMS}")

    sections = index_data["sections"]
    section_num = int(section_match.group(1))
    if section_num < 1 or section_num > len(sections):
        raise AddressError(f"Section §{section_num} not found. Document has {len(sections)} sections.")

    section = sections[section_num - 1]
    para_start, para_end = section["para_range"]

    paragraphs = doc.paragraphs
    para_list = []
    for abs_idx in range(para_start, para_end + 1):
        p = paragraphs[abs_idx]
        rel_idx = abs_idx - para_start
        para_list.append(
            {
                "addr": f"§{section_num}.p{rel_idx}",
                "text": p.text,
                "style": p.style.name,
            }
        )

    # §N.pM — one paragraph out of the section, addressed the way this function
    # labels it. Sending back an address it just printed used to fail here.
    item = section_match.group(3)
    if item:
        if item.startswith("t"):
            raise AddressError(
                f"'{address}' addresses a table, which fetch_section does not return. "
                "Use list_tables() to find it and read_table() to read it."
            )
        rel_idx = int(item[1:])
        if rel_idx < 0 or rel_idx >= len(para_list):
            raise AddressError(
                f"Paragraph §{section_num}.p{rel_idx} out of range. Section has {len(para_list)} paragraphs."
            )
        para_list = [para_list[rel_idx]]

    return {
        "address": address,
        "heading": section["heading"],
        "paragraphs": para_list,
        "tables": [],
    }


# ─── XLSX ─────────────────────────────────────────────────────────────────────


@dataclass
class XlsxNode:
    cell: Any = None  # openpyxl Cell
    cells: Any = None  # list of cells for range


def build_xlsx_index(wb: Any) -> dict[str, Any]:
    """Scan workbook and build sheet index."""
    sheets = []
    for name in wb.sheetnames:
        ws = wb[name]
        dims = ws.dimensions or "A1:A1"
        headers: list[Any] = []
        first_row = next(ws.iter_rows(min_row=1, max_row=1), None)
        if first_row:
            headers = [cell.value for cell in first_row if cell.value is not None]

        sheets.append(
            {
                "name": name,
                "used_range": dims,
                "headers": headers,
                "data_rows": (ws.max_row or 1) - 1,
                "named_ranges": [],
                "chart_count": len(ws._charts) if hasattr(ws, "_charts") else 0,
            }
        )
    return {"sheets": sheets}


def resolve_xlsx_address(ws: Any, cell_or_range: str) -> XlsxNode:
    """Parse cell address or range string, return XlsxNode."""
    if ":" in cell_or_range:
        cells = list(ws[cell_or_range])
        return XlsxNode(cells=cells)
    return XlsxNode(cell=ws[cell_or_range])


# ─── PPTX ─────────────────────────────────────────────────────────────────────


@dataclass
class PptxNode:
    slide: Any = None
    shape: Any = None
    paragraph: Any = None
    slide_index: int = -1
    shape_name: str = ""
    para_index: int = -1


def build_pptx_index(prs: Any) -> dict[str, Any]:
    """Scan presentation and build slide index."""
    slides = []
    for i, slide in enumerate(prs.slides):
        title = ""
        for shape in slide.shapes:
            if shape.has_text_frame and shape.name.startswith("Title"):
                title = shape.text_frame.text
                break

        slides.append(
            {
                "index": i,
                "title": title,
                "shape_count": len(slide.shapes),
                "has_table": any(shape.has_table for shape in slide.shapes),
                "has_chart": any(shape.has_chart for shape in slide.shapes),
                "has_image": any(
                    shape.shape_type == 13  # MSO_SHAPE_TYPE.PICTURE
                    for shape in slide.shapes
                ),
            }
        )

    layouts = [layout.name for layout in prs.slide_layouts]

    return {
        "slide_count": len(prs.slides),
        "available_layouts": layouts,
        "slides": slides,
    }


def resolve_pptx_address(prs: Any, address: str) -> PptxNode:
    """
    Parse slide/shape/paragraph address string.

    Format: slide[N]/shape[name] or slide[N]/shape[name]/pM
    """
    pattern = re.match(r"^slide\[(\d+)\]/shape\[(.+?)\](?:/p(\d+))?$", address)
    if not pattern:
        raise AddressError(f"Invalid PPTX address: '{address}'. Use slide[N]/shape[name] or slide[N]/shape[name]/pN")

    slide_idx = int(pattern.group(1))
    shape_name = pattern.group(2)
    para_idx = int(pattern.group(3)) if pattern.group(3) else None

    if slide_idx >= len(prs.slides):
        raise AddressError(f"Slide index {slide_idx} out of range. Presentation has {len(prs.slides)} slides.")

    slide = prs.slides[slide_idx]
    shape = None
    for s in slide.shapes:
        if s.name == shape_name:
            shape = s
            break

    if shape is None:
        available = [s.name for s in slide.shapes]
        raise AddressError(f"Shape '{shape_name}' not found on slide {slide_idx}. Available: {available}")

    if para_idx is not None:
        if not shape.has_text_frame:
            raise AddressError(f"Shape '{shape_name}' has no text frame.")
        paras = shape.text_frame.paragraphs
        if para_idx >= len(paras):
            raise AddressError(f"Paragraph index {para_idx} out of range. Shape has {len(paras)} paragraphs.")
        return PptxNode(
            slide=slide,
            shape=shape,
            paragraph=paras[para_idx],
            slide_index=slide_idx,
            shape_name=shape_name,
            para_index=para_idx,
        )

    return PptxNode(
        slide=slide,
        shape=shape,
        slide_index=slide_idx,
        shape_name=shape_name,
    )
