"""PPTX Design MCP server — thin wrapper over engine.py."""

from mcp.server.fastmcp import FastMCP

from pptx_design import engine

mcp = FastMCP("pptx-design")


@mcp.tool()
def set_background(
    file_path: str,
    slide_index: int,
    color_hex: str = "",
    image_path: str = "",
) -> dict:
    """Set slide background to solid color (hex) or image file."""
    return engine.set_background(file_path, slide_index, color_hex, image_path)


@mcp.tool()
def set_font_style(
    file_path: str,
    slide_index: int,
    shape_name: str,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    color_hex: str = "",
) -> dict:
    """Apply font name, size, bold, color to all runs in a shape."""
    return engine.set_font_style(
        file_path, slide_index, shape_name, font_name, font_size, bold, color_hex
    )


@mcp.tool()
def add_table(
    file_path: str,
    slide_index: int,
    rows: int,
    cols: int,
    data: list,
    left: float = 1.0,
    top: float = 2.0,
    width: float = 8.0,
    height: float = 3.0,
) -> dict:
    """Insert a table with row/col data on a slide."""
    return engine.add_table(file_path, slide_index, rows, cols, data, left, top, width, height)


@mcp.tool()
def add_chart(
    file_path: str,
    slide_index: int,
    chart_type: str,
    data: dict,
    title: str = "",
    left: float = 1.0,
    top: float = 2.0,
    width: float = 6.0,
    height: float = 4.5,
) -> dict:
    """Add chart to slide. type: bar, line, pie. data: {categories, series}."""
    return engine.add_chart(file_path, slide_index, chart_type, data, title, left, top, width, height)


@mcp.tool()
def duplicate_slide(
    file_path: str,
    slide_index: int,
    insert_at: int = -1,
) -> dict:
    """Copy slide N to position insert_at (-1 = append at end)."""
    return engine.duplicate_slide(file_path, slide_index, insert_at)


@mcp.tool()
def export_pdf(
    file_path: str,
    output_path: str = "",
    open_after: bool = True,
) -> dict:
    """Export PPTX to PDF using LibreOffice or PowerPoint."""
    return engine.export_pdf(file_path, output_path, open_after)


@mcp.tool()
def add_image_to_all_slides(
    file_path: str,
    image_path: str,
    left: float = 0.1,
    top: float = 0.1,
    width: float = 1.0,
    height: float = 0.5,
) -> dict:
    """Add the same image (logo/watermark) to every slide at given position."""
    return engine.add_image_to_all_slides(file_path, image_path, left, top, width, height)


@mcp.tool()
def set_font_all_slides(
    file_path: str,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    color_hex: str = "",
) -> dict:
    """Apply font name/size/bold/color to every text run on all slides."""
    return engine.set_font_all_slides(file_path, font_name, font_size, bold, color_hex)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
