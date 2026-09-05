"""Ring-1 pure utility — low-level .docx formatting primitives. No MCP imports.

python-docx exposes fonts and paragraph spacing but stops short of the things
that make a document readable rather than merely correct: a shaded table
header, banded rows, a rule under a heading, a page number in the footer. Each
needs a hand-built OOXML element, which is why every one of them was missing
from the tool surface and why a model asked to make an executive brief
"readable for my director" left the tools and wrote python-docx by hand.

Everything here takes an already-open python-docx object and mutates it. No
file I/O, no snapshots, no receipts — the calling engine owns all of that.
"""

from __future__ import annotations

from typing import Any

# Word measures border width in eighths of a point.
_EIGHTHS_PER_POINT = 8
_MAX_BORDER_EIGHTHS = 96  # Word's own ceiling: 12pt

ALIGNMENTS: tuple[str, ...] = ("left", "center", "right", "justify")


class DocxStyleError(ValueError):
    """A style argument Word cannot represent, described in the caller's terms."""


def parse_hex(color: str, field: str = "color") -> str:
    """Normalise '#0B1D3A' or '0b1d3a' to bare uppercase 'RRGGBB'.

    Word stores fills and colours as bare six-digit hex. A caller who passes
    'navy' or '#fff' gets told exactly that rather than a silently ignored
    argument, which is how a shading call comes back successful having changed
    nothing visible.
    """
    text = str(color).strip().lstrip("#")
    if len(text) != 6 or any(c not in "0123456789abcdefABCDEF" for c in text):
        raise DocxStyleError(f"{field}='{color}' is not a 6-digit hex colour. Write it as '0B1D3A' or '#0B1D3A'.")
    return text.upper()


def tint(color: str, amount: float) -> str:
    """Mix a colour toward white. amount 0 leaves it, 1 returns white.

    Band fills and callout backgrounds have to be derived from the accent
    rather than picked separately, or a caller who passes one brand colour
    still gets a document with somebody else's grey in it.
    """
    base = parse_hex(color, "color")
    ratio = max(0.0, min(float(amount), 1.0))
    channels = (int(base[i : i + 2], 16) for i in (0, 2, 4))
    mixed = (round(value + (255 - value) * ratio) for value in channels)
    return "".join(f"{value:02X}" for value in mixed)


def _qn(tag: str) -> Any:
    from docx.oxml.ns import qn  # type: ignore[import-untyped]

    return qn(tag)


def _element(tag: str) -> Any:
    from docx.oxml import OxmlElement  # type: ignore[import-untyped]

    return OxmlElement(tag)


def set_cell_fill(cell: Any, color: str) -> None:
    """Shade one table cell. `color` is hex, with or without a leading '#'."""
    fill = parse_hex(color, "fill")
    properties = cell._tc.get_or_add_tcPr()
    for existing in properties.findall(_qn("w:shd")):
        properties.remove(existing)
    shading = _element("w:shd")
    shading.set(_qn("w:val"), "clear")
    shading.set(_qn("w:color"), "auto")
    shading.set(_qn("w:fill"), fill)
    properties.append(shading)


def set_paragraph_rule(paragraph: Any, color: str = "000000", width_pt: float = 1.0, edge: str = "bottom") -> None:
    """Draw a horizontal rule on one edge of a paragraph.

    This is how a designed document separates a kicker from a title without an
    image. There is no python-docx API for it: the border lives in w:pBdr.
    """
    if edge not in {"top", "bottom"}:
        raise DocxStyleError(f"edge='{edge}' is not a paragraph rule edge. Use 'top' or 'bottom'.")
    stroke = parse_hex(color, "rule color")
    eighths = max(1, min(int(round(float(width_pt) * _EIGHTHS_PER_POINT)), _MAX_BORDER_EIGHTHS))

    properties = paragraph._p.get_or_add_pPr()
    borders = properties.find(_qn("w:pBdr"))
    if borders is None:
        borders = _element("w:pBdr")
        properties.append(borders)
    for existing in borders.findall(_qn(f"w:{edge}")):
        borders.remove(existing)
    border = _element(f"w:{edge}")
    border.set(_qn("w:val"), "single")
    border.set(_qn("w:sz"), str(eighths))
    border.set(_qn("w:space"), "4")
    border.set(_qn("w:color"), stroke)
    borders.append(border)


def set_alignment(paragraph: Any, align: str) -> None:
    """Align a paragraph. One of left, center, right, justify."""
    from docx.enum.text import WD_ALIGN_PARAGRAPH  # type: ignore[import-untyped]

    key = str(align).strip().lower()
    if key not in ALIGNMENTS:
        raise DocxStyleError(f"align='{align}' is not valid. Use one of: {', '.join(ALIGNMENTS)}.")
    paragraph.alignment = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }[key]


def set_spacing(
    paragraph: Any,
    line_spacing: float = 0.0,
    space_before: float = 0.0,
    space_after: float = 0.0,
) -> list[str]:
    """Set line spacing (a multiplier) and space before/after (points).

    Returns the names actually changed, so a caller can report "nothing to do"
    instead of claiming a write it did not make. Zero means "leave alone";
    negative is refused rather than quietly clamped.
    """
    from docx.shared import Pt  # type: ignore[import-untyped]

    changed: list[str] = []
    for name, value in (
        ("line_spacing", line_spacing),
        ("space_before", space_before),
        ("space_after", space_after),
    ):
        if value < 0:
            raise DocxStyleError(f"{name}={value} is negative. Use 0 to leave it unchanged.")
    if line_spacing:
        paragraph.paragraph_format.line_spacing = float(line_spacing)
        changed.append("line_spacing")
    if space_before:
        paragraph.paragraph_format.space_before = Pt(float(space_before))
        changed.append("space_before")
    if space_after:
        paragraph.paragraph_format.space_after = Pt(float(space_after))
        changed.append("space_after")
    return changed


def all_runs(paragraph: Any) -> list[Any]:
    """Every run in a paragraph, including ones nested inside a hyperlink.

    `paragraph.runs` returns only direct children, so a paragraph whose text
    sits inside a `w:hyperlink` reports zero runs while `paragraph.text` reads
    fine. Formatting it through `.runs` changes nothing and says it succeeded.

    Adding a run holding `paragraph.text` looks like the fix and duplicates the
    text, because the original run is still there inside the hyperlink. The
    runs have to be found where they are.
    """
    from docx.text.run import Run  # type: ignore[import-untyped]

    return [Run(element, paragraph) for element in paragraph._p.findall(f".//{_qn('w:r')}")]


def style_runs(
    paragraph: Any,
    font_name: str = "",
    font_size: float = 0.0,
    bold: str = "",
    italic: str = "",
    color: str = "",
    all_caps: str = "",
) -> list[str]:
    """Apply run-level formatting to every run in a paragraph.

    bold/italic/all_caps are tristate strings: "true", "false", "".
    """
    from docx.shared import Pt, RGBColor  # type: ignore[import-untyped]

    runs = all_runs(paragraph)
    rgb = RGBColor.from_string(parse_hex(color, "color")) if color else None
    changed: list[str] = []
    for run in runs:
        if font_name:
            run.font.name = font_name
        if font_size:
            run.font.size = Pt(float(font_size))
        for field, value in (("bold", bold), ("italic", italic), ("all_caps", all_caps)):
            flag = _tristate(value, field)
            if flag is not None:
                setattr(run.font, field, flag)
        if rgb is not None:
            run.font.color.rgb = rgb
    for field, value in (
        ("font_name", font_name),
        ("font_size", font_size),
        ("bold", bold),
        ("italic", italic),
        ("color", color),
        ("all_caps", all_caps),
    ):
        if value:
            changed.append(field)
    return changed


def _tristate(value: str, field: str) -> bool | None:
    text = str(value).strip().lower()
    if text in {"", "none", "unchanged"}:
        return None
    if text in {"true", "yes", "1"}:
        return True
    if text in {"false", "no", "0"}:
        return False
    raise DocxStyleError(f"{field}='{value}' is not understood. Use 'true', 'false', or '' to leave it alone.")


def add_page_number(paragraph: Any, prefix: str = "") -> None:
    """Append a live PAGE field so the footer numbers itself.

    Writing the literal page number is the obvious thing and is wrong on every
    page but one. Word wants a field code, which python-docx has no API for.
    """
    if prefix:
        paragraph.add_run(prefix)
    run = paragraph.add_run()
    begin = _element("w:fldChar")
    begin.set(_qn("w:fldCharType"), "begin")
    instr = _element("w:instrText")
    instr.set(_qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = _element("w:fldChar")
    end.set(_qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def set_column_widths(table: Any, widths_cm: list[float]) -> None:
    """Fix column widths in centimetres.

    Word only honours per-cell widths, and only with autofit off, so setting
    `table.columns[i].width` alone does nothing visible in most documents.
    """
    from docx.shared import Cm  # type: ignore[import-untyped]

    if not widths_cm:
        return
    table.autofit = False
    for index, width in enumerate(widths_cm):
        if index >= len(table.columns) or not width:
            continue
        size = Cm(float(width))
        for cell in table.columns[index].cells:
            cell.width = size


# A link that only reads as a link is not a link. Word draws these in the
# document's hyperlink colour, so the values below only apply when a caller
# passes none.
_LINK_COLOR = "0563C1"


def add_hyperlink(paragraph: Any, url: str, text: str = "", color: str = _LINK_COLOR, underline: bool = True) -> Any:
    """Append a real, clickable hyperlink run to a paragraph. Returns the run.

    python-docx has no API for this: a `w:hyperlink` needs a relationship on the
    containing part, and a run written without one is blue underlined text that
    does nothing when clicked. A user review asked for chart `public_url` links
    in the board paper, and text that looks like a link and is not would have
    been worse than the plain URL it replaced.

    `url` is written verbatim as an external relationship target. Whether it is
    reachable is the caller's business -- Word will not check either.
    """
    from docx.opc.constants import RELATIONSHIP_TYPE as RT  # type: ignore[import-untyped]

    part = paragraph.part
    r_id = part.relate_to(str(url), RT.HYPERLINK, is_external=True)

    link = _element("w:hyperlink")
    link.set(_qn("r:id"), r_id)

    run = _element("w:r")
    properties = _element("w:rPr")
    if color:
        node = _element("w:color")
        node.set(_qn("w:val"), parse_hex(color, "color"))
        properties.append(node)
    if underline:
        node = _element("w:u")
        node.set(_qn("w:val"), "single")
        properties.append(node)
    run.append(properties)

    label = _element("w:t")
    # Without this, Word collapses a label with leading or trailing spaces.
    label.set(_qn("xml:space"), "preserve")
    label.text = str(text) if text else str(url)
    run.append(label)

    link.append(run)
    paragraph._p.append(link)
    return run
