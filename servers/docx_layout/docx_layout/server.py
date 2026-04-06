"""DOCX Layout MCP server — styles, fonts, margins, images, export."""

from mcp.server.fastmcp import FastMCP

from docx_layout import engine

mcp = FastMCP("docx-layout")


@mcp.tool()
def set_heading(file_path: str, paragraph_index: int, level: int) -> dict:
    """Apply Heading 1-6 style to paragraph N. level must be 1-6."""
    return engine.set_heading(file_path, paragraph_index, level)


@mcp.tool()
def set_font(
    file_path: str,
    paragraph_index: int,
    font_name: str = "",
    font_size: float = 0,
    bold: bool = False,
    italic: bool = False,
) -> dict:
    """Set font name/size/bold/italic on all runs in paragraph N."""
    return engine.set_font(file_path, paragraph_index, font_name, font_size, bold, italic)


@mcp.tool()
def set_paragraph_style(file_path: str, paragraph_index: int, style_name: str) -> dict:
    """Apply named style from document gallery to paragraph N."""
    return engine.set_paragraph_style(file_path, paragraph_index, style_name)


@mcp.tool()
def add_image(
    file_path: str,
    paragraph_index: int,
    image_path: str,
    width_inches: float = 4.0,
) -> dict:
    """Insert image into paragraph N. Formats: PNG, JPG, GIF, BMP, TIFF."""
    return engine.add_image(file_path, paragraph_index, image_path, width_inches)


@mcp.tool()
def set_page_margins(
    file_path: str,
    top: float = 2.54,
    bottom: float = 2.54,
    left: float = 2.54,
    right: float = 2.54,
) -> dict:
    """Set page margins in cm (top/bottom/left/right) for all sections."""
    return engine.set_page_margins(file_path, top, bottom, left, right)


@mcp.tool()
def add_header_footer(
    file_path: str,
    text: str,
    location: str = "header",
) -> dict:
    """Set header or footer text. location: 'header' or 'footer'."""
    return engine.add_header_footer(file_path, text, location)


@mcp.tool()
def export_pdf(file_path: str, output_path: str = "", open_after: bool = True) -> dict:
    """Export .docx to PDF. Requires Word (Win/Mac) or LibreOffice."""
    return engine.export_pdf(file_path, output_path, open_after)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
